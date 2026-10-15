"""Turning what was uploaded into what is stored.

Nothing about an upload is trusted: not its name, not its declared type. The
kind is read from the file's own first bytes, images are decoded and
re-encoded (which also strips camera metadata such as GPS), and anything that
won't decode is rejected with a reason the user can act on.

Photos and document scans are stored as JPEG whatever they arrived as (HEIC
from an iPhone included), shrunk to a size that is sharp on a printed A4 page
without making every report huge. PDFs are kept exactly as uploaded; they are
only read, to count pages and draw a thumbnail.
"""

from __future__ import annotations

import io
from contextlib import contextmanager
from dataclasses import dataclass

import pillow_heif
import pypdfium2 as pdfium
from PIL import Image, ImageFile, ImageOps

pillow_heif.register_heif_opener()

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 100_000_000  # a guard against decompression bombs, well above any phone camera
IMAGE_MAX_EDGE = 2400
THUMB_EDGE = 480
JPEG_QUALITY = 85
MAX_PDF_PAGES = 150

HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}


class Rejected(Exception):
    """The upload can't be accepted; `str(exc)` says why, in words for the user."""


@dataclass
class ProcessedImage:
    main: bytes
    thumb: bytes
    width: int
    height: int


@dataclass
class ProcessedPdf:
    thumb: bytes
    page_count: int


def sniff(head: bytes) -> str | None:
    """The real kind of a file, from its first bytes: jpeg, png, heic, pdf."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return "heic"
    if head.startswith(b"%PDF-"):
        return "pdf"
    return None


@contextmanager
def _strict_decoding():
    """Refuse truncated images. WeasyPrint switches Pillow's global tolerance
    for them *on* when it is imported, so once a process has rendered a report
    a half-uploaded photo would otherwise be accepted, with the missing part
    filled in grey."""
    previous = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        yield
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = previous


def _jpeg(image: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)  # no exif: stripped
    return out.getvalue()


def _flatten(image: Image.Image) -> Image.Image:
    """RGB, with any transparency shown as white (paper), not black."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        page = Image.new("RGB", rgba.size, "white")
        page.paste(rgba, mask=rgba.getchannel("A"))
        return page
    return image.convert("RGB")


def process_image(data: bytes) -> ProcessedImage:
    try:
        with _strict_decoding(), Image.open(io.BytesIO(data)) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise Rejected("The image is too large to process.")
            opened.load()
            image = _flatten(ImageOps.exif_transpose(opened))
    except Rejected:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise Rejected("The image is damaged or incomplete and couldn't be read.") from exc

    image.thumbnail((IMAGE_MAX_EDGE, IMAGE_MAX_EDGE), Image.Resampling.LANCZOS)
    width, height = image.size
    main = _jpeg(image)
    thumb_image = image.copy()
    thumb_image.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.Resampling.LANCZOS)
    return ProcessedImage(main=main, thumb=_jpeg(thumb_image, 78), width=width, height=height)


def _open_pdf(data: bytes) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise Rejected("The PDF couldn't be read. It may be damaged or password-protected.") from exc


def process_pdf(data: bytes) -> ProcessedPdf:
    pdf = _open_pdf(data)
    try:
        pages = len(pdf)
        if pages == 0:
            raise Rejected("The PDF has no pages.")
        if pages > MAX_PDF_PAGES:
            raise Rejected(f"The PDF has {pages} pages; the limit is {MAX_PDF_PAGES}.")
        page = pdf[0]
        scale = THUMB_EDGE / max(page.get_width(), 1)
        thumb = _flatten(page.render(scale=scale).to_pil())
        return ProcessedPdf(thumb=_jpeg(thumb, 78), page_count=pages)
    except pdfium.PdfiumError as exc:
        raise Rejected("The PDF couldn't be read. It may be damaged.") from exc
    finally:
        pdf.close()


# --- renditions for the report ------------------------------------------------------


def downscale_jpeg(data: bytes, edge: int, quality: int = 80) -> bytes:
    """A smaller copy for the report, so a dozen photos don't make it huge."""
    with Image.open(io.BytesIO(data)) as image:
        image = _flatten(image)
    image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return _jpeg(image, quality)


def render_pdf_pages(
    data: bytes, *, max_pages: int, width_px: int = 1100, quality: int = 78
) -> tuple[list[bytes], int]:
    """The first `max_pages` pages of a PDF as JPEGs, and its total page count."""
    pdf = _open_pdf(data)
    try:
        total = len(pdf)
        pages = []
        for index in range(min(total, max_pages)):
            page = pdf[index]
            scale = width_px / max(page.get_width(), 1)
            pages.append(_jpeg(_flatten(page.render(scale=scale).to_pil()), quality))
        return pages, total
    finally:
        pdf.close()
