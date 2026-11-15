# ClinicalSync

**Synthetic demonstration data — Not for clinical use.**

ClinicalSync is one clinical application with independent hospital workspaces, authorized shared patient information, and traceable review decisions. Its Next.js frontend and FastAPI backend preserve each hospital’s source records in separate databases. Synthetic Epic-inspired and Oracle Health-inspired adapters translate through a documented FHIR R4 subset; no live EHR connection is claimed.

The clinical interface has three primary sections: **Overview**, **Patients**, and **Clinical Review**. Patient charts contain the clinical overview, shared records, timeline, vaccinations, and notes. Source formats, mapping reports, provenance, and operational controls remain available through expanded details and Workspace tools.

Acknowledgment records a hospital’s review. It never imports or overwrites a receiving chart. An explicitly approved note is saved to the originating development hospital’s chart and becomes eligible for sharing; it does not change medications, diagnoses, allergies, or any external EHR.

## Start on Windows

Prerequisites: Python 3.14 and Node.js 24+. A workspace-local portable Node runtime is detected automatically when present.

```powershell
Copy-Item .env.example .env
.\scripts\dev.ps1 -Install
```

Subsequent starts:

```powershell
.\scripts\dev.ps1
```

Open **http://127.0.0.1:3000**. Keep the launcher terminal open. It applies migrations, seeds missing fixtures without resetting existing records, starts the backend, waits for health, and starts Next.js. Backend logs are in `.data/logs/backend.log` and `.data/logs/backend-error.log`. If a port is already occupied, stop the old launcher in its terminal first. A proxy `ECONNRESET` means the frontend lost the API connection; inspect the backend log and restart both services through the launcher.

The three normal local stores are `.data/clinicalsync_shared.db`, `.data/clinicalsync_northstar.db`, and `.data/clinicalsync_riverside.db`. Existing local data was backed up under `.data/backups/` before this schema upgrade. These data directories, credentials, recordings, and transcripts are not tracked in Git.

## Docker or manual startup

With Docker Desktop/Compose installed:

```sh
cp .env.example .env
docker compose up --build -d
```

Open **http://localhost:3000**. Compose provides three PostgreSQL containers with independent database users and volumes, plus the API and frontend. Application ports bind to loopback; database ports are not exposed. `docker compose down` preserves volumes. Docker is unavailable in the implementation environment, so actual Compose/PostgreSQL execution remains unverified. Local runtime verification uses three persistent SQLite stores and the same SQLAlchemy services.

On macOS/Linux use `sh scripts/dev.sh`, or activate a virtual environment and run from the root:

```sh
pip install -r backend/requirements.txt
python -m backend.app.cli migrate
python -m backend.app.cli seed
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

The launchers load `.env`; direct Python commands use process environment variables. OpenAPI documentation is at **http://127.0.0.1:8000/docs**. `make dev`, `make seed`, `make test`, `make reset-demo`, and `make stop` wrap Compose operations when Make is available.

## Accounts and hospital switching

Default password for all seeded accounts: **`ClinicalSync-demo-2026!`**. Set `DEMO_PASSWORD` before initial seeding to change it. Existing password hashes are preserved until an intentional reset.

| Account | Email | Memberships |
| --- | --- | --- |
| Dr. Avery Chen | `network@clinicalsync.demo` | Clinician at Northstar and Riverside; recommended for the full workflow |
| Dr. Elena Park | `northstar@clinicalsync.demo` | Northstar clinician only |
| Dr. Daniel Reed | `riverside@clinicalsync.demo` | Riverside clinician only |
| Alex Morgan | `admin@clinicalsync.demo` | Administrator at both; identity, audit, and development tools |

Choose the active hospital in the top navigation. Memberships and hospital roles are checked on the server; changing the workspace does not change the user’s primary account or grant new permissions. The chart closes when switching to prevent patient-context mix-ups. Multi-hospital mutation requests require an explicit `X-Workspace-ID` matching the active session. Stale browser tabs receive 409 rather than accidentally writing into another workspace.

Administrators do not approve clinical notes or record clinical acknowledgments unless they have an explicit clinician role in that workspace. Sign out through the sidebar icon to change accounts.

## Clinical workflows

**Find a patient.** Open Patients, choose Hospital patients or Shared patients, and search by name or local identifier. Shared patients have confirmed records connected to multiple hospitals; a local-only identity is not mislabeled shared.

**Register a patient.** Choose Add patient, enter minimal demographics and an optional hospital identifier, confirm fictional development data, and check for matches. Review similarities, open an existing local chart, or explicitly create a separate patient. Cross-workspace suggestions require both user membership and a care relationship in the other hospital. Registration never automatically links names or birth dates. Administrators can request and separately confirm links through chart identity controls and Workspace tools.

**Review a chart.** A patient’s Clinical overview contains concise medications, allergies, diagnoses, labs, vaccinations, and approved notes. Expand View details for clinical context; Source & history opens original attribution and immutable versions. Technical JSON stays collapsed. Timeline is loaded from that specific local patient and authorized hospital context, including registration, source events, approved notes, external updates, and review decisions.

**Create or correct an entry.** Use Add within a chart category, or expand an owned record and choose Edit, Correct, or Withdraw. A local transaction appends a version and outbox event. The UI then requests synchronization. A sharing failure is reported separately from a successful local save. Another hospital’s source record is never edited by this action.

**Review an update.** Open Clinical Review or an Overview incoming update. Search/filter, inspect source and reception times, compare changed values, and Acknowledge, Defer, Investigate, or Reject import. Review history persists per hospital. Earlier source versions stay in All updates & history. Different-dose and possible-duplicate reviews can also be documented in the patient chart; resolving a review leaves both source records unchanged and does not choose a clinically correct dose.

**Vaccinations.** Record administration date, dose information, source, provider, route/site, lot, status, and notes when available. Historical reports are distinct from administrations documented by the source. Not-administered entries are explicit. Planned vaccinations use `ImmunizationRecommendation`, not completed `Immunization` records. Possible duplicate source reports retain both histories.

The full walkthrough is in [docs/DEMO.md](docs/DEMO.md).

## Voice notes and documentation providers

The default workflow works without credentials:

1. Open a patient chart → Notes → New note.
2. Confirm the applicable recording authorization/consent and Start recording, then Stop or Cancel. Microphone access requires localhost or HTTPS and browser permission.
3. When transcription is not configured, enter or upload an actual synthetic test transcript. The app never substitutes made-up text for recorded audio.
4. Choose **Organize draft**. The clearly labeled local organizer preserves supplied SOAP headings and leaves undocumented sections blank. Unclassified text remains explicitly unclassified; this fallback is not presented as AI or speech recognition.
5. Edit every section and Save draft. Drafts are private to their author in that hospital and do not enter the shared record or clinical timeline.
6. Choose Approve note, review the patient/hospital context, and explicitly confirm approval. The server saves an attributable approved document, a local event, and an outbox snapshot. The UI requests publication to authorized connected hospitals. Approval is not a cryptographic or production EHR signature.

To enable the implemented OpenAI provider adapters, configure server-side `.env` values:

```dotenv
TRANSCRIPTION_PROVIDER=openai
NOTE_GENERATION_PROVIDER=openai
AI_EXTERNAL_ENABLED=true
AI_API_KEY=your_server_side_key
AI_BASE_URL=https://api.openai.com/v1
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
NOTE_MODEL=gpt-4.1-mini
TRANSCRIPT_RETENTION_DAYS=7
```

Restart the launcher or recreate the backend container. The UI additionally requires explicit authorization before sending audio/transcripts to the configured external provider. API keys never go to the browser. Provider URLs must use HTTPS. Transcription sends the recorded audio; note generation sends only the supplied transcript, not the patient’s entire chart. The note adapter requests extractive SOAP sections and rejects generated excerpts that cannot be found in the source transcript. Clinician approval is mandatory regardless of provider.

OpenAI request construction, response handling, unavailable-provider behavior, and grounding rejection were verified with mocked HTTP transports. **Live external transcription and AI requests were not verified because credentials were unavailable.** Browser recording, manual transcript fallback, draft generation/editing/persistence, approval, and sharing were exercised end to end. See [docs/PROVIDERS.md](docs/PROVIDERS.md) for details.

Audio is held in browser memory and request memory; it is never persisted by this server. Source transcripts are purged after their configured retention period on access, startup, and a 60-second retention sweep. Set `TRANSCRIPT_RETENTION_DAYS=0` to avoid persisting the separate raw-transcript field. Edited drafts and approved notes can retain clinically relevant excerpts; raw-transcript expiry does not erase note content or immutable clinical history. These retention settings are development controls, not a complete production retention/compliance policy.

## Structure and APIs

```text
backend/app/
  main.py, security.py       Authentication, workspace context, existing REST APIs
  workspace.py              Registration, directories, patient charts, timelines, identity requests
  note_routes.py            Draft persistence, generation, approval, audio requests
  documentation.py          Provider interfaces, OpenAI adapters, local organizer
  adapters.py, services.py   Canonical translation, versioning, conflicts, outbox publication
  models.py, retention.py    Relational entities and source-transcript retention
backend/migrations/         Frozen initial schema and additive workspace migration 0002
backend/tests/              Translation, integration, security, migration, and provider tests
frontend/src/
  app/                      One Next.js application and responsive styles
  components/               Overview, directory, patient chart, notes, review, expanded details
  lib/api.ts                Session-bound API client with workspace context
frontend/tests/             Real browser workflows and transport error regressions
scripts/                    Local launchers
docs/                       Architecture, canonical subset, provider setup, demo, validation
```

New API families include `POST /api/auth/workspace`, `GET /api/directory`, `GET /api/overview`, patient match checks and registration under `/api/local/patients`, patient-scoped `/api/charts/{local_id}` and `/timeline`, `/api/notes/config`, local note drafts and `/api/note-drafts/{id}` save/generate/approve, patient-scoped raw audio `/transcriptions`, hospital-specific `/api/conflicts/{id}/reviews`, and administrator identity target/link requests. Existing source, history, compare, shared-patient, review, synchronization, and audit APIs remain available. Full schemas are in OpenAPI.

Migration `0002` adds hospital memberships and active session workspace, patient registration fields, private note drafts, local timeline events, identity-link targets, and hospital-specific discrepancy reviews/decision history. It backfills existing primary memberships without changing passwords or source histories. Additional hospital configuration and the schema relationships are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```sh
cd frontend
npm run typecheck
npm run build
npm run test:e2e
```

Backend tests use isolated databases under `.data/pytest`. Browser tests require a running API and frontend and **reset their configured synthetic demo**. Use dedicated URLs such as `sqlite:///.data/e2e-v2/clinicalsync_shared.db`, `clinicalsync_northstar.db`, and `clinicalsync_riverside.db` before starting the API. Do not point the browser suite at a demo session you want to preserve. Windows tests use installed Edge; other platforms need `npx playwright install chromium`. The microphone tests use a browser-generated fake audio device, not a real consultation or fabricated transcript.

See [docs/VALIDATION.md](docs/VALIDATION.md) for actual final test counts, commands, and verification limits.

## Limits and next steps

This is a functional product foundation using synthetic fixtures and development adapters. It has no real hospital credentials, live EHR connectivity, production chart import, autonomous diagnosis/prescribing, full FHIR validation, or medical/compliance certification. Identity links involving already-published independent global histories require a future reconciliation workflow; the MVP refuses to silently move that history. Incoming queues are explicit REST views with development synchronization, not a production event bus.

Server-side membership, care relationships, confirmed identities, CSRF/origin checks, password hashing, session cookies, optimistic concurrency, and access/modification auditing protect the demonstrated workflow. Default passwords, local HTTP, in-process job scheduling, application-level immutable-model guards, and demonstration authentication are not sufficient for real patient care. Never enter real patient information.

Before real-world deployment, complete HIPAA assessment and BAAs where applicable, access/consent governance, patient matching validation, state-law and 42 CFR Part 2 review where applicable, secure vendor integration, operational auditing, retention/backup governance, security testing, and independent clinical validation. Next engineering work should prioritize PostgreSQL/Compose CI, durable worker leases, database-enforced history protections, identity reconciliation, enterprise identity, production secrets/rate limiting, and accessibility/clinical usability assessment.
