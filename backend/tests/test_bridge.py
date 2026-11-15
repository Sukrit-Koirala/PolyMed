from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import CanonicalResource, LocalRecord, AuditEvent
from backend.app.bridge_models import AccessGrant, OneTimeCode, EncounterVersion, VoiceMemo, IntakeAnswer, BridgeRecordReview
from backend.app.security import verify_password


@pytest.fixture
def bridge(tmp_path):
    settings = Settings(shared_url=f'sqlite:///{tmp_path}/shared.db', hospital_a_url=f'sqlite:///{tmp_path}/a.db', hospital_b_url=f'sqlite:///{tmp_path}/b.db', bridge_enabled=True)
    app = create_app(settings)
    with TestClient(app):
        clients = {}
        for key, email in [('doctor', 'emily'), ('valley', 'daniel'), ('patient', 'sarah'), ('admin', 'admin')]:
            client = TestClient(app)
            context = client.post('/api/auth/login', json={'email': email+'@ehrbridge.demo', 'password': settings.bridge_password}).json()
            client.headers.update({'x-csrf-token': context['csrf_token'], 'x-workspace-id': context['user']['hospital_id']})
            clients[key] = client
        yield app, clients
        for client in clients.values():
            client.close()


def request_access(clients, categories=None):
    response = clients['doctor'].post('/api/bridge/requests', json={'patient_id': 'BR-SARAH', 'source_hospitals': ['valley'], 'categories': categories or ['medication', 'blood_group', 'imaging', 'history', 'note', 'vaccination'], 'purpose': 'Review patient-reported symptoms and prior cardiac testing.', 'encounter_reason': 'Fictional follow-up for reported chest discomfort', 'duration_hours': 4})
    assert response.status_code == 201, response.text
    return response.json()


def activate(clients, categories=None):
    request = request_access(clients, categories)
    approved = clients['patient'].post('/api/bridge/requests/'+request['id']+'/decision', json={'action': 'APPROVE'})
    assert approved.status_code == 200, approved.text
    code = approved.json()['code']
    response = clients['doctor'].post('/api/bridge/requests/'+request['id']+'/redeem', json={'code': code})
    assert response.status_code == 200, response.text
    return request, code


def test_complete_scoped_story_history_preservation_and_revocation(bridge):
    app, c = bridge
    before = c['doctor'].get('/api/bridge/patients/BR-SARAH').json()
    assert {r['hospital_id'] for r in before['records']} == {'memorial'}
    assert before['conflicts'] == []
    assert {s['id'] for s in before['sources']} == {'memorial', 'valley'}
    request, code = activate(c)
    after = c['doctor'].get('/api/bridge/patients/BR-SARAH').json()
    assert {'memorial', 'valley'} == {r['hospital_id'] for r in after['records']}
    assert any(x['category'] == 'MEDICATION_DOSE_DISCREPANCY' for x in after['conflicts'])
    blood = next(r for r in after['records'] if r['category'] == 'blood_group')
    assert blood['fields']['Result'] == 'A+' and 'not mapped' in blood['mapping']
    details = c['doctor'].get('/api/bridge/records/'+blood['id']).json()
    assert details['original']['fields']['Result'] == 'A+'
    assert details['destination']['fields'] == {} and details['destination']['preserved']['Result'] == 'A+'
    medication = next(r for r in after['records'] if r['category'] == 'medication' and r['hospital_id'] == 'valley')
    history = c['doctor'].get('/api/bridge/records/'+medication['id']).json()
    assert [v['fields']['Dose'] for v in history['versions']] == [20, 10]
    assert c['doctor'].post('/api/bridge/requests/'+request['id']+'/redeem', json={'code':code}).status_code == 409
    exchange = c['doctor'].get('/api/bridge/exchange').json()
    assert exchange['metrics']['preserved'] > 0 and all(e['delivery_result'] == 'AVAILABLE_IN_WORKSPACE' for e in exchange['events'])
    assert c['patient'].post('/api/bridge/requests/'+request['id']+'/decision', json={'action':'REVOKE'}).status_code == 200
    assert c['doctor'].get('/api/bridge/records/'+medication['id']).status_code == 404
    assert all(r['hospital_id']=='memorial' for r in c['doctor'].get('/api/bridge/patients/BR-SARAH').json()['records'])
    with app.state.db.local('memorial') as local:
        assert not local.get(LocalRecord, 'valley-sarah-lisinopril')


def test_category_scope_is_checked_on_every_read_and_legacy_paths_are_closed(bridge):
    app,c=bridge
    with app.state.db.shared() as s:
        outside=s.scalar(select(CanonicalResource).where(CanonicalResource.hospital_id=='valley', CanonicalResource.resource_type=='DocumentReference'))
        rid=outside.id
    assert c['doctor'].get('/api/bridge/records/'+rid).status_code==404
    activate(c,['medication'])
    assert c['doctor'].get('/api/bridge/records/'+rid).status_code==404
    assert c['doctor'].get('/api/bridge/records/bridge-blood-group').status_code==404
    for path in ['/api/patients/BR-SARAH','/api/patients/BR-SARAH/timeline','/api/records/'+rid,'/api/identity/targets?q=Sarah','/api/local/patients/VM-SARAH','/api/charts/MH-SARAH']:
        assert c['doctor'].get(path).status_code==403,path
    records=c['doctor'].get('/api/bridge/patients/BR-SARAH').json()['records']
    assert {r['category'] for r in records if r['hospital_id']=='valley'}=={'medication'}


def test_patient_and_administrator_have_separate_permissions(bridge):
    _,c=bridge
    assert c['patient'].get('/api/bridge/patient-home').json()['name']=='Sarah Mitchell'
    assert c['patient'].get('/api/bridge/patients/BR-JAMES').status_code==404
    assert c['patient'].get('/api/bridge/dashboard').status_code==403
    assert c['admin'].get('/api/bridge/patients/BR-SARAH').status_code==403
    assert c['admin'].get('/api/bridge/sessions').status_code==403
    data=c['admin'].get('/api/bridge/admin').json()
    assert data['hospital']['id']=='memorial' and all(s['hospital_id']=='memorial' for s in data['staff'])
    assert 'records' not in data
    request=request_access(c)
    assert c['doctor'].post('/api/bridge/requests/'+request['id']+'/decision',json={'action':'APPROVE'}).status_code==403
    assert c['valley'].post('/api/bridge/requests/'+request['id']+'/redeem',json={'code':'123456'}).status_code==404
    app,_=bridge
    with TestClient(app) as legacy:
        auth=legacy.post('/api/auth/login',json={'email':'admin@clinicalsync.demo','password':app.state.settings.demo_password}).json()
        legacy.headers.update({'x-csrf-token':auth['csrf_token'],'x-workspace-id':'northstar'})
        assert legacy.get('/api/patients/BR-SARAH').status_code==404
        assert legacy.post('/api/identity/link-requests',json={'hospital_id':'memorial','local_patient_id':'MH-SARAH','target_patient_id':'PAT-001','evidence':'Cannot bypass Bridge scope through a legacy identity action.'}).status_code==403


def test_otp_hashing_expiration_single_use_and_attempt_limit(bridge):
    app,c=bridge
    request=request_access(c)
    approval=c['patient'].post('/api/bridge/requests/'+request['id']+'/decision',json={'action':'APPROVE'}).json()
    with app.state.db.shared() as s:
        code=s.scalar(select(OneTimeCode).where(OneTimeCode.request_id==request['id']))
        assert code.code_hash!=approval['code'] and verify_password(approval['code'],code.code_hash)
    wrong='000000'
    for _ in range(5):
        assert c['doctor'].post('/api/bridge/requests/'+request['id']+'/redeem',json={'code':wrong}).status_code==400
    assert c['doctor'].post('/api/bridge/requests/'+request['id']+'/redeem',json={'code':approval['code']}).status_code==429
    renewed=c['patient'].post('/api/bridge/requests/'+request['id']+'/decision',json={'action':'NEW_CODE'}).json()
    with app.state.db.shared() as s:
        code=s.scalar(select(OneTimeCode).where(OneTimeCode.request_id==request['id']))
        assert code.attempts==0
        code.expires_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    assert c['doctor'].post('/api/bridge/requests/'+request['id']+'/redeem',json={'code':renewed['code']}).status_code==409
    assert c['patient'].get('/api/bridge/requests').json()[0]['state']=='CODE_EXPIRED'


@pytest.mark.parametrize('decision,state',[('DENY','DENIED'),('INVESTIGATE','INVESTIGATING')])
def test_patient_denial_and_investigation_persist_without_content_access(bridge,decision,state):
    _,c=bridge
    request=request_access(c)
    response=c['patient'].post('/api/bridge/requests/'+request['id']+'/decision',json={'action':decision,'message':'Please explain the requested purpose.'})
    assert response.status_code==200 and response.json()['state']==state
    assert c['doctor'].get('/api/bridge/requests').json()[0]['state']==state
    assert all(r['hospital_id']=='memorial' for r in c['doctor'].get('/api/bridge/patients/BR-SARAH').json()['records'])


def test_expired_grant_stops_history_and_record_access(bridge):
    app,c=bridge
    request,_=activate(c)
    with app.state.db.shared() as s:
        grant=s.scalar(select(AccessGrant).where(AccessGrant.request_id==request['id']))
        grant.expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert c['doctor'].get('/api/bridge/records/bridge-blood-group').status_code==404
    assert c['doctor'].get('/api/bridge/requests').json()[0]['state']=='EXPIRED'


def test_sessions_tasks_intake_provenance_and_optimistic_history(bridge):
    app,c=bridge
    transcript='I have chest discomfort for three days and take lisinopril.'
    extracted=c['doctor'].post('/api/bridge/intake/extract',json={'transcript':transcript}).json()
    assert all(v['status']=='DRAFT' and v['source_quote'] in transcript for v in extracted['suggestions'])
    before=c['doctor'].get('/api/bridge/patients/BR-SARAH').json()['records']
    intake={'transcript':transcript,'transcript_source':'Manual synthetic test transcript','suggestions':[{**v,'status':'ACCEPTED'} for v in extracted['suggestions']], 'questions':[{'label':'Have symptoms occurred before?','kind':'yes_no','answer':'No'}]}
    body={'patient_id':'BR-SARAH','reason':'Reviewed synthetic follow-up','status':'DRAFT','intake':intake}
    response=c['doctor'].post('/api/bridge/sessions',json=body)
    assert response.status_code==201,response.text
    session=response.json()
    assert c['valley'].put('/api/bridge/tasks/'+session['tasks'][0]['id'],json={'status':'DONE'}).status_code==404
    assert c['doctor'].put('/api/bridge/sessions/'+session['id'],json=body|{'status':'COMPLETED','expected_revision':1}).status_code==409
    for task in session['tasks']:
        assert c['doctor'].put('/api/bridge/tasks/'+task['id'],json={'status':'DONE'}).status_code==200
    saved=c['doctor'].put('/api/bridge/sessions/'+session['id'],json=body|{'status':'ACTIVE','expected_revision':1}).json()
    assert saved['revision']==2
    assert c['doctor'].put('/api/bridge/sessions/'+session['id'],json=body|{'expected_revision':1}).status_code==409
    complete=c['doctor'].put('/api/bridge/sessions/'+session['id'],json=body|{'status':'COMPLETED','expected_revision':2})
    assert complete.status_code==200 and complete.json()['completed_at']
    assert len(complete.json()['versions'])==3
    after=c['doctor'].get('/api/bridge/patients/BR-SARAH').json()['records']
    assert before==after
    with app.state.db.shared() as s:
        assert s.scalar(select(func.count()).select_from(VoiceMemo).where(VoiceMemo.session_id==session['id']))==3
        assert s.scalar(select(func.count()).select_from(IntakeAnswer))>=3


def test_insurance_and_record_reviews_are_persisted_explicit_simulations(bridge):
    app,c=bridge
    session=c['doctor'].post('/api/bridge/sessions',json={'patient_id':'BR-SARAH','reason':'Fictional consultation'}).json()
    result=c['doctor'].post('/api/bridge/sessions/'+session['id']+'/insurance',json={'provider':'Demo Health','plan':'Fictional PPO','member_id':'TEST-1001'}).json()
    assert len(result['results'])==4 and 'not verified' in result['source']
    assert all('Simulated' in row['eligibility'] for row in result['results'])
    task=c['doctor'].post('/api/bridge/sessions/'+session['id']+'/tasks',json={'kind':'follow_up','title':'Confirm the fictional follow-up details'})
    assert task.status_code==201 and task.json()['status']=='TODO'
    assert c['valley'].post('/api/bridge/sessions/'+session['id']+'/tasks',json={'kind':'missing_info','title':'Unauthorized task'}).status_code==404
    record=c['doctor'].get('/api/bridge/patients/BR-SARAH').json()['records'][0]
    assert c['doctor'].post('/api/bridge/records/'+record['id']+'/reviews',json={'action':'FLAGGED','note':'Compare documented doses before review.'}).status_code==200
    history=c['doctor'].get('/api/bridge/records/'+record['id']).json()['review_history']
    assert history[0]['note']=='Compare documented doses before review.'


def test_admin_staff_control_is_organization_scoped_and_enforced_on_existing_sessions(bridge):
    _,c=bridge
    data=c['admin'].get('/api/bridge/admin').json()
    emily=next(s for s in data['staff'] if s['user_id']=='bridge-emily')
    assert c['admin'].put('/api/bridge/admin/staff/'+emily['id'],json={'active':False,'role':'clinician'}).status_code==200
    assert c['doctor'].get('/api/bridge/dashboard').status_code==403
    assert c['valley'].get('/api/bridge/dashboard').status_code==200
    assert c['admin'].put('/api/bridge/admin/connection',json={'status':'PAUSED','department':'Demo outpatient care'}).status_code==200
    assert c['admin'].get('/api/bridge/admin').json()['connection']['status']=='PAUSED'


def test_enabling_a_mock_mapping_preserves_source_and_respects_approved_scope(bridge):
    _,c=bridge
    activate(c,['blood_group'])
    before=c['doctor'].get('/api/bridge/records/bridge-blood-group').json()
    assert before['destination']['fields']=={}
    config=c['admin'].get('/api/bridge/admin').json()['connection']
    response=c['admin'].put('/api/bridge/admin/connection',json={'status':config['status'],'department':config['department'],'supported_categories':config['supported_categories']+['blood_group']})
    assert response.status_code==200
    after=c['doctor'].get('/api/bridge/records/bridge-blood-group').json()
    assert after['original']==before['original'] and after['versions']==before['versions']
    assert after['destination']['fields']['Result']=='A+'
    records=c['doctor'].get('/api/bridge/patients/BR-SARAH').json()['records']
    assert {r['category'] for r in records if r['hospital_id']=='valley'}=={'blood_group'}


def test_pending_patient_approval_task_cannot_be_bypassed_and_bad_intake_is_rejected(bridge):
    _,c=bridge
    request=request_access(c)
    body={'patient_id':'BR-SARAH','reason':'Fictional approval task','intake':{'access_request_id':request['id']}}
    session=c['doctor'].post('/api/bridge/sessions',json=body).json()
    task=next(t for t in session['tasks'] if t['kind']=='patient_approval')
    assert c['doctor'].put('/api/bridge/tasks/'+task['id'],json={'status':'DONE'}).status_code==409
    c['patient'].post('/api/bridge/requests/'+request['id']+'/decision',json={'action':'DENY'})
    assert c['doctor'].put('/api/bridge/tasks/'+task['id'],json={'status':'DONE'}).status_code==200
    assert c['doctor'].post('/api/bridge/sessions',json=body|{'intake':{'questions':'invalid'}}).status_code==422
    assert c['doctor'].post('/api/bridge/sessions',json=body|{'reason':'   '}).status_code==422
