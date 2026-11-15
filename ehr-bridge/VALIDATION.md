# Validation

Checked on Windows with Python 3.14, Node 26.13.1, Microsoft Edge, and the locked project dependencies.

## Automated results

- **Backend: 18 tests passed.** `..\.venv\Scripts\python.exe -m pytest tests -q`
- **Frontend production build passed.** `npm run build`
- **TypeScript check passed.** `npm run typecheck`
- **Frontend checks passed: 16 model tests and 8 browser scenarios (24 total).** The latest full suite passed against the production build with isolated data in `.data/e2e-measurements-final/`, through `npm run test:e2e`. Earlier detailed-seed checks used `.data/full-data-preview/`.

The backend suite checks:

1. Outside versions are inaccessible before approval; OTP redemption writes actual rows to the separate destination SQLite file in its mock native format, retaining original source JSON and unmapped data.
2. Image bytes are protected before consent and physically copied to the destination database after consent.
3. Excluding images excludes their metadata and bytes; a later explicit image approval adds them without rewriting an existing record snapshot.
4. Patient sessions cannot perform hospital clinical writes or read another patient's clinical record through hospital routes.
5. First-time account activation requires ID plus activation code; codes cannot be reused or reset enrolled accounts.
6. Versions preserve source hospital, authenticated doctor, timestamp, old content, and stale-update rejection; database triggers reject history modification.
7. OTP attempts, expiry, doctor binding, denial, and replay rejection are enforced.
8. Requests include a fixed set of versions and do not silently include later uploads.
9. An injected destination-database failure rolls back the transfer and leaves the OTP available for a successful retry.
10. Duplicate review, mismatched payload patient IDs, and false image MIME claims are rejected.
11. Seed is idempotent and can grow the fictional patient population.
12. Upload retries with an unchanged idempotency key return the original committed version; altered retry content is rejected.

The browser suite signs into separate hospital and patient browser contexts, uploads an image, requests records, generates patient OTP approval, rejects an incorrect OTP, completes a transfer, verifies the copied image bytes, inspects translated JSON and version changes, and confirms persistence on reload. It also registers/activates a new patient, logs back in with ID/password, appends a visit correction, and checks patient navigation at a 390px mobile width with no horizontal page overflow.

One upstream Starlette test-client deprecation warning is emitted for `httpx`; the tests pass. The prototype keeps its existing compatible dependency set.

## Manual/script checks

The detailed seed CLI was run twice against an isolated dataset: both runs reported **2 hospitals, 8 patients, 32 visits, 48 versions, and 16 PDF reports**, with no duplicated rows. A dedicated seed test checks chart completeness, historical dates, doctor attribution, local database copies, four enrolled patient accounts, one pending request, PDF signatures/hashes, idempotence, and correct pre-procedure chronology. The upload API rejects attempts to supply the seed builder's historical timestamp override.

At the user's request, the ordinary demo database was replaced with this detailed dataset. All three previous database files were backed up under `.data/backups/` and passed SQLite integrity checks before any old file was removed. The original backup contains **10 patients, 11 visits, 12 versions, and 2 transfers**. Restoration instructions are saved alongside the backups in `README.txt`. The reset and launcher PowerShell scripts completed successfully, and startup did not duplicate the new records.

The live replacement dataset contains **8 patients, 32 visits, 48 versions, 16 reports, one pending request, and no completed transfers**. A read-only browser check verifies Sarah's detailed visit notes, six cross-hospital blood-pressure snapshots, allergy list, authenticated PDF download, and pending consent request. Existing hospital credentials and Sarah's login remain available. Other workspace projects were not modified.

The transfer uses an on-disk central database with an attached on-disk hospital database and rollback journals, rather than WAL. This is the local configuration in which SQLite supports transactions across attached databases; see the [SQLite ATTACH documentation](https://www.sqlite.org/lang_attach.html). The failure-injection test covers the application's rollback behavior. It does not establish a distributed transaction guarantee for remote EHR systems or test power-loss recovery.

These checks validate a local prototype. They do not validate real Epic/Oracle compatibility, clinical correctness of user-supplied information, DICOM interpretation, malware protection, or production security/compliance. All medical input used in testing is fictional.

## Official Oracle FHIR sandbox check

The fixture downloader performed successful HTTP GET requests against Oracle's documented public R4 sandbox for Patient `12742400` and Observation `L-209133576` (Potassium Level, LOINC `2823-3`, `4.4 mmol/L`). Original response bytes and their SHA-256 hashes are retained under `demo-reports/oracle-sandbox/`; both saved resource hashes were verified against `fetch-receipt.json`. A local FHIR collection Bundle contains the unchanged Patient and Observation resources.

Three added backend tests verify the official fixture import and OTP transfer into a separate hospital database; preservation of original JSON, patient identity, LOINC, units and numeric value; explicit patient confirmation, matching name/DOB and source-URI binding; and rejection of unsupported resources, mismatched subjects, entered-in-error status, absent units, conflicting values, and grouped observations without partial writes.

The fifth browser scenario registers the sandbox patient, imports the downloaded file using the FHIR R4 tab, activates that patient's account, requests records from another hospital, generates and redeems the OTP, and inspects the original FHIR and converted local format. The resulting screenshot is `.data/screenshots/oracle-fhir-conversion.png`.

This checks a supported FHIR R4 quantity Observation mapping, rather than full FHIR profile/invariant conformance. The remote sandbox is used only for reads; the receiving hospital remains a local mock. No write to Oracle or Epic was attempted.

## Patient dashboard and cross-hospital field history

Eight focused model checks cover clinical-date ordering despite a newer upload timestamp, complete list snapshots from multiple hospitals, FHIR observations not clearing allergy/medication history, omitted values in newer source revisions, backdated visit corrections, nested additional fields/files/zero/false values, deduplication of repeated copies, and separate histories for different lab tests' reference ranges and statuses.

The added browser scenario creates a 2025 Valley blood-pressure record, a current Memorial visit, an older report uploaded last, and a second Memorial version authored by a different doctor. While the patient dashboard stays open, it verifies the live update to `120/80 mmHg`, Apple/Almond allergy and Ibuprofen/Mouth wash medication dropdowns, preservation of dropdown state, readable nested fields, and no raw JSON in the default patient view. Field history includes every reading/source and source version, with the latest value first. Original payloads open only on View source. Mobile history is checked for overflow. The hospital view is separately checked to exclude an unapproved outside version.

The existing official-FHIR browser scenario also checks its patient's plain-language observation card and absence of raw JSON in the summary. Screenshots were generated for the readable dashboard, blood-pressure history, and mobile history under `.data/screenshots/` and the desktop summary/history were visually inspected. No backend/schema or existing demo patient data changes were required for this display change.

A separate read-only browser smoke against the ordinary development server verifies the summary, field history, source viewer, and mobile width with no browser runtime errors. The normal demo dataset is preserved; test uploads were made only to isolated test databases.

## Measurement forms and autocomplete

The JSON observation textarea is replaced by 97 preset fields in 13 expandable categories, with value/unit inputs, paired blood-pressure inputs, optional context, and a searchable Other/custom field option. Suggestions match names/abbreviations and previously recorded keys from the hospital's authorized patient records. No external autocomplete service is called.

Eight measurement-model checks verify blank fields produce no invented values, numeric SpO2 and zero become valid stored text, half-entered BP and invalid numeric input give field-specific errors, unchanged original keys/units/context/text readings round-trip exactly, explicit unit selection does not convert numbers, custom text/units/comparators work, suggestions rank abbreviations and avoid duplicate aliases, and SpO2 aliases share history while pulse/heart rate remain distinct.

Two added browser scenarios verify preset selection and automatic field focus, keyboard navigation, Escape dismissing suggestions without closing the visit, custom numeric/qualitative measurements, exact stored values (`120/80 mmHg`, `100%`, `0/10`, etc.), and preservation of original readings while editing notes. The measurement dialog is checked at 390px for horizontal overflow. Screenshots of the desktop suggestions and mobile fields are saved under `.data/screenshots/` and were visually inspected. Existing upload, consent, transfer, source-view and patient-history scenarios also pass with the new forms.
