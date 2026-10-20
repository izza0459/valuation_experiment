"""Sending an issued report to the bank from the Review & Send tab."""
import pytest
from rest_framework.test import APIClient

from apps.jobs.models import Job
from apps.reports.models import ReportDelivery
from apps.reports.tests.test_issue import approved, boss, clean_template, fake_engine, issue, make_user, storage

pytestmark = pytest.mark.django_db

# Fixtures from test_issue, used by name below.
__all__ = ["approved", "boss", "clean_template", "fake_engine", "storage"]


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def send(user, job, **body):
    return client_for(user).post(f"/api/jobs/{job.pk}/report/send/", body, format="json")


@pytest.fixture
def issued(approved, boss):
    approved.bank.contacts = [{"name": "Rana", "email": "rana@bank.example"}, {"name": "No email"}]
    approved.bank.save()
    assert issue(boss, approved).status_code in (200, 202)
    return Job.objects.get(pk=approved.pk)


class TestSendToBank:
    def test_the_admin_who_created_the_job_sends_it_to_a_bank_contact(self, issued, boss, mailoutbox):
        res = send(boss, issued, email="rana@bank.example", message="Please find attached.")
        assert res.status_code == 201, res.json()
        delivery = ReportDelivery.objects.get()
        assert (delivery.recipient_name, delivery.status) == ("Rana", "sent")
        assert delivery.sent_at is not None
        assert delivery.report_version.issued_at is not None
        (mail,) = mailoutbox
        assert mail.to == ["rana@bank.example"]
        assert [a[0] for a in mail.attachments] == [f"{issued.file_stem}.pdf"]

    def test_a_failed_send_is_logged_not_raised(self, issued, boss, mailoutbox, monkeypatch):
        def boom(self, fail_silently=False):
            raise OSError("smtp down")

        monkeypatch.setattr("django.core.mail.EmailMessage.send", boom)
        res = send(boss, issued, email="rana@bank.example")
        assert res.status_code == 201
        delivery = ReportDelivery.objects.get()
        assert (delivery.status, delivery.error) == ("failed", "smtp down")

    def test_a_demo_sends_it_to_our_own_inbox_not_the_bank(self, issued, boss, mailoutbox, settings):
        settings.REPORT_EMAIL_REDIRECT_TO = ["demo@example.test"]
        assert send(boss, issued, email="rana@bank.example").status_code == 201
        (mail,) = mailoutbox
        assert mail.to == ["demo@example.test"]
        assert mail.subject.startswith("[DEMO for rana@bank.example]")
        assert "rana@bank.example" in mail.body
        # The log still says which contact was picked.
        assert ReportDelivery.objects.get().recipient_email == "rana@bank.example"

    def test_it_can_go_through_an_email_api_instead_of_smtp(self, issued, boss, settings, monkeypatch):
        """Render's free plan blocks SMTP; Brevo/Resend/SendGrid are called over HTTPS."""
        settings.EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
        settings.ANYMAIL = {"BREVO_API_KEY": "test-key"}
        calls = []

        class Reply:
            status_code = 201
            text = '{"messageId": "<1@brevo>"}'
            content = text.encode()

            def json(self):
                return {"messageId": "<1@brevo>"}

        def fake_request(self, method, url, **kwargs):
            calls.append((url, kwargs))
            return Reply()

        monkeypatch.setattr("requests.Session.request", fake_request)
        assert send(boss, issued, email="rana@bank.example").status_code == 201
        assert ReportDelivery.objects.get().status == "sent"
        (url, kwargs) = calls[0]
        assert "api.brevo.com" in url and kwargs["headers"]["api-key"] == "test-key"
        assert f'"name": "{issued.file_stem}.pdf"' in kwargs["data"]

    def test_a_lost_pdf_is_rebuilt_from_what_was_signed(self, issued, boss, mailoutbox, monkeypatch):
        """Free hosting wipes stored files on every deploy."""
        from django.core.files.storage import default_storage

        from apps.reports import generate
        from apps.reports.models import ReportVersion

        version = ReportVersion.objects.get(job=issued, issued_at__isnull=False)
        default_storage.delete(version.pdf_s3_key)
        rendered = []
        monkeypatch.setattr(generate, "render_pdf", lambda html: rendered.append(html) or b"%PDF-rebuilt")
        assert send(boss, issued, email="rana@bank.example").status_code == 201
        assert ReportDelivery.objects.get().status == "sent"
        (mail,) = mailoutbox
        assert mail.attachments[0][1] == b"%PDF-rebuilt"
        # From the stored snapshot, not the live job.
        assert version.input_snapshot["meta"]["ref_no"] in rendered[0]
        # And the download works again too, without rebuilding twice.
        res = client_for(boss).get(f"/api/jobs/{issued.pk}/report/{version.pk}/pdf/")
        assert res.status_code == 200 and b"".join(res.streaming_content) == b"%PDF-rebuilt"
        assert len(rendered) == 1

    def test_the_job_offers_the_bank_contacts_and_the_log(self, issued, boss):
        send(boss, issued, email="rana@bank.example")
        data = client_for(boss).get(f"/api/jobs/{issued.pk}/").json()
        assert data["can_send_report"] is True
        assert data["bank_contacts"] == [{"name": "Rana", "email": "rana@bank.example"}]
        assert data["deliveries"][0]["recipient_email"] == "rana@bank.example"

    def test_nobody_else_can_send_it(self, issued):
        dan = issued.valuer
        assert send(dan, issued, email="rana@bank.example").status_code == 403
        assert client_for(dan).get(f"/api/jobs/{issued.pk}/").json()["can_send_report"] is False

    def test_it_must_be_issued_first(self, approved, boss):
        res = send(boss, approved, email="rana@bank.example")
        assert res.status_code == 400 and "issued" in res.json()["detail"]

    def test_the_address_must_be_an_email(self, issued, boss):
        res = send(boss, issued, email="not-an-email")
        assert res.status_code == 400 and "email" in res.json()["errors"]

    def test_a_platform_admin_can_send_too(self, issued):
        other_admin = make_user("other", roles=["admin"], licence=None)
        assert send(other_admin, issued, email="ops@bank.example").status_code == 201
