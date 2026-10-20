"""File storage that survives a wiped disk, for the most recent job.

Render's free plan starts every restart (deploy, waking from sleep) with an
empty disk, so uploaded photos and documents and the report PDFs vanish.
With FILE_COPIES_IN_DB on, every job file written is also copied into the
database, and a file missing from disk is put back from its copy when read.
Only one job's copies are kept, the one most recently written to, so the free
database (1 GB) doesn't fill up: writing a file for another job clears the
copies of the previous one. Real hosting uses S3 instead (CLAUDE.md §8).
"""

from __future__ import annotations

import logging

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

logger = logging.getLogger(__name__)

# Files under these folders belong to a job: jobs/<ref>/… and reports/<ref>/….
JOB_FOLDERS = ("jobs/", "reports/")


def job_ref(name: str) -> str | None:
    """`jobs/BYT-2026-00006-v2/photos/x.jpg` -> `BYT-2026-00006` (a revision
    belongs with its job)."""
    if not name.startswith(JOB_FOLDERS):
        return None
    parts = name.split("/")
    if len(parts) < 3 or not parts[1]:
        return None
    return "-".join(parts[1].split("-")[:3])


class LatestJobCopyStorage(FileSystemStorage):
    def _save(self, name, content):
        name = super()._save(name, content)
        ref = job_ref(name)
        if ref:
            try:
                from .models import FileCopy

                with super()._open(name, "rb") as handle:
                    data = handle.read()
                FileCopy.objects.update_or_create(name=name, defaults={"job_ref": ref, "data": data})
                # Only the most recent job's files are kept.
                FileCopy.objects.exclude(job_ref=ref).delete()
            except Exception:  # a failed copy must never fail the upload itself
                logger.exception("Couldn't keep a database copy of %s", name)
        return name

    def _copy(self, name):
        if not job_ref(name):
            return None
        from .models import FileCopy

        return FileCopy.objects.filter(name=name).only("data").first()

    def _restore(self, name) -> bool:
        """Puts a file wiped from disk back from its copy."""
        copy = self._copy(name)
        if copy is None:
            return False
        super()._save(name, ContentFile(bytes(copy.data)))  # same name: the file isn't there
        return True

    def exists(self, name):
        return super().exists(name) or self._copy(name) is not None

    def _open(self, name, mode="rb"):
        if not super().exists(name):
            self._restore(name)
        return super()._open(name, mode)

    def size(self, name):
        if not super().exists(name):
            self._restore(name)
        return super().size(name)

    def delete(self, name):
        super().delete(name)
        if job_ref(name):
            from .models import FileCopy

            FileCopy.objects.filter(name=name).delete()
