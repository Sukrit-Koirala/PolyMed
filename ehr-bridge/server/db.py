"""Independent central/hospital databases. Local atomic copies, no real EHR connection."""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
HOSPITALS = {
    'memorial': {'name': 'Memorial Hospital', 'format': 'epic', 'doctor': 'Dr. Emily Carter', 'email': 'emily@bridge.demo'},
    'valley': {'name': 'Valley Medical', 'format': 'oracle', 'doctor': 'Dr. Daniel Reed', 'email': 'daniel@bridge.demo'},
}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS hospitals(id TEXT PRIMARY KEY,name TEXT NOT NULL,format TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS patients(id TEXT PRIMARY KEY,name TEXT NOT NULL,birth_date TEXT NOT NULL,phone TEXT NOT NULL,email TEXT NOT NULL,address TEXT NOT NULL,created_hospital TEXT NOT NULL REFERENCES hospitals(id),created_at TEXT NOT NULL,activation_hash TEXT,activation_expires TEXT,activation_attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,login TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('hospital','patient')),password_hash TEXT NOT NULL,hospital_id TEXT REFERENCES hospitals(id),patient_id TEXT UNIQUE REFERENCES patients(id));
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES accounts(id),csrf TEXT NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS visits(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),hospital_id TEXT NOT NULL REFERENCES hospitals(id),current_version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,visit_id TEXT NOT NULL REFERENCES visits(id),version INTEGER NOT NULL,patient_id TEXT NOT NULL REFERENCES patients(id),hospital_id TEXT NOT NULL REFERENCES hospitals(id),doctor_id TEXT NOT NULL REFERENCES accounts(id),doctor_name TEXT NOT NULL,updated_at TEXT NOT NULL,native_json TEXT NOT NULL,canonical_json TEXT NOT NULL,changes_json TEXT NOT NULL,files_json TEXT NOT NULL,UNIQUE(visit_id,version));
CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),hospital_id TEXT NOT NULL REFERENCES hospitals(id),name TEXT NOT NULL,mime TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL REFERENCES patients(id),hospital_id TEXT NOT NULL REFERENCES hospitals(id),doctor_id TEXT NOT NULL REFERENCES accounts(id),purpose TEXT NOT NULL,sources_json TEXT NOT NULL,version_ids_json TEXT NOT NULL,include_images INTEGER NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,code_hash TEXT,code_expires TEXT,attempts INTEGER NOT NULL DEFAULT 0,completed_at TEXT);
CREATE TABLE IF NOT EXISTS transfers(id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL REFERENCES requests(id),patient_id TEXT NOT NULL REFERENCES patients(id),hospital_id TEXT NOT NULL REFERENCES hospitals(id),doctor_id TEXT NOT NULL REFERENCES accounts(id),version_count INTEGER NOT NULL,file_count INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS upload_receipts(id TEXT PRIMARY KEY,body_hash TEXT NOT NULL,result_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id TEXT NOT NULL,patient_id TEXT,hospital_id TEXT,action TEXT NOT NULL,target TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS versions_patient ON versions(patient_id);
CREATE INDEX IF NOT EXISTS requests_patient ON requests(patient_id,created_at);
CREATE INDEX IF NOT EXISTS requests_hospital ON requests(hospital_id,created_at);
'''
LOCAL_SCHEMA = '''
CREATE TABLE IF NOT EXISTS local_patients(patient_id TEXT PRIMARY KEY,name TEXT NOT NULL,local_id TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS local_records(version_id TEXT PRIMARY KEY,visit_id TEXT NOT NULL,version INTEGER NOT NULL,patient_id TEXT NOT NULL,source_hospital TEXT NOT NULL,doctor_id TEXT NOT NULL,doctor_name TEXT NOT NULL,updated_at TEXT NOT NULL,original_json TEXT NOT NULL,native_json TEXT NOT NULL,canonical_json TEXT NOT NULL,preserved_json TEXT NOT NULL,files_json TEXT NOT NULL,imported INTEGER NOT NULL,request_id TEXT,received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS local_files(id TEXT PRIMARY KEY,patient_id TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS local_record_files(version_id TEXT NOT NULL REFERENCES local_records(version_id),file_id TEXT NOT NULL REFERENCES local_files(id),metadata_json TEXT NOT NULL,PRIMARY KEY(version_id,file_id));
'''


class Database:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.getenv('BRIDGE_DATA_DIR', str(ROOT / '.data'))).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'central.sqlite3'

    @contextmanager
    def connect(self, hospital=None, write=False):
        if hospital is not None and hospital not in HOSPITALS:
            raise ValueError('Unknown configured hospital')
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA journal_mode=DELETE')
        if hospital:
            c.execute('ATTACH DATABASE ? AS destination', (str(self.directory / (hospital + '.sqlite3')),))
            c.execute('PRAGMA destination.journal_mode=DELETE')
        try:
            c.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def initialize(self):
        with sqlite3.connect(self.path) as c:
            c.executescript(SCHEMA)
            for table in ('versions', 'files', 'transfers', 'audit'):
                for action in ('UPDATE', 'DELETE'):
                    c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'History is append-only'); END")
        for hospital in HOSPITALS:
            with sqlite3.connect(self.directory / (hospital + '.sqlite3')) as c:
                c.executescript(LOCAL_SCHEMA)
                for table in ('local_records', 'local_files', 'local_record_files'):
                    for action in ('UPDATE', 'DELETE'):
                        c.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Hospital snapshots are append-only'); END")
