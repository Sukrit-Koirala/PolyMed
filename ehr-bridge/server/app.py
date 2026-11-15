import base64
from collections import defaultdict,deque
from contextlib import asynccontextmanager
import hmac,json,os,secrets,sqlite3,time
from datetime import date
from urllib.parse import quote
from zoneinfo import ZoneInfo
from fastapi import FastAPI,Depends,HTTPException,Request,Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator
from .db import Database,HOSPITALS
from .core import *


class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Login(Strict):
    login:str=Field(min_length=2,max_length=180)
    password:str=Field(min_length=1,max_length=200)
class Enroll(Strict):
    patient_id:str=Field(min_length=4,max_length=80)
    activation_code:str=Field(min_length=6,max_length=30)
    password:str=Field(min_length=12,max_length=200)
class PatientInput(Strict):
    name:str=Field(min_length=2,max_length=120)
    birth_date:date
    phone:str=Field(default='Not provided',max_length=80)
    email:str=Field(default='Not provided',max_length=160)
    address:str=Field(default='Not provided',max_length=400)
    separate_patient_confirmed:bool=False
    fictional_data_confirmed:bool
    @field_validator('name')
    @classmethod
    def name_valid(cls,value):
        if len(value.strip())<2:raise ValueError('Enter a full name')
        return value.strip()
class Attachment(Strict):
    name:str=Field(min_length=1,max_length=200)
    mime:str=Field(max_length=80)
    base64:str=Field(max_length=7_000_000)
class Upload(Strict):
    patient_id:str=Field(max_length=80)
    payload:dict
    fhir_patient_confirmed:bool=False
    visit_id:str|None=Field(default=None,max_length=80)
    expected_version:int|None=Field(default=None,ge=1)
    files:list[Attachment]=Field(default_factory=list,max_length=4)
    retain_file_ids:list[str]|None=Field(default=None,max_length=10)
    idempotency_key:str|None=Field(default=None,max_length=80,pattern=r'^[a-zA-Z0-9-]+$')
class RequestInput(Strict):
    patient_id:str=Field(max_length=80)
    source_hospitals:list[str]=Field(min_length=1,max_length=2)
    purpose:str=Field(min_length=5,max_length=1000)
    include_images:bool=True
    @field_validator('purpose')
    @classmethod
    def purpose_valid(cls,value):
        if len(value.strip())<5:raise ValueError('Describe the purpose of the transfer')
        return value.strip()
class Consent(Strict):confirmed:bool
class Redeem(Strict):code:str=Field(pattern=r'^\d{6}$')


def create_app(directory=None,seed=True):
    db=Database(directory)
    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        if seed:
            from .seed import populate
            populate(db)
        yield
    app=FastAPI(title='EHR Bridge — patient-controlled exchange',lifespan=lifespan)
    app.state.db=db
    attempts=defaultdict(deque)
    origins={'http://127.0.0.1:3200','http://localhost:3200','http://testserver'}
    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Cache-Control':'no-store','Referrer-Policy':'same-origin'})
        return response
    @app.exception_handler(sqlite3.Error)
    async def database_error(request,exc):
        return JSONResponse(status_code=503,content={'detail':'The database operation did not commit. No partial transfer was accepted. Try again.'})
    def actor(request:Request):
        with db.connect() as c:
            row=c.execute('SELECT a.*,s.csrf FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires_at>?',(digest(request.cookies.get('ehr_bridge_session','')),now())).fetchone()
            if not row:raise HTTPException(401,'Sign in to your hospital or patient account')
            if request.method not in ('GET','HEAD','OPTIONS'):
                if request.headers.get('origin') and request.headers['origin'] not in origins:raise HTTPException(403,'Origin is not allowed')
                if not hmac.compare_digest(request.headers.get('x-csrf-token',''),row['csrf']):raise HTTPException(403,'Valid CSRF token required')
            return dict(row)
    def hospital(user=Depends(actor)):
        if user['role']!='hospital':raise HTTPException(403,'A hospital staff account is required; patients cannot update clinical data')
        return user
    def patient_account(user=Depends(actor)):
        if user['role']!='patient':raise HTTPException(403,'A patient account is required')
        return user
    def context(user):
        return {k:user[k] for k in ('id','name','role','hospital_id','patient_id')}|({'hospital':HOSPITALS[user['hospital_id']]} if user['hospital_id'] else {})
    def session_response(c,user,response):
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(token),user['id'],csrf,expiry(hours=8)))
        response.set_cookie('ehr_bridge_session',token,httponly=True,samesite='lax',secure=os.getenv('SECURE_COOKIE','false').lower()=='true',max_age=28800,path='/')
        return {'user':context(dict(user)),'csrf_token':csrf}
    def public_request(c,row):
        result=dict(row);result.pop('code_hash',None)
        result['source_hospitals']=json.loads(result.pop('sources_json'))
        result['version_count']=len(json.loads(result.pop('version_ids_json')))
        result['doctor_name']=c.execute('SELECT name FROM accounts WHERE id=?',(row['doctor_id'],)).fetchone()[0]
        result['hospital_name']=HOSPITALS[row['hospital_id']]['name']
        result['patient_name']=c.execute('SELECT name FROM patients WHERE id=?',(row['patient_id'],)).fetchone()[0]
        result['source_names']=[HOSPITALS[hid]['name'] for hid in result['source_hospitals']]
        if result['state'] in ('PENDING','CODE_READY'):
            if result['expires_at']<=now():result['state']='EXPIRED'
            elif result['code_expires'] and result['code_expires']<=now():result['state']='CODE_EXPIRED'
        result['attempts_remaining']=max(0,5-result['attempts'])
        return result
    def patient_summary(c,p,user):
        own=p['created_hospital']==user['hospital_id']
        local=c.execute('SELECT * FROM destination.local_patients WHERE patient_id=?',(p['id'],)).fetchone()
        sources=[{'id':r['hospital_id'],'name':HOSPITALS[r['hospital_id']]['name'],'version_count':r['n']} for r in c.execute('SELECT hospital_id,COUNT(*) n FROM versions WHERE patient_id=? GROUP BY hospital_id',(p['id'],))]
        data={key:p[key] for key in ('id','name','birth_date','created_at')}
        data.update({'local_id':local['local_id'] if local else None,'enrolled':bool(c.execute('SELECT 1 FROM accounts WHERE patient_id=?',(p['id'],)).fetchone()),'sources':sources,'created_here':own})
        if own or local:data.update({key:p[key] for key in ('phone','email','address')})
        return data
    @app.get('/api/health')
    def health():return {'status':'ok','demo':True,'live_ehr_connection':False}
    @app.post('/api/auth/login')
    def login(body:Login,request:Request,response:Response):
        if request.headers.get('origin') and request.headers['origin'] not in origins:raise HTTPException(403,'Origin not allowed')
        key=(request.client.host if request.client else 'local',body.login.casefold())
        while attempts[key] and attempts[key][0]<time.monotonic()-60:attempts[key].popleft()
        if len(attempts[key])>=10:raise HTTPException(429,'Too many sign-in attempts. Wait one minute.')
        attempts[key].append(time.monotonic())
        login_value=body.login.strip().upper() if body.login.upper().startswith('PT-') else body.login.strip().lower()
        with db.connect(write=True) as c:
            user=c.execute('SELECT * FROM accounts WHERE login=?',(login_value,)).fetchone()
            if not user or not verify(body.password,user['password_hash']):raise HTTPException(401,'Incorrect login or password')
            result=session_response(c,user,response);audit(c,dict(user),'SIGNED_IN',user['id'],user['patient_id']);return result
    @app.get('/api/auth/me')
    def me(user=Depends(actor)):return {'user':context(user),'csrf_token':user['csrf']}
    @app.post('/api/auth/logout')
    def logout(request:Request,response:Response,user=Depends(actor)):
        with db.connect(write=True) as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(digest(request.cookies.get('ehr_bridge_session','')),))
        response.delete_cookie('ehr_bridge_session',path='/');return {'signed_out':True}
    @app.post('/api/auth/activate',status_code=201)
    def activate(body:Enroll,request:Request,response:Response):
        if request.headers.get('origin') and request.headers['origin'] not in origins:raise HTTPException(403,'Origin not allowed')
        failure=None;result=None;patient_id=body.patient_id.strip().upper()
        with db.connect(write=True) as c:
            p=c.execute('SELECT * FROM patients WHERE id=?',(patient_id,)).fetchone()
            if not p or not p['activation_hash'] or p['activation_expires']<=now():failure=(400,'Patient ID or activation code is invalid, expired, or already used')
            elif p['activation_attempts']>=5:failure=(429,'Activation attempt limit reached. Ask the registering hospital for a new activation code.')
            elif not verify(body.activation_code,p['activation_hash']):
                c.execute('UPDATE patients SET activation_attempts=activation_attempts+1 WHERE id=?',(patient_id,));failure=(400,'Patient ID or activation code is invalid, expired, or already used')
            else:
                account=uid('account-');c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)',(account,patient_id,p['name'],'patient',hashed(body.password),None,patient_id))
                c.execute('UPDATE patients SET activation_hash=NULL WHERE id=?',(patient_id,))
                user=c.execute('SELECT * FROM accounts WHERE id=?',(account,)).fetchone();result=session_response(c,user,response);audit(c,dict(user),'PATIENT_ACCOUNT_ACTIVATED',patient_id,patient_id)
        if failure:return JSONResponse(status_code=failure[0],content={'detail':failure[1]})
        return result
    @app.get('/api/hospital/home')
    def hospital_home(user=Depends(hospital)):
        with db.connect(user['hospital_id']) as c:
            roster=[]
            for row in c.execute('SELECT p.* FROM patients p JOIN destination.local_patients l ON l.patient_id=p.id ORDER BY p.name'):
                summary=patient_summary(c,row,user)
                summary['version_count']=c.execute('SELECT COUNT(*) FROM destination.local_records WHERE patient_id=?',(row['id'],)).fetchone()[0]
                roster.append(summary)
            requests=[public_request(c,r) for r in c.execute('SELECT * FROM requests WHERE hospital_id=? AND doctor_id=? ORDER BY created_at DESC',(user['hospital_id'],user['id']))]
            return {'patients':roster,'requests':requests,'metrics':{'patients':len(roster),'uploaded_versions':c.execute('SELECT COUNT(*) FROM destination.local_records WHERE imported=0').fetchone()[0],'imported_versions':c.execute('SELECT COUNT(*) FROM destination.local_records WHERE imported=1').fetchone()[0]},'hospital':HOSPITALS[user['hospital_id']]}
    @app.get('/api/hospital/patients/{patient_id}')
    def lookup(patient_id:str,user=Depends(hospital)):
        with db.connect(user['hospital_id'],write=True) as c:
            p=c.execute('SELECT * FROM patients WHERE id=?',(patient_id.upper(),)).fetchone()
            if not p:raise HTTPException(404,'No patient with that ID. Register a new patient if appropriate.')
            audit(c,user,'PATIENT_ID_LOOKUP',p['id'],p['id'])
            records=[view_version(r,c) for r in c.execute('SELECT * FROM destination.local_records WHERE patient_id=? ORDER BY updated_at DESC,version DESC',(p['id'],))]
            return patient_summary(c,p,user)|{'records':records}
    @app.post('/api/hospital/patients',status_code=201)
    def register(body:PatientInput,user=Depends(hospital)):
        if not body.fictional_data_confirmed:raise HTTPException(422,'Use fictional demonstration information only')
        if body.birth_date>datetime.now(ZoneInfo('America/Chicago')).date() or body.birth_date.year<1900:raise HTTPException(422,'Enter a valid date of birth')
        with db.connect(user['hospital_id'],write=True) as c:
            # Only local-care identity matches are disclosed to this hospital.
            matches=[dict(r) for r in c.execute('SELECT p.id,p.name,p.birth_date FROM patients p JOIN destination.local_patients l ON l.patient_id=p.id WHERE lower(p.name)=? OR p.birth_date=?',(body.name.casefold(),body.birth_date.isoformat()))]
            if matches and not body.separate_patient_confirmed:raise HTTPException(409,{'message':'Review possible duplicates before creating a separate patient.','matches':matches})
            pid='PT-'+secrets.token_hex(8).upper();activation=str(secrets.randbelow(90000000)+10000000)
            c.execute('INSERT INTO patients VALUES(?,?,?,?,?,?,?,?,?,?,0)',(pid,body.name,body.birth_date.isoformat(),body.phone.strip() or 'Not provided',body.email.strip() or 'Not provided',body.address.strip() or 'Not provided',user['hospital_id'],now(),hashed(activation),expiry(hours=24)))
            p=c.execute('SELECT * FROM patients WHERE id=?',(pid,)).fetchone();local_patient(c,user['hospital_id'],p);audit(c,user,'PATIENT_REGISTERED',pid,pid)
            return patient_summary(c,p,user)|{'activation_code':activation,'activation_expires':p['activation_expires']}
    @app.post('/api/hospital/patients/{patient_id}/activation')
    def reissue_activation(patient_id:str,user=Depends(hospital)):
        with db.connect(write=True) as c:
            p=c.execute('SELECT * FROM patients WHERE id=? AND created_hospital=?',(patient_id,user['hospital_id'])).fetchone()
            if not p:raise HTTPException(404,'Only the registering hospital can reissue activation')
            if c.execute('SELECT 1 FROM accounts WHERE patient_id=?',(patient_id,)).fetchone():raise HTTPException(409,'The patient already has an account. Activation cannot reset an existing password.')
            code=str(secrets.randbelow(90000000)+10000000);until=expiry(hours=24)
            c.execute('UPDATE patients SET activation_hash=?,activation_expires=?,activation_attempts=0 WHERE id=?',(hashed(code),until,patient_id));audit(c,user,'ACTIVATION_REISSUED',patient_id,patient_id)
            return {'id':patient_id,'name':p['name'],'activation_code':code,'activation_expires':until}
    @app.post('/api/hospital/visits',status_code=201)
    async def upload(request:Request,user=Depends(hospital)):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>16*1024*1024:raise HTTPException(413,'Upload exceeds the 16 MiB request limit')
        try:body=Upload.model_validate_json(raw)
        except ValueError:raise HTTPException(422,'Upload requires patient_id, a native payload, and valid attachment fields') from None
        files=[file_payload(f.model_dump()) for f in body.files]
        with db.connect(user['hospital_id'],write=True) as c:
            receipt_id=user['id']+':'+body.idempotency_key if body.idempotency_key else None
            body_hash=digest(dump(body.model_dump()))
            if receipt_id:
                receipt=c.execute('SELECT * FROM upload_receipts WHERE id=?',(receipt_id,)).fetchone()
                if receipt:
                    if receipt['body_hash']!=body_hash:raise HTTPException(409,'This upload key was already committed with different content. Open a new update.')
                    return json.loads(receipt['result_json'])
            result=append_visit(c,user,body.patient_id,body.payload,files,body.visit_id,body.expected_version,body.retain_file_ids,body.fhir_patient_confirmed)
            if receipt_id:c.execute('INSERT INTO upload_receipts VALUES(?,?,?)',(receipt_id,body_hash,dump(result)))
            return result
    @app.get('/api/versions/{version_id}')
    def version(version_id:str,user=Depends(actor)):
        with db.connect(user['hospital_id']) as c:
            if user['role']=='hospital':row=c.execute('SELECT * FROM destination.local_records WHERE version_id=?',(version_id,)).fetchone()
            else:row=c.execute('SELECT * FROM versions WHERE id=? AND patient_id=?',(version_id,user['patient_id'])).fetchone()
            if not row:raise HTTPException(404,'This version is not in your authorized record set')
            return view_version(row,c if user['role']=='hospital' else None)
    @app.get('/api/files/{file_id}')
    def file(file_id:str,user=Depends(actor)):
        with db.connect(user['hospital_id']) as c:
            if user['role']=='hospital':row=c.execute('SELECT * FROM destination.local_files WHERE id=?',(file_id,)).fetchone()
            else:row=c.execute('SELECT * FROM files WHERE id=? AND patient_id=?',(file_id,user['patient_id'])).fetchone()
            if not row:raise HTTPException(404,'Attachment not found within your authorized records')
            disposition='attachment' if row['mime']=='application/pdf' else 'inline'
            # Read authorization is enforced against the hospital copy or patient's own file.
            return Response(bytes(row['content']),media_type=row['mime'],headers={'Content-Disposition':f"{disposition}; filename*=UTF-8''{quote(row['name'])}",'X-Content-SHA256':row['sha256']})
    @app.post('/api/hospital/requests',status_code=201)
    def request_records(body:RequestInput,user=Depends(hospital)):
        sources=sorted(set(body.source_hospitals))
        if any(h not in HOSPITALS or h==user['hospital_id'] for h in sources):raise HTTPException(422,'Choose other configured source hospitals')
        with db.connect(write=True) as c:
            if not c.execute('SELECT 1 FROM patients WHERE id=?',(body.patient_id,)).fetchone():raise HTTPException(404,'Patient not found')
            rows=list(c.execute('SELECT id FROM versions WHERE patient_id=? AND hospital_id IN ('+','.join('?' for _ in sources)+') ORDER BY updated_at',(body.patient_id,*sources)))
            if not rows:raise HTTPException(422,'The selected hospitals have no uploaded versions for this patient')
            rid=uid('req-');c.execute('INSERT INTO requests(id,patient_id,hospital_id,doctor_id,purpose,sources_json,version_ids_json,include_images,state,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(rid,body.patient_id,user['hospital_id'],user['id'],body.purpose,dump(sources),dump([r['id'] for r in rows]),int(body.include_images),'PENDING',now(),expiry(hours=24)))
            audit(c,user,'TRANSFER_REQUESTED',rid,body.patient_id)
            return public_request(c,c.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone())
    @app.post('/api/patient/requests/{request_id}/code')
    def generate_code(request_id:str,body:Consent,user=Depends(patient_account)):
        if not body.confirmed:raise HTTPException(422,'Confirm the displayed hospital, snapshot, and image scope')
        with db.connect(write=True) as c:
            row=c.execute('SELECT * FROM requests WHERE id=? AND patient_id=?',(request_id,user['patient_id'])).fetchone()
            if not row:raise HTTPException(404,'Request not found')
            if row['state'] not in ('PENDING','CODE_READY') or row['expires_at']<=now():raise HTTPException(409,'This request is completed, denied, or expired')
            code=str(secrets.randbelow(900000)+100000);until=expiry(minutes=5)
            c.execute("UPDATE requests SET state='CODE_READY',code_hash=?,code_expires=?,attempts=0 WHERE id=?",(hashed(code),until,request_id));audit(c,user,'TRANSFER_CODE_GENERATED',request_id,user['patient_id'])
            return {'code':code,'expires_at':until,'request_id':request_id,'hospital_name':HOSPITALS[row['hospital_id']]['name'],'version_count':len(json.loads(row['version_ids_json']))}
    @app.post('/api/patient/requests/{request_id}/deny')
    def deny(request_id:str,user=Depends(patient_account)):
        with db.connect(write=True) as c:
            row=c.execute('SELECT * FROM requests WHERE id=? AND patient_id=?',(request_id,user['patient_id'])).fetchone()
            if not row:raise HTTPException(404,'Request not found')
            if row['state']=='COMPLETED':raise HTTPException(409,'A completed transfer cannot be recalled from the hospital database')
            c.execute("UPDATE requests SET state='DENIED',code_hash=NULL WHERE id=?",(request_id,));audit(c,user,'TRANSFER_DENIED',request_id,user['patient_id']);return {'state':'DENIED'}
    @app.post('/api/hospital/requests/{request_id}/transfer')
    def transfer(request_id:str,body:Redeem,user=Depends(hospital)):
        failure=None;result=None
        with db.connect(user['hospital_id'],write=True) as c:
            r=c.execute('SELECT * FROM requests WHERE id=? AND doctor_id=? AND hospital_id=?',(request_id,user['id'],user['hospital_id'])).fetchone()
            if not r:raise HTTPException(404,'Only the requesting doctor and hospital can redeem this request')
            if r['state']!='CODE_READY' or r['expires_at']<=now() or not r['code_hash'] or r['code_expires']<=now():failure=(409,'Code is missing, expired, denied, or already used. Ask the patient for a new code or request.')
            elif r['attempts']>=5:failure=(429,'Five incorrect attempts. The patient must generate a new code.')
            elif not verify(body.code,r['code_hash']):
                c.execute('UPDATE requests SET attempts=attempts+1 WHERE id=?',(request_id,));audit(c,user,'TRANSFER_CODE_INVALID',request_id,r['patient_id']);failure=(400,'Invalid one-time code')
            else:
                p=c.execute('SELECT * FROM patients WHERE id=?',(r['patient_id'],)).fetchone();local_id=local_patient(c,user['hospital_id'],p)
                version_ids=json.loads(r['version_ids_json']);copied=0;files_copied=set();timestamp=now()
                for vid in version_ids:
                    v=c.execute('SELECT * FROM versions WHERE id=? AND patient_id=?',(vid,r['patient_id'])).fetchone()
                    if not v or v['hospital_id'] not in json.loads(r['sources_json']):raise HTTPException(409,'The approved snapshot is unavailable; nothing was transferred')
                    canonical=json.loads(v['canonical_json']);native,preserved=ADAPTERS[HOSPITALS[user['hospital_id']]['format']].represent(canonical,local_id)
                    native['_bridgeProvenance']={'central_patient_id':r['patient_id'],'source_hospital':v['hospital_id'],'source_version':v['version'],'source_version_id':vid,'doctor_id':v['doctor_id'],'doctor_name':v['doctor_name'],'updated_at':v['updated_at']}
                    files=json.loads(v['files_json']) if r['include_images'] else []
                    inserted=c.execute('INSERT OR IGNORE INTO destination.local_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(vid,v['visit_id'],v['version'],v['patient_id'],v['hospital_id'],v['doctor_id'],v['doctor_name'],v['updated_at'],v['native_json'],dump(native),v['canonical_json'],dump(preserved),dump(files),1,request_id,timestamp))
                    copied+=inserted.rowcount
                    for info in files:
                        f=c.execute('SELECT * FROM files WHERE id=? AND patient_id=?',(info['id'],r['patient_id'])).fetchone()
                        if not f:raise HTTPException(409,'An approved attachment is unavailable; nothing was transferred')
                        c.execute('INSERT OR IGNORE INTO destination.local_files VALUES(?,?,?,?,?,?)',(f['id'],f['patient_id'],f['name'],f['mime'],f['sha256'],f['content']))
                        c.execute('INSERT OR IGNORE INTO destination.local_record_files VALUES(?,?,?)',(vid,f['id'],dump(info)));files_copied.add(f['id'])
                c.execute("UPDATE requests SET state='COMPLETED',completed_at=?,code_hash=NULL WHERE id=?",(timestamp,request_id))
                tid=uid('transfer-');c.execute('INSERT INTO transfers VALUES(?,?,?,?,?,?,?,?)',(tid,request_id,r['patient_id'],user['hospital_id'],user['id'],len(version_ids),len(files_copied),timestamp));audit(c,user,'TRANSFER_COMMITTED',tid,r['patient_id'])
                result={'state':'COMPLETED','transfer_id':tid,'approved_versions':len(version_ids),'new_copies':copied,'files_copied':len(files_copied),'destination_format':HOSPITALS[user['hospital_id']]['format'],'local_patient_id':local_id,'notice':'Copies committed to the separate simulated hospital database. No live vendor API was called.'}
        if failure:return JSONResponse(status_code=failure[0],content={'detail':failure[1]})
        return result
    @app.get('/api/patient/home')
    def patient_home(user=Depends(patient_account)):
        with db.connect() as c:
            p=dict(c.execute('SELECT id,name,birth_date,phone,email,address,created_at FROM patients WHERE id=?',(user['patient_id'],)).fetchone())
            p['records']=[view_version(r) for r in c.execute('SELECT * FROM versions WHERE patient_id=? ORDER BY updated_at DESC,version DESC',(user['patient_id'],))]
            p['requests']=[public_request(c,r) for r in c.execute('SELECT * FROM requests WHERE patient_id=? ORDER BY created_at DESC',(user['patient_id'],))]
            p['history']=[dict(r) for r in c.execute('SELECT a.*,u.name actor_name FROM audit a JOIN accounts u ON u.id=a.actor_id WHERE a.patient_id=? ORDER BY a.id DESC LIMIT 100',(user['patient_id'],))]
            return p
    @app.get('/api/hospital/activity')
    def activity(user=Depends(hospital)):
        with db.connect() as c:return [dict(r) for r in c.execute('SELECT a.*,u.name actor_name FROM audit a JOIN accounts u ON u.id=a.actor_id WHERE a.hospital_id=? ORDER BY a.id DESC LIMIT 150',(user['hospital_id'],))]
    return app

app=create_app()
