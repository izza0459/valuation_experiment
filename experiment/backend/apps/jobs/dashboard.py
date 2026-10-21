"""The admin pipeline dashboard on the Home screen (CRM feedback DB-01..03).

A stage's count is the jobs that *entered* it within the date range (Q10),
dated by when they entered it: the request's arrival for Set-up, the
lifecycle log for the stages after it, the send for Sent to Bank (Q11). So
the drop-off between two stages reads as "of the jobs that reached this
stage, how many reached the next". Each count lists its jobs.

Opening a stage counts its jobs by section (DB-03), with its own range: where
each job currently is within the stage (the first section not complete),
the call status on Scheduling, and the review outcome on Peer Review.
"""

from __future__ import annotations

import datetime

from django.db.models import Q
from django.utils import timezone

from .field_config import TABS
from .models import Job, JobTransition, SchedulingData
from .tabs import MEDIA_TABS, job_progress
from .workflow import JobStatus

STAGES = [
    ("setup", "Set-up"),
    ("scheduling", "Scheduling"),
    ("inspection", "Inspection"),
    ("valuation", "Valuation"),
    ("peer_review", "Peer Review"),
    ("sent", "Sent to Bank"),
]

# The status a job reaches on entering each stage after Set-up.
ENTERS = {
    "scheduling": JobStatus.SCHEDULING,
    "inspection": JobStatus.INSPECTION_SCHEDULED,
    "valuation": JobStatus.VALUATION_IN_PROGRESS,
    "peer_review": JobStatus.PEER_REVIEW,
}

# Statuses in which a job is "in" a stage, for the section counts.
IN_STAGE = {
    "setup": {JobStatus.INSTRUCTION_RECEIVED, JobStatus.SETUP},
    "scheduling": {JobStatus.SCHEDULING},
    "inspection": {JobStatus.INSPECTION_SCHEDULED, JobStatus.INSPECTED},
    "valuation": {JobStatus.VALUATION_IN_PROGRESS},
}

PRESETS = ("today", "week", "month", "30d")


def date_range(preset: str | None, start: str | None, end: str | None) -> tuple[datetime.datetime, datetime.datetime]:
    """[from, to) in Dubai time for a preset (DB-02), or a custom range of dates."""
    today = timezone.localdate()
    if start or end:
        first = datetime.date.fromisoformat(start) if start else today - datetime.timedelta(days=29)
        last = datetime.date.fromisoformat(end) if end else today
    elif preset == "today":
        first = last = today
    elif preset == "week":
        first, last = today - datetime.timedelta(days=today.weekday()), today
    elif preset == "month":
        first, last = today.replace(day=1), today
    else:  # last 30 days, the default
        first, last = today - datetime.timedelta(days=29), today
    if last < first:
        first, last = last, first
    tz = timezone.get_current_timezone()
    begin = datetime.datetime.combine(first, datetime.time.min, tzinfo=tz)
    finish = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz)
    return begin, finish


def _describe(job: Job) -> dict:
    return {"id": job.pk, "ref": job.bayut_internal_reference_no, "property": str(job.property),
            "status": job.get_status_display()}


def _entered(jobs, stage: str, begin, end) -> list[Job]:
    if stage == "setup":
        rule = Q(date_time_request_received__gte=begin, date_time_request_received__lt=end) | Q(
            date_time_request_received__isnull=True, created_at__gte=begin, created_at__lt=end)
        return list(jobs.filter(rule).select_related("property"))
    if stage == "sent":
        return list(jobs.filter(deliveries__status="sent", deliveries__sent_at__gte=begin,
                                deliveries__sent_at__lt=end).distinct().select_related("property"))
    ids = JobTransition.objects.filter(
        to_status=ENTERS[stage], created_at__gte=begin, created_at__lt=end
    ).values_list("job_id", flat=True)
    return list(jobs.filter(pk__in=ids).select_related("property"))


def funnel(jobs, begin, end) -> dict:
    stages, previous = [], None
    for key, label in STAGES:
        entered = _entered(jobs, key, begin, end)
        entry = {"key": key, "label": label, "count": len(entered), "jobs": [_describe(j) for j in entered]}
        if previous is not None:
            lost = previous - len(entered)
            entry["drop"] = {"count": lost, "pct": round(lost / previous * 100) if previous else None}
        stages.append(entry)
        previous = len(entered)
    return {"from": begin.date(), "to": (end - datetime.timedelta(days=1)).date(), "stages": stages}


def sections(jobs, stage: str, begin, end) -> list[dict]:
    """Counts within one stage (DB-03)."""
    groups: dict[str, list[Job]] = {}

    def add(label, job):
        groups.setdefault(label, []).append(job)

    if stage == "scheduling":
        entered = _entered(jobs, "scheduling", begin, end)
        statuses = dict(SchedulingData.objects.filter(job__in=entered).values_list("job_id", "call_status"))
        labels = dict(SchedulingData.CALL_STATUS_CHOICES)
        for label in labels.values():
            groups[label] = []
        for job in entered:
            add(labels.get(statuses.get(job.pk, "not_called"), "Not Called"), job)
    elif stage == "peer_review":
        for label in ("Awaiting review", "Returned to valuer", "Approved & signed"):
            groups[label] = []
        for job in _entered(jobs, "peer_review", begin, end):
            if job.status == JobStatus.PEER_REVIEW:
                add("Awaiting review", job)
            elif job.status in (JobStatus.APPROVED_SIGNED, JobStatus.ISSUED):
                add("Approved & signed", job)
            else:
                add("Returned to valuer", job)
    elif stage in IN_STAGE:
        # Every section of the stage gets a card, empty or not.
        for tab in sorted(TABS, key=lambda t: t["order"]):
            if tab["stage"] == stage and (tab["fields"] or tab["key"] in MEDIA_TABS):
                groups[tab["label"]] = []
        groups["Ready for the next stage"] = []
        for job in _entered(jobs, stage, begin, end):
            if job.status in IN_STAGE[stage]:
                add(job_progress(job)["sub_status"], job)
    return [{"label": label, "count": len(group), "jobs": [_describe(j) for j in group]}
            for label, group in groups.items()]
