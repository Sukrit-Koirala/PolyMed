import type { Category, EhrVendor, FieldMapStatus, TranslationMapping } from "../types";

/**
 * Data-driven field specifications used by the mock adapters.
 *
 * IMPORTANT: the "oracle" keys are an invented Oracle-*style* flat shape and the
 * "fhir" keys are a simplified FHIR-R4-*like* rendering. Neither is an official
 * vendor schema. Real integrations must be built against the vendor's supported
 * FHIR profiles / interface specifications and tested adapters.
 */
export interface FieldSpec {
  norm: string; // normalized EHR Bridge field
  label: string;
  oracle: string; // key in Oracle-style mock payload
  fhir: string; // dotted path in FHIR-like mock payload
  /** Value conversions. When present, the field is reported as "transformed". */
  fromOracle?: (raw: Record<string, unknown>) => string | undefined;
  toOracle?: (v: string) => string;
  toFhir?: (v: string) => string;
  fromFhir?: (raw: Record<string, unknown>) => string | undefined;
}

export interface CategorySpec {
  fhirResource: string;
  oracleEntity: string;
  label: string;
  fields: FieldSpec[];
}

const title = (s: string) => s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
const str = (v: unknown) => (v === undefined || v === null || v === "" ? undefined : String(v));
const fhirTitle = (r: Record<string, unknown>, k: string) => { const v = r[k]; return v === undefined || v === null || v === "" ? undefined : title(String(v)); };

export const CATEGORY_SPECS: Record<Category, CategorySpec> = {
  allergy: {
    fhirResource: "AllergyIntolerance",
    oracleEntity: "ALLERGY",
    label: "Allergy",
    fields: [
      { norm: "substance", label: "Substance", oracle: "allergyName", fhir: "code.text" },
      { norm: "reaction", label: "Reaction", oracle: "reaction", fhir: "reaction[0].manifestation[0].text" },
      {
        norm: "severity", label: "Severity", oracle: "severityCd", fhir: "reaction[0].severity",
        fromOracle: (r) => str(r.severityCd) && title(String(r.severityCd)),
        toOracle: (v) => v.toUpperCase(), toFhir: (v) => v.toLowerCase(), fromFhir: (r) => fhirTitle(r, "reaction[0].severity"),
      },
      {
        norm: "status", label: "Status", oracle: "recordStatus", fhir: "clinicalStatus",
        fromOracle: (r) => str(r.recordStatus) && title(String(r.recordStatus)),
        toOracle: (v) => v.toUpperCase(), toFhir: (v) => v.toLowerCase(), fromFhir: (r) => fhirTitle(r, "clinicalStatus"),
      },
    ],
  },
  medication: {
    fhirResource: "MedicationRequest",
    oracleEntity: "ORDER_MED",
    label: "Medication",
    fields: [
      { norm: "drug", label: "Medication", oracle: "drugName", fhir: "medicationCodeableConcept.text" },
      {
        norm: "dose", label: "Dose", oracle: "doseQty", fhir: "dosageInstruction[0].doseAndRate[0].doseQuantity",
        fromOracle: (r) => (str(r.doseQty) ? `${r.doseQty} ${r.doseUnit ?? ""}`.trim() : undefined),
        toOracle: (v) => v.split(" ")[0], toFhir: (v) => v,
      },
      { norm: "frequency", label: "Frequency", oracle: "freqText", fhir: "dosageInstruction[0].timing.code.text" },
      {
        norm: "status", label: "Status", oracle: "orderStatus", fhir: "status",
        fromOracle: (r) => str(r.orderStatus) && title(String(r.orderStatus)),
        toOracle: (v) => v.toUpperCase(), toFhir: (v) => v.toLowerCase(), fromFhir: (r) => fhirTitle(r, "status"),
      },
      { norm: "prescriber", label: "Prescriber", oracle: "orderingProvider", fhir: "requester.display" },
    ],
  },
  bloodGroup: {
    fhirResource: "Observation",
    oracleEntity: "LAB_RESULT",
    label: "Blood group",
    fields: [
      {
        norm: "abo", label: "ABO group", oracle: "resultVal", fhir: "component[0].valueCodeableConcept.text",
        fromOracle: (r) => str(r.resultVal)?.split(" ")[0],
        toOracle: (v) => v,
      },
      {
        norm: "rh", label: "Rh factor", oracle: "resultVal", fhir: "component[1].valueCodeableConcept.text",
        fromOracle: (r) => (str(r.resultVal)?.includes("POS") ? "Positive" : str(r.resultVal)?.includes("NEG") ? "Negative" : undefined),
        toOracle: (v) => (v === "Positive" ? "POS" : "NEG"),
      },
      { norm: "method", label: "Method", oracle: "resultName", fhir: "code.text" },
    ],
  },
  lab: {
    fhirResource: "Observation",
    oracleEntity: "LAB_RESULT",
    label: "Laboratory result",
    fields: [
      { norm: "test", label: "Test", oracle: "resultName", fhir: "code.text" },
      { norm: "value", label: "Value", oracle: "resultVal", fhir: "valueQuantity.value" },
      { norm: "unit", label: "Unit", oracle: "units", fhir: "valueQuantity.unit" },
      { norm: "reference", label: "Reference range", oracle: "refRange", fhir: "referenceRange[0].text" },
      {
        norm: "flag", label: "Interpretation", oracle: "abnormalFlag", fhir: "interpretation[0].text",
        fromOracle: (r) => ({ N: "Normal", H: "High", L: "Low" } as Record<string, string>)[String(r.abnormalFlag)] ?? str(r.abnormalFlag),
        toOracle: (v) => v.charAt(0),
      },
    ],
  },
  condition: {
    fhirResource: "Condition",
    oracleEntity: "PROBLEM",
    label: "Condition",
    fields: [
      { norm: "name", label: "Condition", oracle: "problemName", fhir: "code.text" },
      {
        norm: "status", label: "Status", oracle: "lifeCycleStatus", fhir: "clinicalStatus",
        fromOracle: (r) => str(r.lifeCycleStatus) && title(String(r.lifeCycleStatus)),
        toOracle: (v) => v.toUpperCase(), toFhir: (v) => v.toLowerCase(), fromFhir: (r) => fhirTitle(r, "clinicalStatus"),
      },
      { norm: "onset", label: "Onset", oracle: "onsetDt", fhir: "onsetDateTime" },
    ],
  },
  vitals: {
    fhirResource: "Observation",
    oracleEntity: "VITAL_SIGN",
    label: "Vital signs",
    fields: [
      { norm: "bloodPressure", label: "Blood pressure", oracle: "bp", fhir: "component[bp].valueString" },
      { norm: "heartRate", label: "Heart rate", oracle: "pulse", fhir: "component[hr].valueQuantity" },
      { norm: "height", label: "Height", oracle: "heightCm", fhir: "component[height].valueQuantity" },
      { norm: "weight", label: "Weight", oracle: "weightKg", fhir: "component[weight].valueQuantity" },
      { norm: "temperature", label: "Temperature", oracle: "tempC", fhir: "component[temp].valueQuantity" },
      { norm: "spo2", label: "SpO₂", oracle: "spo2", fhir: "component[spo2].valueQuantity" },
    ],
  },
  imaging: {
    fhirResource: "DiagnosticReport",
    oracleEntity: "RAD_REPORT",
    label: "Diagnostic report",
    fields: [
      { norm: "study", label: "Study", oracle: "examName", fhir: "code.text" },
      { norm: "conclusion", label: "Conclusion", oracle: "impression", fhir: "conclusion" },
      { norm: "performer", label: "Interpreted by", oracle: "readingProvider", fhir: "resultsInterpreter[0].display" },
    ],
  },
  procedure: {
    fhirResource: "Procedure",
    oracleEntity: "PROCEDURE",
    label: "Procedure",
    fields: [
      { norm: "name", label: "Procedure", oracle: "procName", fhir: "code.text" },
      { norm: "outcome", label: "Outcome", oracle: "outcomeText", fhir: "outcome.text" },
    ],
  },
  immunization: {
    fhirResource: "Immunization",
    oracleEntity: "IMMUNIZATION",
    label: "Immunization",
    fields: [
      { norm: "vaccine", label: "Vaccine", oracle: "vaccineName", fhir: "vaccineCode.text" },
      { norm: "date", label: "Date given", oracle: "adminDt", fhir: "occurrenceDateTime" },
      { norm: "lot", label: "Lot number", oracle: "lotNum", fhir: "lotNumber" },
    ],
  },
  encounter: {
    fhirResource: "Encounter",
    oracleEntity: "VISIT",
    label: "Encounter",
    fields: [
      { norm: "type", label: "Encounter type", oracle: "visitType", fhir: "type[0].text" },
      { norm: "reason", label: "Reason", oracle: "reasonForVisit", fhir: "reasonCode[0].text" },
      { norm: "department", label: "Department", oracle: "unit", fhir: "serviceProvider.display" },
    ],
  },
  familyHistory: {
    fhirResource: "FamilyMemberHistory",
    oracleEntity: "FAMILY_HX",
    label: "Family history",
    fields: [
      { norm: "relation", label: "Relation", oracle: "relationCd", fhir: "relationship.text" },
      { norm: "condition", label: "Condition", oracle: "conditionText", fhir: "condition[0].code.text" },
    ],
  },
  document: {
    fhirResource: "DocumentReference",
    oracleEntity: "CLIN_DOC",
    label: "Document",
    fields: [
      { norm: "docType", label: "Type", oracle: "docType", fhir: "type.text" },
      { norm: "summary", label: "Summary", oracle: "docSummary", fhir: "description" },
    ],
  },
};

export const CATEGORY_LABELS: Record<Category, string> = Object.fromEntries(
  Object.entries(CATEGORY_SPECS).map(([k, v]) => [k, v.label]),
) as Record<Category, string>;

/** Patient-readable category names (used in access requests). */
export const CATEGORY_PLAIN: Record<Category, string> = {
  condition: "Diagnoses & conditions",
  medication: "Medications",
  allergy: "Allergies",
  vitals: "Vital signs",
  bloodGroup: "Blood group",
  lab: "Lab results",
  imaging: "Imaging & test reports",
  immunization: "Vaccinations",
  encounter: "Past visits",
  procedure: "Procedures",
  familyHistory: "Family history",
  document: "Clinical documents",
};

export const vendorStyle = (v: EhrVendor): "oracle" | "fhir" => (v === "Oracle Health" ? "oracle" : "fhir");

export interface TranslationRow {
  label: string;
  sourceKey: string;
  sourceValue?: string;
  normKey: string;
  normValue?: string;
  destKey: string;
  destValue?: string;
  normStatus: FieldMapStatus; // source -> normalized
  destStatus: FieldMapStatus; // normalized -> destination
}

/** Normalize a raw source payload into EHR Bridge's internal representation. */
export function normalize(
  category: Category,
  sourceVendor: EhrVendor,
  raw: Record<string, unknown>,
): { data: Record<string, string>; rows: Omit<TranslationRow, "destKey" | "destValue" | "destStatus">[] } {
  const spec = CATEGORY_SPECS[category];
  const style = vendorStyle(sourceVendor);
  const data: Record<string, string> = {};
  const rows = spec.fields.map((f) => {
    const sourceKey = style === "oracle" ? f.oracle : f.fhir;
    const rawValue = str(raw[sourceKey]);
    const conv = style === "oracle" ? f.fromOracle : f.fromFhir;
    const normValue = conv ? conv(raw) : rawValue;
    if (normValue !== undefined) data[f.norm] = normValue;
    const normStatus: FieldMapStatus =
      normValue === undefined ? "missing" : conv && normValue !== rawValue ? "transformed" : "mapped";
    return { label: f.label, sourceKey, sourceValue: rawValue, normKey: f.norm, normValue, normStatus };
  });
  return { data, rows };
}

/** Render a normalized record for a destination EHR, honoring that destination's import mapping. */
export function toDestination(
  category: Category,
  destVendor: EhrVendor,
  data: Record<string, string>,
  mapping?: TranslationMapping,
): { payload: Record<string, string>; rows: Pick<TranslationRow, "destKey" | "destValue" | "destStatus" | "normKey">[] } {
  const spec = CATEGORY_SPECS[category];
  const style = vendorStyle(destVendor);
  const payload: Record<string, string> = {};
  if (style === "fhir") payload.resourceType = spec.fhirResource;
  else payload.entity = spec.oracleEntity;
  const rows = spec.fields.map((f) => {
    const destKey = style === "oracle" ? f.oracle : f.fhir;
    const v = data[f.norm];
    const unsupported = mapping && (!mapping.supported || mapping.unsupportedFields.includes(f.norm));
    if (v === undefined) return { normKey: f.norm, destKey, destStatus: "missing" as FieldMapStatus };
    if (unsupported) return { normKey: f.norm, destKey, destStatus: "preserved" as FieldMapStatus };
    const conv = style === "oracle" ? f.toOracle : f.toFhir;
    const destValue = conv ? conv(v) : v;
    payload[destKey] = destValue;
    return { normKey: f.norm, destKey, destValue, destStatus: (conv && destValue !== v ? "transformed" : "mapped") as FieldMapStatus };
  });
  return { payload, rows };
}

export function fullTranslation(
  category: Category,
  sourceVendor: EhrVendor,
  destVendor: EhrVendor,
  raw: Record<string, unknown>,
  mapping?: TranslationMapping,
): { rows: TranslationRow[]; normalized: Record<string, string>; destination: Record<string, string> } {
  const n = normalize(category, sourceVendor, raw);
  const d = toDestination(category, destVendor, n.data, mapping);
  const rows = n.rows.map((r) => {
    const dr = d.rows.find((x) => x.normKey === r.normKey)!;
    return { ...r, destKey: dr.destKey, destValue: dr.destValue, destStatus: r.normStatus === "missing" ? ("missing" as FieldMapStatus) : dr.destStatus };
  });
  return { rows, normalized: n.data, destination: d.payload };
}

/** Fields of a normalized record that a destination mapping cannot represent. */
export function preservedFieldsFor(category: Category, data: Record<string, string>, mapping?: TranslationMapping): string[] {
  if (!mapping) return [];
  const spec = CATEGORY_SPECS[category];
  return spec.fields
    .filter((f) => data[f.norm] !== undefined && (!mapping.supported || mapping.unsupportedFields.includes(f.norm)))
    .map((f) => f.label);
}

/** Inverse of normalize for building realistic raw mock payloads from seed data. */
export function denormalize(category: Category, vendor: EhrVendor, data: Record<string, string>): Record<string, unknown> {
  const spec = CATEGORY_SPECS[category];
  const style = vendorStyle(vendor);
  const raw: Record<string, unknown> = {};
  if (style === "fhir") raw.resourceType = spec.fhirResource;
  for (const f of spec.fields) {
    const v = data[f.norm];
    if (v === undefined) continue;
    if (style === "fhir") raw[f.fhir] = f.toFhir ? f.toFhir(v) : v;
    else if (category === "medication" && f.norm === "dose") {
      const [q, ...u] = v.split(" ");
      raw.doseQty = q;
      raw.doseUnit = u.join(" ");
    } else if (category === "bloodGroup" && (f.norm === "abo" || f.norm === "rh")) {
      raw.resultVal = `${data.abo ?? ""} ${data.rh === "Positive" ? "POS" : data.rh === "Negative" ? "NEG" : ""}`.trim();
    } else if (category === "lab" && f.norm === "flag") raw.abnormalFlag = v.charAt(0);
    else raw[f.oracle] = f.toOracle ? f.toOracle(v) : v;
  }
  if (style === "oracle") raw._entity = spec.oracleEntity;
  return raw;
}
