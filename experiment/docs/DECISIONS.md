# Decision log

Every significant decision taken while building the platform so far, with the reason and who made it.

**Source tags**

| Tag | Meaning |
|---|---|
| **You** | Izza told me directly |
| **Spec** | Comes from `CLAUDE.md` (the planning handoff) |
| **Me** | My judgment where neither of the above settled it |
| **Default** | A placeholder value I chose so work could continue; **needs your confirmation** |

Reasons for the older decisions are reconstructed from the code, its comments and the commit history, so treat those as my best account and not a transcript. Section 11 lists everything marked **Default** or still open.

---

## 1. Decisions you made

| # | Decision | Effect |
|---|---|---|
| 1 | The server returns computed values (sqft, DMS, rate/sqft, value in words, etc.) | The screen never calculates; it shows what the server says, so the screen and the PDF can't disagree |
| 2 | If two people edit the same thing, **the first edit wins** | Stale saves get a 409 and apply nothing; the second person chooses "use theirs" or "re-apply mine" |
| 3 | Build order: write API → lifecycle transitions → missing model fields → report generator → sign-in, New instruction and Admin screens → issue flow → photos and documents | Each slice was committed separately |
| 4 | Install Pango via Homebrew for the PDF engine (rather than switch to Playwright) | WeasyPrint stays the PDF route |
| 5 | Commit after each slice, with a sensible message | One commit per slice; nothing is pushed |
| 6 | Write the PRD, then add photo/document upload and a one-command dev script | `docs/PRD.md`, the upload feature, `dev.sh` |

---

## 2. Architecture and stack

| # | Decision | Why | Source |
|---|---|---|---|
| 2.1 | One **field config** (`field_config.py`) defines every tab and field; the UI renders from it and the server validates from it | Two copies of the rules would drift. The spec asked for config-driven forms like Carforce | Spec |
| 2.2 | Each tab has its own typed table; a field's storage (tab row, Job, or Property) is **worked out from the config**, not hard-coded | Typed columns for anything used in calculations, reports or the register, as the spec recommended; routing from config means adding a field is one edit | Spec + Me |
| 2.3 | SQLite in development, Postgres in production | Zero setup locally; the spec names Postgres 16 | Spec |
| 2.4 | Email + password session sign-in for now; Google SSO later | The spec wants SSO, but it needs Google Workspace setup. Sessions mean the later swap doesn't change the app's contract | Spec + Me |
| 2.5 | Design system vendored **unmodified** | So the design team's updates can be re-synced; our own tweaks live in a separate stylesheet | Me |
| 2.6 | Money, areas and coordinates travel as **strings**, never floats | A float would round a valuation figure between the database and the screen | Me |
| 2.7 | Files go to local disk behind Django's storage layer; the column is still called `s3_key` | S3 needs AWS. Keeping the storage layer means S3 later is configuration, not a rewrite | Me |
| 2.8 | Soft delete everywhere; `hard_delete()` refuses inside the 5-year window | DLD Resolution 67/2020 retention | Spec |

---

## 3. Editing and concurrency

| # | Decision | Why | Source |
|---|---|---|---|
| 3.1 | Each tab saves through its own `PATCH`, **autosaved** after a short pause, one request at a time | Valuers shouldn't hit a Save button; one in flight avoids two saves racing | Me |
| 3.2 | Each tab has its **own version number** | Two people on different tabs never conflict; conflicts are only reported where they really collide | Me |
| 3.3 | A save is **all-or-nothing** | One bad field must not half-apply a tab | Me |
| 3.4 | A field the server rejected is held back from later saves until it's edited again | Otherwise one bad field would block every other field's save | Me |
| 3.5 | The text a user types stays as typed ("7250" isn't swapped for "7250.00" mid-typing) | An early bug: the screen reformatted what was being typed | Me |
| 3.6 | Who may edit which tab: Instructions → admin/valuer; Summary, Location, Valuation → valuer; Check List, Inspection → inspector/valuer; Photos → inspector/valuer; Documents → admin/valuer | Follows the roles table in the spec; the exact mapping is mine | Spec + Me |
| 3.7 | Fields that decide **who works on the job** (valuer, inspector, reviewers, signers) can only be changed by admin/valuer, even on a tab the inspector can edit | The inspector sits on the Check List tab and must not be able to reassign the valuer | Me |
| 3.8 | **Data is frozen** while a job is in peer review or signed off | An edit after the reviewer approved would put numbers on the report nobody reviewed. To change anything, return it to the valuer | Me |
| 3.9 | Visibility ("only when Interest = long leasehold") and completion are **evaluated on the server** | Hidden fields must never block completion; the server must be the authority | Me |

---

## 4. New instruction (how "new job" works)

| # | Decision | Why | Source |
|---|---|---|---|
| 4.1 | **Only admins create jobs** | The spec: "Admin creates the instruction" | Spec |
| 4.2 | One screen with a **small set of fields**, with title-document details and everything else entered in the workspace afterwards. **From the brief (`DESIGN_BRIEF.md` S2):** bank, bank reference, received date/time, purpose, property type, unit/building/community, applicant name, inspector and valuer. **Added by me beyond the brief:** date of instruction, latitude/longitude, ownership name, contact for access, signing valuer, peer reviewer, counter-signatory. **In the brief but not built:** attaching the bank's email or PDF | The brief asked for the minimum to open a job. I added what an admin usually has to hand and what the later gates need (the review gate needs a peer reviewer, approval a counter-signatory), so they can be set once, up front | Design brief + Me |
| 4.3 | Property category is on the intake form | It drives the conditional fields (plot area for villas, and so on), so they behave correctly from the first opening of the job. This is my reasoning; the code doesn't state it | Me |
| 4.4 | Intake values are applied **through the same write path** as editing a tab | A field is accepted or refused by exactly the same rules whether entered here or later. No second set of validation | Me |
| 4.5 | The whole creation is **one transaction**, with errors collected across all tabs | A rejected value must leave no half-created job, and the user sees every problem at once | Me |
| 4.6 | **Billing address is copied from the bank, only if its SLA is signed** | The spec states this rule | Spec |
| 4.7 | The creator becomes the job's admin | Someone has to own the instruction; the creator is the obvious person | Me |
| 4.8 | The bank must exist and be **active**; unknown fields are rejected | Stops typos and stale clients silently creating bad jobs | Me |
| 4.9 | A new job starts at `instruction_received` | First status in the spec's lifecycle | Spec |
| 4.10 | **Reference numbers** (`BYT-2026-00001`) come from a per-year counter that never reuses a number; the database's unique constraint settles any race | A number that has reached a bank report must never be reissued | Me |

---

## 5. Lifecycle and review

| # | Decision | Why | Source |
|---|---|---|---|
| 5.1 | The lifecycle is **data** (`TRANSITION_RULES`: who, label, comment needed, gate), not scattered if/else | Spec: stages and transitions as config, like Carforce | Spec |
| 5.2 | Illegal status jumps are rejected on **every write path** (API, admin, shell, tasks) | An early bug let a job skip peer review by setting its status directly | Me |
| 5.3 | A move names the status the user was looking at; if the job moved since, it's refused | Prevents acting on a stale screen (e.g. approving something already returned) | Me |
| 5.4 | **Reopen** (signed off → valuation in progress) was added | Not in the spec. Without it a mistake found after approval could only be fixed by issuing and then revising | Me |
| 5.5 | Return and Reopen **require a written reason** | Spec says "with comments" for return; the same logic applies to reopen. It becomes the Comments panel | Spec + Me |
| 5.6 | Sending for review needs **every tab complete** and an assigned peer reviewer | The data freezes at that point, so it must be complete first | Me |
| 5.7 | The peer reviewer must be **someone other than the valuer or signing valuer** (a setting, on by default) | A review only means something if it's independent. It's switchable for a small team | Me |
| 5.8 | Platform admins can act as admin, valuer and inspector, but **never** as peer reviewer or counter-signatory | An admin shouldn't be able to approve or sign on someone else's behalf | Me |
| 5.9 | Approving needs a counter-signatory assigned | Spec: no issue without counter-signature | Spec |
| 5.10 | **Only an admin issues** | Spec | Spec |
| 5.11 | Issuing needs **both** signatories' RERA licences valid | The spec says "signer's"; both signatories print their RERA number on the report | Me (confirm) |
| 5.12 | Issuing is **blocked while any `[PLACEHOLDER` text remains** anywhere in the report | The spec says to use placeholder legal wording until approved; I made the block so a placeholder can never reach a bank | Me |
| 5.13 | Issuing is **one atomic step**: render, store file, record, lock. On failure the job stays open and the file is removed | A job must never be locked without a report, or reported without being locked | Me |
| 5.14 | A **revision** is a new job version that keeps the issued one as signed; once per version; admin only; copies the property, tab data and media | Spec: a re-issue creates a new version and keeps the old one | Spec + Me |
| 5.15 | A revision keeps the **original reference with a version suffix** (`BYT-2026-00012-v2`) | So the bank can match a re-issue to its instruction. Replaced the earlier "new number" approach | You (audit fix #5) |
| 5.16 | The issued job is **locked** at the model level, including its property record | Spec: on issue, the job and report are locked | Spec |
| 5.17 | **Counter-signing is its own step**: in `approved_signed`, only the assigned counter-signatory can "Counter-sign"; issue is blocked until they have. Returning or reopening the job voids the signature | Spec: no issue without counter-signature. An assignment alone isn't a signature. Done as an in-place action rather than a new status, so the lifecycle in the spec is unchanged | You (audit fix #2) + Me (how) |
| 5.18 | **Issuing runs in a Celery task.** The request records it and returns 202; the PDF is rendered once, with no lock held; then the report, lock and log are written under the row lock, after checking nothing changed during the render. Without a worker (dev.sh, tests) it runs inline | Spec: PDF rendering in Celery. Keeps a slow render from holding the job's lock | You (audit fix #8) + Me (how) |
| 5.19 | Evidence (chosen comparables, AVM runs, and comparables an issued report cites) is **frozen with the job**. A revision carries the chosen comparables forward, but not AVM runs | Evidence is part of what was signed; AVM runs are per version (spec §6) | You (audit fix #6) + Me (how) |
| 5.20 | Turnaround is measured from **request received**, else the instruction date, else when the job was keyed in | Spec §7: instruction → issue | You (audit fix #10) |
| 5.21 | **BUA and plot area are entered in sqft**; sqm is calculated. The report shows `519 sqft (48.22 sqm)`. Existing values were converted (migration 0011). This replaces CLAUDE.md §2's sqm entry | Field dictionary: "must always be in sqft" | You (16 Oct 2026) |
| 5.22 | **Custom Villa keeps plot area and satellite measurement**, like villas, although the field dictionary marks them N/A | Custom villas sit on plots; the sheet looked wrong | You (16 Oct 2026) |
| 5.23 | **Disclosure** is inserted from the field dictionary's three statements, as written, then editable. It has no default and is required | Field dictionary | You (16 Oct 2026) |
| 5.24 | **Property Address is its own tab** (between Instructions and Summary), holding the address, parties and title-document fields. Registered valuer and contact for access stay on Instructions | Field dictionary Tab 3; the valuer is about signing, not the address | You (the move) + Me (what stays) |
| 5.25 | **Exact age = valuation year − built year**, falling back to the built date when no year is entered, and to today until there's a valuation date | Field dictionary: "current year − built year"; the valuation year keeps a regenerated report stable | You (sheet) + Me (valuation year) |
| 5.27 | **The form shows only what the field dictionary or the Word report template uses.** Hidden (data kept, not reported): land/build rate, report template, contact for access, type of property, service charge, coastline distance, age band, forced sale value, the under-construction figures, the rental range, GPS in DMS. Added for the report: development, tenant name and tenancy expiry, a single market rent, reinstatement wording, purpose options (Financial Reporting, Acquisition, Disposal) and External inspection | Sheet + report as the source of truth | You (16 Oct 2026) |
| 5.28 | "Total floors" is the number **above the ground floor**, printed `G + n Floors`; age prints as years.months from the built date (whole years from the built year otherwise) | Word template | Me |
| 5.29 | **Tabs are grouped into stages** — Setup (Check List, Instructions, Property Address, Summary), Inspection (Inspection, Photos), Valuation (Location, Valuation, Documents, Evidence), Review & Send. Completing a stage's tabs moves the job on by itself; nothing is locked by stage and a job can be sent for review from any stage once every required field is in. Summary sits in Setup to keep the sheet's tab order with each stage's tabs together | You (16 Oct 2026) + Me (Summary in Setup) |
| 5.30 | **Review & Send tab, simplified**: send for review → the assigned peer reviewer reads the report there and **signs off** (or returns it). **Sign-off is the second signature and finalises the report** in one step: approved, the reviewer recorded as counter-signatory, final PDF produced and the job locked; then the send-to-bank card appears. There is no separate counter-signatory or issue step (an admin can retry if producing the PDF fails) | You (16 Oct 2026) |
| 5.31 | **Sending to the bank** is done by the admin who created the job (or a platform admin), to a bank contact or any email. Only the request is recorded (`ReportDelivery`, status queued); the email itself (SES) is wired in later | You (16 Oct 2026) |
| 5.32 | **The activity log is hidden** from the workspace but still recorded (DLD / RICS audit) | You (16 Oct 2026) |
| 5.33 | **Library text replaces, not appends,** on single-answer fields; Special Assumptions and Other Matters still take several | You (16 Oct 2026) |
| 5.35 | **The firm name stands in for the registered legal name** (`REPORT_FIRM_LEGAL_NAME` defaults to `REPORT_FIRM_NAME`) so reports can be finalised for demos. **Needs the real legal name before any bank sees a report** | You (16 Oct 2026) — Default |
| 5.36 | **Demo mode (`DEMO_MODE`, on by default)**: signing off doesn't wait for the signatories' RERA licences on file or for approved wording in place of placeholder text. Missing required fields still block. **Set `DEMO_MODE=false` before any report goes to a bank** | You (16 Oct 2026) — Default |
| 5.34 | **Evidence**: comparables entered by hand with source, link, building, community, type, beds, floor, view, BUA, price, date, sold/asking and notes; ticked ones fill the report table. **AVM v1** = median AED/sqft of the ticked comparables × subject BUA, rounded to AED 1,000; range = middle half of the rates (lowest–highest under 4); confidence from count and spread; no adjustments yet. Bayut and Property Monitor come in as connectors from an internal export/API, not by scraping their sites | You (what) + Me (how) |
| 5.26 | First-floor accommodation, and rear views, apply to villas, townhouses and custom villas only; a rear view typed before the category changed isn't reported | Field dictionary | Spec (sheet) + Me (custom villa, per 5.22) |

---

## 6. Report

| # | Decision | Why | Source |
|---|---|---|---|
| 6.1 | Jinja2 in a **sandbox**, autoescaped, with **strict undefined** variables | Templates are editable by admins and the data is user-typed: a bad template must fail loudly, and typed text must never inject markup | Me |
| 6.2 | Templates are stored in the database; the shipped default is versioned by a **hash of its content** (`v1-ab12cd34`) | Spec: templates versioned. A hash means editing the shipped file creates a new version instead of rewriting the one old reports used | Spec + Me |
| 6.3 | Each report stores the template version and a **snapshot of every input** | Spec; an issued report re-renders exactly as signed | Spec |
| 6.4 | WeasyPrint for the PDF | Spec's first choice (Playwright was the alternative) | Spec + You |
| 6.5 | **All legal wording is a visible placeholder** until you supply approved text | Spec: never copy another firm's wording | Spec |
| 6.6 | The HTML preview is instant and served with a locked-down security policy | Fast edit-and-check loop; the page is on the API's origin so scripts are denied as a second line of defence | Me |
| 6.7 | Value in words must match the figure **including fils** | An early bug; the words are the legally relevant version | Me |
| 6.8 | Dates print as `26 Aug 2026`; money as `AED 725,000`; area as `48.20 sqm (519 sqft)`, `sqft = sqm × 10.76391` | Spec | Spec |
| 6.9 | Age is measured **at the valuation date**, not today | A report must say how old the building was when valued | Me |
| 6.10 | Every major section starts on a new page | Simple and predictable for v1. It leaves many half-empty pages | Me (**to tune**) |
| 6.11 | The **DRAFT** watermark is drawn as a page background | The first approach rendered once, as a grey block on the last page | Me |
| 6.12 | Executive summary shows the **first three general photographs** in the order set; Appendix 5 shows all included photos | Spec says 3 summary photos; "first three in order" lets the valuer choose them by reordering | Spec + Me |
| 6.13 | Makani and DEWA photos stay out of the summary and are captioned with their numbers if no caption is written | Spec: the appendix shows "DEWA no. and Makani no. photos" | Spec + Me |
| 6.14 | A document in the report is capped at **10 pages**, and the page says so | A 40-page contract doesn't belong whole in a valuation report | Default |
| 6.15 | Scans are limited by **height** on the page | Heading, page and caption must share one A4 page; without this a 3-page deed took 8 pages | Me |
| 6.16 | `pydyf` pinned to 0.10.0 | WeasyPrint 62 breaks on newer versions | Me |
| 6.17 | The service charge unit is left undefined (a TODO) | The spec doesn't say whether it's per sqft or total | Me (**open**) |

---

## 7. Photos and documents

| # | Decision | Why | Source |
|---|---|---|---|
| 7.1 | Accept JPG, PNG, HEIC (and PDF for documents), by **real file type read from the bytes** | A name or declared type proves nothing | Spec + Me |
| 7.2 | Photos are decoded, shrunk to 2400 px and **re-saved as JPEG**; HEIC is converted; PDFs are kept as uploaded | Sharp on a printed page without huge reports; PDFs are only read | Me |
| 7.3 | **Camera metadata, including GPS, is stripped** | Privacy; a phone's location data shouldn't travel with a bank report | Me |
| 7.4 | Limits: 25 MB per file, 20 files per upload, 80 photos and 40 documents per job, 150 pages per PDF | Sensible ceilings against abuse and accidents | Default |
| 7.5 | Upload decoding is **strict about truncated images** even though WeasyPrint relaxes this globally | Found by a test: otherwise a half-uploaded photo would be accepted and filled with grey | Me |
| 7.6 | A bad file is refused alone, with a reason; the rest of the batch is added | One bad scan shouldn't lose a dozen good photographs | Me |
| 7.7 | The same file twice, or already on the job, is refused | Catches accidental re-uploads in bulk selections | Me |
| 7.8 | Stored names are **generated**; the uploaded name is display-only | A file name must not steer where anything is written | Me |
| 7.9 | Removing **hides** the item; the file is never deleted | Issued reports and revisions may still point at it | Me |
| 7.10 | Uploads go **through the server**, not direct to S3 | S3 isn't set up; presigned upload is listed as missing | Me (**gap**) |
| 7.11 | A file is only viewable by someone who can see the job | Files are never behind a guessable public link | Me |
| 7.12 | Captions and settings carry a version (first edit wins); reordering needs the **complete** list of ids and is refused if the list changed | Same rule as everything else; a partial reorder could silently drop an item | You + Me |
| 7.13 | Document types are admin-editable presets | Spec: all dropdown lists are admin-editable presets | Spec |
| 7.14 | A full inspection needs **3 general photos**; drive-by needs 1; desktop none; **every job needs one document** | The summary has 3 photo slots; the document minimum guards against an empty appendix | Default (**confirm**) |
| 7.15 | A bank's Makani/DEWA rule is enforced, and so is a Check List "photo taken" answer without an upload | The bank settings existed with nothing enforcing them | Me |
| 7.16 | Issuing is blocked if an included stored file has gone missing | A report must never carry a hole where an image should be | Me |

---

## 8. Admin and sign-in

| # | Decision | Why | Source |
|---|---|---|---|
| 8.1 | Admin screens (users, banks, presets, text library, templates) are **admin-only with no delete**; use deactivate | Records may be referenced by issued work and must be kept | Me |
| 8.2 | `is_staff` and `is_superuser` are never shown or changed through the API | Privilege flags shouldn't be one click away in a web form | Me |
| 8.3 | Bank rules are validated strictly (unknown keys and wrong types rejected) | A typo like `requires_makani_phto` would silently do nothing | Me |
| 8.4 | Sign-in: 10 attempts a minute per address; **one generic error** for every failure | Slows password guessing; doesn't reveal which emails exist | Me |
| 8.5 | The sign-in check uses the email as typed, then lower-cased | Addresses created by hand in the Django admin may not be normalised | Me |
| 8.6 | Users are not in the audit trail; banks, valuer profiles, presets and the text library are | A user row carries the password hash and last-login time, which would flood the log | Me |
| 8.7 | Licence expiry shows a warning 60 days ahead | A reasonable lead time to renew; a licence can't be used past expiry anyway | Default |
| 8.8 | Everything audited as field-level changes: who, what, old and new value, when | Spec | Spec |

---

## 9. Process and tooling

| # | Decision | Why |
|---|---|---|
| 9.1 | Each slice is verified by tests, linting, a type-check, a production build **and** a real browser run against a throwaway QA database | Tests alone had missed visible bugs |
| 9.2 | QA data is never put in your dev database | A separate SQLite file with throwaway accounts, deleted afterwards |
| 9.3 | Placeholder wording is also the **default for the seeded text library** | So seeded text can't be mistaken for approved wording |
| 9.4 | Tests never write into the project's `media/` folder | Per-test storage isolation |
| 9.5 | `dev.sh` starts both servers, sets the PDF library path, and stops everything on exit | Starting a server through `nohup` silently loses that setting on macOS |

---

## 10. Decisions I deliberately did **not** make

| Left open | Why |
|---|---|
| Final report wording (T&C, assumptions, disclaimer, reliance, independence, skills) | Only you can supply or approve legal text |
| Forced sale discount: 10% or 15%? | The spec lists it as an open question |
| The AVM's adjustment rules and confidence thresholds | They need your valuers' input |
| Which bank to build for first | Only ADIB's service charge exists as a bank-specific rule |
| Whether to use Property Monitor's or Bayut's own estimates | I haven't seen their API documentation |

---

## 11. Defaults and open points that need you

These are the decisions most likely to be wrong, because they were my choice and not yours or the spec's:

1. **Counter-signatory licence at issue:** keep requiring it? (5.11)
2. **Counter-signatory = valuer:** currently allowed; I recommend blocking it. (PRD §5.1)
3. **Upload gates:** 3 general photos for a full inspection; one document per job. (7.14)
4. **Upload limits:** 25 MB, 20 per upload, 80 photos, 40 documents, 150 PDF pages. (7.4)
5. **Report cap of 10 pages per document.** (6.14)
6. **Peer-reviewer independence on by default.** (5.7)
7. **Service charge unit.** (6.17)
8. **Page-per-section layout** to tune against a real template. (6.10)
