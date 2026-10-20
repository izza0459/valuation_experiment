"""Producing and storing report versions."""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from .context import build_context
from .models import ReportVersion
from .render import choose_template, render_html, render_pdf


def preview_html(job) -> str:
    """The report as it would read right now, rendered from live data. Cheap
    and instant: the preview-edit-regenerate loop (CLAUDE.md §5) runs on this."""
    return render_html(choose_template(job), build_context(job))


@transaction.atomic
def generate_report(job, user) -> ReportVersion:
    """Renders a draft PDF and stores it with the template used and a
    snapshot of every input, so it can be reproduced later (CLAUDE.md §5).

    The PDF is rendered before anything is written: if the engine is
    unavailable nothing is left behind."""
    template = choose_template(job)
    context = build_context(job)
    pdf = render_pdf(render_html(template, context))

    version = ReportVersion.objects.create(
        job=job, job_version=job.version, template=template, input_snapshot=context,
    )
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    key = f"reports/{job.reference_root}/{job.file_stem}-{stamp}-draft.pdf"
    version.pdf_s3_key = default_storage.save(key, ContentFile(pdf))  # the key name predates local storage
    version.save(update_fields=["pdf_s3_key"])
    return version


def render_version_html(version: ReportVersion) -> str:
    """Re-renders a stored version from its own snapshot and template, not
    from the live job, so an issued report can always be reproduced."""
    return render_html(version.template, version.input_snapshot)


def stored_pdf_key(version: ReportVersion) -> str:
    """The storage key of a version's PDF, rebuilding the file from the
    version's own snapshot and template when it has gone missing (hosting
    without persistent storage loses files on every deploy). The content is
    what was signed; only the file is new. Photos and documents that were
    lost too are left out, as when a report is rendered without them."""
    key = version.pdf_s3_key
    if key and default_storage.exists(key):
        return key
    job = version.job
    pdf = render_pdf(render_version_html(version))
    name = key or f"reports/{job.reference_root}/{job.file_stem}-version-{version.pk}.pdf"
    version.pdf_s3_key = default_storage.save(name, ContentFile(pdf))
    version.save(update_fields=["pdf_s3_key"])
    return version.pdf_s3_key
