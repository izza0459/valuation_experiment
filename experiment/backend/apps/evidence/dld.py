"""DLD (Dubai Land Department) sales as comparables (CLAUDE.md §6, source 2).

DLD publishes every registered sale as open data. The transactions file
(DLD's open-data export, or Dubai Pulse's `dld_transactions-open`) ships with
the app in backend/data/dld and is loaded by `manage.py import_dld` (on deploy
when the table is empty); nothing here calls DLD. The rows go into our own table and are searched locally with
the job's filters. A sale the valuer picks becomes a `Comparable` with source
"dld" and the DLD transaction number as its reference.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Replace, Upper

from apps.jobs.calculations import sqft_to_sqm
from apps.jobs.constants import PLOT_BEARING_CATEGORIES

from .models import Comparable, DldTransaction, JobComparable

SQFT_PER_SQM = Decimal("10.76391")
BATCH = 2000

# Column names differ between DLD's downloads: Dubai Pulse uses snake_case,
# the open-data page's export uses titles. Each field lists what it may be
# called, compared case- and punctuation-insensitively.
COLUMNS = {
    "transaction_number": ["transaction_id", "transaction_number", "transaction no", "transactionnumber"],
    "date": ["instance_date", "transaction_date", "transaction date", "date"],
    "group": ["trans_group_en", "transaction type", "group_en"],
    "procedure": ["procedure_name_en", "transaction sub type", "procedure_en"],
    "registration": ["reg_type_en", "registration type", "is_offplan_en"],
    "usage": ["property_usage_en", "usage", "usage_en"],
    "area_name": ["area_name_en", "area", "area_en"],
    "master_project": ["master_project_en", "master project"],
    "project_name": ["project_name_en", "project_en", "project"],
    "building_name": ["building_name_en", "building name", "building"],
    "property_type": ["property_type_en", "property type", "prop_type_en"],
    "property_sub_type": ["property_sub_type_en", "property sub type", "prop_sb_type_en"],
    "rooms": ["rooms_en", "room(s)", "rooms"],
    "size_sqm": ["procedure_area", "property size (sq.m)", "transaction size (sq.m)", "actual_area"],
    "price_aed": ["actual_worth", "amount", "trans_value"],
}

# What valuers call a community vs the DLD area it is registered under.
COMMUNITY_AREAS = {
    "dubai marina": ["marsa dubai"],
    "jumeirah village circle": ["al barsha south fourth"],
    "jvc": ["al barsha south fourth"],
    "jumeirah lake towers": ["al thanyah fifth"],
    "jlt": ["al thanyah fifth"],
    "downtown dubai": ["burj khalifa"],
    "dubai hills estate": ["hadaeq sheikh mohammed bin rashid"],
    "jumeirah village triangle": ["al barsha south fifth"],
    "dubailand": ["dubai land"],
    "health care city": ["healthcare city"],
    "dubai healthcare city": ["healthcare city"],
    "al jaddaf": ["jadaf", "jaddaf"],
    "jaddaf": ["jadaf", "jaddaf"],
    "dubai south": ["madinat al mataar"],
}

PLACE_FIELDS = ("area_name", "master_project", "project_name", "building_name")
GENERIC_WORDS = re.compile(r"\b(the|residences?|towers?|buildings?|apartments?|villas?|heights|by)\b", re.I)
# Widen until a search finds at least this many sales.
ENOUGH = 5

# Job property categories, as DLD records the property.
TYPE_GROUPS = {
    "apartment": {"Flat", "Hotel Apartment", "Unit"},
    "villa": {"Villa"},
    "office": {"Office"},
    "retail": {"Shop", "Show Rooms", "Retail"},
}


class DldFileError(ValueError):
    pass


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _map_header(header: list[str]) -> dict[str, int]:
    found = {}
    keys = [_key(h) for h in header]
    for field, names in COLUMNS.items():
        for name in names:
            if _key(name) in keys:
                found[field] = keys.index(_key(name))
                break
    missing = {"transaction_number", "date", "price_aed"} - set(found)
    if missing:
        raise DldFileError(
            "This doesn't look like a DLD transactions file: no "
            + ", ".join(sorted(missing)).replace("_", " ")
            + " column."
        )
    return found


def _date(raw: str) -> date | None:
    """DLD writes dates as 2026-09-28 13:19:50, 2026-09-28T13:19:50 or
    28-09-2026 (Dubai Pulse); the time, if any, is ignored."""
    raw = (raw or "").strip()
    try:
        return datetime.fromisoformat(raw[:19]).date()
    except ValueError:
        pass
    day = raw.split(" ")[0]
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(day, fmt).date()
        except ValueError:
            continue
    return None


def _decimal(raw: str) -> Decimal | None:
    try:
        value = Decimal((raw or "").replace(",", "").strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() and value > 0 else None


def beds_from_rooms(rooms: str) -> int | None:
    rooms = (rooms or "").strip().lower()
    if rooms.startswith("studio"):
        return 0
    match = re.match(r"(\d+)", rooms)
    return int(match.group(1)) if match else None


def import_file(binary, *, sales_only: bool = True) -> dict:
    """Loads a DLD transactions CSV from a binary file object (an upload or an
    opened file). Rows already loaded (same transaction number) are skipped,
    so a file can be loaded again, or a newer one on top."""
    reader = csv.reader(io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline=""))
    try:
        cols = _map_header(next(reader))
    except StopIteration as exc:
        raise DldFileError("The file is empty.") from exc

    def get(row, field):
        index = cols.get(field)
        return row[index].strip() if index is not None and index < len(row) else ""

    seen = skipped = added = 0
    batch = []
    for row in reader:
        seen += 1
        group = get(row, "group").lower()
        if sales_only and group and "sale" not in group:
            skipped += 1
            continue
        number, when, price = get(row, "transaction_number"), _date(get(row, "date")), _decimal(get(row, "price_aed"))
        if not number or when is None or price is None:
            skipped += 1
            continue
        registration = get(row, "registration").lower()
        rooms = get(row, "rooms")
        batch.append(DldTransaction(
            transaction_number=number[:60],
            date=when,
            procedure=get(row, "procedure")[:120],
            is_offplan=("off" in registration) if registration else None,
            usage=get(row, "usage")[:60],
            area_name=get(row, "area_name")[:120],
            master_project=get(row, "master_project")[:200],
            project_name=get(row, "project_name")[:200],
            building_name=get(row, "building_name")[:200],
            property_type=get(row, "property_type")[:60],
            property_sub_type=get(row, "property_sub_type")[:60],
            rooms=rooms[:40],
            beds=beds_from_rooms(rooms),
            size_sqm=_decimal(get(row, "size_sqm")),
            price_aed=price,
        ))
        if len(batch) >= BATCH:
            added += _save(batch)
            batch = []
    added += _save(batch)
    return {"rows": seen, "added": added, "skipped": skipped, "already_loaded": seen - skipped - added}


def _save(batch) -> int:
    if not batch:
        return 0
    numbers = [t.transaction_number for t in batch]
    existing = set(
        DldTransaction.objects.filter(transaction_number__in=numbers).values_list("transaction_number", flat=True)
    )
    fresh = {t.transaction_number: t for t in batch if t.transaction_number not in existing}
    DldTransaction.objects.bulk_create(fresh.values(), ignore_conflicts=True)
    return len(fresh)


def data_status() -> dict:
    latest = DldTransaction.objects.order_by("-date").values_list("date", flat=True).first()
    earliest = DldTransaction.objects.order_by("date").values_list("date", flat=True).first()
    return {"count": DldTransaction.objects.count(), "earliest": earliest, "latest": latest}


# --- searching ------------------------------------------------------------------------


def type_group(category: str) -> str:
    if category in PLOT_BEARING_CATEGORIES:
        return "villa"
    if "office" in (category or ""):
        return "office"
    if "retail" in (category or ""):
        return "retail"
    return "apartment" if category else ""


def defaults_for(job) -> dict:
    """The search a job starts from: its community and building, type,
    bedrooms, BUA ±20%, the last 12 months, ready or off-plan by status."""
    summary, prop, location = job.summary, job.property, job.location
    bua = summary.bua_sqft
    return {
        "community": prop.community_name or "",
        "building": prop.building_name or "",
        "type": type_group(summary.property_category),
        "beds": summary.no_of_bedrooms if summary.no_of_bedrooms is not None else "",
        "bua_min": str((bua * Decimal("0.8")).quantize(Decimal(1))) if bua else "",
        "bua_max": str((bua * Decimal("1.2")).quantize(Decimal(1))) if bua else "",
        "months": 12,
        "status": "offplan" if location.property_status == "under_construction" else "ready",
    }


def _squash(text: str) -> str:
    """Compared without case, spaces, dashes or dots: "health care city" and
    "DUBAI HEALTHCARE CITY - PHASE 2" both become ...HEALTHCARECITY..."""
    return re.sub(r"[\s\-.]", "", (text or "")).upper()


def _squashed(field: str):
    expr = Upper(field)
    for ch in (" ", "-", "."):
        expr = Replace(expr, Value(ch), Value(""))
    return expr


def _place_q(terms: list[str], fields=PLACE_FIELDS) -> Q:
    """Any of the terms in any of the fields, ignoring spacing and dashes. A
    trailing number or "phase" ("health care city 2") is also tried without."""
    variants = set()
    for term in terms:
        variants.add(_squash(term))
        trimmed = re.sub(r"(\s+(phase\s*)?\d+)+$", "", term.strip(), flags=re.I)
        if trimmed and trimmed != term.strip():
            variants.add(_squash(trimmed))
        # "Rukan Residences" is registered as "RUKAN": try it without the
        # generic words buildings are named with.
        core = GENERIC_WORDS.sub("", term).strip()
        if core and core.lower() != term.strip().lower():
            variants.add(_squash(core))
    q = Q()
    for v in (v for v in variants if len(v) >= 3):
        for field in fields:
            q |= Q(**{f"_sq_{field}__contains": v})
    return q


def _annotated(qs):
    return qs.annotate(**{f"_sq_{f}": _squashed(f) for f in PLACE_FIELDS})


def _terms(community: str) -> list[str]:
    name = community.strip().lower()
    return [name, *COMMUNITY_AREAS.get(name, [])] if name else []


def search(params: dict, limit: int = 60) -> list[DldTransaction]:
    qs = _annotated(DldTransaction.objects.all())
    months = int(params.get("months") or 12)
    qs = qs.filter(date__gte=date.today() - timedelta(days=round(months * 30.44)))

    if terms := _terms(params.get("community") or ""):
        qs = qs.filter(_place_q(terms))
    if building := (params.get("building") or "").strip():
        qs = qs.filter(_place_q([building], fields=("project_name", "building_name")))
    if group := TYPE_GROUPS.get(params.get("type") or ""):
        qs = qs.filter(Q(property_sub_type__in=group) | Q(property_type__in=group))
    if str(params.get("beds", "")).strip() != "":
        qs = qs.filter(beds=int(params["beds"]))
    for key, op in (("bua_min", "gte"), ("bua_max", "lte")):
        if (sqft := _decimal(str(params.get(key) or ""))) is not None:
            qs = qs.filter(**{f"size_sqm__{op}": sqft_to_sqm(sqft)})
    status = params.get("status")
    if status in ("ready", "offplan"):
        qs = qs.filter(is_offplan=(status == "offplan"))
    return list(qs.order_by("-date")[:limit])


def search_widening(params: dict, limit: int = 60) -> tuple[list[DldTransaction], list[str]]:
    """The search, widened one step at a time while it finds nothing, so a
    job whose building DLD names differently still gets nearby sales. Says
    what it widened."""
    # The same building registered under another DLD area (Rukan is in
    # Wadi Al Safa 7, not "Dubailand") is the best evidence, so it is tried
    # before loosening anything else.
    steps = [
        ([], {}),
        (["the building anywhere in Dubai"], {"community": ""}),
        (["any building in the community"], {"building": ""}),
        (["any building", "ready or off-plan"], {"building": "", "status": "any"}),
        (["any building", "ready or off-plan", "any bedrooms and size"],
         {"building": "", "status": "any", "beds": "", "bua_min": "", "bua_max": ""}),
    ]
    best: tuple[list[DldTransaction], list[str]] = ([], [])
    for widened, changes in steps:
        if changes.get("community") == "" and not (params.get("building") or "").strip():
            continue
        results = search({**params, **changes}, limit=limit)
        if len(results) >= ENOUGH:
            return results, widened
        if len(results) > len(best[0]):
            best = (results, widened)
    return best


def _sqft(t: DldTransaction):
    """Whole square feet (no decimals anywhere on screen or in the report)."""
    return (t.size_sqm * SQFT_PER_SQM).quantize(Decimal("1")) if t.size_sqm else None


def describe(t: DldTransaction) -> dict:
    sqft = _sqft(t)
    return {
        "id": t.id,
        "transaction_number": t.transaction_number,
        "date": t.date,
        "building": t.building_name or t.project_name,
        "community": t.area_name,
        "master_project": t.master_project,
        "type": t.property_sub_type or t.property_type,
        "rooms": t.rooms,
        "beds": t.beds,
        "size_sqm": str(t.size_sqm) if t.size_sqm else None,
        "bua_sqft": str(sqft) if sqft else None,
        "price_aed": str(t.price_aed.quantize(Decimal("1"))),
        "aed_per_sqft": str((t.price_aed / sqft).quantize(Decimal("1"))) if sqft else None,
        "offplan": t.is_offplan,
    }


# --- adding to a job ---------------------------------------------------------------------


def _readiness(t: DldTransaction) -> str:
    return {True: "Off-plan", False: "Ready"}.get(t.is_offplan, "")


def as_comparable(t: DldTransaction) -> Comparable:
    """The shared Comparable for a DLD sale, made once and reused by any job."""
    existing = Comparable.objects.filter(source="dld", source_ref=t.transaction_number).first()
    if existing:
        return existing
    sqft = _sqft(t)
    return Comparable.objects.create(
        source="dld",
        source_ref=t.transaction_number,
        community_name=(t.area_name or "")[:255],
        building_name=(t.building_name or t.project_name or "")[:255],
        property_type=(t.property_sub_type or t.property_type or "")[:60],
        beds=t.beds,
        bua_sqft=sqft,
        price_aed=t.price_aed,
        transaction_date=t.date,
        status="sold",
        notes=" · ".join(p for p in (t.procedure, _readiness(t), t.master_project) if p),
        raw_data=describe(t) | {"date": t.date.isoformat()},
    )


def add_to_job(job, ids: list[int]) -> int:
    """Links the chosen DLD sales to the job, ticked for the report."""
    added = 0
    with transaction.atomic():
        order = job.job_comparables.count()
        for t in DldTransaction.objects.filter(pk__in=ids):
            comparable = as_comparable(t)
            _, created = JobComparable.objects.get_or_create(
                job=job, comparable=comparable, defaults={"selected": True, "order": order}
            )
            if created:
                added += 1
                order += 1
    return added
