import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.models import AuditEvent, User


@pytest.mark.parametrize('path', ['/api/patients', '/api/local/patients', '/api/reviews', '/api/sync', '/api/identity/candidates', '/api/audit'])
def test_unauthenticated_denied(app, path):
    assert TestClient(app).get(path).status_code == 401


def test_backend_hospital_and_care_boundaries(clients, clinical_body):
    a, b = clients['a'], clients['b']
    assert a.get('/api/local/patients/RG-8824').status_code == 404
    assert a.get('/api/local/patients/NS-9000').status_code == 404
    assert a.get('/api/patients/PAT-900').status_code == 404
    assert b.get('/api/patients/PAT-002').status_code == 404
    assert b.get('/api/records/northstar-pending-condition').status_code == 404
    assert a.post('/api/local/patients/RG-8824/records', json=clinical_body).status_code == 404
    assert a.get('/api/identity/candidates').status_code == 403
    assert a.get('/api/audit').status_code == 403
    assert all(p['id'] != 'PAT-900' for p in a.get('/api/patients').json())


def test_csrf_and_untrusted_origin_rejected(clients):
    client = clients['a']
    csrf = client.headers.pop('x-csrf-token')
    assert client.post('/api/sync').status_code == 403
    client.headers['x-csrf-token'] = csrf
    assert client.post('/api/sync', headers={'origin': 'https://attacker.invalid'}).status_code == 403


def test_cookies_passwords_and_logout(app, clients):
    client = TestClient(app)
    response = client.post('/api/auth/login', json={'email': 'northstar@clinicalsync.demo', 'password': app.state.settings.demo_password})
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    assert 'password_hash' not in response.json()['user']
    with app.state.db.shared() as s:
        assert s.get(User, 'clinician-a').password_hash.startswith('scrypt$')
    client.headers['x-csrf-token'] = response.json()['csrf_token']
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/patients').status_code == 401


def test_ambiguous_link_requires_manual_review_then_publishes(clients):
    b, admin = clients['b'], clients['admin']
    assert b.get('/api/patients/PAT-002').status_code == 404
    candidate = admin.get('/api/identity/candidates').json()[0]
    assert candidate['status'] == 'PENDING_REVIEW'
    decision = {'decision': 'CONFIRMED', 'note': 'Reviewed synthetic independent matching evidence'}
    assert b.post('/api/identity/candidates/MATCH-001/decision', json=decision).status_code == 403
    assert admin.post('/api/identity/candidates/MATCH-001/decision', json=decision).status_code == 200
    profile = b.get('/api/patients/PAT-002')
    assert profile.status_code == 200
    assert profile.json()['records'][0]['hospital_id'] == 'riverside'
    assert admin.post('/api/identity/candidates/MATCH-001/decision', json=decision).status_code == 409


def test_rejected_identity_remains_separate(clients):
    result = clients['admin'].post('/api/identity/candidates/MATCH-001/decision', json={'decision': 'REJECTED', 'note': 'Synthetic evidence insufficient to confirm'})
    assert result.status_code == 200
    assert clients['b'].get('/api/patients/PAT-002').status_code == 404
    assert clients['a'].get('/api/patients/PAT-002').json()['records'] == []


def test_protected_actions_audited(app, clients):
    clients['a'].get('/api/patients/PAT-001')
    clients['a'].post('/api/sync')
    with app.state.db.shared() as s:
        actions = set(s.scalars(select(AuditEvent.action)))
        assert {'LOGIN', 'READ_SHARED_PATIENT', 'TRIGGER_SYNC'} <= actions
    assert clients['admin'].get('/api/audit').status_code == 200


def test_reset_restricted_to_demo_admin_and_named_stores(app, clients):
    body = {'confirmation': 'RESET SYNTHETIC DEMO'}
    assert clients['a'].post('/api/demo/reset', json=body).status_code == 403
    app.state.settings.demo_mode = False
    assert clients['admin'].post('/api/demo/reset', json=body).status_code == 403
    app.state.settings.demo_mode = True
    saved = app.state.settings.shared_url
    app.state.settings.shared_url = 'sqlite:///unrelated.db'
    assert clients['admin'].post('/api/demo/reset', json=body).status_code == 403
    app.state.settings.shared_url = saved
    app.state.settings.shared_url = 'postgresql+psycopg://demo:demo@external.invalid/clinicalsync_shared'
    assert clients['admin'].post('/api/demo/reset', json=body).status_code == 403
    app.state.settings.shared_url = saved
    assert clients['admin'].post('/api/demo/reset', json=body).status_code == 200
    assert clients['a'].get('/api/auth/me').status_code == 401


def test_invalid_inputs_return_422(clients, clinical_body):
    assert clients['a'].post('/api/local/patients/NS-1001/records', json=clinical_body | {'dose': -1}).status_code == 422
    assert clients['a'].post('/api/local/patients/NS-1001/records', json=clinical_body | {'effective': 'yesterday'}).status_code == 422
    assert clients['a'].post('/api/local/patients/NS-1001/records', json=clinical_body | {'status': 'applied'}).status_code == 422


def test_denied_patient_access_is_audited(clients):
    assert clients['a'].get('/api/patients/PAT-900').status_code == 404
    events = clients['admin'].get('/api/audit').json()
    assert any(e['action'] == 'ACCESS_DENIED' and e['user_id'] == 'clinician-a' and e['target'] == 'GET /api/patients/PAT-900' for e in events)
