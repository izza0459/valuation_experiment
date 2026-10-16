from django.conf import settings
from django.db import models

from apps.jobs.models import Job
from apps.jobs.workflow import JobLockedError


def _refuse_if_locked(job_ids, what):
    """Evidence is part of what an issued report rests on, so it is frozen
    with the job (CLAUDE.md §3: on issue the job is locked)."""
    locked = list(
        Job.all_objects.filter(pk__in=set(job_ids), is_locked=True)
        .values_list("bayut_internal_reference_no", flat=True)
    )
    if locked:
        raise JobLockedError(
            f"{what} belongs to issued job {', '.join(locked)} and cannot be changed. Create a revision instead."
        )


class JobEvidenceQuerySet(models.QuerySet):
    """Bulk writes skip `save()`/`delete()`, so they check the lock too."""

    def delete(self):
        _refuse_if_locked(self.values_list("job_id", flat=True), self.model.__name__)
        return super().delete()

    def update(self, **kwargs):
        _refuse_if_locked(self.values_list("job_id", flat=True), self.model.__name__)
        return super().update(**kwargs)


class JobEvidence(models.Model):
    """Base for evidence rows owned by one job."""

    objects = JobEvidenceQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        ids = [self.job_id]
        if self.pk:  # moving a row off a locked job is a change to that job too
            ids += type(self).objects.filter(pk=self.pk).values_list("job_id", flat=True)
        _refuse_if_locked(ids, type(self).__name__)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _refuse_if_locked([self.job_id], type(self).__name__)
        return super().delete(*args, **kwargs)


class Comparable(models.Model):
    """One internal schema for every evidence source (CLAUDE.md §6).
    New sources (DLD, Bayut, Property Monitor) are just connectors that
    write rows here with their own `source` + `source_ref`."""

    # Where the evidence comes from. A valuer entering one by hand picks the
    # source; connectors (DLD, Bayut, Property Monitor) will write the same rows.
    SOURCE_CHOICES = [
        ("dld", "DLD transaction"),
        ("bayut", "Bayut"),
        ("property_finder", "Property Finder"),
        ("property_monitor", "Property Monitor"),
        ("agent", "Agent / broker"),
        ("other", "Other"),
        ("manual", "Manual"),
        ("csv", "CSV/Excel upload"),
    ]
    ENTRY_SOURCES = ["dld", "bayut", "property_finder", "property_monitor", "agent", "other"]
    STATUS_CHOICES = [("sold", "Sold"), ("asking", "Asking")]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    source_ref = models.CharField(max_length=255, blank=True, help_text="External id/url for traceability.")
    pulled_at = models.DateTimeField(auto_now_add=True)

    community_name = models.CharField(max_length=255, blank=True)
    building_name = models.CharField(max_length=255, blank=True)
    property_type = models.CharField(max_length=60, blank=True)
    beds = models.PositiveSmallIntegerField(null=True, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    view = models.CharField(max_length=100, blank=True)
    bua_sqft = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_aed = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    transaction_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="asking")
    raw_data = models.JSONField(default=dict, blank=True, help_text="Original payload from the source connector.")
    link = models.URLField(max_length=1000, blank=True, help_text="The listing or record this came from.")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-transaction_date"]

    def save(self, *args, **kwargs):
        """A comparable cited by an issued report is part of what was signed,
        like its property's address: it can't be edited afterwards."""
        if self.pk:
            _refuse_if_locked(self.job_links.values_list("job_id", flat=True), "This comparable")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_source_display()} comparable: {self.community_name} {self.bua_sqft}sqft"

    @property
    def price_per_sqft(self):
        if not self.price_aed or not self.bua_sqft:
            return None
        return self.price_aed / self.bua_sqft


class JobComparable(JobEvidence):
    """Which comparables a valuer ticked for a given job, and their order
    in the report's comparables table (CLAUDE.md §6)."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="job_comparables")
    comparable = models.ForeignKey(Comparable, on_delete=models.PROTECT, related_name="job_links")
    selected = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta(JobEvidence.Meta):
        abstract = False
        unique_together = [("job", "comparable")]
        ordering = ["order"]

    def __str__(self):
        return f"JobComparable<{self.job}:{self.comparable}>"


class AVMRun(JobEvidence):
    """One record per AVM execution, stored per job version so past runs
    stay auditable even after the valuer overrides the value (CLAUDE.md §6)."""

    CONFIDENCE_CHOICES = [("high", "High"), ("medium", "Medium"), ("low", "Low")]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="avm_runs")
    job_version = models.PositiveIntegerField()
    inputs = models.JSONField(default=dict, help_text="Selected comparable ids + adjustment config used.")
    suggested_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    low_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    high_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    aed_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, blank=True)
    workings = models.JSONField(default=dict, help_text="Show-your-work breakdown for the UI/report.")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    final_value_deviation_reason = models.TextField(
        blank=True,
        help_text="Required when the valuer's final value deviates from this run by more than "
                   "settings.AVM_DEVIATION_THRESHOLD_PCT.",
    )

    class Meta(JobEvidence.Meta):
        abstract = False
        ordering = ["-created_at"]

    def __str__(self):
        return f"AVMRun<{self.job} v{self.job_version} @ {self.created_at:%Y-%m-%d}>"

    def deviation_pct(self, final_value):
        if not self.suggested_value or final_value is None:
            return None
        return abs(final_value - self.suggested_value) / self.suggested_value * 100
