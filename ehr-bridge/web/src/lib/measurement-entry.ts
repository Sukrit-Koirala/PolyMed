import {MEASUREMENTS, findMeasurement, measurementToken, type MeasurementDefinition} from './measurement-catalog';

export type MeasurementRow = {
  id: string; key: string; label: string; category: string; kind: MeasurementDefinition['kind'];
  value: string; second: string; unit: string; context: string;
  original?: string; changed: boolean;
};

export function emptyMeasurement(definition: MeasurementDefinition): MeasurementRow {
  return {id: 'preset-' + measurementToken(definition.key), key: definition.key, label: definition.label,
    category: definition.category, kind: definition.kind, value: '', second: '', unit: definition.units[0] || '', context: '', changed: false};
}

const numeric = '[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?';
const readingPattern = new RegExp('^((?:<=|>=|<|>)?\\s*' + numeric + ')(.*)$');
const pressurePattern = new RegExp('^(' + numeric + ')\\s*/\\s*(' + numeric + ')(.*)$');

function splitUnit(remainder: string, definition: MeasurementDefinition) {
  const text = remainder.trim();
  const choices = definition.units.flatMap(unit => unit === '°C' ? [{match: '°C', unit}, {match: 'C', unit}]
    : unit === '°F' ? [{match: '°F', unit}, {match: 'F', unit}]
      : [{match: unit, unit}]).filter(choice => choice.match).sort((a, b) => b.match.length - a.match.length);
  for (const choice of choices) {
    const suffix = text.slice(choice.match.length);
    if (text.toLowerCase().startsWith(choice.match.toLowerCase()) && (!suffix || /^\s/.test(suffix))) return {unit: choice.unit, context: suffix.trim()};
  }
  if (!text) return {unit: '', context: ''}; // Do not infer a missing unit in an existing record.
  return null;
}

export function createMeasurementRows(observations: Record<string, unknown> = {}): MeasurementRow[] {
  const rows = MEASUREMENTS.map(emptyMeasurement);
  for (const [key, supplied] of Object.entries(observations)) {
    const original = typeof supplied === 'string' ? supplied : String(supplied);
    const definition = findMeasurement(key);
    const empty = definition && rows.find(row => row.id === 'preset-' + measurementToken(definition.key) && row.original === undefined);
    let row = empty || {id: 'existing-' + rows.length, key, label: key, category: 'Other measurements', kind: 'text' as const,
      value: '', second: '', unit: '', context: '', changed: false};
    row.key = key;row.original = original;row.value = original;
    if (definition && definition.kind !== 'text') {
      const match = original.trim().match(definition.kind === 'blood-pressure' ? pressurePattern : readingPattern);
      const remainder = match?.[definition.kind === 'blood-pressure' ? 3 : 2];
      const parsed = remainder === undefined ? null : splitUnit(remainder, definition);
      if (match && parsed) {
        row.value = match[1].trim();row.second = definition.kind === 'blood-pressure' ? match[2] : '';
        row.unit = parsed.unit;row.context = parsed.context;
      } else { row.kind = 'text';row.unit = ''; }
    }
    if (!empty) rows.push(row);
  }
  return rows;
}

export function isEntered(row: MeasurementRow) { return !!(row.value.trim() || row.second.trim()); }

function isNumber(value: string) {
  const number = value.replace(/^(<=|>=|<|>)\s*/, '');
  return new RegExp('^' + numeric + '$').test(number) && Number.isFinite(Number(number));
}

export function serializeMeasurements(rows: MeasurementRow[]): Record<string, string> {
  const output: Record<string, string> = {};
  const seen = new Set<string>();
  for (const row of rows) {
    if (!isEntered(row)) continue;
    const key = row.key.trim();
    const identity = measurementToken(findMeasurement(key)?.key || key);
    if (!key || key.length > 160) throw new Error('Use a measurement name between 1 and 160 characters.');
    if (['__proto__', 'constructor', 'prototype'].includes(key.toLowerCase())) throw new Error('Choose a different measurement name.');
    if (seen.has(identity)) throw new Error(`${row.label} appears more than once. Remove the duplicate measurement.`);
    seen.add(identity);
    if (row.original !== undefined && !row.changed) { output[key] = row.original;continue; }
    const first = row.value.trim(), second = row.second.trim();
    if (row.kind === 'blood-pressure' && (!first || !second)) throw new Error('Blood pressure: enter both systolic and diastolic values, or leave both blank.');
    if (row.kind !== 'text' && (!isNumber(first) || (row.kind === 'blood-pressure' && !isNumber(second)))) throw new Error(`${row.label}: enter a numeric value, such as 72 or 4.4.`);
    if (row.kind === 'blood-pressure' && /[<>]/.test(first + second)) throw new Error('Blood pressure: enter each measured number without a comparator.');
    const unit = row.unit.trim();
    if (row.kind === 'blood-pressure' && !unit) throw new Error('Blood pressure: select the unit used for this reading.');
    if (unit.length > 40) throw new Error(`${row.label}: use a unit up to 40 characters.`);
    const value = row.kind === 'blood-pressure' ? first + '/' + second : first;
    output[key] = value + (unit ? (unit === '%' || unit.startsWith('/') ? '' : ' ') + unit : '') + (row.context.trim() ? ' ' + row.context.trim() : '');
  }
  return output;
}
