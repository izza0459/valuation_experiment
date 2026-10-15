"""Issuing a report (CLAUDE.md §3).

Issuing renders the final PDF, stores it with the template used and a
snapshot of every input, and locks the job. The slow part (the PDF) happens
first, with no lock held; then, under the job's row lock, the report row, the
lock and the transition record are written in one transaction, so a job is
never locked without a report or reported without being locked. If anything
after the PDF is stored fails, the stored file is removed again.

What stands in the way is computed in one place (`_blockers`) and used twice:
by the lifecycle gate, so the UI shows the reasons before anyone clicks, and
again inside `issue_report`, so the rules hold for any caller. The issue run
renders the report's HTML once and uses it both for that check and the PDF.
"""

from __future__ import annotations

import html as htmllib
import json
import re

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import Job, JobTransition
from apps.jobs.workflow import IssueBlockedError, JobLockedError, JobStatus, validate_issue_preconditions
from apps.media_files.checks import missing_files

from .context import build_context, outstanding_items
from .models import ReportVersion
from .render import choose_template, pdf_engine_available, render_html, render_pdf

# Placeholder wording is marked in the default template and in the seeded text
# library; the one pattern covers both. See default_template/report.html.j2.
PLACEHOLDER = re.compile(r"\[PLACEHOLDER[^\]]*\](?P<after>[^<\n]{0,60})")
SHOWN_PLACEHOLDERS = 6


def placeholders_in(html: str) -> list[str]:
    """Short descriptions of each distinct placeholder passage in `html`."""
    found = []
    for match in PLACEHOLDER.finditer(html):
        text = match.group(0)
        if ":" in text.split("]")[0]:
            label = text.split(":", 1)[1].split("]")[0].strip()
        else:
            label = match.group("after").strip().rstrip(".") or "unnamed passage"
        label = htmllib.unescape(label)
        if label not in found:
            found.append(label)
    return found


def _blockers(job, html: str) -> list[str]:
    blockers = validate_issue_preconditions(job)

    if not pdf_engine_available():
        blockers.append("The PDF engine isn't available on the server, so the final report can't be produced.")

    if missing := outstanding_items(job):
        blockers.append("Incomplete: " + "; ".join(missing))

    if gone := missing_files(job):
        blockers.append(
            f"{len(gone)} photograph/document file(s) are missing from storage: {', '.join(gone[:3])}"
            + (" and others." if len(gone) > 3 else ".")
        )

    # The rendered text is the only reliable place to find placeholders: they
    # can come from the template, the text library, or be left in free text
    # by a valuer.
    found = placeholders_in(html)
    if found:
        shown = ", ".join(found[:SHOWN_PLACEHOLDERS])
        more = f" and {len(found) - SHOWN_PLACEHOLDERS} more" if len(found) > SHOWN_PLACEHOLDERS else ""
        blockers.append(
            f"The report still contains {len(found)} placeholder passage(s) awaiting approved wording: {shown}{more}."
        )
    return blockers


def issue_blockers(job) -> list[str]:
    """Everything that currently stops this job being issued. Empty means it can."""
    return _blockers(job, render_html(choose_template(job), build_context(job, issued=True)))


def _fingerprint(context: dict) -> str:
    """What the report says, minus the day it happened to be rendered on."""
    meta = {k: v for k, v in context["meta"].items() if k != "generated_on"}
    return json.dumps({**context, "meta": meta}, sort_keys=True, default=str)


def issue_report(job, user) -> ReportVersion:
    """Renders and stores the final report, then locks the job.

    `job` may be a Job or its id. Must not be called with the job's row
    already locked by a long transaction: the PDF is rendered before the lock
    is taken, and the data it was rendered from is checked again under the
    lock, so an edit that slipped in meanwhile is refused rather than signed."""
    job_id = job.pk if isinstance(job, Job) else job
    job = Job.objects.get(pk=job_id)

    template = choose_template(job)
    context = build_context(job, issued=True)
    html = render_html(template, context)
    if blockers := _blockers(job, html):
        raise IssueBlockedError("; ".join(blockers))
    pdf = render_pdf(html)

    now = timezone.now()
    key = default_storage.save(
        f"reports/{job.reference_root}/{job.file_stem}-issued-{now:%Y%m%d-%H%M%S}.pdf", ContentFile(pdf)
    )
    try:
        # Atomic on its own (a savepoint inside a caller's transaction), so a
        # failure undoes every row written here and the file is removed.
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job_id)
            if job.is_locked:
                raise JobLockedError(f"Job {job.bayut_internal_reference_no} has already been issued.")
            if (
                job.status != JobStatus.APPROVED_SIGNED
                or choose_template(job).pk != template.pk
                or _fingerprint(build_context(job, issued=True)) != _fingerprint(context)
            ):
                raise IssueBlockedError("The job changed while its report was being produced. Issue it again.")
            version = ReportVersion.objects.create(
                job=job,
                job_version=job.version,
                template=template,
                input_snapshot=context,
                pdf_s3_key=key,  # the field name predates local storage
                issued_at=now,
                issued_by=user,
            )
            job.issue()
            JobTransition.objects.create(
                job=job, from_status=JobStatus.APPROVED_SIGNED, to_status=JobStatus.ISSUED, by=user
            )
    except BaseException:
        default_storage.delete(key)
        raise
    return version
