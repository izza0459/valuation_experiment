"""Reassigning a lead: handing one of its roles (admin, inspector, valuer,
peer reviewer, counter-signatory) to someone else, from the lead card.

Allowed for platform admins, the job's admin or valuer (who can already
change the team on the Check List), and the manager of whoever holds the
role now. The change goes through the audit log like any other edit."""

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.models import Role
from apps.accounts.permissions import JOB_ROLE_FIELDS
from apps.audit.middleware import acting_as

from .models import Job
from .tabs import JobIsLocked, NotPermitted, ValidationFailed, may_assign
from .workflow import JobStatus

ROLE_LABELS = {
    Role.ADMIN: "Admin", Role.INSPECTOR: "Inspector", Role.VALUER: "Valuer",
    Role.PEER_REVIEWER: "Peer reviewer", Role.COUNTER_SIGNATORY: "Counter-signatory",
}
# Who can take each role: ops take instructions in as well as admins.
ELIGIBLE = {Role.ADMIN: {Role.ADMIN, Role.OPS}}


def _closed(job) -> bool:
    return job.is_locked or job.status == JobStatus.LOST


def may_reassign(user, job) -> bool:
    if _closed(job):
        return False
    if may_assign(user, job):
        return True
    team = user.team_ids() - {user.pk}
    return any(getattr(job, f"{field}_id", None) in team for field in JOB_ROLE_FIELDS.values())


def candidates() -> dict[str, list[dict]]:
    """Active users who can take each role."""
    users = list(get_user_model().objects.filter(is_active=True).order_by("first_name", "email"))
    return {
        role: [{"id": u.pk, "name": str(u)} for u in users if set(u.roles or []) & ELIGIBLE.get(role, {role})]
        for role in JOB_ROLE_FIELDS
    }


def reassign(job_id: int, user, role: str, person_id) -> Job:
    if role not in JOB_ROLE_FIELDS:
        raise ValidationFailed({"role": "Choose a role."})
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if _closed(job):
            raise JobIsLocked("This lead is closed, so its team can't change.")
        if not may_reassign(user, job):
            raise NotPermitted("Only an admin, the lead's valuer or the holder's manager can reassign it.")
        person = get_user_model().objects.filter(pk=person_id, is_active=True).first() if person_id else None
        if person is None or not set(person.roles or []) & ELIGIBLE.get(role, {role}):
            raise ValidationFailed({"person": f"Choose someone who can be the {ROLE_LABELS[role].lower()}."})
        field = JOB_ROLE_FIELDS[role]
        setattr(job, field, person)
        job.save(update_fields=[field, "updated_at"])
        return job
