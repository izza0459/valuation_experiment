from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"

    def ready(self):
        from apps.jobs.models import (
            ChecklistData,
            InspectionData,
            Job,
            LocationData,
            Property,
            SummaryData,
            ValuationData,
        )

        from .signals import track_model

        track_model(Job, get_job=lambda instance: instance)
        # Address, coordinates and parties are report content too. A property
        # belongs to one job lineage (create_revision clones it), so its
        # newest job is the one the edit belongs to.
        track_model(Property, get_job=lambda instance: instance.jobs.order_by("-pk").first())
        # Masters that change what reports say or who may sign them.
        from apps.accounts.models import User, ValuerProfile
        from apps.banks.models import Bank
        from apps.presets.models import PresetOption, TextLibraryItem

        for master in (Bank, ValuerProfile, PresetOption, TextLibraryItem):
            track_model(master)
        # Who someone is and what they may do; granting admin must leave a
        # trace. Only these fields: the row also carries the password hash
        # and last-login time.
        track_model(
            User,
            fields={"username", "email", "first_name", "last_name", "roles", "is_active", "is_staff", "is_superuser"},
        )
        track_model(ChecklistData, get_job=lambda instance: instance.job)
        track_model(SummaryData, get_job=lambda instance: instance.job)
        track_model(InspectionData, get_job=lambda instance: instance.job)
        track_model(LocationData, get_job=lambda instance: instance.job)
        track_model(ValuationData, get_job=lambda instance: instance.job)

        # Photographs and documents are report content: captions, what is
        # included, order and removals are all part of the trail.
        from apps.media_files.models import Document, Photo

        track_model(Photo, get_job=lambda instance: instance.job)
        track_model(Document, get_job=lambda instance: instance.job)
