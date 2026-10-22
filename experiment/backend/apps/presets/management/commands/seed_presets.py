"""Seeds the dropdown option lists and text library from CLAUDE.md §4.

Idempotent and non-destructive: rows are created only if missing, so an
admin's edits and deactivations survive a re-run.

The text library is not seeded here: its approved wording ("Valuation Report
Text Inputs") comes from the presets migrations (apps.presets.dictionary).
"""

from django.core.management.base import BaseCommand

from apps.presets.models import PresetOption

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
        # The rest of the title document types (presets migration 0005).
        "Initial Contract of Sale", "Usufruct Certificate", "Sale Certificate",
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
class Command(BaseCommand):
    help = "Seed dropdown presets and (idempotent)."

    def handle(self, *args, **options):
        made_presets = 0
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
        self.stdout.write(
            self.style.SUCCESS(f"Created {made_presets} presets.")
        )


def _slug(label: str) -> str:
    from django.utils.text import slugify

    return slugify(label).replace("-", "_")
