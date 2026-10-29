"""The email that carries an issued report to the bank, from the admin's email
templates: the bank's own (active) template, otherwise the default one."""

from __future__ import annotations

import re

from django.conf import settings

from .models import EmailTemplate

MERGE_FIELDS = {
    "greeting": "Dear <name>, or Dear Sir/Madam",
    "recipient_name": "Who it's going to",
    "our_ref": "Bayut reference",
    "bank_ref": "The bank's reference",
    "bank": "Bank / client",
    "property": "Property address",
    "applicant": "Applicant name",
    "valuation_date": "Valuation date",
    "market_value": "Market value (AED)",
    "firm": "Our firm's name",
    "sender": "Who is sending it",
}

FALLBACK_SUBJECT = "Valuation report {our_ref} / {bank_ref}"
FALLBACK_BODY = (
    "{greeting}\n\nPlease find attached our valuation report, ref. {our_ref} (your ref. {bank_ref}), "
    "for {property}.\n\nKind regards,\n{sender}\n{firm}\n"
)


def template_for(job) -> EmailTemplate | None:
    active = EmailTemplate.objects.filter(active=True)
    return (active.filter(bank_id=job.bank_id).first() if job.bank_id else None) or active.filter(
        is_default=True, bank__isnull=True).first()


def merge_values(job, recipient_name="", sender=None) -> dict:
    valuation = getattr(job, "valuation", None)
    value = getattr(valuation, "market_value", None)
    date = getattr(valuation, "valuation_date", None)
    return {
        "greeting": f"Dear {recipient_name}," if recipient_name else "Dear Sir/Madam,",
        "recipient_name": recipient_name,
        "our_ref": job.bayut_internal_reference_no,
        "bank_ref": job.bank_reference_no or "-",
        "bank": job.organisation_name or "",
        "property": str(job.property),
        "applicant": job.property.applicant_name or "",
        "valuation_date": f"{date:%d %B %Y}" if date else "",
        "market_value": f"AED {value:,.0f}" if value is not None else "",
        "firm": settings.REPORT_FIRM_NAME,
        "sender": str(sender) if sender else "",
    }


def fill(text: str, values: dict) -> str:
    """Replaces {field}; anything else in braces is left as typed."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), text)


def draft(job, recipient_name="", sender=None) -> dict:
    template = template_for(job)
    values = merge_values(job, recipient_name, sender)
    return {
        "template": template.name if template else "",
        "subject": fill(template.subject if template else FALLBACK_SUBJECT, values),
        "body": fill(template.body if template else FALLBACK_BODY, values),
    }
