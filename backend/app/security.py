import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import func, select

from .models import AuditEvent, CareRelationship, HospitalMembership, LinkMember, SessionToken, User, now


@dataclass(frozen=True)
class WorkspaceUser:
    id: str
    email: str
    name: str
    hospital_id: str
    role: str


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, stored):
    _, salt, expected = stored.split('$')
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex(), expected)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(s, user):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    s.add(SessionToken(token_hash=token_hash(token), user_id=user.id, csrf=csrf, active_hospital_id=user.hospital_id, expires_at=(datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()))
    return token, csrf


def current_user(request: Request):
    db = request.app.state.db
    token = request.cookies.get('clinicalsync_session', '')
    with db.shared() as s:
        session = s.get(SessionToken, token_hash(token))
        if not session or session.expires_at < now():
            raise HTTPException(401, 'Sign in to ClinicalSync')
        user = s.get(User, session.user_id)
        request.state.authenticated_user_id = user.id
        hospital = session.active_hospital_id or user.hospital_id
        request.state.authenticated_hospital_id = hospital
        membership = s.scalar(select(HospitalMembership).where(HospitalMembership.user_id == user.id, HospitalMembership.hospital_id == hospital, HospitalMembership.active == True))
        if not membership:
            raise HTTPException(403, 'No active membership in this hospital workspace')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if origin and origin not in request.app.state.settings.allowed_origins:
                raise HTTPException(403, 'Origin is not allowed')
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf):
                raise HTTPException(403, 'Valid CSRF token required')
        expected_workspace = request.headers.get('x-workspace-id')
        if expected_workspace and expected_workspace != hospital and request.url.path not in ('/api/auth/me', '/api/auth/workspace', '/api/auth/logout'):
            raise HTTPException(409, 'Your hospital workspace changed. Reload before continuing.')
        membership_count = s.scalar(select(func.count()).select_from(HospitalMembership).where(HospitalMembership.user_id == user.id, HospitalMembership.active == True))
        if membership_count > 1 and request.method not in ('GET', 'HEAD', 'OPTIONS') and not expected_workspace and not request.url.path.startswith('/api/auth/'):
            raise HTTPException(409, 'An explicit workspace context is required for this multi-hospital account')
        request.state.csrf = session.csrf
        # Bridge accounts use the consent-aware APIs. Legacy routes cannot bypass grants.
        if hospital in ('memorial', 'valley', 'patient-portal'):
            path = request.url.path
            capture = path.startswith('/api/local/patients/') and path.endswith(('/transcriptions', '/recording-events')) and membership.role == 'clinician'
            if not (path.startswith(('/api/bridge/', '/api/auth/')) or path == '/api/notes/config' or capture):
                raise HTTPException(403, 'Use the EHR Bridge scoped workflow; legacy clinical routes are unavailable to this account')
        return WorkspaceUser(user.id, user.email, user.name, hospital, membership.role)


def audit(s, user, action, target):
    s.add(AuditEvent(user_id=user.id if user else None, hospital_id=user.hospital_id if user else None, action=action, target=target))


def require_clinician(user):
    if user.role != 'clinician':
        raise HTTPException(403, 'An authorized hospital clinician is required')


def require_admin(user):
    if user.role != 'admin':
        raise HTTPException(403, 'Demo administrator required')


def require_local(s, user, patient_id):
    care = s.scalar(select(CareRelationship).where(CareRelationship.hospital_id == user.hospital_id, CareRelationship.local_patient_id == patient_id))
    if not care:
        raise HTTPException(404, 'Patient not found')


def authorized_patient_ids(s, user):
    query = select(LinkMember.patient_id).join(CareRelationship, (CareRelationship.hospital_id == LinkMember.hospital_id) & (CareRelationship.local_patient_id == LinkMember.local_patient_id)).where(LinkMember.hospital_id == user.hospital_id, LinkMember.status == 'CONFIRMED')
    if user.hospital_id not in ('memorial', 'valley', 'patient-portal'):
        from .bridge_models import BridgePatient
        query = query.where(LinkMember.patient_id.not_in(select(BridgePatient.id)))
    return list(s.scalars(query).unique())


def require_shared(s, user, patient_id):
    if patient_id not in authorized_patient_ids(s, user):
        raise HTTPException(404, 'Patient not found')
