import {test, expect} from '@playwright/test';
import {buildClinicalFields, type ClinicalRecord} from '../src/lib/clinical-summary';

function record(id: string, hospital: string, day: string, version = 1, visit = id): ClinicalRecord {
  return {id, visit_id: visit, version, hospital_id: hospital, hospital_name: hospital,
    doctor_name: 'Dr. ' + hospital, updated_at: day + 'T12:00:00Z', source_format: hospital === 'A' ? 'epic' : 'oracle', files: [],
    canonical: {visit_date: day, reason: 'Fictional visit', notes: '', medications: [], allergies: [], observations: {}, additional: {}}};
}

test('clinical dates choose the latest value and history includes every hospital version', () => {
  const old = record('old', 'B', '2025-01-03');old.canonical.observations = {blood_pressure: '110/70 mmHg'};
  const first = record('first', 'A', '2026-11-15', 1, 'current');first.canonical.observations = {'Blood pressure': '118/78 mmHg'};
  const latest = record('latest', 'A', '2026-11-15', 2, 'current');latest.canonical.observations = {bloodPressure: '120/80 mmHg'};
  latest.updated_at = '2026-11-15T13:00:00Z';
  old.updated_at = '2026-11-16T15:00:00Z'; // An old report uploaded after the recent reading.
  const field = buildClinicalFields([old, first, latest]).find(item => item.label === 'Blood pressure')!;
  expect(field.latest?.value).toBe('120/80 mmHg');
  expect(field.versions.map(item => item.record.id)).toEqual(['latest', 'first', 'old']);
  expect(field.versions.map(item => item.record.hospital_name)).toEqual(['A', 'A', 'B']);
});

test('list histories retain complete lists and source snapshots rather than merge them', () => {
  const a = record('a', 'A', '2025-01-03');a.canonical.allergies = ['Apple'];a.canonical.medications = [{name: 'Ibuprofen', dose: '200', unit: 'mg', frequency: 'As documented'}];
  const b = record('b', 'B', '2026-11-15');b.canonical.allergies = ['Apple', 'Almonds'];b.canonical.medications = [{name: 'Mouth wash', dose: '10', unit: 'mL', frequency: 'As documented'}];
  const fields = buildClinicalFields([a, b]);
  expect(fields.find(field => field.key === 'allergies')!.latest?.value).toEqual(['Apple', 'Almonds']);
  expect(fields.find(field => field.key === 'allergies')!.versions.map(item => item.value)).toEqual([['Apple', 'Almonds'], ['Apple']]);
  expect(fields.find(field => field.key === 'medications')!.latest?.value).toEqual(b.canonical.medications);
});

test('FHIR lab imports do not clear a previously reported allergy or medication list', () => {
  const allergy = record('allergy', 'A', '2025-01-03');allergy.canonical.allergies = ['Almonds'];
  const lab = record('lab', 'B', '2026-11-15');lab.source_format = 'FHIR R4';lab.canonical.observations = {'Potassium Level': '4.4 mmol/L'};
  const field = buildClinicalFields([allergy, lab]).find(item => item.key === 'allergies')!;
  expect(field.latest?.value).toEqual(['Almonds']);expect(field.versions).toHaveLength(1);
});

test('removing a value in a later version does not resurrect the old source snapshot', () => {
  const old = record('old', 'A', '2026-11-15', 1, 'visit');old.canonical.observations = {'Blood pressure': '120/80 mmHg'};
  const revised = record('revised', 'A', '2026-11-15', 2, 'visit');revised.updated_at = '2026-11-15T13:00:00Z';
  const field = buildClinicalFields([old, revised]).find(item => item.label === 'Blood pressure')!;
  expect(field.latest?.record.id).toBe('revised');expect(field.latest?.absent).toBe(true);
  expect(field.versions.map(item => item.value)).toEqual([null, '120/80 mmHg']);
});

test('latest visit revision is authoritative even when it corrects a clinical date backwards', () => {
  const old = record('old', 'A', '2026-11-15', 1, 'visit');old.canonical.observations = {'Blood pressure': '120/80 mmHg'};
  const revised = record('revised', 'A', '2024-01-03', 2, 'visit');revised.canonical.observations = {'Blood pressure': '100/60 mmHg'};
  const other = record('other', 'B', '2025-06-01');other.canonical.observations = {'Blood pressure': '110/70 mmHg'};
  const field = buildClinicalFields([old, revised, other]).find(item => item.label === 'Blood pressure')!;
  expect(field.latest?.record.id).toBe('other');expect(field.versions).toHaveLength(3);
});

test('nested additional fields and attachments receive their own histories, including zero and false', () => {
  const a = record('a', 'A', '2026-11-15');
  a.canonical.additional = {blood_group: 'A+', follow_up: {pain_score: 0, fasting: false, instructions: ['Bring records', 'Confirm details']}};
  a.files = [{id: 'report', name: 'Report.pdf', mime: 'application/pdf', size: 500}];
  const fields = buildClinicalFields([a]);
  expect(fields.find(field => field.label === 'Blood group')?.latest?.value).toBe('A+');
  expect(fields.find(field => field.label === 'Follow up · Pain score')?.latest?.documented).toBe(true);
  expect(fields.find(field => field.label === 'Follow up · Fasting')?.latest?.documented).toBe(true);
  expect(fields.find(field => field.key === 'attachments')?.versions[0].value).toEqual(a.files);
  expect(fields.find(field => field.label === 'Follow up · Instructions')?.kind).toBe('list');
});

test('duplicate copies are not counted twice and FHIR codes stay out of clinical field cards', () => {
  const a = record('a', 'A', '2026-11-15');a.source_format = 'FHIR R4';
  a.canonical.observations = {'Potassium Level': '4.4 mmol/L'};
  a.canonical.additional = {'FHIR R4 source': {status: 'final', code: {coding: [{system: 'http://loinc.org', code: '2823-3'}]}, effectiveDateTime: '2026-11-15T10:30:00Z'}};
  const fields = buildClinicalFields([a, {...a}]);
  expect(fields.find(field => field.label === 'Potassium Level')?.versions).toHaveLength(1);
  expect(fields.some(field => field.label.includes('Coding') || field.label.includes('System'))).toBe(false);
  expect(fields.find(field => field.label === 'Potassium Level · Report status')?.latest?.value).toBe('Final');
});

test('different lab measurements retain separate reference-range and status histories', () => {
  const potassium = record('potassium', 'A', '2026-11-14');potassium.source_format = 'FHIR R4';
  potassium.canonical.observations = {'Potassium Level': '4.4 mmol/L'};
  potassium.canonical.additional = {'FHIR R4 source': {status: 'final', referenceRange: [{text: '3.5–5.0 mmol/L'}]}};
  const glucose = record('glucose', 'B', '2026-11-15');glucose.source_format = 'FHIR R4';
  glucose.canonical.observations = {Glucose: '5.1 mmol/L'};
  glucose.canonical.additional = {'FHIR R4 source': {status: 'corrected', referenceRange: [{text: '3.0–6.0 mmol/L'}]}};
  const fields = buildClinicalFields([potassium, glucose]);
  expect(fields.find(field => field.label === 'Potassium Level · Reference range')?.versions).toHaveLength(1);
  expect(fields.find(field => field.label === 'Potassium Level · Reference range')?.latest?.value).toEqual(['3.5–5.0 mmol/L']);
  expect(fields.find(field => field.label === 'Glucose · Reference range')?.latest?.value).toEqual(['3.0–6.0 mmol/L']);
  expect(fields.find(field => field.label === 'Potassium Level · Report status')?.latest?.value).toBe('Final');
  expect(fields.find(field => field.label === 'Glucose · Report status')?.latest?.value).toBe('Corrected');
});
