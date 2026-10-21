"""CRM feedback (21 Oct 2026), the medium items: BUA in sqm, parking,
custom entries, market rent ranges, duplex as a villa, the COI check."""
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.jobs.models import Job, Property
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, make_user, patch, presets
from apps.reports.context import build_context

pytestmark = pytest.mark.django_db

# Fixtures from test_tabs, used by name below.
__all__ = ["bank", "dan", "job", "presets"]


def rows(ctx, key):
    return {r["label"]: r["value"] for r in ctx[key]}


class TestBuaInSqm:
    def test_entered_in_sqm_with_two_decimals_sqft_follows(self, job, dan):
        res = patch(client_for(dan), job, "summary", {"bua_sqm": "125.756"})
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert job.summary.bua_sqm == Decimal("125.76")
        assert job.summary.bua_sqft == Decimal("1353.67")

    def test_clearing_it_clears_sqft_too(self, job, dan):
        client = client_for(dan)
        patch(client, job, "summary", {"bua_sqm": "100"})
        patch(client, job, "summary", {"bua_sqm": ""}, base_version=1)
        job.refresh_from_db()
        assert (job.summary.bua_sqm, job.summary.bua_sqft) == (None, None)

    def test_the_report_states_sqm_then_sqft(self, job):
        job.summary.bua_sqm = Decimal("125.75")
        job.summary.save()
        assert rows(build_context(Job.objects.get(pk=job.pk)), "property_details")["Built-up area"] == (
            "125.75 sqm (1,354 sqft)")


class TestParking:
    @pytest.mark.parametrize("parking,spaces,expected", [
        ("yes", 2, "Parking for 2 cars"),
        ("assumed", 1, "Parking for 1 car (assumed)"),
        ("assumed", None, "Parking (assumed)"),
        ("no", 2, None),
    ])
    def test_what_the_report_says(self, job, parking, spaces, expected):
        job.summary.parking, job.summary.no_of_parkings = parking, spaces
        job.summary.save()
        accommodation = build_context(Job.objects.get(pk=job.pk))["accommodation"]
        found = [r["rooms"][0] for r in accommodation if r["floor"] == "Designated parking spaces"]
        assert found == ([expected] if expected else [])

    def test_only_the_listed_answers(self, job, dan, presets):
        assert patch(client_for(dan), job, "summary", {"parking": "assumed"}).status_code == 200
        res = patch(client_for(dan), job, "summary", {"parking": "maybe"}, base_version=1)
        assert "parking" in res.json()["errors"]


class TestCustomEntries:
    def test_rooms_and_amenities_take_typed_entries_printed_as_typed(self, job, dan, presets):
        client = client_for(dan)
        res = patch(client, job, "inspection", {"accommodation_details": ["kitchen", "Private cinema"]})
        assert res.status_code == 200, res.json()
        assert patch(client, job, "location", {"amenities": ["gym", "Padel courts"]}).status_code == 200
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert "Private cinema" in ctx["accommodation"][0]["rooms"]
        assert "Kitchen" in ctx["accommodation"][0]["rooms"]
        assert "Padel courts" in ctx["text"]["amenities"]

    def test_a_custom_entry_has_a_length_limit(self, job, dan):
        res = patch(client_for(dan), job, "location", {"amenities": ["x" * 101]})
        assert "amenities" in res.json()["errors"]


class TestMarketRent:
    @pytest.mark.parametrize("raw,stored", [
        ("40000", "40,000"), ("40,000", "40,000"), ("30,000 - 50,000", "30,000–50,000"),
        ("30000–50000", "30,000–50,000"),
    ])
    def test_a_figure_or_a_range(self, job, dan, raw, stored):
        assert patch(client_for(dan), job, "valuation", {"market_rent": raw}).status_code == 200
        job.refresh_from_db()
        assert job.valuation.market_rent == stored

    @pytest.mark.parametrize("raw", ["abc", "40,00", "1-2-3", "50,000-30,000", "40000.5", "AED 40000"])
    def test_anything_else_is_refused(self, job, dan, raw):
        assert "market_rent" in patch(client_for(dan), job, "valuation", {"market_rent": raw}).json()["errors"]

    def test_the_report_prints_the_range(self, job):
        job.valuation.market_rent = "30,000–50,000"
        job.valuation.save()
        summary = rows(build_context(Job.objects.get(pk=job.pk)), "valuation_summary")
        assert summary["Market Rent"] == "AED 30,000 – 50,000 per annum"


class TestDuplex:
    def test_a_duplex_follows_the_villa_fields(self, job, dan):
        res = patch(client_for(dan), job, "summary", {"property_category": "duplex", "property_sub_type": "Corner",
                                                       "plot_area_sqft": "3000"})
        assert res.status_code == 200, res.json()
        assert build_context(Job.objects.get(pk=job.pk))["plot_bearing"] is True


class TestCoiCheck:
    def other_job(self, bank, **prop):
        return Job.objects.create(bank=bank, property=Property.objects.create(**prop))

    def test_no_recent_instruction_suggests_no(self, job):
        assert job.coi_suggestion.startswith("Suggested: No.")

    def test_the_same_unit_in_the_last_year_suggests_yes(self, job, bank):
        job.property.unit_number = "1203"
        job.property.save()
        earlier = self.other_job(bank, unit_number="1203", building_name="marina gate 1")
        suggestion = Job.objects.get(pk=job.pk).coi_suggestion
        assert suggestion.startswith("Suggested: Yes.") and earlier.bayut_internal_reference_no in suggestion

    def test_the_same_applicant_suggests_yes(self, job, bank):
        job.property.applicant_name = "Fatima Al Mansoori"
        job.property.save()
        self.other_job(bank, applicant_name="Fatima Al Mansoori")
        assert "same applicant" in Job.objects.get(pk=job.pk).coi_suggestion

    def test_older_than_twelve_months_doesnt_count(self, job, bank):
        job.property.unit_number = "1203"
        job.property.save()
        earlier = self.other_job(bank, unit_number="1203", building_name="Marina Gate 1")
        Job.objects.filter(pk=earlier.pk).update(created_at=timezone.now() - timedelta(days=400))
        assert Job.objects.get(pk=job.pk).coi_suggestion.startswith("Suggested: No.")

    def test_who_confirmed_it_and_when_is_kept(self, job, dan, presets):
        res = patch(client_for(dan), job, "instructions", {"coi_check": "no"})
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert job.coi_confirmed_by == dan and job.coi_confirmed_at is not None
        assert job.coi_confirmed.startswith("By Dan")

    def test_yes_holds_setup_until_the_consent_is_uploaded(self, job, dan, presets, settings, tmp_path):
        from apps.presets.models import PresetOption

        PresetOption.objects.get_or_create(field_key="document_type", value="coi_consent",
                                           defaults={"label": "COI consent received (proof)"})
        client = client_for(dan)
        res = patch(client, job, "instructions", {"coi_check": "yes"}).json()
        assert "Consent received (proof)" in res["completion"]["instructions"]["missing"]
        from PIL import Image

        scan = io.BytesIO()
        Image.new("RGB", (400, 300), "white").save(scan, "PNG")
        consent = SimpleUploadedFile("consent.png", scan.getvalue(), content_type="image/png")
        upload = client.post(f"/api/jobs/{job.pk}/documents/", {"files": [consent], "doc_type": "coi_consent"},
                             format="multipart")
        assert upload.status_code in (200, 201), upload.content
        state = client.get(f"/api/jobs/{job.pk}/").json()["tabs"]["instructions"]["completion"]
        assert "Consent received (proof)" not in state["missing"]

    def test_jobs_need_it_answered_for_setup(self, job):
        from apps.jobs.tabs import tab_completion, visibility_context

        assert "COI Check" in tab_completion("instructions", visibility_context(job))["missing"]


class TestLocationMap:
    def test_built_from_the_coordinates_with_a_pin_and_stored(self, job, settings, monkeypatch):
        from PIL import Image

        from apps.reports import maps

        settings.LOCATION_MAPS = True
        tile = io.BytesIO()
        Image.new("RGB", (256, 256), "#cde").save(tile, "PNG")
        calls = []
        monkeypatch.setattr(maps, "_tile", lambda z, x, y: calls.append((z, x, y)) or tile.getvalue())
        job.property.latitude, job.property.longitude = Decimal("25.2229"), Decimal("55.2853")
        job.property.save()
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert ctx["property"]["map"].endswith(".jpg") and calls
        fetched = len(calls)
        build_context(Job.objects.get(pk=job.pk))
        assert len(calls) == fetched  # stored: fetched once per location

    def test_no_map_when_the_tiles_cant_be_fetched(self, job, settings, monkeypatch):
        from apps.reports import maps

        settings.LOCATION_MAPS = True

        def offline(*args):
            raise OSError("offline")

        monkeypatch.setattr(maps, "_tile", offline)
        job.property.latitude, job.property.longitude = Decimal("25.2229"), Decimal("55.2853")
        job.property.save()
        assert build_context(Job.objects.get(pk=job.pk))["property"]["map"] == ""


def test_make_user_is_shared():
    assert make_user("someone").pk
