"""What happens to a file between 'uploaded' and 'stored'."""
import io
import os

import pillow_heif
import pytest
from PIL import Image

from apps.media_files import processing
from apps.media_files.tests.helpers import jpeg_bytes, pdf_bytes


def heic_bytes(size=(640, 480)) -> bytes:
    out = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", size, "blue")).save(out, format="HEIF")
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


class TestSniff:
    def test_reads_the_kind_from_the_bytes(self):
        assert processing.sniff(jpeg_bytes()[:16]) == "jpeg"
        assert processing.sniff(heic_bytes()[:16]) == "heic"
        assert processing.sniff(pdf_bytes()[:16]) == "pdf"
        png = io.BytesIO()
        Image.new("RGB", (4, 4)).save(png, "PNG")
        assert processing.sniff(png.getvalue()[:16]) == "png"

    def test_a_name_or_claimed_type_proves_nothing(self):
        assert processing.sniff(b"MZ\x90\x00 this is an executable") is None
        assert processing.sniff(b"<html><script>alert(1)</script>") is None
        assert processing.sniff(b"") is None


class TestImages:
    def test_heic_from_a_phone_becomes_a_jpeg(self):
        result = processing.process_image(heic_bytes())
        assert opened(result.main).format == "JPEG" and (result.width, result.height) == (640, 480)

    def test_big_photos_are_shrunk_and_thumbnailed(self):
        result = processing.process_image(jpeg_bytes(size=(6000, 4000)))
        assert result.width == processing.IMAGE_MAX_EDGE and result.height == 1600
        assert max(opened(result.thumb).size) == processing.THUMB_EDGE
        assert len(result.main) < len(jpeg_bytes(size=(6000, 4000)))

    def test_transparency_becomes_white_paper_not_black(self):
        out = io.BytesIO()
        Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(out, "PNG")
        pixel = opened(processing.process_image(out.getvalue()).main).getpixel((20, 20))
        assert min(pixel) > 240

    def test_camera_metadata_including_gps_is_stripped(self):
        image = Image.new("RGB", (200, 100), "green")
        exif = Image.Exif()
        exif[0x010F] = "SomeCamera"  # make
        exif[0x8825] = {1: "N", 2: (25.0, 2.0, 25.0)}  # GPS block
        out = io.BytesIO()
        image.save(out, "JPEG", exif=exif)
        assert len(opened(out.getvalue()).getexif()) > 0  # the test file really has metadata
        assert len(opened(processing.process_image(out.getvalue()).main).getexif()) == 0

    def test_a_rotated_phone_photo_is_stored_upright(self):
        image = Image.new("RGB", (200, 100), "red")
        exif = Image.Exif()
        exif[0x0112] = 6  # "rotate 90° clockwise to view"
        out = io.BytesIO()
        image.save(out, "JPEG", exif=exif)
        result = processing.process_image(out.getvalue())
        assert (result.width, result.height) == (100, 200)

    def test_a_damaged_image_is_refused_with_a_reason(self):
        with pytest.raises(processing.Rejected, match="damaged"):
            processing.process_image(b"\xff\xd8\xff" + b"not really an image")

    def test_a_half_downloaded_image_is_refused(self):
        noisy = Image.frombytes("RGB", (600, 400), os.urandom(600 * 400 * 3))  # (a flat colour compresses to nothing)
        out = io.BytesIO()
        noisy.save(out, "JPEG")
        with pytest.raises(processing.Rejected, match="damaged"):
            processing.process_image(out.getvalue()[: len(out.getvalue()) // 2])

    def test_truncated_images_are_refused_even_after_weasyprint_has_relaxed_pillow(self):
        """WeasyPrint sets Pillow's global tolerance for truncated images on at import."""
        from PIL import ImageFile

        noisy = Image.frombytes("RGB", (600, 400), os.urandom(600 * 400 * 3))
        out = io.BytesIO()
        noisy.save(out, "JPEG")
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            with pytest.raises(processing.Rejected, match="damaged"):
                processing.process_image(out.getvalue()[: len(out.getvalue()) // 2])
            assert ImageFile.LOAD_TRUNCATED_IMAGES is True  # put back as found
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = False

    def test_an_absurdly_large_image_is_refused_before_it_is_decoded(self, monkeypatch):
        monkeypatch.setattr(processing, "MAX_PIXELS", 100)
        with pytest.raises(processing.Rejected, match="too large"):
            processing.process_image(jpeg_bytes(size=(64, 64)))


class TestPdfs:
    def test_counts_pages_and_draws_a_thumbnail(self):
        result = processing.process_pdf(pdf_bytes(3))
        assert result.page_count == 3 and opened(result.thumb).format == "JPEG"

    def test_garbage_is_refused(self):
        with pytest.raises(processing.Rejected, match="couldn't be read"):
            processing.process_pdf(b"%PDF-1.4 this is not a pdf")

    def test_too_many_pages_are_refused(self, monkeypatch):
        monkeypatch.setattr(processing, "MAX_PDF_PAGES", 2)
        with pytest.raises(processing.Rejected, match="limit"):
            processing.process_pdf(pdf_bytes(3))

    def test_pages_can_be_rendered_for_the_report_up_to_a_cap(self):
        pages, total = processing.render_pdf_pages(pdf_bytes(5), max_pages=2)
        assert len(pages) == 2 and total == 5
