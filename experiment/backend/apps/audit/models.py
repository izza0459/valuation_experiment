from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Field-level change log (CLAUDE.md §3: "Every field change is
    audit-logged (who, what, old/new, when)."). Populated by signal
    handlers in apps.audit.signals, not written by hand."""

    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=50, db_index=True)
    job = models.ForeignKey(
        "jobs.Job", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs",
        help_text="Denormalized for fast per-job history lookups.",
    )
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.model_name}#{self.object_id}.{self.field_name}: {self.old_value!r} -> {self.new_value!r}"
