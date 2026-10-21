"""Logging a call on the Scheduling stage (CRM feedback SC-03, SC-04).

A call is saved as one unit, with the Save call button: its status, the
remark (needed unless the inspection was booked) and the booked date and time
(needed when it was). Each save is one entry in the call log; typing in the
form logs nothing. It goes through the same write path as any tab edit, so
permissions, the audit trail and moving the job to Inspection all apply.
"""

from __future__ import annotations

from .models import JobTabVersion, SchedulingData
from .tabs import ValidationFailed, patch_tab

NEEDS_REMARK = {SchedulingData.ANSWERED_NOT_SCHEDULED, SchedulingData.UNABLE_TO_CONTACT}


def log_call(job_id: int, user, data) -> dict:
    data = data if isinstance(data, dict) else {}
    status = data.get("call_status") or ""
    remark = (data.get("call_remark") or "").strip() if isinstance(data.get("call_remark"), str) else ""
    booked = data.get("inspection_booked_at") or None

    errors = {}
    if status not in dict(SchedulingData.CALL_STATUS_CHOICES) or status == SchedulingData.NOT_CALLED:
        errors["call_status"] = "Choose how the call went."
    if status in NEEDS_REMARK and not remark:
        errors["call_remark"] = "Add a remark: why it isn't booked, or when to call back."
    if status == SchedulingData.ANSWERED_SCHEDULED and not booked:
        errors["inspection_booked_at"] = "Enter the inspection date and time."
    if errors:
        raise ValidationFailed(errors)

    values = {
        "call_status": status,
        "call_remark": remark,
        "inspection_booked_at": booked if status == SchedulingData.ANSWERED_SCHEDULED else None,
    }
    version = JobTabVersion.objects.filter(job_id=job_id, tab_key="scheduling").values_list("version", flat=True)
    return patch_tab(job_id, "scheduling", user, values, base_version=version.first() or 0)
