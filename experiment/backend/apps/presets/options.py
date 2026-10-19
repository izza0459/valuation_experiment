"""Where a select/multiselect field's choices come from.

Most option lists are admin-editable `PresetOption` rows keyed by the
field config's `options_key` (CLAUDE.md §4). Two keys are not presets
because the choices are other records: `bank` (the Bank master) and
`report_template`. User fields are served alongside as `users`.

A single resolver feeds both the options endpoint the form renders from
and the server-side validation of submitted values, so what a dropdown
offers and what the API accepts can't drift apart.
"""

from django.contrib.auth import get_user_model

from apps.banks.models import Bank
from apps.reports.models import ReportTemplate

from .models import PresetOption, TextLibraryItem

RECORD_KEYS = {"bank", "report_template"}

# `library` fields (report text the valuer picks from, then edits per job)
# draw on the text library. Keys that name a category differently from the
# field config are mapped here.
LIBRARY_CATEGORIES = {
    "assumption": "assumption",
    "special_assumption": "special_assumption",
    "other_matter": "other_matter",
    "commentary": "commentary",
    "market_commentary": "market_commentary",
    "valuation_commentary": "valuation_commentary",
    "property_specification": "specification",
    "property_condition": "condition",
}


def preset_options(options_key: str, *, free_text: bool = False) -> list[dict]:
    rows = PresetOption.objects.filter(field_key=options_key, active=True)
    # Free-text fields (community, emirate) store what is shown, not a slug:
    # the master list is "later" (CLAUDE.md §4) and report text uses it verbatim.
    return [
        {"value": r.label if free_text else r.value, "label": r.label, "report_text": r.report_text}
        for r in rows
    ]


def record_options(options_key: str) -> list[dict]:
    if options_key == "bank":
        # `code`: the bank's own code, which fills the Bank Reference No.
        return [{"value": b.pk, "label": b.name, "report_text": "", "code": b.code}
                for b in Bank.objects.filter(active=True)]
    if options_key == "report_template":
        return [
            {"value": t.pk, "label": str(t), "report_text": ""}
            for t in ReportTemplate.objects.filter(active=True)
        ]
    raise KeyError(options_key)


def library_options(options_key: str) -> list[dict]:
    """Picker entries for a library field: text-library items for its
    category, plus any presets keyed to it (per-community text lives there)."""
    options = []
    category = LIBRARY_CATEGORIES.get(options_key)
    if category:
        # `categories`: the property categories an entry is offered for
        # (empty = all), so apartment commentary is offered for apartments.
        options += [
            {"value": f"lib-{i.pk}", "label": i.title, "report_text": i.body,
             "categories": list(i.property_categories or [])}
            for i in TextLibraryItem.objects.filter(category=category, active=True)
        ]
    return options + preset_options(options_key)


def options_for(options_key: str, *, free_text: bool = False) -> list[dict]:
    if options_key in LIBRARY_CATEGORIES or options_key in {"sub_community", "location", "disclosure"}:
        return library_options(options_key)
    if options_key in RECORD_KEYS:
        return record_options(options_key)
    return preset_options(options_key, free_text=free_text)


def user_options() -> list[dict]:
    User = get_user_model()
    return [
        {"value": u.pk, "label": str(u), "roles": list(u.roles or [])}
        for u in User.objects.filter(is_active=True).order_by("first_name", "email")
    ]
