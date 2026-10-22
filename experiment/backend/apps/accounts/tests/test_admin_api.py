"""The in-app Admin screens' APIs (design brief S8): users, banks, presets,
text library, templates. Admin-only, and never able to delete or escalate."""
import datetime

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Role, User, ValuerProfile
from apps.banks.models import Bank
from apps.jobs.models import Job, Property
from apps.presets.models import PresetOption, TextLibraryItem
from apps.reports.models import ReportTemplate
from apps.reports.render import ensure_default_template

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-9"


def make_user(name, roles=None, **kwargs):
    return User.objects.create(username=f"{name}@example.com", email=f"{name}@example.com",
                               first_name=name.title(), roles=roles or [], **kwargs)


def as_user(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin():
    return make_user("boss", roles=[Role.ADMIN])


@pytest.fixture
def client(admin):
    return as_user(admin)


ENDPOINTS = ["users", "banks", "presets", "library", "templates", "preset-keys"]


class TestAccess:
    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    def test_a_non_admin_is_refused(self, endpoint):
        valuer = make_user("val", roles=[Role.VALUER])
        assert as_user(valuer).get(f"/api/admin/{endpoint}/").status_code == 403

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    def test_anonymous_is_refused(self, endpoint):
        assert APIClient().get(f"/api/admin/{endpoint}/").status_code in (401, 403)

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    def test_an_admin_can_read(self, client, endpoint):
        assert client.get(f"/api/admin/{endpoint}/").status_code == 200

    @pytest.mark.parametrize("endpoint", ["users", "banks", "presets"])
    def test_nothing_can_be_deleted(self, client, endpoint):
        """Referenced by jobs, reports or the audit trail. (Library entries
        can be: jobs keep their own copy of the text.)"""
        assert client.delete(f"/api/admin/{endpoint}/1/").status_code in (404, 405)


class TestUsers:
    def create(self, client, **extra):
        body = {"email": "New.User@Example.com", "first_name": "New", "last_name": "User",
                "roles": ["valuer"], "password": PASSWORD, **extra}
        return client.post("/api/admin/users/", body, format="json")

    def test_creates_a_user_who_can_then_sign_in(self, client):
        res = self.create(client)
        assert res.status_code == 201, res.json()
        assert res.json()["email"] == "new.user@example.com"  # normalised
        browser = APIClient(enforce_csrf_checks=True)
        browser.get("/api/csrf/")
        login = browser.post("/api/auth/login/", {"email": "new.user@example.com", "password": PASSWORD},
                             format="json", HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value)
        assert login.status_code == 200 and login.json()["user"]["roles"] == ["valuer"]

    def test_the_password_is_never_returned_or_stored_in_clear(self, client):
        res = self.create(client)
        assert "password" not in res.json()
        user = User.objects.get(email="new.user@example.com")
        assert user.check_password(PASSWORD) and user.password != PASSWORD

    def test_a_weak_password_is_refused(self, client):
        res = self.create(client, password="12345678")
        assert res.status_code == 400 and "password" in res.json()

    def test_no_password_means_the_account_cannot_sign_in_yet(self, client):
        res = self.create(client, password="")
        assert res.status_code == 201
        assert not User.objects.get(email="new.user@example.com").has_usable_password()

    def test_emails_are_unique_ignoring_case(self, client):
        make_user("dup")
        res = self.create(client, email="DUP@example.com")
        assert res.status_code == 400 and "email" in res.json()

    def test_only_real_roles(self, client):
        assert "roles" in self.create(client, roles=["valuer", "emperor"]).json()

    def test_staff_and_superuser_cannot_be_set_through_the_api(self, client):
        """Otherwise any admin could mint a superuser."""
        res = self.create(client, is_staff=True, is_superuser=True)
        user = User.objects.get(email="new.user@example.com")
        assert res.status_code == 201 and not user.is_staff and not user.is_superuser
        patched = client.patch(f"/api/admin/users/{user.pk}/", {"is_superuser": True}, format="json")
        user.refresh_from_db()
        assert patched.status_code == 200 and not user.is_superuser

    def test_a_valuer_profile_is_saved_with_the_user(self, client):
        res = self.create(client, valuer_profile={
            "rera_registration_no": "RERA-1", "rics_membership_no": "RICS-1", "qualifications": "MRICS",
            "title": "Senior Valuer", "rera_licence_expiry": "2099-01-01"})
        profile = ValuerProfile.objects.get(user__email="new.user@example.com")
        assert profile.rera_registration_no == "RERA-1"
        assert res.json()["licence"]["state"] == "valid"

    def test_the_profile_can_be_edited_later(self, client):
        user = make_user("val")
        ValuerProfile.objects.create(user=user, rera_registration_no="OLD")
        client.patch(f"/api/admin/users/{user.pk}/", {"valuer_profile": {"rera_registration_no": "NEW"}}, format="json")
        assert ValuerProfile.objects.get(user=user).rera_registration_no == "NEW"

    @pytest.mark.parametrize("days,state", [(-1, "expired"), (30, "expiring"), (400, "valid")])
    def test_licence_state_warns_before_expiry(self, client, days, state):
        user = make_user("val")
        ValuerProfile.objects.create(user=user, rera_licence_expiry=datetime.date.today() + datetime.timedelta(days))
        row = next(u for u in client.get("/api/admin/users/").json() if u["id"] == user.pk)
        assert row["licence"]["state"] == state

    def test_a_user_with_no_profile_is_marked_missing(self, client):
        user = make_user("bare")
        row = next(u for u in client.get("/api/admin/users/").json() if u["id"] == user.pk)
        assert row["licence"] == {"state": "missing", "days_left": None}

    def test_a_password_can_be_reset(self, client):
        user = make_user("val")
        client.patch(f"/api/admin/users/{user.pk}/", {"password": "another-long-pass-7"}, format="json")
        user.refresh_from_db()
        assert user.check_password("another-long-pass-7")

    def test_a_user_can_be_deactivated(self, client):
        user = make_user("val")
        assert client.patch(f"/api/admin/users/{user.pk}/", {"is_active": False}, format="json").status_code == 200
        user.refresh_from_db()
        assert not user.is_active

    def test_you_cannot_deactivate_or_demote_yourself(self, client, admin):
        assert client.patch(f"/api/admin/users/{admin.pk}/", {"is_active": False}, format="json").status_code == 400
        assert client.patch(f"/api/admin/users/{admin.pk}/", {"roles": ["valuer"]}, format="json").status_code == 400
        assert client.patch(f"/api/admin/users/{admin.pk}/", {"roles": ["admin", "valuer"]},
                            format="json").status_code == 200

    def test_search_by_name_or_email(self, client):
        make_user("alpha")
        make_user("beta")
        found = client.get("/api/admin/users/?q=alph").json()
        assert [u["email"] for u in found] == ["alpha@example.com"]


class TestBanks:
    def test_creates_a_bank_with_rules(self, client):
        res = client.post("/api/admin/banks/", {
            "name": "ADIB", "billing_address": "Abu Dhabi", "po_box": "313", "sla_signed": True,
            "contacts": [{"name": "A", "email": "a@adib.ae", "phone": "1"}],
            "rules": {"requires_service_charge": True, "forced_sale_discount_pct": 15},
        }, format="json")
        assert res.status_code == 201, res.json()
        assert Bank.objects.get(name="ADIB").rules["requires_service_charge"] is True

    def test_unknown_rules_are_refused_because_they_would_silently_do_nothing(self, client):
        res = client.post("/api/admin/banks/", {"name": "X", "rules": {"requires_service_chrage": True}}, format="json")
        assert res.status_code == 400 and "Unknown rule" in str(res.json()["rules"])

    @pytest.mark.parametrize("rules", [
        {"requires_exact_age": "yes"},
        {"forced_sale_discount_pct": 150},
        {"forced_sale_discount_pct": -1},
        {"forced_sale_discount_pct": True},
        ["not", "an", "object"],
    ])
    def test_rule_values_are_checked(self, client, rules):
        assert client.post("/api/admin/banks/", {"name": "X", "rules": rules}, format="json").status_code == 400

    def test_contacts_are_checked(self, client):
        res = client.post("/api/admin/banks/", {"name": "X", "contacts": [{"name": "A", "fax": "1"}]}, format="json")
        assert res.status_code == 400

    def test_names_are_unique_ignoring_case(self, client):
        Bank.objects.create(name="ADIB")
        assert client.post("/api/admin/banks/", {"name": "adib"}, format="json").status_code == 400

    def test_a_bank_can_be_edited_and_deactivated(self, client):
        bank = Bank.objects.create(name="Old")
        client.patch(f"/api/admin/banks/{bank.pk}/", {"name": "New", "active": False}, format="json")
        bank.refresh_from_db()
        assert (bank.name, bank.active) == ("New", False)

    def test_a_rule_change_reaches_jobs_already_in_progress(self, client):
        """Rules are read live, which is why changing one is audited."""
        bank = Bank.objects.create(name="B")
        job = Job.objects.create(bank=bank, property=Property.objects.create())
        client.patch(f"/api/admin/banks/{bank.pk}/", {"rules": {"requires_service_charge": True}}, format="json")
        job.refresh_from_db()
        assert job.bank.rules["requires_service_charge"] is True

    def test_changes_are_audited(self, client, admin):
        from apps.audit.models import AuditLog

        bank = Bank.objects.create(name="B")
        client.patch(f"/api/admin/banks/{bank.pk}/", {"po_box": "99"}, format="json")
        entry = AuditLog.objects.get(model_name="Bank", field_name="po_box")
        assert entry.new_value == "99"


class TestPresets:
    @pytest.fixture(autouse=True)
    def seeded(self):
        call_command("seed_presets")

    def test_lists_only_the_dropdowns_made_of_presets(self, client):
        keys = {k["key"] for k in client.get("/api/admin/preset-keys/").json()}
        assert {"roof", "interest_valued", "property_status"} <= keys
        assert not keys & {"bank", "report_template", "assumption", "special_assumption", "commentary"}

    def test_the_counts_follow_active_options(self, client):
        row = next(k for k in client.get("/api/admin/preset-keys/").json() if k["key"] == "roof")
        assert row["count"] == 2

    def test_adds_an_option_and_derives_its_stable_value(self, client):
        res = client.post("/api/admin/presets/", {"field_key": "roof", "label": "Clay Tiles"}, format="json")
        assert res.status_code == 201, res.json()
        assert res.json()["value"] == "clay_tiles"

    def test_the_value_cannot_be_chosen_or_changed(self, client):
        res = client.post("/api/admin/presets/", {"field_key": "roof", "label": "Slate", "value": "hacked"},
                          format="json")
        assert res.json()["value"] == "slate"
        client.patch(f"/api/admin/presets/{res.json()['id']}/", {"value": "other", "label": "Slate Roof"},
                     format="json")
        option = PresetOption.objects.get(pk=res.json()["id"])
        assert (option.value, option.label) == ("slate", "Slate Roof")

    def test_only_real_dropdowns_can_be_added_to(self, client):
        res = client.post("/api/admin/presets/", {"field_key": "made_up", "label": "X"}, format="json")
        assert res.status_code == 400 and "field_key" in res.json()

    def test_duplicates_are_refused(self, client):
        res = client.post("/api/admin/presets/", {"field_key": "roof", "label": "Metal Sheeting"}, format="json")
        assert res.status_code == 400 and "label" in res.json()

    def test_an_option_cannot_move_to_another_dropdown(self, client):
        option = PresetOption.objects.get(field_key="roof", value="metal_sheeting")
        res = client.patch(f"/api/admin/presets/{option.pk}/", {"field_key": "structure"}, format="json")
        assert res.status_code == 400

    def test_filters_by_dropdown(self, client):
        rows = client.get("/api/admin/presets/?field_key=roof").json()
        assert {r["field_key"] for r in rows} == {"roof"}

    def test_deactivating_removes_it_from_the_form_but_keeps_the_label_for_old_jobs(self, client):
        option = PresetOption.objects.get(field_key="roof", value="metal_sheeting")
        client.patch(f"/api/admin/presets/{option.pk}/", {"active": False}, format="json")
        options = as_user(make_user("val")).get("/api/options/").json()["roof"]
        assert "metal_sheeting" not in [o["value"] for o in options]
        assert PresetOption.objects.get(pk=option.pk).label == "Metal Sheeting"


class TestLibrary:
    def test_adds_edits_and_filters(self, client):
        # The approved wording loads with the migrations; this adds one more.
        assumptions = TextLibraryItem.objects.filter(category="assumption").count()
        specials = TextLibraryItem.objects.filter(category="special_assumption").count()
        res = client.post("/api/admin/library/", {"category": "assumption", "title": " Vacant possession ",
                                                  "body": "Assumed vacant."}, format="json")
        assert res.status_code == 201 and res.json()["title"] == "Vacant possession"
        client.patch(f"/api/admin/library/{res.json()['id']}/", {"body": "Changed."}, format="json")
        assert TextLibraryItem.objects.get(pk=res.json()["id"]).body == "Changed."
        assert len(client.get("/api/admin/library/?category=assumption").json()) == assumptions + 1
        assert len(client.get("/api/admin/library/?category=special_assumption").json()) == specials

    def test_the_category_must_be_real(self, client):
        res = client.post("/api/admin/library/", {"category": "nonsense", "title": "x", "body": "y"}, format="json")
        assert res.status_code == 400

    def test_a_new_entry_shows_up_in_the_form_options(self, client):
        client.post("/api/admin/library/", {"category": "assumption", "title": "Vacant", "body": "Assumed vacant."},
                    format="json")
        options = as_user(make_user("val")).get("/api/options/").json()["assumption"]
        assert any(o["label"] == "Vacant" and o["report_text"] == "Assumed vacant." for o in options)

    def test_a_deleted_entry_is_gone_from_the_library_and_the_form(self, client):
        from apps.presets.dictionary import sync

        item = TextLibraryItem.objects.filter(category="assumption", active=True).exclude(title="Custom").first()
        assert client.delete(f"/api/admin/library/{item.pk}/").status_code == 204
        item.refresh_from_db()
        assert item.deleted and not item.active  # kept as a row: soft delete
        assert all(i["id"] != item.pk for i in client.get("/api/admin/library/?category=assumption").json())
        options = as_user(make_user("val")).get("/api/options/").json()["assumption"]
        assert all(o["label"] != item.title for o in options)
        # A later dictionary sync doesn't bring it back.
        sync(PresetOption, TextLibraryItem)
        item.refresh_from_db()
        assert item.deleted and not item.active
        assert TextLibraryItem.objects.filter(category="assumption", title=item.title).count() == 1


class TestTemplates:
    def test_lists_versions_with_how_many_reports_used_them(self, client):
        template = ensure_default_template()
        row = next(t for t in client.get("/api/admin/templates/").json() if t["id"] == template.pk)
        assert row["name"] == template.name and row["reports_count"] == 0

    def test_only_the_active_flag_can_be_changed(self, client):
        template = ReportTemplate.objects.create(name="T", version="v1", html="<p>original</p>")
        client.patch(f"/api/admin/templates/{template.pk}/", {"active": False, "html": "<p>hacked</p>", "name": "X"},
                     format="json")
        template.refresh_from_db()
        assert template.active is False and template.html == "<p>original</p>" and template.name == "T"
