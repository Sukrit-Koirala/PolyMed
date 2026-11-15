import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from .adapters import ADAPTERS, changes
from .db import HOSPITALS
from .fhir import normalize_bundle

def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def expiry(**kwargs):return (datetime.now(timezone.utc)+timedelta(**kwargs)).isoformat(timespec='microseconds')
def uid(prefix=''):return prefix+secrets.token_hex(12)
def dump(value):return json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))
def hashed(value):
    salt=secrets.token_hex(16)
    return salt+'$'+hashlib.scrypt(value.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def verify(value,stored):
    try:
        salt,expected=stored.split('$')
        return hmac.compare_digest(hashlib.scrypt(value.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex(),expected)
    except (ValueError,TypeError):return False
def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def audit(c,actor,action,target,patient=None):
    c.execute('INSERT INTO audit(actor_id,patient_id,hospital_id,action,target,created_at) VALUES(?,?,?,?,?,?)',(actor['id'],patient,actor.get('hospital_id'),action,target,now()))

def local_patient(c,hospital,patient):
    existing=c.execute('SELECT * FROM destination.local_patients WHERE patient_id=?',(patient['id'],)).fetchone()
    if existing:return existing['local_id']
    local_id=hospital[:3].upper()+'-'+secrets.token_hex(5).upper()
    c.execute('INSERT INTO destination.local_patients VALUES(?,?,?)',(patient['id'],patient['name'],local_id))
    return local_id

def file_payload(value):
    try:
        content=base64.b64decode(value['base64'],validate=True)
    except (ValueError,KeyError):raise HTTPException(422,'Invalid attachment encoding')
    if not 0<len(content)<=5*1024*1024:raise HTTPException(413,'Each attachment must be between 1 byte and 5 MiB')
    mime=value['mime']
    valid=(mime=='image/png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/jpeg' and content.startswith(b'\xff\xd8\xff')) or (mime=='image/webp' and content[:4]==b'RIFF' and content[8:12]==b'WEBP') or (mime=='application/pdf' and content.startswith(b'%PDF-'))
    if not valid:raise HTTPException(415,'File contents must match a supported PNG, JPEG, WebP, or PDF type')
    name=re.split(r'[/\\]',value['name'])[-1]
    name=''.join(ch for ch in name if ch.isprintable() and ch not in ('"',';'))[:160] or 'attachment'
    return {'id':uid('file-'),'name':name,'mime':mime,'content':content,'sha256':hashlib.sha256(content).hexdigest(),'size':len(content)}

def append_visit(c,actor,patient_id,native,new_files=None,visit_id=None,expected=None,retain=None,fhir_patient_confirmed=False):
    hospital=actor['hospital_id'];patient=c.execute('SELECT * FROM patients WHERE id=?',(patient_id,)).fetchone()
    if not patient:raise HTTPException(404,'Patient not found')
    if native.get('resourceType'):
        if not fhir_patient_confirmed:raise HTTPException(422,'Confirm the FHIR source patient mapping before importing')
        try:canonical,source_uri=normalize_bundle(native,patient)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        except (TypeError,KeyError,AttributeError,IndexError):raise HTTPException(422,'Invalid or unsupported FHIR R4 Patient/Observation bundle') from None
        link=c.execute('SELECT patient_id FROM external_patient_links WHERE source_uri=?',(source_uri,)).fetchone()
        if link and link['patient_id']!=patient_id:raise HTTPException(409,'This source patient is already linked to another patient profile')
        c.execute('INSERT OR IGNORE INTO external_patient_links VALUES(?,?)',(source_uri,patient_id))
    else:
        try:canonical=ADAPTERS[HOSPITALS[hospital]['format']].normalize(native,patient_id)
        except (ValueError,TypeError,KeyError,AttributeError):raise HTTPException(422,'Native payload does not match the selected patient or the hospital mock format') from None
    previous=None
    if visit_id:
        visit=c.execute('SELECT * FROM visits WHERE id=? AND hospital_id=? AND patient_id=?',(visit_id,hospital,patient_id)).fetchone()
        if not visit:raise HTTPException(404,'Only your hospital can update its own source visit')
        if expected!=visit['current_version']:raise HTTPException(409,'A newer version exists. Reload before saving.')
        previous=c.execute('SELECT * FROM versions WHERE visit_id=? ORDER BY version DESC LIMIT 1',(visit_id,)).fetchone()
        version=expected+1
        c.execute('UPDATE visits SET current_version=? WHERE id=? AND current_version=?',(version,visit_id,expected))
    else:
        if expected is not None:raise HTTPException(422,'New visits must not specify an expected version')
        visit_id=uid('visit-');version=1
        c.execute('INSERT INTO visits VALUES(?,?,?,1)',(visit_id,patient_id,hospital))
    existing=json.loads(previous['files_json']) if previous else []
    if retain is not None:
        if not set(retain)<={f['id'] for f in existing}:raise HTTPException(422,'Retained attachments must belong to the previous version')
        existing=[f for f in existing if f['id'] in retain]
    files=list(existing)
    new_files=new_files or []
    if sum(len(f['content']) for f in new_files)>10*1024*1024:raise HTTPException(413,'Combined new attachments exceed 10 MiB')
    for f in new_files:
        c.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',(f['id'],patient_id,hospital,f['name'],f['mime'],f['sha256'],f['content']))
        c.execute('INSERT INTO destination.local_files VALUES(?,?,?,?,?,?)',(f['id'],patient_id,f['name'],f['mime'],f['sha256'],f['content']))
        files.append({k:v for k,v in f.items() if k!='content'})
    if len(files)>10:raise HTTPException(422,'A visit version supports up to ten attachments')
    version_id=uid('ver-');updated=now()
    diff=changes(json.loads(previous['canonical_json']) if previous else {},canonical)
    diff+=changes({'attachments':[f['id'] for f in json.loads(previous['files_json'])] if previous else []},{'attachments':[f['id'] for f in files]})
    c.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(version_id,visit_id,version,patient_id,hospital,actor['id'],actor['name'],updated,dump(native),dump(canonical),dump(diff),dump(files)))
    local_id=local_patient(c,hospital,patient)
    c.execute('INSERT INTO destination.local_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(version_id,visit_id,version,patient_id,hospital,actor['id'],actor['name'],updated,dump(native),dump(native),dump(canonical),dump({}),dump(files),0,None,updated))
    audit(c,actor,'VISIT_VERSION_UPLOADED',version_id,patient_id)
    return {'visit_id':visit_id,'version_id':version_id,'version':version,'hospital_local_id':local_id,'files':files,'updated_at':updated}

def view_version(row,connection=None):
    result=dict(row)
    for key in ('native','original','canonical','changes','files','preserved'):
        if key+'_json' in result:result[key]=json.loads(result.pop(key+'_json'))
    result['hospital_name']=HOSPITALS[result.get('hospital_id',result.get('source_hospital'))]['name']
    original=result.get('original',result.get('native',{}))
    result['source_format']='FHIR R4' if original.get('resourceType')=='Bundle' else HOSPITALS[result.get('hospital_id',result.get('source_hospital'))]['format']
    result['id']=result.get('version_id',result.get('id'))
    if connection is not None and 'version_id' in result:
        files={f['id']:f for f in result['files']}
        for linked in connection.execute('SELECT metadata_json FROM destination.local_record_files WHERE version_id=?',(result['version_id'],)):
            info=json.loads(linked['metadata_json']);files[info['id']]=info
        result['files']=list(files.values())
    return result
