"""Creating a job from the New instruction screen (design brief S2)."""
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.banks.models import Bank
from apps.jobs.models import Job, Property
from apps.jobs.workflow import JobStatus

pytestmark = pytest.mark.django_db


def make_user(name, roles=None, **kwargs):
    return User.objects.create(username=name, email=f"{name}@example.com", first_name=name.title(),
                               roles=roles or [], **kwargs)


@pytest.fixture(autouse=True)
def presets():
    call_command("seed_presets")


@pytest.fixture
def admin():
    return make_user("boss", roles=[Role.ADMIN])


@pytest.fixture
def bank():
    return Bank.objects.create(name="Test Bank", billing_address="1 Bank St", sla_signed=True)


def create(user, values):
    client = APIClient()
    client.force_authenticate(user)
    return client.post("/api/jobs/", {"values": values}, format="json")


class TestCreate:
    def test_ops_can_fill_in_the_whole_form_then_only_setup(self, bank):
        """Regression: the form's team and category fields sit on Inspection
        tabs, which ops can't edit, so creating a job failed for ops."""
        ops, val = make_user("olga", roles=[Role.OPS]), make_user("val", roles=[Role.VALUER])
        res = create(ops, {"bank": bank.pk, "applicant_name": "A. Applicant", "property_category": "apartment",
                           "valuer": val.pk, "inspected_by": val.pk})
        assert res.status_code == 201, res.json()
        job = Job.objects.get(pk=res.json()["id"])
        assert (job.valuer, job.summary.property_category) == (val, "apartment")
        client = APIClient()
        client.force_authenticate(ops)
        tabs = client.get(f"/api/jobs/{job.pk}/").json()["tabs"]
        assert tabs["instructions"]["can_edit"] and tabs["address"]["can_edit"]
        assert not tabs["summary"]["can_edit"] and not tabs["checklist"]["can_edit"]

    def test_creates_a_job_with_its_property_and_tab_rows(self, admin, bank):
        res = create(admin, {"bank": bank.pk, "bank_reference_no": "DIB-1", "unit_number": "312",
                             "building_name": "Rukan Residences", "applicant_name": "A. Applicant"})
        assert res.status_code == 201, res.json()
        job = Job.objects.get(pk=res.json()["id"])
        assert job.bayut_internal_reference_no == res.json()["bayut_internal_reference_no"]
        assert job.status == JobStatus.SETUP  # entering the instruction starts setup
        assert (job.bank_reference_no, job.property.unit_number, job.property.applicant_name) == (
            "DIB-1", "312", "A. Applicant")
        assert job.summary and job.inspection and job.location and job.valuation and job.checklist

    def test_the_creator_becomes_the_jobs_admin(self, admin, bank):
        job = Job.objects.get(pk=create(admin, {"bank": bank.pk}).json()["id"])
        assert job.admin_user == admin

    def test_assigns_the_team(self, admin, bank):
        val, ines, pat = (make_user(n) for n in ("val", "ines", "pat"))
        res = create(admin, {"bank": bank.pk, "valuer": val.pk, "registered_valuer": val.pk,
                             "inspected_by": ines.pk, "peer_reviewer": pat.pk})
        job = Job.objects.get(pk=res.json()["id"])
        assert (job.valuer, job.registered_valuer, job.inspected_by, job.peer_reviewer) == (val, val, ines, pat)
        # The reviewer's sign-off is the second signature; nobody is asked for it separately.
        assert "counter_signatory" in create(admin, {"bank": bank.pk, "counter_signatory": pat.pk}).json()["errors"]

    def test_property_category_goes_to_the_summary(self, admin, bank):
        job = Job.objects.get(pk=create(admin, {"bank": bank.pk, "property_category": "villa"}).json()["id"])
        assert job.summary.property_category == "villa"

    def test_billing_address_comes_from_a_bank_with_a_signed_sla(self, admin, bank):
        job = Job.objects.get(pk=create(admin, {"bank": bank.pk}).json()["id"])
        assert job.billing_address == "1 Bank St"

    def test_not_from_a_bank_without_one(self, admin):
        unsigned = Bank.objects.create(name="NoSLA", billing_address="2 St", sla_signed=False)
        job = Job.objects.get(pk=create(admin, {"bank": unsigned.pk}).json()["id"])
        assert job.billing_address == ""

    def test_references_are_sequential(self, admin, bank):
        first = create(admin, {"bank": bank.pk}).json()["bayut_internal_reference_no"]
        second = create(admin, {"bank": bank.pk}).json()["bayut_internal_reference_no"]
        assert int(second[-5:]) == int(first[-5:]) + 1

    def test_the_new_jobs_changes_are_audited_to_the_creator(self, admin, bank):
        job = Job.objects.get(pk=create(admin, {"bank": bank.pk, "unit_number": "9"}).json()["id"])
        entry = AuditLog.objects.get(job=job, model_name="Property", field_name="unit_number")
        assert entry.changed_by == admin


class TestRefusals:
    def test_only_an_admin_may_create(self, bank):
        valuer = make_user("val", roles=[Role.VALUER])
        assert create(valuer, {"bank": bank.pk}).status_code == 403

    def test_anonymous_is_refused(self, bank):
        res = APIClient().post("/api/jobs/", {"values": {"bank": bank.pk}}, format="json")
        assert res.status_code in (401, 403)

    @pytest.mark.parametrize("values,expected", [
        ({}, "Choose the client bank."),
        ({"bank": None}, "Choose the client bank."),
        ({"bank": 9999}, "No such bank."),
        ({"bank": "1"}, "No such bank."),
    ])
    def test_a_bank_is_required(self, admin, values, expected):
        res = create(admin, values)
        assert res.status_code == 400 and res.json()["errors"]["bank"] == expected

    def test_an_inactive_bank_is_refused(self, admin):
        gone = Bank.objects.create(name="Gone", active=False)
        assert create(admin, {"bank": gone.pk}).json()["errors"]["bank"] == "No such bank."

    def test_only_intake_fields_may_be_set(self, admin, bank):
        res = create(admin, {"bank": bank.pk, "market_value": "1", "status": "issued", "is_locked": True})
        assert res.status_code == 400
        assert set(res.json()["errors"]) == {"market_value", "status", "is_locked"}

    def test_errors_from_every_tab_are_reported_together(self, admin, bank):
        res = create(admin, {"bank": bank.pk, "latitude": "999", "property_category": "spaceship",
                             "valuer": 9999})
        assert res.status_code == 400
        assert set(res.json()["errors"]) == {"latitude", "property_category", "valuer"}

    def test_a_rejected_value_leaves_nothing_behind(self, admin, bank):
        jobs, properties = Job.all_objects.count(), Property.all_objects.count()
        assert create(admin, {"bank": bank.pk, "unit_number": "5", "latitude": "999"}).status_code == 400
        assert (Job.all_objects.count(), Property.all_objects.count()) == (jobs, properties)

    def test_values_must_be_an_object(self, admin):
        client = APIClient()
        client.force_authenticate(admin)
        assert client.post("/api/jobs/", {"values": ["x"]}, format="json").status_code == 400
        assert client.post("/api/jobs/", {}, format="json").status_code == 400
