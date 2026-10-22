"""Fixes from full QA (QA-NOTES, Oct 2026)."""
import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.jobs.models import Job
from apps.jobs.tabs import job_progress
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, make_user, patch
from apps.presets.dictionary import sync
from apps.presets.models import PresetOption, TextLibraryItem

pytestmark = pytest.mark.django_db

__all__ = ["bank", "dan", "job"]


@pytest.fixture
def library():
    call_command("seed_presets")
    sync(PresetOption, TextLibraryItem)


def errors(res):
    assert res.status_code == 400, res.json()
    return res.json()["errors"]


class TestRanges:
    """QA #8: implausible figures aren't saved."""

    @pytest.mark.parametrize("tab,key,value", [
        ("location", "built_about", "20566"),
        ("location", "built_about", "1850"),
        ("summary", "no_of_bedrooms", "21"),
        ("summary", "no_of_parkings", "-1"),
        ("summary", "ground_elevation", "900"),
        ("summary", "bua_sqm", "0"),
    ])
    def test_refused(self, job, dan, tab, key, value):
        assert key in errors(patch(client_for(dan), job, tab, {key: value}))

    def test_a_property_under_construction_may_give_a_future_year(self, job, dan):
        year = timezone.localdate().year + 2
        res = patch(client_for(dan), job, "location", {"property_status": "under_construction", "built_about": year})
        assert res.status_code == 200, res.json()


class TestBuiltYearAndDate:
    """QA #6: the year and the date can't disagree."""

    def test_the_date_sets_the_year(self, job, dan):
        res = patch(client_for(dan), job, "location", {"built_about": 2025, "built_date": "2015-03-01"})
        assert "built_about" in res.json()["errors"]  # they disagree
        res = patch(client_for(dan), job, "location", {"built_date": "2015-03-01"})
        assert res.status_code == 200 and res.json()["values"]["built_about"] == 2015

    def test_not_after_the_valuation_date(self, job, dan):
        job.valuation.valuation_date = datetime.date(2026, 1, 1)
        job.valuation.save()
        assert "built_date" in errors(patch(client_for(dan), job, "location", {"built_date": "2026-03-01"}))

    def test_not_in_the_future_for_a_completed_property(self, job, dan):
        future = (timezone.localdate() + datetime.timedelta(days=30)).isoformat()
        assert "built_date" in errors(patch(client_for(dan), job, "location", {"built_date": future}))


class TestReadyForNextStageIsGone:
    """QA #3."""

    def test_a_finished_stage_has_no_sub_status(self, job):
        Job.objects.filter(pk=job.pk).update(status="setup")
        progress = job_progress(Job.objects.get(pk=job.pk))
        assert progress["sub_status"] != "Ready for the next stage"


class TestLibraryAdmin:
    """QA #7."""

    def test_the_offered_for_types_are_editable(self, library):
        boss = make_user("boss", roles=["admin"])
        item = TextLibraryItem.objects.get(category="reinstatement", title="Villa / Townhouse")
        client = client_for(boss)
        assert "villa" in client.get("/api/admin/library/?category=reinstatement").json()[1]["property_categories"]
        res = client.patch(f"/api/admin/library/{item.pk}/", {"property_categories": ["villa"]}, format="json")
        assert res.status_code == 200 and res.json()["property_categories"] == ["villa"]

    def test_choosing_the_category_fills_an_empty_reinstatement_box(self, job, dan, library):
        job.valuation.reinstatement_note = ""
        job.valuation.save()
        patch(client_for(dan), job, "summary", {"property_category": "villa"})
        assert Job.objects.get(pk=job.pk).valuation.reinstatement_note.startswith(
            "The reinstatement cost of the property for insurance purposes")

    def test_a_blank_box_prints_the_librarys_wording_as_edited(self, job, library):
        from apps.reports.context import build_context

        TextLibraryItem.objects.filter(category="reinstatement", title="Apartment / Office / Retail").update(
            body="Edited unit wording.")
        job.summary.property_category = "apartment"
        job.summary.save()
        job.valuation.reinstatement_note = ""
        job.valuation.save()
        assert build_context(Job.objects.get(pk=job.pk))["reinstatement"] == "Edited unit wording."
