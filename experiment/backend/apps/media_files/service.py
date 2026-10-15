"""Storing, changing, ordering and removing a job's photographs and documents.

Every change re-checks who may make it, and that the job still allows it, while
holding a lock on the job row: the checks made before the slow image work can
go stale while it runs (the job may have gone to review in the meantime).

The files are processed and written first and the database rows second, inside
one transaction; if the rows can't be written the files are removed again.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max

from apps.audit.middleware import acting_as
from apps.jobs.models import Job
from apps.jobs.tabs import ValidationFailed, VersionConflict, edit_denial
from apps.presets.options import options_for

from . import processing
from .models import Document, Photo

FILES_PER_REQUEST = 20
CAPTION_MAX = 255


@dataclass(frozen=True)
class Kind:
    name: str  # URL segment and tab key
    model: type
    max_items: int
    accepts: frozenset
    noun: str


PHOTOS = Kind("photos", Photo, 80, frozenset({"jpeg", "png", "heic"}), "photograph")
DOCUMENTS = Kind("documents", Document, 40, frozenset({"jpeg", "png", "heic", "pdf"}), "document")
KINDS = {k.name: k for k in (PHOTOS, DOCUMENTS)}

KIND_NAMES = {"jpeg": "JPG", "png": "PNG", "heic": "HEIC", "pdf": "PDF"}


def accepted_text(kind: Kind) -> str:
    return ", ".join(KIND_NAMES[k] for k in ("jpeg", "png", "heic", "pdf") if k in kind.accepts)


@dataclass
class UploadResult:
    created: list = field(default_factory=list)
    rejected: list = field(default_factory=list)  # [{"name", "reason"}]


def _require_edit(user, job, kind):
    if denial := edit_denial(user, job, kind.name):
        raise denial


def _safe_name(name: str) -> str:
    cleaned = "".join(ch for ch in (name or "") if ch.isprintable() and ch not in '/\\\x00')
    return cleaned.strip()[:255]


def document_types() -> list[str]:
    return [o["value"] for o in options_for("document_type")]


def valid_doc_type(value) -> bool:
    """One of the admin's `document_type` presets. Before any are seeded, any
    plain slug is accepted so uploading isn't blocked on setup."""
    if not isinstance(value, str):
        return False
    known = document_types()
    return value in known if known else bool(re.fullmatch(r"[a-z0-9_]{1,60}", value))


# --- uploading -----------------------------------------------------------------


def _prepare(kind: Kind, uploaded) -> dict:
    """Validates and processes one upload. Raises `Rejected` with a reason."""
    if uploaded.size > processing.MAX_BYTES:
        raise processing.Rejected(f"The file is larger than {processing.MAX_BYTES // (1024 * 1024)} MB.")
    if uploaded.size == 0:
        raise processing.Rejected("The file is empty.")
    data = uploaded.read(processing.MAX_BYTES + 1)
    found = processing.sniff(data[:16])
    if found not in kind.accepts:
        raise processing.Rejected(f"Only {accepted_text(kind)} files can be added here.")

    base = {"sha256": hashlib.sha256(data).hexdigest(), "original_name": _safe_name(uploaded.name), "size": len(data)}
    if found == "pdf":
        pdf = processing.process_pdf(data)
        return {**base, "main": data, "ext": "pdf", "content_type": "application/pdf", "thumb": pdf.thumb,
                "page_count": pdf.page_count}
    image = processing.process_image(data)
    return {**base, "main": image.main, "ext": "jpg", "content_type": "image/jpeg", "thumb": image.thumb,
            "width": image.width, "height": image.height, "page_count": 1, "size": len(image.main)}


def _write(job, kind: Kind, prepared: dict) -> tuple[str, str]:
    stem = uuid.uuid4().hex
    base = f"jobs/{job.bayut_internal_reference_no}/{kind.name}"
    key = default_storage.save(f"{base}/{stem}.{prepared['ext']}", ContentFile(prepared["main"]))
    try:
        thumb_key = default_storage.save(f"{base}/thumbs/{stem}.jpg", ContentFile(prepared["thumb"]))
    except Exception:
        default_storage.delete(key)
        raise
    return key, thumb_key


def upload(
    job_id: int, user, kind: Kind, files, *, slot: str | None = None, doc_type: str | None = None
) -> UploadResult:
    """Adds every acceptable file; the rest come back with a reason each, so
    one bad scan doesn't lose a dozen good photographs."""
    result = UploadResult()
    if slot is not None and slot not in Photo.Slot.values:
        raise ValidationFailed({"slot": "Unknown photograph type."})
    if doc_type is not None and not valid_doc_type(doc_type):
        raise ValidationFailed({"doc_type": "Unknown document type."})

    job = Job.objects.get(pk=job_id)
    _require_edit(user, job, kind)  # fail before spending time on the images

    prepared, written = [], []
    seen = set()
    for uploaded in files[:FILES_PER_REQUEST]:
        name = _safe_name(uploaded.name) or "file"
        try:
            item = _prepare(kind, uploaded)
        except processing.Rejected as exc:
            result.rejected.append({"name": name, "reason": str(exc)})
            continue
        if item["sha256"] in seen:
            result.rejected.append({"name": name, "reason": "This file is in the same upload twice."})
            continue
        seen.add(item["sha256"])
        prepared.append(item)
    for uploaded in files[FILES_PER_REQUEST:]:
        result.rejected.append(
            {"name": _safe_name(uploaded.name) or "file", "reason": f"Up to {FILES_PER_REQUEST} files at a time."}
        )

    if not prepared:
        return result

    try:
        with acting_as(user), transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job_id)
            _require_edit(user, job, kind)  # the job may have moved while we worked

            live = kind.model.objects.filter(job=job)
            existing_hashes = set(live.values_list("sha256", flat=True))
            room = kind.max_items - live.count()
            next_order = (live.aggregate(m=Max("order"))["m"] or 0) + 1

            for item in prepared:
                name = item["original_name"] or "file"
                if item["sha256"] in existing_hashes:
                    result.rejected.append({"name": name, "reason": "This file has already been added to the job."})
                    continue
                if room <= 0:
                    result.rejected.append(
                        {"name": name, "reason": f"A job can hold at most {kind.max_items} {kind.noun}s."}
                    )
                    continue
                key, thumb_key = _write(job, kind, item)
                written += [key, thumb_key]
                fields = dict(
                    job=job, s3_key=key, thumb_key=thumb_key, original_name=item["original_name"],
                    content_type=item["content_type"], size_bytes=item["size"], sha256=item["sha256"],
                    order=next_order, uploaded_by=user,
                )
                if kind is PHOTOS:
                    fields.update(
                        slot=slot or Photo.Slot.GENERAL, width=item.get("width", 0), height=item.get("height", 0)
                    )
                else:
                    fields.update(doc_type=doc_type or "other", page_count=item["page_count"])
                result.created.append(kind.model.objects.create(**fields))
                existing_hashes.add(item["sha256"])
                next_order += 1
                room -= 1
    except Exception:
        for key in written:
            default_storage.delete(key)
        raise
    return result


# --- changing -------------------------------------------------------------------


def _locked(job_id, user, kind, item_id):
    job = Job.objects.select_for_update().get(pk=job_id)
    _require_edit(user, job, kind)
    try:
        item = kind.model.objects.select_for_update().get(pk=item_id, job=job)
    except kind.model.DoesNotExist:
        raise LookupError("No such item.") from None
    return job, item


def update(job_id: int, user, kind: Kind, item_id: int, base_version, changes: dict):
    """Edits caption, inclusion, and (photos) type or (documents) document type.

    `base_version` is the `edit_version` the caller was looking at: if someone
    saved first, nothing is applied and the current state comes back (first edit wins)."""
    errors = {}
    allowed = {"caption", "include_in_report"} | ({"slot"} if kind is PHOTOS else {"doc_type"})
    for key in changes:
        if key not in allowed:
            errors[key] = "This can't be changed."
    if "caption" in changes and (not isinstance(changes["caption"], str) or len(changes["caption"]) > CAPTION_MAX):
        errors["caption"] = f"Must be text of at most {CAPTION_MAX} characters."
    if "include_in_report" in changes and not isinstance(changes["include_in_report"], bool):
        errors["include_in_report"] = "Must be true or false."
    if "slot" in changes and changes["slot"] not in Photo.Slot.values:
        errors["slot"] = "Unknown photograph type."
    if "doc_type" in changes and not valid_doc_type(changes["doc_type"]):
        errors["doc_type"] = "Unknown document type."
    if not isinstance(base_version, int) or isinstance(base_version, bool):
        errors["base_version"] = "Required."
    if errors:
        raise ValidationFailed(errors)

    with acting_as(user), transaction.atomic():
        _, item = _locked(job_id, user, kind, item_id)
        if item.edit_version != base_version:
            raise VersionConflict("Someone else changed this first.", current=item)
        for key, value in changes.items():
            setattr(item, key, value.strip() if isinstance(value, str) else value)
        item.edit_version += 1
        item.save()
    return item


def remove(job_id: int, user, kind: Kind, item_id: int):
    """Hides the item. The file stays in storage: reports already issued, and
    revisions, may still point at it."""
    with acting_as(user), transaction.atomic():
        _, item = _locked(job_id, user, kind, item_id)
        item.delete(by=user)


def reorder(job_id: int, user, kind: Kind, ids) -> list:
    """Sets the display order. `ids` must be exactly the job's current items:
    if one was added or removed meanwhile, nothing changes and the caller
    reloads (first edit wins)."""
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ValidationFailed({"ids": "Must be a list of ids."})
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        _require_edit(user, job, kind)
        items = list(kind.model.objects.filter(job=job))
        if sorted(ids) != sorted(i.pk for i in items) or len(set(ids)) != len(ids):
            raise VersionConflict("The list changed since you loaded it.", current=None)
        by_id = {i.pk: i for i in items}
        for position, pk in enumerate(ids, start=1):
            item = by_id[pk]
            if item.order != position:
                item.order = position
                item.save(update_fields=["order"])
        return [by_id[pk] for pk in ids]
