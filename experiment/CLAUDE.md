# Valuation Platform: Project Context for Claude Code

> Handoff from a Claude (Cowork) planning session, 14 Oct 2026. Owner: Izza Naseer (izza.naseer@dubizzlelabs.com), Dubizzle Labs.
> Read this file fully before writing code. Current focus: **web app + backend**. The Property Monitor API is the **last** priority.

---

## 1. What we are building

An in-house **real estate valuation platform** for Dubizzle Group / Bayut. It replaces the off-the-shelf tool the valuation team uses today (ValuePro on iPad).

Purpose: valuers enter a property valuation instruction across 9 tabs. The system suggests a data-backed value and generates a **bank-ready PDF valuation report** from a preloaded template.

Business goal: approach **UAE banks** (mortgage-security valuations) and get on their valuer panels. We compete with Colliers, CBRE, Knight Frank and others. Our edge is **data + tech**:

- comparables from Bayut listings and Property Monitor transactions (Property Monitor was acquired by Dubizzle Group in April 2025)
- an automated valuation model (AVM) that suggests a value range
- fast, consistent, compliant reports

Launch scope:

- Property types: apartments, villas, townhouses, offices, retail units.
- Location: Dubai first.
- Out of scope for launch: commercial investment-method valuations, the iPad app, WhatsApp, a bank portal/API, the Property Monitor API.

## 2. Domain essentials

- **Regulators:** Dubai Land Department (DLD) and RERA.
  - Valuers must be RERA-registered.
  - Banks must use registered valuers.
- **Standards every report cites:**
  - Emirates Book Valuation Standards (EBVS)
  - RICS Valuation – Global Standards ("Red Book", 31 Jan 2025 edition)
  - IVS (31 Jan 2025)
- **DLD Administrative Resolution 67/2020:**
  - Firms keep an **electronic register** of valuations. Fields: requester name, contact and legal status, purpose, property type and details, developer, ownership form, estimated value, valuation date.
  - Keep reports, files and documents for **at least 5 years**.
  - Register each completed valuation via the DLD electronic system.
- **Basis of value:** almost always Market Value. Approach: Market approach, Comparable method.
- **Units:** areas are entered in sqm and displayed as `48.20 sqm (519 sqft)`. Conversion: `sqft = sqm × 10.76391`. Currency is AED.
- **Glossary:**
  - BUA = built-up area.
  - SPA = sale and purchase agreement.
  - Makani = Dubai's geo-address number.
  - DEWA = utility account number.
  - Title Deed = DLD ownership certificate.
  - Site (Affection) Plan = plot plan.
  - Granted title = land granted by the government; it needs the ruler's permission to sell, which can cost up to 50% of value.
  - Forced sale value = market value less a discount.
  - Reinstatement = rebuild cost for insurance.
  - Peer reviewer = second valuer checking the work.
  - Counter-signatory = second signature authorising the report.

## 3. Users and roles

One user can hold several roles on a job (today one person, "Dan", does most of them).

| Role | Responsibilities |
|---|---|
| Admin | Creates the instruction; enters client, references and title-document data; issues the report |
| Inspector | Site inspection: Check List, Inspection tab, photos |
| Valuer | Summary, Location & Description, Valuation; picks evidence; sets value; signs |
| Peer Reviewer | Approves or returns the valuation before issue |
| Counter-signatory | Second signature on the report |

**Job lifecycle (state machine):**

`instruction_received → setup → inspection_scheduled → inspected → valuation_in_progress → peer_review (→ back to valuation_in_progress with comments) → approved_signed → issued`. A re-issue creates a new version and keeps the old one.

Rules:

- A report can't be issued without peer review and counter-signature.
- On issue, the job and its report are **locked**. Any change creates a new version.
- A report can't be issued if the signer's RERA licence has expired.
- Every field change is audit-logged (who, what, old/new, when).

## 4. Data capture: the 9 tabs

Source: the business spec "REAL ESTATE VALUATION SOFTWARE" plus the ValuePro walkthrough video.

- "Admin later" = the Valuer fills it for now; it moves to an Admin role as the team grows.
- All dropdown option lists are **admin-editable presets**, not hard-coded.
- Many options carry a **preset paragraph** of report text that the valuer can edit per job.

### Tab 1: Check List
- Inspected By (user dropdown)
- Valuer (user dropdown)
- Peer Reviewer (user dropdown)
- DLD Location checked (Y/N; checked on the Makani website / DDA)
- Makani Photo (Y/N, whenever available)
- DEWA Photo (Y/N, whenever available)
- Newly Handed Over (Y/N)
- Satellite Measurement (Y/N; cross-check applicable to **villas/townhouses only**)
- Land Rate Applied (number, default 0; plots / special cases)
- Build Rate Applied (number, default 0; only when reinstatement is needed)

### Tab 2: Instructions
- **References and dates:**
  - Bank Reference No. (per request received by email; Admin later)
  - Bayut Internal Reference No. (auto-generate)
  - Report Template (select a template version)
  - Date/Time request received (Admin later)
  - Date of Instruction
- **Client:**
  - Organisation (bank) / Client name (from the Bank master)
  - Billing address (**auto-filled from the Bank master once the SLA is signed**)
  - Purpose: Mortgage Security / Audit Purpose / Internal Purpose
- **Property address:**
  - Unit Number
  - Building Name (villa community name for villas)
  - Community Name (master dropdown later, e.g. Downtown Dubai, JVC)
  - Latitude and Longitude (from Google Maps, entered manually)
  - Auto-convert to DMS for the report, e.g. `25°2'25.1"N 55°17'10.4"E`
- **Parties:**
  - Applicant Name
  - Ownership Name
- **Title document:**
  - Document type: Title Deed / Site Plan / Site Affection Plan / SPA / Ownership Certificate / Ownership Deed / Usufruct Certificate / Initial Contract of Sale / Initial Sale Certificate / Pre-Registration Certificate / Oqood etc.
  - Fields as per the document: Property No., Plot No., Municipality No., Building No., Building Name, Community, Emirate
  - **Address as per document (auto-formulated)**, e.g. `Property No. X, Plot No. Y, Municipality No. Z, Building No. 1, <Building>, <Community>, Dubai, United Arab Emirates`
- Registered Valuer (signing valuer)
- Contact for access

### Tab 3: Summary
- Interest Valued: International Freehold / International Long Leasehold / GCC Freehold / GCC Leasehold / Granted title / Freehold for UAE Nationals only / Musataha / … (each option has preset text)
- Lease Expiry (date; **only when Interest = International Long Leasehold**)
- Acquisition Method: Purchased / Gifted / Granted / Allotment
- Makani Number
- DEWA Number
- Information Provided (multi-select): Title Deed, SPA, Site Plan, Site Affection Plan, Floor Plan, Developer's Floor Plan, Tenancy Contract … (extendable)
- Market Commentary (template by type: apartment / villa / office / retail)
- Property Floor No.
- Floor Configuration (text, e.g. `B+G+2P+10`)
- Ground Elevation (metres above sea level; valuer's responsibility)
- No. of Bedrooms
- Property Category: Apartment / Villa / Townhouse / Duplex / Penthouse / Custom Villa / Shell & Core Office / Fitted Office / Shell & Core Retail / Fitted Retail / …
- Type of Property (free text, e.g. "1-Bedroom Apartment")
- Parking (Y/N)
- No. of Parkings (number, or "assumed none")
- BUA:
  - entered in sqm; sqft auto-calculated
  - BUA Source: Title Deed / Site Affection Plan / Initial Certificate of Sale / SPA
  - if the source is an SPA, the report must state that the area is assumed correct
- Plot Area:
  - sqm with sqft, **villa/townhouse only**, else "Not Applicable"
  - Plot Area Source
- Disclosure (default text: the signatories confirm they have no existing relationship with the client/applicant and have not previously valued the property)
- Capacity of Valuer (default **External**; RICS requirement)
- Departures (default **None**; RICS requirement)
- Assumptions (library + free text)
- Special Assumptions (library + free text). Library examples:
  - Granted title converted to freehold
  - Hotel apartment rental-pool restriction
  - Assumed UAE Freehold
  - Compound limited access
  - Extension/modification permission assumed
  - No NOC / assumed NOC
  - Satellite imagery
- Other Matters (library). Examples:
  - Title deed size error (clerical; recommend rectification)
  - Wrong plot size
  - Wrong floor plans
  - Structural damage
  - Sharjah properties
  - Sample unit inspection
  - Road noise
  - Payment plan
  - Phone mast
  - Restricted freehold
  - Drive-by/desktop assumed good condition
  - Exaggerated BUA
  - Illegal modifications
  - Under-construction phase notes
  - Vacant & furnished

### Tab 4: Inspection
- Inspection Date
- Inspection Type: Full / Desktop / Drive-by
- Service Charge (**only for Abu Dhabi Islamic Bank**)
- Roof: Reinforced concrete / Metal sheeting …
- External Walls: Rendered over blockwork / Glass cladding / Stone cladding / Curtain wall glazing / Panel cladding / Precast panels / mixtures …
- Structure: Reinforced concrete …
- Flooring (multi): Ceramic tiles / Porcelain tiles / Marble / Granite / Parquet / Wooden laminate / Carpet / Polished concrete …
- Walls (multi): Emulsion paint / Ceramic tiles / Wallpaper / Stone/Marble/Wooden cladding …
- Ceiling (multi): Emulsion paint / False ceiling …
- Lighting (multi): Cove / Recessed / Spot / Strip / Suspended / Provisions provided (shell & core)
- Electrical Services: Connected / Not connected / Assumed connected
- Water: same options as Electrical Services
- Sewerage (Mains drainage): same options as Electrical Services
- Air Conditioning: Central / District cooling / Split / Split ducted / Wall-mounted split / Window
- Occupancy Title (floor): Ground / 1st…nth / Mezzanine / Basement / Podium / Upper/Lower level / Outbuilding
- Accommodation Details (multi-select rooms per floor + parking), e.g. "Living/Dining room, Kitchen, Guest WC, Bedroom (en-suite), 2x Balcony"
- Occupancy: Vacant / Owner occupied / Tenanted / Not applicable
- Rent if any (AED)
- Sale Price if any (AED)
- Front Views
- Rear Views
- Upgraded (Y/N); if Y, the upgrade / modification comment is **required**
- Repairs (if any)

### Tab 5: Location & Description
- Property Status: Complete / Under Construction
- Built About (year)
- Built Date
- Exact Age (auto from built date; only some banks need it)
- Property Age band (e.g. "9 to 10")
- Developer
- Sub Community (preset text per community, editable)
- Location (preset text per community, editable)
- Amenities (multi / text)
- Property Specification: Standard property (inspected) / Modified property (inspected) / Custom specification / Standard property (desktop) / Shell & core office / Fitted office/retail / Under construction / Upgraded unit / Fully upgraded / Minor modifications / Drive-by private villa assumed / Vacant land (each with text)
- Property Condition: Developer standard / Good / Average / Below average / Maintenance required / Under construction / Desktop/Drive-by – assumed good / Vacant land / Off-plan (each with a condition paragraph)

### Tab 6: Valuation
- Valuation Date (usually the inspection date)
- Report Date
- Basis of Valuation: Market Value / Fair Value / Market Rent / Investment Value / Market Value (Assuming Transferable Title)
- Valuation Approach (default: Market approach – Comparable method)
- Valuation Commentary (templates by type: Typical Apartments / Villas / Offices / Northern Emirates / Unique property / Lack of direct comparables …)
- Market Value (AED)
- Market Rent / Estimated Rental Range (AED p.a., low–high)
- Forced Sale Value = MV less 10% or 15% (configurable; **open question**)
- Reinstatement Value (villa/townhouse only)
- **Under-construction sub-section:**
  - Construction Cost
  - Completion %
  - Land Cost / Land Only Value
  - As-Is Value (current state)
  - Assumed Complete Value (with special assumption)
- Material Valuation Uncertainty note (toggle; RICS VPS 3 / VPGA 10 text)

### Tab 7: Photos
Upload, caption and order. Feeds the report's executive-summary photos (3) and the Appendix "Inspection Photographs" (2-column grid with captions, incl. DEWA no. and Makani no. photos).

### Tab 8: Documents
Upload title deed, SPA, plans and so on. Selected documents are rendered in the Appendix "Documents Received".

### Tab 9: Evidence
Comparables: transactions + asking prices. See §6.

### Fields seen in the sample report but missing from the business spec (add them)
- Linear distance from the nearest coastline (km)
- Estimated remaining economic life of the building
- Views summary
- Utilities connection status summary
- Year of construction / completion %
- Market value rate (AED/sqft, auto = MV ÷ BUA sqft)
- Estimated rental range
- Counter-signatory
- Valuer qualifications and RERA/RICS registration numbers

## 5. Report generator

Generate a branded **PDF** that matches the finalised template. The structure below follows the reference sample EV-66983, a 34-page Colliers report used **for structure only**. Our template must use **our own branding and our own legal, T&C, assumptions and disclaimer wording**; never copy Colliers text.

Sections:

0. **Cover:** property address, Valuation Ref No., Valuation Date, Prepared by / Prepared for (bank).
1. **Executive Summary:**
   - 3 photos
   - **Property Details** table: bank, ref, applicant, GPS (DMS + decimal), address as per inspection, address as per title deed, plot no., building, community, BUA, plot area, floor, total floors, elevation, coastline distance, interest valued, acquisition method, type, views, developer, year built / completion %, age, remaining economic life, utilities, upgrades, occupancy
   - **Valuation Summary** table: purpose, approach, dates (instruction, inspection, valuation, report), basis, standards, **Market Value in figures + words**, rate per sqft, rental range, valuer + counter-signatory blocks (name, title, qualifications, RERA/RICS nos.), capacity, departures
2. **Terms of Engagement:** addressee (bank + PO box), reliance statement, standards, basis of value (IVS Market Value definition + highest and best use), independence and objectivity, disclosure, knowledge and skills, assumptions, special assumptions, other matters.
3. **Extent of Due Diligence:** inspection statement, information provided (bullets), property areas table (item / area / source).
4. **Property Analysis:** location text + **location map** (static map from lat/long), description, accommodation table, building specification table (roof, walls, structure, flooring, walls, ceiling, lighting, utilities, A/C), communal amenities, condition paragraph, tenancy, reinstatement note.
5. **Market Commentary:** supply / rental / sales text and tables (manual or library text at launch; Property Monitor data later).
6. **Valuation Methodology:** comparable method text, valuation commentary (with market range), **comparables table** (District · Views · BUA sqft · Type · Net Price AED · Transaction e.g. "Sold, August 2026" / "Asking, August 2026").
7. **Opinion of Market Value:** value in figures + words, gross-of-costs statement, signature blocks, basis definition, optional special note (material valuation uncertainty).
8. **Disclaimer.**
- Appendices:
  1. Terms & Conditions
  2. General Assumptions
  3. Bases of Valuation
  4. Documents Received (images)
  5. Inspection Photographs

Generator requirements:

- Number to words: `725000 → "Seven Hundred and Twenty-Five Thousand UAE Dirhams"`.
- Header logo; footer `Valuation Ref No.: X` + `Page | n` on every page.
- Not-applicable rows and sections are hidden or show "Not Applicable" (plot area, lease expiry, under-construction values, service charge for non-ADIB).
- Templates are versioned in the DB; each issued report stores its template version and a snapshot of its inputs.
- Per-bank template variants are supported.
- Text libraries are admin-editable; each job edits its own copy.
- Preview → edit free text → regenerate. Target under 30 seconds.
- PDF required; Word export optional later.

## 6. Evidence and AVM (Property Monitor API = LAST)

Build evidence in this order:

1. **Manual comparables:** form entry + CSV/Excel upload.
2. **DLD open data** (Dubai Pulse `dld_transactions-open`) imported into our own table; match on building / community / type / BUA.
3. **Bayut listings** (asking prices) via an internal export.
4. **Property Monitor API** (transactions, rents, master data). Last.

Design one internal `Comparable` schema with `source` (manual / csv / dld / bayut / property_monitor), `source_ref`, `pulled_at`, plus price, BUA, type, beds, floor, view, date, sold/asking. New sources are just connectors.

Evidence requirements:

- Auto-suggest comparables for the subject.
- Filters: date range (default 12 months), BUA ±20%, bedrooms, floor, view, sold vs asking.
- Valuer ticks which comparables go into the report.
- Each comparable keeps its source and pull date.

AVM v1 (simple, explainable):

- Median AED/sqft of the selected comparables, with configurable adjustments (size, floor, view, date, condition).
- Outputs: suggested value, low–high range, AED/sqft, confidence (high/med/low from count and similarity).
- Show the workings.
- If the final valuer value deviates from the AVM by more than X% (default 10%), require a reason.
- Store every AVM run per job version.
- **The valuer always sets and signs the final value** (RICS).

## 7. Compliance and non-functional requirements
- Valuation register (DLD fields above), exportable.
- Authority reporting data, per the sample report T&C: client details; property (building, developer, location, type, tenure, size sqft/sqm, ownership); valuation (method, valuer status, value, date, property type, purpose); assumptions.
- 5-year retention, soft deletes only, full audit trail.
- Valuer profile: RERA no., RICS no., qualifications, title, licence expiry; issue blocked if expired.
- Conflict check: warn if the property or applicant was valued before.
- Bank master: name, billing address, PO box, contacts, SLA status, bank-specific rules (e.g. ADIB service charge, Makani/DEWA photo requirements, exact age).
- Email delivery of the issued PDF with a delivery log.
- Turnaround metrics (instruction → issue).
- Google Workspace SSO, RBAC, encryption, **UAE-region hosting** (AWS me-central-1).
- Uploads: JPG/PNG/HEIC/PDF, bulk, compress/convert, presigned direct-to-S3.
- Responsive UI (usable in an iPad browser until a native app exists).

## 8. Tech stack (agreed direction)

| Layer | Choice |
|---|---|
| Backend | Python 3.12, Django 5, Django REST Framework, PostgreSQL 16 |
| Async jobs | Celery + Redis (PDF render, image processing, imports, email) |
| Frontend | Next.js (React, TypeScript), React Hook Form + Zod, TanStack Query, Tailwind |
| Form engine | **Config-driven field definitions** (visibility/required rules, options, defaults) shared by UI and validation; mirrors how Carforce defines flows via config |
| PDF | Jinja2 HTML/CSS templates → WeasyPrint (or Playwright) |
| Maps | Google Static Maps (or Mapbox) for the location map |
| Storage | S3 (UAE region), presigned uploads |
| Email | AWS SES |
| Auth | Google Workspace SSO (OIDC) + role-based permissions |
| Infra | Docker, docker-compose locally; AWS me-central-1; CI/CD |
| Admin | Django admin for banks, users, presets, text libraries, templates |

Carforce (the team's other product) uses config files to define flow stages and variables. Reuse that style: job stages and transitions and tab field definitions as config.

## 9. Core data model (starting point)
- `Bank` (client master, SLA, billing, rules JSON)
- `User` / `ValuerProfile` (roles, RERA/RICS, licence expiry)
- `Job` (refs, status, version, assigned users, timestamps)
- `Property` (address parts, title doc fields, lat/long, community, building)
- `ChecklistData`, `InstructionData`, `SummaryData`, `InspectionData`, `LocationData`, `ValuationData`: one per tab, or one JSONB `tab_data` validated by field config. **Decide early.** Recommendation: typed columns for fields used in calculations, reports and the register; JSONB for the long tail.
- `PresetOption` (field key, label, report_text, order, active)
- `TextLibraryItem` (category: assumption / special_assumption / other_matter / condition / spec / commentary, title, body)
- `Photo`, `Document` (S3 key, caption, order, include_in_report)
- `Comparable`, `JobComparable` (selected, order)
- `AVMRun` (inputs, outputs, confidence)
- `ReportTemplate` (version, html, css, bank variant), `ReportVersion` (pdf key, template version, input snapshot, issued_at, issued_by)
- `ValuationRegisterEntry`
- `AuditLog`

## 10. Build order
1. Repo scaffold (monorepo `backend/` + `web/`, docker-compose with Postgres + Redis), auth/SSO stub, roles.
2. Data model + migrations + Django admin for masters and presets.
3. Field-config engine + 9-tab job form (autosave, conditional fields, calculations: sqft, age, rate/sqft, forced sale, DMS, value-in-words).
4. **Report generator** matching the template (highest value for bank demos), using placeholder branding until the final template arrives.
5. Photos/documents upload → report appendices.
6. Workflow: stages, peer review, lock-on-issue, versioning, register, audit log.
7. Evidence: manual + CSV, comparables table in report, AVM v1.
8. DLD open-data import; email delivery (SES).
9. Bayut listings connector.
10. Property Monitor connector (last).

**Definition of done for MVP:** re-run 3 real past jobs end to end and produce reports that match the finalised template.

## 11. Open questions (don't block on these; use sensible defaults and mark TODO)
- Final branded report template + our own T&C / assumptions / disclaimer text (not available yet; use placeholders).
- Forced sale discount: 10% or 15%, per bank?
- Launch counter-signatory and peer reviewer names + RERA/RICS nos.
- First target bank and its specific requirements.
- Desktop (no-inspection) valuation product in scope?
- Source of market commentary tables at launch.
- DLD register submission system and whether it can be integrated.
- Property Monitor and Bayut data access details (later).

## 12. Reference materials (in `/docs`)
- `REAL ESTATE VALAUTION SOFTWARE.docx`: business field spec (9 tabs)
- `EV-66983_EvaluationReport_redacted.pdf`: sample bank report (structure reference only)
- `ValuePro_walkthrough_transcript.txt`: 24-min walkthrough of the current tool
- Claude Docs: "Valuation Platform – Requirements for Bank Launch" and "ValuePro Walkthrough – Tabs & Requirements"
