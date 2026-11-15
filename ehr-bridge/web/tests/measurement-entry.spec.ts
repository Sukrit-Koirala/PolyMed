import {test, expect} from '@playwright/test';
import {createMeasurementRows, serializeMeasurements, type MeasurementRow} from '../src/lib/measurement-entry';
import {MEASUREMENTS, findMeasurement, suggestMeasurements} from '../src/lib/measurement-catalog';
import {buildClinicalFields, type ClinicalRecord} from '../src/lib/clinical-summary';

function set(rows: MeasurementRow[], key: string, patch: Partial<MeasurementRow>) {
  const row = rows.find(row => findMeasurement(row.key)?.key === key)!;
  Object.assign(row, patch, {changed: true});
}

test('blank measurement presets do not invent clinical values', () => {
  expect(MEASUREMENTS.length).toBeGreaterThan(80);
  expect(serializeMeasurements(createMeasurementRows())).toEqual({});
});

test('vital forms serialize blood pressure, numeric SpO2 and zero without JSON type errors', () => {
  const rows = createMeasurementRows();
  set(rows, 'Blood pressure', {value: '120', second: '80'});
  set(rows, 'Oxygen saturation', {value: '100'});
  set(rows, 'Pain score', {value: '0'});
  expect(serializeMeasurements(rows)).toEqual({'Blood pressure': '120/80 mmHg', 'Oxygen saturation': '100%', 'Pain score': '0/10'});
  expect(Object.values(serializeMeasurements(rows)).every(value => typeof value === 'string')).toBe(true);
});

test('partial blood pressure and invalid numeric entries produce specific errors', () => {
  const rows = createMeasurementRows();set(rows, 'Blood pressure', {value: '120'});
  expect(() => serializeMeasurements(rows)).toThrow('both systolic and diastolic');
  set(rows, 'Blood pressure', {value: '', second: ''});set(rows, 'Heart rate', {value: 'NaN'});
  expect(() => serializeMeasurements(rows)).toThrow('Heart rate: enter a numeric value');
});

test('editing a visit preserves exact original keys, units, context and unknown readings', () => {
  const original = {BP: '119/79mmhg', SPO2: '97% on 2 L/min oxygen', Temperature: '36.7 C', Weight: '68.0 kg', Glucose: '5.4 mmol/L', 'Drainage score': 'trace; reviewed onsite'};
  const rows = createMeasurementRows(original);
  expect(rows.find(row => row.key === 'SPO2')).toMatchObject({value: '97', unit: '%', context: 'on 2 L/min oxygen'});
  expect(serializeMeasurements(rows)).toEqual(original);
  set(rows, 'Oxygen saturation', {value: '98'});
  expect(serializeMeasurements(rows)).toEqual({...original, SPO2: '98% on 2 L/min oxygen'});
});

test('changing units never converts the entered value and clearing removes only that field', () => {
  const rows = createMeasurementRows();set(rows, 'Temperature', {value: '98.6', unit: '°F'});set(rows, 'Weight', {value: '150', unit: 'lb'});
  expect(serializeMeasurements(rows)).toEqual({Temperature: '98.6 °F', Weight: '150 lb'});
  set(rows, 'Weight', {value: ''});expect(serializeMeasurements(rows)).toEqual({Temperature: '98.6 °F'});
});

test('custom and qualitative measurements retain names, text, optional units and comparators', () => {
  const rows = createMeasurementRows();set(rows, 'Glucose', {value: '< 5', unit: 'mmol/L'});
  rows.push({id: 'custom-1', key: 'Skin temperature difference', label: 'Skin temperature difference', category: 'Other measurements', kind: 'text', value: '0.8', second: '', unit: '°C', context: 'left compared with right', changed: true});
  rows.push({id: 'custom-2', key: 'Drainage appearance', label: 'Drainage appearance', category: 'Other measurements', kind: 'text', value: 'None observed', second: '', unit: '', context: '', changed: true});
  expect(serializeMeasurements(rows)).toEqual({Glucose: '< 5 mmol/L', 'Skin temperature difference': '0.8 °C left compared with right', 'Drainage appearance': 'None observed'});
});

test('autocomplete ranks exact abbreviations, includes recorded custom keys and avoids duplicate aliases', () => {
  expect(suggestMeasurements('SPO2')[0].key).toBe('Oxygen saturation');
  expect(suggestMeasurements('HbA1c')[0].key).toBe('Hemoglobin A1c');
  expect(suggestMeasurements('drain', ['Drainage score']).some(item => item.key === 'Drainage score')).toBe(true);
  expect(findMeasurement('Pulse')?.key).toBe('Pulse rate');
  expect(findMeasurement('HR')?.key).toBe('Heart rate');
  const rows = createMeasurementRows({BP: '120/80 mmHg', 'blood_pressure': '130/85 mmHg'});
  expect(() => serializeMeasurements(rows)).toThrow('more than once');
});

test('SpO2 aliases share one field history while clinically distinct measurements stay separate', () => {
  const base: ClinicalRecord = {id: 'old', hospital_id: 'a', hospital_name: 'Hospital A', doctor_name: 'Dr. A', visit_id: 'old', version: 1, updated_at: '2025-01-01T12:00:00Z', source_format: 'epic', files: [],
    canonical: {visit_date: '2025-01-01', reason: 'Synthetic visit', notes: '', medications: [], allergies: [], additional: {}, observations: {SPO2: '97%'}}};
  const recent = {...base, id: 'new', visit_id: 'new', updated_at: '2026-11-15T12:00:00Z', canonical: {...base.canonical, visit_date: '2026-11-15', observations: {'Oxygen saturation': '100%', 'Heart rate': '72 beats/min', 'Pulse rate': '70 beats/min'}}};
  const fields = buildClinicalFields([base, recent]);
  expect(fields.find(field => field.label === 'Oxygen saturation')?.versions).toHaveLength(2);
  expect(fields.find(field => field.label === 'Oxygen saturation')?.latest?.value).toBe('100%');
  expect(fields.some(field => field.label === 'Heart rate')).toBe(true);
  expect(fields.some(field => field.label === 'Pulse rate')).toBe(true);
});
