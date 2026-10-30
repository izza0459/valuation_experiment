"""Coordinates stay in the UAE, the lead card's Bayut-style data, grouped
property types and reassigning a lead."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.jobs.models import Job
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, patch
from apps.jobs.workflow import JobStatus as S
from apps.presets.options import options_for

pytestmark = pytest.mark.django_db

__all__ = ["bank", "dan", "job"]


class TestCoordinates:
    def test_uae_coordinates_save(self, job, dan):
        res = patch(client_for(dan), job, "address", {"latitude": "25.0805", "longitude": "55.1403"})
        assert res.status_code == 200, res.json()

    def test_swapped_ones_are_refused_with_a_hint(self, job, dan):
        res = patch(client_for(dan), job, "address", {"latitude": "55.1403"})
        assert res.status_code == 400
        assert "wrong way round" in res.json()["errors"]["latitude"]

    def test_outside_the_uae_is_refused(self, job, dan):
        res = patch(client_for(dan), job, "address", {"longitude": "37.6"})
        assert "Outside the UAE" in res.json()["errors"]["longitude"]

    def test_the_map_leaves_out_mistyped_leads(self, job, dan):
        prop = job.property
        prop.latitude, prop.longitude = Decimal("55.2"), Decimal("25.1")
        prop.save()
        data = client_for(dan).get("/api/dashboard/").json()
        assert job.pk in data["misplaced"] and not any(p["id"] == job.pk for p in data["pins"])


class TestLeadCard:
    def test_location_in_bayuts_order(self, job, dan):
        prop = job.property
        prop.unit_number = "1203"
        prop.save()
        data = client_for(dan).get(f"/api/jobs/{job.pk}/").json()
        assert data["location_path"][0] == "Dubai"
        assert data["location_path"][-1] == f"Unit {prop.unit_number}"
        listed = client_for(dan).get("/api/jobs/").json()["results"]
        assert next(j for j in listed if j["id"] == job.pk)["location_line"].startswith(f"Unit {prop.unit_number} · ")

    def test_checks(self, job, dan):
        Job.objects.filter(pk=job.pk).update(coi_check="no")
        checks = {c["key"]: c["ok"] for c in client_for(dan).get(f"/api/jobs/{job.pk}/").json()["checks"]}
        assert checks["coi"] is True and checks["makani"] is False

    def test_property_types_are_grouped(self):
        groups = {o["value"]: o.get("group") for o in options_for("property_category")}
        assert groups["apartment"] == "Residential" and groups["fitted_office"] == "Commercial"


class TestReassign:
    @pytest.fixture
    def other(self):
        return get_user_model().objects.create_user("sam", "sam@example.test", roles=["valuer"])

    def test_choices_and_reassigning(self, job, dan, other):
        client = client_for(dan)
        choices = client.get(f"/api/jobs/{job.pk}/assign/").json()
        assert any(p["id"] == other.pk for p in choices["people"]["valuer"])
        assert client.get(f"/api/jobs/{job.pk}/").json()["can_reassign"] is True
        res = client.post(f"/api/jobs/{job.pk}/assign/", {"role": "valuer", "person": other.pk}, format="json")
        assert res.status_code == 200, res.json()
        assert Job.objects.get(pk=job.pk).valuer == other
        activity = client.get(f"/api/jobs/{job.pk}/activity/").json()
        assert any(i["kind"] == "assign" and i["title"] == "Valuer reassigned" for i in activity)

    def test_only_someone_who_can_take_the_role(self, job, dan):
        nobody = get_user_model().objects.create_user("ins", "ins@example.test", roles=["inspector"])
        res = client_for(dan).post(f"/api/jobs/{job.pk}/assign/", {"role": "valuer", "person": nobody.pk},
                                   format="json")
        assert res.status_code == 400 and "person" in res.json()["errors"]

    def test_not_by_an_outsider_or_on_a_closed_lead(self, job, dan, other):
        outsider = get_user_model().objects.create_user("out", "out@example.test", roles=["valuer"])
        body = {"role": "valuer", "person": other.pk}
        assert client_for(outsider).post(f"/api/jobs/{job.pk}/assign/", body, format="json").status_code in (403, 404)
        Job.objects.filter(pk=job.pk).update(status=S.LOST)
        assert client_for(dan).post(f"/api/jobs/{job.pk}/assign/", body, format="json").status_code == 409

    def test_a_manager_can_reassign_their_reports_lead(self, job, dan, other):
        boss = get_user_model().objects.create_user("boss", "boss@example.test", roles=["valuer"])
        get_user_model().objects.filter(pk=dan.pk).update(manager=boss)
        res = client_for(boss).post(f"/api/jobs/{job.pk}/assign/", {"role": "valuer", "person": other.pk},
                                    format="json")
        assert res.status_code == 200, res.json()
