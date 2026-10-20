"""Creating a job from the New instruction screen (design brief S2).

Reuses the tab write path rather than validating a second time: the intake
values are applied to the new job through `patch_tab`, so a field is accepted
or refused by exactly the same rules whether it is entered here or edited later
in the workspace. Everything happens in one transaction, so a rejected value
leaves no half-created job behind.
"""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models import Role
from apps.banks.models import Bank

from .models import Job, Property
from .tabs import TabError, ValidationFailed, patch_tab

# What the intake form may set, by the tab that stores it. Title-document
# details and the rest are entered in the workspace afterwards.
INTAKE_FIELDS = {
    "instructions": {
        "bank", "bank_reference_no", "client_name", "purpose", "date_time_request_received",
        "date_of_instruction", "contact_name", "contact_number",
    },
    "address": {
        "unit_number", "building_name", "community_name", "latitude", "longitude",
        "applicant_name", "ownership_name", "registered_valuer",
    },
    "checklist": {"inspected_by", "valuer", "peer_reviewer"},
    "summary": {"property_category"},
}


class NotAllowedToCreate(TabError):
    status = 403
    code = "forbidden"


def create_job(user, values: dict) -> Job:
    """Creates a job, its property and tab rows, and applies `values`.

    The creator becomes the job's admin. Mortgage work names a bank from the
    master, whose billing address comes across once its SLA is signed
    (CLAUDE.md §4 Tab 2); audit and internal work names the client
    organisation instead. Raises ValidationFailed with per-field errors,
    collected across every tab."""
    if not isinstance(values, dict):
        raise TabError("`values` must be an object.")

    by_tab: dict[str, dict] = {tab: {} for tab in INTAKE_FIELDS}
    errors: dict[str, str] = {}
    for key, raw in values.items():
        tab = next((t for t, keys in INTAKE_FIELDS.items() if key in keys), None)
        if tab is None:
            errors[key] = "Unknown field."
        else:
            by_tab[tab][key] = raw

    purpose = values.get("purpose") or "mortgage_security"
    bank_id = values.get("bank")
    bank = None
    if purpose == "mortgage_security":
        if isinstance(bank_id, int) and not isinstance(bank_id, bool):
            bank = Bank.objects.filter(pk=bank_id, active=True).first()
        if bank is None:
            errors["bank"] = "Choose the client bank." if bank_id in (None, "") else "No such bank."
    else:
        by_tab["instructions"].pop("bank", None)
        by_tab["instructions"].pop("bank_reference_no", None)
        if not str(values.get("client_name") or "").strip():
            errors["client_name"] = "Enter the organisation or client name."
    if errors:
        raise ValidationFailed(errors)

    # A valuer taking the instruction in values it too, unless the form names
    # someone else: they carry on past Setup, where ops hand the job off.
    if Role.VALUER in (user.roles or []):
        if by_tab["checklist"].get("valuer") in (None, ""):
            by_tab["checklist"]["valuer"] = user.pk
        if by_tab["address"].get("registered_valuer") in (None, ""):
            by_tab["address"]["registered_valuer"] = by_tab["checklist"]["valuer"]

    with transaction.atomic():
        job = Job(
            bank=bank,
            property=Property.objects.create(),
            admin_user=user,
            billing_address=bank.billing_address if bank and bank.sla_signed else "",
            # The bank's own code, unless the form gives a reference.
            bank_reference_no=bank.code if bank else "",
        )
        job.save()  # allocates the reference number; the signal adds the tab rows

        for tab, tab_values in by_tab.items():
            if not tab_values:
                continue
            try:
                patch_tab(job.pk, tab, user, tab_values, base_version=0, intake=True)
            except ValidationFailed as exc:
                errors.update(exc.extra["errors"])
        if errors:
            raise ValidationFailed(errors)  # rolls the whole creation back
    return Job.objects.get(pk=job.pk)
