# Validation

Checked on Windows with Python 3.14, Node 26.13.1, Microsoft Edge, and the locked project dependencies.

## Automated results

- **Backend: 13 tests passed.** `..\.venv\Scripts\python.exe -m pytest tests -q`
- **Frontend production build passed.** `npm run build`
- **TypeScript check passed.** `npm run typecheck`
- **Browser: 4 scenarios passed against the production build.** `npm run test:e2e`, isolated dataset in `.data/e2e-production/`.

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

The seed CLI was run twice against an isolated dataset with 24 patients: both runs reported **2 hospitals, 24 patients, 25 visits, 26 versions**, with no duplicated rows. Reset then backed up all three SQLite files and rebuilt that isolated dataset with **12 patients, 13 visits, and 14 versions**. The ordinary demo database was not reset. A Windows file-lock issue found during this check was corrected by explicitly closing backup connections before replacing files.

The PowerShell seed wrapper and `run.ps1` were also executed successfully. The launcher started a healthy API and frontend using the clean ordinary dataset: **8 patients, 9 visits, 10 versions, no requests/transfers**. The proxied health route and homepage returned successfully. Screenshots of the hospital dashboard, patient OTP, translation inspector, and mobile dashboard are generated under `.data/screenshots/`; the desktop and mobile dashboards were visually inspected locally.

The transfer uses an on-disk central database with an attached on-disk hospital database and rollback journals, rather than WAL. This is the local configuration in which SQLite supports transactions across attached databases; see the [SQLite ATTACH documentation](https://www.sqlite.org/lang_attach.html). The failure-injection test covers the application's rollback behavior. It does not establish a distributed transaction guarantee for remote EHR systems or test power-loss recovery.

These checks validate a local prototype. They do not validate real Epic/Oracle compatibility, clinical correctness of user-supplied information, DICOM interpretation, malware protection, or production security/compliance. All medical input used in testing is fictional.
