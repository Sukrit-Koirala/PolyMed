'use client';

import {useEffect, useId, useRef, useState, type KeyboardEvent} from 'react';
import {ChevronDown, Search, X} from 'lucide-react';
import {MEASUREMENTS, findMeasurement, measurementToken, suggestMeasurements, type MeasurementSuggestion} from '../lib/measurement-catalog';
import {isEntered, type MeasurementRow} from '../lib/measurement-entry';

type Props = {rows: MeasurementRow[]; onChange: (rows: MeasurementRow[]) => void; previousKeys: string[]};

function MeasurementField({row, inputId, onChange, onRemove}: {row: MeasurementRow; inputId: string; onChange: (patch: Partial<MeasurementRow>) => void; onRemove: () => void}) {
  const definition = findMeasurement(row.key);
  const units = definition?.units || [];
  const [customUnit, setCustomUnit] = useState(!units.includes(row.unit));
  const pressure = row.kind === 'blood-pressure';
  return <div role="group" aria-label={row.label} className={'measurement-field' + (isEntered(row) ? ' entered' : '')}>
    <header><h4>{row.label}</h4><button type="button" className="icon" aria-label={(definition ? 'Clear ' : 'Remove ') + row.label} onClick={onRemove}><X size={13}/></button></header>
    <div className={'measurement-inputs' + (pressure ? ' pressure-inputs' : '')}>
      <label>{pressure ? 'Systolic' : 'Value'}<input id={inputId} aria-label={pressure ? 'Blood pressure systolic' : row.label + ' value'} inputMode={row.kind === 'text' ? 'text' : 'decimal'} value={row.value} maxLength={500} onChange={event => onChange({value: event.target.value})} autoComplete="off"/></label>
      {pressure && <label>Diastolic<input aria-label="Blood pressure diastolic" inputMode="decimal" value={row.second} maxLength={40} onChange={event => onChange({second: event.target.value})} autoComplete="off"/></label>}
      <label>Unit{definition ? <select aria-label={row.label + ' unit'} value={customUnit ? '__other__' : row.unit} onChange={event => {
        if (event.target.value === '__other__') {setCustomUnit(true);onChange({unit: ''});}
        else {setCustomUnit(false);onChange({unit: event.target.value});}
      }}>
        {!units.includes('') && <option value="">Not recorded</option>}
        {units.map(unit => <option key={unit} value={unit}>{unit || 'No unit'}</option>)}
        <option value="__other__">Other unit…</option>
      </select> : <input aria-label={row.label + ' unit'} value={row.unit} maxLength={40} onChange={event => onChange({unit: event.target.value})} placeholder="Optional"/>}</label>
    </div>
    {definition && customUnit && <label className="custom-measurement-unit">Custom unit<input aria-label={row.label + ' custom unit'} value={row.unit} maxLength={40} onChange={event => onChange({unit: event.target.value})} placeholder="Enter the unit from the source report"/></label>}
    <details className="measurement-context"><summary>{row.context ? 'Context: ' + row.context : 'Add context (optional)'}</summary><input aria-label={row.label + ' context'} value={row.context} maxLength={300} onChange={event => onChange({context: event.target.value})} placeholder="For example: on room air, seated, or left arm"/></details>
  </div>;
}

export default function MeasurementEditor({rows, onChange, previousKeys}: Props) {
  const prefix = useId();
  const [query, setQuery] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [expanded, setExpanded] = useState(() => new Set(['Vital signs', ...rows.filter(isEntered).map(row => row.category)]));
  const [focusId, setFocusId] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const suggestions = suggestMeasurements(query, previousKeys);
  const exact = findMeasurement(query) || suggestions.find(option => measurementToken(option.key) === measurementToken(query));
  const custom = query.trim() && !exact ? {key: query.trim(), label: query.trim(), category: 'Custom measurement'} : null;
  const options: MeasurementSuggestion[] = [...suggestions, ...(custom ? [custom] : [])];
  const showMenu = menuOpen && !!query.trim() && options.length > 0;
  const categories = [...new Set([...MEASUREMENTS.map(item => item.category), ...rows.map(row => row.category)])];
  const inputId = (id: string) => prefix + '-reading-' + id;

  useEffect(() => {
    if (!focusId) return;
    const input = document.getElementById(inputId(focusId));
    if (input) {input.focus();input.scrollIntoView({block: 'center'});setFocusId(null);}
  }, [focusId, expanded, prefix]);

  useEffect(() => {
    if (!showMenu || active < 0) return;
    const menu = document.getElementById(prefix + '-options');
    const option = document.getElementById(prefix + '-option-' + active);
    if (!menu || !option) return;
    if (option.offsetTop < menu.scrollTop) menu.scrollTop = option.offsetTop;
    else if (option.offsetTop + option.offsetHeight > menu.scrollTop + menu.clientHeight) menu.scrollTop = option.offsetTop + option.offsetHeight - menu.clientHeight;
  }, [showMenu, active, prefix, query]);

  function choose(option: MeasurementSuggestion) {
    const identity = measurementToken(findMeasurement(option.key)?.key || option.key);
    let row = rows.find(item => measurementToken(findMeasurement(item.key)?.key || item.key) === identity);
    if (!row) {
      row = {id: 'custom-' + crypto.randomUUID(), key: option.key, label: option.label, category: 'Other measurements',
        kind: 'text', value: '', second: '', unit: '', context: '', changed: true};
      onChange([...rows, row]);
    }
    setExpanded(current => new Set([...current, row!.category]));
    setFocusId(row.id);setQuery('');setMenuOpen(false);setActive(-1);
  }

  function keyboard(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape' && menuOpen) {event.preventDefault();event.stopPropagation();setMenuOpen(false);return;}
    if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && options.length && query.trim()) {
      event.preventDefault();setMenuOpen(true);
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setActive(current => current < 0 ? (direction === 1 ? 0 : options.length - 1) : (current + direction + options.length) % options.length);
    } else if (event.key === 'Enter' && showMenu) {
      event.preventDefault();event.stopPropagation();choose(options[active] || options[0]);
    }
  }

  function update(id: string, patch: Partial<MeasurementRow>) {
    onChange(rows.map(row => row.id === id ? {...row, ...patch, changed: true} : row));
  }

  function clear(row: MeasurementRow) {
    if (!findMeasurement(row.key)) onChange(rows.filter(item => item.id !== row.id));
    else update(row.id, {value: '', second: '', context: ''});
  }

  return <section className="measurement-editor" aria-label="Measured observations">
    <div className="measurement-heading"><div><h3>Measured observations</h3><p>Enter available readings and leave the rest blank. Values are saved with their units; no JSON is needed.</p></div><span>{rows.filter(isEntered).length} entered</span></div>
    <div className="measurement-search" onBlur={event => {if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setMenuOpen(false);}}>
      <label htmlFor={prefix + '-search'}>Other / find a measurement</label>
      <div className="measurement-search-input"><Search size={16}/><input ref={searchRef} id={prefix + '-search'} role="combobox" aria-label="Other measurement" aria-autocomplete="list" aria-expanded={showMenu} aria-controls={showMenu ? prefix + '-options' : undefined} aria-activedescendant={showMenu && active >= 0 ? prefix + '-option-' + active : undefined} value={query} maxLength={160} autoComplete="off" placeholder="Type a name or abbreviation, such as SpO2, glucose, or creatinine" onFocus={() => setMenuOpen(true)} onChange={event => {setQuery(event.target.value);setMenuOpen(true);setActive(-1);}} onKeyDown={keyboard}/>{query && <button type="button" className="icon" aria-label="Clear measurement search" onClick={() => {setQuery('');searchRef.current?.focus();}}><X size={14}/></button>}</div>
      {showMenu && <div className="measurement-options" id={prefix + '-options'} role="listbox" aria-label="Measurement suggestions">{options.map((option, index) => <button key={option.category + option.key} type="button" role="option" tabIndex={-1} id={prefix + '-option-' + index} aria-selected={active === index} onMouseDown={event => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => choose(option)}>
        <strong>{option === custom ? `Use “${option.label}” as a new measurement` : option.label}</strong><span>{option.category}{option.definition?.units[0] ? ' · ' + option.definition.units[0] : ''}</span>
      </button>)}</div>}
      <p className="measurement-search-help">Select a suggestion, then enter its value below. If no preset fits, choose your typed name to add a custom measurement.</p>
    </div>
    <div className="measurement-categories">{categories.map(category => {
      const fields = rows.filter(row => row.category === category);
      if (!fields.length) return null;
      const open = expanded.has(category), count = fields.filter(isEntered).length;
      const region = prefix + '-group-' + measurementToken(category);
      return <section className="measurement-category" key={category}><button type="button" className="measurement-category-toggle" aria-label={category} aria-expanded={open} aria-controls={region} onClick={() => setExpanded(current => {const next = new Set(current);if (next.has(category)) next.delete(category);else next.add(category);return next;})}><span>{category}</span><small>{count ? `${count} entered` : fields.length + ' fields'}</small><ChevronDown size={16}/></button>{open && <div className="measurement-grid" id={region}>{fields.map(row => <MeasurementField key={row.id} row={row} inputId={inputId(row.id)} onChange={patch => update(row.id, patch)} onRemove={() => clear(row)}/>)}</div>}</section>;
    })}</div>
    <p className="measurement-unit-note">Use the unit supplied with the reading. Changing a unit does not convert the number.</p>
  </section>;
}
