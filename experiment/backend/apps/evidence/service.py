"""The Evidence tab: comparables the valuer enters and ticks for the report,
and the AVM that runs on the ticked ones (CLAUDE.md §6).

Manual entry comes first. Connectors (DLD open data, then Bayut and Property
Monitor) will add `Comparable` rows with their own `source` and `source_ref`,
and everything here works on them unchanged.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction

from apps.audit.middleware import acting_as
from apps.jobs.models import Job
from apps.jobs.tabs import TabError, ValidationFailed, edit_denial

from . import avm
from .models import AVMRun, Comparable, JobComparable

TEXT_FIELDS = {"building_name": 255, "community_name": 255, "property_type": 60, "floor": 50, "view": 100}
EDITABLE = {*TEXT_FIELDS, "source", "link", "beds", "bua_sqft", "price_aed", "transaction_date", "status", "notes"}


class NotFound(TabError):
    status = 404
    code = "not_found"


# --- reading --------------------------------------------------------------------


def describe(link: JobComparable) -> dict:
    c = link.comparable
    rate = c.price_per_sqft
    return {
        "id": link.id,
        "selected": link.selected,
        "source": c.source,
        "source_label": c.get_source_display(),
        "link": c.link,
        "building_name": c.building_name,
        "community_name": c.community_name,
        "property_type": c.property_type,
        "beds": c.beds,
        "floor": c.floor,
        "view": c.view,
        "bua_sqft": str(c.bua_sqft) if c.bua_sqft is not None else None,
        "price_aed": str(c.price_aed) if c.price_aed is not None else None,
        "aed_per_sqft": str(rate.quantize(Decimal("0.01"))) if rate else None,
        "transaction_date": c.transaction_date,
        "status": c.status,
        "notes": c.notes,
    }


def describe_run(run: AVMRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "suggested_value": f"{run.suggested_value:.2f}",
        "low_value": f"{run.low_value:.2f}",
        "high_value": f"{run.high_value:.2f}",
        "aed_per_sqft": f"{run.aed_per_sqft:.2f}",
        "confidence": run.confidence,
        "workings": run.workings,
        "created_at": run.created_at,
        "created_by": str(run.created_by) if run.created_by else "",
    }


def evidence_state(job) -> dict:
    links = job.job_comparables.select_related("comparable")
    return {
        "comparables": [describe(link) for link in links],
        "avm": describe_run(job.avm_runs.filter(job_version=job.version).first()),
        "sources": [{"value": v, "label": label} for v, label in Comparable.SOURCE_CHOICES
                    if v in Comparable.ENTRY_SOURCES],
    }


# --- validation -------------------------------------------------------------------


def _clean(data: dict, *, partial: bool) -> dict:
    if not isinstance(data, dict):
        raise TabError("Send the comparable's details as an object.")
    errors, cleaned = {}, {}
    for key in data:
        if key not in EDITABLE:
            errors[key] = "Unknown field."
    for key, raw in data.items():
        if key in errors:
            continue
        try:
            cleaned[key] = _clean_one(key, raw)
        except ValueError as exc:
            errors[key] = str(exc)
    if not partial:
        for key in ("source", "price_aed", "bua_sqft"):
            if cleaned.get(key) in (None, ""):
                errors.setdefault(key, "Required.")
    if errors:
        raise ValidationFailed(errors)
    return cleaned


def _clean_one(key, raw):
    if key in TEXT_FIELDS:
        value = (raw or "").strip() if isinstance(raw, str) or raw is None else None
        if value is None:
            raise ValueError("Must be text.")
        if len(value) > TEXT_FIELDS[key]:
            raise ValueError(f"At most {TEXT_FIELDS[key]} characters.")
        return value
    if key == "notes":
        if raw is not None and not isinstance(raw, str):
            raise ValueError("Must be text.")
        return (raw or "").strip()
    if key == "source":
        if raw not in Comparable.ENTRY_SOURCES:
            raise ValueError("Choose where this comparable comes from.")
        return raw
    if key == "status":
        if raw not in ("sold", "asking"):
            raise ValueError("Sold or asking.")
        return raw
    if key == "link":
        value = (raw or "").strip() if isinstance(raw, str) or raw is None else None
        if value is None:
            raise ValueError("Must be a link.")
        if value:
            try:
                URLValidator(schemes=["http", "https"])(value)
            except ValidationError as exc:
                raise ValueError("Enter a full link starting with http:// or https://.") from exc
        return value
    if key == "beds":
        if raw in (None, ""):
            return None
        if isinstance(raw, bool) or not str(raw).isdigit() or int(raw) > 50:
            raise ValueError("Must be a whole number.")
        return int(raw)
    if key in ("bua_sqft", "price_aed"):
        if raw in (None, ""):
            return None
        try:
            value = Decimal(str(raw).replace(",", "").strip())
        except InvalidOperation as exc:
            raise ValueError("Must be a number.") from exc
        if not value.is_finite() or value <= 0:
            raise ValueError("Must be more than zero.")
        return value.quantize(Decimal("0.01"))
    if key == "transaction_date":
        if raw in (None, ""):
            return None
        try:
            return date.fromisoformat(raw) if isinstance(raw, str) else None
        except ValueError as exc:
            raise ValueError("Enter a valid date (YYYY-MM-DD).") from exc
    raise ValueError("Unknown field.")


# --- writing ------------------------------------------------------------------------


def _check(job, user):
    if denial := edit_denial(user, job, "evidence"):
        raise denial


def add_comparable(job_id: int, user, data: dict) -> dict:
    cleaned = _clean(data, partial=False)
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        _check(job, user)
        comparable = Comparable.objects.create(created_by=user, **cleaned)
        order = job.job_comparables.count()
        link = JobComparable.objects.create(job=job, comparable=comparable, selected=True, order=order)
    return describe(link)


def _link(job, link_id) -> JobComparable:
    link = job.job_comparables.select_related("comparable").filter(pk=link_id).first()
    if link is None:
        raise NotFound("No such comparable on this job.")
    return link


def update_comparable(job_id: int, user, link_id: int, data: dict) -> dict:
    data = dict(data) if isinstance(data, dict) else {}
    selected = data.pop("selected", None)
    if selected is not None and not isinstance(selected, bool):
        raise ValidationFailed({"selected": "Must be true or false."})
    cleaned = _clean(data, partial=True)
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        _check(job, user)
        link = _link(job, link_id)
        if cleaned:
            comparable = link.comparable
            if comparable.job_links.exclude(job=job).exists():
                raise TabError("This comparable is also used by another job, so it can't be edited here.")
            for key, value in cleaned.items():
                setattr(comparable, key, value)
            comparable.save()
        if selected is not None:
            link.selected = selected
            link.save(update_fields=["selected"])
    return describe(link)


def remove_comparable(job_id: int, user, link_id: int) -> None:
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        _check(job, user)
        link = _link(job, link_id)
        comparable = link.comparable
        link.delete()
        # Typed in for a job and now used by none: nothing left to keep. Rows a
        # connector imported (no `created_by`) stay for other jobs to use.
        if comparable.created_by_id and not comparable.job_links.exists():
            comparable.delete()


def run_avm(job_id: int, user) -> dict:
    with acting_as(user), transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        _check(job, user)
        chosen = [link.comparable for link in job.job_comparables.select_related("comparable") if link.selected]
        result = avm.compute(chosen, job.summary.bua_sqft, job.valuation.market_value)
        if "error" in result:
            raise ValidationFailed({"avm": result["error"]})
        run = AVMRun.objects.create(
            job=job,
            job_version=job.version,
            inputs={"comparable_ids": [c.id for c in chosen], "adjustments": []},
            created_by=user,
            **result,
        )
    return describe_run(run)
