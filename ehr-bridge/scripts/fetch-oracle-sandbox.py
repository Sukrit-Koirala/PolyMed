"""Download one public Oracle sandbox Patient + Observation; never writes to an EHR."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = 'https://fhir-open.cerner.com/r4/ec2458f2-1e24-41c8-b71b-0e701af7583d'
OUTPUT = Path(__file__).resolve().parents[1] / 'demo-reports' / 'oracle-sandbox'


def main():
    receipt = {'provider': 'Oracle Health public sandbox', 'fhir_version': '4.0.1',
               'fetched_at': datetime.now(timezone.utc).isoformat(),
               'documentation': 'https://docs.oracle.com/en/industries/health/millennium-platform-apis/mfrap/srv_root_url.html',
               'requests': [], 'scope': 'Public test records; GET only. No remote writes.'}
    with httpx.Client(headers={'Accept': 'application/fhir+json'}, timeout=25) as client:
        def get(path, params=None):
            response = client.get(BASE + path, params=params)
            response.raise_for_status()
            receipt['requests'].append({'url': str(response.url), 'status': response.status_code,
                                        'sha256_response_bytes': hashlib.sha256(response.content).hexdigest()})
            return response

        patient_response = get('/Patient/12742400')
        patient = patient_response.json()
        if patient.get('resourceType') != 'Patient':
            raise ValueError('Sandbox did not return a Patient')
        search = get('/Observation', {'patient': patient['id'], 'code': 'http://loinc.org|2823-3',
                                     'category': 'laboratory', '_count': 5}).json()
        candidates = [entry['resource'] for entry in search.get('entry', [])
                      if entry.get('resource', {}).get('resourceType') == 'Observation'
                      and entry['resource'].get('status') in ('final', 'amended', 'corrected')
                      and 'valueQuantity' in entry['resource']]
        if not candidates:
            raise ValueError('No supported potassium observation returned; no fixture files were replaced')
        observation_response = get('/Observation/' + candidates[0]['id'])
        observation = observation_response.json()
        if observation.get('resourceType') != 'Observation':
            raise ValueError('Sandbox did not return an Observation')

    names = patient.get('name', [])
    name = next((n for n in names if n.get('use') == 'official'), names[0] if names else {})
    full_name = ' '.join([*name.get('given', []), name.get('family', '')]).strip() or name.get('text', '')
    patient_uri = BASE + '/Patient/' + patient['id']
    if observation.get('subject', {}).get('reference') not in ('Patient/' + patient['id'], patient_uri):
        raise ValueError('Observation subject does not match the fetched patient')
    bundle = {'resourceType': 'Bundle', 'type': 'collection', 'timestamp': receipt['fetched_at'],
              'entry': [{'fullUrl': patient_uri, 'resource': patient},
                        {'fullUrl': BASE + '/Observation/' + observation['id'], 'resource': observation}]}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'patient.fhir.json').write_bytes(patient_response.content)
    (OUTPUT / 'observation.fhir.json').write_bytes(observation_response.content)
    for filename, data in [('upload-bundle.fhir.json', bundle), ('fetch-receipt.json', receipt)]:
        (OUTPUT / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (OUTPUT / 'PATIENT.txt').write_text(
        f'Oracle sandbox test patient\nName: {full_name}\nDate of birth: {patient["birthDate"]}\n'
        f'Source patient: {patient_uri}\n\n'
        'Register this test patient at Valley Medical and use the newly issued patient ID.\n'
        'Upload upload-bundle.fhir.json using Upload visit > FHIR R4.\n'
        'Confirm the source patient mapping. Do not upload it to Sarah.\n'
        'Activate the new patient account to demonstrate OTP sharing with Memorial.\n', encoding='utf-8')
    print(f'Saved official FHIR sandbox records to {OUTPUT}')
    print(f'Register: {full_name}; DOB {patient["birthDate"]}')
    print(f'Observation: {observation["id"]}; value {observation["valueQuantity"]}')


if __name__ == '__main__':
    try:
        main()
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise SystemExit(f'Sandbox download failed: {error}') from None
