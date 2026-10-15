"""Background work for reports (CLAUDE.md §8: PDF rendering runs in Celery).

Issuing is requested by the lifecycle move (apps.jobs.transitions) and
carried out here, so the slow PDF render happens outside the request and
outside the job's row lock. With no worker running (dev.sh, tests:
CELERY_TASK_ALWAYS_EAGER) it runs inline straight after the request's
transaction instead, and its errors reach the caller as before.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.accounts.models import User
from apps.audit.middleware import acting_as
from apps.jobs.models import Job
from apps.jobs.workflow import IssueBlockedError, JobLockedError

from .issue import issue_report

logger = logging.getLogger(__name__)

FAILED = "Producing the final report failed. Try issuing again; if it keeps failing, contact support."


def run_issue(job_id: int, user_id: int | None):
    """Issues the job, or records why it couldn't and frees it for another try."""
    user = User.objects.filter(pk=user_id).first() if user_id else None
    with acting_as(user):
        try:
            return issue_report(job_id, user)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, IssueBlockedError | JobLockedError) else FAILED
            if reason == FAILED:
                logger.exception("Issuing job %s failed", job_id)
            Job.objects.filter(pk=job_id, is_locked=False).update(issue_requested_at=None, issue_error=reason)
            raise


@shared_task(name="reports.issue_job")
def issue_job(job_id: int, user_id: int | None):
    try:
        run_issue(job_id, user_id)
    except (IssueBlockedError, JobLockedError):
        pass  # recorded on the job for the UI; nothing to retry


def request_issue(job_id: int, user):
    """Starts issuing a job whose issue request has just been recorded. Call
    it after that request's transaction has committed, so a worker sees it."""
    user_id = user.pk if user else None
    if settings.CELERY_TASK_ALWAYS_EAGER:
        run_issue(job_id, user_id)
    else:
        issue_job.delay(job_id, user_id)
