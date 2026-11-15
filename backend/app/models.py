from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def uid():
    return str(uuid4())


class SharedBase(DeclarativeBase):
    pass


class LocalBase(DeclarativeBase):
    pass


class Hospital(SharedBase):
    __tablename__ = 'hospitals'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    ehr: Mapped[str]


class User(SharedBase):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str]
    password_hash: Mapped[str]
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    role: Mapped[str]


class SessionToken(SharedBase):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    csrf: Mapped[str]
    expires_at: Mapped[str]
    active_hospital_id: Mapped[str | None] = mapped_column(ForeignKey('hospitals.id'), nullable=True)


class HospitalMembership(SharedBase):
    __tablename__ = 'hospital_memberships'
    __table_args__ = (UniqueConstraint('user_id', 'hospital_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    role: Mapped[str]
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PatientLink(SharedBase):
    __tablename__ = 'patient_links'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    birth_date: Mapped[str]
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class LinkMember(SharedBase):
    __tablename__ = 'patient_link_members'
    __table_args__ = (UniqueConstraint('hospital_id', 'local_patient_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    local_patient_id: Mapped[str]
    status: Mapped[str]
    evidence: Mapped[str]
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)


class CareRelationship(SharedBase):
    __tablename__ = 'patient_care_relationships'
    __table_args__ = (UniqueConstraint('hospital_id', 'local_patient_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    local_patient_id: Mapped[str]
    reason: Mapped[str]


class IdentityCandidate(SharedBase):
    __tablename__ = 'identity_review_candidates'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey('patient_link_members.id'))
    status: Mapped[str] = mapped_column(default='PENDING_REVIEW')
    evidence: Mapped[dict] = mapped_column(JSON)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(nullable=True)
    note: Mapped[str] = mapped_column(default='')
    target_patient_id: Mapped[str | None] = mapped_column(ForeignKey('patient_links.id'), nullable=True)


class SourceRecord(SharedBase):
    __tablename__ = 'source_records'
    __table_args__ = (UniqueConstraint('hospital_id', 'source_record_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    source_record_id: Mapped[str]
    local_patient_id: Mapped[str]
    latest_version: Mapped[int] = mapped_column(Integer)
    last_observed_at: Mapped[str]


class CanonicalResource(SharedBase):
    __tablename__ = 'canonical_resources'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('source_records.id'), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'), index=True)
    local_patient_id: Mapped[str]
    resource_type: Mapped[str] = mapped_column(index=True)
    source_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str]
    effective_at: Mapped[str] = mapped_column(index=True)
    updated_at: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    original_payload: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON)


class ResourceVersion(SharedBase):
    __tablename__ = 'canonical_resource_versions'
    __table_args__ = (UniqueConstraint('resource_id', 'version'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    resource_id: Mapped[str] = mapped_column(ForeignKey('canonical_resources.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    original_payload: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON)


class ClinicalEvent(SharedBase):
    __tablename__ = 'clinical_events'
    __table_args__ = (UniqueConstraint('hospital_id', 'source_record_id', 'source_version'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    source_record_id: Mapped[str]
    resource_id: Mapped[str] = mapped_column(ForeignKey('canonical_resources.id'))
    resource_type: Mapped[str]
    source_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str]
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict] = mapped_column(JSON)
    diff: Mapped[list] = mapped_column(JSON)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('clinical_events.id'), nullable=True)
    author: Mapped[str]
    occurred_at: Mapped[str]
    ingested_at: Mapped[str] = mapped_column(default=now)
    transformation_version: Mapped[str]
    correlation_id: Mapped[str]
    lineage: Mapped[list] = mapped_column(JSON)
    fingerprint: Mapped[str]


class Provenance(SharedBase):
    __tablename__ = 'provenance_records'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey('clinical_events.id'), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)


class SyncJob(SharedBase):
    __tablename__ = 'synchronization_jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'), index=True)
    started_at: Mapped[str] = mapped_column(default=now)
    completed_at: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str]
    published: Mapped[int] = mapped_column(Integer, default=0)
    suppressed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    waiting: Mapped[int] = mapped_column(Integer, default=0)


class DeliveryEvent(SharedBase):
    __tablename__ = 'delivery_events'
    __table_args__ = (UniqueConstraint('event_id', 'hospital_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey('clinical_events.id'))
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    state: Mapped[str] = mapped_column(default='DELIVERED')
    delivered_at: Mapped[str] = mapped_column(default=now)


class ReviewItem(SharedBase):
    __tablename__ = 'review_items'
    __table_args__ = (UniqueConstraint('event_id', 'hospital_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(ForeignKey('clinical_events.id'), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'), index=True)
    status: Mapped[str] = mapped_column(default='PENDING_REVIEW')
    revision: Mapped[int] = mapped_column(Integer, default=1)


class ReviewDecision(SharedBase):
    __tablename__ = 'review_decisions'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(ForeignKey('review_items.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    decision: Mapped[str]
    note: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class Conflict(SharedBase):
    __tablename__ = 'clinical_conflicts'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patient_links.id'), index=True)
    record_ids: Mapped[list] = mapped_column(JSON)
    category: Mapped[str]
    differences: Mapped[list] = mapped_column(JSON)
    explanation: Mapped[str]
    detected_at: Mapped[str] = mapped_column(default=now)
    status: Mapped[str] = mapped_column(default='REVIEW_REQUIRED')
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditEvent(SharedBase):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str]
    target: Mapped[str]
    hospital_id: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)


class LocalPatient(LocalBase):
    __tablename__ = 'patients'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    birth_date: Mapped[str]
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    first_name: Mapped[str] = mapped_column(default='')
    last_name: Mapped[str] = mapped_column(default='')
    administrative_gender: Mapped[str] = mapped_column(default='unknown')
    contact: Mapped[str] = mapped_column(default='')
    care_status: Mapped[str] = mapped_column(default='active')
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class NoteDraft(LocalBase):
    __tablename__ = 'clinical_note_drafts'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    author_id: Mapped[str]
    author_name: Mapped[str]
    title: Mapped[str] = mapped_column(default='Consultation note')
    transcript: Mapped[str | None] = mapped_column(nullable=True)
    transcript_expires_at: Mapped[str | None] = mapped_column(nullable=True)
    sections: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default='DRAFT')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    generation_provider: Mapped[str] = mapped_column(default='manual')
    generation_warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)
    approved_by: Mapped[str | None] = mapped_column(nullable=True)
    approved_at: Mapped[str | None] = mapped_column(nullable=True)
    record_id: Mapped[str | None] = mapped_column(ForeignKey('clinical_records.id'), nullable=True)


class LocalTimelineEvent(LocalBase):
    __tablename__ = 'patient_timeline_events'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    event_type: Mapped[str]
    description: Mapped[str]
    author: Mapped[str]
    occurred_at: Mapped[str] = mapped_column(default=now)
    record_id: Mapped[str | None] = mapped_column(ForeignKey('clinical_records.id'), nullable=True)


class ConflictReview(SharedBase):
    __tablename__ = 'conflict_reviews'
    __table_args__ = (UniqueConstraint('conflict_id', 'hospital_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    conflict_id: Mapped[str] = mapped_column(ForeignKey('clinical_conflicts.id'))
    hospital_id: Mapped[str] = mapped_column(ForeignKey('hospitals.id'))
    status: Mapped[str]
    revision: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_fingerprint: Mapped[str]


class ConflictReviewDecision(SharedBase):
    __tablename__ = 'conflict_review_decisions'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    conflict_review_id: Mapped[str] = mapped_column(ForeignKey('conflict_reviews.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str]
    note: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class LocalUser(LocalBase):
    __tablename__ = 'local_users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str]


class LocalRecord(LocalBase):
    __tablename__ = 'clinical_records'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'), index=True)
    category: Mapped[str]
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(default='ACTIVE')
    payload: Mapped[dict] = mapped_column(JSON)
    author: Mapped[str]
    updated_at: Mapped[str] = mapped_column(default=now)


class LocalVersion(LocalBase):
    __tablename__ = 'clinical_record_versions'
    __table_args__ = (UniqueConstraint('record_id', 'version'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    record_id: Mapped[str] = mapped_column(ForeignKey('clinical_records.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    author: Mapped[str]
    occurred_at: Mapped[str]


class OutboxEvent(LocalBase):
    __tablename__ = 'outbox_events'
    __table_args__ = (UniqueConstraint('record_id', 'source_version'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    record_id: Mapped[str] = mapped_column(ForeignKey('clinical_records.id'))
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    category: Mapped[str]
    source_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    author: Mapped[str]
    occurred_at: Mapped[str]
    lineage: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(default='PENDING')
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(nullable=True)


def immutable(mapper, connection, target):
    raise ValueError(f'{target.__tablename__} is append-only')


for cls in (LocalVersion, ResourceVersion, ClinicalEvent, Provenance, AuditEvent, ReviewDecision, LocalTimelineEvent, ConflictReviewDecision):
    event.listen(cls, 'before_update', immutable)
    event.listen(cls, 'before_delete', immutable)
