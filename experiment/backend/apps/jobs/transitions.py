"""Moving a job through its lifecycle (CLAUDE.md §3).

`workflow.py` says which moves exist, who may make them and what they need;
this module applies those rules. The same code answers two questions so the
UI and the server can't disagree: "what can this user do now?"
(`available_actions`, with the reasons any are blocked) and "do it"
(`perform_transition`).

Tab data is frozen during review and after sign-off (see tabs.FROZEN_STATUSES),
so a move out of valuation is also the moment the numbers stop being editable:
that is why sending for review insists every tab is complete.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.permissions import is_platform_admin, roles_on_job
from apps.audit.middleware import acting_as

from .field_config import TABS, stage_tabs
from .models import Job, JobTransition
from .tabs import MEDIA_TABS, NotPermitted, TabError, media_completion, tab_completion, visibility_context
from .workflow import (
    PRE_REVIEW_STATUSES,
    TRANSITION_RULES,
    IssueBlockedError,
    JobLockedError,
    JobStatus,
    TransitionError,
)

# --- errors -----------------------------------------------------------------


class StaleStatus(TabError):
    status = 409
    code = "stale"


class NotAllowed(TabError):
    status = 409
    code = "not_allowed"


class JobLocked(TabError):
    status = 409
    code = "locked"


class CommentsRequired(TabError):
    status = 400
    code = "validation"

    def __init__(self):
        super().__init__("Some values are invalid.", errors={"comments": "A comment is required for this action."})


class GateBlocked(TabError):
    status = 422
    code = "blocked"

    def __init__(self, blockers):
        super().__init__("This can't be done yet.", blockers=blockers)


# --- who may act ----------------------------------------------------------------


def held_roles(user, job) -> set[str]:
    """Roles `user` can act as on this job.

    Platform admins can act as admin, valuer and inspector, but never as the
    peer reviewer or counter-signatory: a review only means something if the
    person doing it was actually assigned to it."""
    held = set(roles_on_job(user, job))
    if is_platform_admin(user):
        held |= {Role.ADMIN, Role.VALUER, Role.INSPECTOR}
    return held


# --- gates ------------------------------------------------------------------------


def review_ready(job) -> list[str]:
    """What stops this job going to peer review. Empty means it can."""
    blockers = []

    context = visibility_context(job)
    for tab in TABS:
        if not tab["fields"]:
            continue
        missing = tab_completion(tab["key"], context)["missing"]
        if missing:
            blockers.append(f"{tab['label']}: {', '.join(missing)}")

    from apps.media_files.checks import media_blockers  # the media app depends on this one

    blockers += media_blockers(job)

    if not job.peer_reviewer_id:
        blockers.append("Assign a peer reviewer on the Check List.")
    elif settings.PEER_REVIEW_REQUIRES_INDEPENDENT_REVIEWER and job.peer_reviewer_id in {
        job.valuer_id,
        job.registered_valuer_id,
    }:
        blockers.append("The peer reviewer must be someone other than the valuer or signing valuer.")
    return blockers


def countersign_ready(job) -> list[str]:
    return ["Already counter-signed."] if job.countersigned_at else []


def _as_signed_off(job) -> Job:
    """A fresh copy of `job` as it would be once the reviewer signs off, so
    the final-report checks can run before anything is written."""
    signed = Job.objects.get(pk=job.pk)
    signed.status = JobStatus.APPROVED_SIGNED
    signed.counter_signatory = job.peer_reviewer
    signed.countersigned_by = job.peer_reviewer
    signed.countersigned_at = timezone.now()
    return signed


def signoff_ready(job) -> list[str]:
    """What stops the reviewer signing off, which also finalises the report."""
    from apps.reports.issue import issue_blockers  # the reports app depends on this one

    if not job.peer_reviewer_id:
        return ["Assign a peer reviewer on the Check List."]
    return [b.replace("Counter-signatory", "Peer reviewer") for b in issue_blockers(_as_signed_off(job))]


def issue_ready(job) -> list[str]:
    # Imported here: the reports app depends on this one.
    from apps.reports.issue import issue_blockers

    return issue_blockers(job)


GATES = {
    "review_ready": review_ready,
    "signoff_ready": signoff_ready,
    "countersign_ready": countersign_ready,
    "issue_ready": issue_ready,
}


# In-place actions (see TransitionRule.action): what doing one records, and
# when it has already been done, so it stops being offered.
ACTIONS = {
    "countersign": {
        "perform": lambda job, user: job.countersign(user),
        "done": lambda job: job.countersigned_at is not None,
    },
}


def _blockers(job, rule) -> list[str]:
    return GATES[rule.gate](job) if rule.gate else []


# --- reading ------------------------------------------------------------------------


def available_actions(job, user) -> list[dict]:
    """The moves this user may make from the job's current status, each with
    whatever currently blocks it. Moves the user's role doesn't permit are
    left out rather than shown disabled."""
    if job.is_locked or job.issue_in_progress:
        return []
    held = held_roles(user, job)
    actions = []
    for (from_status, to_status), rule in TRANSITION_RULES.items():
        if from_status != job.status or not held & rule.roles:
            continue
        if rule.action and ACTIONS[rule.action]["done"](job):
            continue
        blockers = _blockers(job, rule)
        actions.append(
            {
                "to": to_status,
                "label": rule.label,
                "tone": rule.tone,
                "comments_required": rule.comments_required,
                "enabled": not blockers,
                "blockers": blockers,
            }
        )
    return actions


def transition_log(job) -> list[dict]:
    return [
        {
            "id": t.id,
            "from_status": t.from_status,
            "to_status": t.to_status,
            "to_label": dict(JobStatus.CHOICES).get(t.to_status, t.to_status),
            "label": TRANSITION_RULES.get((t.from_status, t.to_status)).label
            if (t.from_status, t.to_status) in TRANSITION_RULES
            else dict(JobStatus.CHOICES).get(t.to_status, t.to_status),
            "who": str(t.by) if t.by else "System",
            "comments": t.comments,
            "at": t.created_at,
        }
        for t in job.transitions.select_related("by")
    ]


# --- stages follow the tabs -------------------------------------------------------------

# The status a job reaches once a stage's tabs are all complete.
STAGE_REACHES = [
    ("setup", JobStatus.INSPECTION_SCHEDULED),
    ("inspection", JobStatus.VALUATION_IN_PROGRESS),
]


def _stage_complete(job, stage, context) -> bool:
    for key in stage_tabs(stage):
        done = media_completion(job, key) if key in MEDIA_TABS else tab_completion(key, context)
        if done["pct"] < 100:
            return False
    return True


def sync_stage(job, user) -> None:
    """Moves a job forward through the stages before review as their tabs are
    filled in: any edit starts setup, a complete Setup stage schedules the
    inspection, a complete Inspection stage starts the valuation. It only ever
    moves forward, and only before review; nothing is locked by stage (a job
    can be sent for review from any of them). Each step is logged like a
    manual one."""
    if job.status not in PRE_REVIEW_STATUSES:
        return
    order = PRE_REVIEW_STATUSES
    target = max(order.index(job.status), order.index(JobStatus.SETUP))
    context = visibility_context(job)
    for stage, status in STAGE_REACHES:
        if _stage_complete(job, stage, context):
            target = max(target, order.index(status))
    while order.index(job.status) < target:
        from_status = job.status
        job.transition_to(order[order.index(from_status) + 1])
        JobTransition.objects.create(job=job, from_status=from_status, to_status=job.status, by=user)


# --- doing -----------------------------------------------------------------------------


def perform_transition(job_id: int, user, from_status: str, to_status: str, comments: str = "") -> Job:
    """Makes one move, atomically.

    `from_status` is what the caller was looking at. If the job has moved on
    since (the valuer already pulled it back, say), the request is refused
    instead of acting on a screen that is no longer true.

    Issuing only *requests* the issue here: producing the final PDF is slow,
    so it runs in a background task (apps.reports.tasks) rather than inside
    this request and its row lock. Without a worker it runs straight after."""
    comments = (comments or "").strip()

    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)

        if job.is_locked:
            raise JobLocked("This job has been issued and is locked.")
        if job.issue_in_progress:
            raise NotAllowed("The final report is being produced. Wait for it to finish.")
        if job.status != from_status:
            raise StaleStatus(f"This job is now '{job.status}', not '{from_status}'. Reload and try again.")

        rule = TRANSITION_RULES.get((job.status, to_status))
        if rule is None:
            raise NotAllowed(f"A job can't go from '{job.status}' to '{to_status}' this way.")
        if not held_roles(user, job) & rule.roles:
            raise NotPermitted(f"Your role on this job doesn't allow '{rule.label}'.")
        if rule.comments_required and not comments:
            raise CommentsRequired()
        if blockers := _blockers(job, rule):
            raise GateBlocked(blockers)

        if to_status == JobStatus.ISSUED and from_status == JobStatus.PEER_REVIEW:
            # Sign-off: the reviewer approves and gives the second signature,
            # then the final report is produced as for any issue.
            job.counter_signatory = user
            job.transition_to(JobStatus.APPROVED_SIGNED)
            job.countersigned_by = user
            job.countersigned_at = timezone.now()
            JobTransition.objects.create(
                job=job, from_status=from_status, to_status=JobStatus.APPROVED_SIGNED, by=user,
                comments=comments,
            )
        if to_status == JobStatus.ISSUED:
            # The issue task writes the transition record when it succeeds.
            job.issue_requested_at = timezone.now()
            job.issue_requested_by = user
            job.issue_error = ""
            job.save()
        else:
            try:
                if rule.action:
                    ACTIONS[rule.action]["perform"](job, user)
                else:
                    job.transition_to(to_status, comments=comments if rule.comments_required else "")
            except JobLockedError as exc:
                raise JobLocked(str(exc)) from exc
            except TransitionError as exc:
                raise NotAllowed(str(exc)) from exc

            JobTransition.objects.create(
                job=job, from_status=from_status, to_status=to_status, by=user, comments=comments
            )

    if to_status == JobStatus.ISSUED:
        from apps.reports.tasks import request_issue  # the reports app depends on this one

        try:
            request_issue(job.pk, user)
        except IssueBlockedError as exc:  # only when run inline: something changed since the gate
            raise GateBlocked([str(exc)]) from exc
        except JobLockedError as exc:
            raise JobLocked(str(exc)) from exc
        job.refresh_from_db()
    return job
