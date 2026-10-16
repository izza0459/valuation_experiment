"""Issuing: the final report is rendered and stored, and the job locked, in one
step, and only when everything that must be true is (CLAUDE.md §3)."""
import datetime

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.accounts.models import Role, User, ValuerProfile
from apps.banks.models import Bank
from apps.jobs.models import Job, JobTransition, Property
from apps.jobs.tests.test_transitions import fill_everything, get_to
from apps.jobs.workflow import JobStatus
from apps.reports import issue as issue_module
from apps.reports.generate import render_version_html
from apps.reports.issue import issue_blockers, issue_report, placeholders_in
from apps.reports.models import ReportTemplate, ReportVersion
from apps.reports.render import pdf_engine_available

pytestmark = pytest.mark.django_db

needs_pdf_engine = pytest.mark.skipif(
    not pdf_engine_available(), reason="WeasyPrint's system libraries aren't installed"
)

CLEAN_HTML = "<html><body><h1>{{ meta.ref_no }}</h1><p>{{ valuation_summary | length }} rows</p></body></html>"
FAKE_PDF = b"%PDF-1.7 fake"


def make_user(name, *, roles=None, licence=datetime.date(2099, 1, 1)):
    user = User.objects.create(
        username=name, email=f"{name}@example.com", first_name=name.title(), roles=roles or []
    )
    if licence is not None:
        ValuerProfile.objects.create(user=user, rera_registration_no=f"RERA-{name}", rera_licence_expiry=licence)
    return user


@pytest.fixture(autouse=True)
def storage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture(autouse=True)
def fake_engine(monkeypatch):
    """Most tests are about the rules, not the PDF engine."""
    monkeypatch.setattr(issue_module, "pdf_engine_available", lambda: True)
    monkeypatch.setattr(issue_module, "render_pdf", lambda html: FAKE_PDF)


@pytest.fixture
def boss():
    return make_user("boss", roles=[Role.ADMIN], licence=None)


@pytest.fixture
def clean_template():
    return ReportTemplate.objects.create(name="No placeholders", version="t1", html=CLEAN_HTML, css="")


@pytest.fixture
def approved(boss, clean_template):
    """A complete job, signed off and ready to issue."""
    dan, pat, ines = make_user("dan"), make_user("pat"), make_user("ines")
    job = Job.objects.create(
        bank=Bank.objects.create(name="Test Bank"),
        property=Property.objects.create(unit_number="312", building_name="Rukan Residences"),
        valuer=dan, inspected_by=dan, registered_valuer=dan, peer_reviewer=pat, counter_signatory=ines,
        admin_user=boss, report_template=clean_template,
    )
    fill_everything(job)
    return get_to(Job.objects.get(pk=job.pk), JobStatus.APPROVED_SIGNED).countersign(ines)


def issue(client_user, job):
    client = APIClient()
    client.force_authenticate(client_user)
    return client.post(
        f"/api/jobs/{job.pk}/transitions/", {"from": "approved_signed", "to": "issued"}, format="json"
    )


# --- finding placeholders ----------------------------------------------------------------------


class TestPlaceholders:
    def test_finds_both_forms_in_use(self):
        html = (
            '<p class="placeholder">[PLACEHOLDER – replace with approved wording: the disclaimer]</p>'
            "<p>[PLACEHOLDER – replace with approved wording] Granted title converted to freehold.</p>"
        )
        assert placeholders_in(html) == ["the disclaimer", "Granted title converted to freehold"]

    def test_names_read_as_text_not_as_escaped_html(self):
        assert placeholders_in("[PLACEHOLDER – x: the valuer&#39;s skills]") == ["the valuer's skills"]

    def test_lists_each_passage_once(self):
        html = "[PLACEHOLDER – x: same] [PLACEHOLDER – x: same]"
        assert placeholders_in(html) == ["same"]

    def test_clean_text_has_none(self):
        assert placeholders_in("<p>All approved.</p>") == []


# --- what blocks issuing -----------------------------------------------------------------------


class TestBlockers:
    def test_a_ready_job_has_none(self, approved):
        assert issue_blockers(approved) == []

    def test_the_shipped_template_blocks_until_the_legal_name_is_set(self, approved, settings):
        ReportTemplate.objects.update(active=False)  # nothing authored: the shipped default applies
        settings.REPORT_FIRM_LEGAL_NAME = ""
        blockers = issue_blockers(Job.objects.get(pk=approved.pk))
        assert any("placeholder" in b and "legal name" in b for b in blockers)

    def test_the_shipped_template_is_issuable_once_the_legal_name_is_set(self, approved, settings):
        ReportTemplate.objects.update(active=False)
        settings.REPORT_FIRM_LEGAL_NAME = "Example Valuations LLC"
        assert not any("placeholder" in b for b in issue_blockers(Job.objects.get(pk=approved.pk)))

    def test_a_placeholder_left_in_the_valuers_own_text_blocks_too(self, approved):
        ReportTemplate.objects.filter(version="t1").update(html="<p>{{ text.assumptions }}</p>")
        approved.summary.assumptions = "[PLACEHOLDER – replace with approved wording: the lease terms]"
        approved.summary.save()
        assert any("the lease terms" in b for b in issue_blockers(Job.objects.get(pk=approved.pk)))

    def test_an_expired_counter_signatory_licence_blocks(self, approved):
        ValuerProfile.objects.filter(user=approved.counter_signatory).update(
            rera_licence_expiry=datetime.date(2020, 1, 1)
        )
        assert any("Counter-signatory" in b and "licence" in b for b in issue_blockers(approved))

    def test_a_counter_signatory_with_no_profile_blocks(self, approved):
        ValuerProfile.objects.filter(user=approved.counter_signatory).delete()
        assert any("Counter-signatory" in b for b in issue_blockers(Job.objects.get(pk=approved.pk)))

    def test_an_expired_signing_valuer_licence_blocks(self, approved):
        ValuerProfile.objects.filter(user=approved.registered_valuer).update(
            rera_licence_expiry=datetime.date(2020, 1, 1)
        )
        assert any("Signing valuer" in b for b in issue_blockers(approved))

    def test_a_missing_pdf_engine_blocks_with_a_reason(self, approved, monkeypatch):
        monkeypatch.setattr(issue_module, "pdf_engine_available", lambda: False)
        assert any("PDF engine" in b for b in issue_blockers(approved))

    def test_an_incomplete_job_blocks(self, approved):
        approved.valuation.market_value = None
        approved.valuation.save()
        assert any("Incomplete" in b for b in issue_blockers(approved))


# --- issuing -----------------------------------------------------------------------------------


class TestIssuing:
    def test_issuing_stores_the_final_report_and_locks_the_job(self, approved, boss, storage):
        res = issue(boss, approved)
        assert res.status_code == 200, res.content

        approved.refresh_from_db()
        assert approved.status == JobStatus.ISSUED and approved.is_locked and approved.issued_at

        version = ReportVersion.objects.get(job=approved)
        assert version.issued_by == boss and version.issued_at
        assert version.template.version == "t1"
        assert (storage / version.pdf_s3_key).read_bytes() == FAKE_PDF
        assert version.input_snapshot["meta"]["is_draft"] is False

        log = JobTransition.objects.get(job=approved, to_status=JobStatus.ISSUED)
        assert log.by == boss and log.from_status == JobStatus.APPROVED_SIGNED

    def test_the_stored_report_re_renders_as_issued_whatever_happens_to_the_job(self, approved, boss):
        issue(boss, approved)
        version = ReportVersion.objects.get(job=approved)
        assert approved.bayut_internal_reference_no in render_version_html(version)
        assert version.input_snapshot["meta"]["ref_no"] == approved.bayut_internal_reference_no

    def test_an_issued_job_rejects_edits(self, approved, boss):
        issue(boss, approved)
        res = APIClient()
        res.force_authenticate(approved.valuer)
        out = res.patch(
            f"/api/jobs/{approved.pk}/tabs/valuation/", {"base_version": 0, "values": {"market_value": "1"}},
            format="json",
        )
        assert out.status_code == 409

    def test_only_an_admin_can_issue(self, approved):
        for user in (approved.valuer, approved.peer_reviewer, approved.counter_signatory):
            assert issue(user, approved).status_code == 403
        approved.refresh_from_db()
        assert approved.status == JobStatus.APPROVED_SIGNED and not ReportVersion.objects.exists()

    def test_a_blocked_job_says_why_and_stays_open(self, approved, boss):
        ValuerProfile.objects.filter(user=approved.counter_signatory).update(
            rera_licence_expiry=datetime.date(2020, 1, 1)
        )
        res = issue(boss, approved)
        assert res.status_code == 422
        assert any("licence" in b for b in res.json()["blockers"])
        approved.refresh_from_db()
        assert not approved.is_locked and not ReportVersion.objects.exists()

    def test_the_admin_is_offered_issue_and_sees_what_blocks_it(self, approved, boss, settings):
        settings.REPORT_FIRM_LEGAL_NAME = ""  # the shipped template then has a placeholder
        ReportTemplate.objects.update(active=False)
        client = APIClient()
        client.force_authenticate(boss)
        actions = client.get(f"/api/jobs/{approved.pk}/").json()["available_actions"]
        issue_action = next(a for a in actions if a["to"] == "issued")
        assert issue_action["label"] == "Issue report" and issue_action["enabled"] is False
        assert any("placeholder" in b for b in issue_action["blockers"])

    def test_nobody_else_is_offered_it(self, approved):
        client = APIClient()
        client.force_authenticate(approved.counter_signatory)
        actions = client.get(f"/api/jobs/{approved.pk}/").json()["available_actions"]
        assert all(a["to"] != "issued" for a in actions)

    def test_a_failed_render_leaves_the_job_open_and_nothing_stored(self, approved, boss, monkeypatch, storage):
        def boom(html):
            raise RuntimeError("renderer crashed")

        monkeypatch.setattr(issue_module, "render_pdf", boom)
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(boss)
        res = client.post(
            f"/api/jobs/{approved.pk}/transitions/", {"from": "approved_signed", "to": "issued"}, format="json"
        )
        assert res.status_code == 500
        approved.refresh_from_db()
        assert approved.status == JobStatus.APPROVED_SIGNED and not approved.is_locked
        assert not ReportVersion.objects.exists() and not list(storage.glob("reports/**/*.pdf"))

    def test_a_failure_after_the_pdf_is_stored_removes_the_file_and_the_row(self, approved, boss, monkeypatch, storage):
        def boom(self):
            raise RuntimeError("database went away")

        monkeypatch.setattr(Job, "issue", boom)
        with pytest.raises(RuntimeError), transaction.atomic():
            issue_report(approved, boss)
        assert not list(storage.glob("reports/**/*.pdf")) and not ReportVersion.objects.exists()


class TestDraftsAfterIssue:
    def test_no_draft_pdf_can_be_made_for_an_issued_job(self, approved, boss):
        issue(boss, approved)
        client = APIClient()
        client.force_authenticate(boss)
        res = client.post(f"/api/jobs/{approved.pk}/report/")
        assert res.status_code == 409 and res.json()["code"] == "locked"

    def test_the_issued_pdf_is_downloadable_and_marked_issued(self, approved, boss):
        issue(boss, approved)
        client = APIClient()
        client.force_authenticate(boss)
        detail = client.get(f"/api/jobs/{approved.pk}/").json()
        assert detail["issued_report"]["id"]
        res = client.get(f"/api/jobs/{approved.pk}/report/{detail['issued_report']['id']}/pdf/")
        assert res.status_code == 200 and b"".join(res.streaming_content) == FAKE_PDF
        listed = client.get(f"/api/jobs/{approved.pk}/report/").json()
        assert [v["is_draft"] for v in listed] == [False]


# --- revising ----------------------------------------------------------------------------------


class TestRevising:
    def revise(self, user, job):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(f"/api/jobs/{job.pk}/revise/")

    def test_a_revision_keeps_the_issued_version_and_starts_a_new_one(self, approved, boss):
        issue(boss, approved)
        res = self.revise(boss, approved)
        assert res.status_code == 201, res.content

        revision = Job.objects.get(pk=res.json()["id"])
        assert revision.version == 2 and revision.parent_job_id == approved.pk
        assert revision.status == JobStatus.VALUATION_IN_PROGRESS and not revision.is_locked
        assert revision.valuation.market_value == approved.valuation.market_value

        approved.refresh_from_db()
        assert approved.is_locked and approved.status == JobStatus.ISSUED
        assert ReportVersion.objects.filter(job=approved, issued_at__isnull=False).count() == 1
        assert JobTransition.objects.filter(job=revision, comments__contains=approved.bayut_internal_reference_no)

    def test_a_version_can_be_revised_only_once(self, approved, boss):
        issue(boss, approved)
        assert self.revise(boss, approved).status_code == 201
        again = self.revise(boss, approved)
        assert again.status_code == 409 and again.json()["code"] == "already_revised"

    def test_an_open_job_cannot_be_revised(self, approved, boss):
        res = self.revise(boss, approved)
        assert res.status_code == 409 and res.json()["code"] == "not_issued"

    def test_only_an_admin_can_revise(self, approved, boss):
        issue(boss, approved)
        assert self.revise(approved.valuer, approved).status_code == 403

    def test_the_job_says_whether_it_can_be_revised_and_where_the_revision_is(self, approved, boss):
        issue(boss, approved)
        client = APIClient()
        client.force_authenticate(boss)
        assert client.get(f"/api/jobs/{approved.pk}/").json()["can_revise"] is True
        rev_id = self.revise(boss, approved).json()["id"]
        detail = client.get(f"/api/jobs/{approved.pk}/").json()
        assert detail["can_revise"] is False and detail["revision"]["id"] == rev_id


# --- the real engine ---------------------------------------------------------------------------


@needs_pdf_engine
def test_the_real_engine_produces_the_final_pdf(approved, boss, monkeypatch, storage):
    from apps.reports.render import render_pdf as real_render_pdf

    monkeypatch.setattr(issue_module, "render_pdf", real_render_pdf)
    assert issue(boss, approved).status_code == 200
    version = ReportVersion.objects.get(job=approved)
    assert (storage / version.pdf_s3_key).read_bytes().startswith(b"%PDF")


# --- sign-off: the reviewer's approval is the second signature and finalises the report ---------


class TestSignOff:
    @pytest.fixture
    def in_review(self, boss, clean_template):
        dan, pat = make_user("dan"), make_user("pat")
        job = Job.objects.create(
            bank=Bank.objects.create(name="Test Bank"),
            property=Property.objects.create(unit_number="312", building_name="Rukan Residences"),
            valuer=dan, inspected_by=dan, registered_valuer=dan, peer_reviewer=pat,
            admin_user=boss, report_template=clean_template,
        )
        fill_everything(job)
        return get_to(Job.objects.get(pk=job.pk), JobStatus.PEER_REVIEW)

    def sign_off(self, user, job, comments=""):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(
            f"/api/jobs/{job.pk}/transitions/", {"from": "peer_review", "to": "issued", "comments": comments},
            format="json",
        )

    def test_the_reviewers_sign_off_issues_the_report_with_them_as_second_signatory(self, in_review):
        pat = in_review.peer_reviewer
        res = self.sign_off(pat, in_review, "Happy with the evidence.")
        assert res.status_code in (200, 202), res.json()
        job = Job.objects.get(pk=in_review.pk)
        assert job.is_locked and job.status == JobStatus.ISSUED
        assert job.counter_signatory == pat and job.countersigned_by == pat
        version = ReportVersion.objects.get(job=job)
        assert version.issued_by == pat and version.input_snapshot["counter_signatory"]["name"] == "Pat"
        steps = list(JobTransition.objects.filter(job=job).order_by("id").values_list("from_status", "to_status"))
        assert steps[-2:] == [("peer_review", "approved_signed"), ("approved_signed", "issued")]
        assert JobTransition.objects.filter(job=job, comments="Happy with the evidence.").exists()

    def test_the_draft_already_names_the_reviewer_as_second_signatory(self, in_review):
        from apps.reports.context import build_context

        assert build_context(in_review)["counter_signatory"]["name"] == "Pat"

    def test_nothing_is_written_while_something_blocks_it(self, in_review):
        ValuerProfile.objects.filter(user=in_review.peer_reviewer).update(
            rera_licence_expiry=datetime.date(2020, 1, 1)
        )
        res = self.sign_off(in_review.peer_reviewer, in_review)
        assert res.status_code == 422
        job = Job.objects.get(pk=in_review.pk)
        assert job.status == JobStatus.PEER_REVIEW and job.counter_signatory is None
