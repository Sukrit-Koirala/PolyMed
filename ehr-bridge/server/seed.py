"""Idempotent, detailed fictional hospital charts for local demonstrations."""
import base64
from copy import deepcopy
import os

from .adapters import make_native
from .core import append_visit, audit, dump, expiry, file_payload, hashed, now
from .db import HOSPITALS
from .demo_cases import CASES
from .demo_pdf import make_report

DEMO_PASSWORD = 'Demo-access-2026!'
SOURCE_PRESSURES = ['126/80 mmHg', '128/80 mmHg', '120/78 mmHg', '118/74 mmHg',
                    '114/74 mmHg', '120/76 mmHg', '116/74 mmHg', '124/78 mmHg']
FOLLOW_UP = {'baseline': '2025-05-20', 'middle': '2026-07-16', 'source': '2026-11-12', 'latest': '2026-11-26'}


def _notes(case, stage, addendum=False):
    history, exam, assessment, plan = case['history'], case['exam'], case['assessment'], case['plan']
    reason = case['condition']
    if case['name'] == 'Sarah Mitchell' and stage == 'baseline':
        history = 'Earlier review after elevated blood-pressure readings. The medication list supplied at this visit records lisinopril 10 mg daily. No chest pain, breathlessness, or focal neurologic symptoms are reported. A home monitoring record is discussed for the next scheduled review.'
    if case['name'] == 'Maya Flores' and stage == 'baseline':
        history = 'Earlier assessment for fatigue and a previously abnormal blood count. The outside report records hemoglobin 10.4 g/dL and ferritin 8 ng/mL. No active bleeding, chest pain, or syncope is reported. The treating service has arranged longitudinal follow-up.'
    if case['name'] == 'Liam Walker' and stage in ('baseline', 'middle'):
        reason = 'Left forearm skin-lesion assessment'
        history = 'Earlier assessment of a slowly enlarging superficial left forearm lump. The patient reports no drainage, surrounding redness, fever, or impaired hand movement. This visit precedes the later fictional excision.'
        exam = 'Small, well-circumscribed superficial left forearm lump with intact overlying skin. No drainage or surrounding erythema. Distal movement and sensation preserved.'
        assessment = ['Left forearm skin lesion under routine assessment', 'No procedure performed during this earlier visit']
        plan = ['Record the lesion appearance and patient-reported symptoms.', 'Document routine surgical assessment; no procedure was performed at this earlier visit.']
    heading = {'baseline': 'Earlier outside-hospital assessment', 'middle': 'Interval primary-care review',
               'source': 'Outside-hospital follow-up and report review', 'latest': 'Current continuity-of-care review'}[stage]
    text = '\n\n'.join([
        f'ENCOUNTER: {heading}. {case["department"]}.',
        f'CHIEF CONCERN: {reason}.',
        f'HISTORY OF PRESENT ILLNESS: {history}',
        'REVIEW OF SYSTEMS: ' + case['review'],
        'EXAMINATION: ' + exam,
        'ASSESSMENT:\n' + '\n'.join(f'{i + 1}. {item}.' for i, item in enumerate(assessment)),
        'DOCUMENTED PLAN:\n' + '\n'.join('- ' + item for item in plan),
        f'FOLLOW-UP: Routine review with the treating service is recorded for {FOLLOW_UP[stage]}. Outside records remain subject to patient-approved transfer.',
    ])
    if addendum:
        correction = 'Medication reconciliation addendum: the source list was corrected from lisinopril 10 mg to the patient-confirmed existing 20 mg regimen. This documents the existing prescription; it does not issue a new order.' if stage == 'source' and case['name'] == 'Sarah Mitchell' else 'Review addendum: the repeat observations and the complete patient-reported allergy list were verified and recorded. Earlier documentation is retained in its original version.'
        text += '\n\nADDENDUM: ' + correction
    return text + '\n\nSYNTHETIC TRAINING RECORD: Invented patient and clinical details. Not for clinical decisions.'


def _canonical(case, patient, stage, corrected=False):
    index = CASES.index(case)
    day = {'baseline': '2025-04-22', 'middle': '2026-06-18', 'source': '2026-10-28', 'latest': '2026-11-12'}[stage]
    pressure = case['old_pressure'] if stage == 'baseline' else case['middle_pressure'] if stage == 'middle' else SOURCE_PRESSURES[index]
    if stage == 'latest' and corrected:
        pressure = case['blood_pressure']
    observations = {
        'BP' if stage == 'baseline' else 'blood_pressure' if stage == 'source' else 'Blood pressure': pressure,
        'Heart rate': f'{case["heart_rate"] + (4 if stage == "baseline" else 0)} beats/min',
        'Respiratory rate': '16 breaths/min', 'Temperature': '36.7 C',
        'Oxygen saturation': '98 % on room air', 'Height': f'{case["height"]} cm',
        'Weight': f'{case["weight"] + (1.5 if stage == "baseline" else 0):.1f} kg',
    }
    if stage in ('baseline', 'source'):
        observations.update(case['labs'])
        if case['name'] == 'David Kim' and stage == 'baseline':
            observations.update({'Hemoglobin A1c': '7.6 %', 'Glucose': '146 mg/dL'})
        if case['name'] == 'Maya Flores' and stage == 'baseline':
            observations.update({'Hemoglobin': '10.4 g/dL', 'Mean corpuscular volume': '74 fL', 'Ferritin': '8 ng/mL'})
    medications = deepcopy(case['medications'])
    if 'previous_medications' in case and (stage in ('baseline', 'middle') or (stage == 'source' and not corrected)):
        medications = deepcopy(case['previous_medications'])
    if case['name'] == 'Liam Walker' and stage in ('baseline', 'middle'):
        medications = []
    allergies = list(case['allergies'])
    if len(allergies) > 1 and not (stage == 'latest' and corrected):
        allergies = allergies[:-1]
    extra = {
        'Blood group (fictional laboratory report)': case['blood_group'],
        'Past medical history': case['past_history'], 'Family history': case['family_history'],
        'Social history': case['social_history'], 'Assessment': case['assessment'],
        'Documented plan': case['plan'],
        'Encounter details': {'Department': case['department'], 'Setting': 'Outpatient clinic',
                              'Record type': 'Addendum' if corrected else 'Signed visit note'},
        'Follow-up': {'Date': FOLLOW_UP[stage], 'Service': case['department'], 'Status': 'Scheduled in this fictional chart'},
        'Data classification': 'Synthetic demonstration data',
    }
    if case['name'] == 'Liam Walker' and stage in ('baseline', 'middle'):
        extra['Assessment'] = ['Left forearm skin lesion under routine assessment']
        extra['Documented plan'] = ['Record the lesion appearance and patient-reported symptoms.', 'Document routine surgical assessment; no procedure was performed at this earlier visit.']
    elif case['name'] == 'Liam Walker':
        extra['Procedure history'] = {'Procedure': 'Left forearm skin-cyst excision (fictional)', 'Date': '2026-10-24', 'Site': 'Left forearm'}
    reason = 'Left forearm skin-lesion assessment' if case['name'] == 'Liam Walker' and stage in ('baseline', 'middle') else case['condition']
    return {'patient_id': patient['id'], 'visit_date': day, 'reason': reason,
            'notes': _notes(case, stage, corrected), 'medications': medications,
            'allergies': allergies, 'observations': observations, 'additional': extra}


def _attachment(patient, case, canonical, hospital_id, doctor_name, summary=False):
    title = 'Visit summary and review addendum' if summary else case['report_title']
    sections = [('Visit notes', canonical['notes'])] if summary else [
        ('Report context', case.get('report_findings', 'Invented observations recorded for the demonstration. These are not results of an actual specimen or examination.')),
        ('Recorded results', '\n'.join(f'{key}: {value}' for key, value in canonical['observations'].items())),
        ('Clinical context', canonical['reason']),
    ]
    content = make_report(title, patient, HOSPITALS[hospital_id]['name'], doctor_name, canonical['visit_date'], sections)
    name = f'{patient["id"]}_{canonical["visit_date"]}_{"visit-summary" if summary else "report"}.pdf'
    return file_payload({'name': name, 'mime': 'application/pdf', 'base64': base64.b64encode(content).decode()})


def populate(db, count=8):
    password = os.getenv('BRIDGE_DEMO_PASSWORD', DEMO_PASSWORD)
    count = max(2, count)
    with db.connect(write=True) as c:
        for hid, hospital in HOSPITALS.items():
            c.execute('INSERT OR IGNORE INTO hospitals VALUES(?,?,?)', (hid, hospital['name'], hospital['format']))
            if not c.execute('SELECT 1 FROM accounts WHERE login=?', (hospital['email'],)).fetchone():
                c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)', ('doctor-' + hid, hospital['email'], hospital['doctor'], 'hospital', hashed(password), hid, None))
        if not c.execute("SELECT 1 FROM accounts WHERE login='jordan@bridge.demo'").fetchone():
            c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)', ('doctor-jordan', 'jordan@bridge.demo', 'Dr. Jordan Lee', 'hospital', hashed(password), 'memorial', None))
        for i in range(count):
            pid = 'PT-DEMO-SARAH' if i == 0 else f'PT-DEMO-{i + 1:04d}'
            if c.execute('SELECT 1 FROM patients WHERE id=?', (pid,)).fetchone():
                continue
            case = CASES[i % len(CASES)]
            name = case['name'] + (f' {i // len(CASES) + 1}' if i >= len(CASES) else '')
            hid = 'memorial' if i % 2 == 0 else 'valley'
            c.execute('INSERT INTO patients VALUES(?,?,?,?,?,?,?,?,?,?,0)',
                      (pid, name, case['birth_date'], f'(312) 555-{100 + i % 100:04d}',
                       f'patient{i + 1}@example.test', f'{101 + i} Example Avenue, Unit {i + 1}, Chicago, IL 60601', hid, now(), None, None))
            if i < 4:
                c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?)', ('patient-sarah' if i == 0 else f'patient-demo-{i + 1}', pid, name, 'patient', hashed(password), None, pid))
    for i in range(count):
        pid = 'PT-DEMO-SARAH' if i == 0 else f'PT-DEMO-{i + 1:04d}'
        case = CASES[i % len(CASES)]
        with db.connect() as c:
            # Never overwrite or embellish an existing chart during normal startup.
            if c.execute('SELECT 1 FROM visits WHERE patient_id=?', (pid,)).fetchone():
                continue
            patient = dict(c.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone())
        for hid, stage, timestamp in [('valley', 'baseline', '2025-04-22T14:20:00+00:00'),
                                      ('memorial', 'middle', '2026-06-18T15:00:00+00:00'),
                                      ('valley', 'source', '2026-10-28T14:30:00+00:00'),
                                      ('memorial', 'latest', '2026-11-12T14:15:00+00:00')]:
            with db.connect(hid, write=True) as c:
                actor = dict(c.execute('SELECT * FROM accounts WHERE id=?', ('doctor-' + hid,)).fetchone())
                canonical = _canonical(case, patient, stage)
                result = append_visit(c, actor, pid, make_native(HOSPITALS[hid]['format'], canonical, pid), recorded_at=timestamp)
                if stage in ('source', 'latest'):
                    if stage == 'latest':
                        actor = dict(c.execute("SELECT * FROM accounts WHERE id='doctor-jordan'").fetchone())
                    canonical = _canonical(case, patient, stage, corrected=True)
                    document = _attachment(patient, case, canonical, hid, actor['name'], summary=stage == 'latest')
                    append_visit(c, actor, pid, make_native(HOSPITALS[hid]['format'], canonical, pid), [document],
                                 visit_id=result['visit_id'], expected=1,
                                 recorded_at='2026-10-29T15:10:00+00:00' if stage == 'source' else '2026-11-12T16:10:00+00:00')
    with db.connect(write=True) as c:
        request_id = 'req-demo-sarah-continuity'
        if not c.execute('SELECT 1 FROM requests WHERE id=?', (request_id,)).fetchone():
            versions = [row['id'] for row in c.execute("SELECT id FROM versions WHERE patient_id='PT-DEMO-SARAH' AND hospital_id='valley' ORDER BY updated_at")]
            c.execute('INSERT INTO requests(id,patient_id,hospital_id,doctor_id,purpose,sources_json,version_ids_json,include_images,state,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (request_id, 'PT-DEMO-SARAH', 'memorial', 'doctor-memorial',
                       'Review previous laboratory results and medication reconciliation for continuity of care.',
                       dump(['valley']), dump(versions), 1, 'PENDING', now(), expiry(hours=24)))
            actor = dict(c.execute("SELECT * FROM accounts WHERE id='doctor-memorial'").fetchone())
            audit(c, actor, 'TRANSFER_REQUESTED', request_id, 'PT-DEMO-SARAH')
    return {'profile': 'Detailed synthetic hospital charts', 'hospitals': 2, 'patients_requested': count,
            'patient_login': 'PT-DEMO-SARAH', 'other_enrolled_patients': [f'PT-DEMO-{i+1:04d}' for i in range(1,min(4,count))],
            'hospital_logins': ['emily@bridge.demo', 'daniel@bridge.demo', 'jordan@bridge.demo']}
