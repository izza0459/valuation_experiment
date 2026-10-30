"""Peer-review suggestions.

During peer review the reviewer can change any form field, but the change
is recorded as a suggestion (a ReviewerEdit) rather than saved: the valuer's
value stays until the valuer accepts it, which saves it like any other edit
(audit-logged), or declines it with a reason. Sign-off waits until none are
open (transitions.signoff_ready).
"""

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.permissions import is_platform_admin, roles_on_job
from apps.audit.middleware import acting_as

from .field_config import get_tab
from .models import Job, JobTabVersion, ReviewerEdit
from .workflow import JobStatus
from .tabs import ASSIGNMENT_FIELDS, NotPermitted, TabError, ValidationFailed, _validated, _wire, job_tab_state, patch_tab


class NotFound(TabError):
    status = 404
    code = "not_found"


def open_suggestions(job):
    return job.reviewer_edits.filter(accepted_at__isnull=True, declined_at__isnull=True)


def may_suggest(user, job, tab_key: str | None = None) -> bool:
    """The job's peer reviewer, while the job is with them, on a form tab."""
    if job.status != JobStatus.PEER_REVIEW or Role.PEER_REVIEWER not in roles_on_job(user, job):
        return False
    return tab_key is None or (tab_key != "review" and bool(get_tab(tab_key)["fields"]))


def may_decide(user, job) -> bool:
    return not job.is_locked and (is_platform_admin(user) or Role.VALUER in roles_on_job(user, job))


def suggest(job_id: int, user, tab_key: str, field_key: str, value, note: str = "") -> ReviewerEdit | None:
    """Records (or updates) the reviewer's suggestion for one field. Suggesting
    the value already saved withdraws it. Returns the suggestion, or None."""
    try:
        tab = get_tab(tab_key)
    except KeyError as exc:
        raise NotFound(f"No such tab: {tab_key}.") from exc
    field = next((f for f in tab["fields"] if f["key"] == field_key), None)
    if field is None or field["calculated"] or field_key in ASSIGNMENT_FIELDS:
        raise ValidationFailed({field_key: "This field can't be suggested."})

    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if not may_suggest(user, job, tab_key):
            raise NotPermitted("Only the peer reviewer can suggest changes, while the job is in review.")
        _, cleaned = _validated(job, tab_key, {field_key: value})
        suggested = _wire({field_key: cleaned[field_key][2]})[field_key]
        current = job_tab_state(job)[tab_key]["values"].get(field_key)
        existing = open_suggestions(job).filter(tab_key=tab_key, field_key=field_key).first()
        if suggested == current:
            if existing:
                existing.delete()
            return None
        if existing:
            existing.new_value, existing.note, existing.at = suggested, note.strip(), timezone.now()
            existing.save(update_fields=["new_value", "note", "at"])
            return existing
        return ReviewerEdit.objects.create(
            job=job, tab_key=tab_key, field_key=field_key, label=field["label"],
            old_value=current, new_value=suggested, note=note.strip(), by=user,
        )


def _open(job_id: int, suggestion_id: int) -> tuple[Job, ReviewerEdit]:
    job = Job.objects.select_for_update().get(pk=job_id)
    edit = open_suggestions(job).filter(pk=suggestion_id).first()
    if edit is None:
        raise NotFound("That suggestion has already been dealt with.")
    return job, edit


def _check_may_decide(user, job, edit) -> None:
    if edit.by_id == user.pk:
        raise NotPermitted("The valuer answers your suggestions; you can withdraw one instead.")
    if not may_decide(user, job):
        raise NotPermitted("Only the valuer on this job can answer suggestions.")


def accept(job_id: int, suggestion_id: int, user) -> ReviewerEdit:
    """Saves the suggested value as the valuer, then marks it accepted."""
    with acting_as(user), transaction.atomic():
        job, edit = _open(job_id, suggestion_id)
        _check_may_decide(user, job, edit)
        version, _ = JobTabVersion.objects.get_or_create(job=job, tab_key=edit.tab_key)
        # `intake`: accepting is allowed while the job is still in review,
        # when the valuer can't otherwise edit; the lock still applies.
        patch_tab(job.pk, edit.tab_key, user, {edit.field_key: edit.new_value}, version.version, intake=True)
        edit.accepted_by, edit.accepted_at = user, timezone.now()
        edit.save(update_fields=["accepted_by", "accepted_at"])
        return edit


def decline(job_id: int, suggestion_id: int, user, reason: str) -> ReviewerEdit:
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed({"reason": "Say why, so the reviewer knows."})
    with transaction.atomic():
        job, edit = _open(job_id, suggestion_id)
        _check_may_decide(user, job, edit)
        edit.declined_by, edit.declined_at, edit.decline_reason = user, timezone.now(), reason
        edit.save(update_fields=["declined_by", "declined_at", "decline_reason"])
        return edit


def withdraw(job_id: int, suggestion_id: int, user) -> None:
    with transaction.atomic():
        _, edit = _open(job_id, suggestion_id)
        if edit.by_id != user.pk:
            raise NotPermitted("Only the reviewer who made a suggestion can withdraw it.")
        edit.delete()


def as_text(tab_key: str, field_key: str, value) -> str:
    """A value as the screen shows it: option labels rather than stored
    keys, Yes/No, library entries by title."""
    if value is None or value == "" or value == []:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    try:
        field = next((f for f in get_tab(tab_key)["fields"] if f["key"] == field_key), None)
    except KeyError:
        field = None
    labels = {}
    if field and field.get("options_key") and field["type"] in {"select", "multiselect"}:
        from apps.presets.options import options_for

        try:
            labels = {str(o["value"]): o["label"] for o in options_for(field["options_key"])}
        except KeyError:
            labels = {}
    if isinstance(value, list):
        return ", ".join(
            str(v.get("title") or v.get("body", "")) if isinstance(v, dict) else labels.get(str(v), str(v)) for v in value
        )
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, "", []))
    return labels.get(str(value), str(value))


def describe(edit: ReviewerEdit) -> dict:
    status = "accepted" if edit.accepted_at else "declined" if edit.declined_at else "open"
    decided_by = edit.accepted_by if edit.accepted_at else edit.declined_by
    return {
        "id": edit.id, "tab": edit.tab_key, "field": edit.field_key, "label": edit.label,
        "old": edit.old_value, "new": edit.new_value, "note": edit.note,
        "old_text": as_text(edit.tab_key, edit.field_key, edit.old_value),
        "new_text": as_text(edit.tab_key, edit.field_key, edit.new_value),
        "by": str(edit.by) if edit.by else "", "by_id": edit.by_id, "at": edit.at, "status": status,
        "decided_by": str(decided_by) if decided_by else "", "decided_at": edit.accepted_at or edit.declined_at,
        "decline_reason": edit.decline_reason,
    }
