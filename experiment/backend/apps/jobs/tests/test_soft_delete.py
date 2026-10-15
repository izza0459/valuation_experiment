"""Soft deletion and retention (CLAUDE.md §7, DLD 67/2020)."""
import datetime

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.banks.models import Bank
from apps.common.models import RetentionError
from apps.jobs.models import Job, Property
from apps.jobs.workflow import JobLockedError
from apps.media_files.models import Photo

pytestmark = pytest.mark.django_db


@pytest.fixture
def job():
    bank = Bank.objects.create(name="Test Bank")
    prop = Property.objects.create(building_name="Marina Gate 1")
    return Job.objects.create(bank=bank, property=prop)


class TestSoftDelete:
    def test_delete_hides_the_row_without_destroying_it(self, job):
        job.delete()

        assert Job.objects.filter(pk=job.pk).count() == 0
        assert Job.all_objects.filter(pk=job.pk).count() == 1
        assert Job.all_objects.get(pk=job.pk).is_deleted is True

    def test_records_who_deleted_it(self, job):
        user = User.objects.create(username="dan", email="dan@example.com")
        job.delete(by=user)
        assert Job.all_objects.get(pk=job.pk).deleted_by == user

    def test_queryset_delete_also_soft_deletes(self, job):
        """Bulk delete (the admin's delete action) must not be a way around
        the rule."""
        Job.objects.filter(pk=job.pk).delete()

        assert Job.objects.filter(pk=job.pk).count() == 0
        assert Job.all_objects.filter(pk=job.pk).count() == 1

    def test_related_lookups_skip_deleted_rows(self, job):
        keep = Photo.objects.create(job=job, s3_key="keep.jpg")
        drop = Photo.objects.create(job=job, s3_key="drop.jpg")
        drop.delete()

        assert list(job.photos.all()) == [keep]
        assert Photo.all_objects.filter(job=job).count() == 2

    def test_restore_brings_it_back(self, job):
        job.delete()
        Job.all_objects.get(pk=job.pk).restore()
        assert Job.objects.filter(pk=job.pk).count() == 1


class TestIssuedJobsCannotBeRemoved:
    """An issued job is a regulatory record — neither delete path may
    remove it (CLAUDE.md §3 lock-on-issue + §7 retention)."""

    @pytest.fixture
    def issued_job(self, job):
        Job.all_objects.filter(pk=job.pk).update(is_locked=True)
        job.refresh_from_db()
        return job

    def test_instance_delete_is_refused(self, issued_job):
        with pytest.raises(JobLockedError):
            issued_job.delete()
        assert Job.objects.filter(pk=issued_job.pk).count() == 1

    def test_bulk_delete_is_refused_too(self, issued_job):
        """Regression: queryset.delete() goes straight to UPDATE, so it
        would otherwise slip past the save() guard."""
        with pytest.raises(JobLockedError):
            Job.objects.filter(pk=issued_job.pk).delete()
        assert Job.objects.filter(pk=issued_job.pk).count() == 1

    def test_unlocked_jobs_still_bulk_delete_normally(self, job):
        Job.objects.filter(pk=job.pk).delete()
        assert Job.objects.filter(pk=job.pk).count() == 0


class TestRetention:
    def test_purge_refused_inside_the_retention_window(self, job):
        with pytest.raises(RetentionError) as exc:
            job.hard_delete()
        assert "retention" in str(exc.value).lower()
        assert Job.all_objects.filter(pk=job.pk).count() == 1

    def test_purge_allowed_once_retention_has_expired(self, job):
        # Six years old: past the five-year window.
        Job.all_objects.filter(pk=job.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=365 * 6)
        )
        job.refresh_from_db()

        job.hard_delete()
        assert Job.all_objects.filter(pk=job.pk).count() == 0

    def test_retention_runs_from_issue_date_for_issued_work(self, job):
        job.issued_at = timezone.now()
        assert job.retention_anchor == job.issued_at

    def test_force_overrides_for_records_created_in_error(self, job):
        job.hard_delete(force=True)
        assert Job.all_objects.filter(pk=job.pk).count() == 0
