import base64,json,sqlite3
from datetime import datetime,timedelta,timezone
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.seed import DEMO_PASSWORD,populate
from server.adapters import make_native

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')

@pytest.fixture
def world(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app):
        clients={}
        for key,login in [('a','emily@bridge.demo'),('b','daniel@bridge.demo'),('patient','PT-DEMO-SARAH'),('other','jordan@bridge.demo')]:
            client=TestClient(app);r=client.post('/api/auth/login',json={'login':login,'password':DEMO_PASSWORD});assert r.status_code==200,r.text
            client.headers['x-csrf-token']=r.json()['csrf_token'];clients[key]=client
        yield app.state.db,clients
        for client in clients.values():client.close()

def request(c,images=True):
    r=c['a'].post('/api/hospital/requests',json={'patient_id':'PT-DEMO-SARAH','source_hospitals':['valley'],'purpose':'Review prior clinical records for continued care.','include_images':images});assert r.status_code==201,r.text;return r.json()
def code(c,r):
    result=c['patient'].post('/api/patient/requests/'+r['id']+'/code',json={'confirmed':True});assert result.status_code==200,result.text;return result.json()['code']
def upload_body(patient='PT-DEMO-SARAH',kind='oracle'):
    canonical={'patient_id':patient,'visit_date':'2026-11-15','reason':'Fictional imaging follow-up','notes':'Synthetic test only','medications':[],'allergies':[],'observations':{},'additional':{'blood_group':'A+'}}
    return {'patient_id':patient,'payload':make_native(kind,canonical,patient),'files':[{'name':'fictional-xray.png','mime':'image/png','base64':base64.b64encode(PNG).decode()}]}

def test_transfer_writes_real_destination_rows_in_destination_format(world):
    db,c=world
    with db.connect() as sql:outside=sql.execute("SELECT id FROM versions WHERE hospital_id='valley' LIMIT 1").fetchone()[0]
    assert c['a'].get('/api/versions/'+outside).status_code==404
    before=c['a'].get('/api/hospital/patients/PT-DEMO-SARAH').json()['records']
    assert all(r['source_hospital']=='memorial' for r in before)
    r=request(c);otp=code(c,r)
    assert c['other'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==404
    response=c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp});assert response.status_code==200,response.text
    assert response.json()['destination_format']=='epic' and response.json()['new_copies']==2
    with sqlite3.connect(db.directory/'memorial.sqlite3') as sql:
        rows=sql.execute('SELECT native_json,original_json,preserved_json FROM local_records WHERE imported=1').fetchall()
        assert len(rows)==2
        assert all('patientId' in json.loads(row[0]) and 'drugList' in json.loads(row[1]) for row in rows)
        assert json.loads(rows[0][2])['Blood group (fictional laboratory report)']=='A+'
    assert c['a'].get('/api/versions/'+outside).status_code==200
    assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==409

def test_images_are_authenticated_and_copied_as_bytes(world):
    db,c=world
    uploaded=c['b'].post('/api/hospital/visits',json=upload_body());assert uploaded.status_code==201,uploaded.text
    file_id=uploaded.json()['files'][0]['id']
    assert c['a'].get('/api/files/'+file_id).status_code==404
    assert c['patient'].get('/api/files/'+file_id).content==PNG
    r=request(c);otp=code(c,r);assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==200
    assert c['a'].get('/api/files/'+file_id).content==PNG
    with sqlite3.connect(db.directory/'memorial.sqlite3') as sql:assert sql.execute('SELECT content FROM local_files WHERE id=?',(file_id,)).fetchone()[0]==PNG

def test_image_scope_excludes_file_bytes_and_metadata(world):
    _,c=world;uploaded=c['b'].post('/api/hospital/visits',json=upload_body()).json();fid=uploaded['files'][0]['id'];r=request(c,False);otp=code(c,r)
    result=c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp});assert result.status_code==200 and result.json()['files_copied']==0
    assert c['a'].get('/api/files/'+fid).status_code==404
    imported=c['a'].get('/api/versions/'+uploaded['version_id']).json();assert imported['files']==[]

def test_patient_can_read_but_cannot_write_clinical_information(world):
    _,c=world
    for path,body in [('/api/hospital/visits',upload_body()),('/api/hospital/patients',{'name':'Other Patient','birth_date':'1990-01-01','fictional_data_confirmed':True}),('/api/hospital/requests',{'patient_id':'PT-DEMO-SARAH','source_hospitals':['memorial'],'purpose':'Forbidden request'})]:
        assert c['patient'].post(path,json=body).status_code==403
    assert c['patient'].get('/api/patient/home').status_code==200
    assert c['a'].get('/api/patient/home').status_code==403
    assert c['patient'].get('/api/hospital/patients/PT-DEMO-0002').status_code==403


def test_later_image_approval_adds_files_without_rewriting_the_existing_record(world):
    db,c=world
    uploaded=c['b'].post('/api/hospital/visits',json=upload_body()).json();vid=uploaded['version_id'];fid=uploaded['files'][0]['id']
    first=request(c,False);otp=code(c,first)
    assert c['a'].post('/api/hospital/requests/'+first['id']+'/transfer',json={'code':otp}).status_code==200
    assert c['a'].get('/api/versions/'+vid).json()['files']==[]
    second=request(c,True);otp=code(c,second)
    assert c['a'].post('/api/hospital/requests/'+second['id']+'/transfer',json={'code':otp}).status_code==200
    assert c['a'].get('/api/versions/'+vid).json()['files'][0]['id']==fid
    assert c['a'].get('/api/files/'+fid).content==PNG
    with sqlite3.connect(db.directory/'memorial.sqlite3') as sql:
        assert sql.execute('SELECT COUNT(*) FROM local_records WHERE version_id=?',(vid,)).fetchone()[0]==1
        assert json.loads(sql.execute('SELECT files_json FROM local_records WHERE version_id=?',(vid,)).fetchone()[0])==[]

def test_activation_requires_more_than_patient_id_and_is_single_use(world):
    db,c=world
    p=c['a'].post('/api/hospital/patients',json={'name':'Robin Harper','birth_date':'1991-04-03','phone':'555-0101','address':'12 Fictional Lane','fictional_data_confirmed':True}).json()
    client=TestClient(create_app(db.directory))
    try:
        wrong=client.post('/api/auth/activate',json={'patient_id':p['id'],'activation_code':'00000000','password':'Safe-demo-password-2026!'});assert wrong.status_code==400
        r=client.post('/api/auth/activate',json={'patient_id':p['id'],'activation_code':p['activation_code'],'password':'Safe-demo-password-2026!'});assert r.status_code==201,r.text
        client.headers['x-csrf-token']=r.json()['csrf_token'];assert client.get('/api/patient/home').json()['name']=='Robin Harper'
        assert c['a'].post('/api/hospital/patients/'+p['id']+'/activation').status_code==409
        assert client.post('/api/auth/activate',json={'patient_id':p['id'],'activation_code':p['activation_code'],'password':'Safe-demo-password-2026!'}).status_code==400
    finally:client.close()

def test_versions_preserve_doctor_hospital_date_and_old_content(world):
    db,c=world
    records=c['a'].get('/api/hospital/patients/PT-DEMO-SARAH').json()['records'];old=records[0]
    body={'patient_id':'PT-DEMO-SARAH','visit_id':old['visit_id'],'expected_version':old['version'],'payload':{**old['original'],'clinicalNotes':'An explicitly entered fictional correction.'}}
    result=c['other'].post('/api/hospital/visits',json=body);assert result.status_code==201,result.text
    latest=c['a'].get('/api/versions/'+result.json()['version_id']).json()
    assert latest['doctor_name']=='Dr. Jordan Lee' and latest['source_hospital']=='memorial' and latest['updated_at']
    assert c['a'].get('/api/versions/'+old['id']).json()['canonical']['notes']!=latest['canonical']['notes']
    assert c['a'].post('/api/hospital/visits',json=body).status_code==409
    with db.connect(write=True) as sql:
        with pytest.raises(sqlite3.IntegrityError):sql.execute('UPDATE versions SET doctor_name=? WHERE id=?',('Tamper',old['id']))

def test_code_attempts_expiration_and_denial(world):
    db,c=world;r=request(c);otp=code(c,r)
    for _ in range(5):assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':'000000'}).status_code==400
    assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==429
    otp=code(c,r)
    with db.connect(write=True) as sql:sql.execute('UPDATE requests SET code_expires=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),r['id']))
    assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==409
    assert c['patient'].get('/api/patient/home').json()['requests'][0]['state']=='CODE_EXPIRED'
    otp=code(c,r);assert c['patient'].post('/api/patient/requests/'+r['id']+'/deny').status_code==200
    assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==409

def test_transfer_snapshot_does_not_include_later_uploads(world):
    _,c=world;r=request(c);later=c['b'].post('/api/hospital/visits',json=upload_body()).json();otp=code(c,r)
    result=c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp});assert result.status_code==200 and result.json()['approved_versions']==2
    assert c['a'].get('/api/versions/'+later['version_id']).status_code==404

def test_failed_destination_write_rolls_back_code_and_central_transfer(world):
    db,c=world;r=request(c);otp=code(c,r)
    with sqlite3.connect(db.directory/'memorial.sqlite3') as sql:sql.execute("CREATE TRIGGER fail_transfer BEFORE INSERT ON local_records WHEN NEW.imported=1 BEGIN SELECT RAISE(ABORT,'test failure'); END")
    assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==503
    with db.connect() as sql:
        assert sql.execute('SELECT state FROM requests WHERE id=?',(r['id'],)).fetchone()[0]=='CODE_READY'
        assert sql.execute('SELECT COUNT(*) FROM transfers WHERE request_id=?',(r['id'],)).fetchone()[0]==0
    with sqlite3.connect(db.directory/'memorial.sqlite3') as sql:sql.execute('DROP TRIGGER fail_transfer')
    assert c['a'].post('/api/hospital/requests/'+r['id']+'/transfer',json={'code':otp}).status_code==200

def test_duplicate_review_wrong_patient_payload_and_invalid_files(world):
    _,c=world
    response=c['a'].post('/api/hospital/patients',json={'name':'Sarah Mitchell','birth_date':'1988-06-12','fictional_data_confirmed':True});assert response.status_code==409
    body=upload_body();body['payload']['personId']='PT-SOMEONE-ELSE';assert c['b'].post('/api/hospital/visits',json=body).status_code==422
    body=upload_body();body['files'][0]['base64']=base64.b64encode(b'<html>not a scan</html>').decode();assert c['b'].post('/api/hospital/visits',json=body).status_code==415

def test_seed_is_idempotent_and_can_add_demo_patients(world):
    db,_=world
    with db.connect() as c:before=c.execute('SELECT COUNT(*) FROM versions').fetchone()[0]
    populate(db,8)
    with db.connect() as c:assert c.execute('SELECT COUNT(*) FROM versions').fetchone()[0]==before
    populate(db,12)
    with db.connect() as c:assert c.execute('SELECT COUNT(*) FROM patients').fetchone()[0]==12

def test_upload_retry_is_idempotent_and_reusing_key_with_different_data_is_rejected(world):
    _,c=world;body=upload_body();body['idempotency_key']='demo-upload-retry-001'
    first=c['b'].post('/api/hospital/visits',json=body);second=c['b'].post('/api/hospital/visits',json=body)
    assert first.status_code==second.status_code==201 and first.json()['version_id']==second.json()['version_id']
    body['payload']['encounter']['note']='Changed after commit'
    assert c['b'].post('/api/hospital/visits',json=body).status_code==409
