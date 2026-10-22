"""Everything a valuation report prints, gathered from a job into one
JSON-serialisable snapshot (CLAUDE.md §5).

The report template does layout and boilerplate only. What is shown, hidden
or marked "Not Applicable" is decided here, where it can be tested, and the
result is stored on each ReportVersion as its input snapshot: an issued
report can be re-rendered later from exactly what was signed, whatever has
happened to the live job since (CLAUDE.md §5: "each issued report stores its
template version and a snapshot of its inputs").
"""

from __future__ import annotations

import copy
import re
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils import timezone

from apps.jobs import calculations
from apps.jobs.constants import (
    FIGURE_BLANK,
    PARKING_PRESENT,
    PLOT_BEARING_CATEGORIES,
    TENANTED_OCCUPANCIES,
    storeys_for,
)
from apps.jobs.field_config import TABS, get_tab, where
from apps.jobs.tabs import tab_completion, visibility_context
from apps.media_files.checks import exec_summary_photos, media_blockers
from apps.presets.dictionary import REINSTATEMENT_UNIT, REINSTATEMENT_VILLA
from apps.presets.models import PresetOption

from .maps import location_map_key

NOT_APPLICABLE = "Not Applicable"
EMPTY = "—"

# Cited in every report (CLAUDE.md §2).
STANDARDS = (
    "Emirates Book Valuation Standards (EBVS); RICS Valuation – Global Standards "
    "(effective 31 January 2025); International Valuation Standards (effective 31 January 2025)"
)

LONG_LEASEHOLD = "international_long_leasehold"


# --- formatting ----------------------------------------------------------------


def fmt_date(value) -> str:
    """`26 Aug 2026`."""
    if isinstance(value, datetime):
        value = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if not isinstance(value, date):
        return ""
    return value.strftime("%d %b %Y")


def fmt_aed(value) -> str:
    """`AED 725,000`; pence-style fractions only when there are some."""
    if value in (None, ""):
        return ""
    amount = Decimal(str(value))
    return f"AED {amount:,.0f}" if amount == amount.to_integral_value() else f"AED {amount:,.2f}"


def fmt_number(value, suffix="") -> str:
    if value in (None, ""):
        return ""
    number = Decimal(str(value))
    text = f"{number:,.0f}" if number == number.to_integral_value() else f"{number:,.2f}"
    return f"{text}{suffix}"


def fmt_rent(value) -> str:
    """A figure or a range as entered ('30,000–50,000'), with separators
    added to a bare figure ('60000' -> '60,000')."""
    text = str(value or "").strip()
    if text.replace(",", "").isdigit():
        return f"{int(text.replace(',', '')):,}"
    return text.replace("\u2013", " \u2013 ")


def _dec(value):
    return None if value in (None, "") else Decimal(str(value))


def humanise(slug: str) -> str:
    return (slug or "").replace("_", " ").strip().capitalize()


# Fields taken off the form whose stored values older reports still print.
LEGACY_FIELDS = {
    ("inspection", "accommodation_first_floor"): {"free_text": False, "options_key": "accommodation_room",
                                                  "custom": True},
}


class Labels:
    """Stored preset keys ('international_freehold') back to the labels the
    valuer picked ('International Freehold'). Inactive presets are included:
    a value stored before an option was retired must still read properly on a
    report."""

    def __init__(self):
        self._by_key = {(p.field_key, p.value): p.label for p in PresetOption.objects.all()}

    def __call__(self, tab_key: str, field_key: str, value) -> str:
        if value in (None, ""):
            return ""
        field = next((f for f in get_tab(tab_key)["fields"] if f["key"] == field_key), None)
        if field is None:  # a field no longer on the form, whose values older jobs still hold
            field = LEGACY_FIELDS[(tab_key, field_key)]
        if field["free_text"]:
            return str(value)
        label = self._by_key.get((field["options_key"], value))
        if label:
            return label
        # A custom entry typed in (rooms, amenities) prints as typed.
        return str(value) if field.get("custom") else humanise(str(value))

    def many(self, tab_key: str, field_key: str, values) -> list[str]:
        return [self(tab_key, field_key, v) for v in (values or []) if v]


def _row(label, value, *, always=True):
    """A table row. With `always=False` it is dropped when there is no value;
    otherwise a missing value shows as a dash so a draft makes the gap obvious."""
    text = value if value not in (None, "") else ""
    if not text and not always:
        return None
    return {"label": label, "value": text or EMPTY}


def _rows(*rows):
    return [r for r in rows if r is not None]


def library_text(category: str, property_category: str) -> str:
    """The active library entry of `category` offered for this property type
    (or, failing that, one offered for every type)."""
    from apps.presets.models import TextLibraryItem

    items = list(TextLibraryItem.objects.filter(category=category, active=True).exclude(title="Custom")
                 .exclude(body=""))
    for item in items:
        if property_category and property_category in (item.property_categories or []):
            return item.body
    return next((i.body for i in items if not i.property_categories), "")


def _entries(value) -> list[dict]:
    """Library entries [{title, body}]; text saved before assumptions became a
    list reads as one untitled entry."""
    if isinstance(value, list):
        return [e for e in value if isinstance(e, dict) and (e.get("body") or "").strip()]
    if isinstance(value, str) and value.strip():
        return [{"title": "", "body": value}]
    return []


# A blank left in report text for the valuer to fill in: "[date]", "[client]".
BLANK = re.compile(r"\[[^\[\]\n]{1,160}\]")


def unfilled_blanks(context: dict) -> list[str]:
    """Where the report's own text still has a [blank]: "Assumptions › Desktop
    Valuation: [date], [client]". The reinstatement [●] is checked on its own."""
    text = context.get("text", {})
    found = []

    def scan(where, value):
        blanks = list(dict.fromkeys(m for m in BLANK.findall(value or "") if m != "[\u25cf]"))
        if blanks:
            found.append(f"{where}: {', '.join(blanks[:4])}{' …' if len(blanks) > 4 else ''}")

    for key, label in (("assumptions", "Assumptions"), ("special_assumptions", "Special Assumptions")):
        for entry in text.get(key) or []:
            scan(f"{label} › {entry.get('title') or 'text'}", entry.get("body"))
    for key, label in (("condition", "Property Condition"), ("specification", "Property Specification"),
                       ("repairs", "Repairs")):
        scan(label, text.get(key))
    return found


def _join(*parts, sep=", ") -> str:
    return sep.join(p for p in parts if p)


def _without(instance, tab_key: str, excluded: set[str]):
    """A copy of a tab's row with the fields left out of the report emptied."""
    prefix = f"{tab_key}."
    keys = [k[len(prefix):] for k in excluded if k.startswith(prefix)]
    if not keys or instance is None:
        return instance
    clone = copy.copy(instance)
    for key in keys:
        try:
            model_field = instance._meta.get_field(key)
        except FieldDoesNotExist:
            continue
        if isinstance(model_field, models.BooleanField):
            empty = False
        elif isinstance(model_field, models.JSONField):
            empty = []
        elif isinstance(model_field, models.CharField | models.TextField):
            empty = ""
        else:
            empty = None
        setattr(clone, model_field.attname, empty)
    return clone


# --- people -----------------------------------------------------------------------


def person_block(user) -> dict | None:
    """Name, title, qualifications and registration numbers for a signatory."""
    if user is None:
        return None
    profile = getattr(user, "valuer_profile", None)
    return {
        "name": str(user),
        "title": getattr(profile, "title", "") or "",
        "qualifications": getattr(profile, "qualifications", "") or "",
        "rera_no": getattr(profile, "rera_registration_no", "") or "",
        "rics_no": getattr(profile, "rics_membership_no", "") or "",
        "licence_expiry": fmt_date(getattr(profile, "rera_licence_expiry", None)),
    }


# --- the builder -----------------------------------------------------------------


def outstanding_items(job) -> list[str]:
    """What is still missing, for the banner on a draft. Same rules as the
    workspace's completion rings."""
    context = visibility_context(job)
    items = []
    for tab in TABS:
        if tab["fields"]:
            missing = tab_completion(tab["key"], context)["missing"]
            if missing:
                items.append(f"{where(tab['key'])}: {', '.join(missing)}")
    return items + media_blockers(job)


def _photo_caption(photo, summary) -> str:
    """What is printed under a photograph. The Makani and DEWA ones say which
    number they show when the valuer hasn't written a caption."""
    if photo.caption:
        return photo.caption
    if photo.slot == "makani":
        return f"Makani No. {summary.makani_number}" if summary.makani_number else "Makani number"
    if photo.slot == "dewa":
        return f"DEWA No. {summary.dewa_number}" if summary.dewa_number else "DEWA number"
    return ""


def _media_context(job, summary) -> dict:
    photos = [p for p in job.photos.all() if p.include_in_report]
    entry = lambda p: {"key": p.s3_key, "caption": _photo_caption(p, summary), "slot": p.slot}  # noqa: E731
    doc_labels = dict(PresetOption.objects.filter(field_key="document_type").values_list("value", "label"))
    documents = [
        {
            "key": d.s3_key,
            "title": doc_labels.get(d.doc_type) or d.doc_type.replace("_", " ").title(),
            "caption": d.caption,
            "kind": "pdf" if d.content_type == "application/pdf" else "image",
            "page_count": d.page_count,
        }
        for d in job.documents.all()
        if d.include_in_report
    ]
    return {
        "photos": [entry(p) for p in photos],
        "exec_photos": [entry(p) for p in exec_summary_photos(job)],
        "documents": documents,
    }


def _comparables(job) -> list[dict]:
    """The comparables the valuer ticked, as the report's table shows them."""
    rows = []
    for link in job.job_comparables.select_related("comparable").filter(selected=True):
        c = link.comparable
        when = c.transaction_date.strftime("%b-%y") if c.transaction_date else ""
        rows.append({
            "district": _join(c.building_name, c.community_name) or EMPTY,
            "views": c.view or EMPTY,
            "floor": c.floor or EMPTY,
            "bua_sqft": fmt_number(c.bua_sqft) or EMPTY,
            "type": _join(f"{c.beds} BR" if c.beds is not None else "", c.property_type, sep=" ") or EMPTY,
            "price": fmt_number(c.price_aed) or EMPTY,
            "rate": fmt_number(c.price_per_sqft.quantize(Decimal("1"))) if c.price_per_sqft else EMPTY,
            "transaction": _join(c.get_status_display(), when, sep=" "),
        })
    return rows


def build_context(job, *, issued: bool | None = None) -> dict:
    """`issued` renders the job as a final report. It defaults to the job's
    lock; the issue flow passes True because it builds the final report
    before it locks the job."""
    labels = Labels()
    bank = job.bank  # None on audit / internal work, which names a client instead
    prop = job.property
    # Fields the valuer left out of the report (include-in-report step).
    excluded = set(job.report_exclusions or [])

    def row(label, value, key=None, *, always=True):
        return None if key in excluded else _row(label, value, always=always)

    def keep(key, value):
        return None if key in excluded else value
    # Every left-out field reads as empty, on copies so the job is untouched;
    # rows and paragraphs that need more than that check `excluded` below.
    prop = _without(prop, "address", excluded)
    summary = _without(job.summary, "summary", excluded)
    inspection = _without(job.inspection, "inspection", excluded)
    location = _without(job.location, "location", excluded)
    valuation = _without(job.valuation, "valuation", excluded)
    checklist = _without(job.checklist, "checklist", excluded)

    plot_bearing = summary.property_category in PLOT_BEARING_CATEGORIES
    under_construction = location.property_status == "under_construction"
    long_leasehold = summary.interest_valued == LONG_LEASEHOLD

    market_value = _dec(valuation.market_value)

    address_inspected = _join(
        f"Unit {prop.unit_number}" if prop.unit_number else "",
        prop.building_name,
        prop.community_name,
        prop.title_doc_emirate,
    )
    # The report's address is the one on the title document (property, plot,
    # municipality and building numbers, building, community, emirate);
    # until those are entered, the address as inspected stands in.
    address = prop.address_as_per_document if prop.title_doc_property_no or prop.title_doc_plot_no \
        else address_inspected
    coordinates = ""
    if prop.latitude is not None and prop.longitude is not None:
        coordinates = f"Latitude {prop.latitude}, Longitude {prop.longitude}"
    # A map with a pin, from the coordinates (CRM feedback RP-01).
    location_map = location_map_key(job, prop.latitude, prop.longitude) if coordinates else ""

    interest = labels("summary", "interest_valued", summary.interest_valued)
    category = labels("summary", "property_category", summary.property_category)
    occupancy = keep("inspection.occupancy", labels("inspection", "occupancy", inspection.occupancy))
    tenanted = inspection.occupancy in TENANTED_OCCUPANCIES
    if occupancy and tenanted and inspection.rent_if_any:
        occupancy = f"{occupancy} (passing rent {fmt_aed(inspection.rent_if_any)} p.a.)"

    year_built = "Under construction" if under_construction else (
        str(location.built_about) if location.built_about else ""
    )
    # Years.months from the built date when there is one, else whole years.
    if location.built_date:
        age = calculations.age_years_months(location.built_date, as_of=valuation.valuation_date)
    else:
        age = fmt_number(location.age_years, " years") if location.age_years is not None else ""

    beds = summary.no_of_bedrooms
    type_of_property = f"{beds} Bedroom {category.lower()}" if beds and category else category
    if plot_bearing and summary.property_sub_type and type_of_property:
        type_of_property = f"{type_of_property} ({summary.property_sub_type})"

    tenancy = ""
    if tenanted:
        tenancy = "The property is let"
        if inspection.rent_if_any:
            tenancy += f" at {fmt_aed(inspection.rent_if_any)} per annum"
        tenancy += "."
    elif inspection.occupancy == "vacant":
        tenancy = "The subject property is currently vacant."
    elif inspection.occupancy == "assumed_vacant":
        tenancy = "We have assumed that the subject property is vacant."
    elif inspection.occupancy == "owner_occupied":
        tenancy = "The subject property is owner occupied."

    # The valuer's wording, else the property type's (CRM feedback VL-06);
    # [●] takes the Reinstatement Value, and blocks issue while it has none.
    if valuation.reinstatement_note:
        reinstatement = valuation.reinstatement_note
    else:
        # The library's wording for this property type, as an admin last edited it.
        reinstatement = library_text("reinstatement", summary.property_category) or (
            REINSTATEMENT_VILLA if plot_bearing else REINSTATEMENT_UNIT)
    if FIGURE_BLANK in reinstatement and valuation.reinstatement_value:
        reinstatement = reinstatement.replace(FIGURE_BLANK, fmt_number(valuation.reinstatement_value))

    upgrades = ""
    if "inspection.upgraded" in excluded:
        pass
    elif inspection.upgraded:
        upgrades = _join("Yes", inspection.upgrade_comment, sep=" – ")
    elif inspection.inspection_type or inspection.inspection_date:
        # `upgraded` defaults to False, so "No" only means something once
        # the inspection has actually been recorded.
        upgrades = "No"

    bua_text = (
        calculations.format_bua(summary.bua_sqm, summary.bua_sqft)
        if summary.bua_sqm is not None or summary.bua_sqft is not None else ""
    )
    # Exclusions saved before BUA was entered in sqm name the sqft field.
    bua_key = "summary.bua_sqft" if "summary.bua_sqft" in excluded else "summary.bua_sqm"
    plot_text = (
        calculations.format_area(summary.plot_area_sqft)
        if plot_bearing and summary.plot_area_sqft is not None else ""
    )

    # Yes / Assumed, with the number of spaces when known (CRM feedback IN-02).
    parking_text = ""
    if summary.parking in PARKING_PRESENT:
        n = summary.no_of_parkings
        parking_text = f"Parking for {n} car{'s' if n != 1 else ''}" if n else "Parking"
        if summary.parking == "assumed":
            parking_text += " (assumed)"

    # Villas and the like storey by storey (CRM feedback IN-05); jobs recorded
    # before that keep their ground and first floor lists.
    by_storey = inspection.accommodation_by_storey if isinstance(inspection.accommodation_by_storey, dict) else {}
    storey_rows = [
        {"floor": label, "rooms": labels.many("inspection", "accommodation_by_storey", by_storey.get(key))}
        for key, label in storeys_for(inspection.floors_above_ground, inspection.has_basement)
        if by_storey.get(key)
    ] if plot_bearing and by_storey else []

    # One row per floor: the ground floor (or the unit, named by its floor),
    # then a villa's or townhouse's first floor.
    accommodation = storey_rows + _rows(
        {"floor": labels("inspection", "occupancy_title", inspection.occupancy_title)
                  or ("Ground floor" if plot_bearing else ""),
         "rooms": labels.many("inspection", "accommodation_details", inspection.accommodation_details)}
        if "inspection.accommodation_details" not in excluded and not storey_rows else None,
        {"floor": "First floor",
         "rooms": labels.many("inspection", "accommodation_first_floor", inspection.accommodation_first_floor)}
        if plot_bearing and inspection.accommodation_first_floor and not storey_rows
        and "inspection.accommodation_first_floor" not in excluded else None,
        {"floor": "Designated parking spaces", "rooms": [parking_text]}
        if parking_text and "summary.parking" not in excluded else None,
    )
    approaches = labels.many("valuation", "valuation_approaches", valuation.valuation_approaches)
    approach = ", ".join(approaches) or valuation.valuation_approach
    report_date = valuation.report_date or timezone.localdate()
    applicants = ", ".join(prop.applicant_names)
    owners = ", ".join(prop.ownership_names)

    property_details = _rows(
        _row("Client", job.organisation_name),
        _row("Valuation Ref No.", job.bayut_internal_reference_no),
        row("Bank reference", job.bank_reference_no, "instructions.bank_reference_no", always=False),
        _row("Applicant" if len(prop.applicant_names) < 2 else "Applicants", applicants),
        row("Owner" if len(prop.ownership_names) < 2 else "Owners", owners, "address.ownership_name", always=False),
        row("GPS coordinates", coordinates, "address.latitude"),
        _row("Address (as per title document)", prop.address_as_per_document),
        _row("Address (as inspected)", address_inspected),
        row("Built-up area", bua_text, bua_key),
        row("Plot area", (plot_text or EMPTY) if plot_bearing else NOT_APPLICABLE, "summary.plot_area_sqft"),
        row("Floor", summary.property_floor_no, "summary.property_floor_no"),
        row("Total no. of floors", f"G + {summary.total_floors} Floors" if summary.total_floors else "",
            "summary.total_floors"),
        row("Elevation above sea level",
            f"Approximately {fmt_number(summary.ground_elevation)} m" if summary.ground_elevation is not None else "",
            "summary.ground_elevation"),
        row("Interest valued", interest, "summary.interest_valued"),
        row("Lease expiry", fmt_date(summary.lease_expiry), "summary.lease_expiry", always=False)
        if long_leasehold else None,
        row("Acquisition method", labels("summary", "acquisition_method", summary.acquisition_method),
            "summary.acquisition_method"),
        _row("Type of property", type_of_property),
        row("Views", inspection.views_summary, "inspection.front_views"),
        row("Developer", location.developer, "location.developer"),
        row("Year built", year_built, "location.built_about"),
        row("Age of the property", age, "location.built_about"),
        row("Remaining economic life",
            f"Circa {fmt_number(location.remaining_economic_life, ' years')}"
            if location.remaining_economic_life is not None else "", "location.built_about"),
        row("Utilities", inspection.utilities_summary, "inspection.electrical_services"),
        row("Upgrades / modifications", upgrades, "inspection.upgraded"),
        row("Occupancy", occupancy, "inspection.occupancy"),
    )

    valuation_summary = _rows(
        _row("Purpose of valuation", labels("instructions", "purpose", job.purpose)),
        _row("Valuation approach", approach),
        _row("Basis of value", labels("valuation", "basis_of_valuation", valuation.basis_of_valuation)),
        _row("Standards", STANDARDS),
        _row("Date of instruction", fmt_date(job.date_of_instruction)),
        _row("Date of inspection", fmt_date(inspection.inspection_date)),
        _row("Type of inspection", labels("inspection", "inspection_type", inspection.inspection_type)),
        _row("Date of valuation", fmt_date(valuation.valuation_date)),
        _row("Date of report", fmt_date(report_date)),
        _row("Market Value", fmt_aed(market_value)),
        _row("Market Value in words", calculations.amount_in_words(market_value) if market_value else ""),
        _row("Market Value rate", f"{fmt_aed(valuation.market_value_rate_per_sqft)} / sqft"
             if valuation.market_value_rate_per_sqft else ""),
        row("Market Rent", f"AED {fmt_rent(valuation.market_rent)} per annum" if valuation.market_rent else "",
            "valuation.market_rent", always=False),
        row("Capacity of valuer", labels("summary", "capacity_of_valuer", summary.capacity_of_valuer),
            "summary.capacity_of_valuer"),
        row("Departures", summary.departures, "summary.departures"),
    )

    areas = _rows(
        row("Built-up area", bua_text, bua_key),
        row("Plot area", plot_text or EMPTY, "summary.plot_area_sqft") if plot_bearing else None,
    )

    def spec(label, key, value):
        return row(label, value, f"inspection.{key}", always=False)

    building_specification = _rows(
        spec("Structure", "structure", labels("inspection", "structure", inspection.structure)),
        spec("Roof", "roof", labels("inspection", "roof", inspection.roof)),
        spec("External walls", "external_walls", labels("inspection", "external_walls", inspection.external_walls)),
        spec("Flooring", "flooring", ", ".join(labels.many("inspection", "flooring", inspection.flooring))),
        spec("Internal walls", "walls", ", ".join(labels.many("inspection", "walls", inspection.walls))),
        spec("Ceiling", "ceiling", ", ".join(labels.many("inspection", "ceiling", inspection.ceiling))),
        spec("Lighting", "lighting", ", ".join(labels.many("inspection", "lighting", inspection.lighting))),
        spec("Utilities", "electrical_services", inspection.utilities_summary),
        spec("Air conditioning", "air_conditioning",
             ", ".join(labels.many("inspection", "air_conditioning", inspection.air_conditioning))),
    )

    valuer = person_block(job.registered_valuer)
    # The peer reviewer's sign-off is the second signature (they become the
    # counter-signatory when they sign off), so a draft shows them already.
    counter_signatory = person_block(job.counter_signatory or job.peer_reviewer)
    if issued is None:
        issued = job.is_locked

    return {
        "meta": {
            "ref_no": job.bayut_internal_reference_no,
            "version": job.version,
            "is_draft": not issued,
            "generated_on": fmt_date(timezone.now()),
            "outstanding": [] if issued else outstanding_items(job),
        },
        "standards": STANDARDS,
        # Wording in Terms of Engagement and the Opinion of Value quotes these.
        "purpose": labels("instructions", "purpose", job.purpose),
        "interest": interest,
        "occupancy_key": inspection.occupancy,
        "capacity": labels("summary", "capacity_of_valuer", summary.capacity_of_valuer),
        "firm": {
            "name": settings.REPORT_FIRM_NAME,
            "legal_name": settings.REPORT_FIRM_LEGAL_NAME,
            "address": settings.REPORT_FIRM_ADDRESS,
        },
        "client": {
            "name": job.organisation_name,
            "billing_address": job.billing_address or (bank.billing_address if bank else ""),
            "po_box": bank.po_box if bank else "",
        },
        "property": {
            "address": address,
            "inspected_address": address_inspected,
            "title_address": prop.address_as_per_document,
            "applicants": applicants,
            "owners": keep("address.ownership_name", owners) or "",
            "coordinates": keep("address.latitude", coordinates) or "",
            "map": keep("address.latitude", location_map) or "",
            "category": category,
        },
        "dates": {
            "valuation": fmt_date(valuation.valuation_date),
            "report": fmt_date(report_date),
        },
        "property_details": property_details,
        "valuation_summary": valuation_summary,
        "areas": areas,
        "bua_assumed_note": (
            "The built-up area is taken from the sale and purchase agreement and is assumed to be correct."
            if summary.bua_source == "spa" else ""
        ),
        "bua_source": labels("summary", "bua_source", summary.bua_source),
        "plot_source": labels("summary", "plot_area_source", summary.plot_area_source) if plot_bearing else "",
        "building_specification": building_specification,
        "accommodation": accommodation,
        "information_provided": keep(
            "summary.information_provided",
            labels.many("summary", "information_provided", summary.information_provided),
        ) or [],
        "inspection_type": labels("inspection", "inspection_type", inspection.inspection_type),
        "inspection_date": fmt_date(inspection.inspection_date),
        "inspector": str(job.inspected_by) if job.inspected_by else "",
        "text": {
            "disclosure": summary.disclosure,
            # Yes / No, then the paragraphs adopted (report text inputs, Oct 2026).
            "assumptions": _entries(keep("summary.assumptions", summary.assumptions))
            if summary.has_assumptions else [],
            "special_assumptions": _entries(keep("summary.special_assumptions", summary.special_assumptions))
            if summary.has_special_assumptions else [],
            # No longer entered (Other Matters joined the assumptions library);
            # kept so older jobs still print theirs.
            "other_matters": summary.other_matters or [],
            "market_commentary": keep("summary.market_commentary", summary.market_commentary) or "",
            "valuation_commentary": keep("valuation.valuation_commentary", valuation.valuation_commentary) or "",
            # By property type (CRM feedback VL-04); empty boxes aren't printed.
            "type_commentary": [
                {"title": title, "body": body}
                for title, body in (
                    ("Villas / Townhouses", valuation.commentary_villas),
                    ("Shell & Core / Fitted Offices", valuation.commentary_offices),
                    ("Shell & Core / Fitted Retail", valuation.commentary_retail),
                )
                if (body or "").strip()
            ],
            "sub_community": keep("location.sub_community", location.sub_community) or "",
            "location": keep("location.location", location.location) or "",
            "amenities": keep(
                "location.amenities", ", ".join(labels.many("location", "amenities", location.amenities))
            ) or "",
            "specification": keep("location.property_specification", location.property_specification) or "",
            "condition": keep("location.property_condition", location.property_condition) or "",
            "repairs": keep("inspection.repairs", inspection.repairs) or "",
        },
        "reinstatement": "" if {"valuation.reinstatement_value", "valuation.reinstatement_note"} & excluded
        else reinstatement,
        "tenancy": keep("inspection.occupancy", tenancy) or "",
        "tenanted": tenanted,
        "plot_bearing": plot_bearing,
        "valuation": {
            "market_value": fmt_aed(market_value),
            "market_value_words": calculations.amount_in_words(market_value) if market_value else "",
            "basis": labels("valuation", "basis_of_valuation", valuation.basis_of_valuation),
            "basis_key": valuation.basis_of_valuation,
            "uncertainty": bool(valuation.material_valuation_uncertainty),
            "uncertainty_note": valuation.material_valuation_uncertainty_note,
        },
        "valuer": valuer,
        "counter_signatory": counter_signatory,
        "comparables": _comparables(job),
        **_media_context(job, summary),
        "checklist": {
            "makani_photo": checklist.makani_photo,
            "dewa_photo": checklist.dewa_photo,
        },
    }
