"""The dropdown lists and text-library entries from the business field
dictionary ("Valuation Report Field Dictionary (3).xlsx", Oct 2026).

`sync` brings the database in line: the dictionary's options are created or
re-labelled and put in its order, and options it no longer lists are
deactivated (never deleted: a value already stored on a job must still read
properly on its report). Existing stored keys are kept where an option was
only renamed. Used by migration 0004 and by `seed_presets`.
"""

from django.utils.text import slugify

PLACEHOLDER = "[PLACEHOLDER – replace with approved wording] "


def _slug(label):
    return slugify(label).replace("-", "_")


# field_key -> [(label, value, older values that mean the same option)]
def o(label, value=None, *aliases):
    return (label, value or _slug(label), aliases)


PRESETS = {
    "purpose": [o("Mortgage Security"), o("Audit Purpose"), o("Internal Purpose")],
    "title_doc_type": [
        o("Title Deed"), o("Initial Contract of Sale"), o("Sales and Purchase Agreement (SPA)", "spa"),
        o("Usufruct Certificate"), o("Sale Certificate"), o("Site Plan"), o("Site Affection Plan"),
    ],
    "emirate": [
        o("Dubai"), o("Sharjah"), o("Ras Al Khaimah"), o("Umm Al Quwain"), o("Ajman"), o("Fujairah"),
        o("Abu Dhabi"), o("Al Ain"),
    ],
    "interest_valued": [
        o("International Freehold"), o("International Long Leasehold"), o("GCC Freehold"),
        o("GCC Freehold - Granted", "gcc_freehold_granted"),
    ],
    "acquisition_method": [o("Purchased"), o("Gifted"), o("Granted")],
    "information_provided": [
        o("Title Deed"), o("Initial Contract of Sale"), o("Site Plan"), o("Site Affection Plan"),
        o("Sales and Purchase Agreement (SPA)", "spa"), o("MOU Extract"), o("Usufruct Certificate"),
        o("Floor Plans", "floor_plan"), o("Unit Plan"),
    ],
    "property_category": [
        o("Apartment"), o("Villa"), o("Townhouse"), o("Fitted Office"),
        o("Shell and Core Office", "shell_core_office"), o("Fitted Retail"),
        o("Shell and Core Retail", "shell_core_retail"), o("Duplex"), o("Penthouse"),
        # Not in the dictionary's list, but it has a column in its matrix.
        o("Custom Villa"),
    ],
    "area_source": [
        o("Title Deed"), o("Initial Contract of Sale"), o("Sales and Purchase Agreement (SPA)", "spa"),
        o("Usufruct Certificate"), o("Floor Plans", "floor_plan"), o("Unit Plan"),
    ],
    "inspection_type": [
        o("Full Inspection", "full"), o("Desktop", "desktop"), o("Drive-By", "drive_by"),
        o("Previous Inspection", "previous_inspection"),
    ],
    "roof": [o("Metal Sheeting"), o("Reinforced Concrete")],
    "external_walls": [
        o("Render Over Block-work", "rendered_over_blockwork"), o("Glass Cladding"),
        o("Mixture of Block-work and Glass Cladding", "mixture_of_blockwork_and_glass_cladding"),
        o("Stone Cladding"), o("Curtain Wall Glazing"), o("Panel Cladding"), o("Precast Panels"),
        o("Mixture of Block-work and Marble Cladding", "mixture_of_blockwork_and_marble_cladding"),
    ],
    "structure": [o("Brick and Concrete Slab"), o("Reinforced Concrete"), o("Metal Frame"), o("Precast Panels")],
    "flooring": [
        o("Carpet"), o("Ceramic Flooring", "ceramic_tiles"), o("Exposed Concrete"), o("Granite"), o("Leather"),
        o("Marble"), o("Parquet"), o("Polished Concrete"), o("Polished Stone"), o("Porcelain Tiles"),
        o("Vinyl Wrap"), o("Wooden"), o("Wooden Laminate"),
    ],
    "walls_finish": [
        o("Ceramic Tiles (To Wet Areas)", "ceramic_tiles"), o("Decorative Cladding"), o("Emulsion Paint"),
        o("Exposed Block Work", "exposed_blockwork"), o("Glass"), o("Marble Cladding"), o("Stone Cladding"),
        o("Textured Wallpaper"), o("Tiles"), o("Wallpaper"), o("Wooden Cladding"), o("Leather Cladding"),
    ],
    "ceiling": [
        o("Combination of render over concrete with paint finish and false ceilings"),
        o("Decorative False Ceiling"), o("Emulsion Paint"), o("Exposed Concrete"), o("False Ceiling"),
        o("Suspended"), o("Suspended Ceiling (To Wet Areas)", "suspended_ceiling_to_wet_areas"),
        o("Exposed Paint Over Exposed Concrete"),
    ],
    "lighting": [
        o("Cove"), o("Provisions Provided", "provisions_provided_shell_core"), o("Spot"), o("Strip"),
        o("Suspended"),
    ],
    "utility_status": [o("Assumed Connected"), o("Connected"), o("Not Connected")],
    "air_conditioning": [
        o("Split Ducted Air Conditioning", "split_ducted"),
        o("Wall Mounted Split Air Conditioning", "wall_mounted_split"),
        o("District Cooling"), o("Central Air Conditioning", "central"), o("Window A/C", "window"),
    ],
    "accommodation_room": [
        o("Living/Dining Room", "livingdining_room"), o("Kitchen"), o("Pantry"), o("Living Room"),
        o("Dining Room"), o("Guest W/C", "guest_wc"), o("Kitchenette"), o("Bedroom"),
        o("Bedroom (en-suite)", "bedroom_en_suite"),
        o("Master Bedroom (en-suite/dressing)", "master_bedroom_en_suitedressing"),
        o("Bedroom (en-suite/dressing)", "bedroom_en_suitedressing"), o("Study"),
        o("Maid's Room (en-suite)", "maids_room_en_suite"), o("Store"), o("Balcony"), o("Large Terrace"),
        o("Combined Living/Dining/Bedroom", "combined_livingdiningbedroom"), o("Family Area"),
        o("Entertainment Lounge"), o("Home Theater", "home_theatre"), o("SPA Area", "spa_area"), o("Gym"),
        o("Roof Terrace"),
    ],
    "occupancy": [
        o("Assumed Vacant"), o("Multi-Tenanted", "multi_tenanted"), o("Not Applicable"),
        o("Not Applicable - Under Construction", "not_applicable_under_construction"),
        o("Owner Occupied"), o("Tenanted"), o("Tenanted (Short Term Rental)", "tenanted_short_term"),
        o("Under Construction"), o("Vacant"),
    ],
    "property_status": [o("Completed", "complete"), o("Under Construction")],
    "basis_of_valuation": [o("Market Value"), o("Fair Value"), o("Market Rent"), o("Investment Value")],
    "valuation_approach": [
        o("Market Approach - Comparable Method", "market_approach_comparable_method"),
        o("Income Approach - Traditional Investment Method", "income_approach_traditional_investment_method"),
        o("Cost Approach"),
    ],
    "amenities": [
        o("Gym"), o("Swimming Pool"), o("Walkways"), o("Retail Shops"), o("Restaurants"), o("Jogging Trails"),
        o("Mosques"), o("Schools"), o("Children's Play Area", "childrens_play_area"), o("Barbecue Area"),
    ],
}

DISCLOSURE_4 = (
    "No existing relationship; not previously valued",
    "The Signatory to this Valuation Report confirms that they do not have an existing relationship with the "
    "Client and that they have not previously valued the subject property.",
)

APARTMENTS = ["apartment", "duplex", "penthouse"]
VILLAS = ["villa", "townhouse", "custom_villa"]

# category -> [(title, older titles, property categories it is offered for)]
LIBRARY = {
    "specification": [
        ("Standard Property (Inspected)", [], []), ("Modified Property (Inspected)", [], []),
        ("Custom Specification", [], []), ("Standard Property (Desktop)", [], []),
        ("Shell & Core Office/Retail (Desktop)", [], []), ("Shell & Core Office/Retail (Inspected)", [], []),
        ("Fitted Office/Retail (Desktop)", [], []), ("Fitted Office/Retail (Inspected)", [], []),
        ("Under Construction", [], []), ("Vacant Land", [], []), ("Fully Upgraded", [], []),
    ],
    "condition": [
        ("Developer Standard Condition", ["Developer standard"], []), ("Good Condition", ["Good"], []),
        ("Average Condition", ["Average"], []), ("Maintenance Required", [], []),
    ],
    "market_commentary": [
        ("Apartment", [], APARTMENTS), ("Villa", [], VILLAS),
        ("Office", [], ["fitted_office", "shell_core_office"]),
        ("Retail", [], ["fitted_retail", "shell_core_retail"]),
    ],
    "valuation_commentary": [
        ("Apartment", [], APARTMENTS), ("Villa/Townhouse", [], VILLAS),
        ("Shell and Core Office", [], ["shell_core_office"]), ("Shell and Core Retail", [], ["shell_core_retail"]),
        ("Fitted Office", [], ["fitted_office"]), ("Fitted Retail", [], ["fitted_retail"]),
        ("Fully Customised Property", [], []), ("Rare and Unique Property", [], []),
    ],
}


def sync(PresetOption, TextLibraryItem):
    """Applies the dictionary to the given models (real or migration-state)."""

    for field_key, entries in PRESETS.items():
        kept = set()
        for order, (label, value, aliases) in enumerate(entries):
            row = PresetOption.objects.filter(field_key=field_key, value__in=[value, *aliases]).order_by(
                "-active"
            ).first()
            if row is None:
                row = PresetOption(field_key=field_key, value=value)
            row.label, row.order, row.active = label, order, True
            row.save()
            kept.add(row.pk)
        PresetOption.objects.filter(field_key=field_key).exclude(pk__in=kept).update(active=False)

    label, text = DISCLOSURE_4
    PresetOption.objects.get_or_create(
        field_key="disclosure", value=_slug(label), defaults={"label": label, "order": 3, "report_text": text}
    )

    # Other Matters joined the assumptions library.
    TextLibraryItem.objects.filter(category="other_matter").update(category="assumption")

    for category, entries in LIBRARY.items():
        kept = set()
        for order, (title, older, categories) in enumerate(entries):
            row = None
            for candidate in (title, *older):
                row = TextLibraryItem.objects.filter(category=category, title__iexact=candidate).first()
                if row:
                    break
            if row is None:
                row = TextLibraryItem(category=category, body=f"{PLACEHOLDER}{title}.")
            row.title, row.order, row.active, row.property_categories = title, order, True, categories
            row.save()
            kept.add(row.pk)
        TextLibraryItem.objects.filter(category=category).exclude(pk__in=kept).update(active=False)

    # Market and valuation commentary now have their own lists.
    TextLibraryItem.objects.filter(category="commentary").update(active=False)


