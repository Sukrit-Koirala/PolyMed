# EHR Bridge

A fresh, local prototype for the hospital/patient flow: identify a patient, upload a visit, ask for outside records, get patient approval with an OTP, and copy the approved records into the requesting hospital's separate database.

**Official EHR sandbox test:** [Try the downloaded Oracle FHIR R4 sample](demo-reports/oracle-sandbox/README.md). The upload dialog now accepts a supported Patient/Observation FHIR collection through **FHIR R4**. Hospital destination formats remain simulated.

This project is isolated in `ehr-bridge/`. It uses ports **3200** and **8200**, its own cookie, and its own data. Existing projects elsewhere in this workspace are untouched.

## Run on Windows

From the workspace root (`PolyMed\PolyMed`):

```powershell
.\ehr-bridge\run.ps1
```

Open **http://127.0.0.1:3200**. Keep the terminal open; **Ctrl+C** stops this app. The script checks both ports and waits for the API before starting the frontend. API logs are in `ehr-bridge/.data/logs/`; health is at http://127.0.0.1:8200/api/health.

Dependencies are installed in this workspace. On a fresh checkout, install Python 3.12+ and Node 24+, then:

```powershell
python -m venv .venv
.\ehr-bridge\run.ps1 -Install
```

The launcher uses the workspace `.venv` and automatically finds the workspace's portable Node installation when present. If PowerShell blocks local scripts, run `powershell -ExecutionPolicy Bypass -File .\ehr-bridge\run.ps1` for this invocation.

## Demo accounts

All seeded accounts use password **`Demo-access-2026!`**.

| Role | Login | Hospital / status |
| --- | --- | --- |
| Hospital doctor | `emily@bridge.demo` | Dr. Emily Carter, Memorial Hospital; Epic-inspired mock format |
| Hospital doctor | `daniel@bridge.demo` | Dr. Daniel Reed, Valley Medical; Oracle-inspired mock format |
| Second doctor | `jordan@bridge.demo` | Dr. Jordan Lee, Memorial Hospital; demonstrates doctor attribution |
| Patient | `PT-DEMO-SARAH` | Sarah Mitchell; already enrolled |

David (`PT-DEMO-0002`), Amara (`PT-DEMO-0003`), and Noah (`PT-DEMO-0004`) also have enrolled patient accounts with the same demo password. See [DEMO_DATA.md](DEMO_DATA.md) for all patient stories and their histories.

Use a separate browser profile or an InPrivate window for the patient while a hospital is signed in. Ordinary tabs share a login cookie. For three simultaneous roles, use three browser profiles or sign out and switch accounts.

## Five-minute demonstration

1. Sign in as Emily. Find patient **`PT-DEMO-SARAH`**. Memorial can see its own visit. Valley's clinical records are locked until approval.
2. Select **Request outside records**, select Valley, enter a purpose, and choose whether to include images. Send the request.
3. In a separate browser profile, sign in as Sarah. Open **Access requests**. Check the requesting hospital, doctor, purpose, source hospital, version count, and image scope. Select **Generate OTP**, confirm approval, and give the displayed code to Emily.
4. As Emily, open **Transfer requests**, select **Enter OTP & transfer**, and submit the code. The server writes approved version snapshots, converted native data, and approved attachment bytes into **Memorial's database**. This is a real local database copy.
5. Find Sarah again. Valley's records now appear as imported copies. Open **Versions & source**. Compare Valley's medication dose change from 10 to 20 and inspect the original Oracle-inspired JSON, general representation, and stored Epic-inspired JSON. The fictional blood group is preserved separately because the mock Epic adapter does not map it.
6. Sign in as Daniel, find Sarah, and **Upload visit**. Enter a reason and notes, optionally add medications, observations, and a PNG/JPEG/WebP/PDF file. **Native payload** lets you inspect or supply the hospital's mock JSON directly. The visit saves in Valley and the central server, and Sarah can view it immediately.
7. As Daniel, choose **Add an update** on that visit. Save a correction and inspect the new version's authenticated doctor, hospital, timestamp, changes, and earlier attachment snapshots. A new request/approval is needed to transfer later uploads; an earlier approval is a fixed snapshot.

### New patient demonstration

1. As a hospital doctor, select **Register patient**, enter fictional name, DOB, phone, email, and address, and confirm the demo-data checkbox. Review any possible local duplicates.
2. Copy the returned **patient ID and one-time activation code** and hand both to the patient through a trusted channel. The activation code is shown once and expires after 24 hours.
3. In a separate browser profile, choose **Patient → First time? Activate**, enter both items, and choose a password of at least 12 characters.
4. The patient can subsequently sign in with the ID and password. Their medical records are read-only. The hospital can upload visits as soon as the profile exists; the patient must activate before approving transfers.

Knowing someone's ID alone cannot claim their account. Only the registering hospital can reissue activation for an **unenrolled** patient. Activation cannot reset an existing account's password.

## Patient summary and field versions

### Entering measurements

**Upload visit → Clinical entry → Measured observations** has **97 preset fields in 13 expandable categories**: vital signs, blood count, kidney/electrolytes, glucose/metabolism, liver/proteins, lipids, coagulation, inflammation, thyroid/nutrients, respiratory/blood gas, cardiac markers, urine/fluids, and body measurements/scores. Vital signs open first; other sections can be expanded as needed. Each field has a value and unit input, with optional context. Blood pressure has separate systolic and diastolic boxes.

**Other / find a measurement** suggests matching preset names, abbreviations such as `SpO2`/`HbA1c`, and previously used custom field names from the hospital's authorized records as you type. Select a suggestion to open and focus its field. If no preset fits, choose **Use “[your name]” as a new measurement**, then enter its value and optional unit. Arrow keys and Enter select suggestions; Escape closes the suggestions before closing the visit dialog. Suggestions run locally, without sending entered names or patient records to an external search service.

Leave unmeasured fields blank; no values are prefilled from previous visits. Filled values are saved as text with their units, so entering SpO2 `100` with unit `%` produces `100%` and avoids the old numeric-JSON validation error. Zero values are retained. Changing a unit does not convert the number. When editing a visit, original keys, units, context, and unfamiliar reading formats are retained unless edited; clear a field to omit it from the new version. Known aliases such as `SPO2` and `Oxygen saturation` share one history, while distinct tests remain separate.

These presets are an entry aid, not an exhaustive terminology or a clinical interpretation engine. The advanced Native payload and FHIR R4 import tabs remain available. [HL7's vital-sign definitions](https://hl7.org/fhir/R4/observation-vitalsigns.html) and the [UCUM specification](https://ucum.org/ucum) describe the corresponding standards; choosing a form field does not assign a clinical code or establish FHIR conformance.

### Reading values and history

The patient dashboard displays a **Health summary** in plain language. Allergies, medications, measurements, visit details, additional clinical fields, and attachments each have **Show versions**. Lists expand/collapse using their dropdown; a medication's name, dose, unit, and frequency are shown as readable text. Nested additional information is labeled rather than displayed as JSON. The same summary is available when a hospital opens a patient profile.

Each field's history combines every available hospital's stored snapshots and includes the complete field value, clinical date, doctor, hospital, and source version. Values are ordered by **clinical date**, then original source update time and version. A backdated report imported today does not replace a more recent clinical reading. The latest revision of a visit supplies that visit's current values; older revisions remain in the history. Observation labels differing only by case, camel case, or underscores are grouped; `BP` and `Blood pressure` share a history. No fuzzy clinical matching or unit conversion is performed.

The summary shows the latest **reported** value from current visit revisions, rather than merging different hospitals' lists. Empty or missing data is labeled not documented and is not treated as a negative finding or proof of resolution. An observation-only FHIR import does not clear medication/allergy history. A field omitted by a later revision remains visible in history without resurrecting that visit's older value. Zero and false values are retained.

**View source** opens the original source JSON on demand; the picker includes hospital records and their individual versions. Each field/history entry also links to its specific source. Raw integration metadata stays in this source view; clinical result status, interpretations, and reference ranges remain readable in the summary. The dashboard refreshes every five seconds and preserves list dropdown state. Patient access is read-only. Hospital summaries/history include only local records and approved transferred copies.

## Populate and reset demo data

The app seeds **2 hospitals, 3 doctors, 8 patients, 32 visits, 48 versions, and 16 PDF reports** by default. Every patient has detailed notes and records at both hospitals, with histories spanning 2025–2026. Four patient accounts are enrolled and four remain available for activation. One pending Memorial request for Sarah's Valley records is included; no transfer is pre-approved. The ankle imaging report is a fictional narrative rather than an actual X-ray image. See [DEMO_DATA.md](DEMO_DATA.md).

Add more patients without replacing existing demo work:

```powershell
.\ehr-bridge\scripts\seed.ps1 -Patients 24
```

Seed is idempotent: repeated runs do not duplicate patients/visits or overwrite changes. `-Patients` sets the seeded population target, between 2 and 500; it does not remove extra patients. Existing starter charts are preserved; use reset to replace them with the detailed dataset.

To restore a clean demonstration, stop this app with Ctrl+C, then:

```powershell
.\ehr-bridge\scripts\reset-demo.ps1 -Patients 24
.\ehr-bridge\run.ps1
```

**Reset replaces this project's three demo databases**, removing its created patients, accounts, sessions, uploads, requests, and transfers. It first saves SQLite backups under `ehr-bridge/.data/backups/`. It refuses while API port 8200 is active and cannot reset a directory outside this project. It never resets the other workspace projects.

To inspect counts or seed an isolated dataset:

```powershell
Set-Location ehr-bridge
..\.venv\Scripts\python.exe -m server.cli inspect
..\.venv\Scripts\python.exe -m server.cli seed --patients 24 --data-dir .data\practice
```

Set `BRIDGE_DATA_DIR` before launching the API to use an alternate data directory. `BRIDGE_DEMO_PASSWORD` changes the initial seeded account password; it does not overwrite accounts already created. The default public demo credentials are intended for local demonstrations only.

## What is stored and authorized

| File | Contents |
| --- | --- |
| `.data/central.sqlite3` | Patient registry, hashed credentials, sessions, general visit model, original source payloads, immutable versions and files, requests, transfer receipts, audit events |
| `.data/memorial.sqlite3` | Memorial's local patient IDs, source visits, approved imported snapshots, translated Epic-inspired JSON, preserved fields, and actual attachment bytes |
| `.data/valley.sqlite3` | Valley's independent local records and Oracle-inspired JSON |

The canonical/general model covers visit date, reason, notes, medications with units/frequency, allergies, observations, and additional fields. Original input JSON is retained. Unmapped additional information is retained separately and displayed; translation does not silently drop it. Hospital-native patient IDs are associated with the global patient ID.

Hospital accounts read clinical versions and files from their **local hospital store**. Global ID lookup reveals minimal identity and source counts so a doctor can request records; it does not reveal outside clinical content. Patient accounts can read only their own central records. All clinical writes require a hospital session; doctor/hospital attribution comes from that authenticated session.

Each request expires after 24 hours and fixes the list of source versions at request time. OTPs expire after 5 minutes, have a five-attempt limit, and are bound to the requesting doctor and hospital. Regeneration invalidates the previous code. A successful code cannot be reused. A patient may deny a pending request. A completed copy remains at the hospital and **cannot be recalled**. Repeated transfers deduplicate version copies; later image approval can add an authorized attachment without rewriting an earlier snapshot.

Updates append versions rather than overwrite them. Concurrent stale updates are rejected; upload retries with the same idempotency key do not create duplicate versions. Prior attachment snapshots remain available in their original versions. Request completion and local transfer writes commit together; a failed destination write leaves the code usable for retry.

Attachments: up to 4 new files per upload, 5 MiB per file, 10 MiB combined new bytes, and 10 attachments per version. PNG, JPEG, WebP, and PDF are checked for type signatures, stored with SHA-256 hashes, and served through authenticated routes. This is not a DICOM viewer or a malware scanner.

## Scope and additions to consider

This is a **local prototype using fictional data**, including official Oracle sandbox test resources. Epic/Oracle hospital destinations use deliberately simplified mock adapters. A narrow FHIR R4 Patient/Observation import is supported; full FHIR profile validation and authenticated writes to live hospital EHRs are not implemented. The separate fixture downloader reads Oracle's public sandbox. Notifications are in-app and refresh every five seconds; no SMS/email is sent. Local database files and backups are not encrypted.

Before expanding the demonstration or using real information, decide these product gaps:

- **Account recovery and identity verification:** lost patient IDs/passwords, verified contact details, hospital/doctor enrollment, and staff lifecycle management. Secure first-time activation is already included.
- **Consent detail and retention:** date/category/document-specific sharing, who within the receiving hospital can use a completed copy, and retention rules. Stopping a pending transfer and recalling an existing copy are different operations.
- **Patient matching and corrections:** cross-hospital duplicate review/merge, demographic corrections, and a patient-requested correction process that still preserves the original clinical versions. The current duplicate warning covers the hospital's local patients only.
- **Real integration and operations:** agreed vendor/FHIR mappings and terminology, vendor credentials, encrypted storage/backups, HTTPS, durable delivery/retry monitoring, malware scanning, DICOM support, and a complete record-view/download audit. The current audit covers authentication, lookups, uploads, and consent/transfer actions.

## Development and checks

Backend (from `ehr-bridge/`):

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8200
```

Frontend (another terminal, from `ehr-bridge/web/`, with Node on PATH):

```powershell
npm run dev
npm run typecheck
npm run build
```

Browser checks require an API with a **fresh isolated seeded dataset**, the frontend on 3200, and Microsoft Edge on Windows. Stop the ordinary app, set `BRIDGE_DATA_DIR` to a new path inside `.data/` in the API terminal, start the API and frontend, then run `npm run test:e2e` from `web/`. These checks create fictional patients/records/transfers; they should not use your demonstration database. Screenshots are written to `.data/screenshots/`. See [VALIDATION.md](VALIDATION.md) for the checked scenarios.
