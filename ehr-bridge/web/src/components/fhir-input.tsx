'use client';

import {useState} from 'react';
import {Alert} from './ui';

export default function FhirInput({value,onChange,patient,confirmed,onConfirm}:any){
 const [error,setError]=useState('');
 let source:any=null,reference='';
 try{const bundle=JSON.parse(value);const entry=bundle.entry?.find((e:any)=>e.resource?.resourceType==='Patient');source=entry?.resource;reference=entry?.fullUrl||''}catch{}
 const names=source?.name||[],name=names.find((n:any)=>n.use==='official')||names[0];
 const sourceName=name?([...name.given||[],name.family||''].join(' ').trim()||name.text):'';
 async function load(file?:File){if(!file)return;setError('');onConfirm(false);try{if(file.size>200000)throw new Error('Use a JSON bundle smaller than 200 KB.');const text=await file.text();const parsed=JSON.parse(text);if(parsed.resourceType!=='Bundle')throw new Error('Select the collection Bundle, not the individual Patient or Observation file.');onChange(text)}catch(e:any){setError(e.message);onChange('')}}
 return <section><div className="notice"><span>Import a FHIR R4 collection containing one Patient and one final quantity Observation. This adds an observation, not a complete encounter or medical history. The original resources, codes, units, and source references are retained.</span></div><label>FHIR file<input type="file" accept=".json,application/json,application/fhir+json" aria-label="Import FHIR R4 JSON file" onChange={e=>load(e.target.files?.[0])}/></label><Alert text={error}/><label>FHIR R4 bundle JSON<textarea aria-label="FHIR R4 bundle JSON" className="code-editor" rows={12} maxLength={200000} value={value} onChange={e=>{onChange(e.target.value);onConfirm(false)}} placeholder="Choose upload-bundle.fhir.json from demo-reports/oracle-sandbox, or paste a supported bundle."/></label>{source&&<div className="notice amber"><div><strong>Check the patient mapping</strong><p>Source: {sourceName||'Name unavailable'} · DOB {source.birthDate||'unavailable'}</p><p>Destination: {patient.name} · DOB {patient.birth_date} · {patient.id}</p><p className="small" style={{overflowWrap:'anywhere'}}>{reference}</p><label className="check"><input type="checkbox" checked={confirmed} onChange={e=>onConfirm(e.target.checked)}/>I verified that the source and selected profile represent the same sandbox patient.</label></div></div>}<p className="muted small">Supported-field checks are performed on the server. Full FHIR profile validation and writes to a live EHR are not included. Hospital destination formats remain simulated.</p></section>;
}
