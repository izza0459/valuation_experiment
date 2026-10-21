"""The admin pipeline dashboard (CRM feedback DB-01..03)."""
import datetime

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.jobs.models import Job, JobTransition, Property, SchedulingData
from apps.jobs.tests.test_tabs import bank, client_for, make_user
from apps.jobs.workflow import JobStatus as S

pytestmark = pytest.mark.django_db

__all__ = ["bank"]


@pytest.fixture
def boss():
    return make_user("boss", roles=[Role.ADMIN])


def new_job(bank, status=S.SETUP, received=None):
    job = Job.objects.create(bank=bank, property=Property.objects.create(building_name="Tower"),
                             date_time_request_received=received or timezone.now())
    Job.objects.filter(pk=job.pk).update(status=status)
    return Job.objects.get(pk=job.pk)


def entered(job, status, when=None):
    t = JobTransition.objects.create(job=job, from_status=S.SETUP, to_status=status)
    if when:
        JobTransition.objects.filter(pk=t.pk).update(created_at=when)


def funnel(user, **params):
    return client_for(user).get("/api/jobs/funnel/", params)


class TestFunnel:
    def test_counts_jobs_that_entered_each_stage_with_drop_off(self, bank, boss):
        a, b, c = new_job(bank), new_job(bank), new_job(bank)
        for job in (a, b):
            entered(job, S.SCHEDULING)
        entered(a, S.INSPECTION_SCHEDULED)
        stages = {s["key"]: s for s in funnel(boss).json()["stages"]}
        assert [stages[k]["count"] for k in ("setup", "scheduling", "inspection", "valuation")] == [3, 2, 1, 0]
        assert stages["scheduling"]["drop"] == {"count": 1, "pct": 33}
        assert {j["ref"] for j in stages["scheduling"]["jobs"]} == {a.bayut_internal_reference_no,
                                                                    b.bayut_internal_reference_no}
        assert c.pk  # in Set-up only

    def test_the_date_filter_recounts(self, bank, boss):
        old = new_job(bank, received=timezone.now() - datetime.timedelta(days=60))
        entered(old, S.SCHEDULING, when=timezone.now() - datetime.timedelta(days=60))
        new_job(bank)
        stages = {s["key"]: s["count"] for s in funnel(boss, range="30d").json()["stages"]}
        assert (stages["setup"], stages["scheduling"]) == (1, 0)
        start = (timezone.localdate() - datetime.timedelta(days=90)).isoformat()
        stages = {s["key"]: s["count"] for s in funnel(boss, **{"from": start}).json()["stages"]}
        assert (stages["setup"], stages["scheduling"]) == (2, 1)

    def test_admins_only(self, bank):
        assert funnel(make_user("val", roles=[Role.VALUER])).status_code == 403

    def test_bad_dates_are_refused(self, boss):
        assert funnel(boss, **{"from": "21/10/2026"}).status_code == 400


class TestSections:
    def test_scheduling_by_call_status(self, bank, boss):
        job = new_job(bank, status=S.SCHEDULING)
        entered(job, S.SCHEDULING)
        SchedulingData.objects.filter(job=job).update(call_status="utc")
        sections = {s["label"]: s["count"] for s in funnel(boss, stage="scheduling").json()["sections"]}
        assert sections["UTC (Unable to contact)"] == 1 and sections["Not Called"] == 0

    def test_peer_review_outcomes(self, bank, boss):
        waiting, returned = new_job(bank, status=S.PEER_REVIEW), new_job(bank, status=S.VALUATION_IN_PROGRESS)
        for job in (waiting, returned):
            entered(job, S.PEER_REVIEW)
        sections = {s["label"]: s["count"] for s in funnel(boss, stage="peer_review").json()["sections"]}
        assert sections == {"Awaiting review": 1, "Returned to valuer": 1, "Approved & signed": 0}

    def test_a_stage_by_the_section_being_worked_on(self, bank, boss):
        job = new_job(bank, status=S.SETUP)
        sections = funnel(boss, stage="setup").json()["sections"]
        assert sum(s["count"] for s in sections) == 1 and sections[0]["jobs"][0]["id"] == job.pk


class TestFiltering:
    def test_every_section_of_a_stage_gets_a_card(self, bank, boss):
        labels = [s["label"] for s in funnel(boss, stage="inspection").json()["sections"]]
        assert labels == ["Check List", "Preliminary Check", "Inspection", "Photos", "Ready for the next stage"]

    def test_the_jobs_list_filters_to_a_cards_jobs(self, bank, boss):
        a, b = new_job(bank), new_job(bank)
        listed = client_for(boss).get("/api/jobs/", {"ids": f"{a.pk}"}).json()["results"]
        assert [j["id"] for j in listed] == [a.pk] and b.pk
