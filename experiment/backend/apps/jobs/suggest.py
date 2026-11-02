"""Report text ticked for the valuer from what the job already says (report
text inputs, Oct 2026). The valuer can untick or edit anything; nothing is
ticked twice, and a condition or specification already chosen is left alone.

  Inspection Type Desktop  -> Assumption "Desktop Valuation", Condition
                              "Desktop Standard Property - Good Condition",
                              Specification "Desktop Standard Property" (or
                              the desktop shell & core / fitted office one)
  Inspection Type Drive-By -> Assumption "Drive By/External Inspection"
  Inspection Type Previous -> Condition and Specification "Previous Inspection"
  Interest Valued Granted  -> Special Assumption "Granted"
"""

from __future__ import annotations

from apps.presets.models import TextLibraryItem

from .models import JobTabVersion

# The desktop specification follows the property type.
DESKTOP_SPEC = "desktop specification"
DESKTOP_SPECS = {
    "shell_core_office": "Desktop Shell and Core Office", "shell_core_retail": "Desktop Shell and Core Office",
    "fitted_office": "Desktop Fitted Office/Retail", "fitted_retail": "Desktop Fitted Office/Retail",
}

RULES = {
    ("inspection_type", "desktop"): [
        ("assumption", "Desktop Valuation"),
        ("condition", "Desktop Standard Property - Good Condition"),
        ("specification", DESKTOP_SPEC),
    ],
    ("inspection_type", "drive_by"): [("assumption", "Drive By/External Inspection")],
    ("inspection_type", "previous_inspection"): [
        ("condition", "Previous Inspection"),
        ("specification", "Previous Inspection"),
    ],
    ("interest_valued", "gcc_freehold_granted"): [("special_assumption", "Granted")],
}


def _text(category: str, title: str) -> str | None:
    item = TextLibraryItem.objects.filter(category=category, title=title, active=True).first()
    return item.body if item else None


def _tagged_text(category: str, property_category: str) -> str:
    """The library entry written for this property type; none if no entry is
    tagged with it (an untagged one isn't specific enough to fill in)."""
    for item in TextLibraryItem.objects.filter(category=category, active=True).exclude(body=""):
        if property_category in (item.property_categories or []):
            return item.body
    return ""


def _is_library_wording(category: str, text: str) -> bool:
    """True when `text` is one of the library's entries, unedited."""
    return any(body.strip() == text for body in TextLibraryItem.objects.filter(category=category, active=True)
               .values_list("body", flat=True))


def _bump(job, tab_key: str, saved_tab: str) -> None:
    """Another tab changed under the user: its version moves on so a stale
    screen reloads instead of overwriting it. The tab being saved moves on
    by itself."""
    if tab_key == saved_tab:
        return
    version, _ = JobTabVersion.objects.get_or_create(job=job, tab_key=tab_key)
    version.version += 1
    version.save(update_fields=["version"])


def apply(job, saved_tab: str, cleaned: dict) -> None:
    """After a save: tick what the new Inspection Type or Interest Valued implies."""
    changed: set[str] = set()
    for (key, value), ticks in RULES.items():
        if key not in cleaned or cleaned[key][2] != value:
            continue
        summary, location = job.summary, job.location
        for category, title in ticks:
            if title == DESKTOP_SPEC:
                title = DESKTOP_SPECS.get(summary.property_category, "Desktop Standard Property")
            body = _text(category, title)
            if body is None:
                continue
            if category in ("assumption", "special_assumption"):
                field = "assumptions" if category == "assumption" else "special_assumptions"
                entries = list(getattr(summary, field) or [])
                if any(isinstance(e, dict) and e.get("title") == title for e in entries):
                    continue
                setattr(summary, field, [*entries, {"title": title, "body": body}])
                setattr(summary, "has_" + field, True)
                summary.save()
                changed.add("summary")
            else:
                field = "property_condition" if category == "condition" else "property_specification"
                if (getattr(location, field) or "").strip():
                    continue
                setattr(location, field, body)
                location.save()
                changed.add("location")
    if "property_category" in cleaned and cleaned["property_category"][2]:
        from apps.reports.context import library_text

        category = cleaned["property_category"][2]
        valuation = job.valuation
        if not (valuation.reinstatement_note or "").strip():
            if text := library_text("reinstatement", category):
                valuation.reinstatement_note = text
                valuation.save()
                changed.add("valuation")
        # The commentary for the property type (QA #16): filled in when the box
        # is empty, or still holds another type's library wording unedited.
        boxes = (("valuation", valuation, "valuation_commentary", "valuation_commentary"),
                 ("summary", job.summary, "market_commentary", "market_commentary"))
        for tab_key, target, field, library in boxes:
            current = (getattr(target, field) or "").strip()
            text = _tagged_text(library, category)
            if not text or current == text.strip():
                continue
            if current and not _is_library_wording(library, current):
                continue  # written for this job: leave it
            setattr(target, field, text)
            target.save()
            changed.add(tab_key)
    for tab_key in changed:
        _bump(job, tab_key, saved_tab)
