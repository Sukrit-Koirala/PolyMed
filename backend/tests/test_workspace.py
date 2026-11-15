import json

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.adapters import ADAPTERS, clinical_fields
from backend.app.config import Settings
from backend.app.documentation import LocalTranscriptOrganizer, OpenAINoteGenerationProvider, OpenAITranscriptionProvider
from backend.app.models import CanonicalResource, ClinicalEvent, LinkMember, LocalRecord, NoteDraft, OutboxEvent, ReviewItem
from backend.app.seed import source_payload


def signed_in(app, email):
    client = TestClient(app)
    response = client.post('/api/auth/login', json={'email': email + '@clinicalsync.demo', 'password': app.state.settings.demo_password})
    assert response.status_code == 200
    client.headers['x-csrf-token'] = response.json()['csrf_token']
    client.headers['x-workspace-id'] = response.json()['user']['hospital_id']
    return client


def registration(**changes):
    return {'first_name': 'Robin', 'last_name': 'Hale', 'birth_date': '1991-03-07', 'administrative_gender': 'unknown', 'synthetic_confirmed': True, **changes}


def register(client, **changes):
    body = registration(**changes)
    possible = client.post('/api/local/patients/check-matches', json=body)
    assert possible.status_code == 200
    response = client.post('/api/local/patients', json=body | {'match_token': possible.json()['match_token']})
    assert response.status_code == 201, response.text
    return response.json()


def test_workspace_switch_memberships_and_stale_context(app, clients):
    network = signed_in(app, 'network')
    assert len(network.get('/api/auth/me').json()['user']['memberships']) == 2
    assert network.get('/api/local/patients/NS-1001').status_code == 200
    response = network.post('/api/auth/workspace', json={'hospital_id': 'riverside'})
    assert response.status_code == 200
    assert response.json()['user']['hospital_id'] == 'riverside'
    assert network.get('/api/directory').status_code == 409
    network.headers['x-workspace-id'] = 'riverside'
    assert network.get('/api/charts/RG-8824').status_code == 200
    assert network.get('/api/charts/NS-1001').status_code == 404
    assert network.get('/api/auth/me').json()['user']['hospital_id'] == 'riverside'
    assert clients['a'].post('/api/auth/workspace', json={'hospital_id': 'riverside'}).status_code == 403
    assert network.post('/api/auth/workspace', json={'hospital_id': 'unconfigured'}).status_code == 403
    network.headers.pop('x-workspace-id')
    assert network.post('/api/sync').status_code == 409


def test_directory_distinguishes_local_and_multihospital(clients):
    data = clients['a'].get('/api/directory').json()
    assert {p['id'] for p in data['hospital_patients']} == {'NS-1001', 'NS-2002'}
    assert [p['id'] for p in data['shared_patients']] == ['NS-1001']
    assert data['shared_patients'][0]['connected_count'] == 2
    assert clients['a'].get('/api/overview').json()['linked_patient_count'] == 1
    assert clients['a'].get('/api/directory?q=NS-2002').json()['hospital_patients'][0]['name'] == 'Elise Carter'
    assert not clients['b'].get('/api/directory?q=NS-9000').json()['hospital_patients']


def test_registration_creates_local_chart_and_independent_timeline(clients):
    patient = register(clients['a'], local_patient_id='NS-NEW-1')
    assert patient['automatically_linked'] is False
    profile = clients['a'].get('/api/charts/NS-NEW-1').json()
    assert profile['records'] == [] and len(profile['members']) == 1
    assert clients['b'].get('/api/charts/NS-NEW-1').status_code == 404
    timeline = clients['a'].get('/api/charts/NS-NEW-1/timeline').json()
    assert len(timeline) == 1 and timeline[0]['event_type'] == 'PATIENT_REGISTERED'
    assert 'Maya' not in json.dumps(timeline)
    assert clients['a'].post('/api/local/patients', json=registration(local_patient_id='NS-NEW-1')).status_code == 409
    assert clients['a'].post('/api/local/patients', json=registration(birth_date='2099-01-01')).status_code == 422
    assert clients['a'].post('/api/local/patients', json=registration(synthetic_confirmed=False)).status_code == 422


def test_possible_duplicate_requires_explicit_review_never_autolinks(clients):
    body = registration(first_name='Maya', last_name='Bennett', birth_date='1985-04-18')
    check = clients['a'].post('/api/local/patients/check-matches', json=body).json()
    assert any(m['local_patient_id'] == 'NS-1001' for m in check['matches'])
    assert 'RG-8824' not in json.dumps(check)
    assert clients['a'].post('/api/local/patients', json=body).status_code == 409
    created = clients['a'].post('/api/local/patients', json=body | {'match_token': check['match_token']})
    assert created.status_code == 201
    assert created.json()['shared_patient_id'] != 'PAT-001'
    assert clients['b'].get('/api/patients/' + created.json()['shared_patient_id']).status_code == 404


def test_cross_workspace_match_suggestions_require_membership_and_care(app, clients):
    body = registration(first_name='Maya', last_name='Bennett', birth_date='1985-04-18')
    single = clients['a'].post('/api/local/patients/check-matches', json=body).json()
    assert not any(match.get('hospital_id') == 'riverside' for match in single['matches'])
    network = signed_in(app, 'network')
    authorized = network.post('/api/local/patients/check-matches', json=body).json()
    assert any(match.get('hospital_id') == 'riverside' and match['local_patient_id'] == 'RG-8824' for match in authorized['matches'])


@pytest.mark.parametrize('origin', ADAPTERS)
@pytest.mark.parametrize('destination', ADAPTERS)
@pytest.mark.parametrize('status,historical', [('completed', False), ('completed', True), ('not-done', False), ('planned', False)])
def test_vaccination_roundtrips_and_administration_semantics(origin, destination, status, historical):
    payload = source_payload(origin, 'vax-test', 'patient-test', 'vaccination', 'Synthetic vaccine', 'VACCINE_DEMO', status=status, historical=historical, dose_number=2, dose_amount=0.5, dose_unit='mL', route='Intramuscular', site='Left arm', lot_number='SYNTH-X', provider='Synthetic provider', status_reason='Recorded source reason', note='Source context')
    canonical = ADAPTERS[origin].to_canonical(payload)
    assert canonical.resource['resourceType'] == ('ImmunizationRecommendation' if status == 'planned' else 'Immunization')
    reverse = ADAPTERS[destination].from_canonical(canonical)
    roundtrip = ADAPTERS[destination].to_canonical(reverse)
    assert clinical_fields(canonical.resource) == clinical_fields(roundtrip.resource)
    if status == 'planned':
        assert 'status' not in canonical.resource and 'occurrenceDateTime' not in canonical.resource
    else:
        assert canonical.resource['primarySource'] is not historical
        assert canonical.resource['lotNumber'] == 'SYNTH-X'


@pytest.mark.parametrize('origin', ADAPTERS)
@pytest.mark.parametrize('destination', ADAPTERS)
def test_approved_note_document_roundtrip(origin, destination):
    sections = {'subjective': 'Source statement.', 'objective': '', 'assessment': '', 'plan': 'Documented follow-up.'}
    payload = source_payload(origin, 'note-test', 'p', 'note', 'Consultation', 'SOAP_NOTE', status='current', sections=sections, approved_by='Synthetic clinician', approved_at='2026-11-12T09:00:00+00:00')
    canonical = ADAPTERS[origin].to_canonical(payload)
    assert canonical.resource['resourceType'] == 'DocumentReference'
    reverse = ADAPTERS[destination].from_canonical(canonical)
    assert ADAPTERS[destination].unpack(reverse)[0]['sections'] == sections
    assert clinical_fields(canonical.resource) == clinical_fields(ADAPTERS[destination].to_canonical(reverse).resource)


def test_vaccination_publishes_reviews_history_and_idempotency(clients, app):
    body = {'category': 'vaccination', 'display': 'Synthetic vaccine B', 'code': 'VACCINE_B', 'status': 'completed', 'effective': '2026-11-01', 'dose_number': 1, 'dose_amount': 0.5, 'dose_unit': 'mL', 'historical': True, 'provider': 'Synthetic clinic'}
    created = clients['a'].post('/api/local/patients/NS-1001/records', json=body)
    assert created.status_code == 201
    rid = created.json()['id']
    assert clients['a'].post('/api/sync').json()[0]['published'] == 1
    incoming = next(item for item in clients['b'].get('/api/reviews').json() if item['event']['source_record_id'] == rid)
    assert incoming['event']['resource_type'] == 'Immunization'
    assert incoming['fields']['Documentation'] == 'Historical report'
    before = len(clients['b'].get('/api/reviews').json())
    clients['a'].post('/api/sync')
    assert len(clients['b'].get('/api/reviews').json()) == before
    assert clients['a'].post(f'/api/local/records/{rid}/withdraw', json={'expected_version': 1, 'note': 'Synthetic source correction'}).status_code == 200
    clients['a'].post('/api/sync')
    details = clients['a'].get(f'/api/records/northstar-{rid}').json()
    assert len(details['versions']) == 2 and details['status'] == 'WITHDRAWN'
    assert any(item['category'] == 'POSSIBLE_VACCINATION_DUPLICATE' for item in clients['a'].get('/api/patients/PAT-001/conflicts').json())


def test_vaccination_status_at_different_dates_is_not_a_conflicting_administration(clients):
    body = {'category': 'vaccination', 'display': 'Influenza vaccination', 'code': 'INFLUENZA_DEMO', 'status': 'not-done', 'effective': '2026-11-01', 'dose_number': 1, 'status_reason': 'Source documents a later declined visit'}
    created = clients['a'].post('/api/local/patients/NS-1001/records', json=body).json()
    clients['a'].post('/api/sync')
    conflicts = clients['a'].get('/api/patients/PAT-001/conflicts').json()
    assert not any(c['active'] and f"northstar-{created['id']}" in c['record_ids'] for c in conflicts)


def test_note_drafts_require_approval_and_do_not_mutate_structured_categories(clients, app):
    a, b = clients['a'], clients['b']
    before = a.get('/api/local/patients/NS-1001').json()['records']
    b_before = b.get('/api/local/patients/RG-8824').json()['records']
    created = a.post('/api/local/patients/NS-1001/note-drafts', json={'title': 'Synthetic consultation', 'transcript': 'Subjective: Reports a concern.\nPlan: Clinician documented follow-up.'})
    assert created.status_code == 201
    draft = created.json()
    assert draft['status'] == 'DRAFT'
    assert a.post('/api/sync').json()[0]['published'] == 0
    assert a.get('/api/local/patients/NS-1001').json()['records'] == before
    assert b.put('/api/note-drafts/' + draft['id'], json={'title': 'Wrong hospital', 'expected_revision': 1}).status_code == 404
    generated = a.post(f"/api/note-drafts/{draft['id']}/generate", json={'expected_revision': 1}).json()
    assert generated['sections']['objective'] == '' and generated['sections']['assessment'] == ''
    assert generated['sections']['plan'] == 'Clinician documented follow-up.'
    approved = a.post(f"/api/note-drafts/{draft['id']}/approve", json={'expected_revision': generated['revision'], 'approval_confirmed': True})
    assert approved.status_code == 200
    assert approved.json()['status'] == 'APPROVED'
    assert approved.json()['external_ehr_written'] is False
    after = a.get('/api/local/patients/NS-1001').json()['records']
    assert [r for r in after if r['category'] != 'note'] == [r for r in before if r['category'] != 'note']
    assert len(after) == len(before) + 1
    assert a.post(f"/api/note-drafts/{draft['id']}/approve", json={'expected_revision': generated['revision'], 'approval_confirmed': True}).json()['already_approved'] is True
    assert a.post('/api/sync').json()[0]['published'] == 1
    review = next(item for item in b.get('/api/reviews').json() if item['event']['source_record_id'] == approved.json()['local_record_id'])
    assert review['event']['resource_type'] == 'DocumentReference'
    assert b.post(f"/api/reviews/{review['id']}/decisions", json={'decision': 'ACCEPTED', 'note': 'Reviewed note', 'expected_revision': 1}).status_code == 200
    assert b.get('/api/local/patients/RG-8824').json()['records'] == b_before
    timeline = a.get('/api/charts/NS-1001/timeline').json()
    assert any(event['event_type'] == 'NOTE_APPROVED' for event in timeline)
    assert not any(event['event_type'] == 'NOTE_APPROVED' for event in a.get('/api/charts/NS-2002/timeline').json())
    audit = clients['admin'].get('/api/audit').json()
    assert any(event['action'] == 'CLINICAL_NOTE_APPROVED' for event in audit)


def test_note_draft_concurrency_privacy_and_empty_approval(app, clients):
    a = clients['a']
    draft = a.post('/api/local/patients/NS-1001/note-drafts', json={'title': 'Private draft'}).json()
    assert a.post(f"/api/note-drafts/{draft['id']}/approve", json={'expected_revision': 1, 'approval_confirmed': True}).status_code == 422
    update = {'title': 'Edited draft', 'transcript': 'Source text.', 'sections': {'subjective': 'Reviewed source text.'}, 'expected_revision': 1}
    assert a.put('/api/note-drafts/' + draft['id'], json=update).status_code == 200
    assert a.put('/api/note-drafts/' + draft['id'], json=update).status_code == 409
    network = signed_in(app, 'network')
    assert not network.get('/api/local/patients/NS-1001/note-drafts').json()
    assert network.put('/api/note-drafts/' + draft['id'], json=update).status_code == 403
    assert clients['admin'].post(f"/api/note-drafts/{draft['id']}/approve", json={'expected_revision': 2, 'approval_confirmed': True}).status_code == 403


def test_transcript_expiry_and_zero_retention(app, clients):
    a = clients['a']
    draft = a.post('/api/local/patients/NS-1001/note-drafts', json={'title': 'Retention test', 'transcript': 'A source transcript.'}).json()
    with app.state.db.local('northstar') as local:
        local.get(NoteDraft, draft['id']).transcript_expires_at = '2000-01-01T00:00:00+00:00'
    assert a.get('/api/local/patients/NS-1001/note-drafts').json()[0]['transcript'] is None
    app.state.settings.transcript_retention_days = 0
    zero = a.post('/api/local/patients/NS-1001/note-drafts', json={'title': 'Zero retention', 'transcript': 'Source kept in browser.'}).json()
    assert zero['transcript'] is None
    generated = a.post(f"/api/note-drafts/{zero['id']}/generate", json={'expected_revision': 1, 'transcript': 'Subjective: Supplied for this request.'})
    assert generated.status_code == 200 and generated.json()['transcript'] is None


def test_recording_fallback_and_consent_are_explicit(clients):
    a = clients['a']
    path = '/api/local/patients/NS-1001/transcriptions'
    assert a.post(path, content=b'audio', headers={'content-type': 'audio/webm'}).status_code == 403
    response = a.post(path, content=b'audio', headers={'content-type': 'audio/webm', 'x-recording-consent': 'true'})
    assert response.status_code == 503
    assert 'test transcript' in response.json()['detail']


def test_recording_consent_and_lifecycle_are_audited_without_audio(clients):
    from uuid import uuid4
    recording_id = str(uuid4())
    path = '/api/local/patients/NS-1001/recording-events'
    body = {'recording_id': recording_id, 'action': 'STARTED', 'consent_confirmed': True}
    assert clients['a'].post(path, json=body | {'consent_confirmed': False}).status_code == 422
    assert clients['a'].post(path, json=body | {'action': 'STOPPED'}).status_code == 409
    assert clients['a'].post(path, json=body).status_code == 200
    assert clients['a'].post(path, json=body | {'action': 'STOPPED'}).status_code == 200
    actions = [event['action'] for event in clients['admin'].get('/api/audit').json() if recording_id in event['target']]
    assert set(actions) == {'RECORDING_CONSENT_CONFIRMED', 'RECORDING_STARTED', 'RECORDING_STOPPED'}
    assert clients['b'].post(path, json=body).status_code == 404


def test_local_generator_preserves_missing_sections_and_unclassified_source():
    sections, warnings = LocalTranscriptOrganizer().generate('Only this source sentence was provided.')
    assert sections['objective'] == sections['assessment'] == sections['plan'] == ''
    assert 'Only this source sentence was provided.' in sections['subjective']
    assert 'no AI' in warnings[0]


def test_external_provider_extractive_grounding_and_audio_transport():
    settings = Settings(ai_external_enabled=True, ai_api_key='test-only-server-key')
    transcript = 'Patient reports a concern. Clinician documented follow-up.'
    def handler(request):
        assert request.headers['authorization'] == 'Bearer test-only-server-key'
        if request.url.path.endswith('/audio/transcriptions'):
            assert b'controlled-test-audio' in request.content
            return httpx.Response(200, json={'text': transcript})
        body = json.loads(request.content)
        assert body['response_format']['type'] == 'json_schema' and body['store'] is False
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'subjective': ['Patient reports a concern.'], 'objective': [], 'assessment': [], 'plan': ['Clinician documented follow-up.']})}}]})
    transport = httpx.MockTransport(handler)
    assert OpenAITranscriptionProvider(settings, transport).transcribe(b'controlled-test-audio', 'audio/webm') == transcript
    assert OpenAINoteGenerationProvider(settings, transport).generate(transcript)[0]['objective'] == ''
    bad = httpx.MockTransport(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'subjective': ['Invented unsupported diagnosis'], 'objective': [], 'assessment': [], 'plan': []})}}]}))
    with pytest.raises(HTTPException, match='grounded'):
        OpenAINoteGenerationProvider(settings, bad).generate(transcript)
    with pytest.raises(HTTPException):
        OpenAITranscriptionProvider(Settings(ai_api_key='test-only-server-key', ai_external_enabled=False))


def test_identity_link_request_requires_confirmation_and_rejection_preserves_identity(clients):
    patient = register(clients['b'], first_name='Elise', last_name='Carter', birth_date='1974-09-06')
    admin = clients['admin']
    request = admin.post('/api/identity/link-requests', json={'hospital_id': 'riverside', 'local_patient_id': patient['id'], 'target_patient_id': 'PAT-002', 'evidence': 'Synthetic independent identity evidence supplied for review.'})
    assert request.status_code == 201
    assert clients['b'].get('/api/charts/' + patient['id']).json()['shared_patient_id'] == patient['shared_patient_id']
    assert admin.post('/api/identity/candidates/' + request.json()['id'] + '/decision', json={'decision': 'REJECTED', 'note': 'Identity evidence insufficient.'}).status_code == 200
    assert clients['b'].get('/api/charts/' + patient['id']).json()['shared_patient_id'] == patient['shared_patient_id']
    second = admin.post('/api/identity/link-requests', json={'hospital_id': 'riverside', 'local_patient_id': patient['id'], 'target_patient_id': 'PAT-002', 'evidence': 'Re-reviewed independent synthetic evidence.'}).json()
    assert admin.post('/api/identity/candidates/' + second['id'] + '/decision', json={'decision': 'CONFIRMED', 'note': 'Explicitly confirmed from synthetic evidence.'}).status_code == 200
    assert clients['b'].get('/api/charts/' + patient['id']).json()['shared_patient_id'] == 'PAT-002'


def test_difference_reviews_are_hospital_specific_and_patient_scoped(clients):
    a, b = clients['a'], clients['b']
    issue = next(item for item in a.get('/api/charts/NS-1001').json()['conflicts'] if item['category'] == 'MEDICATION_DOSE_DISCREPANCY')
    response = a.post(f"/api/conflicts/{issue['id']}/reviews", json={'status': 'RESOLVED', 'note': 'Reviewed the source difference; source charts retained.', 'expected_revision': 0})
    assert response.status_code == 200 and response.json()['local_status'] == 'RESOLVED'
    other = next(item for item in b.get('/api/charts/RG-8824').json()['conflicts'] if item['id'] == issue['id'])
    assert other['local_status'] == 'NEEDS_REVIEW'
    assert any(event['event_type'] == 'DIFFERENCE_RESOLVED' for event in a.get('/api/charts/NS-1001/timeline').json())


def test_configured_third_workspace_uses_existing_engine_without_extra_frontend(tmp_path):
    from backend.app.main import create_app
    settings = Settings(shared_url=f'sqlite:///{tmp_path}/clinicalsync_shared.db', hospital_a_url=f'sqlite:///{tmp_path}/clinicalsync_northstar.db', hospital_b_url=f'sqlite:///{tmp_path}/clinicalsync_riverside.db', extra_hospitals={'harbor': {'name': 'Harbor Community Hospital', 'adapter': 'epic-mock', 'database_url': f'sqlite:///{tmp_path}/clinicalsync_harbor.db', 'memberships': {'network@clinicalsync.demo': 'clinician'}}})
    try:
        app = create_app(settings)
        with TestClient(app):
            client = signed_in(app, 'network')
            switched = client.post('/api/auth/workspace', json={'hospital_id': 'harbor'})
            assert switched.status_code == 200
            client.headers['x-workspace-id'] = 'harbor'
            assert not client.get('/api/directory').json()['hospital_patients']
            patient = register(client, local_patient_id='HC-1001')
            assert client.get('/api/charts/' + patient['id']).status_code == 200
            assert client.post('/api/local/patients/HC-1001/records', json={'category': 'diagnosis', 'display': 'Synthetic condition', 'code': 'DEMO', 'status': 'active', 'effective': '2026-11-01'}).status_code == 201
            assert client.post('/api/sync').json()[0]['published'] == 1
    finally:
        ADAPTERS.pop('harbor', None)
