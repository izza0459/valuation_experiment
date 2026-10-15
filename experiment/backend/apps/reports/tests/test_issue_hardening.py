"""The counter-signature, background issuing, revisions' references, frozen
evidence, audit coverage and turnaround (audit fixes, Oct 2026)."""
import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.audit.middleware import acting_as
from apps.audit.models import AuditLog
from apps.evidence.models import AVMRun, Comparable, JobComparable
from apps.jobs.models import Job, JobTransition, Property
from apps.jobs.workflow import JobLockedError, JobStatus
from apps.reports import issue as issue_module
from apps.reports import tasks as tasks_module
from apps.reports.issue import issue_blockers, issue_report
from apps.reports.models import ReportVersion
from apps.reports.tests import test_issue
from apps.reports.tests.test_issue import FAKE_PDF, issue, make_user

# The fixtures from the main issue tests: a complete, approved, counter-signed job.
approved, boss, clean_template = test_issue.approved, test_issue.boss, test_issue.clean_template
storage, fake_engine = test_issue.storage, test_issue.fake_engine

pytestmark = pytest.mark.django_db

S = JobStatus


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def move(user, job, to, comments=""):
    job.refresh_from_db()
    return client_for(user).post(
        f"/api/jobs/{job.pk}/transitions/", {"from": job.status, "to": to, "comments": comments}, format="json"
    )


def actions_for(user, job):
    return client_for(user).get(f"/api/jobs/{job.pk}/").json()["available_actions"]


def revise(user, job):
    return client_for(user).post(f"/api/jobs/{job.pk}/revise/")


@pytest.fixture
def unsigned(approved):
    """Approved by the peer reviewer, not yet counter-signed."""
    Job.objects.filter(pk=approved.pk).update(countersigned_by=None, countersigned_at=None)
    approved.refresh_from_db()
    return approved


# --- counter-signature (#2) ----------------------------------------------------------------------


class TestCounterSignature:
    def test_issue_is_blocked_until_the_counter_signatory_signs(self, unsigned, boss):
        assert any("not counter-signed" in b for b in issue_blockers(unsigned))
        res = issue(boss, unsigned)
        assert res.status_code == 422 and any("not counter-signed" in b for b in res.json()["blockers"])

    def test_only_the_counter_signatory_is_offered_it(self, unsigned, boss):
        assert [a["label"] for a in actions_for(unsigned.counter_signatory, unsigned)] == ["Counter-sign"]
        for user in (boss, unsigned.valuer, unsigned.peer_reviewer):
            assert all(a["label"] != "Counter-sign" for a in actions_for(user, unsigned))

    def test_nobody_else_can_sign_for_them(self, unsigned, boss):
        for user in (boss, unsigned.valuer, unsigned.peer_reviewer):
            assert move(user, unsigned, S.APPROVED_SIGNED).status_code == 403
        unsigned.refresh_from_db()
        assert unsigned.countersigned_at is None

    def test_signing_is_recorded_and_unblocks_issue(self, unsigned, boss):
        res = move(unsigned.counter_signatory, unsigned, S.APPROVED_SIGNED, "Agreed.")
        assert res.status_code == 200 and res.json()["status"] == S.APPROVED_SIGNED
        unsigned.refresh_from_db()
        assert unsigned.countersigned_by == unsigned.counter_signatory and unsigned.countersigned_at
        entry = JobTransition.objects.get(job=unsigned, from_status=S.APPROVED_SIGNED, to_status=S.APPROVED_SIGNED)
        assert entry.by == unsigned.counter_signatory and entry.comments == "Agreed."
        assert actions_for(unsigned.counter_signatory, unsigned) == []  # done; not offered again
        assert issue(boss, unsigned).status_code == 200

    def test_reopening_voids_the_signature(self, approved):
        assert approved.countersigned_at
        move(approved.peer_reviewer, approved, S.VALUATION_IN_PROGRESS, "BUA source is wrong.")
        approved.refresh_from_db()
        assert approved.countersigned_at is None and approved.countersigned_by is None

    def test_a_signature_by_someone_since_replaced_does_not_count(self, approved):
        other = make_user("olive")
        Job.objects.filter(pk=approved.pk).update(counter_signatory=other)
        assert any("not counter-signed" in b for b in issue_blockers(Job.objects.get(pk=approved.pk)))


# --- issuing in the background (#8) and cleaning up (#9) -----------------------------------------


class TestBackgroundIssue:
    @pytest.fixture
    def queued(self, settings, monkeypatch):
        """A worker is configured: requests are queued, not run."""
        settings.CELERY_TASK_ALWAYS_EAGER = False
        sent = []
        monkeypatch.setattr(tasks_module.issue_job, "delay", lambda *args: sent.append(args))
        return sent

    def test_the_request_is_queued_and_answered_at_once(self, approved, boss, queued):
        res = issue(boss, approved)
        assert res.status_code == 202 and res.json() == {
            "status": S.APPROVED_SIGNED, "status_label": "Approved & Signed", "issuing": True,
        }
        assert queued == [(approved.pk, boss.pk)]
        approved.refresh_from_db()
        assert approved.issue_in_progress and not approved.is_locked and not ReportVersion.objects.exists()

    def test_nothing_else_can_happen_while_it_runs(self, approved, boss, queued):
        issue(boss, approved)
        assert actions_for(boss, approved) == [] and actions_for(approved.peer_reviewer, approved) == []
        res = move(approved.peer_reviewer, approved, S.VALUATION_IN_PROGRESS, "wait")
        assert res.status_code == 409 and res.json()["code"] == "not_allowed"

    def test_the_worker_issues_it(self, approved, boss, queued, storage):
        issue(boss, approved)
        tasks_module.issue_job(approved.pk, boss.pk)
        approved.refresh_from_db()
        assert approved.is_locked and approved.status == S.ISSUED and not approved.issue_in_progress
        version = ReportVersion.objects.get(job=approved)
        assert version.issued_by == boss and (storage / version.pdf_s3_key).read_bytes() == FAKE_PDF
        assert JobTransition.objects.get(job=approved, to_status=S.ISSUED).by == boss

    def test_a_failed_run_says_why_and_frees_the_job(self, approved, boss, queued, monkeypatch):
        issue(boss, approved)
        monkeypatch.setattr(issue_module, "render_pdf", lambda html: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            tasks_module.issue_job(approved.pk, boss.pk)
        approved.refresh_from_db()
        assert not approved.issue_in_progress and "failed" in approved.issue_error
        assert {a["label"] for a in actions_for(boss, approved)} >= {"Issue report", "Reopen"}

    def test_a_lost_request_stops_blocking_after_the_timeout(self, approved, boss, queued, settings):
        issue(boss, approved)
        Job.objects.filter(pk=approved.pk).update(
            issue_requested_at=timezone.now() - datetime.timedelta(seconds=settings.ISSUE_TASK_TIMEOUT_SECONDS + 1)
        )
        approved.refresh_from_db()
        assert not approved.issue_in_progress
        assert issue(boss, approved).status_code == 202

    def test_the_pdf_is_rendered_once(self, approved, boss, monkeypatch):
        calls = []
        real = issue_module.render_html
        monkeypatch.setattr(issue_module, "render_html", lambda *a: calls.append(1) or real(*a))
        issue_report(approved, boss)
        assert len(calls) == 1

    def test_an_edit_during_the_render_is_refused_and_leaves_nothing(self, approved, boss, monkeypatch, storage):
        def edit_then_render(html):
            Job.objects.filter(pk=approved.pk).update(bank_reference_no="CHANGED")
            return FAKE_PDF

        monkeypatch.setattr(issue_module, "render_pdf", edit_then_render)
        with pytest.raises(issue_module.IssueBlockedError, match="changed while"):
            issue_report(approved, boss)
        assert not ReportVersion.objects.exists() and not list(storage.glob("reports/**/*.pdf"))
        approved.refresh_from_db()
        assert not approved.is_locked

    def test_a_failure_writing_the_log_removes_the_file_and_the_lock(self, approved, boss, monkeypatch, storage):
        def boom(*args, **kwargs):
            raise RuntimeError("log write failed")

        monkeypatch.setattr(issue_module.JobTransition.objects, "create", boom)
        with pytest.raises(RuntimeError):
            issue_report(approved, boss)
        approved.refresh_from_db()
        assert not approved.is_locked and not ReportVersion.objects.exists()
        assert not list(storage.glob("reports/**/*.pdf"))


# --- revisions keep the reference (#5) ------------------------------------------------------------


class TestRevisionReferences:
    def test_revisions_carry_the_original_reference(self, approved, boss):
        root = approved.bayut_internal_reference_no
        issue(boss, approved)
        v2 = Job.objects.get(pk=revise(boss, approved).json()["id"])
        assert v2.bayut_internal_reference_no == f"{root}-v2" and v2.reference_root == root

        Job.objects.filter(pk=v2.pk).update(is_locked=True, status=S.ISSUED)
        v3 = Job.objects.get(pk=revise(boss, v2).json()["id"])
        assert v3.bayut_internal_reference_no == f"{root}-v3"

    def test_a_revision_starts_unsigned(self, approved, boss):
        issue(boss, approved)
        v2 = Job.objects.get(pk=revise(boss, approved).json()["id"])
        assert v2.countersigned_at is None and v2.issue_requested_at is None

    def test_file_names_name_the_version_once(self, approved, boss):
        issue(boss, approved)
        assert approved.file_stem == f"{approved.bayut_internal_reference_no}-v1"
        v2 = Job.objects.get(pk=revise(boss, approved).json()["id"])
        assert v2.file_stem == v2.bayut_internal_reference_no


# --- evidence is frozen with the job (#6) ---------------------------------------------------------


class TestEvidence:
    @pytest.fixture
    def comparable(self):
        return Comparable.objects.create(source="manual", community_name="JVC", price_aed=700000, bua_sqft=500)

    @pytest.fixture
    def issued_with_evidence(self, approved, boss, comparable):
        JobComparable.objects.create(job=approved, comparable=comparable, order=1)
        AVMRun.objects.create(job=approved, job_version=1, suggested_value=710000)
        issue(boss, approved)
        approved.refresh_from_db()
        assert approved.is_locked
        return approved

    def test_selected_comparables_cannot_change_after_issue(self, issued_with_evidence):
        link = JobComparable.objects.get(job=issued_with_evidence)
        link.selected = False
        with pytest.raises(JobLockedError):
            link.save()
        with pytest.raises(JobLockedError):
            link.delete()
        with pytest.raises(JobLockedError):
            JobComparable.objects.filter(job=issued_with_evidence).delete()
        with pytest.raises(JobLockedError):
            JobComparable.objects.filter(job=issued_with_evidence).update(order=9)

    def test_nothing_new_can_be_added_after_issue(self, issued_with_evidence, comparable):
        with pytest.raises(JobLockedError):
            AVMRun.objects.create(job=issued_with_evidence, job_version=1)

    def test_a_cited_comparable_cannot_be_edited(self, issued_with_evidence, comparable):
        comparable.price_aed = 1
        with pytest.raises(JobLockedError):
            comparable.save()

    def test_a_revision_keeps_the_chosen_comparables_but_not_the_avm_runs(self, issued_with_evidence, boss, comparable):
        v2 = Job.objects.get(pk=revise(boss, issued_with_evidence).json()["id"])
        assert list(v2.job_comparables.values_list("comparable_id", "order")) == [(comparable.pk, 1)]
        assert not v2.avm_runs.exists()
        assert issued_with_evidence.job_comparables.count() == 1  # the issued version keeps its own


# --- audit coverage (#7) ---------------------------------------------------------------------------


class TestAuditCoverage:
    def test_granting_a_role_is_logged_without_the_password(self, boss):
        someone = make_user("sam")
        with acting_as(boss):
            someone.roles = [Role.ADMIN]
            someone.set_password("new-secret-123")
            someone.save()
        entries = AuditLog.objects.filter(model_name="User", object_id=str(someone.pk))
        assert list(entries.values_list("field_name", "changed_by")) == [("roles", boss.pk)]

    def test_a_bulk_soft_delete_is_attributed_and_logged(self, boss):
        properties = [Property.objects.create(building_name=f"B{i}") for i in range(2)]
        with acting_as(boss):
            count, _ = Property.objects.filter(pk__in=[p.pk for p in properties]).delete()
        assert count == 2
        for prop in Property.all_objects.filter(pk__in=[p.pk for p in properties]):
            assert prop.deleted_at and prop.deleted_by == boss
        assert AuditLog.objects.filter(model_name="Property", field_name="deleted_at", changed_by=boss).count() == 2


# --- turnaround (#10) ------------------------------------------------------------------------------


class TestTurnaround:
    def test_measured_from_when_the_request_arrived(self, approved, boss):
        issue(boss, approved)
        issued_at = timezone.now()
        Job.objects.filter(pk=approved.pk).update(
            issued_at=issued_at, date_time_request_received=issued_at - datetime.timedelta(hours=30)
        )
        assert client_for(boss).get("/api/jobs/kpis/").json()["avg_turnaround_hours"] == 30.0

    def test_falls_back_to_the_instruction_date(self, approved, boss):
        issue(boss, approved)
        start = timezone.make_aware(datetime.datetime(2026, 8, 26))
        Job.objects.filter(pk=approved.pk).update(
            issued_at=start + datetime.timedelta(hours=50), date_time_request_received=None,
            date_of_instruction=datetime.date(2026, 8, 26),
        )
        assert client_for(boss).get("/api/jobs/kpis/").json()["avg_turnaround_hours"] == 50.0
