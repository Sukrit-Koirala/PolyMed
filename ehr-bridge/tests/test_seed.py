import hashlib
import json
from datetime import datetime

from server.db import Database
from server.seed import populate


def test_detailed_seed_has_complete_charts_historical_dates_and_readable_reports(tmp_path):
    db=Database(tmp_path);db.initialize();populate(db)
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM patients').fetchone()[0]==8
        assert c.execute('SELECT COUNT(*) FROM visits').fetchone()[0]==32
        assert c.execute('SELECT COUNT(*) FROM versions').fetchone()[0]==48
        assert c.execute('SELECT COUNT(*) FROM files').fetchone()[0]==16
        assert c.execute("SELECT COUNT(*) FROM accounts WHERE role='patient'").fetchone()[0]==4
        assert c.execute("SELECT COUNT(*) FROM requests WHERE state='PENDING'").fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM transfers').fetchone()[0]==0
        for row in c.execute('SELECT * FROM versions'):
            chart=json.loads(row['canonical_json'])
            assert len(chart['notes'])>900
            assert all(label in chart['notes'] for label in ('HISTORY OF PRESENT ILLNESS','REVIEW OF SYSTEMS','EXAMINATION','ASSESSMENT','DOCUMENTED PLAN'))
            assert len(chart['observations'])>=7
            assert chart['additional']['Family history'] and chart['additional']['Social history']
            assert datetime.fromisoformat(row['updated_at']).year in (2025,2026)
        for file in c.execute('SELECT * FROM files'):
            assert file['mime']=='application/pdf' and bytes(file['content']).startswith(b'%PDF-1.4')
            assert hashlib.sha256(file['content']).hexdigest()==file['sha256']
            assert b'SYNTHETIC HOSPITAL RECORD' in file['content']
        sarah=[json.loads(row[0]) for row in c.execute("SELECT canonical_json FROM versions WHERE patient_id='PT-DEMO-SARAH' AND hospital_id='memorial' ORDER BY updated_at DESC")]
        assert sarah[0]['observations']['Blood pressure']=='120/80 mmHg'
        assert len(sarah[0]['allergies'])==2
        assert c.execute("SELECT doctor_name FROM versions WHERE patient_id='PT-DEMO-SARAH' ORDER BY updated_at DESC LIMIT 1").fetchone()[0]=='Dr. Jordan Lee'
        for row in c.execute("SELECT canonical_json FROM versions WHERE patient_id='PT-DEMO-0008'"):
            chart=json.loads(row[0])
            if chart['visit_date']<'2026-10-24':
                assert chart['reason']=='Left forearm skin-lesion assessment'
                assert 'Procedure history' not in chart['additional']
                assert chart['medications']==[]
    for hid in ('memorial','valley'):
        with db.connect(hid) as c:
            assert c.execute('SELECT COUNT(*) FROM destination.local_records').fetchone()[0]==24
            assert c.execute('SELECT COUNT(*) FROM destination.local_files').fetchone()[0]==8
    populate(db)
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM versions').fetchone()[0]==48
        assert c.execute('SELECT COUNT(*) FROM files').fetchone()[0]==16
        assert c.execute('SELECT COUNT(*) FROM requests').fetchone()[0]==1


def test_historical_seed_timestamp_cannot_be_supplied_through_upload_api(tmp_path):
    from fastapi.testclient import TestClient
    from server.app import create_app
    from server.seed import DEMO_PASSWORD
    with TestClient(create_app(tmp_path)) as client:
        login=client.post('/api/auth/login',json={'login':'daniel@bridge.demo','password':DEMO_PASSWORD})
        client.headers['x-csrf-token']=login.json()['csrf_token']
        body={'patient_id':'PT-DEMO-SARAH','payload':{},'recorded_at':'2000-01-01T00:00:00+00:00'}
        assert client.post('/api/hospital/visits',json=body).status_code==422
