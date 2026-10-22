"""The peer reviewer reads the job and returns it or signs it off; they can't
edit it. Changes recorded while reviewers could (CRM feedback PR-01) are still
accepted by the valuer before sign-off."""
import pytest

from apps.jobs.models import Job, ReviewerEdit
from apps.jobs.tabs import TAB_EDIT_ROLES
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


class TestTheReviewerCantEdit:
    @pytest.mark.parametrize("tab, values", [
        ("valuation", {"valuation_commentary": "Tightened wording."}),
        ("valuation", {"market_value": "900000"}),
        ("summary", {"departures": "None, as instructed."}),
        ("checklist", {"dld_location_checked": True}),
        ("scheduling", {"call_remark": "x"}),
    ])
    def test_any_tab_is_refused(self, in_review, tab, values):
        res = patch(client_for(in_review.peer_reviewer), in_review, tab, values)
        assert res.status_code == 403, res.json()
        assert not ReviewerEdit.objects.exists()

    def test_the_job_shows_every_tab_read_only_to_them(self, in_review):
        tabs = client_for(in_review.peer_reviewer).get(f"/api/jobs/{in_review.pk}/").json()["tabs"]
        assert all(tabs[key]["can_edit"] is False for key in TAB_EDIT_ROLES if key in tabs)

    def test_they_can_still_return_it_or_sign_it_off(self, in_review):
        actions = client_for(in_review.peer_reviewer).get(f"/api/jobs/{in_review.pk}/").json()["available_actions"]
        assert {"Return to valuer", "Sign off"} <= {a["label"] for a in actions}

    def test_everyone_else_stays_frozen(self, in_review, dan):
        res = patch(client_for(dan), in_review, "valuation", {"valuation_commentary": "x"})
        assert res.status_code == 409 and res.json()["code"] == "frozen"


class TestEarlierChanges:
    """Recorded before reviewers became read-only."""

    @pytest.fixture
    def earlier(self, in_review):
        return ReviewerEdit.objects.create(job=in_review, tab_key="summary", field_key="departures",
                                           label="Departures", old_value="None", new_value="None, as instructed.",
                                           by=in_review.peer_reviewer)

    def test_sign_off_waits_for_the_valuer_to_accept(self, in_review, earlier, dan):
        assert any("hasn't accepted" in b for b in signoff_ready(in_review))
        assert accept(in_review.peer_reviewer, in_review).status_code == 403  # not their own
        res = accept(dan, in_review)
        assert res.status_code == 200 and res.json()["accepted"] == 1
        assert not any("hasn't accepted" in b for b in signoff_ready(in_review))
        assert ReviewerEdit.objects.get().accepted_by == dan

    def test_the_valuer_sees_them_and_a_badge(self, in_review, earlier, dan):
        detail = client_for(dan).get(f"/api/jobs/{in_review.pk}/").json()
        assert detail["can_accept_reviewer_edits"] is True
        assert detail["reviewer_edits"][0]["new"] == "None, as instructed."
        listed = client_for(dan).get("/api/jobs/").json()["results"]
        assert next(j for j in listed if j["id"] == in_review.pk)["reviewer_changes_to_accept"] == 1
