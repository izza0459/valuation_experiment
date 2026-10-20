"""The most recent job's files survive a wiped disk (Render's free plan)."""
import shutil

import pytest
from django.core.files.base import ContentFile

from apps.media_files.models import FileCopy
from apps.media_files.storage import LatestJobCopyStorage, job_ref

pytestmark = pytest.mark.django_db


@pytest.fixture
def storage(tmp_path):
    return LatestJobCopyStorage(location=tmp_path)


def wipe(storage):
    """What a restart does to the disk."""
    shutil.rmtree(storage.location)


def test_a_wiped_file_comes_back_from_its_copy(storage):
    name = storage.save("jobs/BYT-2026-00006/photos/front.jpg", ContentFile(b"jpeg-bytes"))
    wipe(storage)
    assert storage.exists(name)
    with storage.open(name) as handle:
        assert handle.read() == b"jpeg-bytes"
    assert storage.size(name) == len(b"jpeg-bytes")


def test_only_the_most_recent_jobs_files_are_kept(storage):
    old = storage.save("jobs/BYT-2026-00005/photos/a.jpg", ContentFile(b"old"))
    pdf = storage.save("reports/BYT-2026-00006/BYT-2026-00006-v2-issued.pdf", ContentFile(b"%PDF"))
    new = storage.save("jobs/BYT-2026-00006-v2/photos/b.jpg", ContentFile(b"new"))
    assert set(FileCopy.objects.values_list("name", flat=True)) == {pdf, new}
    wipe(storage)
    assert not storage.exists(old)
    assert storage.exists(new) and storage.exists(pdf)


def test_deleting_a_file_deletes_its_copy(storage):
    name = storage.save("jobs/BYT-2026-00006/documents/deed.pdf", ContentFile(b"%PDF"))
    storage.delete(name)
    assert not FileCopy.objects.exists()


def test_files_outside_a_job_are_not_copied(storage):
    storage.save("other/logo.png", ContentFile(b"png"))
    assert not FileCopy.objects.exists()


def test_a_revision_belongs_with_its_job():
    assert job_ref("jobs/BYT-2026-00006-v2/photos/x.jpg") == "BYT-2026-00006"
    assert job_ref("reports/BYT-2026-00006/x.pdf") == "BYT-2026-00006"
    assert job_ref("jobs/") is None
