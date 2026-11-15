import {findMeasurement, measurementToken} from './measurement-catalog';

export type ClinicalValue = string | number | boolean | null | ClinicalValue[] | {[key: string]: ClinicalValue};
export type ClinicalFile = {id: string; name: string; mime: string; size: number};
export type ClinicalRecord = {
  id: string; version_id?: string; visit_id: string; version: number;
  hospital_id?: string; source_hospital?: string; hospital_name: string;
  doctor_name: string; updated_at: string; source_format?: string;
  original?: unknown; native?: unknown; imported?: boolean; files: ClinicalFile[];
  canonical: {
    visit_date: string; reason: string; notes: string;
    allergies: ClinicalValue[]; medications: ClinicalValue[];
    observations: {[key: string]: ClinicalValue}; additional: {[key: string]: ClinicalValue};
  };
};
export type FieldGroup = 'Lists' | 'Measurements' | 'Visit information' | 'Additional information' | 'Images & reports';
export type FieldKind = 'list' | 'value' | 'text' | 'date' | 'files';
export type FieldVersion = {record: ClinicalRecord; value: ClinicalValue; documented: boolean; absent: boolean; current: boolean};
export type ClinicalField = {key: string; label: string; group: FieldGroup; kind: FieldKind; versions: FieldVersion[]; latest?: FieldVersion};
type ExtractedField = Omit<ClinicalField, 'versions' | 'latest'> & {value: ClinicalValue};

export function humanLabel(label: string): string {
  const words = label.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  return words ? words[0].toUpperCase() + words.slice(1) : 'Additional information';
}

function token(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function measurement(label: string) {
  const definition = findMeasurement(label);
  // Exact preset aliases only; pulse/heart rate and distinct lab tests remain separate.
  return {key: measurementToken(definition?.key || label), label: definition?.key || humanLabel(label)};
}

export function recordId(record: ClinicalRecord): string {
  return record.version_id || record.id || `${record.visit_id}:${record.hospital_id || record.source_hospital}:${record.version}`;
}

function visitId(record: ClinicalRecord): string {
  return `${record.hospital_id || record.source_hospital || record.hospital_name}:${record.visit_id || recordId(record)}`;
}

export function clinicalDate(record: ClinicalRecord): string {
  const source = record.canonical.additional?.['FHIR R4 source'];
  if (source && !Array.isArray(source) && typeof source === 'object' && typeof source.effectiveDateTime === 'string') {
    return source.effectiveDateTime;
  }
  return record.canonical.visit_date || record.updated_at;
}

function time(value: string): number {
  return Date.parse(value) || 0;
}

export function newestFirst(a: ClinicalRecord, b: ClinicalRecord): number {
  return time(clinicalDate(b)) - time(clinicalDate(a)) || time(b.updated_at) - time(a.updated_at)
    || b.version - a.version || recordId(a).localeCompare(recordId(b));
}

export function uniqueRecords(records: ClinicalRecord[]): ClinicalRecord[] {
  return Array.from(new Map(records.map(record => [recordId(record), record])).values()).sort(newestFirst);
}

function supplied(value: ClinicalValue): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return !!value.trim() && !/^(not documented|not provided|not supplied|unknown)$/i.test(value.trim());
  if (Array.isArray(value)) return value.some(supplied);
  if (typeof value === 'object') return Object.values(value).some(supplied);
  return true; // Zero and false are actual supplied values.
}

function fieldsFrom(record: ClinicalRecord): Map<string, ExtractedField> {
  const c = record.canonical;
  const fields = new Map<string, ExtractedField>();
  function put(key: string, label: string, group: FieldGroup, kind: FieldKind, value: ClinicalValue) {
    fields.set(key, {key, label, group, kind, value});
  }
  // A FHIR Observation does not make any assertion about allergy/medication history.
  if (record.source_format !== 'FHIR R4') {
    put('allergies', 'Allergies', 'Lists', 'list', c.allergies || []);
    put('medications', 'Medications', 'Lists', 'list', c.medications || []);
  }
  put('visit-date', 'Visit date', 'Visit information', 'date', c.visit_date || null);
  put('visit-reason', 'Visit reason', 'Visit information', 'text', c.reason || null);
  put('visit-notes', 'Visit notes', 'Visit information', 'text', c.notes || null);
  put('attachments', 'Images & reports', 'Images & reports', 'files', (record.files || []) as unknown as ClinicalValue);
  for (const [label, value] of Object.entries(c.observations || {})) {
    const field = measurement(label);
    put('observation:' + field.key, field.label, 'Measurements', Array.isArray(value) ? 'list' : 'value', value);
  }
  function extra(value: ClinicalValue, path: string[]) {
    if (value !== null && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length) {
      for (const [key, item] of Object.entries(value)) extra(item, [...path, key]);
    } else {
      const key = path.map(token).join('.');
      put('additional:' + key, path.map(humanLabel).join(' · '), 'Additional information', Array.isArray(value) ? 'list' : 'value', value);
    }
  }
  for (const [key, value] of Object.entries(c.additional || {})) {
    if (key === 'FHIR R4 source' && value && typeof value === 'object' && !Array.isArray(value)) {
      // Clinical result details are readable; integration IDs/codings remain in View source.
      const result = measurement(Object.keys(c.observations || {})[0] || c.reason);
      const resultKey = 'observation:' + result.key;
      if (typeof value.status === 'string') put(resultKey + ':status', result.label + ' · Report status', 'Additional information', 'value', humanLabel(value.status));
      const ranges = Array.isArray(value.referenceRange) ? value.referenceRange : [];
      const readableRanges = ranges.map(range => {
        if (!range || typeof range !== 'object' || Array.isArray(range)) return range;
        if (typeof range.text === 'string') return range.text;
        return range;
      });
      if (readableRanges.length) put(resultKey + ':range', result.label + ' · Reference range', 'Additional information', 'list', readableRanges);
      const interpretations = Array.isArray(value.interpretation) ? value.interpretation : [];
      if (interpretations.length) put(resultKey + ':interpretation', result.label + ' · Interpretation', 'Additional information', 'list', interpretations);
    } else extra(value, [key]);
  }
  return fields;
}

export function buildClinicalFields(input: ClinicalRecord[]): ClinicalField[] {
  const records = uniqueRecords(input);
  const fields = new Map<string, ClinicalField>();
  const extracted = new Map(records.map(record => [recordId(record), fieldsFrom(record)]));
  const visits = new Map<string, ClinicalRecord[]>();
  for (const record of records) {
    const id = visitId(record);
    visits.set(id, [...(visits.get(id) || []), record]);
  }
  // Keep the list categories visible even when a lab report supplies no history.
  for (const key of ['allergies', 'medications']) {
    fields.set(key, {key, label: humanLabel(key), group: 'Lists', kind: 'list', versions: []});
  }
  for (const visit of visits.values()) {
    const current = [...visit].sort((a, b) => b.version - a.version || time(b.updated_at) - time(a.updated_at))[0];
    const definitions = new Map<string, ExtractedField>();
    for (const record of visit) {
      for (const [key, field] of extracted.get(recordId(record))!) definitions.set(key, field);
    }
    for (const definition of definitions.values()) {
      let field = fields.get(definition.key);
      if (!field) {
        field = {...definition, versions: []};
        fields.set(field.key, field);
      }
      for (const record of visit) {
        const snapshot = extracted.get(recordId(record))!.get(field.key);
        const value = snapshot?.value ?? null;
        field.versions.push({record, value, documented: supplied(value), absent: !snapshot, current: recordId(record) === recordId(current)});
      }
    }
  }
  for (const field of fields.values()) {
    field.versions.sort((a, b) => newestFirst(a.record, b.record));
    const current = field.versions.filter(version => version.current);
    // A revision that removes a field must not resurrect its own previous snapshot.
    // Empty lists elsewhere do not assert that an earlier allergy/medication resolved.
    field.latest = current.find(version => version.documented) || current[0];
  }
  const groups: FieldGroup[] = ['Lists', 'Measurements', 'Visit information', 'Additional information', 'Images & reports'];
  return [...fields.values()].sort((a, b) => groups.indexOf(a.group) - groups.indexOf(b.group) || a.label.localeCompare(b.label));
}
