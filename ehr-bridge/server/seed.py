"""Idempotent fictional hospital/patient dataset, also callable from the CLI."""
import os
from .db import HOSPITALS
from .core import hashed,now,expiry,append_visit,local_patient
from .adapters import make_native

DEMO_PASSWORD='Demo-access-2026!'


def populate(db,count=8):
    password=os.getenv('BRIDGE_DEMO_PASSWORD',DEMO_PASSWORD)
    with db.connect(write=True) as c:
        for hid,h in HOSPITALS.items():
            c.execute('INSERT OR IGNORE INTO hospitals VALUES(?,?,?)',(hid,h['name'],h['format']))
            if not c.execute('SELECT 1 FROM accounts WHERE login=?',(h['email'],)).fetchone():
                c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)',('doctor-'+hid,h['email'],h['doctor'],'hospital',hashed(password),hid,None))
        if not c.execute("SELECT 1 FROM accounts WHERE login='jordan@bridge.demo'").fetchone():
            c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)',('doctor-jordan','jordan@bridge.demo','Dr. Jordan Lee','hospital',hashed(password),'memorial',None))
        names=['Sarah Mitchell','David Kim','Amara Patel','Noah Bennett','Maya Flores','Ethan Brooks','Olivia Rivera','Liam Walker']
        for i in range(max(2,count)):
            pid='PT-DEMO-SARAH' if i==0 else f'PT-DEMO-{i+1:04d}'
            if c.execute('SELECT 1 FROM patients WHERE id=?',(pid,)).fetchone():continue
            name=names[i%len(names)]+(f' {i//len(names)+1}' if i>=len(names) else '')
            hid='memorial' if i%2==0 else 'valley'
            c.execute('INSERT INTO patients VALUES(?,?,?,?,?,?,?,?,?,?,0)',(pid,name,f'{1980+i%20}-06-12',f'(312) 555-{1400+i:04d}',f'patient{i+1}@example.test',f'{100+i} Fictional Lane, Chicago',hid,now(),None,None))
            if i==0:c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)',('patient-sarah',pid,name,'patient',hashed(password),None,pid))
    for i in range(max(2,count)):
        pid='PT-DEMO-SARAH' if i==0 else f'PT-DEMO-{i+1:04d}'
        for hid in ('memorial','valley') if i==0 else (('memorial' if i%2==0 else 'valley'),):
            with db.connect(hid,write=True) as c:
                p=c.execute('SELECT * FROM patients WHERE id=?',(pid,)).fetchone()
                local_patient(c,hid,p)
                if c.execute('SELECT 1 FROM visits WHERE patient_id=? AND hospital_id=?',(pid,hid)).fetchone():continue
                actor=dict(c.execute('SELECT * FROM accounts WHERE id=?',('doctor-'+hid,)).fetchone())
                canonical={'patient_id':pid,'visit_date':'2026-11-01','reason':'Fictional follow-up consultation','notes':'Synthetic demonstration visit. Review source information with the care team.','medications':[{'name':'Lisinopril','dose':'10','unit':'mg','frequency':'Once daily'}] if i==0 else [],'allergies':['Penicillin — rash'] if i==0 and hid=='memorial' else [],'observations':{'Blood pressure':'122/78 mmHg'} if hid=='memorial' else {},'additional':{'Blood group (fictional laboratory report)':'A+'} if i==0 and hid=='valley' else {}}
                native=make_native(HOSPITALS[hid]['format'],canonical,pid)
                result=append_visit(c,actor,pid,native)
                if i==0 and hid=='valley':
                    canonical['medications'][0]['dose']='20';canonical['notes']='Synthetic source update: documented medication dose revised. Both versions remain preserved.'
                    append_visit(c,actor,pid,make_native('oracle',canonical,pid),visit_id=result['visit_id'],expected=1)
    return {'hospitals':2,'patients_requested':max(2,count),'patient_login':'PT-DEMO-SARAH','hospital_logins':['emily@bridge.demo','daniel@bridge.demo','jordan@bridge.demo']}
