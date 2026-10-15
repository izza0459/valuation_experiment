"""Photographs and documents as they appear in the report."""
import json

import pytest
from django.core.management import call_command

from apps.accounts.models import Role, User
from apps.banks.models import Bank
from apps.jobs.models import Job, Property
from apps.media_files import service
from apps.media_files.models import Photo
from apps.media_files.tests.helpers import jpeg_bytes, pdf_bytes, upload_file
from apps.reports.context import build_context
from apps.reports.issue import issue_blockers
from apps.reports.render import choose_template, render_html

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def presets():
    call_command("seed_presets")


@pytest.fixture
def boss():
    return User.objects.create(username="boss", email="boss@example.com", roles=[Role.ADMIN])


@pytest.fixture
def job(boss):
    j = Job.objects.create(
        bank=Bank.objects.create(name="Test Bank"),
        property=Property.objects.create(unit_number="312", building_name="Rukan Residences"),
        valuer=boss, registered_valuer=boss,
    )
    j.summary.makani_number = "12345 67890"
    j.summary.dewa_number = "555-1"
    j.summary.save()
    return Job.objects.get(pk=j.pk)


def photos(job, user, n, start=1, **kw):
    return service.upload(
        job.pk, user, service.PHOTOS, [upload_file(f"p{start + i}.jpg", jpeg_bytes(start + i)) for i in range(n)], **kw
    ).created


def html(job):
    return render_html(choose_template(job), build_context(job))


class TestContext:
    def test_the_executive_summary_takes_the_first_three_general_photographs(self, job, boss):
        photos(job, boss, 5)
        ctx = build_context(job)
        assert len(ctx["photos"]) == 5 and len(ctx["exec_photos"]) == 3
        assert [p["key"] for p in ctx["exec_photos"]] == [p["key"] for p in ctx["photos"][:3]]

    def test_makani_and_dewa_photos_stay_out_of_the_executive_summary(self, job, boss):
        photos(job, boss, 1, start=20, slot="makani")
        photos(job, boss, 2, start=1)
        ctx = build_context(job)
        assert len(ctx["photos"]) == 3 and len(ctx["exec_photos"]) == 2
        assert all(p["slot"] == "general" for p in ctx["exec_photos"])

    def test_the_makani_and_dewa_photos_say_which_number_they_show(self, job, boss):
        photos(job, boss, 1, start=20, slot="makani")
        photos(job, boss, 1, start=21, slot="dewa")
        captions = {p["slot"]: p["caption"] for p in build_context(job)["photos"]}
        assert captions == {"makani": "Makani No. 12345 67890", "dewa": "DEWA No. 555-1"}

    def test_a_written_caption_wins_and_excluded_photos_are_left_out(self, job, boss):
        first, second = photos(job, boss, 2)
        service.update(job.pk, boss, service.PHOTOS, first.pk, 1, {"caption": "Front elevation"})
        service.update(job.pk, boss, service.PHOTOS, second.pk, 1, {"include_in_report": False})
        ctx = build_context(job)
        assert [p["caption"] for p in ctx["photos"]] == ["Front elevation"]

    def test_documents_carry_their_type_and_kind(self, job, boss):
        service.upload(job.pk, boss, service.DOCUMENTS, [upload_file("d.pdf", pdf_bytes(3))], doc_type="title_deed")
        service.upload(job.pk, boss, service.DOCUMENTS, [upload_file("s.jpg", jpeg_bytes(4))], doc_type="floor_plan")
        docs = build_context(job)["documents"]
        assert [(d["title"], d["kind"]) for d in docs] == [("Title Deed", "pdf"), ("Floor Plan", "image")]

    def test_the_snapshot_holds_references_not_pictures(self, job, boss):
        photos(job, boss, 3)
        service.upload(job.pk, boss, service.DOCUMENTS, [upload_file("d.pdf", pdf_bytes(2))])
        snapshot = json.dumps(build_context(job))
        assert "base64" not in snapshot and len(snapshot) < 40_000


class TestRendering:
    def test_the_photographs_appear_in_the_summary_and_the_appendix(self, job, boss):
        photos(job, boss, 4)
        page = html(job)
        assert page.count("data:image/jpeg;base64,") == 3 + 4  # three in the summary, all four in the appendix
        assert "have not been attached" not in page and "No photographs have been attached" not in page

    def test_without_any_the_report_says_so(self, job):
        page = html(job)
        assert "No photographs have been attached" in page and "No documents have been attached" in page

    def test_a_pdf_document_appears_page_by_page(self, job, boss):
        service.upload(job.pk, boss, service.DOCUMENTS, [upload_file("d.pdf", pdf_bytes(3))], doc_type="spa")
        page = html(job)
        assert page.count("data:image/jpeg;base64,") == 3
        assert "Page 3 of 3" in page and "SPA" in page

    def test_a_long_document_is_cut_and_says_so(self, job, boss, monkeypatch):
        monkeypatch.setattr("apps.reports.media.DOCUMENT_MAX_PAGES", 2)
        service.upload(job.pk, boss, service.DOCUMENTS, [upload_file("d.pdf", pdf_bytes(5))])
        page = html(job)
        assert page.count("data:image/jpeg;base64,") == 2 and "The first 2 of 5 pages are shown" in page

    def test_captions_cannot_inject_markup(self, job, boss):
        item = photos(job, boss, 1)[0]
        service.update(job.pk, boss, service.PHOTOS, item.pk, 1, {"caption": "<script>alert(1)</script>"})
        assert "<script>alert(1)</script>" not in html(job)

    def test_a_missing_file_shows_a_marker_instead_of_breaking_the_report(self, job, boss, settings):
        item = photos(job, boss, 1)[0]
        (settings.MEDIA_ROOT / item.s3_key).unlink()
        assert "Photograph unavailable" in html(job)

    def test_a_stored_version_re_renders_with_the_same_pictures(self, job, boss):
        from apps.reports.generate import render_version_html
        from apps.reports.models import ReportVersion

        photos(job, boss, 3)
        version = ReportVersion.objects.create(
            job=job, job_version=1, template=choose_template(job), input_snapshot=build_context(job)
        )
        photos(job, boss, 2, start=30)  # added after the version was made
        assert render_version_html(version).count("data:image/jpeg;base64,") == 6


class TestIssuing:
    def test_issue_is_blocked_while_a_file_is_missing(self, job, boss, settings):
        item = photos(job, boss, 1)[0]
        (settings.MEDIA_ROOT / item.s3_key).unlink()
        assert any("missing from storage" in b for b in issue_blockers(job))

    def test_issue_is_not_blocked_by_hidden_photographs_whose_file_is_gone(self, job, boss, settings):
        item = photos(job, boss, 1)[0]
        service.update(job.pk, boss, service.PHOTOS, item.pk, 1, {"include_in_report": False})
        (settings.MEDIA_ROOT / Photo.objects.get(pk=item.pk).s3_key).unlink()
        assert not any("missing from storage" in b for b in issue_blockers(job))


def test_a_template_stored_before_documents_had_pages_still_renders(job, boss):
    """Older stored templates print `d.src`; it is the document's first page."""
    from apps.reports.models import ReportTemplate

    ReportTemplate.objects.create(
        name="Old", version="old1", css="",
        html="{% for d in documents %}<img src='{{ d.src }}'><i>{{ d.caption }}</i>{% endfor %}",
    )
    service.upload(job.pk, boss, service.DOCUMENTS, [upload_file("d.pdf", pdf_bytes(3))])
    page = render_html(ReportTemplate.objects.get(version="old1"), build_context(job))
    assert page.count("data:image/jpeg;base64,") == 1
