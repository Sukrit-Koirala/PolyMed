# Clinical workflow walkthrough

Start the app, open http://127.0.0.1:3000, and sign in as **network@clinicalsync.demo**, password **ClinicalSync-demo-2026!**. Dr. Avery Chen has explicit clinician memberships at both Northstar and Riverside. The top hospital selector changes the active server-authorized workspace; the application and primary navigation stay the same.

## 1. Find and understand a patient

Open **Patients**. **Hospital patients** includes only the current hospital’s authorized care relationships; **Shared patients** includes patients linked across more than one hospital. Search Maya Bennett or the local identifier. At Northstar, Maya’s local ID is `NS-1001`; at Riverside it is `RG-8824`. Both confirmed source identities contribute to the shared patient layer while retaining their originals.

Open Maya. The chart header identifies the patient, date of birth, current hospital identifier, connected hospitals, and latest source update. **Clinical overview** summarizes medications, allergies, diagnoses, labs, vaccinations, and approved notes. It flags the 500 mg versus 1000 mg metformin difference and the potentially duplicate influenza vaccination reports without selecting a correct source or deleting either entry.

Expand **View details**, then **Source & history**. The initial view uses clinical labels, source author/dates, and change history. Original payloads, normalized resources, reverse previews, mapping reports, and version snapshots remain under collapsed **Technical details**.

## 2. Switch workspaces safely

Choose Riverside in the top selector. The chart closes and Riverside’s Overview loads. Its directory and incoming review queue are hospital-specific. Open Maya again to inspect Riverside’s local identifier and its external Northstar information.

Sign in as **northstar@clinicalsync.demo** to demonstrate a single-hospital account: it cannot select or access Riverside. Backend tests also attempt unauthorized switches and stale workspace writes; frontend filtering is not the authorization boundary.

## 3. Register a new patient

At Northstar choose **Patients → Add patient**. Enter fictional demographics, optionally provide a hospital identifier, and confirm synthetic data. **Check for matches** displays permitted similarities. A same name or date of birth is not an identity confirmation. Open an existing local chart or explicitly **Create separate patient**.

The new chart opens with its own local identifier and independent registration timeline. Add a synthetic medication or diagnosis. The source transaction saves the entry, historical version, and outbox event; the UI then requests synchronization. This does not connect an unrelated hospital record. Switch to Riverside and verify that its directory does not gain this patient automatically.

## 4. Vaccinations

Open Maya → **Vaccinations**. The seeded source reports show an administered influenza vaccination and a historical report of what may be the same event. Both source histories remain.

Choose **Add vaccination**. Record an administered or historical entry with date and optional dose, lot, site, route, and provider. Alternatively choose **Planned — not administered** and a future date. The chart and receiving update must show that this is a plan; the backend represents it as `ImmunizationRecommendation`, not a completed administration. A **Not administered** entry can record the documented reason. Correcting or withdrawing an owned entry appends history.

## 5. Review a meaningful clinical change

At Northstar open Maya → Clinical overview → expand the Northstar metformin entry → **Edit** or **Correct**. Change its dose and save. This publishes a new source version through the outbox.

Switch to Riverside → **Clinical Review**. Search Maya or Metformin. The left panel identifies the patient, source, update description, reception time, and status. The right panel shows what changed, previous/updated information, source dates, why review is needed, and available decisions. Changed values are highlighted; unchanged values are neutral.

Add a note and **Acknowledge**, **Defer**, **Investigate**, or **Reject import**. Choose the corresponding status filter and refresh to verify persisted reviewer identity, time, and note. Original Northstar information remains. Acknowledging does not import the record or change Riverside’s dose.

Patient **Timeline** includes this hospital’s review decision separately from the source’s clinical occurrence/update/reception dates. The chart’s **Review difference** action can document a local resolved/investigating status while leaving both claims intact. A changed discrepancy can require a fresh review.

## 6. Capture, edit, and approve a note

Open a patient → **Notes → New note**. Confirm applicable recording authorization and consent, then **Start recording**. Allow microphone access. A live indicator and elapsed time show actual capture. **Stop recording** produces playable audio; **Cancel recording** discards capture and stops microphone tracks.

Without external credentials, **Manual transcript mode** explicitly asks for an entered or uploaded synthetic test transcript. Use the actual source text with optional Subjective/Objective/Assessment/Plan headings. **Organize draft** preserves supplied content and leaves missing sections blank; it is not represented as AI transcription.

Review and edit the SOAP sections. **Save draft**, refresh, and reopen it under private drafts. It is not in the approved chart, shared records, or clinical timeline. Choose **Approve note**, verify the patient/hospital context, explicitly confirm review, and **Approve and save note**. The approved document appears in that patient’s chart and timeline and is eligible for authorized cross-hospital review. Medication/allergy/diagnosis lists remain unchanged.

Switch hospitals and locate the approved note in Clinical Review. Acknowledge it; its source remains the original hospital and no receiving local note is silently imported. Actual external speech-to-text/AI requires the configuration and verification described in [PROVIDERS.md](PROVIDERS.md).

## Administrator and reliability checks

Sign in as **admin@clinicalsync.demo**. **Workspace tools** contains synchronization status, audit activity, identity review, and development controls without adding global clinical navigation sections.

**Identity review:** inspect the pending Elise Carter / Elise C. Carter match. Its local source condition remains outside the shared layer until explicit approval. A review note and Confirm or Reject action are required. New unpublished local identities can also request a separate link review from their chart. Already-published independent histories are refused pending a future reconciliation workflow rather than silently reassigned.

**Replay:** Development controls → Simulate new update creates an attributable allergy correction. Replay event resends the same outbox identity: expect **0 published, 1 suppressed**, with no extra clinical event or receiving review item. Repeated synchronization does not create circular imports.

**Reset:** Development controls → Reset demo requires administrator authorization, demo mode, exact local/Compose database names/hosts, synthetic-only rows, and `RESET SYNTHETIC DEMO`. It signs everyone out and recreates only the named fixture stores. Reset is disabled if additional hospitals are configured. Do not reset a demo session whose entered data you want to preserve.

On a fresh reset, Maya has **10 published source records/events/versions/provenance entries**: 6 Northstar records and 4 Riverside records. Northstar has 4 incoming reviews and Riverside has 6. One medication-dose difference and one possible vaccination duplicate are seeded. Each hospital also has a separate local-only/identity-pending patient. An intentionally held Riverside identity contributes no shared clinical content before confirmation.
