"""The lifecycle rules from CLAUDE.md §3 that a bank panel review would
probe: no issue without peer review + counter-signature + a valid RERA
licence, and an issued job is locked.
"""
import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import User, ValuerProfile
from apps.banks.models import Bank
from apps.jobs.models import Job, Property
from apps.jobs.workflow import (
    IssueBlockedError,
    JobLockedError,
    JobStatus,
    TransitionError,
    validate_transition,
)

pytestmark = pytest.mark.django_db


def make_valuer(email, *, licence_expiry=datetime.date(2099, 1, 1)):
    user = User.objects.create(username=email.split("@")[0], email=email)
    ValuerProfile.objects.create(
        user=user,
        rera_registration_no="RERA-1234",
        rics_membership_no="RICS-5678",
        rera_licence_expiry=licence_expiry,
    )
    return user


@pytest.fixture
def bank():
    return Bank.objects.create(name="Test Bank", sla_signed=True)


@pytest.fixture
def property_obj():
    return Property.objects.create(building_name="Marina Gate 1", community_name="Dubai Marina")


@pytest.fixture
def job(bank, property_obj):
    return Job.objects.create(bank=bank, property=property_obj)


def advance_to_approved(job):
    for status in [
        JobStatus.SETUP,
        JobStatus.INSPECTION_SCHEDULED,
        JobStatus.INSPECTED,
        JobStatus.VALUATION_IN_PROGRESS,
        JobStatus.PEER_REVIEW,
        JobStatus.APPROVED_SIGNED,
    ]:
        job.transition_to(status)
    if job.counter_signatory_id:
        job.countersign(job.counter_signatory)
    return job


class TestTransitionRules:
    def test_allows_the_documented_path(self):
        validate_transition(JobStatus.PEER_REVIEW, JobStatus.APPROVED_SIGNED)

    def test_peer_review_can_bounce_back_with_comments(self):
        validate_transition(JobStatus.PEER_REVIEW, JobStatus.VALUATION_IN_PROGRESS)

    def test_issued_is_terminal(self):
        with pytest.raises(TransitionError):
            validate_transition(JobStatus.ISSUED, JobStatus.VALUATION_IN_PROGRESS)

    def test_cannot_skip_peer_review(self, job):
        """Regression: status was a plain field, so this jump succeeded."""
        job.status = JobStatus.ISSUED
        with pytest.raises(TransitionError):
            job.save()

    def test_saving_without_changing_status_is_fine(self, job):
        job.bank_reference_no = "REF-1"
        job.save()
        job.refresh_from_db()
        assert job.bank_reference_no == "REF-1"


class TestIssuePreconditions:
    def test_blocked_without_peer_reviewer_or_countersignatory(self, job):
        advance_to_approved(job)
        with pytest.raises(IssueBlockedError) as exc:
            job.issue()
        assert "Peer reviewer" in str(exc.value)
        assert "Counter-signatory" in str(exc.value)

    def test_blocked_when_signing_valuer_licence_expired(self, job):
        job.registered_valuer = make_valuer(
            "expired@example.com", licence_expiry=datetime.date(2020, 1, 1)
        )
        job.peer_reviewer = make_valuer("peer@example.com")
        job.counter_signatory = make_valuer("counter@example.com")
        job.save()
        advance_to_approved(job)

        with pytest.raises(IssueBlockedError) as exc:
            job.issue()
        assert "licence" in str(exc.value).lower()

    def test_issues_when_everything_is_in_place(self, job):
        job.registered_valuer = make_valuer("valuer@example.com")
        job.peer_reviewer = make_valuer("peer@example.com")
        job.counter_signatory = make_valuer("counter@example.com")
        job.save()
        advance_to_approved(job)

        job.issue()

        job.refresh_from_db()
        assert job.status == JobStatus.ISSUED
        assert job.is_locked is True
        assert job.issued_at is not None


class TestLockOnIssue:
    @pytest.fixture
    def issued_job(self, job):
        job.registered_valuer = make_valuer("valuer@example.com")
        job.peer_reviewer = make_valuer("peer@example.com")
        job.counter_signatory = make_valuer("counter@example.com")
        job.save()
        advance_to_approved(job)
        return job.issue()

    def test_job_cannot_be_edited_after_issue(self, issued_job):
        """Regression: an issued, locked job accepted edits silently."""
        issued_job.bank_reference_no = "EDITED-AFTER-ISSUE"
        with pytest.raises(JobLockedError):
            issued_job.save()

        issued_job.refresh_from_db()
        assert issued_job.bank_reference_no != "EDITED-AFTER-ISSUE"

    def test_tab_data_cannot_be_edited_after_issue(self, issued_job):
        """The valuation figures behind an issued report must be frozen too."""
        valuation = issued_job.valuation
        valuation.market_value = 9_999_999
        with pytest.raises(JobLockedError):
            valuation.save()

    def test_revision_unlocks_a_new_version_and_keeps_the_old(self, issued_job):
        issued_job.summary.job.refresh_from_db()
        revision = issued_job.create_revision()

        assert revision.pk != issued_job.pk
        assert revision.version == issued_job.version + 1
        assert revision.parent_job_id == issued_job.pk
        assert revision.is_locked is False
        assert revision.status == JobStatus.VALUATION_IN_PROGRESS

        issued_job.refresh_from_db()
        assert issued_job.is_locked is True
        assert issued_job.status == JobStatus.ISSUED

    def test_revision_carries_tab_data_forward(self, job):
        job.summary.bua_sqft = 519
        job.summary.property_category = "apartment"
        job.summary.save()

        job.registered_valuer = make_valuer("valuer@example.com")
        job.peer_reviewer = make_valuer("peer@example.com")
        job.counter_signatory = make_valuer("counter@example.com")
        job.save()
        advance_to_approved(job)
        job.issue()

        revision = job.create_revision()
        assert revision.summary.bua_sqft == Decimal("519")
        assert revision.summary.property_category == "apartment"


class TestReferenceNumbers:
    def test_allocates_sequentially(self, bank, property_obj):
        first = Job.objects.create(bank=bank, property=property_obj)
        second = Job.objects.create(bank=bank, property=property_obj)
        assert first.bayut_internal_reference_no != second.bayut_internal_reference_no
        assert second.bayut_internal_reference_no.endswith("00002")

    def test_does_not_reuse_a_deleted_jobs_number(self, bank, property_obj):
        """Regression: a count()-based reference reused numbers after a
        delete, colliding with the unique constraint."""
        first = Job.objects.create(bank=bank, property=property_obj)
        second = Job.objects.create(bank=bank, property=property_obj)
        taken = second.bayut_internal_reference_no
        second.delete()

        third = Job.objects.create(bank=bank, property=property_obj)
        assert third.bayut_internal_reference_no != taken
        assert third.bayut_internal_reference_no != first.bayut_internal_reference_no
