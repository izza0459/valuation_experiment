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
    ChecklistData,
    InspectionData,
    Job,
    JobTabVersion,
    LocationData,
    Property,
    SummaryData,
    ValuationData,
)
from .workflow import FROZEN_STATUSES, JobLockedError

TAB_MODELS = {
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
TAB_EDIT_ROLES = {
    "checklist": {Role.INSPECTOR, Role.VALUER},
    "instructions": {Role.ADMIN, Role.VALUER},
    "address": {Role.ADMIN, Role.VALUER},
    "summary": {Role.VALUER},
    "inspection": {Role.INSPECTOR, Role.VALUER},
    "location": {Role.VALUER},
    "valuation": {Role.VALUER},
    # Photos and documents have no form fields; their uploads, captions and
    # ordering are checked against the same rules (see apps/media_files).
    "photos": {Role.INSPECTOR, Role.VALUER},
    "documents": {Role.ADMIN, Role.VALUER},
}

MEDIA_TABS = ("photos", "documents")

# Fields that decide who works on the job. Sitting on the inspector's Check
# List tab must not let the inspector reassign the valuer.
ASSIGNMENT_FIELDS = {"inspected_by", "valuer", "peer_reviewer", "counter_signatory", "registered_valuer"}
ASSIGNMENT_ROLES = {Role.ADMIN, Role.VALUER}

# Coordinates are pasted from Google Maps with more decimals than the column
# keeps. Rounding them to the column's precision (~0.1 m) is harmless; for
# money it is not, so every other decimal field rejects excess precision
# instead of silently rounding.
ROUND_TO_COLUMN_PRECISION = {"latitude", "longitude"}

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
        values[f["key"]] = getattr(targets[target], mf.attname)
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
    if op == "is_true":
        return bool(actual)
    return True


def _is_empty(value) -> bool:
    return value is None or value == "" or value == []


def visibility_context(job) -> dict:
    context = {tab["key"]: tab_values(job, tab["key"]) for tab in TABS if tab["fields"]}
    context["bank"] = {"name": job.bank.name, "rules": job.bank.rules or {}}
    return context


def tab_completion(tab_key: str, context: dict) -> dict:
    """Share of the *visible required* fields that are filled in.

    Hidden fields never count, so a conditional field the job will never need
    (plot area on an apartment) can't hold a tab below 100%."""
    values = context.get(tab_key, {})
    required = [
        f for f in get_tab(tab_key)["fields"] if f["required"] and is_field_visible(f, context)
    ]
    if not required:
        return {"pct": 100, "missing": []}
    missing = [f["label"] for f in required if _is_empty(values.get(f["key"]))]
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
            has_form = bool(get_tab(key)["fields"]) or key in MEDIA_TABS
            denial = edit_denial(user, job, key) if has_form else None
            tab_state["can_edit"] = has_form and denial is None
            tab_state["read_only_reason"] = denial.detail if denial else ""
            # Fields on an otherwise editable tab that this user may not change.
            tab_state["read_only_fields"] = (
                [] if may_assign(user, job)
                else [f["key"] for f in get_tab(key)["fields"] if f["key"] in ASSIGNMENT_FIELDS]
            )
    return state


# --- validation ---------------------------------------------------------------


class _Invalid(Exception):
    pass


def _allowed_values(field: dict, mf) -> list | None:
    """The option values a select accepts, or None when anything goes
    (free-text fields, and keys an admin hasn't populated yet)."""
    if field["free_text"] or not field["options_key"]:
        return None
    options = options_for(field["options_key"])
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
        if isinstance(raw, float) and not raw.is_integer():
            raise _Invalid("Must be a whole number.")
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise _Invalid("Must be a whole number.") from exc
    mf.run_validators(value)
    return value


def _coerce_decimal(raw, mf, key):
    if raw is None or raw == "":
        if mf.null:
            return None
        raise _Invalid("A value is required.")
    if isinstance(raw, bool):
        raise _Invalid("Must be a number.")
    try:
        # str() first: Decimal(48.2) would carry the float's binary noise.
        value = Decimal(str(raw).strip())
    except InvalidOperation as exc:
        raise _Invalid("Must be a number.") from exc
    if not value.is_finite():
        raise _Invalid("Must be a number.")

    low, high = DECIMAL_RANGES.get(key, (None if key in SIGNED_DECIMALS else Decimal(0), None))
    if (low is not None and value < low) or (high is not None and value > high):
        if low is not None and high is not None:
            raise _Invalid(f"Must be between {low} and {high}.")
        raise _Invalid("Can't be negative.")

    if key in ROUND_TO_COLUMN_PRECISION:
        try:
            value = value.quantize(Decimal(1).scaleb(-mf.decimal_places), rounding=ROUND_HALF_UP)
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
    allowed = _allowed_values(field, mf)
    if allowed is not None:
        stale = set(current or [])
        unknown = [v for v in value if v not in allowed and v not in stale]
        if unknown:
            raise _Invalid(f"Not available: {', '.join(unknown)}.")
    return value


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


def coerce(field: dict, mf, raw, current):
    """One submitted value -> the Python value to store, or raises _Invalid."""
    kind = field["type"]
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
    except DjangoValidationError as exc:
        raise _Invalid(exc.messages[0]) from exc
    raise _Invalid(f"Unsupported field type {kind!r}.")


# --- writing ------------------------------------------------------------------


def edit_denial(user, job, tab_key) -> TabError | None:
    """Why `user` can't edit this tab right now, or None if they can.

    The one place this is decided: the PATCH endpoint enforces it and the job
    detail reports it, so the UI never offers an edit the server will refuse."""
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
    job.billing_address = job.bank.billing_address if job.bank.sla_signed else ""


def patch_tab(job_id: int, tab_key: str, user, values: dict, base_version: int) -> dict:
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

        if denial := edit_denial(user, job, tab_key):
            raise denial
        _check_may_assign(user, job, values.keys())

        version, _ = JobTabVersion.objects.get_or_create(job=job, tab_key=tab_key)
        if version.version != base_version:
            raise VersionConflict(
                "Someone else saved this tab first. Your changes were not applied.",
                current=job_tab_state(job)[tab_key],
            )

        targets, cleaned = _validated(job, tab_key, values)
        old_bank_id = job.bank_id

        touched = set()
        for target, mf, value in cleaned.values():
            setattr(targets[target], mf.attname, value)
            touched.add(target)

        if "bank" in cleaned:
            _follow_bank_billing_address(job, old_bank_id, cleaned)

        try:
            for target in touched | ({"job"} if "bank" in cleaned else set()):
                targets[target].save()
        except JobLockedError as exc:  # e.g. a property shared with an issued job
            raise JobIsLocked(str(exc)) from exc

        version.version += 1
        version.save(update_fields=["version"])

        state = job_tab_state(Job.objects.get(pk=job_id))

    return {
        "tab": tab_key,
        "values": state[tab_key]["values"],
        "version": state[tab_key]["version"],
        "computed": {k: v["computed"] for k, v in state.items()},
        "completion": {k: v["completion"] for k, v in state.items()},
    }
