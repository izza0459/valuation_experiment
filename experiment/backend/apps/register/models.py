from django.db import models

from apps.common.models import SoftDeleteModel
from apps.jobs.models import Job


class ValuationRegisterEntry(SoftDeleteModel):
    """DLD Administrative Resolution 67/2020 electronic register (CLAUDE.md
    §2, §7). One entry per completed valuation; exportable for DLD
    submission and for authority reporting."""

    job = models.OneToOneField(Job, on_delete=models.PROTECT, related_name="register_entry")

    requester_name = models.CharField(max_length=255)
    requester_contact = models.CharField(max_length=255, blank=True)
    requester_legal_status = models.CharField(max_length=100, blank=True, help_text="e.g. Bank, Individual, Company.")
    purpose = models.CharField(max_length=100)
    property_type = models.CharField(max_length=100)
    property_details = models.TextField(blank=True)
    developer = models.CharField(max_length=255, blank=True)
    ownership_form = models.CharField(max_length=100, blank=True)
    estimated_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    valuation_date = models.DateField(null=True, blank=True)

    registered_with_dld = models.BooleanField(default=False)
    registered_with_dld_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Valuation register entry"
        verbose_name_plural = "Valuation register entries"
        ordering = ["-valuation_date"]

    def __str__(self):
        return f"RegisterEntry<{self.job}>"
