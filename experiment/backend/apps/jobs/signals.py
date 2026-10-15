from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ChecklistData, InspectionData, Job, LocationData, SummaryData, ValuationData

TAB_DATA_MODELS = [ChecklistData, SummaryData, InspectionData, LocationData, ValuationData]


@receiver(post_save, sender=Job)
def create_tab_data(sender, instance, created, **kwargs):
    """A job's 9 tabs are filled progressively by different roles over the
    job lifecycle (CLAUDE.md §3), so the one-to-one tab rows must exist
    from creation rather than being lazily created on first edit."""
    if not created or kwargs.get("raw"):
        return  # a fixture load (raw) brings its own tab rows
    for model in TAB_DATA_MODELS:
        model.objects.get_or_create(job=instance)
