"""Job lifecycle state machine, defined as config rather than scattered
if/else — mirrors Carforce's config-driven flow stages (CLAUDE.md §8).
"""

from django.conf import settings

from apps.accounts.models import Role


class JobStatus:
    INSTRUCTION_RECEIVED = "instruction_received"
    SETUP = "setup"
    # Calling the contact to book the inspection (CRM feedback SC-01).
    SCHEDULING = "scheduling"
    INSPECTION_SCHEDULED = "inspection_scheduled"
    INSPECTED = "inspected"
    VALUATION_IN_PROGRESS = "valuation_in_progress"
    PEER_REVIEW = "peer_review"
    APPROVED_SIGNED = "approved_signed"
    ISSUED = "issued"

    CHOICES = [
        (INSTRUCTION_RECEIVED, "Instruction Received"),
        (SETUP, "Setup"),
        (SCHEDULING, "Scheduling"),
        (INSPECTION_SCHEDULED, "Inspection Scheduled"),
        (INSPECTED, "Inspected"),
        (VALUATION_IN_PROGRESS, "Valuation In Progress"),
        (PEER_REVIEW, "Peer Review"),
        (APPROVED_SIGNED, "Approved & Signed"),
        (ISSUED, "Issued"),
    ]


# Allowed forward/back transitions (CLAUDE.md §3). Peer review can bounce
# the job back to valuation_in_progress with comments.
# Stages before review: the job moves through these as their tabs are filled in
# (transitions.sync_stage), and can be sent for review from any of them —
# nothing is locked by stage.
PRE_REVIEW_STATUSES = [
    JobStatus.INSTRUCTION_RECEIVED,
    JobStatus.SETUP,
    JobStatus.SCHEDULING,
    JobStatus.INSPECTION_SCHEDULED,
    JobStatus.INSPECTED,
    JobStatus.VALUATION_IN_PROGRESS,
]

ALLOWED_TRANSITIONS = {
    JobStatus.INSTRUCTION_RECEIVED: {JobStatus.SETUP, JobStatus.PEER_REVIEW},
    # Straight to inspection_scheduled stays allowed for jobs set up before
    # the Scheduling stage existed.
    JobStatus.SETUP: {JobStatus.SCHEDULING, JobStatus.INSPECTION_SCHEDULED, JobStatus.PEER_REVIEW},
    JobStatus.SCHEDULING: {JobStatus.INSPECTION_SCHEDULED, JobStatus.PEER_REVIEW},
    JobStatus.INSPECTION_SCHEDULED: {JobStatus.INSPECTED, JobStatus.PEER_REVIEW},
    JobStatus.INSPECTED: {JobStatus.VALUATION_IN_PROGRESS, JobStatus.PEER_REVIEW},
    JobStatus.VALUATION_IN_PROGRESS: {JobStatus.PEER_REVIEW},
    JobStatus.PEER_REVIEW: {JobStatus.VALUATION_IN_PROGRESS, JobStatus.APPROVED_SIGNED},
    # Reopen: sign-off froze the data (see FROZEN_STATUSES), so without a way
    # back a mistake found after approval could only be fixed by issuing the
    # report and then revising it. Not in the original lifecycle in CLAUDE.md.
    JobStatus.APPROVED_SIGNED: {JobStatus.ISSUED, JobStatus.VALUATION_IN_PROGRESS},
    JobStatus.ISSUED: set(),  # locked; re-issue creates a new Job version instead
}


# While a job is under review or signed off its data must not move: an edit
# after the peer reviewer approved would put numbers on the report that
# nobody reviewed. To change anything, return it to valuation_in_progress.
FROZEN_STATUSES = {JobStatus.PEER_REVIEW, JobStatus.APPROVED_SIGNED}


class TransitionRule:
    """Who may make one transition and what it needs, as data (CLAUDE.md §8:
    stages and transitions as config, like Carforce flows)."""

    def __init__(self, label, roles, *, comments_required=False, gate=None, tone="primary", action=None):
        self.label = label
        self.roles = frozenset(roles)
        self.comments_required = comments_required
        self.gate = gate  # name of a check in apps.jobs.transitions.GATES
        self.tone = tone
        # An in-place action (from == to): something recorded at this stage
        # without moving the job on, named in apps.jobs.transitions.ACTIONS.
        self.action = action


# Issuing is a rule like the others but `perform_transition` hands it to
# apps.reports.issue, because it must render and store the final PDF and lock
# the job in the same transaction (CLAUDE.md §3).
TRANSITION_RULES = {
    (JobStatus.INSTRUCTION_RECEIVED, JobStatus.SETUP):
        TransitionRule("Start setup", {Role.ADMIN, Role.VALUER}),
    (JobStatus.SETUP, JobStatus.SCHEDULING):
        TransitionRule("Start scheduling", {Role.ADMIN, Role.OPS, Role.VALUER}),
    (JobStatus.SETUP, JobStatus.INSPECTION_SCHEDULED):
        TransitionRule("Schedule inspection", {Role.ADMIN, Role.VALUER}),
    (JobStatus.SCHEDULING, JobStatus.INSPECTION_SCHEDULED):
        TransitionRule("Inspection booked", {Role.ADMIN, Role.OPS, Role.INSPECTOR, Role.VALUER}),
    (JobStatus.INSPECTION_SCHEDULED, JobStatus.INSPECTED):
        TransitionRule("Mark inspected", {Role.INSPECTOR, Role.VALUER}),
    (JobStatus.INSPECTED, JobStatus.VALUATION_IN_PROGRESS):
        TransitionRule("Start valuation", {Role.VALUER}),
    **{
        (status, JobStatus.PEER_REVIEW): TransitionRule("Send for review", {Role.VALUER}, gate="review_ready")
        for status in PRE_REVIEW_STATUSES
    },
    (JobStatus.PEER_REVIEW, JobStatus.VALUATION_IN_PROGRESS):
        TransitionRule("Return to valuer", {Role.PEER_REVIEWER}, comments_required=True, tone="outline"),
    # The reviewer's sign-off is the second signature and finalises the report
    # in one step: approved, counter-signed by the reviewer, then issued
    # (transitions.perform_transition). Only the assigned reviewer can give it.
    (JobStatus.PEER_REVIEW, JobStatus.ISSUED):
        TransitionRule("Sign off", {Role.PEER_REVIEWER}, gate="signoff_ready"),
    # A separate second signature, for jobs approved before sign-off became
    # one step. Only the assigned counter-signatory can give it.
    (JobStatus.APPROVED_SIGNED, JobStatus.APPROVED_SIGNED):
        TransitionRule("Counter-sign", {Role.COUNTER_SIGNATORY}, gate="countersign_ready", action="countersign"),
    (JobStatus.APPROVED_SIGNED, JobStatus.VALUATION_IN_PROGRESS):
        TransitionRule("Reopen", {Role.PEER_REVIEWER, Role.ADMIN}, comments_required=True, tone="outline"),
    # Retrying a sign-off whose report couldn't be produced.
    (JobStatus.APPROVED_SIGNED, JobStatus.ISSUED):
        TransitionRule("Issue report", {Role.ADMIN}, gate="issue_ready"),
}


# Sign-off moves peer_review -> approved_signed -> issued in one request; it
# is the one rule that isn't a single allowed move.
SIGN_OFF = (JobStatus.PEER_REVIEW, JobStatus.ISSUED)


class TransitionError(Exception):
    """Raised when a job is moved to a status it can't legally reach."""


class JobLockedError(Exception):
    """Raised when something tries to modify an issued (locked) job."""


class IssueBlockedError(Exception):
    """Raised when a job fails the pre-issue checks (peer review,
    counter-signature, valid RERA licence)."""


def validate_transition(current_status: str, new_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise TransitionError(
            f"Cannot transition job from '{current_status}' to '{new_status}'. "
            f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
        )


def _licence_errors(user, who: str) -> list[str]:
    """Both signatories put their RERA registration on the report, so both
    need a current one (CLAUDE.md §3: "signer's RERA licence")."""
    if user is None:
        return ["Registered (signing) valuer is required before issue."] if who == "Signing valuer" else []
    profile = getattr(user, "valuer_profile", None)
    if profile is None or not profile.is_licence_valid:
        return [f"{who}'s RERA licence is missing or expired."]
    return []


def validate_issue_preconditions(job) -> list[str]:
    """Returns a list of blocking reasons; empty list means issuable.
    Rules per CLAUDE.md §3: peer review + counter-signature required,
    signer's RERA licence must not be expired.
    """
    errors = []
    if job.status != JobStatus.APPROVED_SIGNED:
        errors.append("Job must be in 'approved_signed' status before it can be issued.")
    if not job.peer_reviewer_id:
        errors.append("Peer reviewer is required before issue.")
    if not job.counter_signatory_id:
        errors.append("Counter-signatory is required before issue.")
    elif not job.countersigned_at or job.countersigned_by_id != job.counter_signatory_id:
        errors.append("The counter-signatory has not counter-signed the report.")

    if not settings.DEMO_MODE:  # demo: licences needn't be on file yet
        errors.extend(_licence_errors(job.registered_valuer, "Signing valuer"))
        if job.counter_signatory_id:
            errors.extend(_licence_errors(job.counter_signatory, "Counter-signatory"))

    return errors
