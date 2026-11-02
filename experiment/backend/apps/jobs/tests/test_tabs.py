"""The tab read/write path: storage routing, validation, concurrency, roles,
locking and audit (CLAUDE.md §3, §4, §8)."""
from datetime import date

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.banks.models import Bank
from apps.jobs import tabs
from apps.jobs.field_config import TABS, get_tab
from apps.jobs.models import Job, JobTabVersion, Property
from apps.jobs.workflow import JobLockedError, JobStatus

pytestmark = pytest.mark.django_db


# --- fixtures ---------------------------------------------------------------


def make_user(name, roles=None, **kwargs):
    return User.objects.create(
        username=name, email=f"{name}@example.com", first_name=name.title(), roles=roles or [], **kwargs
    )


@pytest.fixture
def bank():
    return Bank.objects.create(name="Test Bank", billing_address="1 Bank St", sla_signed=True)


@pytest.fixture
def dan():
    return make_user("dan")


@pytest.fixture
def job(bank, dan):
    """Dan holds every working role, as in the team today."""
    return Job.objects.create(
        bank=bank,
        property=Property.objects.create(building_name="Marina Gate 1", community_name="Dubai Marina"),
        valuer=dan,
        inspected_by=dan,
        registered_valuer=dan,
        peer_reviewer=make_user("pat"),
    )


@pytest.fixture
def presets():
    call_command("seed_presets")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def patch(client, job, tab, values, base_version=0):
    return client.patch(
        f"/api/jobs/{job.pk}/tabs/{tab}/", {"base_version": base_version, "values": values}, format="json"
    )


# --- config integrity ---------------------------------------------------------


class TestFieldConfigStorage:
    def test_every_editable_field_has_exactly_one_home(self):
        """A field in the config with no column would be silently dropped on
        save. Failing here is the point."""
        for tab in TABS:
            for f in tab["fields"]:
                if not f["calculated"]:
                    tabs.resolve_storage(tab["key"], f["key"])

    def test_every_calculated_field_is_actually_computed(self, job):
        for tab in TABS:
            computed = tabs.tab_computed(job, tab["key"]) if tab["fields"] else {}
            for f in tab["fields"]:
                if f["calculated"]:
                    assert f["key"] in computed, f"{tab['key']}.{f['key']} is never computed"

    def test_fields_route_to_the_row_that_stores_them(self):
        assert tabs.resolve_storage("checklist", "valuer")[0] == "job"
        assert tabs.resolve_storage("checklist", "makani_photo")[0] == "tab"
        assert tabs.resolve_storage("address", "unit_number")[0] == "property"
        assert tabs.resolve_storage("instructions", "bank_reference_no")[0] == "job"
        assert tabs.resolve_storage("valuation", "market_value")[0] == "tab"


class TestVisibilityAndCompletion:
    def field(self, tab, key):
        return next(f for f in get_tab(tab)["fields"] if f["key"] == key)

    @pytest.mark.parametrize("category,visible", [
        ("villa", True), ("custom_villa", True), ("townhouse", True), ("apartment", False), ("", False),
    ])
    def test_plot_fields_follow_property_category(self, category, visible):
        context = {"summary": {"property_category": category}}
        assert tabs.is_field_visible(self.field("summary", "plot_area_sqft"), context) is visible

    def test_hidden_required_fields_do_not_count(self, monkeypatch):
        tab = {"fields": [
            {"key": "a", "label": "A", "required": True, "visible_if": None},
            {"key": "b", "label": "B", "required": True,
             "visible_if": {"field": "t.flag", "op": "is_true"}},
        ]}
        monkeypatch.setattr(tabs, "get_tab", lambda key: tab)
        assert tabs.tab_completion("t", {"t": {"a": "x", "flag": False}}) == {"pct": 100, "missing": []}
        assert tabs.tab_completion("t", {"t": {"a": "x", "flag": True}})["missing"] == ["B"]

    def test_false_and_zero_count_as_filled(self, monkeypatch):
        tab = {"fields": [{"key": "a", "label": "A", "required": True, "visible_if": None}]}
        monkeypatch.setattr(tabs, "get_tab", lambda key: tab)
        assert tabs.tab_completion("t", {"t": {"a": False}})["pct"] == 100
        assert tabs.tab_completion("t", {"t": {"a": 0}})["pct"] == 100

    def test_role_fks_on_the_job_count_toward_checklist_completion(self, job):
        """Regression: inspected_by/valuer live on Job, not on the checklist
        row, and used to read as missing however they were set."""
        state = tabs.job_tab_state(job)["checklist"]
        assert state["completion"]["pct"] == 100
        assert state["values"]["valuer"] == job.valuer_id


# --- writing ------------------------------------------------------------------


class TestPatch:
    def test_updates_the_row_that_stores_each_field(self, job, dan):
        res = patch(client_for(dan), job, "checklist", {"makani_photo": True, "peer_reviewer": dan.pk})
        assert res.status_code == 200
        job.refresh_from_db()
        assert job.checklist.makani_photo is True
        assert job.peer_reviewer_id == dan.pk

    def test_instructions_and_address_store_on_job_and_property(self, job, dan):
        client = client_for(dan)
        assert patch(client, job, "instructions", {"bank_reference_no": "DIB-1"}).status_code == 200
        res = patch(client, job, "address", {"unit_number": "312", "applicant_name": "A. Suwaidi"})
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert job.bank_reference_no == "DIB-1"
        assert job.property.unit_number == "312"
        assert job.property.applicant_name == "A. Suwaidi"

    def test_only_the_named_fields_change(self, job, dan):
        patch(client_for(dan), job, "summary", {"makani_number": "123"})
        patch(client_for(dan), job, "summary", {"dewa_number": "456"}, base_version=1)
        job.refresh_from_db()
        assert (job.summary.makani_number, job.summary.dewa_number) == ("123", "456")

    def test_returns_server_computed_values(self, job, dan):
        res = patch(client_for(dan), job, "summary", {"bua_sqm": "48.22"}).json()
        # BUA is entered in sqm to 2 decimals; sqft follows (CRM feedback IN-01).
        assert res["values"]["bua_sqm"] == "48.22"
        assert res["computed"]["summary"]["bua_sqft"] == "519.04"

    def test_a_change_on_one_tab_updates_computed_values_on_another(self, job, dan):
        """Rate/sqft is on Valuation but depends on the BUA from Summary."""
        client = client_for(dan)
        patch(client, job, "valuation", {"market_value": "725000"})
        res = patch(client, job, "summary", {"bua_sqm": "48.22"}).json()
        valuation = res["computed"]["valuation"]
        assert valuation["market_value_rate_per_sqft"] == "1397"  # 725,000 / 519.04 sqft, rounded
        assert valuation["market_value_in_words"] == "Seven Hundred and Twenty-Five Thousand UAE Dirhams"

    def test_completion_is_returned_for_every_tab(self, job, dan):
        res = patch(client_for(dan), job, "summary", {"bua_sqm": "48.22"}).json()
        assert set(res["completion"]) == {t["key"] for t in TABS}
        assert "BUA (sqm)" not in res["completion"]["summary"]["missing"]

    def test_bad_requests(self, job, dan):
        client = client_for(dan)
        assert client.patch(f"/api/jobs/{job.pk}/tabs/summary/", {"values": {"makani_number": "1"}},
                            format="json").status_code == 400  # no base_version
        assert patch(client, job, "summary", {}).status_code == 400
        assert patch(client, job, "nonsense", {"a": 1}).status_code == 404
        assert patch(client, job, "photos", {"a": 1}).status_code == 404


class TestValidation:
    def errors(self, client, job, tab, values):
        res = patch(client, job, tab, values)
        assert res.status_code == 400, res.json()
        assert res.json()["code"] == "validation"
        return res.json()["errors"]

    def test_unknown_and_calculated_fields_are_refused(self, job, dan):
        errors = self.errors(client_for(dan), job, "summary", {"nope": 1, "bua_sqft": "10"})
        assert errors["nope"] == "Unknown field."
        assert "Calculated" in errors["bua_sqft"]

    def test_a_field_from_another_tab_is_refused(self, job, dan):
        assert "Unknown" in self.errors(client_for(dan), job, "summary", {"market_value": "1"})["market_value"]

    def test_nothing_is_written_if_any_field_is_invalid(self, job, dan):
        res = patch(client_for(dan), job, "summary", {"makani_number": "999", "bua_sqm": "abc"})
        assert res.status_code == 400
        job.refresh_from_db()
        assert job.summary.makani_number == ""
        assert not JobTabVersion.objects.filter(job=job, tab_key="summary", version__gt=0).exists()
        assert not AuditLog.objects.filter(job=job, field_name="makani_number").exists()

    @pytest.mark.parametrize("value", ["abc", "1e999", "NaN", True, "-5"])
    def test_bad_money_values(self, job, dan, value):
        assert "market_value" in self.errors(client_for(dan), job, "valuation", {"market_value": value})

    def test_figures_are_rounded_to_whole_numbers_and_take_commas(self, job, dan):
        """Field dictionary round 2: no decimals anywhere; numbers are typed
        with thousands separators."""
        res = patch(client_for(dan), job, "valuation", {"market_value": "1,250,000.50", "market_rent": "84999"})
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert (job.valuation.market_value, job.valuation.market_rent) == (1250001, "84,999")

    def test_whole_number_fields_take_commas_too(self, job, dan):
        res = patch(client_for(dan), job, "summary", {"no_of_bedrooms": "3", "total_floors": "1,0"})
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert (job.summary.no_of_bedrooms, job.summary.total_floors) == (3, 10)

    def test_coordinates_are_rounded_to_what_the_column_keeps(self, job, dan):
        res = patch(client_for(dan), job, "address", {"latitude": "25.04030429", "longitude": "55.28623161"})
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert str(job.property.latitude) == "25.040304"

    @pytest.mark.parametrize("key,value", [("latitude", "91"), ("longitude", "-181")])
    def test_coordinates_are_range_checked(self, job, dan, key, value):
        assert key in self.errors(client_for(dan), job, "address", {key: value})

    def test_percentages_are_bounded(self, job, dan):
        assert "completion_pct" in self.errors(client_for(dan), job, "valuation", {"completion_pct": "101"})

    def test_elevation_may_be_negative(self, job, dan):
        assert patch(client_for(dan), job, "summary", {"ground_elevation": "-2.5"}).status_code == 200

    def test_wrong_types(self, job, dan):
        errors = self.errors(client_for(dan), job, "summary", {
            "parking": 5, "no_of_bedrooms": "two", "lease_expiry": "31/12/2030",
            "information_provided": "Title Deed", "makani_number": 5,
        })
        assert set(errors) == {"parking", "no_of_bedrooms", "lease_expiry", "information_provided", "makani_number"}

    def test_max_length_is_enforced(self, job, dan):
        assert "makani_number" in self.errors(client_for(dan), job, "summary", {"makani_number": "9" * 51})

    def test_selects_must_be_an_available_option(self, job, dan, presets):
        client = client_for(dan)
        errors = self.errors(client, job, "summary", {"interest_valued": "freehold_ish"})
        assert "Not one of" in errors["interest_valued"]
        assert patch(client, job, "summary", {"interest_valued": "gcc_freehold"}).status_code == 200

    def test_multiselects_must_be_available_options(self, job, dan, presets):
        errors = self.errors(client_for(dan), job, "inspection", {"flooring": ["marble", "lava"]})
        assert "lava" in errors["flooring"]

    def test_multiselect_values_are_deduplicated(self, job, dan, presets):
        patch(client_for(dan), job, "inspection", {"flooring": ["marble", "marble", "carpet"]})
        job.refresh_from_db()
        assert job.inspection.flooring == ["marble", "carpet"]

    def test_a_deactivated_preset_already_on_the_job_can_still_be_saved(self, job, dan, presets):
        from apps.presets.models import PresetOption

        client = client_for(dan)
        patch(client, job, "summary", {"interest_valued": "gcc_freehold"})
        PresetOption.objects.filter(field_key="interest_valued", value="gcc_freehold").update(active=False)
        res = patch(client, job, "summary", {"interest_valued": "gcc_freehold", "makani_number": "1"}, base_version=1)
        assert res.status_code == 200

    def test_an_unpopulated_option_list_does_not_block_editing(self, job, dan):
        """Before an admin has set a list up there is nothing to check
        against; refusing everything would make the field unusable."""
        from apps.presets.models import PresetOption

        PresetOption.objects.filter(field_key="interest_valued").delete()
        assert patch(client_for(dan), job, "summary", {"interest_valued": "anything"}).status_code == 200

    def test_free_text_fields_accept_text_outside_the_suggestions(self, job, dan, presets):
        res = patch(client_for(dan), job, "address", {"community_name": "Brand New Community"})
        assert res.status_code == 200

    def test_people_and_masters_must_exist_and_be_active(self, job, dan):
        client = client_for(dan)
        gone = make_user("gone", is_active=False)
        errors = self.errors(client, job, "instructions", {"registered_valuer": gone.pk, "bank": 9999})
        assert set(errors) == {"registered_valuer", "bank"}

    def test_a_mortgage_job_without_a_bank_is_incomplete(self, job, dan):
        res = patch(client_for(dan), job, "instructions", {"bank": None})
        assert res.status_code == 200
        assert "Bank / Organisation" in res.json()["completion"]["instructions"]["missing"]

    def test_picking_a_bank_fills_the_reference_with_its_code(self, job, dan):
        other = Bank.objects.create(name="Other Bank", code="OB-1")
        third = Bank.objects.create(name="Third Bank", code="TB-9")
        client = client_for(dan)
        res = patch(client, job, "instructions", {"bank": other.pk})
        assert res.json()["values"]["bank_reference_no"] == "OB-1"
        # Switching again replaces the old bank's untouched code ...
        res = patch(client, job, "instructions", {"bank": third.pk}, base_version=1)
        assert res.json()["values"]["bank_reference_no"] == "TB-9"
        # ... but never a reference typed by hand.
        patch(client, job, "instructions", {"bank_reference_no": "REQ-1"}, base_version=2)
        res = patch(client, job, "instructions", {"bank": other.pk}, base_version=3)
        assert res.json()["values"]["bank_reference_no"] == "REQ-1"

    def test_audit_and_internal_work_names_a_client_instead_of_a_bank(self, job, dan):
        client = client_for(dan)
        res = patch(client, job, "instructions", {"purpose": "audit_purpose", "bank": None}).json()
        assert "Organisation / Client name" in res["completion"]["instructions"]["missing"]
        assert "Bank / Organisation" not in res["completion"]["instructions"]["missing"]
        patch(client, job, "instructions", {"client_name": "Acme Holdings"}, base_version=1)
        job.refresh_from_db()
        assert job.organisation_name == "Acme Holdings"

    def test_owners_and_applicants_are_lists(self, job, dan):
        res = patch(client_for(dan), job, "address", {"ownership_name": ["A. One", " ", "B. Two"]})
        assert res.status_code == 200, res.json()
        assert res.json()["values"]["ownership_name"] == ["A. One", "B. Two"]
        job.refresh_from_db()
        assert job.property.ownership_names == ["A. One", "B. Two"]

    def test_library_lists_need_titles(self, job, dan):
        errors = self.errors(client_for(dan), job, "summary", {"special_assumptions": [{"body": "x"}]})
        assert "special_assumptions" in errors
        ok = patch(client_for(dan), job, "summary", {"special_assumptions": [{"title": "T", "body": "B"}]})
        assert ok.status_code == 200

    def test_required_is_reported_not_enforced(self, job, dan):
        """Autosave has to accept a draft; completeness is a gate elsewhere."""
        res = patch(client_for(dan), job, "valuation", {"market_value": None})
        assert res.status_code == 200
        assert "Market Value (AED)" in res.json()["completion"]["valuation"]["missing"]


# --- concurrency --------------------------------------------------------------


class TestFirstEditWins:
    def test_each_save_bumps_the_tab_version(self, job, dan):
        client = client_for(dan)
        assert patch(client, job, "summary", {"makani_number": "1"}, base_version=0).json()["version"] == 1
        assert patch(client, job, "summary", {"makani_number": "2"}, base_version=1).json()["version"] == 2

    def test_a_stale_save_is_refused_and_changes_nothing(self, job, dan):
        client = client_for(dan)
        assert patch(client, job, "summary", {"makani_number": "FIRST"}, base_version=0).status_code == 200

        late = patch(client, job, "summary", {"makani_number": "SECOND", "dewa_number": "X"}, base_version=0)

        assert late.status_code == 409
        body = late.json()
        assert body["code"] == "conflict"
        assert body["current"]["version"] == 1
        assert body["current"]["values"]["makani_number"] == "FIRST"
        job.refresh_from_db()
        assert (job.summary.makani_number, job.summary.dewa_number) == ("FIRST", "")

    def test_a_save_ahead_of_the_server_is_refused_too(self, job, dan):
        assert patch(client_for(dan), job, "summary", {"makani_number": "1"}, base_version=7).status_code == 409

    def test_the_loser_can_retry_from_the_returned_version(self, job, dan):
        client = client_for(dan)
        patch(client, job, "summary", {"makani_number": "FIRST"}, base_version=0)
        late = patch(client, job, "summary", {"dewa_number": "X"}, base_version=0).json()
        retry = patch(client, job, "summary", {"dewa_number": "X"}, base_version=late["current"]["version"])
        assert retry.status_code == 200

    def test_different_tabs_never_conflict(self, job, dan):
        """The inspector and valuer work on different tabs at the same time;
        that must not make either's autosave fail."""
        client = client_for(dan)
        assert patch(client, job, "summary", {"makani_number": "1"}).status_code == 200
        assert patch(client, job, "inspection", {"repairs": "none"}).status_code == 200

    def test_a_rejected_save_does_not_consume_a_version(self, job, dan):
        client = client_for(dan)
        patch(client, job, "summary", {"bua_sqm": "abc"})
        assert patch(client, job, "summary", {"makani_number": "1"}, base_version=0).status_code == 200


# --- roles --------------------------------------------------------------------


class TestRoles:
    def test_inspector_edits_inspection_but_not_valuation(self, bank):
        ines = make_user("ines")
        job = Job.objects.create(bank=bank, property=Property.objects.create(), inspected_by=ines)
        client = client_for(ines)
        assert patch(client, job, "inspection", {"repairs": "none"}).status_code == 200
        res = patch(client, job, "valuation", {"market_value": "1"})
        assert res.status_code == 403 and res.json()["code"] == "forbidden"

    def test_inspector_cannot_reassign_the_valuer_from_the_checklist(self, bank):
        ines, val = make_user("ines"), make_user("val")
        job = Job.objects.create(bank=bank, property=Property.objects.create(), inspected_by=ines, valuer=val)
        assert patch(client_for(ines), job, "checklist", {"makani_photo": True}).status_code == 200
        assert patch(client_for(ines), job, "checklist", {"valuer": ines.pk}, base_version=1).status_code == 403

    def test_peer_reviewer_and_counter_signatory_cannot_edit(self, bank):
        pat, cos = make_user("pat"), make_user("cos")
        job = Job.objects.create(bank=bank, property=Property.objects.create(), peer_reviewer=pat,
                                 counter_signatory=cos)
        for user in (pat, cos):
            assert patch(client_for(user), job, "summary", {"makani_number": "1"}).status_code == 403

    def test_someone_with_no_role_on_the_job_cannot_see_it(self, job):
        assert patch(client_for(make_user("stranger")), job, "summary", {"makani_number": "1"}).status_code == 404

    def test_platform_admin_can_edit_any_tab(self, job):
        boss = make_user("boss", roles=[Role.ADMIN])
        assert patch(client_for(boss), job, "valuation", {"market_value": "1"}).status_code == 200

    def test_unauthenticated_is_refused(self, job):
        assert patch(APIClient(), job, "summary", {"makani_number": "1"}).status_code in (401, 403)

    def test_valuer_can_fill_the_admin_tab_for_now(self, bank):
        """CLAUDE.md §4: 'Admin later' = the valuer fills it for now."""
        val = make_user("val")
        job = Job.objects.create(bank=bank, property=Property.objects.create(), valuer=val)
        assert patch(client_for(val), job, "instructions", {"bank_reference_no": "X"}).status_code == 200


# --- locking and review freeze ----------------------------------------------------


class TestLockAndFreeze:
    def test_an_issued_job_refuses_edits(self, job, dan):
        Job.objects.filter(pk=job.pk).update(is_locked=True, status=JobStatus.ISSUED)
        res = patch(client_for(dan), job, "summary", {"makani_number": "1"})
        assert res.status_code == 409 and res.json()["code"] == "locked"

    @pytest.mark.parametrize("status", [JobStatus.PEER_REVIEW, JobStatus.APPROVED_SIGNED])
    def test_review_and_signoff_freeze_the_data(self, job, dan, status):
        Job.objects.filter(pk=job.pk).update(status=status)
        res = patch(client_for(dan), job, "valuation", {"market_value": "999"})
        assert res.status_code == 409 and res.json()["code"] == "frozen"
        job.refresh_from_db()
        assert job.valuation.market_value is None

    def test_returned_to_the_valuer_it_is_editable_again(self, job, dan):
        Job.objects.filter(pk=job.pk).update(status=JobStatus.VALUATION_IN_PROGRESS)
        assert patch(client_for(dan), job, "valuation", {"market_value": "725000"}).status_code == 200


# --- audit --------------------------------------------------------------------


class TestAudit:
    def test_changes_are_attributed_to_the_requesting_user(self, job, dan):
        """The client authenticates per-request (as a token would), so the
        middleware never sees the user; the write path has to carry it."""
        patch(client_for(dan), job, "summary", {"makani_number": "777"})
        entry = AuditLog.objects.get(job=job, field_name="makani_number")
        assert entry.changed_by == dan
        assert (entry.old_value, entry.new_value) == ("", "777")

    def test_property_edits_are_audited_too(self, job, dan):
        patch(client_for(dan), job, "address", {"unit_number": "312"})
        entry = AuditLog.objects.get(model_name="Property", field_name="unit_number")
        assert entry.job == job and entry.changed_by == dan

    def test_job_level_fields_are_audited(self, job, dan):
        patch(client_for(dan), job, "instructions", {"bank_reference_no": "DIB-9"})
        assert AuditLog.objects.filter(job=job, model_name="Job", field_name="bank_reference_no").exists()


# --- instructions specifics -------------------------------------------------------


class TestBillingAddress:
    def other_bank(self):
        return Bank.objects.create(name="Other", billing_address="2 Other St", sla_signed=True)

    def test_follows_the_bank_when_it_was_the_banks_own_address(self, bank, dan):
        job = Job.objects.create(bank=bank, property=Property.objects.create(), valuer=dan,
                                 billing_address=bank.billing_address)
        other = self.other_bank()
        patch(client_for(dan), job, "instructions", {"bank": other.pk})
        job.refresh_from_db()
        assert job.billing_address == "2 Other St"

    def test_a_hand_typed_address_is_never_overwritten(self, bank, dan):
        job = Job.objects.create(bank=bank, property=Property.objects.create(), valuer=dan,
                                 billing_address="Typed by hand")
        patch(client_for(dan), job, "instructions", {"bank": self.other_bank().pk})
        job.refresh_from_db()
        assert job.billing_address == "Typed by hand"

    def test_not_carried_to_a_bank_without_a_signed_sla(self, bank, dan):
        job = Job.objects.create(bank=bank, property=Property.objects.create(), valuer=dan,
                                 billing_address=bank.billing_address)
        unsigned = Bank.objects.create(name="NoSLA", billing_address="3 St", sla_signed=False)
        patch(client_for(dan), job, "instructions", {"bank": unsigned.pk})
        job.refresh_from_db()
        assert job.billing_address == ""

    def test_changing_bank_is_saved(self, bank, dan):
        job = Job.objects.create(bank=bank, property=Property.objects.create(), valuer=dan)
        adib = Bank.objects.create(name="ADIB", rules={"requires_service_charge": True})
        res = patch(client_for(dan), job, "instructions", {"bank": adib.pk}).json()
        assert res["values"]["bank"] == adib.pk


class TestExactAgeAndDates:
    def test_dates_and_datetimes_round_trip(self, job, dan):
        client = client_for(dan)
        assert patch(client, job, "location", {"built_date": "2019-03-01"}).status_code == 200
        received = {"date_time_request_received": "2026-08-26T09:10:00"}
        assert patch(client, job, "instructions", received).status_code == 200
        job.refresh_from_db()
        assert job.location.built_date == date(2019, 3, 1)
        assert job.date_time_request_received.year == 2026


# --- property integrity -----------------------------------------------------------


class TestPropertyOfIssuedJobs:
    def test_a_property_used_by_an_issued_job_cannot_be_edited(self, job):
        Job.objects.filter(pk=job.pk).update(is_locked=True)
        prop = Property.objects.get(pk=job.property_id)
        prop.unit_number = "CHANGED"
        with pytest.raises(JobLockedError):
            prop.save()

    def test_a_revision_gets_its_own_copy_of_the_property(self, job, dan):
        """Regression: revisions shared the issued job's Property row, so
        editing the draft's address would have rewritten the signed report's."""
        job.property.unit_number = "100"
        job.property.save()
        Job.objects.filter(pk=job.pk).update(is_locked=True, status=JobStatus.ISSUED)
        issued = Job.objects.get(pk=job.pk)

        revision = issued.create_revision(by=dan)
        assert revision.property_id != issued.property_id
        assert revision.property.unit_number == "100"

        res = patch(client_for(dan), revision, "address", {"unit_number": "200"})
        assert res.status_code == 200, res.json()
        issued.refresh_from_db()
        assert issued.property.unit_number == "100"
        assert revision.property.__class__.objects.get(pk=revision.property_id).unit_number == "200"


# --- the read side ------------------------------------------------------------------


class TestEndpoints:
    def test_job_detail_carries_every_tab_with_its_version(self, job, dan):
        patch(client_for(dan), job, "summary", {"makani_number": "1"})
        data = client_for(dan).get(f"/api/jobs/{job.pk}/").json()
        assert set(data["tabs"]) == {t["key"] for t in TABS}
        assert data["tabs"]["summary"]["version"] == 1
        assert data["tabs"]["summary"]["values"]["makani_number"] == "1"
        assert "bua_sqft" in data["tabs"]["summary"]["computed"]

    def test_get_one_tab(self, job, dan):
        res = client_for(dan).get(f"/api/jobs/{job.pk}/tabs/inspection/")
        assert res.status_code == 200 and res.json()["tab"] == "inspection"
        assert client_for(dan).get(f"/api/jobs/{job.pk}/tabs/nope/").status_code == 404

    def test_options_cover_every_options_key_and_the_users(self, job, dan, presets):
        data = client_for(dan).get("/api/options/").json()
        for tab in TABS:
            for f in tab["fields"]:
                if f["options_key"]:
                    assert f["options_key"] in data
        assert {o["value"] for o in data["property_status"]} == {"complete", "under_construction"}
        assert any(u["value"] == dan.pk for u in data["users"])
        assert data["bank"][0]["label"] == "Test Bank"

    def test_free_text_options_are_their_own_labels(self, job, dan, presets):
        data = client_for(dan).get("/api/options/").json()
        assert {"value": "Downtown Dubai", "label": "Downtown Dubai"}.items() <= data["community"][0].items()

    def test_library_options_carry_their_text(self, job, dan, presets):
        data = client_for(dan).get("/api/options/").json()
        item = next(o for o in data["special_assumption"] if o["label"] == "Granted")
        assert item["report_text"].startswith("We understand that the property is held under a granted title.")

    def test_seed_is_idempotent_and_keeps_admin_edits(self, presets):
        from apps.presets.models import PresetOption

        PresetOption.objects.filter(field_key="roof", value="metal_sheeting").update(label="Metal deck")
        call_command("seed_presets")
        assert PresetOption.objects.get(field_key="roof", value="metal_sheeting").label == "Metal deck"
        assert PresetOption.objects.filter(field_key="roof").count() == 2


class TestCsrf:
    def test_session_auth_requires_the_token_on_patch(self, job, dan):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(dan)
        body = {"base_version": 0, "values": {"makani_number": "1"}}
        assert client.patch(f"/api/jobs/{job.pk}/tabs/summary/", body, format="json").status_code == 403

        client.get("/api/csrf/")
        token = client.cookies["csrftoken"].value
        res = client.patch(f"/api/jobs/{job.pk}/tabs/summary/", body, format="json", HTTP_X_CSRFTOKEN=token)
        assert res.status_code == 200


class TestEditability:
    def test_job_detail_says_which_tabs_the_user_can_edit(self, bank):
        ines = make_user("ines")
        job = Job.objects.create(bank=bank, property=Property.objects.create(), inspected_by=ines)
        tabs_state = client_for(ines).get(f"/api/jobs/{job.pk}/").json()["tabs"]
        assert tabs_state["inspection"]["can_edit"] is True
        assert tabs_state["valuation"]["can_edit"] is False
        assert "doesn't allow editing" in tabs_state["valuation"]["read_only_reason"]
        assert tabs_state["photos"]["can_edit"] is True  # inspectors take the photographs
        assert tabs_state["documents"]["can_edit"] is True  # the title document is attached on the Check List

    def test_a_frozen_job_is_read_only_for_everyone(self, job, dan):
        Job.objects.filter(pk=job.pk).update(status=JobStatus.PEER_REVIEW)
        state = client_for(dan).get(f"/api/jobs/{job.pk}/").json()["tabs"]["valuation"]
        assert state["can_edit"] is False and "frozen" in state["read_only_reason"]

    def test_the_ui_and_the_endpoint_agree(self, bank):
        """What the detail says is editable must be what PATCH accepts, down
        to individual fields."""
        ines = make_user("ines")
        job = Job.objects.create(bank=bank, property=Property.objects.create(), inspected_by=ines)
        client = client_for(ines)
        shown = client.get(f"/api/jobs/{job.pk}/").json()["tabs"]
        for tab in TABS:
            if not tab["fields"]:
                continue
            read_only = set(shown[tab["key"]]["read_only_fields"])
            for field in (f for f in tab["fields"] if not f["calculated"]):
                res = patch(client, job, tab["key"], {field["key"]: None}, shown[tab["key"]]["version"])
                refused = res.status_code == 403
                expected = (not shown[tab["key"]]["can_edit"]) or field["key"] in read_only
                assert refused == expected, f"{tab['key']}.{field['key']}"

    def test_assignment_fields_are_read_only_for_an_inspector_but_not_a_valuer(self, bank):
        ines, val = make_user("ines"), make_user("val")
        job = Job.objects.create(bank=bank, property=Property.objects.create(), inspected_by=ines, valuer=val)
        as_inspector = client_for(ines).get(f"/api/jobs/{job.pk}/").json()["tabs"]["checklist"]
        as_valuer = client_for(val).get(f"/api/jobs/{job.pk}/").json()["tabs"]["checklist"]
        assert set(as_inspector["read_only_fields"]) == {"inspected_by", "valuer", "peer_reviewer"}
        assert as_valuer["read_only_fields"] == []


class TestReportFields:
    """Fields the report prints that the original spec left out (CLAUDE.md §4)."""

    def test_the_new_fields_save_and_come_back(self, job, dan):
        client = client_for(dan)
        res = patch(client, job, "location", {"developer": "Emaar"})
        assert res.status_code == 200
        assert patch(client, job, "summary", {"total_floors": 12}).status_code == 200
        assert patch(client, job, "instructions", {"contact_name": "R. Agent",
                                                   "contact_number": "+971 50 000 0000"}).status_code == 200
        job.refresh_from_db()
        assert (job.contact_name, job.contact_number) == ("R. Agent", "+971 50 000 0000")
        assert job.location.developer == "Emaar"
        assert job.summary.total_floors == 12

    @pytest.mark.parametrize("tab,key,value", [
        ("location", "built_about", "lots"),
        ("summary", "total_floors", 201),
        ("summary", "total_floors", -3),
    ])
    def test_implausible_values_are_refused(self, job, dan, tab, key, value):
        res = patch(client_for(dan), job, tab, {key: value})
        assert res.status_code == 400 and key in res.json()["errors"]

    def test_views_and_utilities_summaries_follow_what_the_inspector_recorded(self, job, dan, presets):
        patch(client_for(dan), job, "summary", {"property_category": "villa"})
        res = patch(client_for(dan), job, "inspection", {
            "front_views": "Marina", "rear_views": "Road",
            "electrical_services": "connected", "water": "connected", "sewerage": "connected",
        }).json()
        computed = res["computed"]["inspection"]
        assert computed["views_summary"] == "Front: Marina; Rear: Road"
        assert computed["utilities_summary"] == "Electricity, water and sewerage: connected."

    def test_rear_views_are_left_out_for_an_apartment(self, job, dan):
        patch(client_for(dan), job, "summary", {"property_category": "apartment"})
        res = patch(client_for(dan), job, "inspection", {"front_views": "Marina", "rear_views": "Road"}).json()
        assert res["computed"]["inspection"]["views_summary"] == "Front: Marina"

    def test_summaries_cannot_be_written_directly(self, job, dan):
        res = patch(client_for(dan), job, "inspection", {"views_summary": "x", "utilities_summary": "y"})
        assert set(res.json()["errors"]) == {"views_summary", "utilities_summary"}

    def test_a_revision_carries_the_new_fields_forward(self, job, dan):
        client = client_for(dan)
        patch(client, job, "location", {"developer": "Nakheel"})
        patch(client, job, "summary", {"total_floors": 9})
        patch(client, job, "inspection", {"occupancy": "tenanted", "rent_if_any": "90000"})
        Job.objects.filter(pk=job.pk).update(is_locked=True, status=JobStatus.ISSUED)
        revision = Job.objects.get(pk=job.pk).create_revision(by=dan)
        assert revision.inspection.rent_if_any == 90000
        assert revision.location.developer == "Nakheel"
        assert revision.summary.total_floors == 9


class TestCrmFeedbackSmallItems:
    """CRM feedback, 21 Oct 2026: the small items."""

    def test_remaining_economic_life_is_45_years_less_the_age(self, job, dan):
        from datetime import date

        client = client_for(dan)
        patch(client, job, "valuation", {"valuation_date": "2026-10-21"})
        res = patch(client, job, "location", {"built_date": "2015-03-01"}).json()
        assert res["computed"]["location"]["remaining_economic_life"] == 45 - 11
        job.location.built_date = None
        job.location.built_about = None
        assert job.location.remaining_economic_life is None
        job.location.built_date = date(1950, 1, 1)
        assert job.location.remaining_economic_life == 0  # never negative

    def test_repairs_start_with_the_standard_wording(self, job):
        from apps.jobs.constants import REPAIRS_DEFAULT

        assert job.inspection.repairs == REPAIRS_DEFAULT

    def test_sub_type_is_for_villas_and_townhouses(self, job, dan):
        client = client_for(dan)
        res = patch(client, job, "summary", {"property_category": "villa", "property_sub_type": "Corner"})
        assert res.status_code == 200, res.json()
        job.refresh_from_db()
        assert job.summary.property_sub_type == "Corner"

    def test_the_three_commentary_boxes_save(self, job, dan):
        res = patch(client_for(dan), job, "valuation", {"commentary_offices": "Grade A stock is limited."})
        assert res.status_code == 200


class TestExactAge:
    def age(self, job, dan, built, valued):
        client = client_for(dan)
        patch(client, job, "location", {"built_date": built})
        if valued:
            patch(client, job, "valuation", {"valuation_date": valued})
        job.refresh_from_db()
        return job.location.exact_age

    def test_is_measured_at_the_valuation_date_not_today(self, job, dan):
        """A report regenerated next year must still state the age it was
        valued at. (A valuation years ago is the case where 'today' and 'at
        valuation' give different answers.)"""
        assert self.age(job, dan, "2019-03-01", "2024-02-01") == "4 years, 11 months, 0 days"

    def test_the_day_before_the_anniversary_is_still_the_younger_age(self, job, dan):
        assert self.age(job, dan, "2019-09-01", "2026-08-31") == "6 years, 11 months, 30 days"

    def test_falls_back_to_today_until_there_is_a_valuation_date(self, job, dan):
        from apps.jobs.calculations import age_text

        assert self.age(job, dan, "2019-03-01", None) == age_text(date(2019, 3, 1), None)

    def test_a_built_year_gives_valuation_year_minus_built_year(self, job, dan):
        client = client_for(dan)
        patch(client, job, "location", {"built_about": 2015})
        patch(client, job, "valuation", {"valuation_date": "2026-01-02"})
        job.refresh_from_db()
        assert job.location.exact_age == "11 years"

    def test_the_built_date_gives_years_months_and_days(self, job, dan):
        """Regression: with a built year as well, only whole years showed."""
        client = client_for(dan)
        patch(client, job, "location", {"built_about": 2015, "built_date": "2015-12-31"})
        patch(client, job, "valuation", {"valuation_date": "2026-01-02"})
        job.refresh_from_db()
        assert job.location.exact_age == "10 years, 0 months, 2 days"


class TestAddressTab:
    def test_the_document_names_override_the_address_ones_when_given(self, job, dan):
        client = client_for(dan)
        res = patch(client, job, "address", {
            "building_name": "One Central", "community_name": "Trade Centre", "title_doc_plot_no": "100",
        }).json()
        assert res["computed"]["address"]["address_as_per_document"] == (
            "Plot No. 100, One Central, Trade Centre, Dubai, United Arab Emirates"
        )
        res = patch(client, job, "address", {"title_doc_community_name": "Trade Center 1"}, base_version=1).json()
        assert "One Central, Trade Center 1, Dubai" in res["computed"]["address"]["address_as_per_document"]
