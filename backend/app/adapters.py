"""Deterministic, synthetic vendor-inspired adapters. Not vendor API schemas."""
import copy
import hashlib
import json
import math
import base64
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TRANSFORMATION_VERSION = 'clinicalsync-fhir-subset-2.0'
KINDS = {'medication': 'MedicationStatement', 'allergy': 'AllergyIntolerance', 'diagnosis': 'Condition', 'lab': 'Observation', 'vaccination': 'Immunization', 'note': 'DocumentReference'}
REVERSE_KINDS = {v: k for k, v in KINDS.items()}
REVERSE_KINDS['ImmunizationRecommendation'] = 'vaccination'
CATEGORY_FIELDS = {
    'medication': {'dose', 'unit', 'frequency', 'end'},
    'allergy': {'reaction', 'severity', 'criticality', 'verification'},
    'diagnosis': {'verification', 'end'},
    'lab': {'value', 'unit'},
    'vaccination': {'dose_number', 'dose_amount', 'dose_unit', 'route', 'site', 'lot_number', 'provider', 'historical', 'status_reason'},
    'note': {'sections', 'approved_by', 'approved_at'},
}
FREQUENCIES = {'QD': 1, 'DAILY': 1, 'BID': 2, 'TID': 3, 'QID': 4}
DEMO_SYSTEM = 'https://clinicalsync.example/terminology/demo'
STATUS_SYSTEM = 'http://terminology.hl7.org/CodeSystem/'
SUPPORTED_UCUM = {'mg', 'g', 'ug', 'mL', 'L', '%', 'mmol/L', 'mg/dL'}


def quantity(value, unit, warnings):
    result = {'value': value, 'unit': unit}
    if unit in SUPPORTED_UCUM:
        result.update(system='http://unitsofmeasure.org', code=unit)
    else:
        warnings.append({'path': 'unit', 'code': 'UNMAPPED_UNIT', 'message': f'Source unit preserved as text: {unit}. No UCUM mapping was asserted.'})
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def date_iso(value):
    if not value:
        raise ValueError('A clinically relevant date is required')
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Source datetimes require an explicit timezone; none will be inferred')
    return parsed.astimezone(timezone.utc).isoformat()


def concept(code, system):
    return {'coding': [{'system': system, 'code': code}]}


def code_concept(r):
    kind = r['resourceType']
    if kind == 'MedicationStatement':
        return r['medicationCodeableConcept']
    if kind == 'Immunization':
        return r['vaccineCode']
    if kind == 'ImmunizationRecommendation':
        return r['recommendation'][0]['vaccineCode'][0]
    if kind == 'DocumentReference':
        return r['type']
    return r['code']


def note_sections(r):
    return json.loads(base64.b64decode(r['content'][0]['attachment']['data'], validate=True).decode('utf-8'))


class CanonicalClinicalModel(BaseModel):
    """FHIR R4-shaped subset plus a separate, lossless translation envelope."""
    resource: dict[str, Any]
    original_payload: dict[str, Any]
    warnings: list[dict[str, str]] = Field(default_factory=list)
    transformation_version: str = TRANSFORMATION_VERSION

    @model_validator(mode='after')
    def validate_subset(self):
        TranslationValidator.validate(self.resource)
        return self


class TranslationValidator:
    @staticmethod
    def validate(r):
        kind = r.get('resourceType')
        if kind not in REVERSE_KINDS:
            raise ValueError('Unsupported canonical resource type')
        if not r.get('id') or not r.get('meta', {}).get('versionId'):
            raise ValueError('Resource identity and source version are required')
        reference = r.get('patient' if kind in ('AllergyIntolerance', 'Immunization', 'ImmunizationRecommendation') else 'subject', {}).get('reference', '')
        if not reference.startswith('Patient/'):
            raise ValueError('Patient reference required')
        code = code_concept(r)
        if not code.get('coding') or not code.get('text'):
            raise ValueError('Clinical code and display required')
        statuses = {'MedicationStatement': {'active', 'completed', 'entered-in-error', 'intended', 'stopped', 'on-hold', 'unknown', 'not-taken'}, 'Observation': {'registered', 'preliminary', 'final', 'amended', 'corrected', 'cancelled', 'entered-in-error', 'unknown'}}
        if kind in statuses and r.get('status') not in statuses[kind]:
            raise ValueError('Unsupported resource status')
        if kind in ('Condition', 'AllergyIntolerance'):
            erroneous = r.get('verificationStatus', {}).get('coding', [{}])[0].get('code') == 'entered-in-error'
            if erroneous:
                if 'clinicalStatus' in r:
                    raise ValueError('Entered-in-error assertions cannot carry clinicalStatus')
            else:
                if not r.get('clinicalStatus', {}).get('coding'):
                    raise ValueError('Clinical status required')
                allowed = {'Condition': {'active', 'recurrence', 'relapse', 'inactive', 'remission', 'resolved'}, 'AllergyIntolerance': {'active', 'inactive', 'resolved'}}[kind]
                if r['clinicalStatus']['coding'][0]['code'] not in allowed:
                    raise ValueError('Unsupported clinical status')
        if kind == 'MedicationStatement':
            value = r['dosage'][0]['doseAndRate'][0]['doseQuantity']['value']
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Positive finite medication dose required')
        if kind == 'Observation':
            value = r['valueQuantity']['value']
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Finite numeric laboratory result required')
        if kind == 'Immunization':
            if r.get('status') not in ('completed', 'not-done', 'entered-in-error') or not r.get('occurrenceDateTime'):
                raise ValueError('Immunization requires a supported status and occurrence date')
        if kind == 'ImmunizationRecommendation' and not r.get('date'):
            raise ValueError('A planned vaccination requires a recommendation date')
        if kind == 'DocumentReference':
            if r.get('status') not in ('current', 'superseded', 'entered-in-error') or r.get('docStatus') != 'final':
                raise ValueError('Only explicitly approved final notes enter the clinical representation')
            sections = note_sections(r)
            if set(sections) != {'subjective', 'objective', 'assessment', 'plan'} or not all(isinstance(v, str) for v in sections.values()):
                raise ValueError('A note requires the supported SOAP document structure')
        return r


class ClinicalAdapter(ABC):
    @abstractmethod
    def unpack(self, source_record): ...

    @abstractmethod
    def pack(self, data): ...

    def to_canonical(self, source_record, patient_id='UNLINKED', resource_id=None, source_version=1, updated_at=None):
        d, warnings = self.unpack(source_record)
        kind = d['kind']
        resource_type = KINDS[kind]
        if kind == 'vaccination' and d.get('status') == 'planned':
            resource_type = 'ImmunizationRecommendation'
        coding = {'coding': [{'system': d.get('system') or DEMO_SYSTEM, 'code': d['code'], 'display': d['display']}], 'text': d['display']}
        if not d.get('system') or d.get('system') == DEMO_SYSTEM:
            warnings.append({'path': 'code', 'code': 'DEMO_TERMINOLOGY', 'message': 'Controlled demonstration terminology; no official clinical code is asserted.'})
        elif (d.get('system'), d['code']) != ('http://loinc.org', '4548-4'):
            warnings.append({'path': 'code', 'code': 'UNVERIFIED_TERMINOLOGY', 'message': 'Source coding preserved. This MVP has no terminology service to validate this code.'})
        effective = date_iso(d['effective'])
        r = {'resourceType': resource_type, 'id': resource_id or d.get('id', 'preview'), 'meta': {'versionId': str(source_version), 'lastUpdated': updated_at or d.get('recorded') or effective, 'source': f"urn:clinicalsync:{self.hospital_id}"}, 'identifier': [{'system': f'urn:clinicalsync:{self.hospital_id}:record', 'value': d.get('id', 'preview')}], 'patient' if kind in ('allergy', 'vaccination') else 'subject': {'reference': f'Patient/{patient_id}'}}
        status = d.get('status', 'active').lower()
        if kind == 'medication':
            freq = d.get('frequency', '')
            dosage = {'text': str(freq), 'doseAndRate': [{'doseQuantity': quantity(d['dose'], d['unit'], warnings)}]}
            if str(freq).upper() in FREQUENCIES:
                dosage['timing'] = {'repeat': {'frequency': FREQUENCIES[str(freq).upper()], 'period': 1, 'periodUnit': 'd'}}
            elif freq:
                dosage['extension'] = [{'url': 'https://clinicalsync.example/fhir/StructureDefinition/source-frequency', 'valueString': str(freq)}]
                warnings.append({'path': 'frequency', 'code': 'UNKNOWN_FREQUENCY', 'message': f'Unmapped frequency preserved: {freq}. Review required; no frequency was inferred.'})
            r.update(status=status, medicationCodeableConcept=coding, effectivePeriod={'start': effective}, dateAsserted=d.get('recorded') or effective, dosage=[dosage])
            if d.get('end'):
                r['effectivePeriod']['end'] = date_iso(d['end'])
        elif kind == 'allergy':
            r.update(code=coding, clinicalStatus=concept(status, STATUS_SYSTEM + 'allergyintolerance-clinical'), verificationStatus=concept(d.get('verification', 'confirmed'), STATUS_SYSTEM + 'allergyintolerance-verification'), recordedDate=d.get('recorded') or effective, onsetDateTime=effective, criticality=d.get('criticality', 'unable-to-assess'))
            if d.get('reaction'):
                r['reaction'] = [{'manifestation': [{'text': d['reaction']}], 'severity': d.get('severity', 'moderate')}]
        elif kind == 'diagnosis':
            r.update(code=coding, clinicalStatus=concept(status, STATUS_SYSTEM + 'condition-clinical'), verificationStatus=concept(d.get('verification', 'confirmed'), STATUS_SYSTEM + 'condition-ver-status'), onsetDateTime=effective, recordedDate=d.get('recorded') or effective)
            if d.get('end'):
                r['abatementDateTime'] = date_iso(d['end'])
        elif kind == 'lab':
            r.update(code=coding, status='final' if status == 'active' else status, effectiveDateTime=effective, issued=d.get('recorded') or effective, valueQuantity=quantity(d['value'], d['unit'], warnings))
        elif kind == 'vaccination':
            if status == 'planned':
                r.update(date=d.get('recorded') or r['meta']['lastUpdated'], recommendation=[{'vaccineCode': [coding], 'forecastStatus': {'coding': [{'system': DEMO_SYSTEM, 'code': 'PLANNED'}], 'text': 'Planned; not administered'}, 'dateCriterion': [{'code': {'text': 'Planned date'}, 'value': effective}]}])
                if d.get('dose_number') is not None:
                    r['recommendation'][0]['doseNumberPositiveInt'] = d['dose_number']
                # Preserve planned attributes without claiming an administration occurred.
                planned = {k: d[k] for k in CATEGORY_FIELDS['vaccination'] if d.get(k) is not None}
                r['extension'] = [{'url': 'https://clinicalsync.example/fhir/StructureDefinition/planned-vaccination-source-details', 'valueString': json.dumps(planned, sort_keys=True)}]
            else:
                r.update(status=status, vaccineCode=coding, occurrenceDateTime=effective, recorded=d.get('recorded') or effective, primarySource=not d.get('historical', False))
                if d.get('dose_number') is not None:
                    r['protocolApplied'] = [{'doseNumberPositiveInt': d['dose_number']}]
                if d.get('dose_amount') is not None:
                    r['doseQuantity'] = quantity(d['dose_amount'], d.get('dose_unit') or 'mL', warnings)
                for key, field in [('route', 'route'), ('site', 'site'), ('status_reason', 'statusReason')]:
                    if d.get(key):
                        r[field] = {'text': d[key]}
                if d.get('lot_number'):
                    r['lotNumber'] = d['lot_number']
                if d.get('provider'):
                    r['performer'] = [{'actor': {'display': d['provider']}}]
        elif kind == 'note':
            sections = d.get('sections') or {k: '' for k in ('subjective', 'objective', 'assessment', 'plan')}
            r.update(status=status, docStatus='final', type=coding, date=d.get('approved_at') or d.get('recorded'), author=[{'display': d.get('approved_by') or d.get('author') or 'Source clinician'}], content=[{'attachment': {'contentType': 'application/json', 'title': d['display'], 'data': base64.b64encode(json.dumps(sections, ensure_ascii=False).encode('utf-8')).decode('ascii')}}], context={'period': {'start': effective}})
        if d.get('note'):
            if kind == 'note':
                r['description'] = d['note']
            elif resource_type == 'ImmunizationRecommendation':
                r['recommendation'][0]['description'] = d['note']
            else:
                r['note'] = [{'text': d['note']}]
        if kind in ('allergy', 'diagnosis') and d.get('verification') == 'entered-in-error':
            r.pop('clinicalStatus', None)
        return CanonicalClinicalModel(resource=r, original_payload=copy.deepcopy(source_record), warnings=warnings)

    def from_canonical(self, canonical_record, local_patient_id='DESTINATION-PREVIEW'):
        r = canonical_record.resource if isinstance(canonical_record, CanonicalClinicalModel) else canonical_record
        TranslationValidator.validate(r)
        kind = REVERSE_KINDS[r['resourceType']]
        code = code_concept(r)
        coding = code['coding'][0]
        d = {'kind': kind, 'id': r['identifier'][0]['value'], 'patient': local_patient_id, 'code': coding['code'], 'system': coding['system'], 'display': code['text'], 'recorded': r.get('recordedDate', r.get('dateAsserted', r.get('issued', r['meta']['lastUpdated']))), 'author': 'External source — preview only', 'note': '\n'.join(n['text'] for n in r.get('note', []))}
        if kind == 'medication':
            dose = r['dosage'][0]
            quantity = dose['doseAndRate'][0]['doseQuantity']
            repeat = dose.get('timing', {}).get('repeat', {})
            d.update(status=r['status'], effective=r['effectivePeriod']['start'], end=r['effectivePeriod'].get('end'), dose=quantity['value'], unit=quantity['unit'], frequency={1: 'QD', 2: 'BID', 3: 'TID', 4: 'QID'}.get(repeat.get('frequency'), dose.get('text', '')))
        elif kind in ('allergy', 'diagnosis'):
            d.update(status=r.get('clinicalStatus', {}).get('coding', [{'code': 'inactive'}])[0]['code'], effective=r['onsetDateTime'], verification=r['verificationStatus']['coding'][0]['code'])
            if kind == 'allergy':
                reaction = r.get('reaction', [{}])[0]
                d.update(reaction=reaction.get('manifestation', [{}])[0].get('text', ''), severity=reaction.get('severity', 'moderate'), criticality=r.get('criticality', 'unable-to-assess'))
            else:
                d['end'] = r.get('abatementDateTime')
        elif kind == 'lab':
            d.update(status=r['status'], effective=r['effectiveDateTime'], value=r['valueQuantity']['value'], unit=r['valueQuantity']['unit'])
        elif kind == 'vaccination':
            if r['resourceType'] == 'ImmunizationRecommendation':
                recommendation = r['recommendation'][0]
                d.update(status='planned', effective=recommendation['dateCriterion'][0]['value'], recorded=r['date'])
                for extension in r.get('extension', []):
                    if extension['url'].endswith('/planned-vaccination-source-details'):
                        d.update(json.loads(extension['valueString']))
            else:
                d.update(status=r['status'], effective=r['occurrenceDateTime'], recorded=r.get('recorded'), historical=not r.get('primarySource', True), dose_number=r.get('protocolApplied', [{}])[0].get('doseNumberPositiveInt'), dose_amount=r.get('doseQuantity', {}).get('value'), dose_unit=r.get('doseQuantity', {}).get('unit'), route=r.get('route', {}).get('text', ''), site=r.get('site', {}).get('text', ''), status_reason=r.get('statusReason', {}).get('text', ''), lot_number=r.get('lotNumber', ''), provider=r.get('performer', [{'actor': {}}])[0]['actor'].get('display', ''))
        elif kind == 'note':
            d.update(status=r['status'], effective=r['context']['period']['start'], sections=note_sections(r), approved_by=r['author'][0]['display'], approved_at=r['date'], recorded=r['date'])
        if kind == 'note':
            d['note'] = r.get('description', '')
        elif r['resourceType'] == 'ImmunizationRecommendation':
            d['note'] = r['recommendation'][0].get('description', '')
        return self.pack(d)


def unknown_keys(obj, allowed, path=''):
    return [{'path': f'{path}{k}', 'code': 'UNMAPPED_SOURCE_FIELD', 'message': 'Unmapped source field preserved in original payload; review before incorporation.'} for k in obj if k not in allowed]


class EpicMockAdapter(ClinicalAdapter):
    hospital_id = 'northstar'

    def unpack(self, s):
        d = {'kind': s['kind'], 'id': s['recordId'], 'patient': s['patientMrn'], 'code': s['code']['code'], 'system': s['code'].get('system'), 'display': s['code']['display'], 'status': s.get('status', 'active'), 'effective': s['effective'], 'recorded': s.get('recordedAt'), 'author': s.get('author'), 'note': s.get('note', '') if isinstance(s.get('note', ''), str) else ''}
        detail_key = 'clinicalNote' if s['kind'] == 'note' and 'clinicalNote' in s else s['kind']
        detail = s[detail_key]
        d.update(detail)
        allowed_details = CATEGORY_FIELDS
        warnings = unknown_keys(s, {'kind', 'recordId', 'patientMrn', 'code', 'status', 'effective', 'recordedAt', 'author', 'note', detail_key}) + unknown_keys(detail, allowed_details[s['kind']], detail_key + '.') + unknown_keys(s['code'], {'code', 'system', 'display'}, 'code.')
        return d, warnings

    def pack(self, d):
        fields = sorted(CATEGORY_FIELDS[d['kind']])
        return {'kind': d['kind'], 'recordId': d['id'], 'patientMrn': d['patient'], 'code': {'code': d['code'], 'system': d.get('system') or DEMO_SYSTEM, 'display': d['display']}, 'status': d.get('status', 'active'), 'effective': d['effective'], 'recordedAt': d.get('recorded'), 'author': d.get('author'), 'note': d.get('note', ''), 'clinicalNote' if d['kind'] == 'note' else d['kind']: {k: d[k] for k in fields if d.get(k) is not None}}


class OracleMockAdapter(ClinicalAdapter):
    hospital_id = 'riverside'
    field_map = {'dose': 'doseAmount', 'unit': 'unitText', 'frequency': 'scheduleText', 'end': 'endDate', 'reaction': 'manifestationText', 'severity': 'severityLevel', 'criticality': 'riskLevel', 'verification': 'verificationState', 'value': 'numericResult'}
    field_map.update(dose_number='seriesDose', dose_amount='administeredAmount', dose_unit='administrationUnit', route='administrationRoute', site='administrationSite', lot_number='batchIdentifier', provider='administeredBy', historical='reportedHistory', status_reason='notGivenReason', sections='soapDocument', approved_by='signedBy', approved_at='signedAt')

    def unpack(self, s):
        e = s['entry']
        d = {'kind': s['clinicalType'].lower(), 'id': e['id'], 'patient': s['person']['identifier'], 'code': e['terminology']['value'], 'system': e['terminology'].get('namespace'), 'display': e['terminology']['label'], 'status': e['state'].lower(), 'effective': e['clinicalDate'], 'recorded': e['documentation'].get('timestamp'), 'author': e['documentation'].get('by'), 'note': e.get('comment', '')}
        reverse = {v: k for k, v in self.field_map.items()}
        d.update({reverse[k]: v for k, v in e['details'].items() if k in reverse})
        count = e['details'].get('administrationsPerDay')
        if count is not None:
            d['frequency'] = {1: 'QD', 2: 'BID', 3: 'TID', 4: 'QID'}.get(count, str(count) + ' times daily')
        warnings = unknown_keys(s, {'clinicalType', 'person', 'entry'}) + unknown_keys(e, {'id', 'terminology', 'state', 'clinicalDate', 'documentation', 'details', 'comment'}, 'entry.') + unknown_keys(e['details'], set(reverse) | {'administrationsPerDay'}, 'entry.details.') + unknown_keys(e['terminology'], {'value', 'namespace', 'label'}, 'entry.terminology.') + unknown_keys(e['documentation'], {'timestamp', 'by'}, 'entry.documentation.') + unknown_keys(s['person'], {'identifier'}, 'person.')
        return d, warnings

    def pack(self, d):
        supported = CATEGORY_FIELDS[d['kind']]
        details = {dest: d[src] for src, dest in self.field_map.items() if src in supported and d.get(src) is not None}
        if d['kind'] == 'medication' and d.get('frequency', '').upper() in FREQUENCIES:
            details.pop('scheduleText', None)
            details['administrationsPerDay'] = FREQUENCIES[d['frequency'].upper()]
        return {'clinicalType': d['kind'].upper(), 'person': {'identifier': d['patient']}, 'entry': {'id': d['id'], 'terminology': {'value': d['code'], 'namespace': d.get('system') or DEMO_SYSTEM, 'label': d['display']}, 'state': d.get('status', 'active').upper(), 'clinicalDate': datetime.fromisoformat(date_iso(d['effective'])).strftime('%m/%d/%Y') if len(date_iso(d['effective'])) == 10 else date_iso(d['effective']), 'documentation': {'timestamp': d.get('recorded'), 'by': d.get('author')}, 'details': details, 'comment': d.get('note', '')}}


ADAPTERS = {'northstar': EpicMockAdapter(), 'riverside': OracleMockAdapter()}


def clinical_fields(r):
    """Clinician-readable comparison that excludes transport metadata."""
    if not r:
        return {}
    kind = REVERSE_KINDS[r['resourceType']]
    code = code_concept(r)
    fields = {'Clinical concept': code['text'], 'Code': code['coding'][0]['code'], 'Coding system': code['coding'][0]['system']}
    if kind == 'medication':
        dose = r['dosage'][0]
        q = dose['doseAndRate'][0]['doseQuantity']
        fields.update({'Status': r['status'], 'Dose': q['value'], 'Unit': q['unit'], 'Frequency': dose.get('timing', {}).get('repeat', {}).get('frequency', dose.get('text')), 'Effective date': r['effectivePeriod']['start'], 'End date': r['effectivePeriod'].get('end')})
    elif kind in ('allergy', 'diagnosis'):
        fields.update({'Status': r.get('clinicalStatus', {}).get('coding', [{'code': 'entered-in-error'}])[0]['code'], 'Verification': r['verificationStatus']['coding'][0]['code'], 'Effective date': r['onsetDateTime']})
        if kind == 'allergy':
            reaction = r.get('reaction', [{}])[0]
            fields.update({'Reaction': reaction.get('manifestation', [{}])[0].get('text'), 'Severity': reaction.get('severity'), 'Criticality': r['criticality']})
        else:
            fields['End date'] = r.get('abatementDateTime')
    elif kind == 'lab':
        fields.update({'Status': r['status'], 'Result': r['valueQuantity']['value'], 'Unit': r['valueQuantity']['unit'], 'Effective date': r['effectiveDateTime']})
    elif kind == 'vaccination':
        if r['resourceType'] == 'ImmunizationRecommendation':
            rec = r['recommendation'][0]
            fields.update({'Status': 'planned', 'Effective date': rec['dateCriterion'][0]['value'], 'Dose number': rec.get('doseNumberPositiveInt'), 'Documentation': 'Planned; not administered'})
        else:
            fields.update({'Status': r['status'], 'Effective date': r['occurrenceDateTime'], 'Dose number': r.get('protocolApplied', [{}])[0].get('doseNumberPositiveInt'), 'Dose amount': r.get('doseQuantity', {}).get('value'), 'Dose unit': r.get('doseQuantity', {}).get('unit'), 'Route': r.get('route', {}).get('text'), 'Site': r.get('site', {}).get('text'), 'Lot number': r.get('lotNumber'), 'Administering provider': r.get('performer', [{'actor': {}}])[0]['actor'].get('display'), 'Documentation': 'Historical report' if not r.get('primarySource', True) else 'Administered', 'Reason not administered': r.get('statusReason', {}).get('text')})
    elif kind == 'note':
        fields.update({'Status': 'entered-in-error' if r['status'] == 'entered-in-error' else 'final', 'Document status': r['status'], 'Effective date': r['context']['period']['start'], 'Approved by': r['author'][0]['display'], 'Approved at': r['date']})
        fields.update({section.title(): text for section, text in note_sections(r).items()})
    fields['Notes'] = r.get('description', '') if kind == 'note' else r['recommendation'][0].get('description', '') if r['resourceType'] == 'ImmunizationRecommendation' else '\n'.join(n['text'] for n in r.get('note', []))
    return fields


def clinical_diff(before, after):
    a, b = clinical_fields(before), clinical_fields(after)
    return [{'field': k, 'before': a.get(k), 'after': b.get(k)} for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k)]
