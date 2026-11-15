# Try the official Oracle sandbox sample

These resources were fetched with successful HTTP GETs from Oracle Health's **public FHIR R4 sandbox**. They are test records, not real patient information. See [Oracle's sandbox documentation](https://docs.oracle.com/en/industries/health/millennium-platform-apis/mfrap/srv_root_url.html).

The included sample is **TIM PETERS**, DOB **1990-09-15**, with a **Potassium Level of 4.4 mmol/L** (LOINC **2823-3**). The source observation's effective time is in September 2026; it is retained rather than replaced with the upload time. `PATIENT.txt` records the exact identity for the downloaded snapshot.

## Try it in the app

1. Open http://127.0.0.1:3200 and sign in as **Daniel at Valley** (`daniel@bridge.demo`, password `Demo-access-2026!`).
2. Select **Register patient**. Enter name **TIM PETERS**, DOB **1990-09-15**, and check the fictional-data confirmation. Other contact fields can be left blank. Keep the returned patient ID and activation code.
3. Open that new patient, choose **Upload visit → FHIR R4**, and select **`upload-bundle.fhir.json`** using the file input. Review the displayed source/destination identities, check the mapping confirmation, and upload.
4. Open **Versions & source → Source & translation**. The original FHIR resources and the normalized observation are visible. No PDF is necessary.
5. In a separate browser profile, activate the new patient account with the issued ID/code and a password. As **Emily at Memorial**, find that ID and request Valley's records. Generate the OTP as the new patient, then redeem it as Emily.
6. Open the imported copy's **Source & translation**. Compare the original FHIR `valueQuantity` and `code` with the general model and Memorial's stored mock format. The value/unit stay **4.4 mmol/L**; LOINC and source references remain in the preserved metadata. The copied record has Memorial's local patient identifier.

Do not import this record into Sarah's profile. The server checks name/DOB, requires explicit mapping confirmation, and binds the full external patient URL to one internal patient ID. This is a manual demo association, not a production identity-verification service.

## Files and provenance

- `patient.fhir.json` and `observation.fhir.json`: unchanged response bytes from the sandbox.
- `upload-bundle.fhir.json`: a local FHIR `collection` Bundle containing those two resources, with their full source URLs. The resources are unchanged; Oracle did not return this assembled Bundle as a single response.
- `fetch-receipt.json`: source URLs, fetch timestamp, HTTP statuses, and SHA-256 hashes of response bytes. This records the fetch; it is not a signed attestation.
- `PATIENT.txt`: registration identity and quick instructions.

To fetch a fresh snapshot, from the workspace root:

```powershell
.\.venv\Scripts\python.exe ehr-bridge/scripts/fetch-oracle-sandbox.py
```

This refreshes the fixture files only. It uses GET requests to the fixed public sandbox and never writes to Oracle or imports anything into the local app automatically. Sandbox records may change; read the new `PATIENT.txt` after refreshing. The downloader fails rather than substituting invented data if the service is unavailable.

## Supported scope

The importer supports a FHIR R4 collection containing exactly one Patient and one final/amended/corrected Observation with a numeric quantity, unit, and complete effective date. Unsupported resources, grouped/component observations, mismatched subjects, or conflicting values are rejected. Codes, units, qualifiers, source references, and the complete original Bundle are retained; units are not guessed or converted. It does not derive diagnoses or treatment suggestions.

This demonstrates **official FHIR input → custom general model → local mock hospital output**. Only the supported mapping is checked; full FHIR profile/invariant validation is not implemented. The destination remains the existing Epic/Oracle-inspired local store. It does not demonstrate authenticated writes to an actual hospital EHR.
