from sqlalchemy import select

from .adapters import ADAPTERS, DEMO_SYSTEM
from .models import (CareRelationship, Hospital, HospitalMembership, IdentityCandidate, LinkMember, LocalPatient, LocalRecord, LocalTimelineEvent, LocalUser, PatientLink, User, now)
from .security import hash_password
from .services import ChangeDetectionService, SynchronizationService

SEED_DATE = '2026-11-12T09:00:00+00:00'


def source_payload(hospital, record_id, patient, kind, display, code, **fields):
    d = dict(kind=kind, id=record_id, patient=patient, display=display, code=code, system=DEMO_SYSTEM, effective='2026-11-01', recorded=SEED_DATE, author='Dr. Elena Park' if hospital == 'northstar' else 'Dr. Daniel Reed', status='active', note='Synthetic demonstration fixture.', **{})
    d.update(fields)
    return ADAPTERS[hospital].pack(d)


def seed(db):
    with db.shared() as s:
        initialized = bool(s.get(Hospital, 'northstar'))
    if initialized:
        ensure_workspace_features(db)
        return False
    with db.shared() as s:
        s.add_all([Hospital(id='northstar', name='Northstar Medical Center', ehr='Epic-inspired simulator'), Hospital(id='riverside', name='Riverside General Hospital', ehr='Oracle Health-inspired simulator')])
        s.flush()
        s.add_all([User(id='clinician-a', email='northstar@clinicalsync.demo', name='Dr. Elena Park', hospital_id='northstar', role='clinician', password_hash=hash_password(db.settings.demo_password)), User(id='clinician-b', email='riverside@clinicalsync.demo', name='Dr. Daniel Reed', hospital_id='riverside', role='clinician', password_hash=hash_password(db.settings.demo_password)), User(id='admin', email='admin@clinicalsync.demo', name='Alex Morgan', hospital_id='northstar', role='admin', password_hash=hash_password(db.settings.demo_password))])
        s.add_all([PatientLink(id='PAT-001', name='Maya Bennett', birth_date='1985-04-18'), PatientLink(id='PAT-002', name='Elise Carter', birth_date='1974-09-06'), PatientLink(id='PAT-900', name='Jordan Ellis', birth_date='1992-02-15')])
        s.flush()
        s.add_all([LinkMember(id='maya-ns', patient_id='PAT-001', hospital_id='northstar', local_patient_id='NS-1001', status='CONFIRMED', evidence='Reviewed synthetic master-patient-index fixture', reviewed_by='admin'), LinkMember(id='maya-rg', patient_id='PAT-001', hospital_id='riverside', local_patient_id='RG-8824', status='CONFIRMED', evidence='Reviewed synthetic master-patient-index fixture', reviewed_by='admin'), LinkMember(id='elise-ns', patient_id='PAT-002', hospital_id='northstar', local_patient_id='NS-2002', status='CONFIRMED', evidence='Local synthetic identity', reviewed_by='admin'), LinkMember(id='elise-rg-pending', patient_id='PAT-002', hospital_id='riverside', local_patient_id='RG-3309', status='PENDING_REVIEW', evidence='Similar demographics only; no automatic merge'), LinkMember(id='restricted-ns', patient_id='PAT-900', hospital_id='northstar', local_patient_id='NS-9000', status='CONFIRMED', evidence='Restricted synthetic fixture')])
        s.add_all([CareRelationship(hospital_id='northstar', local_patient_id='NS-1001', reason='Seeded synthetic care team'), CareRelationship(hospital_id='riverside', local_patient_id='RG-8824', reason='Seeded synthetic care team'), CareRelationship(hospital_id='northstar', local_patient_id='NS-2002', reason='Seeded synthetic care team'), CareRelationship(hospital_id='riverside', local_patient_id='RG-3309', reason='Local care only; shared identity pending')])
        s.flush()
        s.add(IdentityCandidate(id='MATCH-001', member_id='elise-rg-pending', evidence={'source_name': 'Elise C. Carter', 'target_name': 'Elise Carter', 'birth_date': '1974-09-06', 'method': 'Demographic similarity only', 'warning': 'Insufficient evidence for automatic linking. Administrator must review the synthetic identity evidence.'}))
    for hospital, patients in {'northstar': [('NS-1001', 'Maya Bennett', '1985-04-18'), ('NS-2002', 'Elise Carter', '1974-09-06'), ('NS-9000', 'Jordan Ellis', '1992-02-15')], 'riverside': [('RG-8824', 'Maya Bennett', '1985-04-18'), ('RG-3309', 'Elise C. Carter', '1974-09-06')]}.items():
        with db.local(hospital) as local:
            local.add(LocalUser(id='clinician-a' if hospital == 'northstar' else 'clinician-b', display_name='Dr. Elena Park' if hospital == 'northstar' else 'Dr. Daniel Reed'))
            for pid, name, dob in patients:
                local.add(LocalPatient(id=pid, name=name, birth_date=dob))
            local.flush()
            patient = 'NS-1001' if hospital == 'northstar' else 'RG-8824'
            rows = [('med-metformin', 'medication', 'Metformin', 'METFORMIN', {'dose': 500 if hospital == 'northstar' else 1000, 'unit': 'mg', 'frequency': 'BID'}), ('dx-diabetes' if hospital == 'northstar' else 'dx-hypertension', 'diagnosis', 'Type 2 diabetes mellitus' if hospital == 'northstar' else 'Essential hypertension', 'TYPE2_DIABETES' if hospital == 'northstar' else 'HYPERTENSION', {'verification': 'confirmed'}), ('lab-hba1c', 'lab', 'Hemoglobin A1c', 'HBA1C', {'value': 6.8 if hospital == 'northstar' else 7.1, 'unit': '%', 'effective': '2026-11-01T08:30:00+00:00' if hospital == 'northstar' else '2026-11-09T08:30:00+00:00', 'status': 'final', 'system': 'http://loinc.org', 'code': '4548-4'})]
            if hospital == 'northstar':
                rows.append(('allergy-penicillin', 'allergy', 'Penicillin allergy', 'PENICILLIN', {'reaction': 'Hives', 'severity': 'moderate', 'criticality': 'low', 'verification': 'confirmed'}))
            for record_id, kind, display, code, fields in rows:
                if 'code' in fields:
                    code = fields.pop('code')
                payload = source_payload(hospital, record_id, patient, kind, display, code, **fields)
                ChangeDetectionService.save(local, hospital, patient, kind, payload, 'Dr. Elena Park' if hospital == 'northstar' else 'Dr. Daniel Reed', record_id, timestamp=SEED_DATE)
            if hospital == 'riverside':
                payload = source_payload(hospital, 'pending-condition', 'RG-3309', 'diagnosis', 'Synthetic restricted condition', 'PENDING_DEMO', verification='confirmed')
                ChangeDetectionService.save(local, hospital, 'RG-3309', 'diagnosis', payload, 'Dr. Daniel Reed', 'pending-condition', timestamp=SEED_DATE)
    for h in ('northstar', 'riverside'):
        SynchronizationService(db).run(h)
    ensure_workspace_features(db)
    return True


def ensure_workspace_features(db):
    """Add new synthetic fixtures idempotently; never reset existing records or decisions."""
    with db.shared() as s:
        for hospital_id, definition in db.settings.extra_hospitals.items():
            if not s.get(Hospital, hospital_id):
                s.add(Hospital(id=hospital_id, name=definition['name'], ehr=definition['adapter'] + ' development adapter'))
        s.flush()
        if not s.get(User, 'network-clinician'):
            s.add(User(id='network-clinician', email='network@clinicalsync.demo', name='Dr. Avery Chen', hospital_id='northstar', role='clinician', password_hash=hash_password(db.settings.demo_password)))
            s.flush()
        for user in s.scalars(select(User)):
            hospitals = ['northstar', 'riverside'] if user.id in ('admin', 'network-clinician') else [user.hospital_id]
            for hospital in hospitals:
                if not s.scalar(select(HospitalMembership).where(HospitalMembership.user_id == user.id, HospitalMembership.hospital_id == hospital)):
                    s.add(HospitalMembership(user_id=user.id, hospital_id=hospital, role=user.role, active=True))
            for hospital_id, definition in db.settings.extra_hospitals.items():
                role = definition.get('memberships', {}).get(user.email)
                if role and not s.scalar(select(HospitalMembership).where(HospitalMembership.user_id == user.id, HospitalMembership.hospital_id == hospital_id)):
                    s.add(HospitalMembership(user_id=user.id, hospital_id=hospital_id, role=role, active=True))
        users = [(u.id, u.name) for u in s.scalars(select(User))]
    changed = []
    for hospital, patient_id in [('northstar', 'NS-1001'), ('riverside', 'RG-8824')]:
        with db.local(hospital) as local:
            for user_id, name in users:
                if not local.get(LocalUser, user_id):
                    local.add(LocalUser(id=user_id, display_name=name))
            for patient in local.scalars(select(LocalPatient)):
                if not patient.first_name:
                    names = patient.name.split(' ', 1)
                    patient.first_name, patient.last_name = names[0], names[-1]
                if not local.scalar(select(LocalTimelineEvent).where(LocalTimelineEvent.patient_id == patient.id, LocalTimelineEvent.event_type.in_(['PATIENT_REGISTERED', 'PATIENT_IMPORTED']))):
                    local.add(LocalTimelineEvent(patient_id=patient.id, event_type='PATIENT_IMPORTED', description='Existing synthetic hospital chart connected to this workspace', author='Synthetic fixture setup', occurred_at=patient.created_at))
            if not local.get(LocalRecord, 'vaccination-influenza'):
                payload = source_payload(hospital, 'vaccination-influenza', patient_id, 'vaccination', 'Influenza vaccination', 'INFLUENZA_DEMO', status='completed', effective='2026-10-20', dose_number=1, dose_amount=0.5, dose_unit='mL', route='Intramuscular', site='Left upper arm', lot_number='SYNTH-LOT-2026', provider='Synthetic vaccination clinic', historical=hospital == 'riverside', note='Synthetic historical vaccination fixture; two source reports may refer to the same administration.')
                ChangeDetectionService.save(local, hospital, patient_id, 'vaccination', payload, 'Synthetic vaccination clinic', 'vaccination-influenza', timestamp=SEED_DATE)
                changed.append(hospital)
            if hospital == 'northstar' and not local.get(LocalRecord, 'note-follow-up'):
                payload = source_payload(hospital, 'note-follow-up', patient_id, 'note', 'Follow-up consultation', 'SOAP_NOTE', status='current', sections={'subjective': 'Synthetic fixture: patient reports attending a scheduled follow-up.', 'objective': '', 'assessment': '', 'plan': 'Synthetic fixture: review the shared medication history with the care team.'}, approved_by='Dr. Elena Park', approved_at=SEED_DATE, note='Approved synthetic source-note fixture. This note was not generated from a recording.')
                ChangeDetectionService.save(local, hospital, patient_id, 'note', payload, 'Dr. Elena Park', 'note-follow-up', timestamp=SEED_DATE)
                changed.append(hospital)
            for record in list(local.scalars(select(LocalRecord).where(LocalRecord.category == 'note'))):
                if hospital == 'northstar' and 'clinicalNote' not in record.payload:
                    data, _ = ADAPTERS[hospital].unpack(record.payload)
                    ChangeDetectionService.save(local, hospital, record.patient_id, 'note', ADAPTERS[hospital].pack(data), record.author, record.id, record.version, 'CORRECTED')
                    changed.append(hospital)
    for hospital in sorted(set(changed)):
        SynchronizationService(db).run(hospital)


def simulate_allergy_update(db, author='Dr. Elena Park'):
    with db.local('northstar') as local:
        from .models import LocalRecord
        record = local.get(LocalRecord, 'allergy-penicillin')
        d, _ = ADAPTERS['northstar'].unpack(record.payload)
        d.update(reaction='Hives and facial swelling', severity='severe', criticality='high', note=f'Correction to synthetic allergy documentation. Source revision {record.version + 1}.', recorded=now(), author=author)
        payload = ADAPTERS['northstar'].pack(d)
        saved, _ = ChangeDetectionService.save(local, 'northstar', record.patient_id, 'allergy', payload, author, record.id, record.version, 'CORRECTED')
        version = saved.version
    return {'record_id': 'allergy-penicillin', 'version': version, 'sync': SynchronizationService(db).run('northstar')}
