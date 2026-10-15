"""Generic field-level change tracking. apps.audit.apps.AuditConfig.ready()
registers which models to track and how to resolve their owning Job."""

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .middleware import get_current_user
from .models import AuditLog

# `edit_version` is the concurrency counter on photos and documents: it moves
# with every edit, so logging it would only repeat the edit it belongs to.
SKIP_FIELDS = {"id", "created_at", "updated_at", "edit_version"}


def track_model(model, get_job=lambda instance: None, fields=None):
    """Connects a pre_save handler that diffs `instance` against its
    current DB row and writes one AuditLog row per changed field.
    `fields` limits tracking to the named fields."""

    @receiver(pre_save, sender=model, weak=False)
    def _log_changes(sender, instance, **kwargs):
        if not instance.pk:
            return  # creation: nothing to diff against yet
        # all_objects where present: a soft-deleted row is still a row,
        # and its changes still belong in the audit trail.
        manager = getattr(sender, "all_objects", sender._default_manager)
        try:
            old = manager.get(pk=instance.pk)
        except sender.DoesNotExist:
            return

        user = get_current_user()
        changed_by = user if user and getattr(user, "is_authenticated", False) else None
        job = get_job(instance)

        for f in instance._meta.concrete_fields:
            if f.name in SKIP_FIELDS or (fields is not None and f.name not in fields):
                continue
            old_value = getattr(old, f.name)
            new_value = getattr(instance, f.name)
            if old_value == new_value:
                continue
            AuditLog.objects.create(
                model_name=sender.__name__,
                object_id=str(instance.pk),
                job=job,
                field_name=f.name,
                old_value=None if old_value is None else str(old_value),
                new_value=None if new_value is None else str(new_value),
                changed_by=changed_by,
            )

    return _log_changes
