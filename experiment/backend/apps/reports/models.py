from django.conf import settings
from django.db import models

from apps.common.models import SoftDeleteModel


class ReportTemplate(models.Model):
    """Versioned Jinja2 HTML/CSS template rendered to PDF via WeasyPrint
    (CLAUDE.md §5, §8). Per-bank variants are supported via `bank`."""

    name = models.CharField(max_length=255)
    version = models.CharField(max_length=20, help_text="e.g. v1, v2-adib")
    bank = models.ForeignKey(
        "banks.Bank", null=True, blank=True, on_delete=models.CASCADE, related_name="report_templates",
        help_text="Leave blank for the default/generic template.",
    )
    html = models.TextField(help_text="Jinja2 template source.")
    css = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("name", "version", "bank")]
        ordering = ["name", "version"]

    def __str__(self):
        bank_part = f" [{self.bank}]" if self.bank_id else ""
        return f"{self.name} {self.version}{bank_part}"


class ReportVersion(SoftDeleteModel):
    """One per issued/generated PDF. Stores a full input snapshot so a
    re-issue is reproducible even if the job's live data later changes
    (CLAUDE.md §5: "each issued report stores its template version and a
    snapshot of its inputs")."""

    job = models.ForeignKey("jobs.Job", on_delete=models.CASCADE, related_name="report_versions")
    job_version = models.PositiveIntegerField()
    template = models.ForeignKey(ReportTemplate, on_delete=models.PROTECT, related_name="report_versions")
    pdf_s3_key = models.CharField(max_length=512, blank=True)
    input_snapshot = models.JSONField(default=dict)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ReportVersion<{self.job} v{self.job_version}>"
