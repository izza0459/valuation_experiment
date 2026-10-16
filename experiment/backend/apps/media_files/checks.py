"""What a job needs in the way of photographs and documents.

One place, used three ways: the Photos/Documents tabs show what is still
needed, sending for review is blocked until it is in, and the draft report
lists it as outstanding."""

from __future__ import annotations

from django.core.files.storage import default_storage

# The executive summary shows three photographs (CLAUDE.md §5).
EXEC_SUMMARY_PHOTOS = 3

LABELS = {"photos": "Photos", "documents": "Documents"}


def exec_summary_photos(job) -> list:
    """The photographs that go on the executive summary: the first three
    general ones, in the order the valuer set."""
    return [p for p in job.photos.all() if p.include_in_report and p.slot == "general"][:EXEC_SUMMARY_PHOTOS]


def requirements(job, tab_key: str) -> list[tuple[str, bool]]:
    """(what is needed, whether it is in) for one media tab."""
    if tab_key == "photos":
        return _photo_requirements(job)
    if tab_key == "documents":
        has_any = any(d.include_in_report for d in job.documents.all())
        return [("Attach at least one document (for example the title deed) and include it in the report", has_any)]
    return []


def _photo_requirements(job) -> list[tuple[str, bool]]:
    included = [p for p in job.photos.all() if p.include_in_report]
    general = [p for p in included if p.slot == "general"]
    inspection_type = job.inspection.inspection_type
    rules = job.bank.rules or {}
    needs = []

    # A site visit produces photographs; a desktop valuation has none to show.
    if inspection_type == "full":
        needs.append(
            (
                f"At least {EXEC_SUMMARY_PHOTOS} general photographs included in the report ({len(general)} so far)",
                len(general) >= EXEC_SUMMARY_PHOTOS,
            )
        )
    elif inspection_type in ("drive_by", "external_inspection"):
        needs.append((f"At least 1 general photograph included in the report ({len(general)} so far)", bool(general)))

    for slot, name, rule, checklist_flag in (
        ("makani", "Makani", "requires_makani_photo", "makani_photo"),
        ("dewa", "DEWA", "requires_dewa_photo", "dewa_photo"),
    ):
        have = any(p.slot == slot for p in included)
        if rules.get(rule) and inspection_type == "full":
            needs.append((f"A {name} number photograph (required by {job.bank.name})", have))
        elif getattr(job.checklist, checklist_flag):
            needs.append((f"A {name} number photograph (the Check List says one was taken)", have))
    return needs


def media_blockers(job) -> list[str]:
    """What is still needed before review, worded for the blocker list."""
    return [
        f"{LABELS[tab]}: {label}"
        for tab in ("photos", "documents")
        for label, met in requirements(job, tab)
        if not met
    ]


def missing_files(job) -> list[str]:
    """Included photographs and documents whose stored file has gone missing.
    A report must never be issued with a hole where an image should be."""
    gone = []
    for item in [*job.photos.filter(include_in_report=True), *job.documents.filter(include_in_report=True)]:
        if not default_storage.exists(item.s3_key):
            gone.append(item.original_name or item.s3_key)
    return gone
