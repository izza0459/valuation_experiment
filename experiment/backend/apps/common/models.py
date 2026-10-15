"""Soft deletion and retention (CLAUDE.md §7: "5-year retention, soft
deletes only, full audit trail", per DLD Administrative Resolution
67/2020).

Nothing that forms part of a valuation record is ever removed from the
database by normal application code. `delete()` marks the row; a genuine
purge needs `hard_delete()`, which refuses while the row is still inside
its retention window.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class RetentionError(Exception):
    """Raised when a purge is attempted inside the retention window."""


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        """Bulk deletes (admin actions, cascades) come through here rather
        than `Model.delete()`, so this has to soft-delete too — otherwise
        the rule is bypassed by selecting two rows instead of one.

        Row by row through `Model.delete()`, not one UPDATE: that is what
        records who deleted each row, runs each model's own save rules and
        writes the audit trail."""
        count = 0
        for obj in self.filter(deleted_at__isnull=True):
            obj.delete()
            count += 1
        return count, {self.model._meta.label: count}

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    """Default manager: soft-deleted rows are invisible to ordinary code,
    including related lookups like `job.photos.all()`."""

    queryset_class = SoftDeleteQuerySet

    def get_queryset(self):
        return self.queryset_class(self.model, using=self._db).filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager):
    """Everything, deleted included — for audit, restore and retention."""

    queryset_class = SoftDeleteQuerySet

    def get_queryset(self):
        return self.queryset_class(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def retention_anchor(self):
        """The date the retention window counts from. Issued work is held
        from its issue date; anything else from when it was created."""
        return getattr(self, "issued_at", None) or getattr(self, "created_at", None)

    @property
    def retention_expires_at(self):
        anchor = self.retention_anchor
        if anchor is None:
            return None
        return anchor + timezone.timedelta(days=365 * settings.VALUATION_RETENTION_YEARS)

    def delete(self, using=None, keep_parents=False, *, by=None):
        if by is None:
            from apps.audit.middleware import get_current_user

            current = get_current_user()
            by = current if current is not None and getattr(current, "is_authenticated", False) else None
        self.deleted_at = timezone.now()
        self.deleted_by = by
        self.save(update_fields=["deleted_at", "deleted_by"])

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["deleted_at", "deleted_by"])

    def hard_delete(self, using=None, keep_parents=False, *, force=False):
        """Permanently removes the row. Refuses inside the retention
        window unless explicitly forced (which should only happen for
        records created in error, with a documented reason)."""
        expires_at = self.retention_expires_at
        if not force and expires_at is not None and timezone.now() < expires_at:
            raise RetentionError(
                f"{type(self).__name__} {self.pk} is retained until "
                f"{expires_at:%Y-%m-%d} ({settings.VALUATION_RETENTION_YEARS}-year "
                f"retention, DLD 67/2020) and cannot be purged."
            )
        return super().delete(using=using, keep_parents=keep_parents)
