"""Bank email templates: the bank's own, else the default."""
import pytest

from apps.accounts.models import Role
from apps.banks.models import Bank
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, make_user
from apps.reports.emails import draft
from apps.reports.models import EmailTemplate

pytestmark = pytest.mark.django_db

__all__ = ["bank", "dan", "job"]


def test_the_default_template_is_used_with_merge_fields(job):
    job.bank_reference_no = "B-77"
    out = draft(job, "Sara")
    assert out["template"] == "Standard report email"
    assert "B-77" in out["subject"] and out["body"].startswith("Dear Sara,")


def test_a_banks_own_template_wins(job):
    EmailTemplate.objects.create(name="ENBD", bank=job.bank, subject="Report {our_ref}",
                                 body="Hello {recipient_name} {unknown}")
    out = draft(job, "Sara")
    assert out["subject"] == f"Report {job.bayut_internal_reference_no}"
    assert out["body"] == "Hello Sara {unknown}"  # unknown fields are left as typed


def test_admins_manage_them_and_one_default_stays(job):
    api = client_for(make_user("root", roles=[Role.ADMIN]))
    listed = api.get("/api/admin/email-templates/").json()
    assert "our_ref" in listed["merge_fields"] and len(listed["results"]) == 1
    res = api.post("/api/admin/email-templates/", {"name": "New", "subject": "S", "body": "B", "is_default": True},
                   format="json")
    assert res.status_code == 201
    assert EmailTemplate.objects.filter(is_default=True).count() == 1
    other = Bank.objects.create(name="Other")
    res = api.post("/api/admin/email-templates/",
                   {"name": "X", "bank": other.pk, "subject": "S", "body": "B", "is_default": True}, format="json")
    assert res.status_code == 400
    assert client_for(job.valuer).get("/api/admin/email-templates/").status_code == 403
