"""Reading a title deed into the lead, on our own server (title_deed.py)."""
from decimal import Decimal

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.banks.models import Bank
from apps.jobs.models import Job, Property
from apps.media_files import title_deed
from apps.media_files.tests.helpers import pdf_bytes, upload_file

pytestmark = pytest.mark.django_db

UNIT_DEED = """Government of Dubai - Dubai Land Department
Title Deed
Issue Date: 12/03/2024
Property Type: Unit
Community: Marsa Dubai
Plot No: 392
Municipality No: 392-123
Building No: 1
Building Name: Marina Gate 1
Property No: 2304
Floor No: 23
Area (sq m): 120.50
Owner Name (English): Layla Hassan   Share: 100%
"""

VILLA_DEED = """Title Deed
Property Type: Villa
Community: Arabian Ranches 2
Land No: 6011-1200
Land Area (sq m): 418.06
Built Up Area (sq m): 310.20
Owners Name: Omar Al Farsi
Owners Name: Huda Al Farsi
"""


def text_pdf(text: str) -> bytes:
    """A real one-page PDF whose text layer holds `text`, as a digital deed has."""
    lines = text.strip("\n").split("\n")
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    stream = "BT /F1 10 Tf 40 800 Td 14 TL " + " ".join(f"({esc(line)}) Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out.encode("latin-1")))
        out += f"{i} 0 obj\n{body}\nendobj\n"
    xref = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


class TestParse:
    def test_a_unit_deed(self):
        deed = title_deed.parse(UNIT_DEED)
        assert deed.is_title_deed
        numbers = (deed.property_no, deed.plot_no, deed.municipality_no, deed.building_no)
        assert numbers == ("2304", "392", "392-123", "1")
        assert (deed.building_name, deed.community) == ("Marina Gate 1", "Marsa Dubai")
        assert deed.unit_area_sqm == Decimal("120.50")
        assert deed.owners == ["Layla Hassan"]

    def test_a_villa_deed(self):
        deed = title_deed.parse(VILLA_DEED)
        assert deed.plot_no == "6011-1200"
        assert (deed.land_area_sqm, deed.unit_area_sqm) == (Decimal("418.06"), Decimal("310.20"))
        assert deed.owners == ["Omar Al Farsi", "Huda Al Farsi"]

    def test_an_owners_heading_isnt_taken_for_an_owner(self):
        deed = title_deed.parse("Title Deed\nOwners\nOwner Name (English): Omar Al Farsi Share: 50%\n"
                                "Owner Name (English): Huda Al Farsi Share: 50%\n")
        assert deed.owners == ["Omar Al Farsi", "Huda Al Farsi"]

    def test_text_that_isnt_a_deed_finds_nothing(self):
        assert not title_deed.parse("Dear valuer, please value this property.").found()

    def test_the_text_layer_is_read_from_a_digital_pdf(self):
        text = title_deed.read_text(text_pdf(UNIT_DEED), "application/pdf")
        assert "Marina Gate 1" in text and "392-123" in text


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_presets")


@pytest.fixture
def ops():
    return User.objects.create(username="ops", email="ops@example.com", roles=[Role.OPS])


@pytest.fixture
def job(ops):
    return Job.objects.create(bank=Bank.objects.create(name="Test Bank"), admin_user=ops,
                              property=Property.objects.create(applicant_name="Layla Hassan"))


def upload(user, job, data, *, name="deed.pdf", doc_type="title_deed"):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(f"/api/jobs/{job.pk}/documents/", {"files": [upload_file(name, data)], "doc_type": doc_type},
                       format="multipart")


class TestUpload:
    def test_a_title_deed_fills_the_empty_fields(self, ops, job):
        res = upload(ops, job, text_pdf(UNIT_DEED))
        assert res.status_code == 201, res.json()
        assert res.json()["deed"]["read"] is True
        job = Job.objects.get(pk=job.pk)
        p = job.property
        assert (p.title_doc_type, p.title_doc_property_no, p.title_doc_plot_no, p.title_doc_municipality_no,
                p.title_doc_building_no) == ("title_deed", "2304", "392", "392-123", "1")
        assert (p.building_name, p.community_name, p.ownership_name) == ("Marina Gate 1", "Marsa Dubai", "Layla Hassan")
        assert (job.summary.bua_sqm, job.summary.bua_source) == (Decimal("120.50"), "title_deed")
        assert "Plot No. as per document" in res.json()["deed"]["filled"]
        # Saved like a person's edit: audited, to whoever uploaded the deed.
        assert AuditLog.objects.get(job=job, field_name="title_doc_plot_no").changed_by == ops

    def test_what_is_already_entered_is_kept_and_reported(self, ops, job):
        job.property.building_name = "MG1"
        job.property.title_doc_plot_no = "999"
        job.property.save()
        res = upload(ops, job, text_pdf(UNIT_DEED)).json()["deed"]
        p = Property.objects.get(pk=job.property.pk)
        assert p.title_doc_plot_no == "999" and "Plot No. as per document" in res["different"]
        # The deed's spelling goes in the "as per document" field instead.
        assert (p.building_name, p.title_doc_building_name) == ("MG1", "Marina Gate 1")

    def test_a_villa_takes_the_land_area_as_its_plot(self, ops, job):
        job.summary.property_category = "villa"
        job.summary.save()
        upload(ops, job, text_pdf(VILLA_DEED))
        summary = Job.objects.get(pk=job.pk).summary
        assert (summary.plot_area_sqm, summary.plot_area_source) == (Decimal("418.06"), "title_deed")
        assert summary.bua_sqm == Decimal("310.20")

    def test_other_documents_arent_read(self, ops, job):
        res = upload(ops, job, text_pdf(UNIT_DEED), doc_type="spa")
        assert res.status_code == 201 and "deed" not in res.json()
        assert Property.objects.get(pk=job.property.pk).title_doc_plot_no == ""

    def test_a_scan_with_no_text_is_still_uploaded(self, ops, job, monkeypatch):
        monkeypatch.setattr(title_deed.shutil, "which", lambda _: None)  # no OCR on this machine
        res = upload(ops, job, pdf_bytes(1))
        assert res.status_code == 201
        assert res.json()["deed"] == {"read": False, "filled": [], "different": []}


class TestReadBeforeTheLeadExists:
    def test_the_form_gets_the_deeds_fields_and_nothing_is_kept(self, ops):
        from apps.media_files.models import Document

        client = APIClient()
        client.force_authenticate(ops)
        res = client.post("/api/title-deed/read/", {"file": upload_file("deed.pdf", text_pdf(UNIT_DEED))},
                          format="multipart")
        assert res.status_code == 200, res.json()
        assert res.json() == {"read": True, "fields": {
            "building_name": "Marina Gate 1", "community_name": "Marsa Dubai",
            "ownership_name": ["Layla Hassan"], "property_no": "2304"}}
        assert not Document.objects.exists()

    def test_signed_in_only(self):
        res = APIClient().post("/api/title-deed/read/", {"file": upload_file("deed.pdf", text_pdf(UNIT_DEED))},
                               format="multipart")
        assert res.status_code in (401, 403)
