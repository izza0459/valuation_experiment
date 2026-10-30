"""The peer reviewer can't edit the job: what they change during review is
recorded as a suggestion (CRM feedback PR-01, apps.jobs.suggestions), which
the valuer accepts (saved like any edit) or declines with a reason. Sign-off
waits until every suggestion is answered."""
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


def suggest(user, job, tab, field, value, note=""):
    return client_for(user).post(f"/api/jobs/{job.pk}/suggestions/",
                                 {"tab": tab, "field": field, "value": value, "note": note}, format="json")


def detail(user, job):
    return client_for(user).get(f"/api/jobs/{job.pk}/").json()


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

    def test_tabs_are_read_only_but_open_to_suggestions(self, in_review):
        tabs = detail(in_review.peer_reviewer, in_review)["tabs"]
        assert all(tabs[key]["can_edit"] is False for key in TAB_EDIT_ROLES if key in tabs)
        assert tabs["valuation"]["can_suggest"] is True
        assert tabs["review"]["can_suggest"] is False

    def test_they_can_still_return_it_or_sign_it_off(self, in_review):
        actions = detail(in_review.peer_reviewer, in_review)["available_actions"]
        assert {"Return to valuer", "Sign off"} <= {a["label"] for a in actions}

    def test_everyone_else_stays_frozen(self, in_review, dan):
        res = patch(client_for(dan), in_review, "valuation", {"valuation_commentary": "x"})
        assert res.status_code == 409 and res.json()["code"] == "frozen"


class TestSuggestions:
    def test_a_suggestion_leaves_the_value_alone(self, in_review):
        before = in_review.summary.departures
        res = suggest(in_review.peer_reviewer, in_review, "summary", "departures", "None, as instructed.", "Clearer")
        assert res.status_code == 201, res.json()
        assert res.json()["status"] == "open" and res.json()["note"] == "Clearer"
        assert Job.objects.get(pk=in_review.pk).summary.departures == before

    def test_only_the_reviewer_during_review(self, in_review, dan):
        assert suggest(dan, in_review, "summary", "departures", "x").status_code == 403
        Job.objects.filter(pk=in_review.pk).update(status=S.VALUATION_IN_PROGRESS)
        assert suggest(in_review.peer_reviewer, in_review, "summary", "departures", "x").status_code == 403

    def test_values_are_checked_like_a_save(self, in_review):
        res = suggest(in_review.peer_reviewer, in_review, "valuation", "market_value", "-5")
        assert res.status_code == 400 and "market_value" in res.json()["errors"]

    def test_the_team_cant_be_suggested(self, in_review):
        assert suggest(in_review.peer_reviewer, in_review, "checklist", "valuer", in_review.peer_reviewer.pk).status_code == 400

    def test_suggesting_again_updates_and_the_saved_value_withdraws(self, in_review):
        reviewer = in_review.peer_reviewer
        suggest(reviewer, in_review, "summary", "departures", "A")
        suggest(reviewer, in_review, "summary", "departures", "B")
        assert list(ReviewerEdit.objects.values_list("new_value", flat=True)) == ["B"]
        suggest(reviewer, in_review, "summary", "departures", in_review.summary.departures)
        assert not ReviewerEdit.objects.exists()

    def test_accepting_saves_it_and_unblocks_sign_off(self, in_review, dan):
        made = suggest(in_review.peer_reviewer, in_review, "summary", "departures", "None, as instructed.").json()
        assert any("hasn't answered" in b for b in signoff_ready(in_review))
        listed = client_for(dan).get("/api/jobs/").json()["results"]
        assert next(j for j in listed if j["id"] == in_review.pk)["reviewer_changes_to_accept"] == 1

        url = f"/api/jobs/{in_review.pk}/suggestions/{made['id']}/accept/"
        assert client_for(in_review.peer_reviewer).post(url).status_code == 403  # not their own
        res = client_for(dan).post(url)
        assert res.status_code == 200 and res.json()["status"] == "accepted"
        assert Job.objects.get(pk=in_review.pk).summary.departures == "None, as instructed."
        assert not any("hasn't answered" in b for b in signoff_ready(in_review))

    def test_declining_needs_a_reason(self, in_review, dan):
        made = suggest(in_review.peer_reviewer, in_review, "summary", "departures", "X").json()
        url = f"/api/jobs/{in_review.pk}/suggestions/{made['id']}/decline/"
        assert client_for(dan).post(url, {"reason": " "}, format="json").status_code == 400
        res = client_for(dan).post(url, {"reason": "The original is right."}, format="json")
        assert res.json()["status"] == "declined" and res.json()["decline_reason"] == "The original is right."
        assert not any("hasn't answered" in b for b in signoff_ready(in_review))

    def test_accept_all(self, in_review, dan):
        suggest(in_review.peer_reviewer, in_review, "summary", "departures", "A")
        suggest(in_review.peer_reviewer, in_review, "valuation", "valuation_commentary", "B")
        res = client_for(dan).post(f"/api/jobs/{in_review.pk}/reviewer-edits/accept/")
        assert res.status_code == 200 and res.json()["accepted"] == 2
        assert Job.objects.get(pk=in_review.pk).valuation.valuation_commentary == "B"

    def test_the_reviewer_can_withdraw_and_everyone_sees_them(self, in_review, dan):
        made = suggest(in_review.peer_reviewer, in_review, "summary", "departures", "A").json()
        shown = detail(dan, in_review)
        assert shown["can_decide_suggestions"] is True and shown["suggestions"][0]["new_text"] == "A"
        activity = client_for(dan).get(f"/api/jobs/{in_review.pk}/activity/").json()
        assert any(i["kind"] == "suggest" for i in activity)
        res = client_for(in_review.peer_reviewer).delete(f"/api/jobs/{in_review.pk}/suggestions/{made['id']}/")
        assert res.status_code == 204 and not ReviewerEdit.objects.exists()
