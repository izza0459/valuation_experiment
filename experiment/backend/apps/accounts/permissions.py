"""Role-based access control (CLAUDE.md §3 roles, §7 "RBAC").

Job access is driven by the role FKs on the Job itself rather than by
global groups: one person commonly holds several roles on one job, and
different people hold them on the next.
"""

from rest_framework import permissions

from .models import Role

# Which Job field corresponds to which role (CLAUDE.md §3).
JOB_ROLE_FIELDS = {
    Role.ADMIN: "admin_user",
    Role.INSPECTOR: "inspected_by",
    Role.VALUER: "valuer",
    Role.PEER_REVIEWER: "peer_reviewer",
    Role.COUNTER_SIGNATORY: "counter_signatory",
}


def is_platform_admin(user) -> bool:
    """Platform admins (and Django staff) see everything — the valuation
    team is small and admins create and issue the work."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser or Role.ADMIN in (user.roles or [])


def roles_on_job(user, job) -> set[str]:
    """Every role this user holds on this job, which may be several."""
    if not user or not user.is_authenticated:
        return set()
    held = {
        role
        for role, field in JOB_ROLE_FIELDS.items()
        if getattr(job, f"{field}_id", None) == user.id
    }
    # The signing valuer isn't a separate role, but it must grant access.
    if getattr(job, "registered_valuer_id", None) == user.id:
        held.add(Role.VALUER)
    return held


def can_access_job(user, job) -> bool:
    return is_platform_admin(user) or bool(roles_on_job(user, job))


def visible_jobs(queryset, user):
    """Scopes a Job queryset to what `user` is entitled to see."""
    from django.db.models import Q

    if is_platform_admin(user):
        return queryset
    if not user or not user.is_authenticated:
        return queryset.none()

    condition = Q(registered_valuer=user)
    for field in JOB_ROLE_FIELDS.values():
        condition |= Q(**{field: user})
    return queryset.filter(condition).distinct()


class IsPlatformAdmin(permissions.BasePermission):
    """Admin-only endpoints: creating instructions and managing users, banks
    and presets."""

    message = "Only an admin can do this."

    def has_permission(self, request, view):
        return is_platform_admin(request.user)


class IsJobParticipantOrAdmin(permissions.BasePermission):
    """Object-level guard for Job (and job-owned) endpoints."""

    message = "You do not hold a role on this job."

    def has_object_permission(self, request, view, obj):
        job = obj if hasattr(obj, "status") else getattr(obj, "job", None)
        if job is None:
            return False
        return can_access_job(request.user, job)
