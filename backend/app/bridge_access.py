"""All Bridge clinical reads share this grant boundary, including history/translation."""
from fastapi import HTTPException
from sqlalchemy import select
from .models import CanonicalResource, ClinicalEvent, Hospital, LinkMember, PatientLink, now
from .bridge_models import AccessGrant, BridgePatient, EHRConnection, PreservedRecord
from .adapters import REVERSE_KINDS, clinical_fields
from .security import audit, require_clinician, require_shared


def row(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def patient_scope(s, user, patient_id):
    profile = s.get(BridgePatient, patient_id)
    if not profile:
        raise HTTPException(404, 'Patient not found')
    if user.role == 'patient':
        if profile.portal_user_id != user.id:
            raise HTTPException(404, 'Patient not found')
    else:
        require_clinician(user)
        require_shared(s, user, patient_id)
    return profile


def live_grants(s, user, patient_id):
    return list(s.scalars(select(AccessGrant).where(AccessGrant.patient_id == patient_id, AccessGrant.doctor_id == user.id, AccessGrant.hospital_id == user.hospital_id, AccessGrant.expires_at > now(), AccessGrant.revoked_at.is_(None))))


def permitted(user, source, category, grants):
    return user.role == 'patient' or source == user.hospital_id or any(source in g.source_hospitals and category in g.categories for g in grants)


def record_views(s, user, patient_id, log=True):
    patient_scope(s, user, patient_id)
    grants = live_grants(s, user, patient_id)
    destination = s.get(EHRConnection, user.hospital_id)
    result = []
    for record in s.scalars(select(CanonicalResource).where(CanonicalResource.patient_id == patient_id)):
        category = REVERSE_KINDS[record.resource_type]
        if not permitted(user, record.hospital_id, category, grants):
            continue
        fields = clinical_fields(record.payload)
        latest = s.scalar(select(ClinicalEvent).where(ClinicalEvent.resource_id == record.id).order_by(ClinicalEvent.source_version.desc()))
        mapped = not destination or category in destination.supported_categories
        result.append({'id': record.id, 'patient_id': patient_id, 'hospital_id': record.hospital_id, 'hospital': s.get(Hospital, record.hospital_id).name, 'category': category, 'display': fields.get('Clinical concept', category), 'fields': fields, 'recorded_at': latest.occurred_at if latest else record.updated_at, 'clinical_date': record.effective_at, 'author': latest.author if latest else 'Author not recorded', 'version': record.source_version, 'verification': 'Imported hospital information · fictional', 'mapping': 'Mapped' if mapped else 'Preserved — not mapped to destination', 'status': record.status, 'kind': 'canonical'})
    for record in s.scalars(select(PreservedRecord).where(PreservedRecord.patient_id == patient_id)):
        if not permitted(user, record.hospital_id, record.category, grants):
            continue
        mapped = not destination or record.category in destination.supported_categories
        result.append({'id': record.id, 'patient_id': patient_id, 'hospital_id': record.hospital_id, 'hospital': s.get(Hospital, record.hospital_id).name, 'category': record.category, 'display': record.display, 'fields': record.normalized['fields'], 'recorded_at': record.recorded_at, 'clinical_date': record.recorded_at, 'author': record.author, 'version': record.version, 'verification': record.verification, 'mapping': 'Mapped' if mapped else 'Preserved — not mapped to destination', 'status': 'ACTIVE', 'kind': 'preserved'})
    if log:
        categories = sorted({r['category'] for r in result if r['hospital_id'] != user.hospital_id})
        audit(s, user, 'BRIDGE_READ_RECORDS', patient_id + '/categories/' + ','.join(categories))
    return sorted(result, key=lambda r: (r['category'], r['hospital_id'], r['id']))


def patient_view(s, user, patient_id, records=None):
    profile = patient_scope(s, user, patient_id)
    patient = s.get(PatientLink, patient_id)
    members = list(s.scalars(select(LinkMember).where(LinkMember.patient_id == patient_id, LinkMember.status == 'CONFIRMED')))
    records = record_views(s, user, patient_id, False) if records is None else records
    grants = live_grants(s, user, patient_id)
    return {'id': patient.id, 'name': patient.name, 'birth_date': patient.birth_date, 'demographics': profile.demographics, 'sources': [{'id': m.hospital_id, 'name': s.get(Hospital, m.hospital_id).name, 'local_id': m.local_patient_id, 'vendor': s.get(EHRConnection, m.hospital_id).vendor if s.get(EHRConnection, m.hospital_id) else 'Mock adapter'} for m in members], 'local_id': next((m.local_patient_id for m in members if m.hospital_id == user.hospital_id), None), 'access_status': 'Personal records' if user.role == 'patient' else 'Approved external access' if grants else 'Local records only', 'access_expires_at': max((g.expires_at for g in grants), default=None), 'record_count': len(records), 'last_updated': max((r['recorded_at'] for r in records), default=profile.created_at), 'assigned_doctor': user.name if user.role == 'clinician' else 'Your authorized care teams', 'completeness': {'available': sorted({r['category'] for r in records}), 'missing': [c for c in ('medication', 'allergy', 'lab', 'vaccination') if c not in {r['category'] for r in records}]}}
