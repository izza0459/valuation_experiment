"""The dropdown lists and text-library entries from the business field
dictionary ("Valuation Report Field Dictionary (3).xlsx", Oct 2026).

`sync` brings the database in line: the dictionary's options are created or
re-labelled and put in its order, and options it no longer lists are
deactivated (never deleted: a value already stored on a job must still read
properly on its report). Existing stored keys are kept where an option was
only renamed. Used by migration 0004 and by `seed_presets`.
"""

from django.utils.text import slugify

from . import report_text

PLACEHOLDER = "[PLACEHOLDER – replace with approved wording] "


def _slug(label):
    return slugify(label).replace("-", "_")


# field_key -> [(label, value, older values that mean the same option)]
def o(label, value=None, *aliases):
    return (label, value or _slug(label), aliases)


PRESETS = {
    "purpose": [o("Mortgage Security"), o("Audit Purpose"), o("Internal Purpose")],
    "parking": [o("Yes"), o("No"), o("Assumed")],
    "coi_check": [o("Yes"), o("No")],
    "call_status": [
        o("Not Called", "not_called"), o("Answered – Not Scheduled", "answered_not_scheduled"),
        o("Answered – Scheduled", "answered_scheduled"), o("UTC (Unable to contact)", "utc"),
    ],
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
        o("Roof Terrace"), o("Bathroom"), o("Laundry Room"), o("Maid's Room", "maids_room"),
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

# A duplex follows the villa flow (CRM feedback IN-06).
APARTMENTS = ["apartment", "penthouse"]
VILLAS = ["villa", "townhouse", "custom_villa", "duplex"]

REINSTATEMENT_UNIT = (
    "The property comprises a single unit forming part of a larger structure, and a reinstatement cost "
    "assessment has therefore not been provided. We have assumed that the building is adequately insured on a "
    "full reinstatement basis against fire and other usual perils. We recommend that the client confirm the "
    "existence and adequacy of the building insurance cover with the owners’ association or building manager."
)
# [●] is filled from the Reinstatement Value (apps.reports.context).
REINSTATEMENT_VILLA = (
    "The reinstatement cost of the property for insurance purposes is estimated at AED [●]. This figure is "
    "provided for guidance only, is not a valuation, and should not be relied upon as a substitute for a formal "
    "insurance valuation. We recommend that the owner confirms that the property is insured for an amount not "
    "less than this figure."
)
MATERIAL_UNCERTAINTY = (
    "Our valuation is reported on the basis of material valuation uncertainty as set out in VPS 6 and VPGA 10 of "
    "the RICS Valuation – Global Standards (effective 31 January 2025). This is due to recent regional "
    "geopolitical developments, which have increased uncertainty in financial and real estate markets, affecting "
    "investor sentiment, logistics, and wider economic conditions. In these circumstances, market conditions may "
    "change more rapidly than usual, and historical market evidence may be less reliable as an indicator of "
    "current value. Some sectors may continue to be supported by domestic demand, while those more dependent on "
    "international investment, trade, or travel may be more sensitive to prevailing conditions. Broader "
    "indicators, including commodity prices and capital market activity, may also remain volatile in the short "
    "term. The inclusion of this statement does not mean that the valuation cannot be relied upon. It indicates "
    "that, in the current environment, less certainty and a higher degree of caution should be attached to the "
    "valuation than would normally be the case. The valuation reflects market circumstances and information "
    "available as at the valuation date only, and we recommend that it is kept under regular review."
)
UNITS = [*APARTMENTS, "fitted_office", "shell_core_office", "fitted_retail", "shell_core_retail"]
SHELL_AND_CORE = ["shell_core_office", "shell_core_retail"]
FITTED = ["fitted_office", "fitted_retail"]
COMMERCIAL = [*FITTED, *SHELL_AND_CORE]
HOMES = [*APARTMENTS, *VILLAS]

# Which property types each report-text option is offered for; anything not
# listed is offered for all of them (the valuer can still search for it).
OFFERED_FOR = {
    ("assumption", "Multiple Properties on Single Plot"): VILLAS,
    ("assumption", "Combined Units with Separate Title Deeds"): COMMERCIAL,
    ("assumption", "Under Construction Phase - Granted Area/Housing Program"): VILLAS,
    ("special_assumption", "Hotel Apartment"): APARTMENTS,
    ("special_assumption", "Land Value"): VILLAS,
    ("specification", "Standard Property"): HOMES,
    ("specification", "Desktop Standard Property"): HOMES,
    ("specification", "Modified Property"): HOMES,
    ("specification", "Custom Built Property"): VILLAS,
    ("specification", "Shell and Core Office"): SHELL_AND_CORE,
    ("specification", "Desktop Shell and Core Office"): SHELL_AND_CORE,
    ("specification", "Fitted Office/Retail"): FITTED,
    ("specification", "Desktop Fitted Office/Retail"): FITTED,
}

# category -> [(title, older titles, property categories it is offered for[, body])]
# A body given here is the approved wording: it replaces a placeholder body,
# never text an admin has since written.
LIBRARY = {
    # "Valuation Report Text Inputs" (Oct 2026): the approved wording, and
    # Custom, each offered for the property types it applies to.
    "assumption": [(t, [], OFFERED_FOR.get(("assumption", t), []), b)
                   for t, b in [*report_text.ASSUMPTIONS, report_text.CUSTOM]],
    "special_assumption": [(t, [], OFFERED_FOR.get(("special_assumption", t), []), b)
                           for t, b in [*report_text.SPECIAL_ASSUMPTIONS, report_text.CUSTOM]],
    "specification": [(t, [], OFFERED_FOR.get(("specification", t), []), b)
                      for t, b in [*report_text.SPECIFICATIONS, report_text.CUSTOM]],
    "condition": [(t, [], OFFERED_FOR.get(("condition", t), []), b)
                  for t, b in [*report_text.CONDITIONS, report_text.CUSTOM]],
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
    "reinstatement": [
        ("Apartment / Office / Retail", [], UNITS, REINSTATEMENT_UNIT),
        ("Villa / Townhouse", [], VILLAS, REINSTATEMENT_VILLA),
    ],
    "special_note": [
        ("Material valuation uncertainty (geopolitical)", [], [], MATERIAL_UNCERTAINTY),
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
        for order, (title, older, categories, *body) in enumerate(entries):
            row = None
            for candidate in (title, *older):
                row = TextLibraryItem.objects.filter(category=category, title__iexact=candidate).first()
                if row:
                    break
            if row is None:
                row = TextLibraryItem(category=category, body=f"{PLACEHOLDER}{title}.")
            if body and (not row.body or row.body.startswith(PLACEHOLDER) or not body[0]):
                row.body = body[0]
            row.title, row.order, row.active, row.property_categories = title, order, True, categories
            row.save()
            kept.add(row.pk)
        TextLibraryItem.objects.filter(category=category).exclude(pk__in=kept).update(active=False)

    # Market and valuation commentary now have their own lists.
    TextLibraryItem.objects.filter(category="commentary").update(active=False)


