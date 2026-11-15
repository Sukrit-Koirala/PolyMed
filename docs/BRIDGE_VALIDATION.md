# EHR Bridge validation

Validation was performed November 15, 2026 (America/Chicago), using Python 3.14.7, Node.js 26.13.1, Next.js 16.4.6, FastAPI 0.163.0, SQLAlchemy 2.1.8, and Edge through Playwright. It uses fictional data, isolated test stores, and a browser-generated fake microphone device. No real consultation, vendor account, payer request, or clinical information was sent to an external service.

## Backend

Run `.\.venv\Scripts\python.exe -m pytest -q` from the repository root. The suite retains the original engine/security/migration checks and adds the Bridge workflow checks. New organizations also participate in the adapter round-trip matrix.

The final run passed **217 tests in 112.87 seconds**. One upstream Starlette warning reports deprecated httpx TestClient transport usage; it did not affect the results.

Bridge coverage includes local-only visibility before approval; category-specific grants on every clinical/history/translation read; patient identity isolation; administrator clinical denial; legacy route and identity-tool bypass prevention; correct doctor/hospital/request binding; hashed codes; five attempts; expiration; single-use/replay rejection; investigation/denial; revocation and expiry; unchanged receiving sources; separate medication versions; preserved unmapped laboratory blood group; later mock capability support without source changes or scope broadening; session/intake/task persistence and optimistic revisions; draft suggestion provenance; custom answer validation; immutable snapshots; mock benefits; review comments; staff deactivation; and organization-scoped connection configuration.

Existing tests cover original payload preservation, mapping warnings, canonical/reverse translation, source corrections/withdrawals, immutable histories, outbox/replay/idempotency, synchronization failures, care/identity/CSRF/session boundaries, and populated Alembic upgrades.

## Browser application

Run `npm run typecheck`, `npm run build`, and `npm run test:e2e` in `frontend`. Use a running API with dedicated `.data/bridge-e2e` URLs, never normal demo databases. The Bridge browser suite does not reset the user's saved data. Legacy browser tests are separately opt-in against a `BRIDGE_ENABLED=false` server.

TypeScript checking and the optimized production build passed. The final browser run against the standalone production frontend and real FastAPI backend passed **8 scenarios in 33.9 seconds**, including:

1. The complete two-account Sarah/Dr. Carter journey: exactly four doctor navigation links, persisted dashboard data, source lock, purpose/scope request, explicit patient approval and countdown, rejection of an invalid code before successful activation, distinct medication reports, real browser voice recording/pause/resume/playback, labeled sample transcript, reviewed suggestions, questions, mock insurance, follow-up task creation, session completion, version comparison, review comments, preservation inspector, and revocation.
2. Patient registration with explicit duplicate review, independent identity, unknown verification status, four typed question responses, saved draft, and persistence after reload.
3. Patient investigation/question and denial with no release of outside records.
4. Administrator configuration/staff persistence and denial of clinical access.
5. Narrow-screen personal records, settled mobile navigation, no page-level horizontal overflow, and another-patient access denial.
6. Delayed microphone permission after cancellation, followed by another capture: stale stream cleanup, live new stream, cancelled audio discarded, and tracks ended.
7. Recoverable proxy 502 handling.
8. Recoverable disconnected/connection-reset handling.

Desktop dashboard, patient approval, translation/version history, and mobile personal-record screenshots are generated in ignored `.test-artifacts` and visually inspected. Recharts shows actual saved activity; it does not show invented live vendor statistics. UI/chart animations do not substitute for record or permission logic.

## Persistence, startup, and external limits

Before implementation, SQLite's backup API copied existing normal stores into `.data/backups/ehrbridge-*/`. Migration `0003` creates additive shared workflow tables and uses the existing source schema in the two new independent stores. Normal launchers never reset prior clinical data.

PostgreSQL DDL compiled for all **44 tables** and their indexes. Compose YAML parsed with **7 services** and **5 independent database volumes**. The Windows launcher parsed without errors. These static checks are distinct from actually running containers.

The Windows launcher successfully applied migration `0003` to all five normal stores and started the app. SHA-256 comparisons confirmed that **all 698 pre-upgrade rows across 35 existing tables** retained identical contents; no reset was performed. Root, `/legacy`, proxied health, and OpenAPI returned 200. All four new accounts authenticated and opened their correct portals. Dr. Carter's outside source values remained locked before approval, and the administrator's clinical read was denied.

**Docker/PostgreSQL runtime execution is unverified because Docker is unavailable.** The Linux launcher is not executed on this Windows machine. External transcription/AI request adapters are implemented and mock-tested, but **live provider calls are unverified because credentials are unavailable**. The default browser voice/sample-transcript/rule-extraction workflow is tested without pretending a real transcription occurred.

This is functional fictional-MVP validation, not clinical validation, penetration testing, accessibility certification, full FHIR conformance, production encryption validation, or a compliance assessment. See the root README and architecture guide for deliberate production limitations.
