# Valuation Platform: Product Requirements Document

**Owner:** Izza Naseer, Dubizzle Labs · **Status as of:** 14 Oct 2026 · **Code state:** `main` at `c1e9b31` plus the uncommitted photos/documents work
**Companion docs:** `CLAUDE.md` (full spec and domain notes), `docs/` (source material)

This PRD says what the product is for, what is built, which checks the system enforces today, which checks it does not enforce yet, and what functionality is missing. Every "built" claim was checked against the code, not the plan. Sections 4 to 6 are the working lists.

---

## 1. Purpose

An in-house valuation platform for Dubizzle Group / Bayut, replacing ValuePro. Valuers enter an instruction across 9 tabs. The system produces a bank-ready PDF valuation report, and later suggests a data-backed value from comparables and an AVM.

**Business goal:** get on UAE banks' valuer panels (mortgage-security valuations) and compete with Colliers, CBRE and Knight Frank, on data, technology and speed. Launch scope is Dubai, and the property types are apartment, villa, townhouse, office and retail.

**Out of scope for launch:** investment-method valuations, the iPad app, WhatsApp, a bank portal/API, and the Property Monitor API.

**Definition of done for MVP:** re-run 3 real past jobs end to end and produce reports that match the finalised template.

## 2. Users and roles

| Role | What they do in the product |
|---|---|
| Admin | Creates the instruction, manages users/banks/presets/templates, **issues** the report, creates revisions |
| Inspector | Check List and Inspection tabs, photos |
| Valuer | Summary, Location & Description, Valuation, picks evidence, sets the value, signs |
| Peer reviewer | Approves or returns the valuation (must be someone other than the valuer or signing valuer) |
| Counter-signatory | Second signature on the report |

One person can hold several roles on one job. Platform admins can act as admin, valuer and inspector, but **never** as peer reviewer or counter-signatory.

## 3. Where the build stands

Status against the build order in `CLAUDE.md` §10:

| # | Step | Status |
|---|---|---|
| 1 | Scaffold, auth, roles | **Done** except Google SSO and docker-compose verification. Email+password sign-in is interim. |
| 2 | Data model, migrations, Django admin | **Done** |
| 3 | Field-config engine and 9-tab form | **Done** for 8 of 9 tabs. Only Evidence is a placeholder. |
| 4 | Report generator | **Done** for HTML and PDF. Legal wording is placeholder and the layout needs tuning. |
| 5 | Photos and documents upload | **Done** for local storage. Direct-to-S3 uploads, virus scanning and encryption are not built. |
| 6 | Workflow, peer review, lock-on-issue, versioning, register, audit | **Mostly done.** Register is not built. |
| 7 | Evidence: manual + CSV, comparables in report, AVM v1 | **Not started** (models only) |
| 8 | DLD open-data import, email delivery | **Not started** |
| 9 | Bayut listings connector | **Not started** |
| 10 | Property Monitor connector | **Not started** (intentionally last) |

### Built and working, end to end
- **Sign-in and admin:** session sign-in/out; Users, Banks, Presets, Text library and Report templates screens (admin only, deactivate instead of delete).
- **New instruction:** one screen creates the job and property, takes the bank, applies the bank's billing address once the SLA is signed.
- **Job workspace:** six editable tabs rendered from one field config, with autosave, conditional fields, server-computed values (sqft, DMS, exact age, rate per sqft, forced sale value, value in words), completion rings, activity feed, comments from the review log.
- **Lifecycle:** Start setup → Schedule inspection → Mark inspected → Start valuation → Send for review → Approve → **Issue**, plus Return to valuer and Reopen, each with role, comment and gate rules.
- **Photos and documents:** bulk upload by drag-and-drop or picker (JPG, PNG, HEIC, PDF), caption, reorder, include/exclude, Makani and DEWA photo slots, document types from admin presets, removal with confirmation. Photos feed the three executive-summary slots and Appendix 5; documents render page by page in Appendix 4.
- **Report:** HTML preview (instant), draft PDF, final PDF on issue. About 15 pages, A4, header/footer, page numbers, DRAFT watermark on drafts, value in figures and words, signatory blocks with RERA/RICS numbers.
- **Issue and revise:** final PDF stored with template version and an input snapshot; the job is locked; admins can create one revision per issued version.
- **Quality bar:** 457 automated tests (2 skipped, which only apply when the PDF engine is missing), ruff, type-check, lint and production build all pass, and CI is configured.

---

## 4. Checks the system HAS today

### 4.1 Access and authentication
| Check | How it works |
|---|---|
| Sign-in is CSRF-protected | Login and logout need the CSRF token; the client retries once if the token rotated |
| Login throttling | 10 attempts per minute; one generic error so accounts can't be probed |
| Password rules | Django validators: minimum length, common-password, numeric-only, similarity to user attributes |
| Job visibility | Users see only jobs they hold a role on; admins see all |
| Per-tab edit rights | Instructions: admin/valuer. Summary, Location, Valuation: valuer. Check List, Inspection: inspector/valuer |
| Assignment fields protected | Only admin/valuer can change who the valuer, inspector, peer reviewer, counter-signatory and signing valuer are |
| Admin APIs are admin-only | `is_staff`/`is_superuser` are never exposed; there are no delete endpoints |
| Reviewer independence of admins | An admin can never approve, return or counter-sign on someone else's behalf |
| Peer-reviewer independence | Sending for review is blocked if the peer reviewer is the valuer or signing valuer (configurable, on by default) |

### 4.2 Data entry and integrity
| Check | How it works |
|---|---|
| Server-side validation | The server re-validates every field from the same config the UI uses; hidden fields are not required |
| Required and conditional rules | `visible_if` and `required` evaluated on the server (lease expiry only for long leasehold, plot area only for villa/townhouse, upgrade comment required when upgraded, service charge per bank rule) |
| Type coercion and ranges | Latitude/longitude, percentages 0–100, non-negative money/areas, column precision; decimals travel as strings so nothing is rounded in transit |
| All-or-nothing save | A tab save with any invalid field changes nothing |
| Bank rules validated strictly | Unknown rule keys or wrong types are rejected |
| First edit wins | Each tab has a version; a save based on a stale version gets a 409 and applies nothing; the UI offers "use theirs" or "re-apply mine" |
| Row locking | Saves and transitions lock the job row, so two people can't interleave |
| Reference numbers never reused | Monotonic per-year counter with a unique constraint |

### 4.3 Lifecycle and locking
| Check | How it works |
|---|---|
| Legal transitions only | Enforced on every write path (API, admin, shell, tasks), not just the UI |
| Stale screen protection | A transition names the status the user was looking at; if the job moved, it is refused |
| Review gate | Sending for review needs every tab complete, a peer reviewer assigned, and independence (§4.1) |
| Approval gate | Approving needs a counter-signatory assigned |
| Comments required | Return to valuer and Reopen need a written reason, kept on the job |
| Data frozen in review and after sign-off | No edits in `peer_review` or `approved_signed`; reopen to change anything |
| Issued jobs are locked | Edits are rejected at the model level, including edits to the property record; amendments go through a revision |
| Revision rules | Once per version; admin only; the revision copies the property so the issued address stays exactly as signed |

### 4.3a Uploads
| Check | How it works |
|---|---|
| Real file type | The kind is read from the file's own first bytes, never from its name or declared type; a program renamed `.jpg` is refused |
| Decoded, not trusted | Images are fully decoded and re-encoded, so damaged, half-uploaded or malformed files are refused with a reason. This is strict even after the PDF library has relaxed Pillow's global setting, which a test now guards |
| Camera metadata stripped | GPS and device data are removed on re-encode; phone photos are rotated upright |
| Size limits | 25 MB per file, 20 files per upload, 80 photos and 40 documents per job, 150 pages per PDF, a pixel cap against decompression bombs |
| Generated storage names | The stored name is generated; the uploaded name is display-only and sanitised, so it can't steer where anything is written |
| Duplicates | The same file twice in one upload, or already on the job, is refused |
| Partial success | One bad file doesn't lose the good ones; each refusal comes back with its reason |
| Same access rules as the tabs | Inspector and valuer for photos; admin and valuer for documents; nothing for a reviewer; nothing during review, after sign-off, or after issue |
| First edit wins | Captions and settings carry a version; reordering is refused if the list changed underneath |
| Files behind sign-in | Every file and thumbnail is served only to someone who can see the job |
| Never destroyed | Removing hides the item; the file stays, so issued reports and revisions that point at it keep working. A revision carries the media over |
| Audited | Captions, inclusion, order and removals appear in the job's history |
| What the job needs | Full inspection: at least 3 general photos in the report. Drive-by: 1. Every job: at least one document. Bank rules can require Makani and DEWA photos. A Check List "photo taken" answer must be matched by an upload. Sending for review is blocked until met |
| Report integrity | A missing stored file blocks issuing; the draft shows an "unavailable" marker instead of breaking |

### 4.4 Issue gate (all must hold, shown in the UI before anyone clicks)
1. Job is `approved_signed`.
2. Peer reviewer and counter-signatory are assigned.
3. The signing valuer's RERA licence is valid.
4. The counter-signatory's RERA licence is valid.
5. Every tab is complete.
6. The PDF engine is available.
7. **No `[PLACEHOLDER` text remains anywhere in the rendered report**, whether it comes from the template, the text library or the valuer's own text.

Issuing is atomic: render, store file, create the report record, lock the job. A failure at any step leaves the job open and removes the stored file.

### 4.5 Audit and traceability
| Check | How it works |
|---|---|
| Field-level audit | Who, field, old value, new value, when, for the job, every tab, the property, banks, valuer profiles, presets and text-library entries |
| Correct attribution | Changes made through the API are attributed to the acting user, not "System" |
| Transition log | Every status move with who, comment and time |
| Reproducible reports | Each report version keeps the template version (content-hashed) and a full snapshot of its inputs; an issued report re-renders exactly from its snapshot |
| Soft delete | Jobs, properties, photos, documents, report versions and register entries are never hard-deleted by the app |

### 4.6 Report safety
- Templates run in a sandboxed Jinja environment with autoescape and strict undefined variables, so a bad template fails loudly and hostile text can't inject markup.
- The HTML preview is served with a sandbox CSP.
- Value in words must match the figure, including fils.
- All legal wording is visibly marked as a placeholder, in both HTML and PDF, until approved.

---

## 5. Checks the system does NOT have

Ranked by risk to a bank-facing launch.

### 5.1 Must fix before real reports go out (P0)
| Missing check | Why it matters |
|---|---|
| **Counter-signatory can be the same person as the valuer** | The second signature is meaningless if it's the same person. Only the peer reviewer's independence is enforced. A test fixture currently relies on this being allowed. |
| **No cross-field date checks** | Nothing stops valuation date after report date, a report date in the future, an inspection before the instruction, or a valuation date years from the inspection. |
| **No valuation reasonableness checks** | No warning for an implausible AED/sqft against the area, an MV far from the asking/sold evidence, or a forced-sale value outside the bank's range. |
| **No tamper-evidence on issued PDFs or uploads** | The upload hash is stored, but the issued report's checksum is not, and files sit on local disk. Production needs a hash on the report record plus write-once storage. |
| **Issue doesn't write the DLD register entry** | DLD Resolution 67/2020 requires every completed valuation to be registered; the model exists but nothing creates entries. |
| **Approved legal wording is absent** | Terms, assumptions, disclaimer, reliance, independence and skills statements are placeholders, so **nothing can be issued**. |

### 5.1a Gaps in the new upload feature
| Missing check | Why it matters |
|---|---|
| **No virus or malware scan** | Images are re-encoded (which neutralises most tricks) but PDFs are stored exactly as uploaded and served inline. |
| **No direct-to-S3 upload, encryption at rest or UAE-region storage** | Uploads go through the server to local disk; CLAUDE.md asks for presigned S3 in me-central-1. |
| **No photo authenticity checks** | Camera metadata is stripped, so nothing checks that a photo was taken at the property, on the inspection date, or isn't reused from another job (only exact duplicates within a job are caught). |
| **No document verification** | Nothing checks the uploaded deed against the entered property number, plot, BUA or owner. |
| **Rules that depend on a document type** | Only "at least one document" is required. A bank that needs the title deed specifically, or an SPA when the BUA source is SPA, isn't enforced. |
| **Report caps long documents at 10 pages** | The page count is stated on the page, but a bank wanting a whole contract appended isn't served. |

### 5.2 Should have for launch (P1)
| Missing check | Why it matters |
|---|---|
| **Conflict check** | CLAUDE.md §7: warn if the property or applicant was valued before. No duplicate-property key exists yet. |
| **AVM deviation reason** | If the final value deviates from the AVM by more than X% (default 10%) a reason must be recorded. There is no AVM. |
| **Assignment-time role checks** | The signing valuer's profile and licence are only checked at issue, not when they're assigned. Users with no valuer profile can be picked as signers. |
| **Licence-expiry warning on the job** | Expiring licences are flagged in Admin (60-day window), but a valuer is not warned while working a job whose signer's licence expires before the report date. |
| **Licence validity at the valuation date** | Licence is checked against today, not against the date the report is signed or issued as of. |
| **Placeholder detection is text-only** | It matches the literal `[PLACEHOLDER`. TODO markers, "XX", empty sections, or lorem text typed by a valuer pass. |
| **Account lockout and session policy** | Throttling is per client address and held in each server process's memory (not shared); there is no per-account lockout, session timeout, concurrent-session limit, or forced password change. |
| **No MFA / SSO** | Google Workspace SSO is the agreed direction and is not built. |
| **Audit log protection** | The audit log is read in the Django admin, but there's no check that it can't be edited or deleted by an admin. Users themselves are not audited. |
| **Delivery checks** | No email of the issued PDF, no delivery log, no confirmation the bank received it. |

### 5.3 Later (P2)
- Rate limiting beyond sign-in; request size limits on the API.
- Retention tooling: the app never deletes, and `hard_delete()` refuses inside the 5-year window (checked in code). There is still no archive or purge workflow, and the retention rule isn't applied to stored files.
- Encryption at rest, UAE-region hosting (AWS me-central-1) and backups are decisions, not configuration, so far.
- Accessibility checks on the web app and the PDF.
- Spelling/consistency checks on report text (for example, "sqm" and "sqft" figures agreeing with each other in free text).

---

## 6. Functionality that is missing

### 6.1 Core product (P0, blocks the MVP definition of done)
1. **Photos and documents upload (build step 5): built.** Remaining: presigned direct-to-S3 upload, a malware scan, and the checks in §5.1a. Upload has also not yet been tested on an iPad.
2. **Evidence and AVM v1 (step 7).** Tab 9 is a placeholder. Needs the `Comparable` schema with source and pull date, manual entry and CSV/Excel upload, auto-suggest with filters (12 months, BUA ±20%, bedrooms, floor, view, sold vs asking), valuer selection, the comparables table in the report, and the AVM: median AED/sqft with configurable adjustments, range, confidence, shown workings, a stored run per job version.
3. **Approved report wording.** Own T&C, general assumptions, bases of valuation, disclaimer, reliance, independence and skills statements; market commentary tables (manual at launch).
4. **Valuation register (step 6).** Create the DLD register entry on issue, list and filter screen, CSV export, a "registered with DLD" flag, and authority-reporting data fields.
5. **Report layout tuning against the sample.** Many near-empty pages (every section starts a new page), floating signature block, no cover branding, no location map (needs a Static Maps key), no accommodation/specification polish. Final branded template (logo, colours) is pending.

### 6.2 Workflow and operations (P1)
6. **Email delivery of the issued PDF** (SES via Celery) with a delivery log and resend.
7. **Revision experience.** A new reference number is created per revision today. Banks may expect the same reference with a version suffix. Also needed: a version history view, and a diff or summary of what changed from the issued version.
8. **Turnaround and SLA.** Dashboard average turnaround exists; per-stage times, SLA fields per bank, overdue flags, and notifications are missing.
9. **Notifications.** No email or in-app alerts for assignment, review requests, returns, or issue.
10. **Assignment and scheduling UI.** Setting the inspector, inspection date and calendar view. Inspection scheduling is a status change only.
11. **Instruction intake extras.** Attach the bank's email or PDF to the instruction; duplicate/conflict warning at creation; bulk import.
12. **Search and filters.** The jobs list has basic filters; no full-text search by address, applicant, bank reference or valuer.
13. **Bank master depth.** Contacts, per-bank report template variants (template choice exists but there is no bank-level assignment screen), forced-sale discount per bank.
14. **Report template editing UX.** Templates can be stored and versioned, but there is no side-by-side preview or edit-and-regenerate loop for admins.

### 6.3 Platform (P1 to P2)
15. **Google Workspace SSO (OIDC)** replacing email+password; role mapping from groups.
16. **Production infrastructure.** Docker image, Postgres, Redis, Celery workers (no tasks exist yet), S3, SES, AWS me-central-1, CI/CD deploy, secrets, monitoring, backups. PDF rendering needs Pango/freetype in the image and the `DYLD_FALLBACK_LIBRARY_PATH` setting on macOS dev machines.
17. **Throttling and sessions in shared storage** (Redis) so limits hold across processes.
18. **Responsive/iPad pass.** The UI is built to be usable on iPad but not yet tested on one.

### 6.4 Data connectors (P2, in order)
19. DLD open-data import (Dubai Pulse `dld_transactions-open`) into our own table, matching on building, community, type and BUA.
20. Bayut listings (asking prices) via an internal export.
21. Property Monitor API (transactions, rents, master data): last.

### 6.5 Housekeeping
- `README.md` status section is out of date (it still describes the old read-only detail screen and a removed component).
- Service-charge unit is undefined (TODO in `apps/reports/context.py`).
- Dev databases need `manage.py migrate` and `seed_presets` after pulling; there is no `seed_demo` command to produce a realistic job without placeholder wording.
- Commits are not pushed anywhere yet.

---

## 7. Open decisions (don't block, but need an owner)

| Decision | Current default |
|---|---|
| Forced sale discount: 10% or 15%, per bank? | Configurable per bank; no default confirmed |
| Revision reference numbers: new number or same number plus version? | New number |
| Should the counter-signatory also need a valid licence at issue? | Yes (built) |
| Should the counter-signatory be required to differ from the valuer? | Not enforced; recommended |
| Launch counter-signatory and peer reviewer names and RERA/RICS numbers | Not provided |
| First target bank and its specific rules | Not chosen; ADIB service charge is the only bank-specific rule |
| Is a desktop (no-inspection) valuation product in scope? | Supported as an inspection type, no separate product |
| Source of market commentary tables at launch | Manual or library text |
| How the DLD register is submitted, and whether it can be integrated | Unknown; entry model only |
| Property Monitor and Bayut data access details | Unknown |

## 8. Suggested next steps, in order

1. **Close the P0 integrity checks** (counter-signatory independence, date sanity, report PDF checksum). Small, high value.
2. **Valuation register on issue**: small once issue exists, and a regulatory requirement.
3. **Approved wording**: a business input; nothing can be issued until it exists.
4. **Evidence and AVM v1**: the product's differentiator, and the largest remaining build.
5. **Email delivery, notifications, SSO, infrastructure** (including S3 and malware scanning for uploads): needed to go live.
6. **Run the 3 real past jobs** against the finalised template, which is the MVP exit test.
