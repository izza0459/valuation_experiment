"""Report text ticked for the valuer from what the job already says (report
text inputs, Oct 2026). The valuer can untick or edit anything; nothing is
ticked twice, and a condition or specification already chosen is left alone.

  Inspection Type Desktop  -> Assumption "Desktop Valuation", Condition
                              "Desktop Standard Property - Good Condition",
                              Specification "Desktop Standard Property"
  Inspection Type Drive-By -> Assumption "Drive By/External Inspection"
  Inspection Type Previous -> Condition and Specification "Previous Inspection"
  Interest Valued Granted  -> Special Assumption "Granted"
"""

from __future__ import annotations

from apps.presets.models import TextLibraryItem

from .models import JobTabVersion

RULES = {
    ("inspection_type", "desktop"): [
        ("assumption", "Desktop Valuation"),
        ("condition", "Desktop Standard Property - Good Condition"),
        ("specification", "Desktop Standard Property"),
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
    for tab_key in changed:
        _bump(job, tab_key, saved_tab)
