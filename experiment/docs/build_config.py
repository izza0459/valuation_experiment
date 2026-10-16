"""Builds docs/Valuation Platform - Config.xlsx from the app's own config, in the
layout of the Carforce flow config (Flows, Flow Stages, Next Stages, Fields
Config, Lead Fields, Field Types, Statuses, reasons, Dispositions) plus the
valuation-specific sheets. Run from experiment/backend:

    DEBUG=true .venv/Scripts/python.exe ../docs/build_config.py "../docs/Valuation Platform - Config.xlsx"
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DEBUG", "true")
import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from apps.accounts.models import Role  # noqa: E402
from apps.evidence.models import Comparable  # noqa: E402
from apps.jobs import intake, tabs, transitions, workflow  # noqa: E402
from apps.jobs.constants import PLOT_BEARING_CATEGORIES, TENANTED_OCCUPANCIES  # noqa: E402
from apps.jobs.field_config import STAGES, TABS  # noqa: E402
from apps.media_files import checks, processing  # noqa: E402
from apps.presets.management.commands import seed_presets as seed  # noqa: E402
from apps.presets.options import LIBRARY_CATEGORIES, RECORD_KEYS  # noqa: E402

OUT = sys.argv[1]
GROUP = "Valuation"
FLOW = "Valuation - Bank Mortgage"
STATUS_LABELS = dict(workflow.JobStatus.CHOICES)
STAGE_LABEL = {s["key"]: s["label"] for s in STAGES}
ROLE_LABEL = dict(Role.choices)

FONT = Font(name="Arial", size=10)
BOLD = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="B00020")
NOTE = Font(name="Arial", size=10, italic=True, color="555555")
TITLE = Font(name="Arial", size=14, bold=True)
THIN = Border(bottom=Side(style="thin", color="DDDDDD"))
WRAP = Alignment(wrap_text=True, vertical="top")

wb = Workbook()
wb.remove(wb.active)


def sheet(name, headers, rows, widths=None, note=None):
    ws = wb.create_sheet(name)
    start = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = NOTE
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        ws.row_dimensions[1].height = 30
        ws.cell(row=1, column=1).alignment = WRAP
        start = 2
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start, column=c, value=h)
        cell.font, cell.fill, cell.alignment = BOLD, HEAD_FILL, WRAP
    for r, row in enumerate(rows, start + 1):
        for c, value in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.font, cell.alignment, cell.border = FONT, WRAP, THIN
    ws.freeze_panes = ws.cell(row=start + 1, column=1)
    for c, h in enumerate(headers, 1):
        width = (widths or {}).get(h)
        if width is None:
            longest = max([len(str(h))] + [min(len(str(r[c - 1] or "")), 60) for r in rows]) if rows else len(h)
            width = min(max(longest + 2, 10), 60)
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.auto_filter.ref = f"A{start}:{get_column_letter(len(headers))}{start + len(rows)}"
    return ws


def labels_for(entries):
    return [e if isinstance(e, str) else e[0] for e in entries]


def values_for(entries):
    return [seed._slug(e) if isinstance(e, str) else e[1] for e in entries]


# Carforce-style type for each of the app's field types.
TYPE_MAP = {
    "text": ("string", "Short text, one line"),
    "textarea": ("text", "Long text, several lines"),
    "number": ("integer", "Whole number"),
    "decimal": ("price / decimal", "Number with decimals (money, areas, coordinates)"),
    "boolean": ("boolean", "Yes or No"),
    "date": ("date", "Date only"),
    "datetime": ("datetime", "Date and time"),
    "select": ("single-select", "One option from a list (presets, bank master or report templates)"),
    "multiselect": ("multi-select", "Several options from a list"),
    "user": ("user", "A person on the team (drives who works on the job)"),
    "library": ("text-library", "Report text chosen from the text library, then edited for this job"),
}


def rule_text(rule):
    if not rule:
        return ""
    field = rule["field"]
    op = rule["op"]
    if op == "in":
        return f"Only when {field} is one of: {', '.join(map(str, rule['value']))}"
    if op == "eq":
        return f"Only when {field} = {rule['value']}"
    if op == "is_true":
        return f"Only when {field} is set"
    return str(rule)


def possible_values(f):
    key = f["options_key"]
    if not key:
        return "", ""
    if key in RECORD_KEYS:
        return key, "From the Bank master" if key == "bank" else "Report templates (Django admin)"
    if key in seed.PRESETS:
        return key, " | ".join(labels_for(seed.PRESETS[key]))
    if key in seed.PRESET_TEXT:
        return key, " | ".join(label for label, _ in seed.PRESET_TEXT[key])
    category = LIBRARY_CATEGORIES.get(key)
    if category and category in seed.LIBRARY:
        titles = seed.LIBRARY[category]
        return key, " | ".join(titles) if titles else "Text library (empty until an admin adds entries)"
    if key in ("sub_community", "location"):
        return key, "Per-community text presets (admin-added)"
    return key, "Presets (admin-editable)"


def storage(tab_key, f):
    if f["calculated"]:
        return "Calculated by the server"
    target, mf = tabs.resolve_storage(tab_key, f["key"])
    model = {"tab": mf.model.__name__, "job": "Job", "property": "Property"}[target]
    return f"{model}.{mf.name}"


# --- README ---------------------------------------------------------------------------
ws = wb.create_sheet("README")
lines = [
    ("Valuation Platform — Flow & Field Config", TITLE),
    (f"Generated from the app's code on {date.today():%d %b %Y} (commit after ef42e50). Same layout as the Carforce flow config.", NOTE),
    ("", FONT),
    ("How to read this workbook", Font(name="Arial", size=11, bold=True)),
    ("Flows — the one valuation flow and what starts it.", FONT),
    ("Flow Stages — the five stages a job moves through (Setup → Inspection → Valuation → Review → Send to bank), who owns each, the sections (tabs) in it and how it moves on.", FONT),
    ("Next Stages — every move between job statuses: who can make it, what blocks it, and whether it's automatic.", FONT),
    ("Fields Config — every form field: stage, section, label, type, list of options, required, when it shows, and where it is stored.", FONT),
    ("Lead Fields — what the New instruction screen asks for.", FONT),
    ("Field Types — the field types used, with the Carforce equivalent.", FONT),
    ("Statuses — the job statuses and which stage each belongs to.", FONT),
    ("Return Reasons / Cancellation Reasons / Dispositions — kept to mirror Carforce; see the notes on each sheet.", FONT),
    ("Option Lists — every dropdown's options as seeded (admin-editable in the app: Admin › Presets).", FONT),
    ("Text Library — report paragraphs valuers pick from (admin-editable).", FONT),
    ("Roles & Permissions — the roles and who can edit which section.", FONT),
    ("Bank Rules — per-bank switches held on the Bank master.", FONT),
    ("Settings — server settings that change behaviour (environment variables).", FONT),
    ("", FONT),
    ("Source of truth", Font(name="Arial", size=11, bold=True)),
    ("Fields: backend/apps/jobs/field_config.py · Stages and moves: backend/apps/jobs/workflow.py and transitions.py · Options: backend/apps/presets/management/commands/seed_presets.py · Settings: backend/config/settings.py. Change those files, not this sheet, then regenerate it with docs/build_config.py (instructions at the top of that file).", FONT),
    ("Option lists and text library are seeded once and then edited by admins in the app, so the live lists may differ from what is seeded here.", NOTE),
]
for r, (text, font) in enumerate(lines, 1):
    cell = ws.cell(row=r, column=1, value=text)
    cell.font, cell.alignment = font, Alignment(wrap_text=True, vertical="top")
ws.column_dimensions["A"].width = 140

# --- Flows ------------------------------------------------------------------------------
sheet(
    "Flows",
    ["Group Name", "Flow Name", "Short Name", "Required Fields", "Optional Fields", "Is Automated", "Trigger", "Stages"],
    [[GROUP, FLOW, "Valuation", "Bank, Purpose, Date of Instruction, Property Category, Applicant Name, Valuer, Registered Valuer, Inspected By (see Lead Fields)",
      "Everything else on New instruction", "Partly: the first three stages move on by themselves",
      "An admin creates a New instruction when a bank's valuation request arrives (by email today)",
      " → ".join(STAGE_LABEL.values()) + " → Send to bank"]],
)

# --- Flow Stages -------------------------------------------------------------------------
stage_rows = []
stage_defs = [
    ("setup", "Setup", "Admin", "admin_user (who created the job)", ["instruction_received", "setup"],
     "All Setup sections complete → Inspection (automatic)", "Edit sections"),
    ("inspection", "Inspection", "Inspector", "inspected_by", ["inspection_scheduled", "inspected"],
     "All Inspection sections complete (incl. required photos) → Valuation (automatic)", "Edit sections, upload photos"),
    ("valuation", "Valuation", "Valuer", "valuer / registered_valuer", ["valuation_in_progress"],
     "Valuer clicks Send for review (blocked until every required field, photo and document is in, and the reviewer is someone else)",
     "Send for review"),
    ("review", "Review", "Peer reviewer", "peer_reviewer", ["peer_review", "approved_signed"],
     "Reviewer clicks Sign off → final PDF produced, job locked; or Return to valuer (comment required)",
     "Sign off · Return to valuer"),
    ("send", "Send to bank", "Admin", "admin_user (or any platform admin)", ["issued"],
     "Admin sends the issued PDF to a bank contact (logged as queued; email not wired yet)",
     "Send report · Create revision"),
]
for i, (key, label, role, field, statuses, moves, action) in enumerate(stage_defs, 1):
    sections = ", ".join(t["label"] for t in TABS if t["stage"] == key) if key != "send" else "Send to bank page"
    if key == "review":
        sections = "Review & sign off page"
    stage_rows.append([
        GROUP, FLOW, i, label, label, "Auto", f"Role on the job: {role}", role, field,
        "Yes" if key in ("valuation", "review") else "No", "TBC", "TBC",
        "Completed" if key == "send" else "In Progress", "Yes" if key in ("setup", "inspection") else "No",
        action, stage_defs[i][1] if i < len(stage_defs) else "—", sections,
        ", ".join(STATUS_LABELS[s] for s in statuses), moves,
        ROLE_LABEL.get(Role.ADMIN) + " can stand in for Admin/Valuer/Inspector; nobody can stand in for the Peer reviewer"
        if key == "review" else ("Platform admins can act as Admin, Valuer and Inspector"),
    ])
sheet(
    "Flow Stages",
    ["Group Name", "Flow Name", "Stage", "Stage Name", "Short Name", "Assignment Type", "Assignment Criteria",
     "Assign To (Role)", "Assignee Attribute (Job field)", "Todo Required", "SLA (Hrs)", "Progress age",
     "Status", "Is Auto", "Action", "Next Stage", "Sections (tabs)", "Job statuses in this stage",
     "Moves on when", "Allowed Roles / stand-ins"],
    stage_rows,
    note="SLA and progress age are not set in the app yet (TBC). Nothing is locked by stage: any section can be edited while the job is before review.",
)

# --- Next Stages -------------------------------------------------------------------------
moves = []
for (frm, to), rule in workflow.TRANSITION_RULES.items():
    gate = {
        "review_ready": "Every required field filled, required photos and documents in, peer reviewer assigned and not the valuer",
        "signoff_ready": "Everything the final report needs (required fields, files present, PDF engine); in DEMO_MODE licences and placeholder wording don't block",
        "countersign_ready": "Not already counter-signed",
        "issue_ready": "Everything the final report needs (as sign-off)",
    }.get(rule.gate, "")
    moves.append([
        GROUP, FLOW, STATUS_LABELS[frm], STATUS_LABELS[to] if (frm, to) != workflow.SIGN_OFF else "Issued (via Approved & Signed)",
        rule.label, ", ".join(ROLE_LABEL[r] for r in sorted(rule.roles)), "Yes" if rule.comments_required else "No",
        gate, "Manual",
        "Hidden in the UI (stages move on by themselves)" if to in ("setup", "inspection_scheduled", "inspected", "valuation_in_progress") and frm in workflow.PRE_REVIEW_STATUSES
        else ("Sign-off: approves, records the reviewer as second signatory, produces the final PDF and locks the job" if (frm, to) == workflow.SIGN_OFF
              else ("Only for jobs approved before sign-off became one step" if rule.action else "")),
    ])
for stage, status in transitions.STAGE_REACHES:
    moves.append([GROUP, FLOW, f"Any status before {STATUS_LABELS[status]}", STATUS_LABELS[status],
                  f"{STAGE_LABEL[stage]} sections complete", "Whoever saved the last field", "No",
                  f"All {STAGE_LABEL[stage]} sections at 100%", "Automatic", "Runs after every save and photo upload; only ever moves forward"])
moves.append([GROUP, FLOW, "Instruction Received", "Setup", "Any field saved", "Whoever saved it", "No", "", "Automatic", ""])
sheet(
    "Next Stages",
    ["Group Name", "Flow Name", "Current Status", "Next Status", "Result (button)", "Who can do it", "Comment required",
     "Blocked until", "Manual / Automatic", "Notes"],
    moves,
)

# --- Fields Config -----------------------------------------------------------------------
field_rows = []
for t in TABS:
    for f in t["fields"]:
        item_key, values = possible_values(f)
        carforce, _ = TYPE_MAP[f["type"]]
        field_rows.append([
            GROUP, FLOW, "Stage", STAGE_LABEL[t["stage"]], t["label"], f["help_text"], f["key"], f["label"], carforce,
            f["type"], item_key, values, "yes" if f["required"] else "", storage(t["key"], f),
            "yes" if f["calculated"] else "", "" if f["default"] in (None, "") else str(f["default"]),
            rule_text(f["visible_if"]), "yes" if f["free_text"] else "",
        ])
sheet(
    "Fields Config",
    ["Group Name", "Flow Name", "Field type", "Stage", "Section (tab)", "Field Placeholder / help", "Field Name",
     "Field Label", "Data Type", "App type", "Item List Key", "Possible Values", "Is Required", "Associated Module (stored in)",
     "Is Calculated", "Default", "Dependent Field (shown when)", "Free text allowed"],
    field_rows,
    widths={"Possible Values": 60, "Field Placeholder / help": 40, "Dependent Field (shown when)": 40},
    note="Photos, Documents and Evidence are record sections (uploads / comparables), not form fields; see the handoff doc. Required fields only count when shown.",
)

# --- Lead Fields (New instruction) ----------------------------------------------------------
fields_by_key = {f["key"]: (t, f) for t in TABS for f in t["fields"]}
sections = [
    ("Client", ["bank", "bank_reference_no", "purpose", "date_time_request_received", "date_of_instruction"]),
    ("Property", ["property_category", "unit_number", "building_name", "development", "community_name", "latitude", "longitude"]),
    ("Parties", ["applicant_name", "ownership_name"]),
    ("Team", ["valuer", "registered_valuer", "inspected_by", "peer_reviewer"]),
]
accepted = {k for keys in intake.INTAKE_FIELDS.values() for k in keys}
lead_rows = []
for section, keys in sections:
    for key in keys:
        tab, f = fields_by_key[key]
        lead_rows.append([section, f["label"], key, "" if f["required"] else "yes", tab["label"],
                          "yes" if key in accepted else "NO (not accepted by intake)"])
sheet("Lead Fields", ["Section", "Field", "Field Name", "Optional?", "Saved to section", "Accepted by the server"], lead_rows,
      note="The New instruction screen (web/src/app/jobs/new/NewInstruction.tsx). The creator becomes the job's admin.")

# --- Field Types -----------------------------------------------------------------------------
sheet("Field Types", ["Field Type (app)", "Carforce equivalent", "Details"],
      [[k, v[0], v[1]] for k, v in TYPE_MAP.items()] + [
          ["attachment / multi-attachments", "attachment / multi-attachments", "Photos and Documents sections: JPG, PNG, HEIC, PDF; up to "
           f"{processing.MAX_BYTES // (1024 * 1024)} MB each, PDFs up to {processing.MAX_PDF_PAGES} pages; images resized to {processing.IMAGE_MAX_EDGE}px"],
          ["comparable", "—", "Evidence section rows: source, link, building, community, type, beds, floor, view, BUA, price, date, sold/asking, notes"],
      ])

# --- Statuses ----------------------------------------------------------------------------------
status_def = {
    "instruction_received": ("Setup", "Job created from New instruction; nothing saved yet."),
    "setup": ("Setup", "Someone has started filling in the job."),
    "inspection_scheduled": ("Inspection", "All Setup sections complete."),
    "inspected": ("Inspection", "Legacy step between inspection and valuation; the automatic move passes through it."),
    "valuation_in_progress": ("Valuation", "All Inspection sections complete, or the job was returned/reopened."),
    "peer_review": ("Review", "Sent for review. Data is frozen; only the peer reviewer can act."),
    "approved_signed": ("Review", "Signed off; the final PDF is being produced (or failed and can be retried)."),
    "issued": ("Send to bank", "Final report stored, job locked. Changes need a revision (new version)."),
}
sheet("Statuses", ["Job Status", "Code", "Stage", "Definition", "Data editable?"],
      [[label, code, *status_def[code], "No" if code in ("peer_review", "approved_signed", "issued") else "Yes"]
       for code, label in workflow.JobStatus.CHOICES])

# --- Reasons (mirroring Carforce) ---------------------------------------------------------------
sheet("Return Reasons", ["Flow Name", "Stage Name", "Reasons", "Configured in app?"],
      [[FLOW, "Review → Return to valuer", "Free-text comment (required). Suggested list for later: Comparable evidence weak | "
        "Area/BUA doesn't match the title deed | Missing or wrong documents | Value outside the AVM range without a reason | "
        "Report wording / typos | Wrong client or purpose", "No — free text only; the list is a suggestion"],
       [FLOW, "Review → Reopen (after sign-off failed)", "Free-text comment (required)", "No — free text only"]])
sheet("Cancellation Reasons", ["Flow Name", "Stage Name", "Reasons", "Configured in app?"],
      [[FLOW, "—", "Jobs can't be cancelled yet; an admin can soft-delete one in the Django admin (kept for 5 years).",
        "No — open question"]])
sheet("Dispositions", ["Request Status", "Disposition"],
      [[label, ""] for _, label in workflow.JobStatus.CHOICES],
      note="No dispositions are configured in the app; kept to mirror the Carforce config.")

# --- Option Lists -----------------------------------------------------------------------------
opt_rows = []
for key, entries in seed.PRESETS.items():
    for order, (label, value) in enumerate(zip(labels_for(entries), values_for(entries)), 1):
        opt_rows.append([key, order, label, value, ""])
for key, entries in seed.PRESET_TEXT.items():
    for order, (label, text) in enumerate(entries, 1):
        opt_rows.append([key, order, label, seed._slug(label), text])
sheet("Option Lists", ["Item List Key", "Order", "Label", "Stored value", "Report text"], opt_rows,
      widths={"Report text": 70},
      note="As seeded by seed_presets. Admins add, rename, reorder or retire options in the app (Admin › Presets); stored values never change.")

# --- Text Library -----------------------------------------------------------------------------
lib_rows = []
for category, titles in seed.LIBRARY.items():
    for order, title in enumerate(titles, 1):
        lib_rows.append([category, order, title, "Placeholder wording (to be replaced by approved text)"])
    if not titles:
        lib_rows.append([category, "", "(none seeded)", "Admins add entries"])
sheet("Text Library", ["Category", "Order", "Title", "Body"], lib_rows,
      note="Valuers pick these in library fields; picking one replaces the field's text (except Special Assumptions / Other Matters, which take several).")

# --- Roles & Permissions -----------------------------------------------------------------------
role_rows = []
for role, label in Role.choices:
    edits = [get for get, roles in tabs.TAB_EDIT_ROLES.items() if role in roles]
    role_rows.append([label, role, ", ".join(edits) or "—", {
        "admin": "Creates the instruction, owns Setup and Send to bank; platform admins see every job",
        "inspector": "Inspection and photos",
        "valuer": "Fills the job, sends for review; the registered valuer signs",
        "peer_reviewer": "Reviews and signs off (the second signature); only the assigned reviewer",
        "counter_signatory": "Retired as a separate step: the reviewer's sign-off is the second signature",
    }[role]])
sheet("Roles & Permissions", ["Role", "Code", "Can edit sections", "Responsibility"], role_rows,
      note="Roles are per job (the person in the job's role field), not global. A platform admin (staff, superuser or admin role) can act as Admin, Valuer and Inspector on any job, never as the Peer reviewer.")

# --- Bank Rules --------------------------------------------------------------------------------
sheet("Bank Rules", ["Rule key (Bank.rules)", "Effect", "Status"], [
    ["requires_makani_photo", "A full inspection needs a Makani number photo", "Active"],
    ["requires_dewa_photo", "A full inspection needs a DEWA number photo", "Active"],
    ["requires_service_charge", "Showed a Service charge field / report row (ADIB)", "Hidden: field removed from the form"],
    ["requires_forced_sale_value", "Showed Forced sale value on the report", "Hidden: field removed from the form"],
    ["forced_sale_discount_pct", "Forced sale discount for this bank (default 10%)", "Hidden with forced sale value"],
    ["requires_exact_age", "Printed exact age", "Superseded: age always printed (years.months)"],
], note="Set per bank in Admin › Banks (rules JSON). Bank contacts (name, email) feed the Send to bank dropdown.")

# --- Settings ----------------------------------------------------------------------------------
sheet("Settings", ["Environment variable", "Current default", "What it does"], [
    ["DEMO_MODE", str(settings.DEMO_MODE), "On: sign-off doesn't wait for RERA licences or approved wording. Set false before real reports."],
    ["REPORT_FIRM_NAME", settings.REPORT_FIRM_NAME, "Firm name on every report"],
    ["REPORT_FIRM_LEGAL_NAME", "= REPORT_FIRM_NAME", "Registered legal name in the signature wording; stands in with the firm name until confirmed"],
    ["REPORT_FIRM_ADDRESS", settings.REPORT_FIRM_ADDRESS, "Firm address on the report"],
    ["PEER_REVIEW_REQUIRES_INDEPENDENT_REVIEWER", str(settings.PEER_REVIEW_REQUIRES_INDEPENDENT_REVIEWER), "The reviewer can't be the valuer"],
    ["AVM_DEVIATION_THRESHOLD_PCT", str(settings.AVM_DEVIATION_THRESHOLD_PCT), "AVM flags a market value further than this from its suggestion"],
    ["FORCED_SALE_DISCOUNT_PCT_DEFAULT", str(settings.FORCED_SALE_DISCOUNT_PCT_DEFAULT), "Forced sale discount (field hidden for now)"],
    ["CELERY_TASK_ALWAYS_EAGER", "= DEBUG", "Run background tasks (final PDF) inline; Docker sets false and uses the worker"],
    ["ISSUE_TASK_TIMEOUT_SECONDS", str(settings.ISSUE_TASK_TIMEOUT_SECONDS), "After this, a stuck final-PDF request can be retried"],
    ["DEBUG", "False", "Development mode; must be False in production"],
    ["DJANGO_SECRET_KEY / DJANGO_ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS / CORS_ALLOWED_ORIGINS / DATABASE_URL", "—", "Standard deployment settings (see backend/.env.example and render.yaml)"],
    ["API_PROXY_TARGET (web)", "http://localhost:8000", "Where the web app forwards /api/ (8001 for the Docker API locally)"],
], note=f"Plot-bearing categories (plot area, first floor, rear views, reinstatement value): {', '.join(PLOT_BEARING_CATEGORIES)}. "
        f"Tenanted occupancies: {', '.join(TENANTED_OCCUPANCIES)}. Executive summary photos: {checks.EXEC_SUMMARY_PHOTOS}. "
        f"Comparable sources: {', '.join(label for _, label in Comparable.SOURCE_CHOICES)}.")

wb.save(OUT)
print("saved", OUT, [ws.title for ws in wb.worksheets], "fields:", len(field_rows), "options:", len(opt_rows))
