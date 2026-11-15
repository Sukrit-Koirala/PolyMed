"""One fictional, internally consistent story; idempotent and never resets data."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .models import Hospital, User, HospitalMembership, PatientLink, LinkMember, CareRelationship, LocalPatient, LocalUser, LocalRecord, now
from .bridge_models import *
from .adapters import ADAPTERS, DEMO_SYSTEM
from .security import hash_password
from .services import ChangeDetectionService, SynchronizationService

CATEGORIES = ['medication', 'allergy', 'diagnosis', 'lab', 'vaccination', 'note', 'blood_group', 'observations', 'history', 'imaging']


def seed_bridge(db):
    if not db.settings.bridge_enabled:
        return
    with db.shared() as s:
        for hid, name, vendor, adapter in [('memorial', 'Memorial Hospital', 'Epic', 'epic-mock'), ('valley', 'Valley Medical', 'Oracle Health', 'oracle-mock')]:
            if not s.get(Hospital, hid):
                s.add(Hospital(id=hid, name=name, ehr=vendor + '-inspired mock adapter'))
                s.flush()
            if not s.get(EHRConnection, hid):
                s.add(EHRConnection(id=hid, vendor=vendor, adapter=adapter, supported_categories=[c for c in CATEGORIES if c != 'blood_group' or hid == 'valley']))
        if not s.get(Hospital, 'patient-portal'):
            s.add(Hospital(id='patient-portal', name='Personal health workspace', ehr='Independent patient account'))
            s.flush()
        accounts = [('bridge-emily', 'emily@ehrbridge.demo', 'Dr. Emily Carter', 'memorial', 'clinician'), ('bridge-daniel', 'daniel@ehrbridge.demo', 'Dr. Daniel Reed', 'valley', 'clinician'), ('bridge-sarah', 'sarah@ehrbridge.demo', 'Sarah Mitchell', 'patient-portal', 'patient'), ('bridge-admin', 'admin@ehrbridge.demo', 'Memorial Administrator', 'memorial', 'admin')]
        for uid, email, name, hospital, role in accounts:
            if not s.get(User, uid):
                s.add(User(id=uid, email=email, name=name, hospital_id=hospital, role=role, password_hash=hash_password(db.settings.bridge_password)))
                s.flush()
                s.add(HospitalMembership(user_id=uid, hospital_id=hospital, role=role, active=True))
        s.flush()
        people = [('BR-SARAH', 'Sarah Mitchell', '1988-06-12', 'female'), ('BR-JAMES', 'James Wilson', '1972-02-24', 'male'), ('BR-ANA', 'Ana Lopez', '1995-09-08', 'female'), ('BR-ROBERT', 'Robert Chen', '1964-11-21', 'male'), ('BR-MARGARET', 'Margaret Collins', '1955-04-03', 'female')]
        for pid, name, birth, sex in people:
            if not s.get(PatientLink, pid):
                s.add(PatientLink(id=pid, name=name, birth_date=birth, synthetic=True))
                s.flush()
                s.add(BridgePatient(id=pid, portal_user_id='bridge-sarah' if pid == 'BR-SARAH' else None, demographics={'sex': sex, 'gender_identity': 'Not provided', 'phone': '(312) 555-0142' if pid == 'BR-SARAH' else 'Unknown', 'email': 'sarah@example.test' if pid == 'BR-SARAH' else 'Unknown', 'address': '104 Fictional Lane, Chicago, IL' if pid == 'BR-SARAH' else 'Unknown', 'emergency_contact': 'Alex Mitchell · (312) 555-0198' if pid == 'BR-SARAH' else 'Unknown', 'language': 'English', 'reported_blood_group': 'Unknown', 'insurance_provider': 'Demo Health', 'insurance_plan': 'Fictional PPO'}))
            for hid in ('memorial', 'valley') if pid == 'BR-SARAH' else ('memorial',):
                local_id = ('MH-' if hid == 'memorial' else 'VM-') + pid.removeprefix('BR-')
                if not s.scalar(select(LinkMember).where(LinkMember.hospital_id == hid, LinkMember.local_patient_id == local_id)):
                    s.add(LinkMember(patient_id=pid, hospital_id=hid, local_patient_id=local_id, status='CONFIRMED', evidence='Reviewed fictional identity fixture', reviewed_by='bridge-admin'))
                    s.add(CareRelationship(hospital_id=hid, local_patient_id=local_id, reason='Fictional local care team; cross-hospital content still requires patient grant'))
                with db.local(hid) as local:
                    if not local.get(LocalPatient, local_id):
                        local.add(LocalPatient(id=local_id, name=name, first_name=name.split()[0], last_name=name.split()[-1], birth_date=birth, administrative_gender=sex))
                    for account, _, person, _, _ in accounts:
                        if not local.get(LocalUser, account):
                            local.add(LocalUser(id=account, display_name=person))
    for hid in ('memorial', 'valley'):
        with db.local(hid) as local:
            patient = ('MH-' if hid == 'memorial' else 'VM-') + 'SARAH'
            author = 'Dr. Emily Carter' if hid == 'memorial' else 'Dr. Daniel Reed'
            entries = [('lisinopril', 'medication', 'Lisinopril', 'LISINOPRIL_DEMO', {'dose': 10, 'unit': 'mg', 'frequency': 'DAILY'})]
            if hid == 'memorial':
                entries += [('penicillin', 'allergy', 'Penicillin allergy', 'PENICILLIN_DEMO', {'reaction': 'Rash', 'severity': 'moderate', 'criticality': 'low', 'verification': 'confirmed'})]
            else:
                entries += [('influenza', 'vaccination', 'Influenza vaccination', 'INFLUENZA_DEMO', {'status': 'completed', 'effective': '2026-10-20', 'dose_number': 1, 'historical': False, 'provider': 'Valley vaccination clinic'}), ('cardiac-test', 'note', 'Prior cardiac testing', 'SOAP_NOTE', {'status': 'current', 'sections': {'subjective': '', 'objective': 'Fictional echocardiogram report from the previous visit is available for review.', 'assessment': '', 'plan': ''}, 'approved_by': author, 'approved_at': '2026-10-15T14:00:00Z'})]
            for key, category, display, code, fields in entries:
                rid = hid + '-sarah-' + key
                if local.get(LocalRecord, rid):
                    continue
                data = {'id': rid, 'patient': patient, 'kind': category, 'display': display, 'code': code, 'system': DEMO_SYSTEM, 'status': 'active', 'effective': '2026-10-01', 'recorded': '2026-10-15T14:00:00Z', 'author': author, 'note': 'Fictional hackathon source record.', **fields}
                record, _ = ChangeDetectionService.save(local, hid, patient, category, ADAPTERS[hid].pack(data), author, rid, timestamp='2026-10-15T14:00:00Z')
                if hid == 'valley' and key == 'lisinopril':
                    data['dose'], data['recorded'] = 20, '2026-11-01T09:00:00Z'
                    ChangeDetectionService.save(local, hid, patient, category, ADAPTERS[hid].pack(data), author, rid, 1, 'UPDATED', timestamp=data['recorded'])
        SynchronizationService(db).run(hid)
    with db.shared() as s:
        for rid, hid, category, display, fields, verification in [('bridge-blood-group', 'valley', 'blood_group', 'Blood group and Rh factor', {'Blood group': 'A', 'Rh factor': 'Positive', 'Result': 'A+', 'Specimen': 'Fictional laboratory sample'}, 'Verified laboratory value · synthetic fixture'), ('bridge-cardiac-imaging', 'valley', 'imaging', 'Echocardiogram report', {'Report': 'Fictional prior cardiac study. Full report preserved for clinician review.', 'Study date': '2026-10-15'}, 'Imported hospital information'), ('bridge-vitals', 'memorial', 'observations', 'Recorded observations', {'Height': '168 cm', 'Weight': '67 kg', 'Blood pressure': '122/78 mmHg', 'Heart rate': '74 bpm', 'Temperature': '36.7 °C', 'Oxygen saturation': '98%'}, 'Doctor-entered measured observations'), ('bridge-history', 'valley', 'history', 'Prior encounter', {'Encounter': 'Outpatient follow-up', 'Date': '2026-10-15', 'Surgeries': 'Not documented', 'Family history': 'Not documented'}, 'Imported hospital information')]:
            if not s.get(PreservedRecord, rid):
                record = PreservedRecord(id=rid, patient_id='BR-SARAH', hospital_id=hid, category=category, display=display, normalized={'resourceType': 'Observation' if category in ('blood_group', 'observations') else 'DiagnosticReport' if category == 'imaging' else 'Encounter', 'fields': fields}, original={'mockSource': hid, 'sourceId': rid, 'fields': fields}, verification=verification, author='Fictional ' + hid + ' source team', recorded_at='2026-10-15T14:00:00Z')
                s.add(record)
                s.flush()
                s.add(PreservedVersion(record_id=rid, version=1, snapshot={'normalized': record.normalized, 'original': record.original, 'verification': verification, 'author': record.author, 'recorded_at': record.recorded_at}))
        if not s.scalar(select(EncounterSession.id).where(EncounterSession.doctor_id == 'bridge-emily')):
            today = datetime.now(ZoneInfo('America/Chicago')).date()
            reasons = ['Medication review', 'Routine follow-up', 'Annual wellness', 'Review recent results', 'Follow-up consultation']
            for days in range(7, -1, -1):
                count = [5, 7, 4, 6, 8, 3, 5, 5][7-days]
                for index in range(count):
                    pid = people[index % len(people)][0]
                    timestamp = datetime.combine(today-timedelta(days=days), datetime.min.time(), tzinfo=ZoneInfo('America/Chicago')).replace(hour=9+index).astimezone(timezone.utc).isoformat()
                    if days == 0:
                        moment = datetime.now(ZoneInfo('America/Chicago'))
                        available = max(0.1, (moment-moment.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds())
                        timestamp = (moment-timedelta(seconds=min((count-index)*600, available*(count-index)/(count+1)))).astimezone(timezone.utc).isoformat()
                    status = 'COMPLETED' if days or index < 2 else ['ACTIVE', 'DRAFT', 'SCHEDULED'][index-2]
                    encounter = EncounterSession(patient_id=pid, hospital_id='memorial', doctor_id='bridge-emily', reason=reasons[index % 5], status=status, intake={'wizard_step': 0, 'reported': {}, 'missing': ['Recent outside records'] if pid == 'BR-SARAH' else ['Confirm current concerns']}, created_at=timestamp, updated_at=timestamp, completed_at=timestamp if status == 'COMPLETED' else None)
                    s.add(encounter)
                    s.flush()
                    s.add(EncounterVersion(encounter_id=encounter.id, revision=1, snapshot={'status': status, 'intake': encounter.intake, 'reason': encounter.reason}, author_id='bridge-emily'))
                    for kind, title in [('documentation', 'Review and complete documentation'), ('record_review', 'Review available source records'), ('insurance', 'Investigate service eligibility')]:
                        s.add(SessionTask(session_id=encounter.id, kind=kind, title=title, status='DONE' if status == 'COMPLETED' else 'TODO', updated_at=timestamp))
