from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update

from .adapters import ADAPTERS, DEMO_SYSTEM
from .documentation import OpenAITranscriptionProvider, note_provider, provider_status
from .models import AuditEvent, LocalRecord, LocalTimelineEvent, NoteDraft, now
from .schemas import NoteApproveInput, NoteDraftInput, NoteDraftUpdate, NoteGenerateInput, RecordingEventInput
from .security import audit, current_user, require_clinician, require_local
from .services import ChangeDetectionService


def row(obj):
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def add_note_routes(router: APIRouter, db, settings):
    def retention_expiry():
        return (datetime.now(timezone.utc) + timedelta(days=settings.transcript_retention_days)).isoformat() if settings.transcript_retention_days else None

    def purge_expired(local):
        local.execute(update(NoteDraft).where(NoteDraft.transcript_expires_at < now(), NoteDraft.transcript.is_not(None)).values(transcript=None))

    def authorized_draft(s, local, user, draft_id):
        draft = local.get(NoteDraft, draft_id)
        if not draft:
            raise HTTPException(404, 'Note draft not found')
        require_local(s, user, draft.patient_id)
        if draft.author_id != user.id:
            raise HTTPException(403, 'Unapproved note drafts are private to their author')
        return draft

    @router.get('/notes/config', tags=['Clinical documentation'])
    def documentation_config(user=Depends(current_user)):
        return provider_status(settings)

    @router.post('/local/patients/{patient_id}/recording-events', tags=['Clinical documentation'])
    def recording_event(patient_id: str, body: RecordingEventInput, user=Depends(current_user)):
        require_clinician(user)
        target = f'{patient_id}/recording/{body.recording_id}'
        with db.shared() as s:
            require_local(s, user, patient_id)
            recorded = set(s.scalars(select(AuditEvent.action).where(AuditEvent.user_id == user.id, AuditEvent.hospital_id == user.hospital_id, AuditEvent.target == target)))
            if body.action != 'STARTED' and 'RECORDING_STARTED' not in recorded:
                raise HTTPException(409, 'Start a consent-confirmed recording session before stopping or cancelling')
            action = 'RECORDING_' + body.action
            if action not in recorded:
                if body.action == 'STARTED':
                    audit(s, user, 'RECORDING_CONSENT_CONFIRMED', target)
                audit(s, user, action, target)
            return {'recorded': True, 'action': body.action, 'audio_stored': False}

    @router.get('/local/patients/{patient_id}/note-drafts', tags=['Clinical documentation'])
    def list_drafts(patient_id: str, user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            require_local(s, user, patient_id)
            purge_expired(local)
            audit(s, user, 'READ_NOTE_DRAFTS', patient_id)
            return [row(draft) for draft in local.scalars(select(NoteDraft).where(NoteDraft.patient_id == patient_id, NoteDraft.author_id == user.id).order_by(NoteDraft.updated_at.desc()))]

    @router.post('/local/patients/{patient_id}/note-drafts', status_code=201, tags=['Clinical documentation'])
    def create_draft(patient_id: str, body: NoteDraftInput, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s, db.local(user.hospital_id) as local:
            require_local(s, user, patient_id)
            purge_expired(local)
            draft = NoteDraft(patient_id=patient_id, author_id=user.id, author_name=user.name, title=body.title.strip(), transcript=body.transcript if settings.transcript_retention_days else None, transcript_expires_at=retention_expiry(), sections=body.sections.model_dump(), status='DRAFT', revision=1, generation_provider='manual', generation_warnings=[])
            local.add(draft)
            local.flush()
            audit(s, user, 'NOTE_DRAFT_CREATED', draft.id)
            return row(draft)

    @router.put('/note-drafts/{draft_id}', tags=['Clinical documentation'])
    def save_draft(draft_id: str, body: NoteDraftUpdate, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s, db.local(user.hospital_id) as local:
            draft = authorized_draft(s, local, user, draft_id)
            result = local.execute(update(NoteDraft).where(NoteDraft.id == draft.id, NoteDraft.status == 'DRAFT', NoteDraft.revision == body.expected_revision).values(title=body.title.strip(), transcript=body.transcript if settings.transcript_retention_days else None, transcript_expires_at=retention_expiry(), sections=body.sections.model_dump(), revision=body.expected_revision + 1, updated_at=now()))
            if result.rowcount != 1:
                raise HTTPException(409, 'The draft changed or was already approved. Reload before saving.')
            local.refresh(draft)
            audit(s, user, 'NOTE_DRAFT_SAVED', draft.id)
            return row(draft)

    @router.post('/note-drafts/{draft_id}/generate', tags=['Clinical documentation'])
    def generate_draft(draft_id: str, body: NoteGenerateInput, user=Depends(current_user)):
        require_clinician(user)
        # Do not hold database write locks during an external provider request.
        with db.shared() as s, db.local(user.hospital_id) as local:
            purge_expired(local)
            draft = authorized_draft(s, local, user, draft_id)
            if draft.status != 'DRAFT' or draft.revision != body.expected_revision:
                raise HTTPException(409, 'Reload the current unapproved draft before generating')
            transcript = body.transcript if body.transcript is not None else draft.transcript
            if not transcript or not transcript.strip():
                raise HTTPException(422, 'Enter or upload a source transcript. Expired transcripts must be supplied again.')
            if settings.note_provider != 'local' and not body.external_processing_consent:
                raise HTTPException(403, 'Explicit authorization for external transcript processing is required')
            audit(s, user, 'NOTE_DRAFT_GENERATION_REQUESTED', draft.id)
        sections, warnings = note_provider(settings).generate(transcript)
        with db.shared() as s, db.local(user.hospital_id) as local:
            draft = authorized_draft(s, local, user, draft_id)
            result = local.execute(update(NoteDraft).where(NoteDraft.id == draft_id, NoteDraft.status == 'DRAFT', NoteDraft.revision == body.expected_revision).values(sections=sections, transcript=transcript if settings.transcript_retention_days else None, transcript_expires_at=retention_expiry(), generation_provider=settings.note_provider, generation_warnings=warnings, revision=body.expected_revision + 1, updated_at=now()))
            if result.rowcount != 1:
                raise HTTPException(409, 'The draft changed during generation. Your newer draft was preserved.')
            local.refresh(draft)
            audit(s, user, 'NOTE_DRAFT_GENERATED', draft_id)
            return row(draft)

    @router.post('/note-drafts/{draft_id}/approve', tags=['Clinical documentation'])
    def approve_draft(draft_id: str, body: NoteApproveInput, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s, db.local(user.hospital_id) as local:
            draft = authorized_draft(s, local, user, draft_id)
            if draft.status == 'APPROVED':
                return row(draft) | {'already_approved': True, 'local_record_id': draft.record_id, 'external_ehr_written': False}
            if not any(text.strip() for text in draft.sections.values()):
                raise HTTPException(422, 'An empty note cannot be approved')
            timestamp = now()
            result = local.execute(update(NoteDraft).where(NoteDraft.id == draft_id, NoteDraft.status == 'DRAFT', NoteDraft.revision == body.expected_revision).values(status='APPROVED', revision=body.expected_revision + 1, approved_by=user.name, approved_at=timestamp, updated_at=timestamp))
            if result.rowcount != 1:
                raise HTTPException(409, 'The draft changed. Review the latest version before approving.')
            local.refresh(draft)
            record_id = 'note-' + draft.id
            payload = ADAPTERS[user.hospital_id].pack({'id': record_id, 'patient': draft.patient_id, 'kind': 'note', 'display': draft.title, 'code': 'SOAP_NOTE', 'system': DEMO_SYSTEM, 'status': 'current', 'effective': timestamp, 'recorded': timestamp, 'author': user.name, 'sections': draft.sections, 'approved_by': user.name, 'approved_at': timestamp, 'note': 'Explicitly reviewed and approved by the authenticated clinician. Approval applies to this development hospital chart.'})
            record, _ = ChangeDetectionService.save(local, user.hospital_id, draft.patient_id, 'note', payload, user.name, record_id)
            draft.record_id = record.id
            local.add(LocalTimelineEvent(patient_id=draft.patient_id, event_type='NOTE_APPROVED', description=draft.title + ' approved by the clinician', author=user.name, occurred_at=timestamp, record_id=record_id))
            audit(s, user, 'CLINICAL_NOTE_APPROVED', record_id)
            return row(draft) | {'already_approved': False, 'local_record_id': record_id, 'external_ehr_written': False}

    @router.post('/local/patients/{patient_id}/transcriptions', tags=['Clinical documentation'])
    async def transcribe(patient_id: str, request: Request, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            require_local(s, user, patient_id)
        if request.headers.get('x-recording-consent') != 'true':
            raise HTTPException(403, 'Recording consent must be confirmed before processing audio')
        if settings.transcription_provider == 'manual':
            raise HTTPException(503, 'Audio transcription is not configured. Enter or upload a test transcript; recordings are never replaced with fabricated text.')
        if request.headers.get('x-external-processing-consent') != 'true':
            raise HTTPException(403, 'External audio processing requires explicit authorization')
        content_type = request.headers.get('content-type', '').split(';')[0].lower()
        if content_type not in ('audio/webm', 'audio/ogg', 'audio/wav', 'audio/mpeg', 'audio/mp4'):
            raise HTTPException(415, 'Unsupported recording type. Use WebM, Ogg, WAV, MP3, or M4A audio.')
        audio = bytearray()
        async for chunk in request.stream():
            if len(audio) + len(chunk) > settings.audio_max_bytes:
                raise HTTPException(413, 'Recording exceeds the configured audio size limit')
            audio.extend(chunk)
        if not audio:
            raise HTTPException(422, 'The recording is empty')
        with db.shared() as s:
            audit(s, user, 'AUDIO_TRANSCRIPTION_AUTHORIZED', patient_id)
        from starlette.concurrency import run_in_threadpool
        text = await run_in_threadpool(OpenAITranscriptionProvider(settings).transcribe, bytes(audio), content_type)
        with db.shared() as s:
            audit(s, user, 'AUDIO_TRANSCRIBED', patient_id)
        return {'transcript': text, 'provider': settings.transcription_provider, 'audio_stored': False}
