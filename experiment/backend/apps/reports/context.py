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
from apps.jobs.constants import PLOT_BEARING_CATEGORIES
from apps.jobs.field_config import TABS, get_tab
from apps.jobs.models import InspectionData
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
    rules = bank.rules or {}
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
        prop.community_name,
        prop.title_doc_emirate,
    )
    coordinates = ""
    if prop.latitude is not None and prop.longitude is not None:
        coordinates = f"{prop.gps_dms} ({prop.latitude}, {prop.longitude})"

    interest = labels("summary", "interest_valued", summary.interest_valued)
    category = labels("summary", "property_category", summary.property_category)
    occupancy = labels("inspection", "occupancy", inspection.occupancy)
    if inspection.occupancy in InspectionData.TENANTED_OCCUPANCIES and inspection.rent_if_any:
        occupancy = f"{occupancy} (passing rent {fmt_aed(inspection.rent_if_any)} p.a.)"

    if under_construction:
        year_or_completion = (
            f"Under construction – {fmt_number(valuation.completion_pct)}% complete"
            if valuation.completion_pct is not None
            else "Under construction"
        )
    else:
        year_or_completion = str(location.built_about) if location.built_about else ""

    upgrades = ""
    if inspection.upgraded:
        upgrades = _join("Yes", inspection.upgrade_comment, sep=" – ")
    elif inspection.inspection_type or inspection.inspection_date:
        # `upgraded` defaults to False, so "No" only means something once
        # the inspection has actually been recorded.
        upgrades = "No"

    bua_text = calculations.format_area(summary.bua_sqm) if summary.bua_sqm is not None else ""
    plot_text = (
        calculations.format_area(summary.plot_area_sqm) if plot_bearing and summary.plot_area_sqm is not None else ""
    )

    property_details = _rows(
        _row("Client", bank.name),
        _row("Valuation Ref No.", job.bayut_internal_reference_no),
        _row("Bank reference", job.bank_reference_no, always=False),
        _row("Applicant", prop.applicant_name),
        _row("GPS coordinates", coordinates),
        _row("Address (as inspected)", address_inspected),
        _row("Address (as per title document)", prop.address_as_per_document),
        _row("Plot no.", prop.title_doc_plot_no),
        _row("Building", prop.building_name),
        _row("Community", prop.community_name),
        _row("Built-up area", bua_text),
        _row("Plot area", (plot_text or EMPTY) if plot_bearing else NOT_APPLICABLE),
        _row("Floor", summary.property_floor_no),
        _row("Total floors", str(summary.total_floors) if summary.total_floors else ""),
        _row("Ground elevation", fmt_number(summary.ground_elevation, " m above sea level")),
        _row("Distance from coastline", fmt_number(location.coastline_distance_km, " km")),
        _row("Interest valued", interest),
        _row("Lease expiry", fmt_date(summary.lease_expiry), always=False) if long_leasehold else None,
        _row("Acquisition method", labels("summary", "acquisition_method", summary.acquisition_method)),
        _row("Type of property", summary.type_of_property or category),
        _row("Views", inspection.views_summary),
        _row("Developer", location.developer),
        _row("Year built / completion", year_or_completion),
        _row("Age band", location.property_age_band, always=False),
        _row("Exact age", f"{location.exact_age} years" if location.exact_age is not None else "")
        if rules.get("requires_exact_age") else None,
        _row("Remaining economic life", fmt_number(location.remaining_economic_life_years, " years")),
        _row("Utilities", inspection.utilities_summary),
        # Only for banks that ask for it (the ADIB rule lives in Bank.rules).
        # TODO: the unit (AED per sqft or per year) isn't captured; confirm
        # with the first target bank before this goes on a real report.
        _row("Service charge", fmt_aed(inspection.service_charge)) if rules.get("requires_service_charge") else None,
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
        _row("Date of valuation", fmt_date(valuation.valuation_date)),
        _row("Date of report", fmt_date(valuation.report_date)),
        _row("Market Value", fmt_aed(market_value)),
        _row("Market Value in words", calculations.amount_in_words(market_value) if market_value else ""),
        _row("Market Value rate", f"{fmt_aed(valuation.market_value_rate_per_sqft)} / sqft"
             if valuation.market_value_rate_per_sqft else ""),
        _row("Estimated rental range",
             f"{fmt_aed(valuation.market_rent_low)} – {fmt_aed(valuation.market_rent_high)} p.a."
             if valuation.market_rent_low and valuation.market_rent_high else "", always=False),
        _row("Forced sale value", f"{fmt_aed(valuation.forced_sale_value)} "
             f"(Market Value less {fmt_number(valuation.effective_forced_sale_discount_pct)}%)")
        if rules.get("requires_forced_sale_value") and market_value else None,
        _row("Capacity of valuer", labels("summary", "capacity_of_valuer", summary.capacity_of_valuer)),
        _row("Departures", summary.departures),
    )

    under_construction_rows = _rows(
        _row("Construction cost", fmt_aed(valuation.construction_cost)),
        _row("Completion", f"{fmt_number(valuation.completion_pct)}%" if valuation.completion_pct is not None else ""),
        _row("Land cost / land-only value", fmt_aed(valuation.land_cost)),
        _row("As-is value", fmt_aed(valuation.as_is_value)),
        _row("Assumed complete value", fmt_aed(valuation.assumed_complete_value)),
    ) if under_construction else []

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
             labels("inspection", "air_conditioning", inspection.air_conditioning), always=False),
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
        "under_construction": under_construction_rows,
        "areas": areas,
        "bua_assumed_note": (
            "The built-up area is taken from the sale and purchase agreement and is assumed to be correct."
            if summary.bua_source == "spa" else ""
        ),
        "bua_source": labels("summary", "bua_source", summary.bua_source),
        "plot_source": labels("summary", "plot_area_source", summary.plot_area_source) if plot_bearing else "",
        "building_specification": building_specification,
        "accommodation": {
            "floor": labels("inspection", "occupancy_title", inspection.occupancy_title),
            "rooms": labels.many("inspection", "accommodation_details", inspection.accommodation_details),
        },
        "information_provided": labels.many("summary", "information_provided", summary.information_provided),
        "inspection_type": labels("inspection", "inspection_type", inspection.inspection_type),
        "inspection_date": fmt_date(inspection.inspection_date),
        "text": {
            "disclosure": summary.disclosure,
            "assumptions": summary.assumptions,
            "special_assumptions": summary.special_assumptions or [],
            "other_matters": summary.other_matters or [],
            "market_commentary": summary.market_commentary,
            "valuation_commentary": valuation.valuation_commentary,
            "sub_community": location.sub_community,
            "location": location.location,
            "amenities": location.amenities,
            "specification": location.property_specification,
            "condition": location.property_condition,
            "repairs": inspection.repairs,
        },
        "reinstatement": (
            fmt_aed(valuation.reinstatement_value) if plot_bearing and valuation.reinstatement_value else ""
        ),
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
