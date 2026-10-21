"""Villas recorded storey by storey (CRM feedback IN-05)."""
import pytest

from apps.jobs.constants import storeys_for
from apps.jobs.models import Job
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, patch, presets
from apps.reports.context import build_context

pytestmark = pytest.mark.django_db

__all__ = ["bank", "dan", "job", "presets"]


def test_the_storeys_follow_floors_and_basement():
    assert [k for k, _ in storeys_for(2, False)] == ["ground", "first"]
    assert [k for k, _ in storeys_for(3, True)] == ["basement", "ground", "first", "second"]
    assert len(storeys_for(9, False)) == 6  # at most six above ground
    assert [k for k, _ in storeys_for(None, False)] == ["ground"]


class TestRecording:
    def test_rooms_per_storey_with_custom_entries(self, job, dan, presets):
        client = client_for(dan)
        patch(client, job, "summary", {"property_category": "villa"})
        res = patch(client, job, "inspection", {
            "floors_above_ground": 2, "has_basement": True,
            "accommodation_by_storey": {"basement": ["store", "Home cinema"], "ground": ["kitchen"],
                                        "first": ["bedroom_en_suite"], "second": []},
        })
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert job.inspection.accommodation_by_storey == {
            "basement": ["store", "Home cinema"], "ground": ["kitchen"], "first": ["bedroom_en_suite"]}

    @pytest.mark.parametrize("value", [["kitchen"], {"attic": ["store"]}, {"ground": "kitchen"}])
    def test_bad_shapes_are_refused(self, job, dan, value):
        res = patch(client_for(dan), job, "inspection", {"accommodation_by_storey": value})
        assert "accommodation_by_storey" in res.json()["errors"]

    def test_floors_are_one_to_six(self, job, dan):
        assert "floors_above_ground" in patch(client_for(dan), job, "inspection",
                                              {"floors_above_ground": 7}).json()["errors"]


class TestReport:
    def test_accommodation_is_grouped_by_storey(self, job, presets):
        job.summary.property_category = "villa"
        job.summary.save()
        job.inspection.floors_above_ground, job.inspection.has_basement = 2, True
        job.inspection.accommodation_by_storey = {
            "basement": ["Home cinema"], "ground": ["kitchen", "guest_wc"], "first": ["bedroom_en_suite"],
        }
        job.inspection.save()
        rows = build_context(Job.objects.get(pk=job.pk))["accommodation"]
        assert [r["floor"] for r in rows] == ["Basement", "Ground floor", "First floor"]
        assert rows[0]["rooms"] == ["Home cinema"]
        assert rows[1]["rooms"] == ["Kitchen", "Guest W/C"]

    def test_an_apartment_keeps_one_list(self, job, presets):
        job.summary.property_category = "apartment"
        job.summary.save()
        job.inspection.accommodation_details = ["kitchen"]
        job.inspection.save()
        rows = build_context(Job.objects.get(pk=job.pk))["accommodation"]
        assert rows[0]["rooms"] == ["Kitchen"]
