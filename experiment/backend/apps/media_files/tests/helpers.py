"""Making real uploads for tests: genuine JPEG/PDF bytes, each different."""
import io

import pypdfium2 as pdfium
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.media_files import service


def jpeg_bytes(seed: int = 0, size=(640, 480)) -> bytes:
    """A real JPEG that differs for each `seed` (so duplicates can be told apart)."""
    image = Image.new("RGB", size, ((seed * 37) % 256, (seed * 91) % 256, (seed * 53) % 256))
    out = io.BytesIO()
    image.save(out, "JPEG")
    return out.getvalue()


def pdf_bytes(pages: int = 2) -> bytes:
    pdf = pdfium.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(595, 842)
    out = io.BytesIO()
    pdf.save(out)
    pdf.close()
    return out.getvalue()


def upload_file(name: str, data: bytes, content_type: str = "application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def attach_media(job, user, *, photos: int = 3, documents: int = 1):
    """What a complete job has: its photographs and a title deed, through the real upload path."""
    if photos:
        service.upload(job.pk, user, service.PHOTOS, [
            upload_file(f"site-{i}.jpg", jpeg_bytes(i + 1)) for i in range(photos)
        ])
    if documents:
        service.upload(job.pk, user, service.DOCUMENTS, [
            upload_file(f"deed-{i}.pdf", pdf_bytes(2 + i)) for i in range(documents)
        ], doc_type="title_deed")
