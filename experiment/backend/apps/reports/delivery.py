"""Sending an issued report to the bank from the app (Review & Send tab).

A request is recorded as queued, then `send_delivery` emails the issued PDF
(SMTP, configured through the EMAIL_* settings) and fills in `sent_at`, or
`error` if it fails.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.utils import timezone

from apps.accounts.permissions import is_platform_admin
from apps.jobs.tabs import TabError

from .models import ReportDelivery

logger = logging.getLogger(__name__)


class DeliveryError(TabError):
    status = 400
    code = "validation"


class DeliveryNotAllowed(TabError):
    status = 403
    code = "forbidden"


def may_send(user, job) -> bool:
    """The admin who took the instruction sends the report; platform admins
    can too while the team is small."""
    return bool(user and (user.pk == job.admin_user_id or is_platform_admin(user)))


def bank_contacts(job) -> list[dict]:
    """The bank master's contacts that have an email address."""
    return [
        {"name": (c.get("name") or "").strip(), "email": c["email"].strip()}
        for c in ((job.bank.contacts if job.bank_id else None) or [])
        if isinstance(c, dict) and (c.get("email") or "").strip()
    ]


def request_delivery(job, user, email, name="", message="") -> ReportDelivery:
    if not may_send(user, job):
        raise DeliveryNotAllowed("Only the admin who created this job can send the report.")
    version = job.report_versions.filter(issued_at__isnull=False).order_by("-issued_at").first()
    if not job.is_locked or version is None:
        raise DeliveryError("The report can be sent once it has been issued.")

    email = (email or "").strip() if isinstance(email, str) else ""
    try:
        validate_email(email)
    except ValidationError as exc:
        raise DeliveryError("Some values are invalid.", errors={"email": "Enter a valid email address."}) from exc

    name = (name or "").strip() if isinstance(name, str) else ""
    if not name:
        name = next((c["name"] for c in bank_contacts(job) if c["email"].lower() == email.lower()), "")
    return ReportDelivery.objects.create(
        job=job,
        report_version=version,
        recipient_name=name[:255],
        recipient_email=email,
        message=message.strip() if isinstance(message, str) else "",
        requested_by=user,
    )


def describe_delivery(delivery: ReportDelivery) -> dict:
    return {
        "id": delivery.id,
        "recipient_name": delivery.recipient_name,
        "recipient_email": delivery.recipient_email,
        "message": delivery.message,
        "status": delivery.status,
        "status_label": delivery.get_status_display(),
        "requested_by": str(delivery.requested_by) if delivery.requested_by else "",
        "requested_at": delivery.requested_at,
        "sent_at": delivery.sent_at,
        "error": delivery.error,
    }


def send_delivery(delivery_id: int) -> ReportDelivery:
    """Emails the delivery's report PDF and records the outcome on the log."""
    delivery = ReportDelivery.objects.select_related("job", "report_version", "requested_by").get(pk=delivery_id)
    if delivery.status == ReportDelivery.SENT:
        return delivery
    job, version = delivery.job, delivery.report_version
    firm = settings.REPORT_FIRM_NAME
    ref = job.bayut_internal_reference_no
    greeting = f"Dear {delivery.recipient_name}," if delivery.recipient_name else "Dear Sir/Madam,"
    note = f"{delivery.message}\n\n" if delivery.message else ""
    their_ref = f" (your ref. {job.bank_reference_no})" if job.bank_reference_no else ""
    body = (
        f"{greeting}\n\n{note}Please find attached our valuation report, ref. {ref}{their_ref}."
        f"\n\nKind regards,\n{firm}\n"
    )
    try:
        email = EmailMessage(
            subject=f"Valuation report {ref}" + (f" / {job.bank_reference_no}" if job.bank_reference_no else ""),
            body=body,
            to=[delivery.recipient_email],
            bcc=settings.REPORT_EMAIL_BCC,
            reply_to=[delivery.requested_by.email] if delivery.requested_by and delivery.requested_by.email else None,
        )
        with default_storage.open(version.pdf_s3_key) as pdf:
            email.attach(f"{job.file_stem}.pdf", pdf.read(), "application/pdf")
        email.send(fail_silently=False)
    except Exception as exc:
        logger.exception("Sending report %s to %s failed", ref, delivery.recipient_email)
        delivery.status, delivery.error = ReportDelivery.FAILED, str(exc)[:1000]
        delivery.save(update_fields=["status", "error"])
        return delivery
    delivery.status, delivery.error, delivery.sent_at = ReportDelivery.SENT, "", timezone.now()
    delivery.save(update_fields=["status", "error", "sent_at"])
    return delivery
