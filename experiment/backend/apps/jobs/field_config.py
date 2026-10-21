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

from .constants import PARKING_PRESENT, PLOT_BEARING_CATEGORIES

FIELD_TYPES = {
    "text", "textarea", "number", "decimal", "boolean", "date", "datetime",
    "select", "multiselect", "user", "library", "names",
}

# Purposes that name a free-text client organisation instead of a bank.
NON_BANK_PURPOSES = ["audit_purpose", "internal_purpose"]
MORTGAGE = {"field": "instructions.purpose", "op": "eq", "value": "mortgage_security"}
PLOT_BEARING = {"field": "summary.property_category", "op": "in", "value": list(PLOT_BEARING_CATEGORIES)}


def field(key, label, type, *, required=False, default=None, options_key=None,
          visible_if=None, calculated=False, help_text="", free_text=False, dropdown=False,
          append=False, custom=False):
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
        # The option's label is stored rather than a key (community, emirate).
        # With `dropdown` it must be one of the options; without, the options
        # are only suggestions and any text is accepted.
        "free_text": free_text,
        "dropdown": dropdown,
        # Library fields: picking an entry adds its text instead of replacing it.
        "append": append,
        # Multiselects: anything not in the list can be typed in and is
        # printed as typed (CRM feedback IN-04, VL-03).
        "custom": custom,
    }


TABS = [
    # --- Setup (ops) -------------------------------------------------------------
    {
        "key": "instructions",
        "label": "Instructions",
        "stage": "setup",
        "order": 1,
        "fields": [
            field("purpose", "Purpose", "select", required=True, options_key="purpose",
                  default="mortgage_security"),
            field("bank", "Bank / Organisation", "select", required=True, options_key="bank",
                  visible_if=MORTGAGE),
            field("bank_reference_no", "Bank Reference No.", "text", visible_if=MORTGAGE,
                  help_text="Filled in from the bank's code when the bank is picked; edit if needed."),
            field("client_name", "Organisation / Client name", "text", required=True,
                  visible_if={"field": "instructions.purpose", "op": "in", "value": NON_BANK_PURPOSES}),
            field("billing_address", "Billing address", "textarea",
                  help_text="Auto-filled from the Bank master once the SLA is signed."),
            field("bayut_internal_reference_no", "Bayut Internal Reference No.", "text", calculated=True),
            field("date_time_request_received", "Date/Time request received", "datetime"),
            field("date_of_instruction", "Date of Instruction", "date", required=True),
            field("contact_name", "Contact name", "text", help_text="Who to call for access."),
            field("contact_number", "Contact number", "text"),
            # Conflict of interest (CRM feedback LG-01).
            field("coi_suggestion", "COI suggestion", "text", calculated=True,
                  help_text="From instructions in the last 12 months for this property or applicant."),
            field("coi_check", "COI Check", "select", required=True, options_key="coi_check",
                  help_text="Yes needs the client's consent (proof) uploaded before Setup can finish."),
            field("coi_confirmed", "COI confirmed", "text", calculated=True),
        ],
    },
    {
        "key": "address",
        "label": "Property Address",
        "stage": "setup",
        "order": 2,
        "fields": [
            field("unit_number", "Unit Number", "text"),
            field("building_name", "Building Name", "text",
                  help_text="Villa community name for villas."),
            field("community_name", "Community Name", "select", options_key="community", free_text=True),
            field("latitude", "Latitude", "decimal"),
            field("longitude", "Longitude", "decimal"),
            field("applicant_name", "Applicant name(s)", "names", required=True),
            field("ownership_name", "Owner name(s)", "names"),
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
                  free_text=True, dropdown=True),
            field("address_as_per_document", "Address as per document", "textarea", calculated=True,
                  help_text="Printed as the property's address on the report."),
        ],
    },
    # --- Scheduling (inspector): booking the inspection (CRM feedback SC-01..04) ---------
    {
        "key": "scheduling",
        "label": "Scheduling",
        "stage": "scheduling",
        "order": 2.5,
        "fields": [
            # Carried over from Setup, read-only.
            field("organisation_name", "Bank", "text", calculated=True),
            field("contact_name", "POC name", "text", calculated=True),
            field("contact_number", "POC phone", "text", calculated=True),
            field("map_link", "Map link", "text", calculated=True,
                  help_text="From the coordinates on Property Address."),
            field("call_status", "Call status", "select", required=True, options_key="call_status"),
            field("call_remark", "Remark", "textarea", required=True,
                  visible_if={"field": "scheduling.call_status", "op": "in",
                              "value": ["answered_not_scheduled", "utc"]},
                  help_text="Why it isn't booked yet, or when to call back."),
            field("inspection_booked_at", "Inspection date and time", "datetime", required=True,
                  visible_if={"field": "scheduling.call_status", "op": "eq", "value": "answered_scheduled"},
                  help_text="Saving it moves the job to Inspection."),
        ],
    },
    # --- Inspection (valuer) --------------------------------------------------------
    {
        "key": "checklist",
        "label": "Check List",
        "stage": "inspection",
        "order": 3,
        "fields": [
            field("inspected_by", "Inspected By", "user", required=True),
            field("valuer", "Valuer", "user", required=True),
            field("peer_reviewer", "Peer Reviewer", "user"),
            field("dld_location_checked", "DLD Location checked", "boolean", default=False,
                  help_text="Checked on the Makani website / DDA."),
            field("makani_photo", "Makani Photo", "boolean", default=False),
            field("dewa_photo", "DEWA Photo", "boolean", default=False),
            field("newly_handed_over", "Newly Handed Over", "boolean", default=False),
            field("satellite_measurement", "Satellite Imagery", "boolean", visible_if=PLOT_BEARING,
                  help_text="Cross-check applicable to villas/townhouses only."),
        ],
    },
    {
        "key": "summary",
        "label": "Preliminary Check",
        "stage": "inspection",
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
            field("market_commentary", "Market Commentary", "library", options_key="market_commentary",
                  help_text="Entries for this property's category."),
            field("property_floor_no", "Property Floor No.", "text"),
            field("floor_configuration", "Floor Configuration", "text", help_text="e.g. B+G+2P+10"),
            field("total_floors", "Total Floors", "number", help_text="Floors in the building."),
            field("ground_elevation", "Sea Level (m)", "decimal", help_text="Elevation above sea level."),
            field("no_of_bedrooms", "No. of Bedrooms", "number"),
            field("property_category", "Property Category", "select", required=True, options_key="property_category"),
            field("property_sub_type", "Sub-type", "text", visible_if=PLOT_BEARING,
                  help_text='e.g. "Corner", "Single row".'),
            field("parking", "Parking", "select", options_key="parking"),
            field("no_of_parkings", "No. of Parkings", "number",
                  visible_if={"field": "summary.parking", "op": "in", "value": list(PARKING_PRESENT)}),
            field("bua_sqm", "BUA (sqm)", "decimal", required=True, help_text="Up to 2 decimals, e.g. 125.75."),
            field("bua_sqft", "BUA (sqft)", "decimal", calculated=True),
            field("bua_source", "BUA Source", "select", options_key="area_source"),
            field("plot_area_sqft", "Plot Area (sqft)", "decimal", visible_if=PLOT_BEARING),
            field("plot_area_sqm", "Plot Area (sqm)", "decimal", calculated=True, visible_if=PLOT_BEARING),
            field("plot_area_source", "Plot Area Source", "select", options_key="area_source",
                  visible_if=PLOT_BEARING),
            field("disclosure", "Disclosure", "library", required=True, options_key="disclosure",
                  help_text="Insert one of the standard statements, then edit if needed."),
            field("capacity_of_valuer", "Capacity of Valuer", "select", options_key="capacity_of_valuer",
                  default="external"),
            field("departures", "Departures", "textarea", default="None"),
            field("assumptions", "Assumptions", "library", options_key="assumption", append=True,
                  help_text="Add as many library entries as apply, then edit the text."),
            field("special_assumptions", "Special Assumptions", "library", options_key="special_assumption"),
        ],
    },
    {
        "key": "inspection",
        "label": "Inspection",
        "stage": "inspection",
        "order": 5,
        "fields": [
            field("inspection_booked_at", "Booked for", "datetime", calculated=True,
                  help_text="From the Scheduling stage."),
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
                  options_key="accommodation_room", custom=True),
            field("accommodation_first_floor", "Accommodation (first floor)", "multiselect",
                  options_key="accommodation_room", visible_if=PLOT_BEARING, custom=True),
            field("occupancy", "Occupancy", "select", options_key="occupancy"),
            field("rent_if_any", "Rent if any (AED p.a.)", "decimal"),
            field("sale_price_if_any", "Sale Price if any (AED)", "decimal"),
            field("front_views", "Front Views", "text"),
            field("rear_views", "Rear Views", "text", visible_if=PLOT_BEARING),
            field("views_summary", "Views summary", "text", calculated=True,
                  help_text="Built from the front and rear views, for the report."),
            field("upgraded", "Upgraded", "boolean", default=False),
            field("upgrade_comment", "Upgrade / modification comment", "textarea",
                  visible_if={"field": "inspection.upgraded", "op": "eq", "value": True}),
            field("repairs", "Repairs (if any)", "textarea",
                  help_text="Starts with the standard wording; edit or replace it for this property."),
        ],
    },
    {"key": "photos", "label": "Photos", "stage": "inspection", "order": 6, "fields": []},
    # --- Valuation (valuer) ---------------------------------------------------------
    {
        "key": "location",
        "label": "Location & Description",
        "stage": "valuation",
        "order": 7,
        "fields": [
            field("property_status", "Property Status", "select", required=True, options_key="property_status"),
            field("built_about", "Built Year", "number"),
            field("built_date", "Built Date", "date",
                  help_text="Gives the exact age in years, months and days."),
            field("exact_age", "Exact Age", "text", calculated=True,
                  help_text="As at the valuation date; from the built date, else the built year."),
            field("developer", "Developer", "text"),
            field("remaining_economic_life", "Remaining economic life (years)", "number", calculated=True,
                  help_text="45 years less the property's age at the valuation date."),
            field("sub_community", "Sub Community", "library", options_key="sub_community"),
            field("location", "Location", "library", options_key="location"),
            field("amenities", "Amenities", "multiselect", options_key="amenities", custom=True),
            field("property_specification", "Property Specification", "library", options_key="property_specification"),
            field("property_condition", "Property Condition", "library", options_key="property_condition"),
        ],
    },
    {
        "key": "valuation",
        "label": "Valuation",
        "stage": "valuation",
        "order": 8,
        "fields": [
            field("valuation_date", "Valuation Date", "date", required=True,
                  help_text="Usually the inspection date."),
            field("report_date", "Report Date", "date", calculated=True,
                  help_text="Set automatically: today, then the date the report is issued."),
            field("basis_of_valuation", "Basis of Valuation", "select", required=True,
                  options_key="basis_of_valuation", default="market_value"),
            field("valuation_approaches", "Valuation Approach", "multiselect", required=True,
                  options_key="valuation_approach"),
            field("valuation_commentary", "Valuation Commentary", "library", options_key="valuation_commentary",
                  help_text="Entries for this property's category."),
            field("commentary_villas", "Commentary: Villas / Townhouses", "textarea",
                  help_text="Left empty, it isn't printed."),
            field("commentary_offices", "Commentary: Shell & Core / Fitted Offices", "textarea",
                  help_text="Left empty, it isn't printed."),
            field("commentary_retail", "Commentary: Shell & Core / Fitted Retail", "textarea",
                  help_text="Left empty, it isn't printed."),
            field("market_value", "Market Value (AED)", "decimal", required=True),
            field("market_value_rate_per_sqft", "Market Value rate (AED/sqft)", "decimal", calculated=True,
                  help_text="= Market Value ÷ BUA sqft"),
            field("market_rent", "Market Rent (AED p.a.)", "text",
                  help_text="One figure (40,000) or a range (30,000-50,000)."),
            field("reinstatement_note", "Reinstatement cost", "library", options_key="reinstatement",
                  help_text="Section 4.5. Pick the wording for the property type and edit it. [●] is filled "
                            "from the Reinstatement Value. Left blank, the property type's wording is used."),
            field("reinstatement_value", "Reinstatement Value (AED)", "decimal", visible_if=PLOT_BEARING,
                  help_text="Fills the [●] in the villa / townhouse wording."),
            field("material_valuation_uncertainty", "Special Note", "boolean", default=False,
                  help_text="Section 7.2: material valuation uncertainty or another risk the reader should know."),
            field("material_valuation_uncertainty_note", "Special Note text", "library", options_key="special_note",
                  visible_if={"field": "valuation.material_valuation_uncertainty", "op": "eq", "value": True}),
        ],
    },
    {"key": "documents", "label": "Documents", "stage": "valuation", "order": 9, "fields": []},
    {"key": "evidence", "label": "Evidence", "stage": "valuation", "order": 10, "fields": []},
    # Sending for review, the reviewer's sign-off, the counter-signature,
    # issuing and sending to the bank, all in one place.
    {"key": "review", "label": "Review & Send", "stage": "review", "order": 11, "fields": []},
]

# The include-in-report step (on leaving the Valuation stage) lists every
# field of the Setup, Inspection and Valuation tabs. What a bank report must
# carry (client, references, applicant, address, the team, dates, basis,
# Market Value) is always in; calculated fields follow the fields they are
# worked out from; the valuer may leave out anything else
# (apps.reports.context honours the keys). Marked on each field as `report`
# ("always" / "derived" / "optional") and `report_optional`.
REPORT_ALWAYS = {
    "instructions": {"purpose", "bank", "client_name", "billing_address", "date_of_instruction"},
    "address": {
        "unit_number", "building_name", "community_name", "applicant_name", "registered_valuer",
        "title_doc_type", "title_doc_property_no", "title_doc_plot_no", "title_doc_municipality_no",
        "title_doc_building_no", "title_doc_building_name", "title_doc_community_name", "title_doc_emirate",
    },
    "checklist": {"inspected_by", "valuer", "peer_reviewer"},
    "summary": {"property_category", "no_of_bedrooms", "disclosure"},
    "inspection": {"inspection_date", "inspection_type"},
    "location": {"property_status"},
    "valuation": {"valuation_date", "basis_of_valuation", "valuation_approaches", "market_value"},
}
REPORT_TABS = ("instructions", "address", "checklist", "summary", "inspection", "location", "valuation")
REPORT_OPTIONAL: dict[str, list[str]] = {}
for _tab in TABS:
    for _field in _tab["fields"]:
        if _field["calculated"]:
            _field["report"] = "derived"
        elif _field["key"] in REPORT_ALWAYS.get(_tab["key"], ()) or _tab["key"] not in REPORT_TABS:
            _field["report"] = "always"
        else:
            _field["report"] = "optional"
            REPORT_OPTIONAL.setdefault(_tab["key"], []).append(_field["key"])
        _field["report_optional"] = _field["report"] == "optional"

# The workspace groups its tabs under these stages. Filling in a stage's tabs
# moves the job on (see transitions.sync_stage); nothing is locked by stage.
STAGES = [
    {"key": "setup", "label": "Setup"},
    {"key": "scheduling", "label": "Scheduling"},
    {"key": "inspection", "label": "Inspection"},
    {"key": "valuation", "label": "Valuation"},
    {"key": "review", "label": "Review & Send"},
]


def get_tab(key: str) -> dict:
    for tab in TABS:
        if tab["key"] == key:
            return tab
    raise KeyError(key)


def where(tab_key: str) -> str:
    """'Setup › Summary': how a missing item is placed for the user."""
    tab = get_tab(tab_key)
    stage = next(s["label"] for s in STAGES if s["key"] == tab["stage"])
    return f"{stage} › {tab['label']}"


def stage_tabs(stage: str) -> list[str]:
    return [tab["key"] for tab in TABS if tab["stage"] == stage]


def serialize_config() -> list:
    """What the frontend fetches to render the form (CLAUDE.md §8:
    "config-driven field definitions ... shared by UI and validation")."""
    return TABS
