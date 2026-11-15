import copy
import asyncio
import logging
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from pathlib import PurePosixPath

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from .adapters import ADAPTERS, KINDS, REVERSE_KINDS, clinical_diff, clinical_fields
from .config import Settings
from .database import Databases
from .models import *
from .schemas import ClinicalInput, IdentityInput, LoginInput, ResetInput, ReviewInput, WithdrawInput, WorkspaceInput
from .security import (WorkspaceUser, audit, authorized_patient_ids, current_user, issue_session, require_admin, require_clinician, require_local, require_shared, token_hash, verify_password)
from .seed import seed, simulate_allergy_update
from .services import ChangeDetectionService, SynchronizationService


def row(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def create_app(settings=None, initialize=True):
    settings = settings or Settings()
    db = Databases(settings)

    @asynccontextmanager
    async def lifespan(app):
        if initialize:
            db.create_schema()
            if settings.demo_mode:
                seed(db)
        from .retention import purge_expired_transcripts
        from starlette.concurrency import run_in_threadpool
        if initialize:
            purge_expired_transcripts(db)
        async def retention_worker():
            while True:
                await asyncio.sleep(60)
                try:
                    await run_in_threadpool(purge_expired_transcripts, db)
                except Exception:
                    logging.getLogger('clinicalsync').warning('Transcript retention sweep failed; the next sweep will retry. No transcript contents are logged.')
        task = asyncio.create_task(retention_worker()) if initialize else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            db.dispose()

    app = FastAPI(title='ClinicalSync', version='1.0.0', description='Synthetic, provenance-preserving clinical collaboration. No clinical write-back.', lifespan=lifespan)
    app.state.db, app.state.settings = db, settings
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True, allow_methods=['GET', 'POST', 'PUT'], allow_headers=['Content-Type', 'X-CSRF-Token', 'X-Workspace-ID', 'X-Recording-Consent', 'X-External-Processing-Consent'])
    login_attempts = defaultdict(deque)

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/') and response.status_code in (401, 403, 404):
            with db.shared() as s:
                user_id = getattr(request.state, 'authenticated_user_id', None)
                actor = s.get(User, user_id) if user_id else None
                principal = WorkspaceUser(actor.id, actor.email, actor.name, getattr(request.state, 'authenticated_hospital_id', actor.hospital_id), actor.role) if actor else None
                audit(s, principal, 'ACCESS_DENIED', request.method + ' ' + request.url.path)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse(status_code=409, content={'detail': 'Concurrent change or duplicate identifier. Refresh and retry.'})

    @app.get('/api/health', tags=['Operations'])
    def health():
        return {'status': 'ok', 'synthetic_only': True, 'demo_mode': settings.demo_mode}

    def user_context(s, user):
        memberships = [{'hospital': row(s.get(Hospital, m.hospital_id)), 'role': m.role} for m in s.scalars(select(HospitalMembership).where(HospitalMembership.user_id == user.id, HospitalMembership.active == True))]
        return {'id': user.id, 'email': user.email, 'name': user.name, 'hospital_id': user.hospital_id, 'role': user.role, 'hospital': row(s.get(Hospital, user.hospital_id)), 'memberships': memberships}

    @app.post('/api/auth/workspace', tags=['Authentication'])
    def switch_workspace(body: WorkspaceInput, request: Request, user=Depends(current_user)):
        with db.shared() as s:
            membership = s.scalar(select(HospitalMembership).where(HospitalMembership.user_id == user.id, HospitalMembership.hospital_id == body.hospital_id, HospitalMembership.active == True))
            if not membership or body.hospital_id not in db.local_factories:
                raise HTTPException(403, 'You do not have access to this hospital workspace')
            session = s.get(SessionToken, token_hash(request.cookies.get('clinicalsync_session', '')))
            session.active_hospital_id = body.hospital_id
            selected = WorkspaceUser(user.id, user.email, user.name, body.hospital_id, membership.role)
            audit(s, selected, 'WORKSPACE_CHANGED', body.hospital_id)
            return {'user': user_context(s, selected), 'csrf_token': session.csrf}

    @app.post('/api/auth/login', tags=['Authentication'])
    def login(body: LoginInput, request: Request, response: Response):
        origin = request.headers.get('origin')
        if origin and origin not in settings.allowed_origins:
            raise HTTPException(403, 'Origin is not allowed')
        ip = request.client.host if request.client else 'local'
        attempts = login_attempts[ip]
        while attempts and attempts[0] < time.monotonic() - 60:
            attempts.popleft()
        if len(attempts) >= 15:
            raise HTTPException(429, 'Too many sign-in attempts. Try again in one minute.')
        attempts.append(time.monotonic())
        with db.shared() as s:
            user = s.scalar(select(User).where(User.email == body.email.lower()))
            if not user or not verify_password(body.password, user.password_hash):
                audit(s, None, 'LOGIN_FAILED', 'session')
                # Commit audit before returning the failure response.
                s.flush()
                return JSONResponse(status_code=401, content={'detail': 'Invalid demo account or password'})
            token, csrf = issue_session(s, user)
            audit(s, user, 'LOGIN', 'session')
            response.set_cookie('clinicalsync_session', token, httponly=True, secure=settings.secure_cookie, samesite='lax', max_age=28800, path='/')
            return {'user': user_context(s, user), 'csrf_token': csrf}

    @app.get('/api/auth/me', tags=['Authentication'])
    def me(request: Request, user=Depends(current_user)):
        with db.shared() as s:
            return {'user': user_context(s, user), 'csrf_token': request.state.csrf, 'demo_mode': settings.demo_mode}

    @app.post('/api/auth/logout', tags=['Authentication'])
    def logout(request: Request, response: Response, user=Depends(current_user)):
        with db.shared() as s:
            token = s.get(SessionToken, token_hash(request.cookies.get('clinicalsync_session', '')))
            if token:
                s.delete(token)
            audit(s, user, 'LOGOUT', 'session')
        response.delete_cookie('clinicalsync_session', path='/')
        return {'signed_out': True}

    @app.get('/api/patients', tags=['Shared patients'])
    def patients(q: str = Query(default='', max_length=100), user=Depends(current_user)):
        with db.shared() as s:
            allowed = authorized_patient_ids(s, user)
            found = [p for p in s.scalars(select(PatientLink).where(PatientLink.id.in_(allowed)).order_by(PatientLink.name)) if q.casefold() in (p.name + p.id).casefold()]
            audit(s, user, 'SEARCH_PATIENTS', 'authorized-patients')
            return [row(p) | {'members': [row(m) for m in s.scalars(select(LinkMember).where(LinkMember.patient_id == p.id, LinkMember.status == 'CONFIRMED'))], 'record_count': s.scalar(select(func.count()).select_from(CanonicalResource).where(CanonicalResource.patient_id == p.id)), 'discrepancies': s.scalar(select(func.count()).select_from(Conflict).where(Conflict.patient_id == p.id, Conflict.active == True, Conflict.category != 'CLINICALLY_EQUIVALENT'))} for p in found]

    def record_view(s, resource, hospital):
        latest = s.scalar(select(ClinicalEvent).where(ClinicalEvent.resource_id == resource.id).order_by(ClinicalEvent.source_version.desc()))
        review = s.scalar(select(ReviewItem).where(ReviewItem.event_id == latest.id, ReviewItem.hospital_id == hospital)) if latest else None
        return row(resource) | {'fields': clinical_fields(resource.payload), 'source': row(s.get(Hospital, resource.hospital_id)), 'review_status': review.status if review else 'SOURCE_RECORD', 'latest_event_id': latest.id if latest else None, 'review_id': review.id if review else None}

    @app.get('/api/patients/{patient_id}', tags=['Shared patients'])
    def patient_profile(patient_id: str, resource_type: str | None = None, source: str | None = None, date_from: str | None = None, date_to: str | None = None, user=Depends(current_user)):
        with db.shared() as s:
            require_shared(s, user, patient_id)
            patient = s.get(PatientLink, patient_id)
            query = select(CanonicalResource).where(CanonicalResource.patient_id == patient_id)
            if resource_type:
                query = query.where(CanonicalResource.resource_type == resource_type)
            if source:
                query = query.where(CanonicalResource.hospital_id == source)
            if date_from:
                query = query.where(CanonicalResource.effective_at >= date_from)
            if date_to:
                query = query.where(CanonicalResource.effective_at <= date_to + 'T23:59:59.999999+00:00')
            audit(s, user, 'READ_SHARED_PATIENT', patient_id)
            return row(patient) | {'fhir_patient': {'resourceType': 'Patient', 'id': patient.id, 'active': True, 'name': [{'text': patient.name}], 'birthDate': patient.birth_date, 'identifier': [{'system': f'urn:clinicalsync:{m.hospital_id}:patient', 'value': m.local_patient_id} for m in s.scalars(select(LinkMember).where(LinkMember.patient_id == patient_id, LinkMember.status == 'CONFIRMED'))]}, 'members': [row(m) for m in s.scalars(select(LinkMember).where(LinkMember.patient_id == patient_id, LinkMember.status == 'CONFIRMED'))], 'records': [record_view(s, r, user.hospital_id) for r in s.scalars(query.order_by(CanonicalResource.resource_type, CanonicalResource.hospital_id))], 'conflicts': [row(c) for c in s.scalars(select(Conflict).where(Conflict.patient_id == patient_id, Conflict.active == True))]}

    @app.get('/api/patients/{patient_id}/timeline', tags=['History and provenance'])
    def timeline(patient_id: str, user=Depends(current_user)):
        with db.shared() as s:
            require_shared(s, user, patient_id)
            audit(s, user, 'READ_TIMELINE', patient_id)
            return [row(e) | {'fields': clinical_fields(e.after)} for e in s.scalars(select(ClinicalEvent).where(ClinicalEvent.patient_id == patient_id).order_by(ClinicalEvent.occurred_at.desc(), ClinicalEvent.source_version.desc()))]

    def authorized_resource(s, user, resource_id):
        resource = s.get(CanonicalResource, resource_id)
        if not resource:
            raise HTTPException(404, 'Record not found')
        require_shared(s, user, resource.patient_id)
        return resource

    @app.get('/api/records/{resource_id}', tags=['History and provenance'])
    def source_details(resource_id: str, user=Depends(current_user)):
        with db.shared() as s:
            resource = authorized_resource(s, user, resource_id)
            destination = ADAPTERS[user.hospital_id].from_canonical(resource.payload)
            versions = [row(v) | {'fields': clinical_fields(v.payload)} for v in s.scalars(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id).order_by(ResourceVersion.version.desc()))]
            events = list(s.scalars(select(ClinicalEvent).where(ClinicalEvent.resource_id == resource_id).order_by(ClinicalEvent.source_version.desc())))
            provenance = [row(p) for p in s.scalars(select(Provenance).where(Provenance.event_id.in_([e.id for e in events])))]
            audit(s, user, 'READ_SOURCE_AND_HISTORY', resource_id)
            return record_view(s, resource, user.hospital_id) | {'versions': versions, 'events': [row(e) for e in events], 'provenance': provenance, 'destination_preview': destination, 'preview_notice': 'Destination-compatible synthetic preview only. No EHR write-back.'}

    @app.get('/api/records/{resource_id}/compare', tags=['History and provenance'])
    def compare(resource_id: str, before: int = Query(ge=1), after: int = Query(ge=1), user=Depends(current_user)):
        with db.shared() as s:
            authorized_resource(s, user, resource_id)
            a = s.scalar(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id, ResourceVersion.version == before))
            b = s.scalar(select(ResourceVersion).where(ResourceVersion.resource_id == resource_id, ResourceVersion.version == after))
            if not a or not b:
                raise HTTPException(404, 'Version not found')
            audit(s, user, 'COMPARE_VERSIONS', resource_id)
            return {'before': a.payload, 'after': b.payload, 'diff': clinical_diff(a.payload, b.payload)}

    @app.get('/api/patients/{patient_id}/conflicts', tags=['Conflicts'])
    def conflicts(patient_id: str, user=Depends(current_user)):
        with db.shared() as s:
            require_shared(s, user, patient_id)
            audit(s, user, 'READ_CONFLICTS', patient_id)
            return [row(c) for c in s.scalars(select(Conflict).where(Conflict.patient_id == patient_id))]

    @app.get('/api/conflicts/{conflict_id}', tags=['Conflicts'])
    def conflict_detail(conflict_id: str, user=Depends(current_user)):
        with db.shared() as s:
            c = s.get(Conflict, conflict_id)
            if not c:
                raise HTTPException(404, 'Discrepancy not found')
            require_shared(s, user, c.patient_id)
            audit(s, user, 'READ_CONFLICT_DETAIL', conflict_id)
            return row(c) | {'records': [record_view(s, s.get(CanonicalResource, rid), user.hospital_id) for rid in c.record_ids]}

    @app.get('/api/local/patients', tags=['Hospital EHR simulator'])
    def local_patients(user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            ids = list(s.scalars(select(CareRelationship.local_patient_id).where(CareRelationship.hospital_id == user.hospital_id)))
            audit(s, user, 'READ_LOCAL_PATIENTS', user.hospital_id)
            return [row(p) for p in local.scalars(select(LocalPatient).where(LocalPatient.id.in_(ids)))]

    @app.get('/api/local/patients/{patient_id}', tags=['Hospital EHR simulator'])
    def local_patient(patient_id: str, user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            require_local(s, user, patient_id)
            p = local.get(LocalPatient, patient_id)
            if not p:
                raise HTTPException(404, 'Local patient not found')
            audit(s, user, 'READ_LOCAL_CHART', patient_id)
            records = []
            for r in local.scalars(select(LocalRecord).where(LocalRecord.patient_id == patient_id)):
                translated = ADAPTERS[user.hospital_id].to_canonical(r.payload, source_version=r.version)
                data, _ = ADAPTERS[user.hospital_id].unpack(r.payload)
                records.append(row(r) | {'fields': clinical_fields(translated.resource), 'canonical': translated.resource, 'warnings': translated.warnings, 'input': data})
            return row(p) | {'records': records, 'hospital_id': user.hospital_id}

    def clinical_source(body, user, patient_id, record_id):
        data = body.model_dump(exclude={'expected_version', 'category'})
        data.update(kind=body.category, id=record_id, patient=patient_id, recorded=now(), author=user.name)
        return ADAPTERS[user.hospital_id].pack(data)

    @app.post('/api/local/patients/{patient_id}/records', status_code=201, tags=['Hospital EHR simulator'])
    def create_local(patient_id: str, body: ClinicalInput, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            require_local(s, user, patient_id)
            rid = uid()
            payload = clinical_source(body, user, patient_id, rid)
            with db.local(user.hospital_id) as local:
                record, changed = ChangeDetectionService.save(local, user.hospital_id, patient_id, body.category, payload, user.name, rid)
                result = row(record)
            audit(s, user, 'CREATE_LOCAL_RECORD', rid)
            return result | {'outbox_pending': changed}

    def edit_local(record_id, body, user, event_type):
        require_clinician(user)
        with db.shared() as s, db.local(user.hospital_id) as local:
            record = local.get(LocalRecord, record_id)
            if not record:
                raise HTTPException(404, 'Local record not found')
            require_local(s, user, record.patient_id)
            if record.category == 'note':
                raise HTTPException(409, 'Approved notes require a new reviewed draft; they cannot be changed through the clinical-entry editor')
            payload = clinical_source(body, user, record.patient_id, record.id)
            # Preserve documented author/date changes while the semantic diff ignores transport metadata.
            if event_type == 'UPDATED':
                old, _ = ADAPTERS[user.hospital_id].unpack(record.payload)
                candidate, _ = ADAPTERS[user.hospital_id].unpack(payload)
                if {k: v for k, v in old.items() if k not in ('recorded', 'author')} == {k: v for k, v in candidate.items() if k not in ('recorded', 'author')}:
                    payload = record.payload
            record, changed = ChangeDetectionService.save(local, user.hospital_id, record.patient_id, body.category, payload, user.name, record.id, body.expected_version, event_type)
            audit(s, user, event_type + '_LOCAL_RECORD', record_id)
            return row(record) | {'outbox_pending': changed}

    @app.put('/api/local/records/{record_id}', tags=['Hospital EHR simulator'])
    def update_local(record_id: str, body: ClinicalInput, user=Depends(current_user)):
        return edit_local(record_id, body, user, 'UPDATED')

    @app.post('/api/local/records/{record_id}/correct', tags=['Hospital EHR simulator'])
    def correct_local(record_id: str, body: ClinicalInput, user=Depends(current_user)):
        return edit_local(record_id, body, user, 'CORRECTED')

    @app.post('/api/local/records/{record_id}/withdraw', tags=['Hospital EHR simulator'])
    def withdraw_local(record_id: str, body: WithdrawInput, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s, db.local(user.hospital_id) as local:
            record = local.get(LocalRecord, record_id)
            if not record:
                raise HTTPException(404, 'Local record not found')
            require_local(s, user, record.patient_id)
            d, _ = ADAPTERS[user.hospital_id].unpack(record.payload)
            d.update(status={'medication': 'stopped', 'allergy': 'inactive', 'diagnosis': 'inactive', 'lab': 'cancelled', 'vaccination': 'entered-in-error', 'note': 'entered-in-error'}[record.category], note=body.note, recorded=now(), author=user.name)
            record, changed = ChangeDetectionService.save(local, user.hospital_id, record.patient_id, record.category, ADAPTERS[user.hospital_id].pack(d), user.name, record_id, body.expected_version, 'WITHDRAWN')
            audit(s, user, 'WITHDRAW_LOCAL_RECORD', record_id)
            return row(record)

    @app.get('/api/local/records/{record_id}/history', tags=['Hospital EHR simulator'])
    def local_history(record_id: str, user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            record = local.get(LocalRecord, record_id)
            if not record:
                raise HTTPException(404, 'Local record not found')
            require_local(s, user, record.patient_id)
            audit(s, user, 'READ_LOCAL_HISTORY', record_id)
            return [row(v) for v in local.scalars(select(LocalVersion).where(LocalVersion.record_id == record_id).order_by(LocalVersion.version.desc()))]

    def review_view(s, review, user):
        event = s.get(ClinicalEvent, review.event_id)
        resource = s.get(CanonicalResource, event.resource_id)
        # Compare with the destination's documented chart, including an explicit empty state.
        local_comparison = []
        with db.local(user.hospital_id) as local:
            member = s.scalar(select(LinkMember).where(LinkMember.patient_id == event.patient_id, LinkMember.hospital_id == user.hospital_id, LinkMember.status == 'CONFIRMED'))
            for r in local.scalars(select(LocalRecord).where(LocalRecord.patient_id == member.local_patient_id, LocalRecord.category == REVERSE_KINDS[event.resource_type])):
                canonical = ADAPTERS[user.hospital_id].to_canonical(r.payload, event.patient_id).resource
                local_comparison.append({'record_id': r.id, 'fields': clinical_fields(canonical), 'diff': clinical_diff(canonical, event.after)})
        decisions = [row(d) | {'reviewer': s.get(User, d.user_id).name} for d in s.scalars(select(ReviewDecision).where(ReviewDecision.review_id == review.id).order_by(ReviewDecision.created_at.desc()))]
        return row(review) | {'event': row(event), 'fields': clinical_fields(event.after), 'patient': row(s.get(PatientLink, event.patient_id)) | {'local_patient_id': member.local_patient_id}, 'source': row(s.get(Hospital, event.hospital_id)), 'warnings': next((v.warnings for v in s.scalars(select(ResourceVersion).where(ResourceVersion.resource_id == resource.id, ResourceVersion.version == event.source_version))), []), 'conflicts': [row(c) for c in s.scalars(select(Conflict).where(Conflict.patient_id == event.patient_id, Conflict.active == True)) if resource.id in c.record_ids], 'decisions': decisions, 'local_comparison': local_comparison, 'current_source_version': resource.source_version, 'is_current_source_version': event.source_version == resource.source_version, 'delivery_status': 'DELIVERED'}

    def get_review(s, user, review_id):
        item = s.get(ReviewItem, review_id)
        if not item:
            raise HTTPException(404, 'Review item not found')
        if item.hospital_id != user.hospital_id:
            raise HTTPException(403, 'Review belongs to another hospital')
        require_shared(s, user, s.get(ClinicalEvent, item.event_id).patient_id)
        return item

    @app.get('/api/reviews', tags=['Clinical reviews'])
    def reviews(status: str | None = None, user=Depends(current_user)):
        with db.shared() as s:
            ids = authorized_patient_ids(s, user)
            query = select(ReviewItem).join(ClinicalEvent).where(ReviewItem.hospital_id == user.hospital_id, ClinicalEvent.patient_id.in_(ids)).order_by(ClinicalEvent.ingested_at.desc())
            if status:
                query = query.where(ReviewItem.status == status)
            audit(s, user, 'READ_REVIEW_QUEUE', user.hospital_id)
            return [review_view(s, r, user) for r in s.scalars(query)]

    @app.get('/api/reviews/{review_id}', tags=['Clinical reviews'])
    def review_detail(review_id: str, user=Depends(current_user)):
        with db.shared() as s:
            item = get_review(s, user, review_id)
            audit(s, user, 'READ_REVIEW', review_id)
            return review_view(s, item, user)

    @app.post('/api/reviews/{review_id}/decisions', tags=['Clinical reviews'])
    def decide(review_id: str, body: ReviewInput, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            item = get_review(s, user, review_id)
            result = s.execute(update(ReviewItem).where(ReviewItem.id == review_id, ReviewItem.revision == body.expected_revision).values(status=body.decision, revision=body.expected_revision + 1))
            if result.rowcount != 1:
                raise HTTPException(409, 'Review changed. Refresh before deciding.')
            s.add(ReviewDecision(review_id=review_id, user_id=user.id, decision=body.decision, note=body.note))
            audit(s, user, 'REVIEW_' + body.decision, review_id)
            s.flush()
            s.refresh(item)
            return review_view(s, item, user) | {'ehr_updated': False}

    @app.get('/api/patients/{patient_id}/identity', tags=['Identity'])
    def patient_identity(patient_id: str, user=Depends(current_user)):
        with db.shared() as s:
            require_shared(s, user, patient_id)
            audit(s, user, 'READ_IDENTITY_LINKS', patient_id)
            return [row(m) for m in s.scalars(select(LinkMember).where(LinkMember.patient_id == patient_id, LinkMember.status == 'CONFIRMED'))]

    @app.get('/api/identity/candidates', tags=['Identity'])
    def identity_candidates(user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            audit(s, user, 'READ_IDENTITY_CANDIDATES', 'candidates')
            return [row(c) | {'member': row(s.get(LinkMember, c.member_id))} for c in s.scalars(select(IdentityCandidate))]

    @app.post('/api/identity/candidates/{candidate_id}/decision', tags=['Identity'])
    def identity_decide(candidate_id: str, body: IdentityInput, user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            candidate = s.scalar(select(IdentityCandidate).where(IdentityCandidate.id == candidate_id).with_for_update())
            if not candidate:
                raise HTTPException(404, 'Candidate not found')
            if candidate.status != 'PENDING_REVIEW':
                raise HTTPException(409, 'Identity candidate already reviewed')
            candidate.status, candidate.note, candidate.reviewed_by, candidate.reviewed_at = body.decision, body.note, user.id, now()
            member = s.get(LinkMember, candidate.member_id)
            if body.decision == 'CONFIRMED' and candidate.target_patient_id and member.patient_id != candidate.target_patient_id:
                if s.scalar(select(CanonicalResource).where(CanonicalResource.patient_id == member.patient_id)):
                    raise HTTPException(409, 'This identity already has published clinical history. Linking requires an identity-reconciliation workflow; no records were moved.')
                if s.scalar(select(LinkMember).where(LinkMember.patient_id == candidate.target_patient_id, LinkMember.hospital_id == member.hospital_id, LinkMember.status == 'CONFIRMED')):
                    raise HTTPException(409, 'The target identity already has a confirmed patient identifier for this hospital')
                member.patient_id = candidate.target_patient_id
            elif candidate.target_patient_id and body.decision == 'REJECTED':
                # Rejecting a proposed cross-hospital link must preserve the existing local identity.
                audit(s, user, 'IDENTITY_REJECTED', candidate.id)
                return {'status': body.decision, 'patient_id': member.patient_id}
            member.status, member.reviewed_by = body.decision, user.id
            member.evidence = 'Manual administrator review: ' + body.note
            patient_id = member.patient_id
            audit(s, user, 'IDENTITY_' + body.decision, candidate.id)
        if body.decision == 'CONFIRMED':
            SynchronizationService(db).run(member.hospital_id)
            SynchronizationService(db).backfill_deliveries(patient_id)
        return {'status': body.decision, 'patient_id': patient_id}

    @app.get('/api/sync', tags=['Synchronization'])
    def sync_status(user=Depends(current_user)):
        sources = []
        with db.shared() as s:
            audit(s, user, 'READ_SYNC_STATUS', user.hospital_id)
            for hospital in s.scalars(select(Hospital)):
                jobs = list(s.scalars(select(SyncJob).where(SyncJob.hospital_id == hospital.id).order_by(SyncJob.started_at.desc()).limit(15)))
                success = s.scalar(select(SyncJob).where(SyncJob.hospital_id == hospital.id, SyncJob.status == 'SUCCEEDED').order_by(SyncJob.completed_at.desc()))
                with db.local(hospital.id) as local:
                    pending = local.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state == 'PENDING'))
                    failed = local.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state == 'FAILED'))
                    waiting = local.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state == 'WAITING_IDENTITY'))
                    observed = local.scalar(select(func.max(LocalRecord.updated_at)))
                sources.append(row(hospital) | {'last_successful_sync': success.completed_at if success else None, 'last_observed_source_update': observed, 'latest_job': row(jobs[0]) if jobs else None, 'pending': pending, 'failed': failed, 'waiting_identity': waiting, 'freshness': 'FAILED' if failed else 'UPDATES_PENDING' if pending else 'PARTIAL_COVERAGE' if waiting else 'CURRENT', 'jobs': [row(j) for j in jobs]})
            ids = authorized_patient_ids(s, user)
            deliveries = [row(d) for d in s.scalars(select(DeliveryEvent).join(ClinicalEvent).where(DeliveryEvent.hospital_id == user.hospital_id, ClinicalEvent.patient_id.in_(ids)))]
            with db.local(user.hospital_id) as local:
                allowed_local = list(s.scalars(select(CareRelationship.local_patient_id).where(CareRelationship.hospital_id == user.hospital_id)))
                failures = [{k: v for k, v in row(e).items() if k not in ('payload', 'lineage')} for e in local.scalars(select(OutboxEvent).where(OutboxEvent.state.in_(['FAILED', 'WAITING_IDENTITY']), OutboxEvent.patient_id.in_(allowed_local)))]
            return {'sources': sources, 'deliveries': deliveries, 'outbox_attention': failures}

    def demo_only():
        if not settings.demo_mode:
            raise HTTPException(403, 'Development controls are disabled outside demo mode')

    @app.post('/api/sync', tags=['Synchronization'])
    def sync_now(user=Depends(current_user)):
        demo_only()
        hospitals = [user.hospital_id]
        result = [SynchronizationService(db).run(h) for h in hospitals]
        with db.shared() as s:
            audit(s, user, 'TRIGGER_SYNC', ','.join(hospitals))
        return result

    @app.get('/api/dashboard', tags=['Dashboard'])
    def dashboard(user=Depends(current_user)):
        with db.shared() as s:
            audit(s, user, 'READ_DASHBOARD', user.hospital_id)
            ids = authorized_patient_ids(s, user)
            queue = list(s.scalars(select(ReviewItem).join(ClinicalEvent).where(ReviewItem.hospital_id == user.hospital_id, ClinicalEvent.patient_id.in_(ids))))
            recent = list(s.scalars(select(ClinicalEvent).where(ClinicalEvent.patient_id.in_(ids)).order_by(ClinicalEvent.ingested_at.desc()).limit(6)))
            return {'hospital': row(s.get(Hospital, user.hospital_id)), 'linked_patients': len(ids), 'incoming_updates': len(queue), 'pending_reviews': len([r for r in queue if r.status in ('PENDING_REVIEW', 'DEFERRED', 'INVESTIGATING')]), 'discrepancies': s.scalar(select(func.count()).select_from(Conflict).where(Conflict.patient_id.in_(ids), Conflict.active == True, Conflict.category != 'CLINICALLY_EQUIVALENT')), 'recent_events': [row(e) | {'fields': clinical_fields(e.after), 'patient_name': s.get(PatientLink, e.patient_id).name} for e in recent]}

    @app.post('/api/demo/scenario', tags=['Demo controls'])
    def scenario(user=Depends(current_user)):
        demo_only()
        if user.role != 'admin' and user.hospital_id != 'northstar':
            raise HTTPException(403, 'Switch to the originating Northstar account to edit its chart')
        with db.shared() as s:
            audit(s, user, 'DEMO_ALLERGY_CORRECTION', 'allergy-penicillin')
        return simulate_allergy_update(db)

    @app.post('/api/demo/replay', tags=['Demo controls'])
    def replay(user=Depends(current_user)):
        demo_only()
        require_admin(user)
        with db.local('northstar') as local:
            e = local.scalar(select(OutboxEvent).where(OutboxEvent.record_id == 'allergy-penicillin').order_by(OutboxEvent.source_version.desc()))
            e.state = 'PENDING'
        with db.shared() as s:
            audit(s, user, 'REPLAY_SOURCE_EVENT', e.id)
        return SynchronizationService(db).run('northstar')

    @app.post('/api/demo/seed', tags=['Demo controls'])
    def seed_demo(user=Depends(current_user)):
        demo_only()
        require_admin(user)
        return {'seeded': seed(db)}

    @app.post('/api/demo/reset', tags=['Demo controls'])
    def reset(body: ResetInput, response: Response, user=Depends(current_user)):
        demo_only()
        require_admin(user)
        if settings.extra_hospitals:
            raise HTTPException(403, 'Demo reset cannot run when additional hospital stores are configured')
        urls = [(settings.shared_url, 'clinicalsync_shared'), (settings.hospital_a_url, 'clinicalsync_northstar'), (settings.hospital_b_url, 'clinicalsync_riverside')]
        for url, expected in urls:
            parsed = make_url(url)
            name = PurePosixPath((parsed.database or '').replace('\\', '/')).name
            if name not in (expected, expected + '.db'):
                raise HTTPException(403, 'Reset is restricted to explicitly named ClinicalSync synthetic demo databases')
            expected_host = {'clinicalsync_shared': 'shared-db', 'clinicalsync_northstar': 'northstar-db', 'clinicalsync_riverside': 'riverside-db'}[expected]
            if parsed.host and parsed.host not in ('localhost', '127.0.0.1', '::1', expected_host):
                raise HTTPException(403, 'Reset cannot target external database hosts')
        with db.shared() as s:
            if s.scalar(select(func.count()).select_from(PatientLink).where(PatientLink.synthetic == False)):
                raise HTTPException(403, 'Reset refuses databases containing non-synthetic patients')
        for hospital in ('northstar', 'riverside'):
            with db.local(hospital) as local:
                if local.scalar(select(func.count()).select_from(LocalPatient).where(LocalPatient.synthetic == False)):
                    raise HTTPException(403, 'Reset refuses databases containing non-synthetic patients')
        # Only these three explicitly named databases can be recreated.
        for engine in db.local_engines.values():
            LocalBase.metadata.drop_all(engine)
        SharedBase.metadata.drop_all(db.shared_engine)
        db.create_schema()
        seed(db)
        with db.shared() as s:
            audit(s, s.get(User, 'admin'), 'DEMO_RESET_COMPLETED', 'synthetic-demo')
        response.delete_cookie('clinicalsync_session', path='/')
        return {'reset': True, 'signed_out': True}

    @app.get('/api/audit', tags=['Audit'])
    def audit_history(user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            return [row(e) for e in s.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100))]

    from .workspace import build_workspace_router
    app.include_router(build_workspace_router(db, settings))
    return app


app = create_app()
