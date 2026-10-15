"""Photographs and documents over the API: who may add them, what is refused,
how they are changed, ordered and removed, and what the job needs of them."""

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.banks.models import Bank
from apps.jobs.models import Job, Property
from apps.jobs.workflow import JobStatus
from apps.media_files import service
from apps.media_files.checks import media_blockers, missing_files
from apps.media_files.models import Document, Photo
from apps.media_files.tests.helpers import attach_media, jpeg_bytes, pdf_bytes, upload_file

pytestmark = pytest.mark.django_db


def make_user(name, roles=None):
    return User.objects.create(username=name, email=f"{name}@example.com", first_name=name.title(), roles=roles or [])


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture(autouse=True)
def presets():
    call_command("seed_presets")


@pytest.fixture
def boss():
    return make_user("boss", [Role.ADMIN])


@pytest.fixture
def dan():
    return make_user("dan")


@pytest.fixture
def ines():
    return make_user("ines")


@pytest.fixture
def pat():
    return make_user("pat")


@pytest.fixture
def job(dan, ines, pat):
    """Dan values, Ines inspects, Pat reviews."""
    return Job.objects.create(
        bank=Bank.objects.create(name="Test Bank"),
        property=Property.objects.create(building_name="Marina Gate 1"),
        valuer=dan,
        registered_valuer=dan,
        inspected_by=ines,
        peer_reviewer=pat,
    )


def post_files(user, job, kind, files, **data):
    return client_for(user).post(f"/api/jobs/{job.pk}/{kind}/", {"files": files, **data}, format="multipart")


def photo(name="a.jpg", seed=1):
    return upload_file(name, jpeg_bytes(seed))


def add_photos(user, job, n=1, start=1):
    res = post_files(user, job, "photos", [photo(f"p{start + i}.jpg", start + i) for i in range(n)])
    assert res.status_code == 201, res.content
    return res.json()["created"]


# --- uploading -------------------------------------------------------------------------------


class TestUploading:
    def test_several_photos_at_once_are_stored_in_order_with_thumbnails(self, job, dan, settings):
        res = post_files(dan, job, "photos", [photo(f"p{i}.jpg", i) for i in range(1, 4)])
        assert res.status_code == 201
        body = res.json()
        assert [p["order"] for p in body["created"]] == [1, 2, 3] and body["rejected"] == []
        stored = Photo.objects.get(pk=body["created"][0]["id"])
        assert (settings.MEDIA_ROOT / stored.s3_key).exists() and (settings.MEDIA_ROOT / stored.thumb_key).exists()
        assert stored.uploaded_by == dan and stored.width == 640 and stored.content_type == "image/jpeg"

    def test_the_stored_name_is_generated_not_taken_from_the_upload(self, job, dan):
        res = post_files(dan, job, "photos", [upload_file("../../etc/passwd.jpg", jpeg_bytes(1))])
        created = res.json()["created"][0]
        stored = Photo.objects.get(pk=created["id"])
        assert stored.s3_key.startswith(f"jobs/{job.bayut_internal_reference_no}/photos/")
        assert ".." not in stored.s3_key and "passwd" not in stored.s3_key
        assert "/" not in created["original_name"] and "\\" not in created["original_name"]

    def test_files_that_are_not_what_they_claim_are_refused_one_by_one(self, job, dan):
        res = post_files(
            dan,
            job,
            "photos",
            [
                upload_file("good.jpg", jpeg_bytes(1)),
                upload_file("malware.jpg", b"MZ\x90\x00 an executable pretending to be a photo"),
                upload_file("contract.pdf", pdf_bytes()),
                upload_file("empty.jpg", b""),
            ],
        )
        assert res.status_code == 201
        body = res.json()
        assert len(body["created"]) == 1
        reasons = {r["name"]: r["reason"] for r in body["rejected"]}
        assert set(reasons) == {"malware.jpg", "contract.pdf", "empty.jpg"}
        assert "JPG, PNG, HEIC" in reasons["malware.jpg"] and "empty" in reasons["empty.jpg"]

    def test_when_nothing_is_acceptable_it_says_so(self, job, dan):
        res = post_files(dan, job, "photos", [upload_file("x.jpg", b"nope")])
        assert res.status_code == 400 and res.json()["code"] == "rejected" and res.json()["rejected"]

    def test_the_same_file_twice_is_added_once(self, job, dan):
        first = post_files(dan, job, "photos", [photo("one.jpg", 7), photo("copy.jpg", 7)])
        assert len(first.json()["created"]) == 1 and "twice" in first.json()["rejected"][0]["reason"]
        again = post_files(dan, job, "photos", [photo("later.jpg", 7)])
        assert again.status_code == 400 and "already been added" in again.json()["rejected"][0]["reason"]

    def test_a_removed_file_can_be_added_again(self, job, dan):
        created = add_photos(dan, job)[0]
        assert client_for(dan).delete(f"/api/jobs/{job.pk}/photos/{created['id']}/").status_code == 204
        assert post_files(dan, job, "photos", [photo("back.jpg", 1)]).status_code == 201

    def test_an_oversized_file_is_refused(self, job, dan, monkeypatch):
        monkeypatch.setattr("apps.media_files.processing.MAX_BYTES", 100)
        res = post_files(dan, job, "photos", [photo()])
        assert res.status_code == 400 and "larger than" in res.json()["rejected"][0]["reason"]

    def test_a_job_holds_a_limited_number(self, job, dan, monkeypatch):
        monkeypatch.setattr(service, "PHOTOS", service.Kind("photos", Photo, 2, service.PHOTOS.accepts, "photograph"))
        monkeypatch.setitem(service.KINDS, "photos", service.PHOTOS)
        res = post_files(dan, job, "photos", [photo(f"p{i}.jpg", i) for i in range(1, 4)])
        assert len(res.json()["created"]) == 2
        assert "at most 2" in res.json()["rejected"][0]["reason"]

    def test_too_many_files_in_one_go_are_declined(self, job, dan, monkeypatch):
        monkeypatch.setattr(service, "FILES_PER_REQUEST", 2)
        res = post_files(dan, job, "photos", [photo(f"p{i}.jpg", i) for i in range(1, 4)])
        assert len(res.json()["created"]) == 2 and "at a time" in res.json()["rejected"][0]["reason"]

    def test_documents_take_pdfs_and_scans_and_record_their_type(self, job, boss):
        res = post_files(
            boss,
            job,
            "documents",
            [
                upload_file("deed.pdf", pdf_bytes(3)),
                upload_file("scan.jpg", jpeg_bytes(2)),
            ],
            doc_type="spa",
        )
        created = res.json()["created"]
        assert [d["doc_type"] for d in created] == ["spa", "spa"]
        assert created[0]["is_pdf"] and created[0]["page_count"] == 3 and not created[1]["is_pdf"]

    def test_an_unknown_type_is_refused(self, job, boss):
        assert (
            post_files(boss, job, "documents", [upload_file("d.pdf", pdf_bytes())], doc_type="nonsense").status_code
            == 400
        )
        assert post_files(boss, job, "photos", [photo()], slot="nonsense").status_code == 400

    def test_no_files_chosen(self, job, dan):
        assert client_for(dan).post(f"/api/jobs/{job.pk}/photos/", {}, format="multipart").status_code == 400


# --- who may do what -----------------------------------------------------------------------


class TestPermissions:
    def test_the_inspector_takes_photographs_but_does_not_attach_title_documents(self, job, ines):
        assert post_files(ines, job, "photos", [photo()]).status_code == 201
        assert post_files(ines, job, "documents", [upload_file("d.pdf", pdf_bytes())]).status_code == 403

    def test_the_valuer_and_the_admin_can_attach_documents(self, job, dan, boss):
        assert post_files(dan, job, "documents", [upload_file("a.pdf", pdf_bytes(1))]).status_code == 201
        assert post_files(boss, job, "documents", [upload_file("b.pdf", pdf_bytes(2))]).status_code == 201

    def test_the_reviewer_can_look_but_not_change(self, job, dan, pat):
        created = add_photos(dan, job)[0]
        client = client_for(pat)
        assert client.get(f"/api/jobs/{job.pk}/photos/").json()["can_edit"] is False
        assert post_files(pat, job, "photos", [photo("x.jpg", 9)]).status_code == 403
        assert (
            client.patch(
                f"/api/jobs/{job.pk}/photos/{created['id']}/", {"base_version": 1, "caption": "x"}, format="json"
            ).status_code
            == 403
        )
        assert client.delete(f"/api/jobs/{job.pk}/photos/{created['id']}/").status_code == 403

    def test_strangers_and_anonymous_users_see_nothing(self, job, dan):
        created = add_photos(dan, job)[0]
        stranger = client_for(make_user("stranger"))
        for path in ("photos/", f"photos/{created['id']}/file/", f"photos/{created['id']}/thumb/"):
            assert stranger.get(f"/api/jobs/{job.pk}/{path}").status_code == 404
        assert APIClient().get(f"/api/jobs/{job.pk}/photos/").status_code in (401, 403)
        assert APIClient().get(f"/api/jobs/{job.pk}/photos/{created['id']}/file/").status_code in (401, 403)

    def test_another_jobs_item_cannot_be_reached_through_this_one(self, job, dan, boss):
        other = Job.objects.create(
            bank=job.bank,
            property=Property.objects.create(building_name="Elsewhere"),
            valuer=dan,
            registered_valuer=dan,
        )
        theirs = add_photos(dan, other)[0]
        client = client_for(boss)
        assert client.get(f"/api/jobs/{job.pk}/photos/{theirs['id']}/file/").status_code == 404
        assert (
            client.patch(
                f"/api/jobs/{job.pk}/photos/{theirs['id']}/", {"base_version": 1, "caption": "x"}, format="json"
            ).status_code
            == 404
        )
        assert client.delete(f"/api/jobs/{job.pk}/photos/{theirs['id']}/").status_code == 404
        assert Photo.objects.get(pk=theirs["id"]).caption == ""

    @pytest.mark.parametrize("status", [JobStatus.PEER_REVIEW, JobStatus.APPROVED_SIGNED])
    def test_nothing_changes_while_the_job_is_with_the_reviewer_or_signed_off(self, job, dan, status):
        created = add_photos(dan, job)[0]
        Job.objects.filter(pk=job.pk).update(status=status)
        client = client_for(dan)
        res = post_files(dan, job, "photos", [photo("late.jpg", 5)])
        assert res.status_code == 409 and res.json()["code"] == "frozen"
        base = f"/api/jobs/{job.pk}/photos/{created['id']}/"
        assert client.patch(base, {"base_version": 1, "caption": "x"}, format="json").status_code == 409
        assert client.delete(base).status_code == 409
        assert (
            client.post(f"/api/jobs/{job.pk}/photos/reorder/", {"ids": [created["id"]]}, format="json").status_code
            == 409
        )
        assert Photo.objects.count() == 1 and Photo.objects.get().caption == ""

    def test_an_issued_job_is_locked(self, job, dan):
        created = add_photos(dan, job)[0]
        Job.objects.filter(pk=job.pk).update(is_locked=True, status=JobStatus.ISSUED)
        assert post_files(dan, job, "photos", [photo("late.jpg", 5)]).json()["code"] == "locked"
        assert client_for(dan).delete(f"/api/jobs/{job.pk}/photos/{created['id']}/").status_code == 409
        assert (
            client_for(dan).get(f"/api/jobs/{job.pk}/photos/{created['id']}/file/").status_code == 200
        )  # still viewable

    def test_the_list_says_why_when_it_is_read_only(self, job, pat):
        body = client_for(pat).get(f"/api/jobs/{job.pk}/photos/").json()
        assert body["can_edit"] is False and "doesn't allow" in body["read_only_reason"]


# --- changing, ordering, removing --------------------------------------------------------------


class TestChanging:
    def patch(self, user, job, item, **body):
        return client_for(user).patch(f"/api/jobs/{job.pk}/photos/{item['id']}/", body, format="json")

    def test_a_caption_is_saved_and_the_version_moves(self, job, dan):
        item = add_photos(dan, job)[0]
        res = self.patch(dan, job, item, base_version=1, caption="  Living room  ")
        assert res.status_code == 200 and res.json()["caption"] == "Living room" and res.json()["edit_version"] == 2

    def test_the_first_edit_wins(self, job, dan, boss):
        item = add_photos(dan, job)[0]
        assert self.patch(dan, job, item, base_version=1, caption="Dan's").status_code == 200
        late = self.patch(boss, job, item, base_version=1, caption="Boss's")
        assert late.status_code == 409 and late.json()["code"] == "conflict"
        assert late.json()["current"]["caption"] == "Dan's"
        assert Photo.objects.get(pk=item["id"]).caption == "Dan's"

    def test_bad_input_is_refused_and_applies_nothing(self, job, dan):
        item = add_photos(dan, job)[0]
        for body in (
            {"base_version": 1, "caption": "x" * 300},
            {"base_version": 1, "caption": 5},
            {"base_version": 1, "include_in_report": "yes"},
            {"base_version": 1, "slot": "roof"},
            {"base_version": 1, "s3_key": "jobs/other/x.jpg"},
            {"base_version": 1, "order": 99},
            {"caption": "no version"},
        ):
            assert self.patch(dan, job, item, **body).status_code == 400, body
        stored = Photo.objects.get(pk=item["id"])
        assert (stored.caption, stored.order, stored.edit_version) == ("", 1, 1)

    def test_a_photo_can_be_left_out_of_the_report(self, job, dan):
        item = add_photos(dan, job)[0]
        assert self.patch(dan, job, item, base_version=1, include_in_report=False).json()["include_in_report"] is False

    def test_reordering_sets_the_order(self, job, dan):
        a, b, c = add_photos(dan, job, 3)
        res = client_for(dan).post(
            f"/api/jobs/{job.pk}/photos/reorder/", {"ids": [c["id"], a["id"], b["id"]]}, format="json"
        )
        assert [(p["id"], p["order"]) for p in res.json()] == [(c["id"], 1), (a["id"], 2), (b["id"], 3)]
        listed = client_for(dan).get(f"/api/jobs/{job.pk}/photos/").json()["items"]
        assert [p["id"] for p in listed] == [c["id"], a["id"], b["id"]]

    def test_a_stale_order_is_refused_if_the_list_changed(self, job, dan):
        a, b = add_photos(dan, job, 2)
        add_photos(dan, job, 1, start=10)  # someone added one meanwhile
        res = client_for(dan).post(f"/api/jobs/{job.pk}/photos/reorder/", {"ids": [b["id"], a["id"]]}, format="json")
        assert res.status_code == 409 and len(res.json()["current"]) == 3
        assert [p.order for p in Photo.objects.filter(pk__in=[a["id"], b["id"]]).order_by("pk")] == [1, 2]

    def test_a_malformed_order_is_refused(self, job, dan):
        a, b = add_photos(dan, job, 2)
        for ids in ("nope", [a["id"], a["id"]], [a["id"], "x"], None):
            res = client_for(dan).post(f"/api/jobs/{job.pk}/photos/reorder/", {"ids": ids}, format="json")
            assert res.status_code in (400, 409), ids

    def test_removing_hides_it_but_keeps_the_file(self, job, dan, settings):
        item = add_photos(dan, job)[0]
        stored = Photo.objects.get(pk=item["id"])
        assert client_for(dan).delete(f"/api/jobs/{job.pk}/photos/{item['id']}/").status_code == 204
        assert client_for(dan).get(f"/api/jobs/{job.pk}/photos/").json()["items"] == []
        assert client_for(dan).get(f"/api/jobs/{job.pk}/photos/{item['id']}/file/").status_code == 404
        assert (settings.MEDIA_ROOT / stored.s3_key).exists()
        row = Photo.all_objects.get(pk=item["id"])
        assert row.deleted_at and row.deleted_by == dan

    def test_changes_are_audited_without_the_version_counter(self, job, dan):
        item = add_photos(dan, job)[0]
        self.patch(dan, job, item, base_version=1, caption="Kitchen")
        client_for(dan).delete(f"/api/jobs/{job.pk}/photos/{item['id']}/")
        logged = AuditLog.objects.filter(model_name="Photo", object_id=str(item["id"]))
        assert {"caption", "deleted_at"} <= set(logged.values_list("field_name", flat=True))
        assert "edit_version" not in set(logged.values_list("field_name", flat=True))
        assert logged.get(field_name="caption").changed_by == dan and logged.get(field_name="caption").job == job


# --- the files themselves ---------------------------------------------------------------------


class TestServingFiles:
    def test_a_photo_and_its_thumbnail_are_served_as_jpeg(self, job, dan):
        item = add_photos(dan, job)[0]
        client = client_for(dan)
        full = client.get(item["url"])
        thumb = client.get(item["thumb_url"])
        assert full.status_code == 200 and full["Content-Type"] == "image/jpeg"
        assert thumb["Content-Type"] == "image/jpeg"
        assert full["X-Content-Type-Options"] == "nosniff" and "private" in full["Cache-Control"]
        assert b"".join(full.streaming_content).startswith(b"\xff\xd8\xff")

    def test_a_pdf_is_served_as_the_pdf_that_was_uploaded(self, job, boss):
        data = pdf_bytes(2)
        item = post_files(boss, job, "documents", [upload_file("deed.pdf", data)]).json()["created"][0]
        res = client_for(boss).get(item["url"])
        assert res["Content-Type"] == "application/pdf" and b"".join(res.streaming_content) == data
        assert 'filename="deed.pdf"' in res["Content-Disposition"]

    def test_a_phone_photo_downloads_with_a_jpg_name(self, job, dan):
        item = post_files(dan, job, "photos", [upload_file("IMG_0001.HEIC", jpeg_bytes(3))]).json()["created"][0]
        assert 'filename="IMG_0001.jpg"' in client_for(dan).get(item["url"])["Content-Disposition"]


# --- what the job needs ---------------------------------------------------------------------


def set_inspection(job, kind):
    job.inspection.inspection_type = kind
    job.inspection.save()


class TestRequirements:
    def blockers(self, job):
        return media_blockers(Job.objects.get(pk=job.pk))

    def test_a_full_inspection_needs_three_general_photographs_and_a_document(self, job, dan, boss):
        set_inspection(job, "full")
        assert len(self.blockers(job)) == 2
        add_photos(dan, job, 2)
        assert any("2 so far" in b for b in self.blockers(job))
        add_photos(dan, job, 1, start=10)
        post_files(boss, job, "documents", [upload_file("d.pdf", pdf_bytes())])
        assert self.blockers(job) == []

    def test_photos_left_out_of_the_report_do_not_count(self, job, dan, boss):
        set_inspection(job, "full")
        attach_media(job, boss)
        assert self.blockers(job) == []
        first = Photo.objects.filter(job=job).first()
        client_for(dan).patch(
            f"/api/jobs/{job.pk}/photos/{first.pk}/", {"base_version": 1, "include_in_report": False}, format="json"
        )
        assert any("2 so far" in b for b in self.blockers(job))

    def test_a_desktop_valuation_needs_no_photographs(self, job, boss):
        set_inspection(job, "desktop")
        post_files(boss, job, "documents", [upload_file("d.pdf", pdf_bytes())])
        assert self.blockers(job) == []

    def test_a_drive_by_needs_one(self, job, boss, dan):
        set_inspection(job, "drive_by")
        post_files(boss, job, "documents", [upload_file("d.pdf", pdf_bytes())])
        assert any("At least 1" in b for b in self.blockers(job))
        add_photos(dan, job)
        assert self.blockers(job) == []

    def test_a_bank_can_require_the_makani_and_dewa_photographs(self, job, dan, boss):
        job.bank.rules = {"requires_makani_photo": True, "requires_dewa_photo": True}
        job.bank.save()
        set_inspection(job, "full")
        attach_media(job, boss)
        needs = self.blockers(job)
        assert any("Makani" in b and "Test Bank" in b for b in needs) and any("DEWA" in b for b in needs)
        post_files(dan, job, "photos", [photo("m.jpg", 40)], slot="makani")
        post_files(dan, job, "photos", [photo("d.jpg", 41)], slot="dewa")
        assert self.blockers(job) == []

    def test_a_makani_photo_does_not_count_towards_the_three_general_ones(self, job, dan, boss):
        set_inspection(job, "full")
        post_files(boss, job, "documents", [upload_file("d.pdf", pdf_bytes())])
        add_photos(dan, job, 2)
        post_files(dan, job, "photos", [photo("m.jpg", 40)], slot="makani")
        assert any("2 so far" in b for b in self.blockers(job))

    def test_saying_a_photo_was_taken_on_the_checklist_means_it_must_be_there(self, job, boss):
        set_inspection(job, "desktop")
        post_files(boss, job, "documents", [upload_file("d.pdf", pdf_bytes())])
        job.checklist.makani_photo = True
        job.checklist.save()
        assert any("Makani" in b and "Check List" in b for b in self.blockers(job))

    def test_the_tabs_show_progress_and_what_is_missing(self, job, dan):
        set_inspection(job, "full")
        add_photos(dan, job, 1)
        tabs = client_for(dan).get(f"/api/jobs/{job.pk}/").json()["tabs"]
        assert tabs["photos"]["completion"]["pct"] == 0 and tabs["photos"]["completion"]["missing"]
        assert tabs["documents"]["completion"]["pct"] == 0
        assert tabs["photos"]["can_edit"] is True

    def test_missing_files_on_disk_are_noticed(self, job, dan, settings):
        item = add_photos(dan, job)[0]
        (settings.MEDIA_ROOT / Photo.objects.get(pk=item["id"]).s3_key).unlink()
        assert missing_files(Job.objects.get(pk=job.pk)) == ["p1.jpg"]

    def test_sending_for_review_waits_for_them(self, job, dan, boss):
        from apps.jobs.tests.test_transitions import fill_everything

        fill_everything(job)
        Photo.objects.filter(job=job).delete()  # (soft)
        Job.objects.filter(pk=job.pk).update(status=JobStatus.VALUATION_IN_PROGRESS)
        res = client_for(dan).get(f"/api/jobs/{job.pk}/")
        review = next(a for a in res.json()["available_actions"] if a["to"] == "peer_review")
        assert review["enabled"] is False and any(b.startswith("Photos:") for b in review["blockers"])


# --- revisions and reports --------------------------------------------------------------------


class TestRevisions:
    def test_a_revision_carries_the_media_over_pointing_at_the_same_files(self, job, dan, boss):
        attach_media(job, boss)
        job.refresh_from_db()
        Job.objects.filter(pk=job.pk).update(is_locked=True, status=JobStatus.ISSUED)
        revision = Job.objects.get(pk=job.pk).create_revision(by=boss)
        assert revision.photos.count() == 3 and revision.documents.count() == 1
        assert {p.s3_key for p in revision.photos.all()} == {p.s3_key for p in job.photos.all()}

    def test_removing_it_from_the_revision_leaves_the_issued_version_alone(self, job, dan, boss, settings):
        attach_media(job, boss)
        Job.objects.filter(pk=job.pk).update(is_locked=True, status=JobStatus.ISSUED)
        revision = Job.objects.get(pk=job.pk).create_revision(by=boss)
        victim = revision.photos.first()
        service.remove(revision.pk, boss, service.PHOTOS, victim.pk)
        assert job.photos.count() == 3 and revision.photos.count() == 2
        assert (settings.MEDIA_ROOT / victim.s3_key).exists()


def test_document_types_are_the_admins_presets(job, boss):
    from apps.presets.models import PresetOption

    PresetOption.objects.create(field_key="document_type", label="Trade Licence")
    res = client_for(boss).get(f"/api/jobs/{job.pk}/documents/")
    offered = {o["value"]: o["label"] for o in res.json()["doc_types"]}
    assert offered["trade_licence"] == "Trade Licence" and offered["title_deed"] == "Title Deed"
    assert (
        post_files(boss, job, "documents", [upload_file("t.pdf", pdf_bytes())], doc_type="trade_licence").status_code
        == 201
    )
    assert Document.objects.get().doc_type == "trade_licence"
