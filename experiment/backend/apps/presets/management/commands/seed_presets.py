"""Seeds the dropdown option lists and text library from CLAUDE.md §4.

Idempotent and non-destructive: rows are created only if missing, so an
admin's edits and deactivations survive a re-run.

The text-library bodies are PLACEHOLDERS. CLAUDE.md §11: our own
assumptions/T&C/disclaimer wording isn't available yet, and the report must
never carry another firm's text. Each body starts with a marker so a
placeholder can't be mistaken for approved wording on a signed report.
"""

from django.core.management.base import BaseCommand

from apps.presets.models import PresetOption, TextLibraryItem

PLACEHOLDER = "[PLACEHOLDER – replace with approved wording] "

# Lists the field dictionary doesn't cover. The ones it does cover are
# created by migration presets.0004 (apps.presets.dictionary).
PRESETS = {
    "community": [
        "Downtown Dubai", "Dubai Marina", "Jumeirah Village Circle (JVC)", "Business Bay", "Palm Jumeirah",
        "Dubai Hills Estate", "Arabian Ranches", "Jumeirah Lake Towers (JLT)", "DIFC", "Dubai Sports City",
        "Dubailand", "Dubai Silicon Oasis", "Dubai South", "Meydan", "Al Barsha",
    ],
    # What an uploaded document is (Tab 8). Slugs of these are stored on the document.
    "document_type": [
        "Title Deed", "SPA", "Site Plan", "Site Affection Plan", "Floor Plan", "Developer's Floor Plan",
        "Tenancy Contract", "Ownership Certificate", "NOC", "Bank instruction", "Other",
    ],
    "capacity_of_valuer": ["External", "Internal"],
    "occupancy_title": [
        "Ground", "1st", "2nd", "3rd", "4th", "5th", "Mezzanine", "Basement", "Podium", "Upper level",
        "Lower level", "Outbuilding",
    ],
}

# Options that carry report text: field key -> [(label, report_text)]. The
# disclosure statements are the field dictionary's three, as written.
PRESET_TEXT = {
    "disclosure": [
        ("Existing relationship; not previously valued",
         "The Signatory to this Valuation Report confirms that they have an existing relationship with the "
         "Client and that they have not previously valued the subject property."),
        ("No existing relationship; previously valued",
         "The Signatory to this Valuation Report confirms that they do not have an existing relationship with "
         "the Client and that they have previously valued the subject property."),
        ("Existing relationship; previously valued",
         "The Signatory to this Valuation Report confirms that they have an existing relationship with the "
         "Client and that they have previously valued the subject property."),
    ],
}

# category -> titles (CLAUDE.md §4). Bodies are placeholders; see module docstring.
# Specification, condition and commentary come from the field dictionary.
LIBRARY = {
    "special_assumption": [
        "Granted title converted to freehold", "Hotel apartment rental-pool restriction", "Assumed UAE Freehold",
        "Compound limited access", "Extension/modification permission assumed", "No NOC / assumed NOC",
        "Satellite imagery",
    ],
    # The former "Other Matters" library, now offered under Assumptions.
    "assumption": [
        "Title deed size error", "Wrong plot size", "Wrong floor plans", "Structural damage", "Sharjah properties",
        "Sample unit inspection", "Road noise", "Payment plan", "Phone mast", "Restricted freehold",
        "Drive-by/desktop assumed good condition", "Exaggerated BUA", "Illegal modifications",
        "Under-construction phase notes", "Vacant & furnished",
    ],
}


class Command(BaseCommand):
    help = "Seed dropdown presets and placeholder text-library entries (idempotent)."

    def handle(self, *args, **options):
        made_presets = made_items = 0
        for field_key, labels in PRESETS.items():
            for order, entry in enumerate(labels):
                label, value = (entry, _slug(entry)) if isinstance(entry, str) else entry
                _, created = PresetOption.objects.get_or_create(
                    field_key=field_key,
                    value=value,
                    defaults={"label": label, "order": order},
                )
                made_presets += created
        for field_key, entries in PRESET_TEXT.items():
            for order, (label, text) in enumerate(entries):
                _, created = PresetOption.objects.get_or_create(
                    field_key=field_key,
                    value=_slug(label),
                    defaults={"label": label, "order": order, "report_text": text},
                )
                made_presets += created
        for category, titles in LIBRARY.items():
            for order, title in enumerate(titles):
                _, created = TextLibraryItem.objects.get_or_create(
                    category=category,
                    title=title,
                    defaults={"body": f"{PLACEHOLDER}{title}.", "order": order},
                )
                made_items += created
        self.stdout.write(
            self.style.SUCCESS(f"Created {made_presets} presets and {made_items} text-library items.")
        )


def _slug(label: str) -> str:
    from django.utils.text import slugify

    return slugify(label).replace("-", "_")
