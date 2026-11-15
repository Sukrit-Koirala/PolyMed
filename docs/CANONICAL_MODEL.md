# Supported canonical clinical subset

## Extended categories

The original four clinical categories remain supported. Migration/workspace version 2 adds vaccinations and approved clinical documents while preserving original source payloads and structured mapping warnings.

**Vaccinations:** completed/historical/not-administered source entries use FHIR R4 `Immunization`: `vaccineCode`, `patient`, `status`, `occurrenceDateTime`, `recorded`, `primarySource`, optional `doseQuantity`, `protocolApplied.doseNumberPositiveInt`, `site`, `route`, `lotNumber`, `performer.actor.display`, `statusReason`, and `note`. Historical reports set `primarySource=false`; a missing local entry is not an explicit negative assertion. Only completed administrations with matching vaccine/date/dose context are candidates for equivalent/duplicate grouping, and all source provenance remains.

**Plans:** a planned vaccination uses `ImmunizationRecommendation` with `patient`, `date`, vaccine concept, planned-date criterion, dose number when supplied, and an explicitly synthetic forecast concept. It has no completed-administration status or occurrence assertion. Supported planned source attributes without standard recommendation fields are preserved in a documented extension `planned-vaccination-source-details` with `valueString` serialization and in the lossless original payload. Recommendation notes use `recommendation.description`.

**Approved notes:** FHIR R4 `DocumentReference` represents the final document with `subject`, `type`, `status`, `docStatus=final`, `date`, `author`, and `context.period`. Its `content.attachment` has `contentType=application/json`, title, and base64-encoded JSON containing the four SOAP section strings. An additional source comment uses `description`. This is a bounded clinical-document subset, not a complete FHIR document bundle or production signing implementation. Unapproved drafts never enter this canonical resource store.

The Epic-inspired note source format uses `clinicalNote` for the structured document and `note` for its separate source comment; Oracle-inspired notes use `entry.details.soapDocument`, `signedBy`, and `signedAt`. Vaccination field names also intentionally differ between the synthetic formats. Cross-adapter tests exercise all note fields and administered, historical, not-administered, and planned vaccination semantics in both directions. Preview serialization never writes a receiving chart.

Vaccination/note fixtures use clearly identified local demonstration codes such as `INFLUENZA_DEMO` and `SOAP_NOTE`, not invented official CVX or LOINC codes. Unknown source coding and UCUM mappings remain flagged. See the official R4 definitions for [Immunization](https://hl7.org/fhir/R4/immunization.html), [ImmunizationRecommendation](https://hl7.org/fhir/R4/immunizationrecommendation.html), and [DocumentReference](https://hl7.org/fhir/R4/documentreference.html).

ClinicalSync uses FHIR R4-shaped resources for a controlled synthetic demonstration. It is not a full FHIR server and does not claim conformance to an implementation guide. The translation envelope separates a normalized `resource`, a lossless `original_payload`, structured `warnings`, and the transformation version. The original vendor-inspired payload is also saved in every immutable canonical version.

The [HL7 R4 MedicationStatement specification](https://hl7.org/fhir/R4/medicationstatement.html) describes a report of medication use. ClinicalSync models documented medication-list information as `MedicationStatement`; it creates no prescription or medication order. See also the R4 definitions for [AllergyIntolerance](https://hl7.org/fhir/R4/allergyintolerance.html), [Condition](https://hl7.org/fhir/R4/condition.html), [Observation](https://hl7.org/fhir/R4/observation.html), [Patient](https://hl7.org/fhir/R4/patient.html), and [Provenance](https://hl7.org/fhir/R4/provenance.html).

## Fields

| Resource | Supported R4 fields |
| --- | --- |
| Patient | `id`, `active`, `name.text`, `birthDate`, source `identifier[]` |
| MedicationStatement | `identifier`, `subject`, `status`, `medicationCodeableConcept`, `effectivePeriod.start/end`, `dateAsserted`, `dosage.text`, `dosage.timing.repeat`, `dosage.doseAndRate.doseQuantity`, `note` |
| AllergyIntolerance | `identifier`, `patient`, `code`, `clinicalStatus`, `verificationStatus`, `recordedDate`, `onsetDateTime`, `criticality`, `reaction.manifestation.text`, `reaction.severity`, `note` |
| Condition | `identifier`, `subject`, `code`, `clinicalStatus`, `verificationStatus`, `onsetDateTime`, optional `abatementDateTime`, `recordedDate`, `note` |
| Observation | `identifier`, `subject`, `code`, `status`, `effectiveDateTime`, `issued`, `valueQuantity`, `note` |
| Provenance | Version-specific `target.reference`, `recorded`, `occurredDateTime`, source-author and organization `agent`, original-source `entity`, event-kind `activity.text` |
| Clinical resource metadata | `meta.versionId`, `meta.lastUpdated`, `meta.source` |

Source authors, local patient IDs, source-record identity, source versions, hospital, original payloads, mapping reports, event lineage, and correlation/fingerprint metadata live in the relational envelope and provenance ledger; they are not misrepresented as arbitrary FHIR top-level properties. Patient linking metadata remains in identity tables.

Validation checks supported resource kinds, source identity/version, patient references, coding/display structure, supported clinical statuses, and finite numeric doses/results. API input also validates category-specific required fields, positive doses, date syntax, allowed review/status enums, field lengths, and end dates. This is intentionally a subset validator, not full FHIR profile validation.

## Synthetic vendor formats

Both formats are invented demonstration schemas; neither is an Epic or Oracle Health production API.

| Concept | EpicMockAdapter | OracleMockAdapter |
| --- | --- | --- |
| Patient | `patientMrn` | `person.identifier` |
| Record type | `kind: medication` | `clinicalType: MEDICATION` |
| Code | `code.code/system/display` | `entry.terminology.value/namespace/label` |
| State | `status: active` | `entry.state: ACTIVE` |
| Effective date | ISO in `effective` | US calendar date or ISO datetime in `entry.clinicalDate` |
| Author/date | `author`, `recordedAt` | `entry.documentation.by/timestamp` |
| Dose | `medication.dose/unit` | `entry.details.doseAmount/unitText` |
| Frequency | `medication.frequency: BID` | `entry.details.administrationsPerDay: 2` |
| Allergy | `allergy.reaction/severity/criticality` | `manifestationText/severityLevel/riskLevel` |
| Lab | `lab.value/unit` | `numericResult/unitText` |

All translation goes through the canonical resource. `from_canonical` produces a destination-compatible **preview** using a placeholder destination identity; it never inserts that preview into a local database. The preview labels its author as external. Source authors remain in the original payload and provenance rather than being invented as destination clinicians.

## Deterministic mapping and uncertainty

`QD`/`DAILY`, `BID`, `TID`, and `QID` map to a repeat frequency of 1–4 with `period: 1` and `periodUnit: d`. Unknown frequencies remain in `dosage.text` and a documented `source-frequency` extension and produce `UNKNOWN_FREQUENCY`; they do not acquire a guessed repeat structure. Unknown units remain human-readable text with `UNMAPPED_UNIT` and no asserted UCUM code/system. Supported UCUM fixtures include `mg`, `g`, `ug`, `mL`, `L`, `%`, `mmol/L`, and `mg/dL`. No unit conversion occurs.

ISO dates, ISO datetimes with explicit timezone offsets, and explicit `MM/DD/YYYY` source dates are supported. Equivalent timestamp instants normalize to UTC so timezone serialization does not defeat same-collection-time comparisons; the original timezone serialization remains in the lossless source payload. Invalid/free-text dates and datetimes without a timezone fail mapping; the outbox snapshot remains available and failure state is visible. The demo does not infer missing timezones or collection times.

For allergy/condition assertions verified as `entered-in-error`, the canonical resource omits `clinicalStatus` and preserves the entered-in-error verification, following the supported R4 invariants. The clinical view labels the assertion erroneous and discrepancy rules exclude it. Corrections still preserve the prior source assertion in immutable history.

Unmapped source fields, including nested vendor-specific details, generate `UNMAPPED_SOURCE_FIELD` warnings and remain in the original source payload. The supported canonical subset does not represent every potential source property. Reverse previews preserve supported clinical meaning and unknown frequency text; they are not a lossless vendor-to-vendor serialization of every unknown property. The complete original payload and warnings remain available for human inspection before incorporation.

All fixture codes below use `https://clinicalsync.example/terminology/demo` and generate `DEMO_TERMINOLOGY` notices. They are **not official RxNorm, SNOMED CT, or ICD codes**:

| Fixture code | Meaning |
| --- | --- |
| `METFORMIN` | Synthetic medication-list concept |
| `PENICILLIN` | Synthetic allergy assertion |
| `TYPE2_DIABETES` | Synthetic condition |
| `HYPERTENSION` | Synthetic condition |
| `NO_KNOWN_ALLERGIES` | Explicit synthetic negative allergy assertion for rule testing |
| `PENDING_DEMO` | Restricted identity-match fixture |

The seeded A1c laboratory example uses [LOINC 4548-4](https://loinc.org/4548-4/) with `%`. Source codes in other systems are retained with `UNVERIFIED_TERMINOLOGY`; the MVP has no terminology validation service. The code system is never inferred from an arbitrary display label. Runtime mapping is deterministic and makes no external data calls.
