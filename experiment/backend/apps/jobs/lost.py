"""Marking a lead lost: it won't go ahead (cancelled, fee not agreed, ...).

Lost is final. The job keeps its data (soft deletes only, CLAUDE.md §7) but
can't be edited or moved again; a new instruction for the property is a new
lead. The status it was lost from feeds the dashboard's drop-off.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.permissions import is_platform_admin, roles_on_job
from apps.audit.middleware import acting_as
from apps.presets.models import PresetOption

from .models import Job, JobTransition
from .tabs import JobIsLocked, NotPermitted, TabError, ValidationFailed
from .workflow import JobStatus

# Before review the work is still a lead; once signed off it is a report.
LOSABLE = {
    JobStatus.INSTRUCTION_RECEIVED, JobStatus.SETUP, JobStatus.SCHEDULING, JobStatus.INSPECTION_SCHEDULED,
    JobStatus.INSPECTED, JobStatus.VALUATION_IN_PROGRESS, JobStatus.PEER_REVIEW,
}
MARK_ROLES = {Role.ADMIN, Role.OPS, Role.VALUER}


class AlreadyClosed(TabError):
    status = 409
    code = "not_allowed"


def may_mark_lost(user, job) -> bool:
    if job.status not in LOSABLE or job.is_locked or job.issue_in_progress:
        return False
    return is_platform_admin(user) or bool(roles_on_job(user, job) & MARK_ROLES)


def reasons() -> list[dict]:
    return [{"value": r.value, "label": r.label}
            for r in PresetOption.objects.filter(field_key="lost_reason", active=True)]


def reason_label(value: str) -> str:
    row = PresetOption.objects.filter(field_key="lost_reason", value=value).first()
    return row.label if row else value


def mark_lost(job_id: int, user, reason, note) -> Job:
    reason = reason if isinstance(reason, str) else ""
    note = note.strip() if isinstance(note, str) else ""
    errors = {}
    if reason not in {r["value"] for r in reasons()}:
        errors["reason"] = "Choose why the lead was lost."
    if reason == "other" and not note:
        errors["note"] = "Say what happened."
    if errors:
        raise ValidationFailed(errors)

    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if job.is_locked:
            raise JobIsLocked("This job has been issued and is locked.")
        if job.status not in LOSABLE or job.issue_in_progress:
            raise AlreadyClosed("This lead can't be marked lost now.")
        if not may_mark_lost(user, job):
            raise NotPermitted("Your role on this job doesn't allow marking it lost.")
        from_status = job.status
        job.status = JobStatus.LOST
        job.lost_reason, job.lost_note, job.lost_from_status = reason, note, from_status
        job.lost_by, job.lost_at = user, timezone.now()
        job.save()
        comment = reason_label(reason) + (f": {note}" if note else "")
        JobTransition.objects.create(job=job, from_status=from_status, to_status=JobStatus.LOST, by=user,
                                     comments=comment)
    return job
