"""The peer reviewer changes the report's wording during review; the valuer
accepts before sign-off (CRM feedback PR-01)."""
import pytest

from apps.audit.models import AuditLog
from apps.jobs.models import Job, ReviewerEdit
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, patch
from apps.jobs.transitions import signoff_ready
from apps.jobs.workflow import JobStatus as S

pytestmark = pytest.mark.django_db

__all__ = ["bank", "dan", "job"]


@pytest.fixture
def in_review(job):
    Job.objects.filter(pk=job.pk).update(status=S.PEER_REVIEW)
    return Job.objects.get(pk=job.pk)


def accept(user, job):
    return client_for(user).post(f"/api/jobs/{job.pk}/reviewer-edits/accept/")


class TestReviewerEditing:
    def test_the_reviewer_can_change_wording_and_it_is_tracked(self, in_review):
        pat = in_review.peer_reviewer
        res = patch(client_for(pat), in_review, "valuation", {"valuation_commentary": "Tightened wording."})
        assert res.status_code == 200, res.json()
        edit = ReviewerEdit.objects.get(job=in_review)
        assert (edit.field_key, edit.old_value, edit.new_value, edit.by) == (
            "valuation_commentary", "", "Tightened wording.", pat)
        assert edit.accepted_at is None
        assert AuditLog.objects.filter(job=in_review, field_name="valuation_commentary").exists()

    def test_figures_too_and_they_are_tracked(self, in_review):
        res = patch(client_for(in_review.peer_reviewer), in_review, "valuation", {"market_value": "900000"})
        assert res.status_code == 200, res.json()
        edit = ReviewerEdit.objects.get(job=in_review, field_key="market_value")
        assert str(edit.new_value) == "900000"

    def test_but_not_who_works_on_the_job(self, in_review, dan):
        res = patch(client_for(in_review.peer_reviewer), in_review, "checklist", {"valuer": dan.pk})
        assert res.status_code == 403 and "who works on the job" in res.json()["detail"]

    def test_nor_scheduling(self, in_review):
        res = patch(client_for(in_review.peer_reviewer), in_review, "scheduling", {"call_remark": "x"})
        assert res.status_code in (403, 409)

    def test_the_tab_says_which_fields_are_the_reviewers(self, in_review):
        tabs = client_for(in_review.peer_reviewer).get(f"/api/jobs/{in_review.pk}/").json()["tabs"]
        assert tabs["valuation"]["can_edit"] is True
        assert "market_value" not in tabs["valuation"]["read_only_fields"]
        assert "valuer" in tabs["checklist"]["read_only_fields"]
        assert tabs["photos"]["can_edit"] is False and tabs["scheduling"]["can_edit"] is False

    def test_everyone_else_stays_frozen(self, in_review, dan):
        res = patch(client_for(dan), in_review, "valuation", {"valuation_commentary": "x"})
        assert res.status_code == 409 and res.json()["code"] == "frozen"


class TestAcceptance:
    def test_sign_off_waits_for_the_valuer_to_accept(self, in_review, dan):
        pat = in_review.peer_reviewer
        patch(client_for(pat), in_review, "summary", {"departures": "None, as instructed."})
        assert any("hasn't accepted" in b for b in signoff_ready(in_review))
        assert accept(pat, in_review).status_code == 403  # the reviewer can't accept their own
        res = accept(dan, in_review)
        assert res.status_code == 200 and res.json()["accepted"] == 1
        assert not any("hasn't accepted" in b for b in signoff_ready(in_review))
        assert ReviewerEdit.objects.get().accepted_by == dan

    def test_the_valuer_sees_the_changes_and_a_badge(self, in_review, dan):
        patch(client_for(in_review.peer_reviewer), in_review, "valuation", {"valuation_commentary": "New."})
        detail = client_for(dan).get(f"/api/jobs/{in_review.pk}/").json()
        assert detail["can_accept_reviewer_edits"] is True
        assert detail["reviewer_edits"][0]["new"] == "New."
        listed = client_for(dan).get("/api/jobs/").json()["results"]
        assert next(j for j in listed if j["id"] == in_review.pk)["reviewer_changes_to_accept"] == 1
