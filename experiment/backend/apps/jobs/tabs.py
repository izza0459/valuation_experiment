"""Reading and writing a job's tabs through the field config.

`field_config.TABS` is the single description of the tabs. This module
is what makes it authoritative on the server as well as in the UI:

* **Storage routing** — a tab is not a model. Check List mixes its own row
  with role FKs on `Job`; Instructions is `Job`, Property Address is `Property`. Where each
  field lives is derived from the config, never hand-listed per field.
* **Visibility and completion** — the same `visible_if` / `required` rules
  the form uses, evaluated here, so "is this tab complete?" has one answer.
* **Validation** — values are coerced and checked against the underlying
  model field and the field's option list before anything is written.
* **Concurrency** — each tab has a version; a write names the version it was
  based on and is refused if someone has saved since (first edit wins).

`required` is deliberately *not* enforced on write: autosave has to accept a
half-filled draft. Completeness is reported (`completion`) and enforced at
the gates that need it (sending for review, issuing).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import Role
from apps.accounts.permissions import is_platform_admin, roles_on_job
from apps.audit.middleware import acting_as
from apps.banks.models import Bank
from apps.presets.options import options_for
from apps.reports.models import ReportTemplate

from .field_config import TABS, get_tab
from .models import (
    CallAttempt,
    ChecklistData,
    InspectionData,
    Job,
    JobTabVersion,
    LocationData,
    Property,
    ReviewerEdit,
    SchedulingData,
    SummaryData,
    ValuationData,
    split_names,
)
from .workflow import FROZEN_STATUSES, JobLockedError, JobStatus

TAB_MODELS = {
    "scheduling": SchedulingData,
    "checklist": ChecklistData,
    "summary": SummaryData,
    "inspection": InspectionData,
    "location": LocationData,
    "valuation": ValuationData,
}

# Who may edit which tab (CLAUDE.md §3). "Admin later" fields on Instructions
# are filled by the valuer for now, so the valuer holds that tab too.
# Platform admins can edit everything; peer reviewers and counter-signatories
# review, they don't edit.
# The Setup stage (Instructions, Property Address) belongs to whoever took
# the instruction (the job's admin, usually an ops person); the valuer does
# the rest and can step into Setup too.
TAB_EDIT_ROLES = {
    "checklist": {Role.INSPECTOR, Role.VALUER},
    "instructions": {Role.ADMIN, Role.OPS, Role.VALUER},
    "address": {Role.ADMIN, Role.OPS, Role.VALUER},
    # Booking the inspection: the inspector, with ops and the valuer.
    "scheduling": {Role.ADMIN, Role.OPS, Role.INSPECTOR, Role.VALUER},
    "summary": {Role.VALUER},
    "inspection": {Role.INSPECTOR, Role.VALUER},
    "location": {Role.VALUER},
    "valuation": {Role.VALUER},
    # Photos and documents have no form fields; their uploads, captions and
    # ordering are checked against the same rules (see apps/media_files).
    "photos": {Role.INSPECTOR, Role.VALUER},
    # The title document is attached from the Check List, so the inspector too.
    "documents": {Role.ADMIN, Role.OPS, Role.INSPECTOR, Role.VALUER},
    # Comparables the valuer enters and picks for the report (apps/evidence).
    "evidence": {Role.VALUER},
}

MEDIA_TABS = ("photos", "documents")
# Tabs without form fields that still hold editable records.
RECORD_TABS = (*MEDIA_TABS, "evidence")

# Fields that decide who works on the job. Sitting on the inspector's Check
# List tab must not let the inspector reassign the valuer.
ASSIGNMENT_FIELDS = {"inspected_by", "valuer", "peer_reviewer", "counter_signatory", "registered_valuer"}
ASSIGNMENT_ROLES = {Role.ADMIN, Role.VALUER}

# Coordinates are pasted from Google Maps with more decimals than the column
# keeps; they are rounded to the column's precision (~0.1 m). Every other
# figure (money, areas, elevation) is a whole number: decimals are rounded
# half-up to the nearest unit, and thousands separators are accepted.
INSPECTOR_LABEL = "Inspector (assign on the Check List)"
BOOKED_LABEL = "Inspection booked"
# Statuses past Scheduling: its tab counts as done there.
PAST_SCHEDULING = {
    "inspection_scheduled", "inspected", "valuation_in_progress", "peer_review", "approved_signed", "issued",
}

# The document type of the consent a COI "Yes" needs (CRM feedback LG-01).
COI_CONSENT_DOC = "coi_consent"
COI_CONSENT_LABEL = "Consent received (proof)"

ROUND_TO_COLUMN_PRECISION = {"latitude", "longitude", "bua_sqm"}

# Decimals are non-negative unless listed here; bounded ones are checked
# against their range. A negative market value would otherwise reach the
# value-in-words renderer and fail there instead of being rejected here.
SIGNED_DECIMALS = {"ground_elevation", "latitude", "longitude"}
DECIMAL_RANGES = {
    "latitude": (Decimal(-90), Decimal(90)),
    "longitude": (Decimal(-180), Decimal(180)),
    "completion_pct": (Decimal(0), Decimal(100)),
    "forced_sale_discount_pct": (Decimal(0), Decimal(100)),
}


# --- errors -----------------------------------------------------------------


class TabError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, detail, **extra):
        super().__init__(detail)
        self.detail = detail
        self.extra = extra

    def payload(self):
        return {"code": self.code, "detail": self.detail, **self.extra}


class UnknownTab(TabError):
    status = 404
    code = "unknown_tab"


class NotPermitted(TabError):
    status = 403
    code = "forbidden"


class JobIsLocked(TabError):
    status = 409
    code = "locked"


class JobIsFrozen(TabError):
    status = 409
    code = "frozen"


class VersionConflict(TabError):
    status = 409
    code = "conflict"


class ValidationFailed(TabError):
    status = 400
    code = "validation"

    def __init__(self, errors: dict):
        super().__init__("Some values are invalid.", errors=errors)


# --- storage routing ----------------------------------------------------------


def _concrete(model, name):
    try:
        mf = model._meta.get_field(name)
    except FieldDoesNotExist:
        return None
    return mf if getattr(mf, "concrete", False) else None


def resolve_storage(tab_key: str, field_key: str):
    """Where a config field is stored: ("tab"|"job"|"property", model field).

    The tab's own model wins, then Job, then Property. Raises LookupError for
    a field that has no column, which the config tests treat as a bug."""
    for target, model in (("tab", TAB_MODELS.get(tab_key)), ("job", Job), ("property", Property)):
        if model is None:
            continue
        mf = _concrete(model, field_key)
        if mf is not None:
            return target, mf
    raise LookupError(f"{tab_key}.{field_key} has no storage")


def _tab_row(job, tab_key, *, create=False):
    model = TAB_MODELS.get(tab_key)
    if model is None:
        return None
    if create:
        return model.objects.get_or_create(job=job)[0]
    try:
        return getattr(job, tab_key)
    except model.DoesNotExist:
        return model(job=job)


def _targets(job, tab_key, *, create=False):
    return {"tab": _tab_row(job, tab_key, create=create), "job": job, "property": job.property}


def _editable_fields(tab_key):
    return [f for f in get_tab(tab_key)["fields"] if not f["calculated"]]


# --- reading ------------------------------------------------------------------


def tab_values(job, tab_key: str) -> dict:
    targets = _targets(job, tab_key)
    values = {}
    for f in _editable_fields(tab_key):
        target, mf = resolve_storage(tab_key, f["key"])
        value = getattr(targets[target], mf.attname)
        values[f["key"]] = split_names(value) if f["type"] == "names" else value
    return values


def tab_computed(job, tab_key: str) -> dict:
    """Derived values the UI shows but never sends (sqft, DMS, rate/sqft ...)."""
    targets = _targets(job, tab_key)
    sources = [targets["tab"], targets["property"], job]
    computed = {}
    for f in get_tab(tab_key)["fields"]:
        if not f["calculated"]:
            continue
        for source in sources:
            if source is not None and hasattr(source, f["key"]):
                computed[f["key"]] = getattr(source, f["key"])
                break
    if tab_key == "valuation":
        # Not a form field, but printed beside the figure on the signed report.
        computed["market_value_in_words"] = targets["tab"].market_value_in_words
        # System-generated: the issue date once issued, today until then.
        computed["report_date"] = targets["tab"].report_date or timezone.localdate()
    return computed


def _resolve_path(path: str, values: dict):
    current = values
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def is_field_visible(field: dict, context: dict) -> bool:
    """Server twin of `isFieldVisible` in web/src/lib/fieldConfig.ts."""
    rule = field["visible_if"]
    if not rule:
        return True
    actual = _resolve_path(rule["field"], context)
    op = rule["op"]
    if op == "eq":
        return actual == rule["value"]
    if op == "in":
        return isinstance(rule["value"], list) and actual in rule["value"]
    if op == "not_in":
        return isinstance(rule["value"], list) and actual not in rule["value"]
    if op == "is_true":
        return bool(actual)
    return True


def _is_empty(value) -> bool:
    return value is None or value == "" or value == []


def visibility_context(job) -> dict:
    context = {tab["key"]: tab_values(job, tab["key"]) for tab in TABS if tab["fields"]}
    # Uploads a form field depends on: a Yes on the COI check needs the consent.
    context["uploads"] = {"coi_consent": job.documents.filter(doc_type=COI_CONSENT_DOC).exists()}
    context["job"] = {"status": job.status}
    bank = job.bank
    context["bank"] = {"name": job.organisation_name, "rules": (bank.rules if bank else None) or {}}
    return context


def tab_completion(tab_key: str, context: dict) -> dict:
    """Share of the *visible required* fields that are filled in.

    Hidden fields never count, so a conditional field the job will never need
    (plot area on an apartment) can't hold a tab below 100%."""
    values = context.get(tab_key, {})
    required = [
        f["label"] for f in get_tab(tab_key)["fields"] if f["required"] and is_field_visible(f, context)
    ]
    missing = [
        f["label"] for f in get_tab(tab_key)["fields"]
        if f["required"] and is_field_visible(f, context) and _is_empty(values.get(f["key"]))
    ]
    # A conflict of interest can't pass Setup without the client's consent.
    if tab_key == "instructions" and values.get("coi_check") == "yes":
        required.append(COI_CONSENT_LABEL)
        if not context.get("uploads", {}).get("coi_consent"):
            missing.append(COI_CONSENT_LABEL)
    # Setup hands over to Scheduling once an inspector is assigned (CRM feedback SC-01).
    if tab_key == "instructions":
        required.append(INSPECTOR_LABEL)
        if not context.get("checklist", {}).get("inspected_by"):
            missing.append(INSPECTOR_LABEL)
    if tab_key == "scheduling":
        status = context.get("job", {}).get("status")
        if status in PAST_SCHEDULING:
            return {"pct": 100, "missing": []}  # booked before the stage existed, or done
        required.append(BOOKED_LABEL)
        if values.get("call_status") != "answered_scheduled" and BOOKED_LABEL not in missing:
            missing.append(BOOKED_LABEL)
    if not required:
        return {"pct": 100, "missing": []}
    return {"pct": round((len(required) - len(missing)) / len(required) * 100), "missing": missing}


def _versions(job) -> dict:
    stored = dict(JobTabVersion.objects.filter(job=job).values_list("tab_key", "version"))
    return {tab["key"]: stored.get(tab["key"], 0) for tab in TABS}


def _wire(mapping: dict) -> dict:
    """Decimals go out as strings. DRF's encoder would turn a bare Decimal
    into a float, and money must not pass through binary floating point
    between the database and the screen."""
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in mapping.items()}


def media_completion(job, tab_key: str) -> dict:
    """Photos/Documents progress: how many of what this job needs are in."""
    from apps.media_files.checks import requirements  # the media app depends on this one

    needs = requirements(job, tab_key)
    if not needs:
        return {"pct": 100, "missing": []}
    missing = [label for label, met in needs if not met]
    return {"pct": round((len(needs) - len(missing)) / len(needs) * 100), "missing": missing}


def job_tab_state(job, user=None) -> dict:
    """Everything the workspace needs per tab, in one place. Given a user it
    also says whether they can edit each tab, and if not, why."""
    context = visibility_context(job)
    versions = _versions(job)
    state = {
        tab["key"]: {
            "values": _wire(context.get(tab["key"], {})),
            "computed": _wire(tab_computed(job, tab["key"])) if tab["fields"] else {},
            "completion": (
                media_completion(job, tab["key"]) if tab["key"] in MEDIA_TABS else tab_completion(tab["key"], context)
            ),
            "version": versions[tab["key"]],
        }
        for tab in TABS
    }
    if user is not None:
        for key, tab_state in state.items():
            has_form = bool(get_tab(key)["fields"]) or key in RECORD_TABS
            denial = edit_denial(user, job, key) if has_form else None
            tab_state["can_edit"] = has_form and denial is None
            tab_state["read_only_reason"] = denial.detail if denial else ""
            # "forbidden": not this user's stage (shown quietly, not as an error);
            # "locked" / "frozen": nobody can edit it now.
            tab_state["read_only_code"] = denial.code if denial else ""
            # Fields on an otherwise editable tab that this user may not change.
            if reviewing(user, job):
                wording = reviewer_fields(key)
                tab_state["read_only_fields"] = [f["key"] for f in get_tab(key)["fields"] if f["key"] not in wording]
            else:
                tab_state["read_only_fields"] = (
                    [] if may_assign(user, job)
                    else [f["key"] for f in get_tab(key)["fields"] if f["key"] in ASSIGNMENT_FIELDS]
                )
    return state


# Where each status sits among the workspace stages (mirrors the web app).
STAGE_FOR_STATUS = {
    "instruction_received": "setup",
    "setup": "setup",
    "scheduling": "scheduling",
    "inspection_scheduled": "inspection",
    "inspected": "inspection",
    "valuation_in_progress": "valuation",
    "peer_review": "review",
    "approved_signed": "review",
    "issued": "issued",
}
STAGE_LABELS = {"setup": "Setup", "scheduling": "Scheduling", "inspection": "Inspection", "valuation": "Valuation",
                "review": "Review", "issued": "Issued"}


def job_progress(job) -> dict:
    """The dashboard's status and sub-status: the stage the job is in, and
    the section of it being worked on (the first that isn't complete)."""
    stage = STAGE_FOR_STATUS.get(job.status, "setup")
    sub = ""
    if stage in ("setup", "scheduling", "inspection", "valuation"):
        context = visibility_context(job)
        for tab in sorted(TABS, key=lambda t: t["order"]):
            if tab["stage"] != stage:
                continue
            if tab["key"] in MEDIA_TABS:
                done = media_completion(job, tab["key"])
            elif tab["fields"]:
                done = tab_completion(tab["key"], context)
            else:
                continue
            if done["pct"] < 100:
                sub = tab["label"]
                break
        sub = sub or "Ready for the next stage"
    elif job.status == "peer_review":
        sub = "Awaiting peer review"
    elif job.status == "approved_signed":
        sub = "Approved & signed"
    else:
        sub = "Report issued"
    return {"stage": stage, "stage_label": STAGE_LABELS[stage], "sub_status": sub}


# --- validation ---------------------------------------------------------------


class _Invalid(Exception):
    pass


def _allowed_values(field: dict, mf) -> list | None:
    """The option values a select accepts, or None when anything goes
    (free-text fields, and keys an admin hasn't populated yet)."""
    if not field["options_key"] or (field["free_text"] and not field.get("dropdown")):
        return None
    options = options_for(field["options_key"], free_text=field["free_text"])
    return [o["value"] for o in options] or None


def _coerce_text(raw, mf, multiline):
    if raw is None:
        raw = ""
    if not isinstance(raw, str):
        raise _Invalid("Must be text.")
    value = raw if multiline else raw.strip()
    if value == "" and mf.null:
        return None
    if value:
        mf.run_validators(value)
    return value


def _coerce_number(raw, mf):
    if raw is None or raw == "":
        if mf.null:
            return None
        raise _Invalid("A value is required.")
    if isinstance(raw, bool):
        raise _Invalid("Must be a whole number.")
    try:
        if isinstance(raw, str):
            raw = _without_separators(raw)
            if raw == "":
                return _coerce_number(None, mf)
        number = Decimal(str(raw))
        if not number.is_finite():
            raise _Invalid("Must be a whole number.")
        value = int(number.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise _Invalid("Must be a whole number.") from exc
    mf.run_validators(value)
    return value


def _without_separators(raw) -> str:
    """'1,250,000' -> '1250000'. Numbers are typed with thousands separators."""
    return str(raw).strip().replace(",", "").replace(" ", "")


def _coerce_decimal(raw, mf, key):
    if raw is None or raw == "":
        if mf.null:
            return None
        raise _Invalid("A value is required.")
    if isinstance(raw, bool):
        raise _Invalid("Must be a number.")
    try:
        # str() first: Decimal(48.2) would carry the float's binary noise.
        value = Decimal(_without_separators(raw))
    except InvalidOperation as exc:
        raise _Invalid("Must be a number.") from exc
    if not value.is_finite():
        raise _Invalid("Must be a number.")

    low, high = DECIMAL_RANGES.get(key, (None if key in SIGNED_DECIMALS else Decimal(0), None))
    if (low is not None and value < low) or (high is not None and value > high):
        if low is not None and high is not None:
            raise _Invalid(f"Must be between {low} and {high}.")
        raise _Invalid("Can't be negative.")

    try:
        if key in ROUND_TO_COLUMN_PRECISION:
            value = value.quantize(Decimal(1).scaleb(-mf.decimal_places), rounding=ROUND_HALF_UP)
        else:
            value = value.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise _Invalid("Out of range.") from exc
    try:
        mf.run_validators(value)
    except DjangoValidationError as exc:
        raise _Invalid(exc.messages[0]) from exc
    return value


def _coerce_boolean(raw, mf):
    if raw is None and mf.null:
        return None
    if not isinstance(raw, bool):
        raise _Invalid("Must be true or false.")
    return raw


def _coerce_date(raw, mf):
    if raw is None or raw == "":
        if mf.null:
            return None
        raise _Invalid("A date is required.")
    try:
        return mf.to_python(raw)
    except DjangoValidationError as exc:
        raise _Invalid("Enter a valid date (YYYY-MM-DD).") from exc


def _coerce_datetime(raw, mf):
    if raw is None or raw == "":
        if mf.null:
            return None
        raise _Invalid("A date and time are required.")
    value = parse_datetime(raw) if isinstance(raw, str) else None
    if value is None:
        raise _Invalid("Enter a valid date and time.")
    return timezone.make_aware(value) if timezone.is_naive(value) else value


def _coerce_select(raw, field, mf, current):
    if mf.is_relation:
        return _coerce_record(raw, field, mf)
    if raw is None or raw == "":
        return ""
    if not isinstance(raw, str):
        raise _Invalid("Must be text.")
    value = raw.strip()
    allowed = _allowed_values(field, mf)
    # A stored value whose preset was later deactivated stays savable.
    if allowed is not None and value not in allowed and value != current:
        raise _Invalid("Not one of the available options.")
    mf.run_validators(value)
    return value


def _coerce_record(raw, field, mf):
    """FK to a master record (bank, report template) or a user."""
    if raw is None or raw == "":
        if mf.null:
            return None
        raise _Invalid("A value is required.")
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise _Invalid("Must be an id.")
    related = mf.related_model
    if related is get_user_model():
        exists = related.objects.filter(pk=raw, is_active=True).exists()
    elif related is Bank:
        exists = Bank.objects.filter(pk=raw, active=True).exists()
    elif related is ReportTemplate:
        exists = ReportTemplate.objects.filter(pk=raw, active=True).exists()
    else:
        exists = related.objects.filter(pk=raw).exists()
    if not exists:
        raise _Invalid("No such record.")
    return raw


def _coerce_multiselect(raw, field, mf, current):
    if raw is None:
        raw = []
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise _Invalid("Must be a list of options.")
    value = list(dict.fromkeys(v.strip() for v in raw if v.strip()))
    if field.get("custom"):
        # Typed-in entries are kept as typed, beside the listed options.
        if any(len(v) > 100 for v in value):
            raise _Invalid("A custom entry can be at most 100 characters.")
        return value
    allowed = _allowed_values(field, mf)
    if allowed is not None:
        stale = set(current or [])
        unknown = [v for v in value if v not in allowed and v not in stale]
        if unknown:
            raise _Invalid(f"Not available: {', '.join(unknown)}.")
    return value


def _coerce_storeys(raw) -> dict:
    """{storey: [rooms]}: listed rooms by key, custom ones as typed."""
    from .constants import STOREYS

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _Invalid("Must be rooms by storey.")
    known = {key for key, _ in STOREYS}
    cleaned = {}
    for storey, rooms in raw.items():
        if storey not in known:
            raise _Invalid(f"Unknown storey: {storey}.")
        if not isinstance(rooms, list) or not all(isinstance(r, str) for r in rooms):
            raise _Invalid("Each storey needs a list of rooms.")
        rooms = list(dict.fromkeys(r.strip() for r in rooms if r.strip()))
        if any(len(r) > 100 for r in rooms):
            raise _Invalid("A custom entry can be at most 100 characters.")
        if rooms:
            cleaned[storey] = rooms
    return cleaned


def _coerce_names(raw, mf):
    """One or more names (owners, applicants), stored one per line."""
    if raw is None:
        raw = []
    if isinstance(raw, str):
        raw = raw.splitlines()
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise _Invalid("Must be a list of names.")
    names = [v.strip() for v in raw if v.strip()]
    if any(len(n) > 255 for n in names):
        raise _Invalid("A name can be at most 255 characters.")
    return "\n".join(names)


def _coerce_library(raw, mf, multiline=True):
    """Library fields hold report text: plain text on most tabs, or a list
    of {title, body} entries where the valuer picks several (special
    assumptions, other matters)."""
    if isinstance(mf, models.JSONField):
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise _Invalid("Must be a list of entries.")
        entries = []
        for entry in raw:
            if not isinstance(entry, dict) or not isinstance(entry.get("title"), str) \
                    or not isinstance(entry.get("body", ""), str):
                raise _Invalid("Each entry needs a title and body.")
            entries.append({"title": entry["title"], "body": entry.get("body", "")})
        return entries
    return _coerce_text(raw, mf, multiline)


AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)"
AMOUNT_OR_RANGE = re.compile(rf"^({AMOUNT})(?:\s*[-\u2013]\s*({AMOUNT}))?$")
# Text fields that hold an amount or a range of amounts.
AMOUNT_RANGE_FIELDS = {"market_rent"}


def _coerce_amount_or_range(raw) -> str:
    """'40000' -> '40,000'; '30,000 - 50,000' -> '30,000–50,000'. Digits,
    thousands separators and one hyphen only (CRM feedback VL-05)."""
    if raw is None or raw == "":
        return ""
    if isinstance(raw, bool) or not isinstance(raw, str | int):
        raise _Invalid("Must be a figure or a range.")
    match = AMOUNT_OR_RANGE.match(str(raw).strip())
    if not match:
        raise _Invalid("Enter a figure (40,000) or a range (30,000-50,000): digits, commas and one hyphen.")
    low = int(match.group(1).replace(",", ""))
    if match.group(2) is None:
        return f"{low:,}"
    high = int(match.group(2).replace(",", ""))
    if high <= low:
        raise _Invalid("The second figure of a range must be the higher one.")
    return f"{low:,}–{high:,}"


def coerce(field: dict, mf, raw, current):
    """One submitted value -> the Python value to store, or raises _Invalid."""
    kind = field["type"]
    if field["key"] in AMOUNT_RANGE_FIELDS:
        return _coerce_amount_or_range(raw)
    try:
        if kind == "text":
            return _coerce_text(raw, mf, multiline=False)
        if kind == "textarea":
            return _coerce_text(raw, mf, multiline=True)
        if kind == "number":
            return _coerce_number(raw, mf)
        if kind == "decimal":
            return _coerce_decimal(raw, mf, field["key"])
        if kind == "boolean":
            return _coerce_boolean(raw, mf)
        if kind == "date":
            return _coerce_date(raw, mf)
        if kind == "datetime":
            return _coerce_datetime(raw, mf)
        if kind == "select":
            return _coerce_select(raw, field, mf, current)
        if kind == "multiselect":
            return _coerce_multiselect(raw, field, mf, current)
        if kind == "user":
            return _coerce_record(raw, field, mf)
        if kind == "library":
            return _coerce_library(raw, mf)
        if kind == "names":
            return _coerce_names(raw, mf)
        if kind == "storeys":
            return _coerce_storeys(raw)
    except DjangoValidationError as exc:
        raise _Invalid(exc.messages[0]) from exc
    raise _Invalid(f"Unsupported field type {kind!r}.")


# --- writing ------------------------------------------------------------------


# What the peer reviewer may change during review (CRM feedback PR-01):
# everything the report prints above the Appendix, figures included. Not the
# team on the job (who works on it isn't report content), nor the Scheduling
# stage (not in the report). Every change is kept and the valuer accepts them
# before sign-off.
REVIEWER_TABS = ("instructions", "address", "checklist", "summary", "inspection", "location", "valuation")


def reviewer_fields(tab_key) -> set[str]:
    if tab_key not in REVIEWER_TABS:
        return set()
    return {
        f["key"] for f in get_tab(tab_key)["fields"]
        if not f["calculated"] and f["key"] not in ASSIGNMENT_FIELDS
    }


def reviewing(user, job) -> bool:
    """The assigned peer reviewer, while the job is with them."""
    return job.status == JobStatus.PEER_REVIEW and Role.PEER_REVIEWER in roles_on_job(user, job)


def edit_denial(user, job, tab_key) -> TabError | None:
    """Why `user` can't edit this tab right now, or None if they can.

    The one place this is decided: the PATCH endpoint enforces it and the job
    detail reports it, so the UI never offers an edit the server will refuse."""
    if not job.is_locked and reviewing(user, job) and reviewer_fields(tab_key):
        return None  # the wording only; patch_tab refuses anything else
    if is_platform_admin(user):
        role_ok = True
    else:
        role_ok = bool(roles_on_job(user, job) & TAB_EDIT_ROLES[tab_key])
    if not role_ok:
        return NotPermitted(f"Your role on this job doesn't allow editing the {get_tab(tab_key)['label']} tab.")
    if job.is_locked:
        return JobIsLocked("This job has been issued and is locked. Create a revision to amend it.")
    if job.status in FROZEN_STATUSES:
        return JobIsFrozen(
            "This job is in review or signed off, so its data is frozen. "
            "Return it to the valuer to make changes."
        )
    return None


def may_assign(user, job) -> bool:
    return is_platform_admin(user) or bool(roles_on_job(user, job) & ASSIGNMENT_ROLES)


def _check_may_assign(user, job, field_keys):
    if ASSIGNMENT_FIELDS & set(field_keys) and not may_assign(user, job):
        raise NotPermitted("Only the admin or valuer on this job can change who is assigned to it.")


def _validated(job, tab_key, data):
    fields = {f["key"]: f for f in get_tab(tab_key)["fields"]}
    targets = _targets(job, tab_key, create=True)
    cleaned, errors = {}, {}
    for key, raw in data.items():
        field = fields.get(key)
        if field is None:
            errors[key] = "Unknown field."
            continue
        if field["calculated"]:
            errors[key] = "Calculated automatically; it can't be set."
            continue
        target, mf = resolve_storage(tab_key, key)
        current = getattr(targets[target], mf.attname)
        try:
            cleaned[key] = (target, mf, coerce(field, mf, raw, current))
        except _Invalid as exc:
            errors[key] = str(exc)
    if errors:
        raise ValidationFailed(errors)
    return targets, cleaned


def _follow_bank_billing_address(job, old_bank_id, supplied):
    """Billing address comes from the Bank master once its SLA is signed
    (CLAUDE.md §4 Tab 2). Replace it on a bank change only if it was still
    the old bank's untouched address — never overwrite one typed by hand."""
    if "billing_address" in supplied or job.bank_id == old_bank_id:
        return
    old = Bank.objects.filter(pk=old_bank_id).first()
    if job.billing_address and (old is None or job.billing_address != old.billing_address):
        return
    bank = job.bank
    job.billing_address = bank.billing_address if bank and bank.sla_signed else ""


def _record_reviewer_edits(job, tab_key, user, before, cleaned) -> None:
    """Field, old and new value, who and when (CRM feedback PR-01)."""
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    def plain(value):  # figures and dates as text, so they can be kept as JSON
        return json.loads(json.dumps(value, cls=DjangoJSONEncoder))

    labels = {f["key"]: f["label"] for f in get_tab(tab_key)["fields"]}
    for key, (_, _, value) in cleaned.items():
        if before[key] != value:
            ReviewerEdit.objects.create(job=job, tab_key=tab_key, field_key=key, label=labels.get(key, key),
                                        old_value=plain(before[key]), new_value=plain(value), by=user)


def accept_reviewer_edits(job_id: int, user) -> int:
    """The valuer (or an admin) accepts the reviewer's changes; returns how many."""
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if not (is_platform_admin(user) or Role.VALUER in roles_on_job(user, job)):
            raise NotPermitted("Only the valuer on this job can accept the reviewer's changes.")
        return job.reviewer_edits.filter(accepted_at__isnull=True).update(
            accepted_at=timezone.now(), accepted_by=user
        )


def _log_call(job, scheduling, user, cleaned) -> None:
    """Each save on Scheduling is one call attempt in the log; a booked date
    also becomes the inspection date if none is entered yet (CRM feedback SC-04)."""
    if not {"call_status", "call_remark", "inspection_booked_at"} & cleaned.keys():
        return
    booked = scheduling.inspection_booked_at if scheduling.call_status == "answered_scheduled" else None
    CallAttempt.objects.create(job=job, status=scheduling.call_status, remark=scheduling.call_remark,
                               booked_for=booked, by=user)
    if booked:
        inspection = job.inspection
        if inspection.inspection_date is None:
            inspection.inspection_date = timezone.localtime(booked).date() if timezone.is_aware(booked) \
                else booked.date()
            inspection.save(update_fields=["inspection_date"])


def set_report_exclusions(job_id: int, user, excluded) -> list[str]:
    """Which fields stay out of the report (the include-in-report step, on
    leaving the Valuation stage). Whoever may edit the Valuation tab may set
    it, under the same lock and freeze rules as any edit."""
    from .field_config import REPORT_OPTIONAL

    allowed = {f"{tab}.{key}" for tab, keys in REPORT_OPTIONAL.items() for key in keys}
    if not isinstance(excluded, list) or not all(isinstance(k, str) for k in excluded):
        raise TabError("`excluded` must be a list of field keys.")
    unknown = sorted(set(excluded) - allowed)
    if unknown:
        raise ValidationFailed({"excluded": f"Not a report field: {', '.join(unknown)}."})
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if denial := edit_denial(user, job, "valuation"):
            raise denial
        job.report_exclusions = sorted(set(excluded))
        job.save(update_fields=["report_exclusions", "updated_at"])
    return job.report_exclusions


def _follow_bank_reference(job, old_bank_id, supplied):
    """Picking a bank fills the Bank Reference No. with the bank's own code
    (bank master). Only an empty reference, or the old bank's code left
    untouched, is replaced: a reference typed by hand stays."""
    if "bank_reference_no" in supplied or job.bank_id == old_bank_id:
        return
    old = Bank.objects.filter(pk=old_bank_id).first()
    if job.bank_reference_no and (old is None or job.bank_reference_no != old.code):
        return
    job.bank_reference_no = job.bank.code if job.bank else ""


def patch_tab(job_id: int, tab_key: str, user, values: dict, base_version: int, *, intake: bool = False) -> dict:
    """Applies a partial update to one tab, atomically.

    Order matters: the cheap checks (tab, role) come first, then everything
    that depends on current state runs under a row lock on the job so two
    simultaneous saves, or a save racing an issue, are serialised."""
    try:
        tab = get_tab(tab_key)
    except KeyError as exc:
        raise UnknownTab(f"No such tab: {tab_key}.") from exc
    if not tab["fields"]:
        raise UnknownTab(f"The {tab['label']} tab has no editable fields.")
    if not isinstance(values, dict) or not values:
        raise TabError("`values` must be a non-empty object.")

    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)

        # The New instruction form sets a few fields on tabs the creator won't
        # edit afterwards (the team, the property category): whoever may create
        # the job may set those once. Every later edit follows the tab's roles.
        if intake:
            if job.is_locked:
                raise JobIsLocked("This job has been issued and is locked.")
        else:
            if denial := edit_denial(user, job, tab_key):
                raise denial
            if reviewing(user, job):
                if beyond := sorted(set(values) - reviewer_fields(tab_key)):
                    raise NotPermitted(
                        "During review the peer reviewer can change the report's content, not who works on "
                        f"the job: {', '.join(beyond)}."
                    )
            else:
                _check_may_assign(user, job, values.keys())

        version, _ = JobTabVersion.objects.get_or_create(job=job, tab_key=tab_key)
        if version.version != base_version:
            raise VersionConflict(
                "Someone else saved this tab first. Your changes were not applied.",
                current=job_tab_state(job)[tab_key],
            )

        job.tracker_coi_check = job.coi_check  # before this save changes it
        targets, cleaned = _validated(job, tab_key, values)
        old_bank_id = job.bank_id

        touched = set()
        before = {key: getattr(targets[t], mf.attname) for key, (t, mf, _) in cleaned.items()}
        for target, mf, value in cleaned.values():
            setattr(targets[target], mf.attname, value)
            touched.add(target)
        if not intake and reviewing(user, job):
            _record_reviewer_edits(job, tab_key, user, before, cleaned)
        if "coi_check" in cleaned and cleaned["coi_check"][2] != (job.tracker_coi_check or ""):
            # Who confirmed the COI result, and when (CRM feedback LG-01).
            job.coi_confirmed_by, job.coi_confirmed_at = user, timezone.now()
            touched.add("job")
        if tab_key == "scheduling":
            _log_call(job, targets["tab"], user, cleaned)
        if "bua_sqm" in cleaned and cleaned["bua_sqm"][2] is None:
            targets["tab"].bua_sqft = None  # sqft follows sqm, cleared too

        if "bank" in cleaned:
            _follow_bank_billing_address(job, old_bank_id, cleaned)
            _follow_bank_reference(job, old_bank_id, cleaned)

        try:
            for target in touched | ({"job"} if "bank" in cleaned else set()):
                targets[target].save()
        except JobLockedError as exc:  # e.g. a property shared with an issued job
            raise JobIsLocked(str(exc)) from exc

        version.version += 1
        version.save(update_fields=["version"])

        from .transitions import sync_stage  # transitions imports this module

        sync_stage(job, user)

        state = job_tab_state(Job.objects.get(pk=job_id))

    return {
        "tab": tab_key,
        # Completing a stage's tabs can move the job on (transitions.sync_stage).
        "status": job.status,
        "values": state[tab_key]["values"],
        "version": state[tab_key]["version"],
        "computed": {k: v["computed"] for k, v in state.items()},
        "completion": {k: v["completion"] for k, v in state.items()},
    }
