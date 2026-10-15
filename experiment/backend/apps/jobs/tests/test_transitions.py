"""Moving a job through its lifecycle over the API: who may, what blocks it,
and what the reviewer's comments leave behind (CLAUDE.md §3)."""
import datetime

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.banks.models import Bank
from apps.jobs.models import Job, JobTransition, Property
from apps.jobs.workflow import ALLOWED_TRANSITIONS, TRANSITION_RULES, JobStatus
from apps.media_files.tests.helpers import attach_media

pytestmark = pytest.mark.django_db

S = JobStatus


def make_user(name, roles=None):
    return User.objects.create(username=name, email=f"{name}@example.com", first_name=name.title(), roles=roles or [])


@pytest.fixture
def dan():
    return make_user("dan")


@pytest.fixture
def pat():
    return make_user("pat")


@pytest.fixture
def job(dan, pat):
    """Dan works the job; Pat is the independent peer reviewer."""
    return Job.objects.create(
        bank=Bank.objects.create(name="Test Bank"),
        property=Property.objects.create(building_name="Marina Gate 1"),
        valuer=dan, inspected_by=dan, registered_valuer=dan, peer_reviewer=pat,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def move(client, job, to, comments="", frm=None):
    job.refresh_from_db()
    return client.post(
        f"/api/jobs/{job.pk}/transitions/",
        {"from": frm or job.status, "to": to, "comments": comments},
        format="json",
    )


def fill_everything(job):
    """Every required field, so the review gate has nothing to complain about."""
    job.date_of_instruction = datetime.date(2026, 8, 26)
    job.save()
    job.property.applicant_name = "A. Applicant"
    job.property.save()
    for model, values in (
        (job.summary, {"interest_valued": "international_freehold", "property_category": "apartment",
                       "bua_sqm": "48.20"}),
        (job.inspection, {"inspection_date": datetime.date(2026, 8, 26), "inspection_type": "full"}),
        (job.location, {"property_status": "complete"}),
        (job.valuation, {"valuation_date": datetime.date(2026, 8, 26), "report_date": datetime.date(2026, 8, 28),
                         "market_value": "725000"}),
    ):
        for key, value in values.items():
            setattr(model, key, value)
        model.save()
    # A full inspection needs its photographs, and every job a document.
    uploader, _ = User.objects.get_or_create(
        username="media-admin", defaults={"email": "media-admin@example.com", "roles": [Role.ADMIN]}
    )
    attach_media(job, uploader)


def get_to(job, status):
    """Walks a job to `status` through the model, as setup for a test."""
    path = [S.SETUP, S.INSPECTION_SCHEDULED, S.INSPECTED, S.VALUATION_IN_PROGRESS, S.PEER_REVIEW, S.APPROVED_SIGNED]
    for step in path:
        job.transition_to(step)
        if step == status:
            break
    return job


# --- the rules table --------------------------------------------------------------------


class TestRulesTable:
    def test_every_allowed_move_has_a_rule(self):
        """A move with no rule could never be made through the API."""
        allowed = {(a, b) for a, targets in ALLOWED_TRANSITIONS.items() for b in targets}
        assert allowed - set(TRANSITION_RULES) == set()

    def test_every_rule_is_an_allowed_move(self):
        """Or an in-place action, which records something without moving."""
        allowed = {(a, b) for a, targets in ALLOWED_TRANSITIONS.items() for b in targets}
        moves = {key for key, rule in TRANSITION_RULES.items() if not rule.action}
        assert moves <= allowed
        assert all(a == b for (a, b), rule in TRANSITION_RULES.items() if rule.action)

    def test_roles_are_real_roles(self):
        valid = {r.value for r in Role}
        for rule in TRANSITION_RULES.values():
            assert rule.roles <= valid

    def test_only_the_assigned_reviewer_can_approve_or_return(self):
        for key in ((S.PEER_REVIEW, S.APPROVED_SIGNED), (S.PEER_REVIEW, S.VALUATION_IN_PROGRESS)):
            assert TRANSITION_RULES[key].roles == {Role.PEER_REVIEWER}

    def test_returns_and_reopens_need_a_reason(self):
        assert TRANSITION_RULES[(S.PEER_REVIEW, S.VALUATION_IN_PROGRESS)].comments_required
        assert TRANSITION_RULES[(S.APPROVED_SIGNED, S.VALUATION_IN_PROGRESS)].comments_required


# --- the working path -----------------------------------------------------------------------


class TestEarlyStages:
    def test_walks_to_valuation(self, job, dan):
        client = client_for(dan)
        for to in (S.SETUP, S.INSPECTION_SCHEDULED, S.INSPECTED, S.VALUATION_IN_PROGRESS):
            res = move(client, job, to)
            assert res.status_code == 200, res.json()
            assert res.json()["status"] == to
        job.refresh_from_db()
        assert job.inspection_scheduled_at and job.inspected_at

    def test_each_move_is_logged_with_who(self, job, dan):
        move(client_for(dan), job, S.SETUP)
        entry = JobTransition.objects.get(job=job)
        assert (entry.from_status, entry.to_status, entry.by) == (S.INSTRUCTION_RECEIVED, S.SETUP, dan)

    def test_the_status_change_is_audited_to_the_user(self, job, dan):
        move(client_for(dan), job, S.SETUP)
        entry = AuditLog.objects.get(job=job, field_name="status")
        assert entry.changed_by == dan and entry.new_value == S.SETUP

    def test_cannot_skip_a_stage(self, job, dan):
        res = move(client_for(dan), job, S.PEER_REVIEW)
        assert res.status_code == 409 and res.json()["code"] == "not_allowed"
        job.refresh_from_db()
        assert job.status == S.INSTRUCTION_RECEIVED

    def test_an_out_of_date_screen_is_refused(self, job, dan):
        client = client_for(dan)
        move(client, job, S.SETUP)
        res = move(client, job, S.INSPECTION_SCHEDULED, frm=S.INSTRUCTION_RECEIVED)
        assert res.status_code == 409 and res.json()["code"] == "stale"

    def test_from_and_to_are_required(self, job, dan):
        res = client_for(dan).post(f"/api/jobs/{job.pk}/transitions/", {"to": S.SETUP}, format="json")
        assert res.status_code == 400


# --- sending for review ----------------------------------------------------------------------


class TestSendForReview:
    @pytest.fixture
    def ready_job(self, job):
        fill_everything(job)
        return get_to(job, S.VALUATION_IN_PROGRESS)

    def test_blocked_until_every_tab_is_complete(self, job, dan):
        get_to(job, S.VALUATION_IN_PROGRESS)
        res = move(client_for(dan), job, S.PEER_REVIEW)
        assert res.status_code == 422 and res.json()["code"] == "blocked"
        blockers = " ".join(res.json()["blockers"])
        assert "Summary: Interest Valued" in blockers and "Valuation:" in blockers

    def test_the_blockers_are_also_shown_up_front(self, job, dan):
        get_to(job, S.VALUATION_IN_PROGRESS)
        actions = client_for(dan).get(f"/api/jobs/{job.pk}/").json()["available_actions"]
        send = next(a for a in actions if a["to"] == S.PEER_REVIEW)
        assert send["enabled"] is False and send["blockers"]

    def test_hidden_required_fields_do_not_block(self, ready_job, dan):
        """An apartment has no plot area; it must not hold up review."""
        assert move(client_for(dan), ready_job, S.PEER_REVIEW).status_code == 200

    def test_needs_a_peer_reviewer(self, ready_job, dan):
        Job.objects.filter(pk=ready_job.pk).update(peer_reviewer=None)
        res = move(client_for(dan), ready_job, S.PEER_REVIEW)
        assert res.status_code == 422 and "Assign a peer reviewer" in " ".join(res.json()["blockers"])

    @pytest.mark.parametrize("field", ["valuer", "registered_valuer"])
    def test_the_valuer_cannot_review_their_own_work(self, ready_job, dan, field):
        Job.objects.filter(pk=ready_job.pk).update(peer_reviewer=dan)
        res = move(client_for(dan), ready_job, S.PEER_REVIEW)
        assert res.status_code == 422 and "someone other than" in " ".join(res.json()["blockers"])

    def test_independence_can_be_switched_off(self, ready_job, dan, settings):
        settings.PEER_REVIEW_REQUIRES_INDEPENDENT_REVIEWER = False
        Job.objects.filter(pk=ready_job.pk).update(peer_reviewer=dan)
        assert move(client_for(dan), ready_job, S.PEER_REVIEW).status_code == 200

    def test_data_is_frozen_once_it_is_with_the_reviewer(self, ready_job, dan):
        move(client_for(dan), ready_job, S.PEER_REVIEW)
        res = client_for(dan).patch(
            f"/api/jobs/{ready_job.pk}/tabs/valuation/",
            {"base_version": 0, "values": {"market_value": "999999"}}, format="json",
        )
        assert res.status_code == 409 and res.json()["code"] == "frozen"


# --- review ------------------------------------------------------------------------------------


class TestReview:
    @pytest.fixture
    def in_review(self, job):
        fill_everything(job)
        return get_to(job, S.PEER_REVIEW)

    def test_returning_needs_a_reason(self, in_review, pat):
        res = move(client_for(pat), in_review, S.VALUATION_IN_PROGRESS)
        assert res.status_code == 400 and "comments" in res.json()["errors"]
        in_review.refresh_from_db()
        assert in_review.status == S.PEER_REVIEW

    def test_a_return_keeps_the_reason_and_unfreezes_the_data(self, in_review, pat, dan):
        res = move(client_for(pat), in_review, S.VALUATION_IN_PROGRESS, "Comparable 3 is a different size band.")
        assert res.status_code == 200
        in_review.refresh_from_db()
        assert in_review.peer_review_comments == "Comparable 3 is a different size band."
        edit = client_for(dan).patch(
            f"/api/jobs/{in_review.pk}/tabs/valuation/",
            {"base_version": 0, "values": {"market_value": "700000"}}, format="json",
        )
        assert edit.status_code == 200

    def test_comments_are_listed_newest_first_with_who(self, in_review, pat, dan):
        move(client_for(pat), in_review, S.VALUATION_IN_PROGRESS, "First pass: see comps.")
        move(client_for(dan), in_review, S.PEER_REVIEW)
        move(client_for(pat), in_review, S.VALUATION_IN_PROGRESS, "Second pass: still off.")
        log = client_for(dan).get(f"/api/jobs/{in_review.pk}/transitions/").json()
        assert [e["comments"] for e in log if e["comments"]] == ["Second pass: still off.", "First pass: see comps."]
        assert log[0]["who"] == "Pat" and log[0]["label"] == "Return to valuer"

    def test_approval_needs_a_counter_signatory(self, in_review, pat):
        res = move(client_for(pat), in_review, S.APPROVED_SIGNED)
        assert res.status_code == 422 and "counter-signatory" in " ".join(res.json()["blockers"])

    def test_the_reviewer_approves(self, in_review, pat, dan):
        Job.objects.filter(pk=in_review.pk).update(counter_signatory=dan)
        res = move(client_for(pat), in_review, S.APPROVED_SIGNED, "Happy with the evidence.")
        assert res.status_code == 200 and res.json()["status"] == S.APPROVED_SIGNED
        assert JobTransition.objects.filter(job=in_review, comments="Happy with the evidence.").exists()

    def test_the_valuer_cannot_approve_their_own_work(self, in_review, dan):
        Job.objects.filter(pk=in_review.pk).update(counter_signatory=dan)
        res = move(client_for(dan), in_review, S.APPROVED_SIGNED)
        assert res.status_code == 403 and res.json()["code"] == "forbidden"

    def test_a_platform_admin_cannot_stand_in_for_the_reviewer(self, in_review, dan):
        """A review only means something if the assigned person did it."""
        Job.objects.filter(pk=in_review.pk).update(counter_signatory=dan)
        boss = make_user("boss", roles=[Role.ADMIN])
        assert move(client_for(boss), in_review, S.APPROVED_SIGNED).status_code == 403
        assert move(client_for(boss), in_review, S.VALUATION_IN_PROGRESS, "no").status_code == 403

    def test_reviewer_sees_approve_and_return_the_valuer_sees_neither(self, in_review, pat, dan):
        as_reviewer = client_for(pat).get(f"/api/jobs/{in_review.pk}/").json()["available_actions"]
        as_valuer = client_for(dan).get(f"/api/jobs/{in_review.pk}/").json()["available_actions"]
        assert {a["label"] for a in as_reviewer} == {"Approve", "Return to valuer"}
        assert as_valuer == []


class TestAfterApproval:
    @pytest.fixture
    def approved(self, job, dan):
        fill_everything(job)
        Job.objects.filter(pk=job.pk).update(counter_signatory=dan)
        job.refresh_from_db()
        return get_to(job, S.APPROVED_SIGNED)

    def test_reopening_needs_a_reason_and_unfreezes(self, approved, pat):
        assert move(client_for(pat), approved, S.VALUATION_IN_PROGRESS).status_code == 400
        res = move(client_for(pat), approved, S.VALUATION_IN_PROGRESS, "Wrong BUA source on the title deed.")
        assert res.status_code == 200 and res.json()["status"] == S.VALUATION_IN_PROGRESS

    def test_issuing_is_for_admins_only(self, approved, dan):
        """The full issue flow is in apps/reports/tests/test_issue.py."""
        assert move(client_for(dan), approved, S.ISSUED).status_code == 403
        offered = client_for(dan).get(f"/api/jobs/{approved.pk}/").json()["available_actions"]
        assert all(a["to"] != S.ISSUED for a in offered)


# --- roles and locking -----------------------------------------------------------------------------


class TestRolesAndLocks:
    def test_an_inspector_cannot_send_for_review(self, job):
        ines = make_user("ines")
        Job.objects.filter(pk=job.pk).update(inspected_by=ines, valuer=None, registered_valuer=None)
        job.refresh_from_db()  # a stale instance would write the old roles back
        get_to(job, S.VALUATION_IN_PROGRESS)
        assert move(client_for(ines), job, S.PEER_REVIEW).status_code == 403

    def test_an_inspector_can_mark_a_job_inspected(self, job):
        ines = make_user("ines")
        Job.objects.filter(pk=job.pk).update(inspected_by=ines, valuer=None, registered_valuer=None)
        job.refresh_from_db()  # a stale instance would write the old roles back
        get_to(job, S.INSPECTION_SCHEDULED)
        assert move(client_for(ines), job, S.INSPECTED).status_code == 200

    def test_someone_with_no_role_cannot_even_see_it(self, job):
        assert move(client_for(make_user("stranger")), job, S.SETUP).status_code == 404

    def test_an_issued_job_offers_nothing_and_refuses_everything(self, job, dan):
        Job.objects.filter(pk=job.pk).update(is_locked=True, status=S.ISSUED)
        assert client_for(dan).get(f"/api/jobs/{job.pk}/").json()["available_actions"] == []
        res = move(client_for(dan), job, S.VALUATION_IN_PROGRESS, "x")
        assert res.status_code == 409 and res.json()["code"] == "locked"

    def test_unauthenticated_is_refused(self, job):
        res = APIClient().post(f"/api/jobs/{job.pk}/transitions/", {"from": "a", "to": "b"}, format="json")
        assert res.status_code in (401, 403)
