from django.conf import settings
from django.db import models

from apps.common.models import SoftDeleteModel
from apps.jobs.models import Job


class StoredFile(SoftDeleteModel):
    """What photos and documents have in common.

    The file itself lives in the configured storage under `s3_key` (the name
    predates local storage); the key is generated, never taken from the upload,
    so a file name can't steer where anything is written. Stored files are
    never overwritten or physically removed by the app: deleting an item hides
    it, and a revision's copy of an item points at the same file."""

    s3_key = models.CharField(max_length=512)
    thumb_key = models.CharField(max_length=512, blank=True)
    original_name = models.CharField(max_length=255, blank=True, help_text="As uploaded; for display only.")
    content_type = models.CharField(max_length=100, blank=True, help_text="Of the stored file, not the upload.")
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True, help_text="Of the uploaded bytes.")
    caption = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)
    include_in_report = models.BooleanField(default=True)
    # Bumped on every edit; a save based on an older number is refused (first edit wins).
    edit_version = models.PositiveIntegerField(default=1)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["order", "uploaded_at", "id"]


class Photo(StoredFile):
    class Slot(models.TextChoices):
        GENERAL = "general", "General"
        MAKANI = "makani", "Makani number"
        DEWA = "dewa", "DEWA number"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="photos")
    slot = models.CharField(max_length=20, choices=Slot.choices, default=Slot.GENERAL)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)

    class Meta(StoredFile.Meta):
        pass

    def __str__(self):
        return f"Photo<{self.job}:{self.caption or self.original_name or self.s3_key}>"


class Document(StoredFile):
    # Values come from the admin-editable `document_type` presets (CLAUDE.md §4).
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=60, default="other")
    page_count = models.PositiveIntegerField(default=1)

    class Meta(StoredFile.Meta):
        pass

    def __str__(self):
        return f"Document<{self.job}:{self.caption or self.original_name or self.s3_key}>"


class FileCopy(models.Model):
    """A copy, in the database, of a file the storage wrote to disk, for
    hosting whose disk is wiped on every restart (Render's free plan). Only
    the most recent job's files are kept: see apps.media_files.storage."""

    name = models.CharField(max_length=512, unique=True)
    # The job's reference without a revision suffix ("BYT-2026-00006").
    job_ref = models.CharField(max_length=64, db_index=True)
    data = models.BinaryField()
    saved_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
