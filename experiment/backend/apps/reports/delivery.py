"""Sending an issued report to the bank from the app (Review & Send tab).

For now a request is recorded and shown as queued; the email itself (AWS SES,
CLAUDE.md §8) is wired in later and fills in `sent_at`, or `error` if it fails.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.accounts.permissions import is_platform_admin
from apps.jobs.tabs import TabError

from .models import ReportDelivery


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
        for c in (job.bank.contacts or [])
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
    }
