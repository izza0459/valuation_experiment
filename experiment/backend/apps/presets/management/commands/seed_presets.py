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

PRESETS = {
    "purpose": ["Mortgage Security", "Audit Purpose", "Internal Purpose"],
    "community": [
        "Downtown Dubai", "Dubai Marina", "Jumeirah Village Circle (JVC)", "Business Bay", "Palm Jumeirah",
        "Dubai Hills Estate", "Arabian Ranches", "Jumeirah Lake Towers (JLT)", "DIFC", "Dubai Sports City",
        "Dubailand", "Dubai Silicon Oasis", "Dubai South", "Meydan", "Al Barsha",
    ],
    "emirate": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah", "Umm Al Quwain", "Al Ain"],
    "title_doc_type": [
        "Title Deed", "Site Plan", "Site Affection Plan", "SPA", "Ownership Certificate", "Ownership Deed",
        "Usufruct Certificate", "Initial Contract of Sale", "Initial Sale Certificate",
        "Pre-Registration Certificate", "Oqood", "Other", "Sale Certificate",
    ],
    # What an uploaded document is (Tab 8). Slugs of these are stored on the document.
    "document_type": [
        "Title Deed", "SPA", "Site Plan", "Site Affection Plan", "Floor Plan", "Developer's Floor Plan",
        "Tenancy Contract", "Ownership Certificate", "NOC", "Bank instruction", "Other",
    ],
    "interest_valued": [
        "International Freehold", "International Long Leasehold", "GCC Freehold", "GCC Leasehold",
        "Granted title", "Freehold for UAE Nationals only", "Musataha", "GCC Freehold – Granted",
    ],
    "acquisition_method": ["Purchased", "Gifted", "Granted", "Allotment"],
    "information_provided": [
        "Title Deed", "SPA", "Site Plan", "Site Affection Plan", "Floor Plan", "Developer's Floor Plan",
        "Tenancy Contract", "Initial Contract of Sale", "MOU Extract", "Usufruct Certificate", "Unit Plan",
    ],
    "property_category": [
        "Apartment", "Villa", "Townhouse", "Duplex", "Penthouse", "Custom Villa", "Shell & Core Office",
        "Fitted Office", "Shell & Core Retail", "Fitted Retail",
    ],
    "area_source": [
        "Title Deed", "Site Affection Plan", "Initial Certificate of Sale", "SPA", "Initial Contract of Sale",
        "Usufruct Certificate", "Floor Plan", "Unit Plan",
    ],
    "capacity_of_valuer": ["External", "Internal"],
    # Values must match InspectionData.INSPECTION_TYPE_CHOICES.
    "inspection_type": ["Full", "Desktop", "Drive-by", "Previous inspection"],
    "roof": ["Reinforced concrete", "Metal sheeting"],
    "external_walls": [
        "Rendered over blockwork", "Glass cladding", "Stone cladding", "Curtain wall glazing", "Panel cladding",
        "Precast panels", "Mixture of blockwork and glass cladding", "Mixture of blockwork and marble cladding",
    ],
    "structure": ["Reinforced concrete", "Brick and concrete slab", "Metal frame", "Precast panels"],
    "flooring": [
        "Ceramic tiles", "Porcelain tiles", "Marble", "Granite", "Parquet", "Wooden laminate", "Carpet",
        "Polished concrete", "Exposed concrete", "Leather", "Polished stone", "Vinyl wrap", "Wooden",
    ],
    "walls_finish": [
        "Emulsion paint", "Ceramic tiles", "Wallpaper", "Stone / marble / wooden cladding", "Decorative cladding",
        "Exposed blockwork", "Glass", "Marble cladding", "Stone cladding", "Textured wallpaper", "Tiles",
        "Wooden cladding", "Leather cladding",
    ],
    "ceiling": [
        "Emulsion paint", "False ceiling", "Decorative false ceiling", "Exposed concrete", "Suspended",
        "Suspended ceiling (to wet areas)",
        "Combination of render over concrete with paint finish and false ceilings",
    ],
    "lighting": ["Cove", "Recessed", "Spot", "Strip", "Suspended", "Provisions provided (shell & core)"],
    "utility_status": ["Connected", "Not connected", "Assumed connected"],
    "air_conditioning": [
        "Central", "District cooling", "Split", "Split ducted", "Wall-mounted split", "Window",
    ],
    "occupancy_title": [
        "Ground", "1st", "2nd", "3rd", "4th", "5th", "Mezzanine", "Basement", "Podium", "Upper level",
        "Lower level", "Outbuilding",
    ],
    "accommodation_room": [
        "Living/Dining room", "Kitchen", "Guest WC", "Bedroom", "Bedroom (en-suite)", "Bathroom", "Maid's room",
        "Study", "Laundry", "Balcony", "Parking", "Pantry", "Living room", "Dining room", "Kitchenette",
        "Master bedroom (en-suite/dressing)", "Bedroom (en-suite/dressing)", "Maid's room (en-suite)", "Store",
        "Large terrace", "Combined living/dining/bedroom", "Family area", "Entertainment lounge", "Home theatre",
        "Spa area", "Gym", "Roof terrace",
    ],
    # Values must match InspectionData.OCCUPANCY_CHOICES.
    "occupancy": [
        "Vacant", "Owner occupied", "Tenanted", "Not applicable", "Assumed vacant", "Multi-tenanted",
        ("Tenanted (short-term rental)", "tenanted_short_term"), "Under construction",
        "Not applicable – under construction",
    ],
    "property_status": ["Complete", "Under Construction"],
    "basis_of_valuation": [
        "Market Value", "Fair Value", "Market Rent", "Investment Value",
        # (label, value): the stored key predates the preset and is kept.
        ("Market Value (Assuming Transferable Title)", "market_value_transferable_title"),
    ],
}

# category -> titles (CLAUDE.md §4). Bodies are placeholders; see module docstring.
LIBRARY = {
    "special_assumption": [
        "Granted title converted to freehold", "Hotel apartment rental-pool restriction", "Assumed UAE Freehold",
        "Compound limited access", "Extension/modification permission assumed", "No NOC / assumed NOC",
        "Satellite imagery",
    ],
    "other_matter": [
        "Title deed size error", "Wrong plot size", "Wrong floor plans", "Structural damage", "Sharjah properties",
        "Sample unit inspection", "Road noise", "Payment plan", "Phone mast", "Restricted freehold",
        "Drive-by/desktop assumed good condition", "Exaggerated BUA", "Illegal modifications",
        "Under-construction phase notes", "Vacant & furnished",
    ],
    "commentary": [
        "Typical apartments", "Villas", "Offices", "Retail", "Northern Emirates", "Unique property",
        "Lack of direct comparables",
    ],
    "specification": [
        "Standard property (inspected)", "Modified property (inspected)", "Custom specification",
        "Standard property (desktop)", "Shell & core office", "Fitted office/retail", "Under construction",
        "Upgraded unit", "Fully upgraded", "Minor modifications", "Drive-by private villa assumed", "Vacant land",
        "Shell & core office/retail (desktop)", "Shell & core office/retail (inspected)",
        "Fitted office/retail (desktop)", "Fitted office/retail (inspected)",
    ],
    "condition": [
        "Developer standard", "Good", "Average", "Below average", "Maintenance required", "Under construction",
        "Desktop/Drive-by – assumed good", "Vacant land", "Off-plan",
    ],
    "assumption": [],
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
