# EHR Bridge

**Your EHR holds the data. EHR Bridge makes that data usable.**

A runnable, full-stack hackathon prototype using **fictional patient information**. EHR Bridge assists existing source systems with patient-controlled retrieval, clinical intake, documentation work, and traceable translation. It does not replace an EHR, connect to live hospitals, establish clinical truth, or write back to an external EHR.

The doctor experience has exactly four destinations: **Dashboard**, **Patients**, **Sessions & Tasks**, and **Exchange & History**. Independent patient and hospital administrator accounts receive their own interfaces and server-enforced permissions.

## Run on Windows

From PowerShell:

```powershell
cd C:\Users\DSU\Documents\PolyMed\PolyMed
.\scripts\dev.ps1
```

On a first installation, use `.\scripts\dev.ps1 -Install` instead. Prerequisites are Python 3.14 and Node.js 24+; an available workspace-local portable Node runtime is detected. Copy `.env.example` to `.env` when configuring providers or custom settings; keep credentials out of Git.

Open **http://127.0.0.1:3000**. Keep the terminal open; Ctrl+C stops the owned services. The launcher checks ports, applies migrations, seeds missing fixtures without resetting entered data, starts FastAPI, waits for health, and starts Next.js. Backend logs are captured in `.data/logs/backend.log` and `.data/logs/backend-error.log`. Stop an existing launcher before starting another on the same ports.

All new demo accounts use **`EHRBridge-demo-2026!`** by default:

| Account | Email | Interface and scope |
| --- | --- | --- |
| Dr. Emily Carter | `emily@ehrbridge.demo` | Memorial Hospital doctor; Epic-inspired mock source |
| Dr. Daniel Reed | `daniel@ehrbridge.demo` | Valley Medical doctor; Oracle Health-inspired mock source |
| Sarah Mitchell | `sarah@ehrbridge.demo` | Independent patient account; her own longitudinal information and access decisions |
| Memorial Administrator | `admin@ehrbridge.demo` | Memorial organization configuration, staff, and audit metadata; no clinical-record permission |

Set `EHR_BRIDGE_DEMO_PASSWORD` before initial seeding to choose another password. Seeding preserves existing password hashes. The login form also accepts individual staff accounts created by an administrator. Doctors with multiple explicit hospital memberships receive a workspace selector; switching validates membership and role on the server.

For the best demonstration, open the doctor in one browser profile and Sarah in another private/profile window. A second tab in the same browser shares its session cookie. Alternatively, save the session draft, sign out, use Sarah's account, then return as Dr. Carter and resume the saved session.

## The complete patient journey

1. Sign in as **Dr. Emily Carter**. Dashboard metrics and charts come from persisted session/task data. The work queue opens the selected session or patient.
2. Select **New Session**. In the seven-step modal, find **Sarah Mitchell / BR-SARAH**, enter a reason, and continue. Her local identity is `MH-SARAH`; Valley's independent source identity is `VM-SARAH`.
3. Select Valley Medical as the outside source. Choose the purpose, encounter reason, categories, and duration, then **Send patient access request**. Only permitted identity/source metadata is available; Valley's clinical values remain locked.
4. Sign in as **Sarah** and open **Access Requests**. Inspect the doctor, organization, department, reason, sources, categories, and duration. Investigate with a question, deny, or explicitly approve the scope.
5. Approval generates a **demonstration six-digit code**, valid for five minutes and one successful use. It is displayed to Sarah, not sent by SMS. Share it with Dr. Carter. A new code invalidates the old one.
6. In the doctor's saved intake, enter the code. Only the requested categories from the requested sources become available for that doctor and active hospital, for the approved duration. Incorrect codes, expiration, attempt limits, denial, and revocation are enforced server-side.
7. Review both Lisinopril reports: Memorial documents **10 mg once daily**, Valley documents **20 mg once daily**. The app flags the difference without selecting a correct dose. Open **Details & history** to compare Valley's earlier 10 mg source version with its later 20 mg version.
8. Valley's fictional laboratory blood group **A+** is retained with its provenance. Memorial's default mock destination mapping does not support blood group, so the inspector displays **Preserved — not mapped to destination**. It is retained in Bridge rather than discarded or silently imported.
9. Continue intake. Record, pause/resume, stop, play back, or cancel a browser voice memo after confirming consent. Without speech credentials, use **Load sample transcript**, which is explicitly labeled fictional and not transcribed audio, or type the actual source transcript.
10. Extract draft suggestions, edit them, and accept/reject each. These local rules quote recognized source text; accepted fields remain **doctor-reviewed patient reports**, not verified medications, diagnoses, or hospital facts.
11. Add text, yes/no, multiple-choice, or numeric questions. Review the intake, currently authorized records, discrepancies, missing information, and source labels.
12. Use the insurance assistant's fictional plan and **Run mock eligibility check**. Results are labeled simulated, unverified, and not guaranteed payment. Save Draft or Start Session.
13. Open **Sessions & Tasks**, resume the intake, add follow-up/missing-information tasks, and update task statuses. A pending patient-approval task cannot be completed before an activated or definitive patient decision. Review remaining work, then complete the session. Dashboard totals update.
14. Sarah can **Revoke future access**. New external record/history/translation reads are denied immediately by the backend. Original source data and already-recorded clinical/intake history are preserved.

See [docs/BRIDGE_ARCHITECTURE.md](docs/BRIDGE_ARCHITECTURE.md) for boundaries, models, and endpoints, and [docs/BRIDGE_VALIDATION.md](docs/BRIDGE_VALIDATION.md) for actual checks and limits.

## Patient and administrator workspaces

The patient portal is mobile-first. Sarah sees her own records from both source hospitals, exact access requests, temporary codes, expiration indicators, revocation controls, and access history with clinician identity, categories, and timestamps. Inconsistent reports remain separate source entries.

The hospital administrator can update the organization's mock connection state, department, and supported destination categories; create staff accounts; edit active memberships and roles; inspect mapping-attention metadata; and review organization audit entries. Enabling a mock category changes preview capability without changing the original source or granting any new patient scope. Administrator access does not authorize patient chart, session intake, or translation-content reads.

## Persistence and preserved earlier work

The retained architecture uses Next.js, TypeScript, Tailwind, Radix/shadcn-style primitives, Lucide, Recharts, and Framer Motion in the client; FastAPI, SQLAlchemy, and Alembic on the server. The established transactional outbox, canonical FHIR R4 subset, source versions, mapping warnings, and provenance engine remain in use. SQLAlchemy persistence was retained rather than introducing a second ORM beside it.

Local stores are independent SQLite files by default:

- `.data/clinicalsync_shared.db`: identities, accounts, grants, workflows, canonical copies, immutable versions and audit metadata.
- `.data/ehrbridge_memorial.db` and `.data/ehrbridge_valley.db`: independent fictional source charts and transactional outboxes.
- `.data/clinicalsync_northstar.db` and `.data/clinicalsync_riverside.db`: preserved earlier ClinicalSync source data.

Migration **0003** adds the Bridge workflow tables using a frozen schema snapshot. It does not delete or rewrite earlier clinical history. Consistent SQLite backups were taken under `.data/backups/ehrbridge-*/` before implementation. Original ClinicalSync functionality remains at **http://127.0.0.1:3000/legacy** with its earlier accounts/passwords; see [docs/CLINICALSYNC_LEGACY.md](docs/CLINICALSYNC_LEGACY.md). Legacy APIs and identity tools cannot bypass Bridge account scope or reassign Bridge identities. Normal startup never resets the user's databases.

Session intake edits append revision snapshots. Preserved supplemental records retain their normalized representation, original mock payload, author, verification class, source time, and immutable version. Review comments, exchanges, insurance examples, and voice snapshots are attributable persisted evidence.

## Optional real transcription

The default Bridge voice workflow requires no keys. To enable the implemented server-side transcription adapter, set in `.env`:

```dotenv
TRANSCRIPTION_PROVIDER=openai
AI_EXTERNAL_ENABLED=true
AI_API_KEY=your_server_side_key
AI_BASE_URL=https://api.openai.com/v1
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
```

Restart the launcher. The browser separately requires authorization before sending recorded audio to the external provider. The API checks clinician role, patient care relationship, CSRF, workspace, recording consent, external-processing authorization, upload size, MIME type, credentials, and HTTPS provider configuration. Keys are not sent to the browser. Audio is never persisted on this server.

**Live provider calls were not verified because credentials were unavailable.** Audio request construction and provider handling are tested with mocked transports. Bridge suggestion extraction is explicitly a local rule-based demo and never presented as AI or verified clinical reasoning. The earlier SOAP-note generation adapter remains available in the legacy clinical note workflow; [docs/PROVIDERS.md](docs/PROVIDERS.md) describes that separate integration.

Bridge consultation transcripts saved in session intake, immutable encounter versions, and voice snapshots are retained as demonstration documentation. They are separate from the legacy private note-draft raw-transcript field, whose configured expiry is described in the provider guide. There is no complete production retention or consent governance implementation; never enter real consultations.

## Docker, manual startup, and tests

With Docker Desktop and Compose available:

```sh
cp .env.example .env
docker compose up --build -d
```

Compose defines five independent PostgreSQL stores (shared plus four retained/new source stores), FastAPI, and Next.js. Open http://localhost:3000. Database ports are not exposed and volumes persist. **Docker/PostgreSQL runtime execution is unverified on this machine; Docker is unavailable.** No Prisma service is required. PostgreSQL DDL and Compose structure receive static validation.

For manual startup, install dependencies, run `python -m backend.app.cli migrate`, `python -m backend.app.cli seed`, then `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`. In `frontend`, run `npm ci` and `npm run dev`. Direct Python commands read process environment; the PowerShell launcher loads `.env`. OpenAPI is at http://127.0.0.1:8000/docs.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```sh
cd frontend
npm run typecheck
npm run build
npm run test:e2e
```

Browser tests need a running app with **dedicated test databases**. Before starting the API for E2E, set `SHARED_DATABASE_URL=sqlite:///.data/bridge-e2e/clinicalsync_shared.db` and the analogous `HOSPITAL_A_DATABASE_URL` and `HOSPITAL_B_DATABASE_URL` paths in that directory; Memorial/Valley derive independent sibling files. Tests use fictional state and do not reset normal databases. Windows uses installed Edge and a browser-generated fake microphone device. Other platforms need a Playwright Chromium installation. The preserved legacy browser suite is opt-in with `E2E_LEGACY=true` against a separately configured `BRIDGE_ENABLED=false` API.

## Production limitations

This is a **demo security simulation using fictional information**. Real Epic/Oracle SMART on FHIR connectivity, payer eligibility, SMS delivery, MFA/enterprise identity, emergency access, clinical validation, full FHIR conformance, encryption/key-management operations, distributed transactions, database-enforced immutability, durable background workers, and compliance certification are not implemented. Default HTTP, demo passwords, local SQLite, and application-level guards are not production controls.

Patient OTP approvals add an access-control workflow; they do not replace medical disclosure rules, legal consent requirements, or emergency policies. Revocation blocks future external reads, not the historical fact that a clinician already reviewed information. Before using real data, independently establish legal/governance requirements, vendor agreements, secure infrastructure, retention and backup policies, security testing, accessibility review, and clinical usability validation.
