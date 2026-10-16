"""
Config-driven field definitions for the job form (CLAUDE.md §4, §8).

This is the single source of truth for which fields exist, their type,
whether they're required, when they're visible, and where their dropdown
options come from (apps.presets.PresetOption.field_key). The frontend
fetches this (see apps.jobs.views.FieldConfigView) to render the form;
the backend uses the same structure to validate submitted tab data.
Options/value lists themselves are NOT hard-coded here — they live in
PresetOption, keyed by `options_key` below (CLAUDE.md: "all dropdown
option lists are admin-editable presets, not hard-coded").

visible_if is a small (field, op, value) rule evaluated against the rest
of the job's tab data — deliberately simple; extend if a real rule engine
is ever needed.
"""

from .constants import PLOT_BEARING_CATEGORIES, TENANTED_OCCUPANCIES

FIELD_TYPES = {
    "text", "textarea", "number", "decimal", "boolean", "date", "datetime",
    "select", "multiselect", "user", "library",
}


def field(key, label, type, *, required=False, default=None, options_key=None,
          visible_if=None, calculated=False, help_text="", free_text=False):
    assert type in FIELD_TYPES, f"unknown field type {type!r} for {key}"
    return {
        "key": key,
        "label": label,
        "type": type,
        "required": required,
        "default": default,
        "options_key": options_key,
        "visible_if": visible_if,
        "calculated": calculated,  # computed server-side; read-only in the UI
        "help_text": help_text,
        # Options are suggestions: any text is accepted and stored as typed
        # (community / emirate, whose master lists don't exist yet).
        "free_text": free_text,
    }


TABS = [
    {
        "key": "checklist",
        "label": "Check List",
        "order": 1,
        "fields": [
            field("inspected_by", "Inspected By", "user", required=True),
            field("valuer", "Valuer", "user", required=True),
            field("peer_reviewer", "Peer Reviewer", "user"),
            field("counter_signatory", "Counter-signatory", "user",
                  help_text="Second signature authorising the report."),
            field("dld_location_checked", "DLD Location checked", "boolean", default=False,
                  help_text="Checked on the Makani website / DDA."),
            field("makani_photo", "Makani Photo", "boolean", default=False),
            field("dewa_photo", "DEWA Photo", "boolean", default=False),
            field("newly_handed_over", "Newly Handed Over", "boolean", default=False),
            field("satellite_measurement", "Satellite Imagery", "boolean",
                  visible_if={"field": "summary.property_category", "op": "in",
                              "value": list(PLOT_BEARING_CATEGORIES)},
                  help_text="Cross-check applicable to villas/townhouses only."),
        ],
    },
    {
        "key": "instructions",
        "label": "Instructions",
        "order": 2,
        "fields": [
            field("bank_reference_no", "Bank Reference No.", "text"),
            field("bayut_internal_reference_no", "Bayut Internal Reference No.", "text", calculated=True),
            field("date_time_request_received", "Date/Time request received", "datetime"),
            field("date_of_instruction", "Date of Instruction", "date", required=True),
            field("bank", "Organisation (bank)", "select", required=True, options_key="bank"),
            field("billing_address", "Billing address", "textarea",
                  help_text="Auto-filled from the Bank master once the SLA is signed."),
            field("purpose", "Purpose", "select", required=True, options_key="purpose",
                  default="mortgage_security"),
        ],
    },
    {
        "key": "address",
        "label": "Property Address",
        "order": 3,
        "fields": [
            field("unit_number", "Unit Number", "text"),
            field("building_name", "Building Name", "text",
                  help_text="Villa community name for villas."),
            field("development", "Development", "text",
                  help_text="Between building and community, e.g. The Views; printed in the report's address."),
            field("community_name", "Community Name", "select", options_key="community", free_text=True),
            field("latitude", "Latitude", "decimal"),
            field("longitude", "Longitude", "decimal"),
            field("applicant_name", "Applicant Name", "text", required=True),
            field("ownership_name", "Ownership Name", "text"),
            field("registered_valuer", "Registered Valuer", "user", required=True,
                  help_text="The signing valuer."),
            field("title_doc_type", "Title Document", "select", options_key="title_doc_type"),
            field("title_doc_property_no", "Property No. as per document", "text"),
            field("title_doc_plot_no", "Plot No. as per document", "text"),
            field("title_doc_municipality_no", "Municipality No. as per document", "text"),
            field("title_doc_building_no", "Building No. as per document", "text"),
            field("title_doc_building_name", "Building Name as per document", "text",
                  help_text="Leave blank if it matches the Building Name above."),
            field("title_doc_community_name", "Community Name as per document", "text",
                  help_text="Leave blank if it matches the Community Name above."),
            field("title_doc_emirate", "Emirate", "select", options_key="emirate", default="Dubai",
                  free_text=True),
            field("address_as_per_document", "Address as per document", "textarea", calculated=True),
        ],
    },
    {
        "key": "summary",
        "label": "Summary",
        "order": 4,
        "fields": [
            field("interest_valued", "Interest Valued", "select", required=True, options_key="interest_valued"),
            field("lease_expiry", "Lease Expiry", "date",
                  visible_if={"field": "summary.interest_valued", "op": "eq",
                              "value": "international_long_leasehold"}),
            field("acquisition_method", "Acquisition Method", "select", options_key="acquisition_method"),
            field("makani_number", "Makani Number", "text"),
            field("dewa_number", "DEWA Number", "text"),
            field("information_provided", "Information Provided", "multiselect", options_key="information_provided"),
            field("market_commentary", "Market Commentary", "library", options_key="commentary"),
            field("property_floor_no", "Property Floor No.", "text"),
            field("floor_configuration", "Floor Configuration", "text", help_text="e.g. B+G+2P+10"),
            field("total_floors", "Total Floors", "number", help_text="Floors in the building."),
            field("ground_elevation", "Sea Level (m)", "decimal", help_text="Elevation above sea level."),
            field("no_of_bedrooms", "No. of Bedrooms", "number"),
            field("property_category", "Property Category", "select", required=True, options_key="property_category"),
            field("parking", "Parking", "boolean", default=False),
            field("no_of_parkings", "No. of Parkings", "number",
                  visible_if={"field": "summary.parking", "op": "eq", "value": True}),
            field("bua_sqft", "BUA (sqft)", "decimal", required=True),
            field("bua_sqm", "BUA (sqm)", "decimal", calculated=True),
            field("bua_source", "BUA Source", "select", options_key="area_source"),
            field("plot_area_sqft", "Plot Area (sqft)", "decimal",
                  visible_if={"field": "summary.property_category", "op": "in",
                              "value": list(PLOT_BEARING_CATEGORIES)}),
            field("plot_area_sqm", "Plot Area (sqm)", "decimal", calculated=True,
                  visible_if={"field": "summary.property_category", "op": "in",
                              "value": list(PLOT_BEARING_CATEGORIES)}),
            field("plot_area_source", "Plot Area Source", "select", options_key="area_source",
                  visible_if={"field": "summary.property_category", "op": "in",
                              "value": list(PLOT_BEARING_CATEGORIES)}),
            field("disclosure", "Disclosure", "library", required=True, options_key="disclosure",
                  help_text="Insert one of the standard statements, then edit if needed."),
            field("capacity_of_valuer", "Capacity of Valuer", "select", options_key="capacity_of_valuer",
                  default="external"),
            field("departures", "Departures", "textarea", default="None"),
            field("assumptions", "Assumptions", "library", options_key="assumption"),
            field("special_assumptions", "Special Assumptions", "library", options_key="special_assumption"),
            field("other_matters", "Other Matters", "library", options_key="other_matter"),
        ],
    },
    {
        "key": "inspection",
        "label": "Inspection",
        "order": 5,
        "fields": [
            field("inspection_date", "Inspection Date", "date", required=True),
            field("inspection_type", "Inspection Type", "select", required=True, options_key="inspection_type"),
            field("roof", "Roof", "select", options_key="roof"),
            field("external_walls", "External Walls", "select", options_key="external_walls"),
            field("structure", "Structure", "select", options_key="structure"),
            field("flooring", "Flooring", "multiselect", options_key="flooring"),
            field("walls", "Walls", "multiselect", options_key="walls_finish"),
            field("ceiling", "Ceiling", "multiselect", options_key="ceiling"),
            field("lighting", "Lighting", "multiselect", options_key="lighting"),
            field("electrical_services", "Electrical Services", "select", options_key="utility_status"),
            field("water", "Water", "select", options_key="utility_status"),
            field("sewerage", "Sewerage (Mains drainage)", "select", options_key="utility_status"),
            field("utilities_summary", "Utilities connection status", "text", calculated=True,
                  help_text="Built from the electricity, water and sewerage statuses, for the report."),
            field("air_conditioning", "Air Conditioning", "multiselect", options_key="air_conditioning"),
            field("occupancy_title", "Occupancy Title (floor)", "select", options_key="occupancy_title"),
            field("accommodation_details", "Accommodation (ground floor / unit)", "multiselect",
                  options_key="accommodation_room"),
            field("accommodation_first_floor", "Accommodation (first floor)", "multiselect",
                  options_key="accommodation_room",
                  visible_if={"field": "summary.property_category", "op": "in",
                              "value": list(PLOT_BEARING_CATEGORIES)}),
            field("occupancy", "Occupancy", "select", options_key="occupancy"),
            field("rent_if_any", "Rent if any (AED p.a.)", "decimal"),
            field("tenant_name", "Tenant name", "text",
                  visible_if={"field": "inspection.occupancy", "op": "in", "value": TENANTED_OCCUPANCIES}),
            field("tenancy_expiry", "Tenancy expiry", "date",
                  visible_if={"field": "inspection.occupancy", "op": "in", "value": TENANTED_OCCUPANCIES}),
            field("sale_price_if_any", "Sale Price if any (AED)", "decimal"),
            field("front_views", "Front Views", "text"),
            field("rear_views", "Rear Views", "text",
                  visible_if={"field": "summary.property_category", "op": "in",
                              "value": list(PLOT_BEARING_CATEGORIES)}),
            field("views_summary", "Views summary", "text", calculated=True,
                  help_text="Built from the front and rear views, for the report."),
            field("upgraded", "Upgraded", "boolean", default=False),
            field("upgrade_comment", "Upgrade / modification comment", "textarea",
                  visible_if={"field": "inspection.upgraded", "op": "eq", "value": True}),
            field("repairs", "Repairs (if any)", "textarea"),
        ],
    },
    {
        "key": "location",
        "label": "Location & Description",
        "order": 6,
        "fields": [
            field("property_status", "Property Status", "select", required=True, options_key="property_status"),
            field("built_about", "Built Year", "number"),
            field("built_date", "Built Date", "date",
                  help_text="Optional; gives the report's age in years and months."),
            field("exact_age", "Exact Age", "number", calculated=True,
                  help_text="Valuation year minus built year; only some banks need it."),
            field("developer", "Developer", "text"),
            field("remaining_economic_life_years", "Remaining economic life (years)", "number",
                  help_text="Estimated remaining economic life of the building."),
            field("sub_community", "Sub Community", "library", options_key="sub_community"),
            field("location", "Location", "library", options_key="location"),
            field("amenities", "Amenities", "multiselect", options_key="amenities"),
            field("property_specification", "Property Specification", "library", options_key="property_specification"),
            field("property_condition", "Property Condition", "library", options_key="property_condition"),
        ],
    },
    {
        "key": "valuation",
        "label": "Valuation",
        "order": 7,
        "fields": [
            field("valuation_date", "Valuation Date", "date", required=True,
                  help_text="Usually the inspection date."),
            field("report_date", "Report Date", "date", required=True),
            field("basis_of_valuation", "Basis of Valuation", "select", required=True,
                  options_key="basis_of_valuation", default="market_value"),
            field("valuation_approach", "Valuation Approach", "text",
                  default="Market approach – Comparable method"),
            field("valuation_commentary", "Valuation Commentary", "library", options_key="commentary"),
            field("market_value", "Market Value (AED)", "decimal", required=True),
            field("market_value_rate_per_sqft", "Market Value rate (AED/sqft)", "decimal", calculated=True,
                  help_text="= Market Value ÷ BUA sqft"),
            field("market_rent", "Market Rent (AED p.a.)", "decimal"),
            field("reinstatement_note", "Reinstatement cost", "textarea",
                  help_text="Section 4.5. Left blank, a unit in a larger building gets the standard wording."),
            field("reinstatement_value", "Reinstatement Value (AED)", "decimal",
                  visible_if={"field": "summary.property_category", "op": "in",
                              "value": list(PLOT_BEARING_CATEGORIES)}),
            field("material_valuation_uncertainty", "Special Note", "boolean", default=False,
                  help_text="Section 7.2: material valuation uncertainty or another risk the reader should know."),
            field("material_valuation_uncertainty_note", "Special Note text", "textarea",
                  visible_if={"field": "valuation.material_valuation_uncertainty", "op": "eq", "value": True}),
        ],
    },
    {"key": "photos", "label": "Photos", "order": 8, "fields": []},
    {"key": "documents", "label": "Documents", "order": 9, "fields": []},
    {"key": "evidence", "label": "Evidence", "order": 10, "fields": []},
]


def get_tab(key: str) -> dict:
    for tab in TABS:
        if tab["key"] == key:
            return tab
    raise KeyError(key)


def serialize_config() -> list:
    """What the frontend fetches to render the form (CLAUDE.md §8:
    "config-driven field definitions ... shared by UI and validation")."""
    return TABS
