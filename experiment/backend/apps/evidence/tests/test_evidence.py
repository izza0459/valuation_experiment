"""The Evidence tab: comparables entered by hand, ticked for the report, and the
AVM that runs on them (CLAUDE.md §6)."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.banks.models import Bank
from apps.evidence import avm
from apps.evidence.models import AVMRun, Comparable, JobComparable
from apps.jobs.models import Job, Property
from apps.jobs.workflow import JobStatus
from apps.reports.context import build_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def dan():
    return User.objects.create(username="dan", email="dan@example.com", first_name="Dan")


@pytest.fixture
def job(dan):
    j = Job.objects.create(bank=Bank.objects.create(name="Bank"), property=Property.objects.create(), valuer=dan)
    j.summary.bua_sqft = Decimal("1000")
    j.summary.save()
    return Job.objects.get(pk=j.pk)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def add(user, job, **overrides):
    body = {"source": "bayut", "link": "https://www.bayut.com/property/details-1.html", "building_name": "Marina Gate",
            "community_name": "Dubai Marina", "property_type": "Apartment", "beds": 1, "floor": "12", "view": "Sea",
            "bua_sqft": "1000", "price_aed": "1500000", "transaction_date": "2026-08-01", "status": "asking",
            "notes": "Agent says offers at 1.45m."}
    body.update(overrides)
    return client_for(user).post(f"/api/jobs/{job.pk}/evidence/", body, format="json")


class TestManualEntry:
    def test_a_comparable_is_added_ticked_with_its_rate(self, job, dan):
        res = add(dan, job)
        assert res.status_code == 201, res.json()
        data = res.json()
        assert data["selected"] is True and data["aed_per_sqft"] == "1500.00"
        assert data["source_label"] == "Bayut" and data["link"].startswith("https://")
        assert Comparable.objects.get().created_by == dan

    def test_source_price_and_bua_are_required(self, job, dan):
        res = client_for(dan).post(f"/api/jobs/{job.pk}/evidence/", {"notes": "x"}, format="json")
        assert res.status_code == 400
        assert {"source", "price_aed", "bua_sqft"} <= set(res.json()["errors"])

    @pytest.mark.parametrize("field,value", [
        ("link", "bayut.com/x"), ("price_aed", "-5"), ("bua_sqft", "abc"), ("source", "zillow"),
        ("status", "maybe"), ("transaction_date", "yesterday"),
    ])
    def test_bad_values_are_refused(self, job, dan, field, value):
        assert field in add(dan, job, **{field: value}).json()["errors"]

    def test_it_can_be_unticked_edited_and_removed(self, job, dan):
        link_id = add(dan, job).json()["id"]
        client = client_for(dan)
        res = client.patch(f"/api/jobs/{job.pk}/evidence/{link_id}/", {"selected": False, "price_aed": "1600000"},
                           format="json")
        assert res.status_code == 200 and res.json()["selected"] is False
        assert res.json()["aed_per_sqft"] == "1600.00"
        assert client.delete(f"/api/jobs/{job.pk}/evidence/{link_id}/").status_code == 204
        assert not Comparable.objects.exists()

    def test_someone_without_a_valuer_role_cannot_add(self, job):
        stranger = User.objects.create(username="pat", email="pat@example.com")
        job.peer_reviewer = stranger
        job.save()
        assert add(stranger, job).status_code == 403

    def test_frozen_during_review(self, job, dan):
        Job.objects.filter(pk=job.pk).update(status=JobStatus.PEER_REVIEW)
        assert add(dan, job).status_code == 409


class TestAvm:
    def comparable(self, price, bua="1000"):
        return Comparable(source="bayut", price_aed=Decimal(price), bua_sqft=Decimal(bua))

    def test_median_rate_times_bua_rounded_to_a_thousand(self):
        result = avm.compute([self.comparable(p) for p in ("1400000", "1500000", "1650000")], Decimal("850"))
        assert result["aed_per_sqft"] == Decimal("1500.00")
        assert result["suggested_value"] == Decimal("1275000")  # 1,500 x 850
        assert (result["low_value"], result["high_value"]) == (Decimal("1190000"), Decimal("1403000"))
        assert result["confidence"] == "medium"

    def test_confidence_follows_count_and_agreement(self):
        tight = [self.comparable(p) for p in ("1480000", "1500000", "1500000", "1510000", "1520000")]
        assert avm.compute(tight, Decimal("1000"))["confidence"] == "high"
        assert avm.compute([self.comparable("1500000")], Decimal("1000"))["confidence"] == "low"

    def test_says_what_it_needs(self):
        assert "error" in avm.compute([], Decimal("1000"))
        assert "error" in avm.compute([self.comparable("1500000")], None)

    def test_deviation_from_the_valuers_figure_is_flagged(self):
        result = avm.compute([self.comparable("1500000")], Decimal("1000"), market_value=Decimal("1700000"))
        assert result["workings"]["deviation_pct"] == "13.3"
        assert result["workings"]["deviation_over_threshold"] is True

    def test_a_run_uses_only_ticked_comparables_and_is_stored(self, job, dan):
        add(dan, job, price_aed="1500000")
        unticked = add(dan, job, price_aed="3000000").json()["id"]
        client_for(dan).patch(f"/api/jobs/{job.pk}/evidence/{unticked}/", {"selected": False}, format="json")
        res = client_for(dan).post(f"/api/jobs/{job.pk}/avm/")
        assert res.status_code == 201, res.json()
        assert res.json()["suggested_value"] == "1500000.00"
        run = AVMRun.objects.get()
        assert len(run.inputs["comparable_ids"]) == 1 and run.created_by == dan
        assert client_for(dan).get(f"/api/jobs/{job.pk}/evidence/").json()["avm"]["id"] == run.id


class TestReport:
    def test_ticked_comparables_fill_the_report_table(self, job, dan):
        add(dan, job)
        add(dan, job, building_name="Unticked")
        JobComparable.objects.filter(comparable__building_name="Unticked").update(selected=False)
        rows = build_context(Job.objects.get(pk=job.pk))["comparables"]
        assert rows == [{
            "district": "Marina Gate, Dubai Marina", "views": "Sea", "floor": "12", "bua_sqft": "1,000",
            "type": "1 BR Apartment", "price": "1,500,000", "rate": "1,500", "transaction": "Asking Aug-26",
        }]
