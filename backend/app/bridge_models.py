"""Persisted EHR Bridge workflows. Clinical sources remain in the existing stores."""
from sqlalchemy import ForeignKey, JSON, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from .models import SharedBase, immutable, now, uid


class EHRConnection(SharedBase):
    __tablename__ = 'bridge_ehr_connections'
    id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'), primary_key=True)
    vendor: Mapped[str]
    adapter: Mapped[str]
    status: Mapped[str] = mapped_column(default='CONNECTED')
    department: Mapped[str] = mapped_column(default='Internal Medicine')
    supported_categories: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[str] = mapped_column(default=now)


class BridgePatient(SharedBase):
    __tablename__ = 'bridge_patients'
    id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), primary_key=True)
    portal_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), unique=True, nullable=True)
    demographics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(default=now)


class PreservedRecord(SharedBase):
    __tablename__ = 'bridge_preserved_records'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    category: Mapped[str]
    display: Mapped[str]
    normalized: Mapped[dict] = mapped_column(JSON)
    original: Mapped[dict] = mapped_column(JSON)
    verification: Mapped[str]
    author: Mapped[str]
    recorded_at: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)


class PreservedVersion(SharedBase):
    __tablename__ = 'bridge_preserved_versions'
    __table_args__ = (UniqueConstraint('record_id', 'version'),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    record_id: Mapped[str] = mapped_column(ForeignKey('bridge_preserved_records.id'), index=True)
    version: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class EncounterSession(SharedBase):
    __tablename__ = 'bridge_encounters'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    reason: Mapped[str]
    status: Mapped[str] = mapped_column(default='DRAFT')
    intake: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)
    completed_at: Mapped[str | None] = mapped_column(nullable=True)


class EncounterVersion(SharedBase):
    __tablename__ = 'bridge_encounter_versions'
    __table_args__ = (UniqueConstraint('encounter_id', 'revision'),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    encounter_id: Mapped[str] = mapped_column(ForeignKey('bridge_encounters.id'), index=True)
    revision: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[str] = mapped_column(default=now)


class SessionTask(SharedBase):
    __tablename__ = 'bridge_session_tasks'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey('bridge_encounters.id'), index=True)
    kind: Mapped[str]
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default='TODO')
    updated_at: Mapped[str] = mapped_column(default=now)


class VoiceMemo(SharedBase):
    __tablename__ = 'bridge_voice_memos'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey('bridge_encounters.id'), index=True)
    transcript: Mapped[str]
    source: Mapped[str]
    suggestions: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class IntakeQuestion(SharedBase):
    __tablename__ = 'bridge_intake_questions'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey('bridge_encounters.id'), index=True)
    label: Mapped[str]
    kind: Mapped[str]
    options: Mapped[list] = mapped_column(JSON, default=list)


class IntakeAnswer(SharedBase):
    __tablename__ = 'bridge_intake_answers'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    question_id: Mapped[str] = mapped_column(ForeignKey('bridge_intake_questions.id'), unique=True)
    value: Mapped[dict] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(default='Doctor-entered patient report')


class AccessRequest(SharedBase):
    __tablename__ = 'bridge_access_requests'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    source_hospitals: Mapped[list] = mapped_column(JSON)
    categories: Mapped[list] = mapped_column(JSON)
    purpose: Mapped[str]
    encounter_reason: Mapped[str]
    duration_hours: Mapped[int]
    state: Mapped[str] = mapped_column(default='PENDING')
    patient_message: Mapped[str] = mapped_column(default='')
    created_at: Mapped[str] = mapped_column(default=now)
    expires_at: Mapped[str]


class OneTimeCode(SharedBase):
    __tablename__ = 'bridge_one_time_codes'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey('bridge_access_requests.id'), unique=True)
    code_hash: Mapped[str]
    expires_at: Mapped[str]
    attempts: Mapped[int] = mapped_column(default=0)
    used_at: Mapped[str | None] = mapped_column(nullable=True)


class AccessGrant(SharedBase):
    __tablename__ = 'bridge_access_grants'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey('bridge_access_requests.id'), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    source_hospitals: Mapped[list] = mapped_column(JSON)
    categories: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
    expires_at: Mapped[str]
    revoked_at: Mapped[str | None] = mapped_column(nullable=True)


class ExchangeEvent(SharedBase):
    __tablename__ = 'bridge_exchange_events'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'))
    grant_id: Mapped[str] = mapped_column(ForeignKey('bridge_access_grants.id'))
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    source_hospital_id: Mapped[str]
    destination_hospital_id: Mapped[str]
    record_id: Mapped[str]
    category: Mapped[str]
    translation_result: Mapped[str]
    delivery_result: Mapped[str] = mapped_column(default='AVAILABLE_IN_WORKSPACE')
    preserved_fields: Mapped[list] = mapped_column(JSON, default=list)
    source_version: Mapped[int]
    created_at: Mapped[str] = mapped_column(default=now)


class BridgeRecordReview(SharedBase):
    __tablename__ = 'bridge_record_reviews'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    record_id: Mapped[str] = mapped_column(index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'))
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str]
    note: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class InsuranceVerification(SharedBase):
    __tablename__ = 'bridge_insurance_verifications'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey('bridge_encounters.id'), index=True)
    input: Mapped[dict] = mapped_column(JSON)
    results: Mapped[list] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(default='Simulated payer response; not verified coverage or guaranteed payment')
    created_at: Mapped[str] = mapped_column(default=now)


for model in (PreservedVersion, EncounterVersion, ExchangeEvent, VoiceMemo, InsuranceVerification, BridgeRecordReview):
    event.listen(model, 'before_update', immutable)
    event.listen(model, 'before_delete', immutable)
