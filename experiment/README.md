# Valuation Platform

In-house real estate valuation platform for Dubizzle Group / Bayut — see
[`CLAUDE.md`](CLAUDE.md) for the full product/technical spec this repo
implements against, and `docs/` for the source reference material.

## Status

Build order steps 1–2 (CLAUDE.md §10) are done and verified end-to-end:

- Monorepo scaffold: `backend/` (Django 5 + DRF) and `web/` (Next.js 16 +
  TypeScript + Tailwind), `docker-compose.yml` wiring Postgres 16 + Redis.
- Core data model (§9) + migrations + Django admin for every app: accounts
  (User/ValuerProfile with RERA/RICS + licence expiry), banks, jobs
  (Property, Job, and one typed model per tab: Checklist/Summary/
  Inspection/Location/Valuation), presets (admin-editable dropdown options
  + text libraries), media_files (Photo/Document), evidence
  (Comparable/JobComparable/AVMRun), reports (ReportTemplate/ReportVersion),
  register (ValuationRegisterEntry — DLD 67/2020 fields), audit (generic
  field-level change log).
- Job lifecycle state machine (`apps/jobs/workflow.py`), **enforced** on
  every write: illegal status jumps are rejected, `Job.issue()` refuses
  without peer review + counter-signature + an unexpired RERA licence, and
  an issued job (plus its tab data) is locked — amendments go through
  `Job.create_revision()`, which carries the previous version's data
  forward. Reference numbers come from a monotonic per-year counter so a
  number that reached a bank report is never reused.
- Calculation helpers (`apps/jobs/calculations.py`): sqm↔sqft, lat/long→DMS,
  exact age, rate/sqft, forced sale value (bank-rule override supported),
  number-to-words, address-as-per-document formatting.
- Config-driven field definitions (`apps/jobs/field_config.py`) for the
  9-tab form, served at `GET /api/field-config/` and consumed by a generic
  frontend renderer (`web/src/components/FieldRenderer.tsx`) that also
  evaluates `visible_if` rules — proven against live data for the Check
  List and Valuation tabs.
- Minimal read API (`/api/jobs/`, `/api/jobs/<id>/`, paginated 25/page) and
  a jobs list/detail UI in Next.js, confirmed working cross-origin against
  a Django session cookie.
- Tests (`pytest`) covering the calculation helpers and every lifecycle
  rule above, plus CI (`.github/workflows/ci.yml`) running ruff, a
  missing-migration check, `manage.py check --deploy`, pytest, and the
  frontend lint/typecheck/build.

**Not built yet** (next up per the build order): the PATCH-per-tab save
API + full write form, report generator (PDF), workflow transitions wired
into the UI, photos/documents upload, evidence/AVM, Google SSO. The
`instructions` data today lives partly on `Job` and partly on `Property`
rather than as its own `InstructionData` model — a deliberate reading of
§9's "decide early" note, documented in `apps/jobs/models.py`.

- Soft deletes and retention (§7, DLD 67/2020): record-bearing models
  (Job, Property, Photo, Document, ReportVersion, ValuationRegisterEntry)
  extend `apps.common.models.SoftDeleteModel`. `delete()` marks the row
  and `objects` hides it; `all_objects` still sees it. Bulk
  `queryset.delete()` soft-deletes too, issued jobs refuse both delete
  paths, and `hard_delete()` is refused inside the 5-year window.
- RBAC (§3, §7): `apps.accounts.permissions` scopes job access to the
  roles a user actually holds on that job (several at once is normal);
  platform admins and Django staff see everything.
- Conditional-field rules no longer depend on editable text: the ADIB
  service charge keys off `Bank.rules.requires_service_charge`, and
  villa/townhouse rules share `apps.jobs.constants.PLOT_BEARING_CATEGORIES`
  against `PresetOption.value` (a stable slug, separate from the label an
  admin can rename).

**Known gaps from the code audit**, in priority order: `exact_age` is
computed as-of today rather than the valuation date (so a regenerated
report can state a different age), the audit log records updates but not
creations and writes in `pre_save` before the row commits, the thread-local
`CurrentUserMiddleware` will mis-attribute under ASGI, `field_config.py`
isn't yet used for server-side validation (`required` is cosmetic), there
are no indexes for the `Comparable` filter columns that DLD open data will
need, and `Property` has no dedup key for the §7 conflict check.

## Local development (no Docker required)

**Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt without test tooling
cp .env.example .env   # REQUIRED: DEBUG defaults off and SECRET_KEY has no fallback
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

Django admin: http://localhost:8000/admin/ — log in with the email you
just created (the custom `User` model uses email, not username, to log in).

**Tests and lint**

```bash
cd backend && pytest && ruff check .
```

**Frontend**

```bash
cd web
cp .env.local.example .env.local
npm install
npm run dev
```

App: http://localhost:3000 — note the API requires an authenticated
session; log into the Django admin in the same browser first (SSO isn't
wired up yet, see §8/§11).

## Docker (matches the target deploy shape: Postgres + Redis + Celery)

```bash
cp backend/.env.example backend/.env   # edit DATABASE_URL etc. for compose
cp web/.env.local.example web/.env.local
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- Postgres: localhost:5432, Redis: localhost:6379

## Repo layout

```
backend/apps/
  common/     SoftDeleteModel + retention (shared abstract bases)
  accounts/   User, ValuerProfile, Role, permissions.py (RBAC)
  banks/      Bank (client master, SLA, per-bank rules JSON)
  jobs/       Property, Job, tab-data models, field_config.py, workflow.py,
              calculations.py, constants.py — the core of the platform
  presets/    PresetOption, TextLibraryItem (admin-editable dropdowns/text)
  media_files/ Photo, Document
  evidence/   Comparable, JobComparable, AVMRun
  reports/    ReportTemplate, ReportVersion
  register/   ValuationRegisterEntry (DLD electronic register)
  audit/      AuditLog + generic change-tracking signal

web/src/
  lib/            API client, field-config types, job hooks (TanStack Query)
  components/     FieldRenderer (config-driven tab renderer), QueryProvider
  app/jobs/       Jobs list + detail (tab-navigated) pages
```
