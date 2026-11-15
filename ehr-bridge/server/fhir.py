"""A deliberately small FHIR R4 import: one Patient and one quantity Observation.

This validates the supported mapping, not every FHIR resource/profile/invariant.
No reference is fetched; the complete original Bundle is stored by the caller.
"""
from datetime import date, datetime
import math
import re
from urllib.parse import urlparse

from .adapters import GeneralVisit


def patient_name(patient):
    names = patient.get('name', [])
    name = next((n for n in names if n.get('use') == 'official'), names[0] if names else {})
    return ' '.join([*name.get('given', []), name.get('family', '')]).strip() or name.get('text', '')


def normalize_bundle(bundle, selected_patient):
    if bundle.get('resourceType') != 'Bundle' or bundle.get('type') != 'collection':
        raise ValueError('Use a FHIR R4 collection Bundle containing one Patient and one Observation')
    entries = bundle.get('entry', [])
    if len(entries) != 2 or sorted(e.get('resource', {}).get('resourceType', '') for e in entries) != ['Observation', 'Patient']:
        raise ValueError('This importer supports exactly one Patient and one Observation; no other resources are silently ignored')
    patient_entry = next(e for e in entries if e['resource']['resourceType'] == 'Patient')
    observation_entry = next(e for e in entries if e['resource']['resourceType'] == 'Observation')
    source_patient, observation = patient_entry['resource'], observation_entry['resource']
    for entry in entries:
        resource, uri = entry['resource'], entry.get('fullUrl', '')
        rid = resource.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9.-]{1,64}', rid) or urlparse(uri).scheme not in ('https', 'http') or not urlparse(uri).netloc:
            raise ValueError('Each resource requires an ID and an absolute source fullUrl')
        if not uri.endswith('/' + resource['resourceType'] + '/' + rid):
            raise ValueError('Resource IDs must match their source fullUrl')
    patient_uri = patient_entry['fullUrl']
    source_root = patient_uri.rsplit('/Patient/', 1)[0]
    if observation_entry['fullUrl'] != source_root + '/Observation/' + observation['id']:
        raise ValueError('Patient and Observation must come from the same source service')
    if observation.get('subject', {}).get('reference') not in (patient_uri, 'Patient/' + source_patient['id']):
        raise ValueError('The Observation subject does not match the included Patient')
    normalize_name = lambda name: ' '.join(name.split()).casefold()
    if normalize_name(patient_name(source_patient)) != normalize_name(selected_patient['name']) or source_patient.get('birthDate') != selected_patient['birth_date']:
        raise ValueError('FHIR patient name and date of birth must match the selected profile. Register the sandbox patient instead of using Sarah.')
    if observation.get('status') not in ('final', 'amended', 'corrected'):
        raise ValueError('This importer accepts final, amended, or corrected Observations only')
    quantity = observation.get('valueQuantity', {})
    value = quantity.get('value')
    choices = [key for key in observation if key.startswith('value')]
    if choices != ['valueQuantity'] or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('The supported Observation requires one numeric valueQuantity')
    if observation.get('component') or observation.get('hasMember') or 'dataAbsentReason' in observation:
        raise ValueError('Grouped/component/absent-value observations require a separate mapping; they cannot be flattened by this importer')
    comparator = quantity.get('comparator', '')
    if comparator not in ('', '<', '<=', '>=', '>'):
        raise ValueError('Unsupported quantity comparator')
    unit = quantity.get('unit') or quantity.get('code')
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError('A quantity unit is required; the importer does not guess units')
    effective = observation.get('effectiveDateTime', '')
    if not isinstance(effective, str) or len(effective) < 10:
        raise ValueError('An effectiveDateTime with a complete calendar date is required')
    visit_date = date.fromisoformat(effective[:10])
    if len(effective) > 10:
        parsed = datetime.fromisoformat(effective.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('FHIR observation timestamps must include a time zone')
    code = observation.get('code', {})
    label = code.get('text') or next((c.get('display') for c in code.get('coding', []) if c.get('display')), '')
    if not isinstance(label, str) or len(label.strip()) < 3:
        raise ValueError('The Observation requires a readable code label')
    notes = [n['text'] for n in observation.get('note', []) if n.get('text')]
    notes.append(f"Imported FHIR R4 observation; source status: {observation['status']}. Medication and allergy histories were not supplied.")
    canonical = GeneralVisit(
        patient_id=selected_patient['id'], visit_date=visit_date, reason=label,
        notes='\n'.join(notes), observations={label: f'{comparator}{value} {unit}'},
        additional={'FHIR R4 source': {
            'patient_reference': patient_uri, 'observation_reference': observation_entry['fullUrl'],
            'status': observation['status'], 'code': code, 'quantity': quantity,
            'effectiveDateTime': effective, 'referenceRange': observation.get('referenceRange', []),
            'interpretation': observation.get('interpretation', []), 'performer': observation.get('performer', []),
            'original_bundle_preserved': True,
        }},
    ).model_dump(mode='json')
    return canonical, patient_uri
