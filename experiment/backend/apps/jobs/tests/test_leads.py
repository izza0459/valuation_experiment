"""Lead lost, the manager hierarchy and the Dashboard tab."""
import pytest
from django.core.management import call_command

from apps.accounts.models import Role
from apps.jobs.models import Job, JobTransition, Property
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, make_user, patch
from apps.jobs.workflow import JobStatus as S

pytestmark = pytest.mark.django_db

__all__ = ["bank", "dan", "job"]


@pytest.fixture(autouse=True)
def presets():
    call_command("seed_presets")


def lose(user, job, reason="client_cancelled", note=""):
    return client_for(user).post(f"/api/jobs/{job.pk}/lost/", {"reason": reason, "note": note}, format="json")


def listed(user, view):
    return [j["id"] for j in client_for(user).get("/api/jobs/", {"view": view}).json()["results"]]


class TestLeadLost:
    def test_the_valuer_marks_it_lost_with_a_reason(self, job, dan):
        assert client_for(dan).get(f"/api/jobs/{job.pk}/").json()["can_mark_lost"] is True
        res = lose(dan, job, note="Bank withdrew")
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert (job.status, job.lost_reason, job.lost_from_status) == (
            S.LOST, "client_cancelled", S.INSTRUCTION_RECEIVED)
        log = JobTransition.objects.get(job=job)
        assert log.to_status == S.LOST and "Bank withdrew" in log.comments
        detail = client_for(dan).get(f"/api/jobs/{job.pk}/").json()
        assert detail["lost"]["reason"] == "Client cancelled" and detail["can_mark_lost"] is False

    def test_a_reason_is_required_and_other_needs_a_note(self, job, dan):
        assert lose(dan, job, reason="").json()["errors"]["reason"]
        assert lose(dan, job, reason="other").json()["errors"]["note"]

    def test_lost_is_final(self, job, dan):
        lose(dan, job)
        assert patch(client_for(dan), job, "valuation", {"market_value": "1"}).status_code == 409
        assert client_for(dan).get(f"/api/jobs/{job.pk}/").json()["available_actions"] == []
        assert lose(dan, job).status_code == 409

    def test_issued_jobs_cant_be_lost(self, job, dan):
        Job.objects.filter(pk=job.pk).update(status=S.ISSUED, is_locked=True)
        assert lose(dan, job).status_code == 409

    def test_roles_without_the_lead_cant(self, job):
        assert lose(job.peer_reviewer, job).status_code == 403

    def test_lost_leads_leave_the_list_but_show_under_lost(self, job, dan):
        lose(dan, job)
        assert job.pk not in listed(dan, "all") and job.pk in listed(dan, "lost")


def lead(bank, **people):
    prop = Property.objects.create(building_name="T", community_name="JVC", latitude="25.05", longitude="55.21")
    return Job.objects.create(bank=bank, property=prop, **people)


class TestHierarchy:
    @pytest.fixture
    def team(self, bank):
        boss = make_user("boss", roles=[Role.VALUER])
        amy = make_user("amy", roles=[Role.VALUER], manager=boss)
        ben = make_user("ben", roles=[Role.INSPECTOR], manager=amy)
        out = make_user("out", roles=[Role.VALUER])
        jobs = {name: lead(bank, valuer=u) for name, u in (("boss", boss), ("amy", amy), ("out", out))}
        jobs["ben"] = lead(bank, inspected_by=ben)
        return boss, amy, ben, out, jobs

    def seen(self, user, **params):
        data = client_for(user).get("/api/dashboard/", params).json()
        return {p["id"] for p in data["pins"]}, data

    def test_a_manager_sees_everyone_below_them(self, team):
        boss, amy, ben, out, jobs = team
        ids, data = self.seen(boss)
        assert ids == {jobs["boss"].pk, jobs["amy"].pk, jobs["ben"].pk}
        assert data["scope"] == "team" and {p["name"] for p in data["people"]} == {"Boss", "Amy", "Ben"}
        assert self.seen(amy)[0] == {jobs["amy"].pk, jobs["ben"].pk}

    def test_anyone_else_sees_their_own(self, team):
        boss, amy, ben, out, jobs = team
        ids, data = self.seen(ben)
        assert ids == {jobs["ben"].pk} and data["scope"] == "mine" and data["people"] == []

    def test_an_admin_sees_everything(self, team):
        ids, data = self.seen(make_user("root", roles=[Role.ADMIN]))
        assert ids == {j.pk for j in team[4].values()} and data["scope"] == "all"

    def test_narrowing_to_someone_outside_the_team_shows_nothing(self, team):
        boss, amy, ben, out, jobs = team
        assert self.seen(boss, person=out.pk)[0] == set()
        assert self.seen(boss, person=ben.pk)[0] == {jobs["ben"].pk}

    def test_team_view_on_the_jobs_list(self, team):
        boss, amy, ben, out, jobs = team
        assert set(listed(boss, "team")) == {jobs["boss"].pk, jobs["amy"].pk, jobs["ben"].pk}

    def test_lost_counts_on_the_funnel_tiles_and_reasons(self, team):
        boss, amy, ben, out, jobs = team
        lose(amy, jobs["amy"])
        _, data = self.seen(boss)
        assert data["tiles"]["lost"] == 1 and data["tiles"]["active"] == 2
        assert next(s for s in data["funnel"] if s["key"] == "setup")["lost"]["count"] == 1
        assert data["lost_reasons"][0]["label"] == "Client cancelled"
        assert (data["by_community"][0]["label"], data["by_community"][0]["count"]) == ("JVC", 2)
