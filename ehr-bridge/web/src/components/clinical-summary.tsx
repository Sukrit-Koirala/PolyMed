'use client';

import {useMemo, useState} from 'react';
import {ArrowLeft, Building2, ChevronDown, FileCode2, History} from 'lucide-react';
import {
  buildClinicalFields, clinicalDate, humanLabel, recordId, uniqueRecords,
  type ClinicalField, type ClinicalFile, type ClinicalRecord, type ClinicalValue, type FieldVersion,
} from '../lib/clinical-summary';
import {Badge, Button, Empty, Modal, date} from './ui';
import {Attachments} from './record-attachments';

function readableDate(value: string, withTime = false) {
  return value && !Number.isNaN(Date.parse(value)) ? date(value, withTime) : 'Date not supplied';
}

function sourceLabel(record: ClinicalRecord) {
  const format = record.source_format;
  return format === 'FHIR R4' ? 'FHIR R4' : format === 'epic' ? 'Epic-inspired JSON' : format === 'oracle' ? 'Oracle-inspired JSON' : 'Original JSON';
}

/** Render supplied clinical values without exposing JSON syntax in the dashboard. */
function HumanValue({value}: {value: ClinicalValue}) {
  if (value === null || value === undefined || value === '') return <p className="field-unsupplied">Not documented</p>;
  if (typeof value === 'boolean') return <p>{value ? 'Yes' : 'No'}</p>;
  if (typeof value === 'number') return <p>{String(value)}</p>;
  if (typeof value === 'string') return <p className="human-text">{value}</p>;
  if (Array.isArray(value)) {
    return value.length ? <ul className="human-list">{value.map((item, index) => <li key={index}><HumanValue value={item}/></li>)}</ul> : <p className="field-unsupplied">Not documented in this report</p>;
  }
  if ('name' in value && typeof value.name === 'string') {
    const details = [value.dose, value.unit, value.frequency].filter(item => typeof item === 'string' && item.trim() && item !== 'Not documented');
    const additional = Object.entries(value).filter(([key]) => !['name', 'dose', 'unit', 'frequency'].includes(key));
    return <div className="human-medication"><strong>{value.name}</strong>{details.length > 0 && <span>{details.join(' ')}</span>}{additional.length > 0 && <dl className="human-properties">{additional.map(([key, item]) => <div key={key}><dt>{humanLabel(key)}</dt><dd><HumanValue value={item}/></dd></div>)}</dl>}</div>;
  }
  if (typeof value.text === 'string' && Object.keys(value).every(key => key === 'text' || key === 'coding')) return <p className="human-text">{value.text}</p>;
  if (Array.isArray(value.coding)) {
    const descriptions = value.coding.flatMap(item => item && typeof item === 'object' && !Array.isArray(item) && typeof item.display === 'string' ? [item.display] : []);
    if (descriptions.length) return <p>{[...new Set(descriptions)].join(' · ')}</p>;
  }
  if (typeof value.value === 'number' && (typeof value.unit === 'string' || typeof value.code === 'string')) {
    const unit = typeof value.unit === 'string' ? value.unit : String(value.code);
    return <p>{typeof value.comparator === 'string' ? value.comparator : ''}{value.value} {unit}</p>;
  }
  const properties = Object.entries(value);
  return properties.length ? <dl className="human-properties">{properties.map(([key, item]) => <div key={key}><dt>{humanLabel(key)}</dt><dd><HumanValue value={item}/></dd></div>)}</dl> : <p className="field-unsupplied">Not documented</p>;
}

function FieldValue({field, version}: {field: ClinicalField; version?: FieldVersion}) {
  if (!version || version.absent) return <p className="field-unsupplied">Not documented in this source version</p>;
  if (field.kind === 'date' && typeof version.value === 'string') return <p>{readableDate(version.value)}</p>;
  if (field.kind === 'files') {
    return Array.isArray(version.value) && version.value.length ? <Attachments files={version.value as unknown as ClinicalFile[]}/> : <p className="field-unsupplied">No attachments supplied</p>;
  }
  return <HumanValue value={version.value}/>;
}

function SourcePanel({records, initialId}: {records: ClinicalRecord[]; initialId?: string}) {
  const ordered = uniqueRecords(records);
  const [selected, setSelected] = useState(initialId || (ordered[0] ? recordId(ordered[0]) : ''));
  const [tab, setTab] = useState('original');
  const record = ordered.find(item => recordId(item) === selected) || ordered[0];
  if (!record) return <Empty title="No source payloads">A hospital has not uploaded any records yet.</Empty>;
  const payload = tab === 'original' ? record.original || record.native : tab === 'general' ? record.canonical : record.native;
  return <div className="source-panel">
    <label>Source record<select aria-label="Source record" value={recordId(record)} onChange={event => setSelected(event.target.value)}>
      {ordered.map(item => <option key={recordId(item)} value={recordId(item)}>{item.hospital_name} · {readableDate(clinicalDate(item))} · {item.canonical.reason} · version {item.version}</option>)}
    </select></label>
    <div className="source-facts"><Badge>{sourceLabel(record)}</Badge><span>{record.hospital_name}</span><span>{record.doctor_name}</span><span>Updated {readableDate(record.updated_at, true)}</span></div>
    <div className="tabs"><button className={tab === 'original' ? 'active' : ''} onClick={() => setTab('original')}>Original source</button><button className={tab === 'general' ? 'active' : ''} onClick={() => setTab('general')}>General model</button><button className={tab === 'stored' ? 'active' : ''} onClick={() => setTab('stored')}>Stored representation</button></div>
    <pre className="source-code"><code>{JSON.stringify(payload, null, 2)}</code></pre>
    <p className="muted small">The original payload is retained as uploaded. Epic/Oracle-inspired hospital destinations use demo adapters.</p>
  </div>;
}

function FieldHistory({field, onClose}: {field: ClinicalField; onClose: () => void}) {
  const [source, setSource] = useState<string | null>(null);
  return <Modal title={source ? `${field.label} · source` : `${field.label} · versions`} description="Every available hospital's stored versions, newest clinical date first. Updates preserve earlier values and attribution." onClose={onClose} wide>
    {source ? <><Button tone="ghost" onClick={() => setSource(null)}><ArrowLeft size={14}/>Back to versions</Button><SourcePanel records={field.versions.map(version => version.record)} initialId={source}/></> : <>
      <div className="field-history-intro"><strong>{field.versions.length} source {field.versions.length === 1 ? 'version' : 'versions'}</strong><span>Empty or omitted data means “not documented”; it does not mean a condition resolved.</span></div>
      <ol className="field-history">{field.versions.map(version => <li key={recordId(version.record)} data-field-version={recordId(version.record)}>
        <div className="field-history-heading"><div><h3>{version.record.hospital_name}</h3><p>Clinical date: <time dateTime={clinicalDate(version.record)}>{readableDate(clinicalDate(version.record))}</time></p></div><div className="inline">{field.latest && recordId(field.latest.record) === recordId(version.record) && <Badge tone={version.documented ? 'green' : 'gray'}>{version.documented ? 'Latest reported' : 'Latest source version'}</Badge>}<Badge tone={version.current ? 'blue' : 'gray'}>Source version {version.record.version}</Badge></div></div>
        <div className="field-history-value"><FieldValue field={field} version={version}/></div>
        <footer><div><strong>{version.record.doctor_name}</strong><span>Updated {readableDate(version.record.updated_at, true)}{!version.current ? ' · Earlier version of this visit' : ''}</span></div><Button tone="ghost" onClick={() => setSource(recordId(version.record))}><FileCode2 size={14}/>View source</Button></footer>
      </li>)}</ol>
    </>}
  </Modal>;
}

function FieldCard({field, onHistory, onSource}: {field: ClinicalField; onHistory: () => void; onSource: () => void}) {
  const latest = field.latest;
  const count = Array.isArray(latest?.value) ? latest.value.length : 0;
  return <article className={'card clinical-field ' + (field.kind === 'text' && field.key === 'visit-notes' ? 'clinical-notes' : '')} aria-label={field.label + ' data'} data-field-kind={field.kind}>
    <header><h3>{field.label}</h3><Button tone="ghost" disabled={!field.versions.length} aria-label={'Show versions for ' + field.label} onClick={onHistory}><History size={14}/>Show versions <span className="field-version-count">{field.versions.length}</span></Button></header>
    {field.kind === 'list' || field.kind === 'files' ? <details className="field-dropdown" open><summary><span>{count ? `${count} ${count === 1 ? 'item' : 'items'}` : 'No list documented'}</span><ChevronDown size={17}/></summary><div><FieldValue field={field} version={latest}/></div></details> : <div className="field-current-value"><FieldValue field={field} version={latest}/></div>}
    <footer>{latest ? <><div><span className="field-latest-label">{latest.documented ? 'Latest reported' : 'Latest source version'} · {readableDate(clinicalDate(latest.record))}</span><strong><Building2 size={12}/>{latest.record.hospital_name}</strong><span>{latest.record.doctor_name}</span></div><Button tone="ghost" aria-label={'View source for ' + field.label} onClick={onSource}>View source</Button></> : <p className="field-unsupplied">No hospital has supplied this information.</p>}</footer>
  </article>;
}

export default function ClinicalSummary({records, hospitalView = false}: {records: ClinicalRecord[]; hospitalView?: boolean}) {
  const fields = useMemo(() => buildClinicalFields(records), [records]);
  const [search, setSearch] = useState('');
  const [historyKey, setHistoryKey] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const history = fields.find(field => field.key === historyKey);
  const query = search.trim().toLowerCase();
  const visible = fields.filter(field => !query || (field.label + ' ' + JSON.stringify(field.latest?.value || '')).toLowerCase().includes(query));
  const groups = [...new Set(visible.map(field => field.group))];
  const ordered = uniqueRecords(records);
  return <section className="clinical-summary" aria-label="Patient health summary">
    <div className="section-heading clinical-summary-heading"><div><h2>Health summary</h2><p>Latest reported values, in plain language. {hospitalView ? 'History includes records available in this hospital.' : 'History includes every hospital that uploaded your records.'}</p></div><div className="inline"><input className="record-search" aria-label="Search health data" placeholder="Find allergies, blood pressure…" value={search} onChange={event => setSearch(event.target.value)}/><Button tone="secondary" disabled={!ordered.length} aria-label="View all source payloads" onClick={() => setSourceId(recordId(ordered[0]))}><FileCode2 size={14}/>View source</Button></div></div>
    {!records.length ? <Empty title="No medical information yet">Your hospital can upload a visit. You can then read each value and its history here.</Empty> : <>
      <p className="clinical-summary-note">Latest reported values use the clinical date, then the source update time. Copying an older report does not make its readings newer.</p>
      {groups.map(group => <section className="clinical-section" key={group} aria-label={group}><h3 className="clinical-section-title">{group === 'Lists' ? 'Allergies & medications' : group}</h3><div className="clinical-field-grid">{visible.filter(field => field.group === group).map(field => <FieldCard key={field.key} field={field} onHistory={() => setHistoryKey(field.key)} onSource={() => field.latest && setSourceId(recordId(field.latest.record))}/>)}</div></section>)}
      {!visible.length && <Empty title="No matching information">Try another field or value.</Empty>}
    </>}
    {history && <FieldHistory field={history} onClose={() => setHistoryKey(null)}/>}
    {sourceId && <Modal title="View source" description="Choose a hospital record to inspect its original payload, general model, or stored representation." onClose={() => setSourceId(null)} wide><SourcePanel records={ordered} initialId={sourceId}/></Modal>}
  </section>;
}
