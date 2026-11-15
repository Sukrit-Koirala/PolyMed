"""Persistent fictional EHR assistive workflow. No vendor or payer write-back."""
import copy
import re
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from .models import *
from .bridge_models import *
from .bridge_schemas import *
from .bridge_access import row, patient_scope, patient_view, record_views, permitted, live_grants
from .security import current_user, require_clinician, require_admin, audit, authorized_patient_ids, hash_password, verify_password
from .adapters import ADAPTERS, clinical_fields, clinical_diff


def later(**kwargs):
    return (datetime.now(timezone.utc) + timedelta(**kwargs)).isoformat()


def build_bridge_router(db, settings):
    router = APIRouter(prefix='/api/bridge', tags=['EHR Bridge'])

    def own_session(s, user, session_id):
        require_clinician(user)
        encounter = s.get(EncounterSession, session_id)
        if not encounter or encounter.doctor_id != user.id or encounter.hospital_id != user.hospital_id:
            raise HTTPException(404, 'Session not found')
        patient_scope(s, user, encounter.patient_id)
        return encounter

    def effective_request_state(s, request):
        grant = s.scalar(select(AccessGrant).where(AccessGrant.request_id == request.id))
        code = s.scalar(select(OneTimeCode).where(OneTimeCode.request_id == request.id))
        if grant:
            return 'REVOKED' if grant.revoked_at else 'EXPIRED' if grant.expires_at <= now() else 'ACTIVE'
        if request.state == 'APPROVED' and code and code.expires_at <= now():
            return 'CODE_EXPIRED'
        return 'EXPIRED' if request.expires_at <= now() and request.state not in ('DENIED', 'REVOKED') else request.state

    def request_view(s, request):
        code = s.scalar(select(OneTimeCode).where(OneTimeCode.request_id == request.id))
        grant = s.scalar(select(AccessGrant).where(AccessGrant.request_id == request.id))
        connection = s.get(EHRConnection, request.hospital_id)
        return row(request) | {'state': effective_request_state(s, request), 'doctor_name': s.get(User, request.doctor_id).name, 'hospital_name': s.get(Hospital, request.hospital_id).name, 'department': connection.department if connection else 'Care team', 'source_names': [s.get(Hospital, hid).name for hid in request.source_hospitals], 'patient_name': s.get(PatientLink, request.patient_id).name, 'code_expires_at': code.expires_at if code else None, 'grant_expires_at': grant.expires_at if grant else None, 'attempts_remaining': max(0, 5-code.attempts) if code else None, 'simulation': 'Demo OTP verification; no SMS or production disclosure service'}

    def issue_code(s, request):
        value = str(secrets.randbelow(900000) + 100000)
        code = s.scalar(select(OneTimeCode).where(OneTimeCode.request_id == request.id))
        if code and code.used_at:
            raise HTTPException(409, 'This approval was already activated')
        if not code:
            code = OneTimeCode(request_id=request.id, code_hash=hash_password(value), expires_at=later(minutes=5))
            s.add(code)
        else:
            code.code_hash, code.expires_at, code.attempts = hash_password(value), later(minutes=5), 0
        s.flush()
        return value, code.expires_at

    def approval_task(s, encounter, user):
        request_id = encounter.intake.get('access_request_id')
        if not request_id:
            return
        request = s.get(AccessRequest, request_id)
        if not request or request.doctor_id != user.id or request.patient_id != encounter.patient_id or request.hospital_id != user.hospital_id:
            raise HTTPException(422, 'The approval request must belong to this doctor, hospital, and patient')
        task = s.scalar(select(SessionTask).where(SessionTask.session_id == encounter.id, SessionTask.kind == 'patient_approval'))
        if not task:
            s.add(SessionTask(session_id=encounter.id, kind='patient_approval', title='Review patient approval outcome', status='DONE' if effective_request_state(s, request) in ('ACTIVE', 'DENIED', 'REVOKED') else 'TODO'))

    def settle_approval_tasks(s, request):
        for encounter in s.scalars(select(EncounterSession).where(EncounterSession.doctor_id == request.doctor_id, EncounterSession.hospital_id == request.hospital_id, EncounterSession.patient_id == request.patient_id, EncounterSession.status != 'COMPLETED')):
            if encounter.intake.get('access_request_id') == request.id:
                for task in s.scalars(select(SessionTask).where(SessionTask.session_id == encounter.id, SessionTask.kind == 'patient_approval')):
                    task.status, task.updated_at = 'DONE', now()

    @router.get('/connection')
    def connection_status(user=Depends(current_user)):
        if user.role not in ('clinician', 'admin'):
            raise HTTPException(403, 'Hospital membership required')
        with db.shared() as s:
            connection = s.get(EHRConnection, user.hospital_id)
            if not connection:
                raise HTTPException(404, 'Mock source connection not configured')
            return row(connection)

    @router.get('/patients')
    def patients(q: str = Query(default='', max_length=120), user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            ids = authorized_patient_ids(s, user)
            patients = list(s.scalars(select(PatientLink).join(BridgePatient).where(PatientLink.id.in_(ids)).order_by(PatientLink.name)))
            audit(s, user, 'BRIDGE_SEARCH_PATIENTS', 'local-care-directory')
            return [patient_view(s, user, p.id) for p in patients if q.casefold() in (p.name + ' ' + p.id).casefold() or q.casefold() in ' '.join(s.scalars(select(LinkMember.local_patient_id).where(LinkMember.patient_id == p.id, LinkMember.hospital_id == user.hospital_id))).casefold()]

    @router.post('/patients', status_code=201)
    def register(body: Registration, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s, db.local(user.hospital_id) as local:
            duplicates = list(s.scalars(select(PatientLink).join(BridgePatient).where(PatientLink.id.in_(authorized_patient_ids(s, user)))))
            matches = [{'id': p.id, 'name': p.name, 'birth_date': p.birth_date} for p in duplicates if p.name.casefold() == body.name.casefold() or p.birth_date == body.birth_date.isoformat()]
            if matches and not body.separate_identity_confirmed:
                raise HTTPException(409, {'message': 'Review possible existing patients before explicitly creating a separate identity.', 'matches': matches})
            pid, local_id = 'BR-' + uid()[:10].upper(), user.hospital_id[:2].upper() + '-' + uid()[:8].upper()
            s.add(PatientLink(id=pid, name=body.name, birth_date=body.birth_date.isoformat(), synthetic=True))
            s.flush()
            demographics = body.model_dump(exclude={'name', 'birth_date', 'synthetic_confirmed', 'separate_identity_confirmed'}, mode='json')
            demographics = {key: value.strip() or 'Unknown' for key, value in demographics.items()}
            s.add(BridgePatient(id=pid, demographics=demographics))
            s.add(LinkMember(patient_id=pid, hospital_id=user.hospital_id, local_patient_id=local_id, status='CONFIRMED', evidence='Explicit new fictional local registration; no automatic identity merge', reviewed_by=user.id))
            s.add(CareRelationship(hospital_id=user.hospital_id, local_patient_id=local_id, reason='Registered by authorized local clinician'))
            local.add(LocalPatient(id=local_id, name=body.name, first_name=body.name.split()[0], last_name=body.name.split()[-1], birth_date=body.birth_date.isoformat(), administrative_gender=body.sex, contact=body.phone))
            s.flush()
            audit(s, user, 'BRIDGE_PATIENT_REGISTERED', pid)
            return patient_view(s, user, pid)

    @router.get('/patients/{patient_id}')
    def patient(patient_id: str, user=Depends(current_user)):
        with db.shared() as s:
            records = record_views(s, user, patient_id)
            visible_ids = {r['id'] for r in records}
            conflicts = [row(c) for c in s.scalars(select(Conflict).where(Conflict.patient_id == patient_id, Conflict.active == True, Conflict.category != 'CLINICALLY_EQUIVALENT')) if set(c.record_ids) <= visible_ids]
            return patient_view(s, user, patient_id, records) | {'records': records, 'conflicts': conflicts}

    @router.get('/records/{record_id}')
    def details(record_id: str, user=Depends(current_user)):
        with db.shared() as s:
            resource = s.get(CanonicalResource, record_id) or s.get(PreservedRecord, record_id)
            if not resource:
                raise HTTPException(404, 'Record not found')
            visible = next((r for r in record_views(s, user, resource.patient_id) if r['id'] == record_id), None)
            if not visible:
                raise HTTPException(404, 'Record not found within your approved scope')
            if isinstance(resource, CanonicalResource):
                versions = [row(v) | {'fields': clinical_fields(v.payload)} for v in s.scalars(select(ResourceVersion).where(ResourceVersion.resource_id == record_id).order_by(ResourceVersion.version.desc()))]
                events = [row(e) for e in s.scalars(select(ClinicalEvent).where(ClinicalEvent.resource_id == record_id).order_by(ClinicalEvent.source_version.desc()))]
                preview = ADAPTERS[user.hospital_id].from_canonical(resource.payload) if user.hospital_id in ADAPTERS else {'notice': 'Personal record view; no destination selected'}
                if visible['mapping'] != 'Mapped':
                    preview = {'mapping_status': visible['mapping'], 'fields': {}, 'preserved': visible['fields'], 'notice': 'Destination mapping is disabled; original source and normalized facts remain preserved.'}
                normalized, original = resource.payload, resource.original_payload
            else:
                versions = [row(v) | {'fields': v.snapshot['normalized']['fields']} for v in s.scalars(select(PreservedVersion).where(PreservedVersion.record_id == record_id).order_by(PreservedVersion.version.desc()))]
                events = [{'author': resource.author, 'occurred_at': resource.recorded_at, 'event_type': 'SOURCE_IMPORTED', 'source_version': resource.version}]
                normalized, original = resource.normalized, resource.original
                preview = {'destination': s.get(Hospital, user.hospital_id).name, 'mapping_status': visible['mapping'], 'fields': resource.normalized['fields'] if visible['mapping'] == 'Mapped' else {}, 'preserved': resource.normalized['fields'], 'notice': 'Preserved in EHR Bridge. No external destination import was attempted.'}
            review = list(s.scalars(select(BridgeRecordReview).where(BridgeRecordReview.record_id == record_id, BridgeRecordReview.hospital_id == user.hospital_id).order_by(BridgeRecordReview.created_at.desc())))
            audit(s, user, 'BRIDGE_INSPECT_TRANSLATION_HISTORY', record_id)
            return visible | {'versions': versions, 'events': events, 'original': original, 'normalized': normalized, 'destination': preview, 'review_history': [row(r) for r in review], 'notice': 'Mock adapter representations. Translation and workspace availability do not establish external EHR delivery or acceptance.'}

    @router.post('/records/{record_id}/reviews')
    def review(record_id: str, body: RecordReviewInput, user=Depends(current_user)):
        require_clinician(user)
        detail = details(record_id, user)
        with db.shared() as s:
            # Review metadata is appended; no original source field is overwritten.
            audit(s, user, 'BRIDGE_RECORD_' + body.action, record_id)
            s.add(BridgeRecordReview(record_id=record_id, patient_id=detail['patient_id'], hospital_id=user.hospital_id, user_id=user.id, action=body.action, note=body.note))
            return {'recorded': True, 'action': body.action, 'note': body.note, 'source_modified': False}

    @router.get('/requests')
    def requests(user=Depends(current_user)):
        with db.shared() as s:
            query = select(AccessRequest)
            if user.role == 'patient':
                profile = s.scalar(select(BridgePatient).where(BridgePatient.portal_user_id == user.id))
                query = query.where(AccessRequest.patient_id == (profile.id if profile else 'NONE'))
            else:
                require_clinician(user)
                query = query.where(AccessRequest.doctor_id == user.id, AccessRequest.hospital_id == user.hospital_id)
            return [request_view(s, r) for r in s.scalars(query.order_by(AccessRequest.created_at.desc()))]

    @router.post('/requests', status_code=201)
    def request_access(body: AccessInput, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            profile = patient_scope(s, user, body.patient_id)
            if not profile.portal_user_id:
                raise HTTPException(422, 'This fictional patient has no linked portal account. Continue with local records or choose Sarah for the approval demonstration.')
            available = set(s.scalars(select(LinkMember.hospital_id).where(LinkMember.patient_id == body.patient_id, LinkMember.status == 'CONFIRMED')))
            sources = sorted(set(body.source_hospitals))
            if user.hospital_id in sources or not set(sources) <= available:
                raise HTTPException(422, 'Select connected external source hospitals for this patient')
            if any(not s.get(EHRConnection, hid) or s.get(EHRConnection, hid).status != 'CONNECTED' for hid in sources):
                raise HTTPException(409, 'A selected mock connection is paused')
            request = AccessRequest(patient_id=body.patient_id, doctor_id=user.id, hospital_id=user.hospital_id, source_hospitals=sources, categories=body.categories, purpose=body.purpose, encounter_reason=body.encounter_reason, duration_hours=body.duration_hours, expires_at=later(hours=24))
            s.add(request)
            s.flush()
            audit(s, user, 'BRIDGE_ACCESS_REQUESTED', request.id)
            return request_view(s, request)

    @router.post('/requests/{request_id}/decision')
    def decide(request_id: str, body: Decision, user=Depends(current_user)):
        if user.role != 'patient':
            raise HTTPException(403, 'The patient must make this access decision')
        with db.shared() as s:
            request = s.scalar(select(AccessRequest).where(AccessRequest.id == request_id).with_for_update())
            if not request:
                raise HTTPException(404, 'Request not found')
            patient_scope(s, user, request.patient_id)
            state = effective_request_state(s, request)
            if body.action == 'REVOKE':
                grant = s.scalar(select(AccessGrant).where(AccessGrant.request_id == request_id))
                if grant:
                    grant.revoked_at = now()
                request.state = 'REVOKED'
                code = s.scalar(select(OneTimeCode).where(OneTimeCode.request_id == request_id))
                if code:
                    code.used_at = now()
                audit(s, user, 'BRIDGE_ACCESS_REVOKED', request.id)
                settle_approval_tasks(s, request)
                return request_view(s, request)
            if request.expires_at <= now() or state in ('DENIED', 'REVOKED', 'ACTIVE', 'EXPIRED'):
                raise HTTPException(409, 'This request no longer accepts that decision')
            code_value = None
            if body.action in ('APPROVE', 'NEW_CODE'):
                if body.action == 'NEW_CODE' and state not in ('APPROVED', 'CODE_EXPIRED'):
                    raise HTTPException(409, 'Approve the request before generating a new code')
                if body.action == 'APPROVE' and state not in ('PENDING', 'INVESTIGATING'):
                    raise HTTPException(409, 'This request was already approved; generate a new code if needed')
                request.state = 'APPROVED'
                code_value, expires = issue_code(s, request)
            elif body.action == 'DENY':
                request.state = 'DENIED'
                settle_approval_tasks(s, request)
            elif body.action == 'INVESTIGATE':
                request.state = 'INVESTIGATING'
            request.patient_message = body.message
            audit(s, user, 'BRIDGE_PATIENT_' + body.action, request.id)
            return request_view(s, request) | ({'code': code_value, 'code_expires_at': expires} if code_value else {})

    @router.post('/requests/{request_id}/redeem')
    def redeem(request_id: str, body: Redeem, user=Depends(current_user)):
        require_clinician(user)
        failure, result = None, None
        with db.shared() as s:
            request = s.scalar(select(AccessRequest).where(AccessRequest.id == request_id).with_for_update())
            if not request or request.doctor_id != user.id or request.hospital_id != user.hospital_id:
                raise HTTPException(404, 'Request not found')
            patient_scope(s, user, request.patient_id)
            code = s.scalar(select(OneTimeCode).where(OneTimeCode.request_id == request_id))
            if request.state != 'APPROVED' or request.expires_at <= now() or not code or code.used_at or code.expires_at <= now():
                failure = (409, 'Approval/code is missing, expired, revoked, or already used')
            elif code.attempts >= 5:
                failure = (429, 'Code attempt limit reached; the patient must generate a new code')
            elif not verify_password(body.code, code.code_hash):
                s.execute(update(OneTimeCode).where(OneTimeCode.id == code.id).values(attempts=OneTimeCode.attempts + 1))
                failure = (400, 'Invalid demonstration code')
                audit(s, user, 'BRIDGE_OTP_INVALID', request.id)
            else:
                # Serialize activation with patient denial/revocation as well as code use.
                consent = s.execute(update(AccessRequest).where(AccessRequest.id == request.id, AccessRequest.state == 'APPROVED', AccessRequest.expires_at > now()).values(state='ACTIVE'))
                if consent.rowcount != 1:
                    return JSONResponse(status_code=409, content={'detail': 'The patient approval changed; no scope was activated'})
                reserved = s.execute(update(OneTimeCode).where(OneTimeCode.id == code.id, OneTimeCode.used_at.is_(None), OneTimeCode.attempts < 5, OneTimeCode.expires_at > now()).values(used_at=now()))
                if reserved.rowcount != 1:
                    request.state = 'APPROVED'
                    failure = (409, 'The code was already used or expired')
                else:
                    grant = AccessGrant(request_id=request.id, patient_id=request.patient_id, doctor_id=user.id, hospital_id=user.hospital_id, source_hospitals=request.source_hospitals, categories=request.categories, expires_at=later(hours=request.duration_hours))
                    s.add(grant)
                    s.flush()
                    records = record_views(s, user, request.patient_id, False)
                    for record in records:
                        if record['hospital_id'] in grant.source_hospitals and record['category'] in grant.categories:
                            unmapped = record['mapping'] != 'Mapped'
                            s.add(ExchangeEvent(patient_id=request.patient_id, grant_id=grant.id, doctor_id=user.id, source_hospital_id=record['hospital_id'], destination_hospital_id=user.hospital_id, record_id=record['id'], category=record['category'], translation_result='PRESERVED_UNMAPPED' if unmapped else 'TRANSFORMED', preserved_fields=list(record['fields']) if unmapped else [], source_version=record['version']))
                    audit(s, user, 'BRIDGE_SCOPE_ACTIVATED', request.id)
                    settle_approval_tasks(s, request)
                    result = request_view(s, request)
        # Invalid attempts must commit before the error response, or limits can be bypassed.
        if failure:
            return JSONResponse(status_code=failure[0], content={'detail': failure[1]})
        return result

    def normalize_intake(intake):
        value = copy.deepcopy(intake)
        for field in ('questions', 'suggestions'):
            if not isinstance(value.get(field, []), list) or any(not isinstance(item, dict) for item in value.get(field, [])):
                raise HTTPException(422, 'Questions and suggestions must be lists of structured fields')
        if not isinstance(value.get('transcript', ''), str) or len(value.get('transcript', '')) > 60000:
            raise HTTPException(422, 'Transcript must contain at most 60,000 characters')
        if not isinstance(value.get('reported', {}), dict) or any(not isinstance(v, str) or len(v)>4000 for v in value.get('reported', {}).values()):
            raise HTTPException(422, 'Patient-reported fields must contain text')
        for question in value.get('questions', []):
            if question.get('kind') not in ('text', 'yes_no', 'multiple_choice', 'numeric') or not isinstance(question.get('label'), str) or not 1 <= len(question['label']) <= 300:
                raise HTTPException(422, 'Intake questions require a valid label and response type')
            answer = question.get('answer', '')
            if not isinstance(question.get('options', []), list) or any(not isinstance(v, str) for v in question.get('options', [])):
                raise HTTPException(422, 'Question options must be a list of text values')
            if question['kind'] == 'numeric' and answer != '':
                try:
                    float(answer)
                except (TypeError, ValueError):
                    raise HTTPException(422, 'Numeric questions require a number')
            if question['kind'] == 'yes_no' and answer not in ('', 'Yes', 'No', 'Unknown'):
                raise HTTPException(422, 'Choose Yes, No, or Unknown')
            if question['kind'] == 'multiple_choice' and answer and answer not in question.get('options', []):
                raise HTTPException(422, 'Choose a supplied question option')
        if len(value.get('questions', [])) > 30:
            raise HTTPException(422, 'Limit the development intake to 30 questions')
        # Caller-supplied classifications cannot turn a patient statement into a verified source fact.
        value['information_origin'] = 'Doctor-entered / reviewed patient report; not a verified clinical source'
        for field in value.get('suggestions', []):
            if field.get('status') not in ('DRAFT', 'ACCEPTED', 'REJECTED'):
                raise HTTPException(422, 'Review each suggestion as draft, accepted, or rejected')
            field['origin'] = 'Doctor-reviewed patient report; not verified clinical fact' if field['status'] == 'ACCEPTED' else 'Unreviewed or rejected draft patient statement'
        return value

    def encounter_view(s, encounter):
        return row(encounter) | {'patient_name': s.get(PatientLink, encounter.patient_id).name, 'tasks': [row(t) for t in s.scalars(select(SessionTask).where(SessionTask.session_id == encounter.id))], 'insurance': [row(i) for i in s.scalars(select(InsuranceVerification).where(InsuranceVerification.session_id == encounter.id).order_by(InsuranceVerification.created_at.desc()))], 'versions': [row(v) for v in s.scalars(select(EncounterVersion).where(EncounterVersion.encounter_id == encounter.id).order_by(EncounterVersion.revision.desc()).limit(20))]}

    def append_intake_evidence(s, encounter, user):
        s.add(EncounterVersion(encounter_id=encounter.id, revision=encounter.revision, snapshot={'status': encounter.status, 'reason': encounter.reason, 'intake': encounter.intake}, author_id=user.id))
        intake = encounter.intake
        if intake.get('transcript'):
            s.add(VoiceMemo(session_id=encounter.id, transcript=intake['transcript'], source=intake.get('transcript_source', 'Manual transcript'), suggestions=intake.get('suggestions', [])))
        for question in intake.get('questions', []):
            item = IntakeQuestion(session_id=encounter.id, label=question['label'], kind=question['kind'], options=question.get('options', []))
            s.add(item)
            s.flush()
            s.add(IntakeAnswer(question_id=item.id, value={'answer': question.get('answer', ''), 'encounter_revision': encounter.revision}))

    @router.get('/sessions')
    def sessions(user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            return [encounter_view(s, e) for e in s.scalars(select(EncounterSession).where(EncounterSession.doctor_id == user.id, EncounterSession.hospital_id == user.hospital_id).order_by(EncounterSession.updated_at.desc()))]

    @router.post('/sessions', status_code=201)
    def create_session(body: SessionInput, user=Depends(current_user)):
        require_clinician(user)
        if body.status == 'COMPLETED':
            raise HTTPException(422, 'Start a session and review its tasks before completing it')
        with db.shared() as s:
            patient_scope(s, user, body.patient_id)
            encounter = EncounterSession(patient_id=body.patient_id, hospital_id=user.hospital_id, doctor_id=user.id, reason=body.reason.strip(), status=body.status, intake=normalize_intake(body.intake))
            s.add(encounter)
            s.flush()
            for kind, title in [('documentation', 'Review and complete documentation'), ('record_review', 'Review available source records'), ('insurance', 'Investigate service eligibility')]:
                s.add(SessionTask(session_id=encounter.id, kind=kind, title=title))
            append_intake_evidence(s, encounter, user)
            approval_task(s, encounter, user)
            audit(s, user, 'BRIDGE_SESSION_CREATED', encounter.id)
            s.flush()
            return encounter_view(s, encounter)

    @router.put('/sessions/{session_id}')
    def save_session(session_id: str, body: SessionInput, user=Depends(current_user)):
        with db.shared() as s:
            encounter = own_session(s, user, session_id)
            if encounter.patient_id != body.patient_id or encounter.status == 'COMPLETED':
                raise HTTPException(409, 'Patient identity is fixed and completed sessions retain their history')
            if body.status == 'COMPLETED' and s.scalar(select(SessionTask.id).where(SessionTask.session_id == encounter.id, SessionTask.status != 'DONE')):
                raise HTTPException(409, 'Review and complete the remaining session tasks first')
            result = s.execute(update(EncounterSession).where(EncounterSession.id == encounter.id, EncounterSession.revision == body.expected_revision).values(reason=body.reason.strip(), intake=normalize_intake(body.intake), status=body.status, revision=EncounterSession.revision+1, updated_at=now(), completed_at=now() if body.status == 'COMPLETED' else None))
            if result.rowcount != 1:
                raise HTTPException(409, 'This session changed. Reload before saving.')
            s.refresh(encounter)
            append_intake_evidence(s, encounter, user)
            approval_task(s, encounter, user)
            audit(s, user, 'BRIDGE_SESSION_' + body.status, encounter.id)
            s.flush()
            return encounter_view(s, encounter)

    @router.post('/sessions/{session_id}/tasks', status_code=201)
    def create_task(session_id: str, body: TaskCreate, user=Depends(current_user)):
        with db.shared() as s:
            encounter = own_session(s, user, session_id)
            if encounter.status == 'COMPLETED':
                raise HTTPException(409, 'Completed sessions retain their task history')
            if body.kind == 'patient_approval' and not encounter.intake.get('access_request_id'):
                raise HTTPException(422, 'Create a patient access request before adding its approval task')
            task = SessionTask(session_id=encounter.id, kind=body.kind, title=body.title.strip())
            s.add(task)
            s.flush()
            audit(s, user, 'BRIDGE_TASK_CREATED', task.id)
            return row(task)

    @router.put('/tasks/{task_id}')
    def update_task(task_id: str, body: TaskInput, user=Depends(current_user)):
        with db.shared() as s:
            task = s.get(SessionTask, task_id)
            if not task:
                raise HTTPException(404, 'Task not found')
            encounter = own_session(s, user, task.session_id)
            if encounter.status == 'COMPLETED':
                raise HTTPException(409, 'Completed session tasks are retained')
            if task.kind == 'patient_approval' and body.status == 'DONE':
                request = s.get(AccessRequest, encounter.intake.get('access_request_id'))
                if not request or effective_request_state(s, request) not in ('ACTIVE', 'DENIED', 'REVOKED'):
                    raise HTTPException(409, 'Wait for an activated approval or a definitive patient decision before completing this task')
            task.status, task.updated_at = body.status, now()
            audit(s, user, 'BRIDGE_TASK_' + body.status, task.id)
            return row(task)

    @router.post('/intake/extract')
    def extract(body: TranscriptInput, user=Depends(current_user)):
        require_clinician(user)
        suggestions = []
        patterns = [('symptom', 'Reported symptom', r'chest (?:discomfort|pain)|headache|fatigue|cough'), ('duration', 'Reported duration', r'\b(?:\d+|one|two|three|four|five|six|seven) (?:days?|weeks?|months?)\b'), ('hospital', 'Hospital mentioned', r'Valley Medical|Memorial Hospital'), ('medication', 'Medication mentioned', r'lisinopril|metformin|amlodipine'), ('testing', 'Prior testing mentioned', r'heart test|cardiac test(?:ing)?|echocardiogram')]
        for key, label, pattern in patterns:
            match = re.search(pattern, body.transcript, re.I)
            if match:
                suggestions.append({'key': key, 'label': label, 'value': match.group(), 'source_quote': match.group(), 'status': 'DRAFT', 'origin': 'Rule-extracted patient statement; unverified'})
        return {'suggestions': suggestions, 'provider': 'Local extractive demo rules; no AI inference or transcription', 'notice': 'Accepted suggestions remain patient-reported intake. They never update the medication list or verified hospital facts.'}

    @router.post('/sessions/{session_id}/insurance')
    def insurance(session_id: str, body: InsuranceInput, user=Depends(current_user)):
        if body.coverage_start and body.coverage_end and body.coverage_end < body.coverage_start:
            raise HTTPException(422, 'Coverage end must follow coverage start')
        with db.shared() as s:
            encounter = own_session(s, user, session_id)
            if encounter.status == 'COMPLETED':
                raise HTTPException(409, 'Completed session evidence cannot be changed')
            results = [{'service': name, 'eligibility': 'Simulated eligible — unverified', 'network': 'Sample in-network', 'copay_estimate': copay, 'deductible': '$750 sample remaining', 'prior_authorization': authorization} for name, copay, authorization in [('Primary care visit', '$25', 'Not required in example'), ('Blood tests', '$10', 'Not required in example'), ('Imaging', '$100', 'Required in example'), ('Specialist consultation', '$50', 'Check plan requirements')]]
            verification = InsuranceVerification(session_id=session_id, input=body.model_dump(mode='json'), results=results)
            s.add(verification)
            audit(s, user, 'BRIDGE_MOCK_INSURANCE_REQUESTED', session_id)
            s.flush()
            return row(verification)

    @router.get('/dashboard')
    def dashboard(user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            encounters = list(s.scalars(select(EncounterSession).where(EncounterSession.doctor_id == user.id, EncounterSession.hospital_id == user.hospital_id)))
            ids = [e.id for e in encounters]
            tasks = list(s.scalars(select(SessionTask).where(SessionTask.session_id.in_(ids))))
            tz = ZoneInfo('America/Chicago')
            today = datetime.now(tz).date()
            day = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(tz).date()
            chart = []
            for offset in range(6, -1, -1):
                date_value = today-timedelta(days=offset)
                chart.append({'day': date_value.strftime('%a'), 'sessions': sum(day(e.created_at) == date_value for e in encounters), 'documentation': sum(day(t.updated_at) == date_value and t.status == 'DONE' and t.kind == 'documentation' for t in tasks), 'administrative': sum(day(t.updated_at) == date_value and t.status == 'DONE' and t.kind != 'documentation' for t in tasks)})
            return {'metrics': {'patients_seen': len({e.patient_id for e in encounters if day(e.created_at) == today and e.status in ('ACTIVE', 'COMPLETED')}), 'active_sessions': sum(e.status == 'ACTIVE' for e in encounters), 'pending_tasks': sum(t.status != 'DONE' for t in tasks), 'completed_tasks': sum(t.status == 'DONE' and day(t.updated_at) == today for t in tasks)}, 'weekly': chart, 'task_distribution': [{'name': 'Completed', 'value': sum(t.status == 'DONE' for t in tasks)}, {'name': 'Pending', 'value': sum(t.status != 'DONE' for t in tasks)}], 'work_queue': [encounter_view(s, e) for e in sorted(encounters, key=lambda e: e.updated_at, reverse=True) if e.status != 'COMPLETED' or day(e.created_at) == today]}

    @router.get('/exchange')
    def exchange(user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            events = [row(e) for e in s.scalars(select(ExchangeEvent).where(ExchangeEvent.doctor_id == user.id, ExchangeEvent.destination_hospital_id == user.hospital_id).order_by(ExchangeEvent.created_at.desc()))]
            records = []
            for pid in authorized_patient_ids(s, user):
                if s.get(BridgePatient, pid):
                    records.extend(record_views(s, user, pid, False))
            connections = [row(c) | {'name': s.get(Hospital, c.id).name, 'simulation': True} for c in s.scalars(select(EHRConnection))]
            return {'events': events, 'records': records, 'connections': connections, 'metrics': {'retrieved': len(events), 'translated': sum(e['translation_result'] == 'TRANSFORMED' for e in events), 'available': sum(e['delivery_result'] == 'AVAILABLE_IN_WORKSPACE' for e in events), 'incomplete': sum(e['translation_result'] == 'PRESERVED_UNMAPPED' for e in events), 'preserved': sum(len(e['preserved_fields']) for e in events)}, 'notice': 'Source mock adapters and cached fictional records. No external EHR delivery or acceptance is claimed.'}

    @router.get('/patient-home')
    def patient_home(user=Depends(current_user)):
        if user.role != 'patient':
            raise HTTPException(403, 'An independent patient account is required')
        with db.shared() as s:
            profile = s.scalar(select(BridgePatient).where(BridgePatient.portal_user_id == user.id))
            if not profile:
                raise HTTPException(404, 'Patient profile not found')
            records = record_views(s, user, profile.id)
            request_ids = list(s.scalars(select(AccessRequest.id).where(AccessRequest.patient_id == profile.id)))
            audit_events = list(s.scalars(select(AuditEvent).where((AuditEvent.target.in_(request_ids)) | (AuditEvent.target.like(profile.id + '/categories/%'))).order_by(AuditEvent.created_at.desc()).limit(80)))
            return patient_view(s, user, profile.id, records) | {'records': records, 'history': [row(a) | {'actor_name': s.get(User, a.user_id).name if a.user_id and s.get(User, a.user_id) else 'System'} for a in audit_events], 'requests': [request_view(s, r) for r in s.scalars(select(AccessRequest).where(AccessRequest.patient_id == profile.id).order_by(AccessRequest.created_at.desc()))]}

    @router.get('/admin')
    def admin(user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            connection = s.get(EHRConnection, user.hospital_id)
            if not connection:
                raise HTTPException(403, 'No Bridge organization administration membership')
            staff = [row(m) | {'name': s.get(User, m.user_id).name, 'email': s.get(User, m.user_id).email} for m in s.scalars(select(HospitalMembership).where(HospitalMembership.hospital_id == user.hospital_id))]
            events = [row(e) for e in s.scalars(select(ExchangeEvent).where(ExchangeEvent.destination_hospital_id == user.hospital_id).order_by(ExchangeEvent.created_at.desc()))]
            logs = [row(a) for a in s.scalars(select(AuditEvent).where(AuditEvent.hospital_id == user.hospital_id).order_by(AuditEvent.created_at.desc()).limit(100))]
            return {'connection': row(connection), 'hospital': row(s.get(Hospital, user.hospital_id)), 'staff': staff, 'events': events, 'audit': logs, 'notice': 'Organization metadata only. Administrator role does not grant clinical-record access.'}

    @router.put('/admin/connection')
    def edit_connection(body: ConnectionInput, user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            connection = s.get(EHRConnection, user.hospital_id)
            if not connection:
                raise HTTPException(404, 'Organization connection not found')
            connection.status, connection.department, connection.updated_at = body.status, body.department, now()
            if body.supported_categories is not None:
                connection.supported_categories = body.supported_categories
            audit(s, user, 'BRIDGE_CONNECTION_UPDATED', user.hospital_id)
            return row(connection)

    @router.post('/admin/staff', status_code=201)
    def add_staff(body: StaffInput, user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            if s.scalar(select(User).where(User.email == body.email.lower())):
                raise HTTPException(409, 'This email is already registered')
            account = User(id='bridge-' + uid(), email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), hospital_id=user.hospital_id, role=body.role)
            s.add(account)
            s.flush()
            s.add(HospitalMembership(user_id=account.id, hospital_id=user.hospital_id, role=body.role, active=True))
            audit(s, user, 'BRIDGE_STAFF_CREATED', account.id)
            return {'id': account.id, 'name': account.name, 'role': account.role, 'email': account.email}

    @router.put('/admin/staff/{membership_id}')
    def staff_membership(membership_id: str, body: MembershipInput, user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            membership = s.get(HospitalMembership, membership_id)
            if not membership or membership.hospital_id != user.hospital_id:
                raise HTTPException(404, 'Staff membership not found')
            if membership.user_id == user.id:
                raise HTTPException(409, 'Use another administrator to change your own organization permissions')
            membership.active, membership.role = body.active, body.role
            audit(s, user, 'BRIDGE_STAFF_PERMISSIONS_UPDATED', membership.user_id)
            return row(membership)

    return router
