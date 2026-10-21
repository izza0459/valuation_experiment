"""The Scheduling stage between Setup and Inspection (CRM feedback SC-01..04)."""
import datetime

import pytest

from apps.accounts.models import Role
from apps.jobs.models import CallAttempt, Job
from apps.jobs.tabs import tab_completion, visibility_context
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, make_user, patch, presets
from apps.jobs.workflow import JobStatus as S

pytestmark = pytest.mark.django_db

# Fixtures from test_tabs, used by name below.
__all__ = ["bank", "dan", "job", "presets"]


def at_scheduling(job):
    Job.objects.filter(pk=job.pk).update(status=S.SCHEDULING)
    return Job.objects.get(pk=job.pk)


def completion(job):
    return tab_completion("scheduling", visibility_context(Job.objects.get(pk=job.pk)))


class TestCalls:
    def test_a_new_job_starts_not_called(self, job):
        assert job.scheduling.call_status == "not_called"
        assert "Inspection booked" in completion(at_scheduling(job))["missing"]

    def test_utc_needs_a_remark_and_is_logged(self, job, dan, presets):
        job = at_scheduling(job)
        client = client_for(dan)
        assert patch(client, job, "scheduling", {"call_status": "utc"}).status_code == 200
        assert "Remark" in completion(job)["missing"]
        patch(client, job, "scheduling", {"call_remark": "No answer, try after 4pm"}, base_version=1)
        log = list(CallAttempt.objects.filter(job=job).values_list("status", "remark"))
        assert log == [("utc", "No answer, try after 4pm"), ("utc", "")]

    def test_booking_moves_the_job_to_inspection_and_fills_the_date(self, job, dan, presets):
        job = at_scheduling(job)
        res = patch(client_for(dan), job, "scheduling", {
            "call_status": "answered_scheduled", "inspection_booked_at": "2026-10-23T10:30:00+04:00",
        })
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert job.status == S.INSPECTION_SCHEDULED
        assert job.inspection.inspection_date == datetime.date(2026, 10, 23)
        assert job.inspection_booked_at is not None
        assert res.json()["computed"]["inspection"]["inspection_booked_at"]

    def test_a_reschedule_keeps_the_earlier_date_in_the_log(self, job, dan, presets):
        job = at_scheduling(job)
        client = client_for(dan)
        patch(client, job, "scheduling", {"call_status": "answered_scheduled",
                                          "inspection_booked_at": "2026-10-23T10:30:00+04:00"})
        patch(client, job, "scheduling", {"inspection_booked_at": "2026-10-25T09:00:00+04:00"}, base_version=1)
        booked = [c.booked_for.date().isoformat() for c in CallAttempt.objects.filter(job=job)]
        assert booked == ["2026-10-25", "2026-10-23"]

    def test_the_job_detail_carries_the_log(self, job, dan, presets):
        job = at_scheduling(job)
        patch(client_for(dan), job, "scheduling", {"call_status": "answered_not_scheduled",
                                                   "call_remark": "Owner travelling"})
        log = client_for(dan).get(f"/api/jobs/{job.pk}/").json()["call_log"]
        assert log[0]["status_label"].startswith("Answered") and log[0]["remark"] == "Owner travelling"


class TestCarriedOver:
    def test_bank_contact_and_map_link_from_setup(self, job, dan):
        job.contact_name, job.contact_number = "R. Agent", "+971 50 000 0000"
        job.save()
        job.property.latitude, job.property.longitude = 25.2229, 55.2853
        job.property.save()
        computed = client_for(dan).get(f"/api/jobs/{job.pk}/").json()["tabs"]["scheduling"]["computed"]
        assert computed["contact_name"] == "R. Agent" and computed["contact_number"] == "+971 50 000 0000"
        assert computed["organisation_name"] == "Test Bank"
        assert computed["map_link"].startswith("https://www.google.com/maps/search/?api=1&query=25.2229")


class TestWhoAndWhen:
    def test_setup_needs_an_inspector_assigned(self, job):
        job.inspected_by = None
        job.save()
        assert any("Inspector" in m for m in tab_completion("instructions", visibility_context(job))["missing"])

    def test_ops_and_the_inspector_can_book_it(self, job, presets):
        ops, ines = make_user("olga", roles=[Role.OPS]), make_user("ines")
        job.inspected_by = ines
        job.save()
        job = at_scheduling(job)
        assert patch(client_for(ops), job, "scheduling", {"call_status": "utc", "call_remark": "x"}).status_code == 200
        assert patch(client_for(ines), job, "scheduling", {"call_remark": "y"}, base_version=1).status_code == 200

    def test_jobs_past_scheduling_count_it_done(self, job):
        Job.objects.filter(pk=job.pk).update(status=S.VALUATION_IN_PROGRESS)
        assert completion(job)["pct"] == 100
