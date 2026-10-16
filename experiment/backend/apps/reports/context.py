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

from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.jobs import calculations
from apps.jobs.constants import PLOT_BEARING_CATEGORIES, TENANTED_OCCUPANCIES
from apps.jobs.field_config import TABS, get_tab
from apps.jobs.tabs import tab_completion, visibility_context
from apps.media_files.checks import exec_summary_photos, media_blockers
from apps.presets.models import PresetOption

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


def _dec(value):
    return None if value in (None, "") else Decimal(str(value))


def humanise(slug: str) -> str:
    return (slug or "").replace("_", " ").strip().capitalize()


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
        field = next(f for f in get_tab(tab_key)["fields"] if f["key"] == field_key)
        if field["free_text"]:
            return str(value)
        return self._by_key.get((field["options_key"], value)) or humanise(str(value))

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


def _join(*parts, sep=", ") -> str:
    return sep.join(p for p in parts if p)


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
                items.append(f"{tab['label']}: {', '.join(missing)}")
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


def build_context(job, *, issued: bool | None = None) -> dict:
    """`issued` renders the job as a final report. It defaults to the job's
    lock; the issue flow passes True because it builds the final report
    before it locks the job."""
    labels = Labels()
    bank = job.bank
    prop = job.property
    summary, inspection, location = job.summary, job.inspection, job.location
    valuation, checklist = job.valuation, job.checklist

    plot_bearing = summary.property_category in PLOT_BEARING_CATEGORIES
    under_construction = location.property_status == "under_construction"
    long_leasehold = summary.interest_valued == LONG_LEASEHOLD

    market_value = _dec(valuation.market_value)

    address_inspected = _join(
        f"Unit {prop.unit_number}" if prop.unit_number else "",
        prop.building_name,
        prop.development,
        prop.community_name,
        prop.title_doc_emirate,
    )
    coordinates = ""
    if prop.latitude is not None and prop.longitude is not None:
        coordinates = f"Latitude {prop.latitude}, Longitude {prop.longitude}"

    interest = labels("summary", "interest_valued", summary.interest_valued)
    category = labels("summary", "property_category", summary.property_category)
    occupancy = labels("inspection", "occupancy", inspection.occupancy)
    tenanted = inspection.occupancy in TENANTED_OCCUPANCIES
    if tenanted and inspection.rent_if_any:
        occupancy = f"{occupancy} (passing rent {fmt_aed(inspection.rent_if_any)} p.a.)"

    year_built = "Under construction" if under_construction else (
        str(location.built_about) if location.built_about else ""
    )
    # Years.months from the built date when there is one, else whole years.
    if location.built_date:
        age = calculations.age_years_months(location.built_date, as_of=valuation.valuation_date)
    else:
        age = fmt_number(location.exact_age, " years") if location.exact_age is not None else ""

    beds = summary.no_of_bedrooms
    type_of_property = f"{beds} Bedroom {category.lower()}" if beds and category else category

    tenancy = ""
    if tenanted:
        tenancy = "The property is let"
        if inspection.tenant_name:
            tenancy += f" to {inspection.tenant_name}"
        if inspection.rent_if_any:
            tenancy += f" at {fmt_aed(inspection.rent_if_any)} per annum"
        if inspection.tenancy_expiry:
            tenancy += f", expiring {fmt_date(inspection.tenancy_expiry)}"
        tenancy += "."
    elif inspection.occupancy == "vacant":
        tenancy = "The subject property is currently vacant."
    elif inspection.occupancy == "assumed_vacant":
        tenancy = "We have assumed that the subject property is vacant."
    elif inspection.occupancy == "owner_occupied":
        tenancy = "The subject property is owner occupied."

    if valuation.reinstatement_note:
        reinstatement = valuation.reinstatement_note
    elif plot_bearing:
        reinstatement = (
            f"The estimated reinstatement value for insurance purposes is {fmt_aed(valuation.reinstatement_value)}."
            if valuation.reinstatement_value else ""
        )
    else:
        reinstatement = (
            "The property forms part of a larger structure and it is therefore not possible to provide a "
            "reinstatement cost estimate for the individual unit. We assume the building is fully insured "
            "against fire and the usual perils."
        )

    upgrades = ""
    if inspection.upgraded:
        upgrades = _join("Yes", inspection.upgrade_comment, sep=" – ")
    elif inspection.inspection_type or inspection.inspection_date:
        # `upgraded` defaults to False, so "No" only means something once
        # the inspection has actually been recorded.
        upgrades = "No"

    bua_text = calculations.format_area(summary.bua_sqft) if summary.bua_sqft is not None else ""
    plot_text = (
        calculations.format_area(summary.plot_area_sqft)
        if plot_bearing and summary.plot_area_sqft is not None else ""
    )

    # One row per floor: the ground floor (or the unit, named by its floor),
    # then a villa's or townhouse's first floor.
    accommodation = _rows(
        {"floor": labels("inspection", "occupancy_title", inspection.occupancy_title)
                  or ("Ground floor" if plot_bearing else ""),
         "rooms": labels.many("inspection", "accommodation_details", inspection.accommodation_details)},
        {"floor": "First floor",
         "rooms": labels.many("inspection", "accommodation_first_floor", inspection.accommodation_first_floor)}
        if plot_bearing and inspection.accommodation_first_floor else None,
        {"floor": "Designated parking spaces",
         "rooms": [f"Parking for {summary.no_of_parkings} car{'s' if summary.no_of_parkings != 1 else ''}"]}
        if summary.parking and summary.no_of_parkings else None,
    )

    property_details = _rows(
        _row("Client", bank.name),
        _row("Valuation Ref No.", job.bayut_internal_reference_no),
        _row("Bank reference", job.bank_reference_no, always=False),
        _row("Applicant", prop.applicant_name),
        _row("GPS coordinates", coordinates),
        _row("Address (as inspected)", address_inspected),
        _row("Address (as per title document)", prop.address_as_per_document),
        _row("Built-up area", bua_text),
        _row("Plot area", (plot_text or EMPTY) if plot_bearing else NOT_APPLICABLE),
        _row("Floor", summary.property_floor_no),
        _row("Total no. of floors", f"G + {summary.total_floors} Floors" if summary.total_floors else ""),
        _row("Elevation above sea level",
             f"Approximately {fmt_number(summary.ground_elevation)} m" if summary.ground_elevation is not None else ""),
        _row("Interest valued", interest),
        _row("Lease expiry", fmt_date(summary.lease_expiry), always=False) if long_leasehold else None,
        _row("Acquisition method", labels("summary", "acquisition_method", summary.acquisition_method)),
        _row("Type of property", type_of_property),
        _row("Views", inspection.views_summary),
        _row("Developer", location.developer),
        _row("Year built", year_built),
        _row("Age of the property", age),
        _row("Remaining economic life",
             f"Circa {fmt_number(location.remaining_economic_life_years, ' years')}"
             if location.remaining_economic_life_years else ""),
        _row("Utilities", inspection.utilities_summary),
        _row("Upgrades / modifications", upgrades),
        _row("Occupancy", occupancy),
    )

    valuation_summary = _rows(
        _row("Purpose of valuation", labels("instructions", "purpose", job.purpose)),
        _row("Valuation approach", valuation.valuation_approach),
        _row("Basis of value", labels("valuation", "basis_of_valuation", valuation.basis_of_valuation)),
        _row("Standards", STANDARDS),
        _row("Date of instruction", fmt_date(job.date_of_instruction)),
        _row("Date of inspection", fmt_date(inspection.inspection_date)),
        _row("Type of inspection", labels("inspection", "inspection_type", inspection.inspection_type)),
        _row("Date of valuation", fmt_date(valuation.valuation_date)),
        _row("Date of report", fmt_date(valuation.report_date)),
        _row("Market Value", fmt_aed(market_value)),
        _row("Market Value in words", calculations.amount_in_words(market_value) if market_value else ""),
        _row("Market Value rate", f"{fmt_aed(valuation.market_value_rate_per_sqft)} / sqft"
             if valuation.market_value_rate_per_sqft else ""),
        _row("Market Rent", f"{fmt_aed(valuation.market_rent)} per annum" if valuation.market_rent else "",
             always=False),
        _row("Capacity of valuer", labels("summary", "capacity_of_valuer", summary.capacity_of_valuer)),
        _row("Departures", summary.departures),
    )

    areas = _rows(
        _row("Built-up area", bua_text),
        _row("Plot area", plot_text or EMPTY) if plot_bearing else None,
    )

    building_specification = _rows(
        _row("Structure", labels("inspection", "structure", inspection.structure), always=False),
        _row("Roof", labels("inspection", "roof", inspection.roof), always=False),
        _row("External walls", labels("inspection", "external_walls", inspection.external_walls), always=False),
        _row("Flooring", ", ".join(labels.many("inspection", "flooring", inspection.flooring)), always=False),
        _row("Internal walls", ", ".join(labels.many("inspection", "walls", inspection.walls)), always=False),
        _row("Ceiling", ", ".join(labels.many("inspection", "ceiling", inspection.ceiling)), always=False),
        _row("Lighting", ", ".join(labels.many("inspection", "lighting", inspection.lighting)), always=False),
        _row("Utilities", inspection.utilities_summary, always=False),
        _row("Air conditioning",
             ", ".join(labels.many("inspection", "air_conditioning", inspection.air_conditioning)), always=False),
    )

    valuer = person_block(job.registered_valuer)
    counter_signatory = person_block(job.counter_signatory)
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
            "name": bank.name,
            "billing_address": job.billing_address or bank.billing_address,
            "po_box": bank.po_box,
        },
        "property": {
            "address": address_inspected,
            "title_address": prop.address_as_per_document,
            "coordinates": coordinates,
            "category": category,
        },
        "dates": {
            "valuation": fmt_date(valuation.valuation_date),
            "report": fmt_date(valuation.report_date),
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
        "information_provided": labels.many("summary", "information_provided", summary.information_provided),
        "inspection_type": labels("inspection", "inspection_type", inspection.inspection_type),
        "inspection_date": fmt_date(inspection.inspection_date),
        "inspector": str(job.inspected_by) if job.inspected_by else "",
        "text": {
            "disclosure": summary.disclosure,
            "assumptions": summary.assumptions,
            "special_assumptions": summary.special_assumptions or [],
            "other_matters": summary.other_matters or [],
            "market_commentary": summary.market_commentary,
            "valuation_commentary": valuation.valuation_commentary,
            "sub_community": location.sub_community,
            "location": location.location,
            "amenities": ", ".join(labels.many("location", "amenities", location.amenities)),
            "specification": location.property_specification,
            "condition": location.property_condition,
            "repairs": inspection.repairs,
        },
        "reinstatement": reinstatement,
        "tenancy": tenancy,
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
        "comparables": [],  # evidence arrives with build-order step 7
        **_media_context(job, summary),
        "checklist": {
            "makani_photo": checklist.makani_photo,
            "dewa_photo": checklist.dewa_photo,
        },
    }
