"""Clinical workspaces, registration, patient charts and human-approved notes."""
import copy
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update

from .adapters import ADAPTERS, REVERSE_KINDS, clinical_diff, clinical_fields, fingerprint
from .documentation import OpenAITranscriptionProvider, note_provider, provider_status
from .models import *
from .schemas import (ConflictReviewInput, IdentityLinkRequest, NoteApproveInput, NoteDraftInput, NoteDraftUpdate, NoteGenerateInput, PatientRegistration)
from .security import (audit, authorized_patient_ids, current_user, require_admin, require_clinician, require_local, require_shared)
from .services import ChangeDetectionService, IdentityLinkingService


def row(obj):
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def friendly_summary(fields, category):
    if category == 'medication':
        frequency = fields.get('Frequency')
        frequencies = {1: 'once daily', 2: 'twice daily', 3: 'three times daily', 4: 'four times daily'}
        return f"{fields['Clinical concept']} — {fields.get('Dose')} {fields.get('Unit')}, {frequencies.get(frequency, str(frequency))}"
    if category == 'lab':
        return f"{fields['Clinical concept']} — {fields.get('Result')} {fields.get('Unit')}"
    if category == 'allergy':
        return f"{fields['Clinical concept']} — {fields.get('Reaction') or 'Reaction not specified'}"
    return fields['Clinical concept']


def review_fingerprint(conflict):
    return fingerprint([conflict.record_ids, conflict.differences])


def conflict_view(s, conflict, hospital):
    review = s.scalar(select(ConflictReview).where(ConflictReview.conflict_id == conflict.id, ConflictReview.hospital_id == hospital))
    current = review and review.reviewed_fingerprint == review_fingerprint(conflict)
    status = review.status if current else 'NEEDS_REVIEW'
    titles = {'MEDICATION_DOSE_DISCREPANCY': 'Different doses', 'ALLERGY_ASSERTION_DISCREPANCY': 'Conflicting allergy information', 'CLINICAL_STATUS_DISCREPANCY': 'Different clinical statuses', 'LAB_RESULT_DISCREPANCY': 'Different laboratory results', 'POSSIBLE_VACCINATION_DUPLICATE': 'Possible duplicate', 'CLINICALLY_EQUIVALENT': 'Matching source entries'}
    history = [row(d) | {'reviewer': s.get(User, d.user_id).name} for d in s.scalars(select(ConflictReviewDecision).where(ConflictReviewDecision.conflict_review_id == review.id).order_by(ConflictReviewDecision.created_at.desc()))] if review else []
    return row(conflict) | {'title': titles.get(conflict.category, 'Needs review'), 'local_status': status, 'review_revision': review.revision if review else 0, 'review_history': history}


def build_workspace_router(db, settings):
    router = APIRouter(prefix='/api')

    def matches(s, local, user, body):
        own_ids = list(s.scalars(select(CareRelationship.local_patient_id).where(CareRelationship.hospital_id == user.hospital_id)))
        results = []
        full_name = f'{body.first_name} {body.last_name}'.casefold()
        for patient in local.scalars(select(LocalPatient).where(LocalPatient.id.in_(own_ids))):
            reasons = []
            if patient.name.casefold() == full_name:
                reasons.append('Same recorded name')
            if patient.birth_date == body.birth_date.isoformat():
                reasons.append('Same date of birth')
            if reasons:
                results.append({'local_patient_id': patient.id, 'name': patient.name, 'birth_date': patient.birth_date, 'source': 'Current hospital', 'reasons': reasons})
        # Cross-hospital suggestions are limited to identities this workspace can already access.
        own_shared = {m.patient_id for m in s.scalars(select(LinkMember).where(LinkMember.hospital_id == user.hospital_id, LinkMember.local_patient_id.in_(own_ids)))}
        for patient in s.scalars(select(PatientLink).where(PatientLink.id.in_(authorized_patient_ids(s, user)))):
            if patient.id in own_shared:
                continue
            if patient.name.casefold() == full_name or patient.birth_date == body.birth_date.isoformat():
                results.append({'shared_patient_id': patient.id, 'name': patient.name, 'birth_date': patient.birth_date, 'source': 'Authorized shared identity', 'reasons': ['Similar authorized identity; manual review required']})
        for membership in s.scalars(select(HospitalMembership).where(HospitalMembership.user_id == user.id, HospitalMembership.active == True, HospitalMembership.hospital_id != user.hospital_id)):
            if membership.hospital_id not in db.local_factories:
                continue
            permitted = list(s.scalars(select(CareRelationship.local_patient_id).where(CareRelationship.hospital_id == membership.hospital_id)))
            with db.local(membership.hospital_id) as other:
                for patient in other.scalars(select(LocalPatient).where(LocalPatient.id.in_(permitted))):
                    reasons = []
                    if patient.name.casefold() == full_name:
                        reasons.append('Same recorded name')
                    if patient.birth_date == body.birth_date.isoformat():
                        reasons.append('Same date of birth')
                    if reasons:
                        hospital = s.get(Hospital, membership.hospital_id)
                        results.append({'hospital_id': hospital.id, 'local_patient_id': patient.id, 'name': patient.name, 'birth_date': patient.birth_date, 'source': hospital.name + ' · authorized workspace', 'reasons': reasons})
        results.sort(key=lambda match: (match.get('hospital_id', user.hospital_id), match.get('local_patient_id', match.get('shared_patient_id', ''))))
        return {'matches': results, 'match_token': fingerprint([full_name, body.birth_date.isoformat(), results]), 'notice': 'Similar demographics do not confirm identity. Creating a patient never automatically links another hospital’s chart.'}

    @router.post('/local/patients/check-matches', tags=['Patient registration'])
    def check_matches(body: PatientRegistration, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s, db.local(user.hospital_id) as local:
            audit(s, user, 'CHECK_PATIENT_MATCHES', user.hospital_id)
            return matches(s, local, user, body)

    @router.post('/local/patients', status_code=201, tags=['Patient registration'])
    def register_patient(body: PatientRegistration, user=Depends(current_user)):
        require_clinician(user)
        with db.local(user.hospital_id) as local, db.shared() as s:
            possible = matches(s, local, user, body)
            if possible['matches'] and body.match_token != possible['match_token']:
                raise HTTPException(409, {'code': 'POSSIBLE_PATIENT_MATCHES', 'message': 'Review possible existing patients before creating a separate hospital chart.', **possible})
            prefix = {'northstar': 'NS', 'riverside': 'RG'}.get(user.hospital_id, user.hospital_id[:3].upper())
            local_id = body.local_patient_id or prefix + '-' + uid()[:8].upper()
            if local.get(LocalPatient, local_id):
                raise HTTPException(409, 'That patient identifier already exists at this hospital')
            timestamp = now()
            patient = LocalPatient(id=local_id, first_name=body.first_name, last_name=body.last_name, name=body.first_name + ' ' + body.last_name, birth_date=body.birth_date.isoformat(), administrative_gender=body.administrative_gender, contact=body.contact, care_status='active', synthetic=True, created_at=timestamp, updated_at=timestamp)
            local.add(patient)
            local.flush()
            local.add(LocalTimelineEvent(patient_id=local_id, event_type='PATIENT_REGISTERED', description='Patient registered in this hospital workspace', author=user.name, occurred_at=timestamp))
            shared_id = 'PAT-' + uid()[:12].upper()
            s.add(PatientLink(id=shared_id, name=patient.name, birth_date=patient.birth_date, synthetic=True))
            s.flush()
            s.add(LinkMember(patient_id=shared_id, hospital_id=user.hospital_id, local_patient_id=local_id, status='CONFIRMED', evidence='New local patient registration only. No cross-hospital identity match was assumed.', reviewed_by=user.id))
            s.add(CareRelationship(hospital_id=user.hospital_id, local_patient_id=local_id, reason='Explicit care relationship established by patient registration'))
            audit(s, user, 'PATIENT_REGISTERED', local_id)
            return row(patient) | {'shared_patient_id': shared_id, 'automatically_linked': False}

    def directory_data(s, local, user, q=''):
        allowed_local = list(s.scalars(select(CareRelationship.local_patient_id).where(CareRelationship.hospital_id == user.hospital_id)))
        items, shared_items = [], []
        for patient in local.scalars(select(LocalPatient).where(LocalPatient.id.in_(allowed_local)).order_by(LocalPatient.name)):
            if q.casefold() not in (patient.name + ' ' + patient.id).casefold():
                continue
            member = IdentityLinkingService.confirmed(s, user.hospital_id, patient.id)
            members = list(s.scalars(select(LinkMember).where(LinkMember.patient_id == member.patient_id, LinkMember.status == 'CONFIRMED'))) if member else []
            hospitals = [row(s.get(Hospital, m.hospital_id)) for m in members]
            last_local = local.scalar(select(func.max(LocalRecord.updated_at)).where(LocalRecord.patient_id == patient.id))
            latest = s.scalar(select(ClinicalEvent).where(ClinicalEvent.patient_id == member.patient_id).order_by(ClinicalEvent.ingested_at.desc()).limit(1)) if member else None
            pending = s.scalar(select(func.count()).select_from(ReviewItem).join(ClinicalEvent).where(ReviewItem.hospital_id == user.hospital_id, ClinicalEvent.patient_id == member.patient_id, ReviewItem.status.in_(['PENDING_REVIEW', 'DEFERRED', 'INVESTIGATING']))) if member else 0
            entry = row(patient) | {'local_patient_id': patient.id, 'shared_patient_id': member.patient_id if member else None, 'connected_hospitals': hospitals, 'connected_count': len(hospitals), 'is_shared': len(hospitals) > 1, 'last_updated': max(patient.updated_at, last_local or ''), 'last_shared_update': latest.ingested_at if latest else None, 'last_update_description': friendly_summary(clinical_fields(latest.after), REVERSE_KINDS[latest.resource_type]) if latest else 'No published clinical updates', 'needs_review': pending}
            items.append(entry)
            if entry['is_shared']:
                shared_items.append(entry)
        return {'hospital_patients': items, 'shared_patients': shared_items}

    @router.get('/directory', tags=['Clinical workspace'])
    def directory(q: str = Query(default='', max_length=100), user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            audit(s, user, 'READ_PATIENT_DIRECTORY', user.hospital_id)
            return directory_data(s, local, user, q)

    @router.get('/overview', tags=['Clinical workspace'])
    def overview(user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            data = directory_data(s, local, user)
            ids = authorized_patient_ids(s, user)
            queue = list(s.scalars(select(ReviewItem).join(ClinicalEvent).where(ReviewItem.hospital_id == user.hospital_id, ClinicalEvent.patient_id.in_(ids)).order_by(ClinicalEvent.ingested_at.desc()).limit(50)))
            incoming = []
            for item in queue[:8]:
                event = s.get(ClinicalEvent, item.event_id)
                patient = s.get(PatientLink, event.patient_id)
                member = IdentityLinkingService.confirmed(s, user.hospital_id, next((p['id'] for p in data['hospital_patients'] if p['shared_patient_id'] == patient.id), ''))
                incoming.append({'id': item.id, 'patient_name': patient.name, 'local_patient_id': member.local_patient_id if member else None, 'hospital': row(s.get(Hospital, event.hospital_id)), 'description': friendly_summary(clinical_fields(event.after), REVERSE_KINDS[event.resource_type]), 'category': REVERSE_KINDS[event.resource_type], 'event_type': event.event_type, 'received_at': event.ingested_at, 'status': item.status})
            issues = [conflict_view(s, c, user.hospital_id) for c in s.scalars(select(Conflict).where(Conflict.patient_id.in_(ids), Conflict.active == True, Conflict.category != 'CLINICALLY_EQUIVALENT'))]
            for issue in issues:
                patient = s.get(PatientLink, issue['patient_id'])
                issue['patient_name'] = patient.name
                issue['local_patient_id'] = next((p['id'] for p in data['hospital_patients'] if p['shared_patient_id'] == patient.id), None)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            audit(s, user, 'READ_CLINICAL_OVERVIEW', user.hospital_id)
            pending_count = s.scalar(select(func.count()).select_from(ReviewItem).join(ClinicalEvent).where(ReviewItem.hospital_id == user.hospital_id, ClinicalEvent.patient_id.in_(ids), ReviewItem.status.in_(['PENDING_REVIEW', 'DEFERRED', 'INVESTIGATING'])))
            return {'hospital': row(s.get(Hospital, user.hospital_id)), 'hospital_patient_count': len(data['hospital_patients']), 'linked_patient_count': len(data['shared_patients']), 'recently_updated_patients': len([p for p in data['shared_patients'] if p['last_shared_update'] and p['last_shared_update'] >= cutoff]), 'patients_needing_review': len([p for p in data['hospital_patients'] if p['needs_review']]), 'pending_review_count': pending_count, 'incoming_updates': incoming, 'issues': [issue for issue in issues if issue['local_status'] != 'RESOLVED']}

    def local_record_view(s, user, record):
        published = s.get(CanonicalResource, f'{user.hospital_id}-{record.id}')
        member = IdentityLinkingService.confirmed(s, user.hospital_id, record.patient_id)
        translated = ADAPTERS[user.hospital_id].to_canonical(record.payload, member.patient_id if member else record.patient_id, f'{user.hospital_id}-{record.id}', record.version, record.updated_at)
        source, _ = ADAPTERS[user.hospital_id].unpack(record.payload)
        return {'id': f'local/{record.id}', 'source_record_id': record.id, 'resource_id': published.id if published else None, 'category': record.category, 'hospital_id': user.hospital_id, 'source': row(s.get(Hospital, user.hospital_id)), 'source_version': record.version, 'status': record.state, 'effective_at': clinical_fields(translated.resource)['Effective date'], 'updated_at': record.updated_at, 'author': record.author, 'payload': translated.resource, 'fields': clinical_fields(translated.resource), 'warnings': translated.warnings, 'input': source, 'is_local': True, 'review_status': 'LOCAL_RECORD', 'publication_pending': not published or published.source_version < record.version}

    @router.get('/charts/{patient_id}', tags=['Clinical workspace'])
    def chart(patient_id: str, user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            require_local(s, user, patient_id)
            patient = local.get(LocalPatient, patient_id)
            if not patient:
                raise HTTPException(404, 'Patient not found')
            member = IdentityLinkingService.confirmed(s, user.hospital_id, patient_id)
            members = list(s.scalars(select(LinkMember).where(LinkMember.patient_id == member.patient_id, LinkMember.status == 'CONFIRMED'))) if member else []
            own = [local_record_view(s, user, record) for record in local.scalars(select(LocalRecord).where(LocalRecord.patient_id == patient_id).order_by(LocalRecord.updated_at.desc()))]
            external = []
            if member:
                require_shared(s, user, member.patient_id)
                for resource in s.scalars(select(CanonicalResource).where(CanonicalResource.patient_id == member.patient_id, CanonicalResource.hospital_id != user.hospital_id).order_by(CanonicalResource.updated_at.desc())):
                    event = s.scalar(select(ClinicalEvent).where(ClinicalEvent.resource_id == resource.id).order_by(ClinicalEvent.source_version.desc()))
                    review = s.scalar(select(ReviewItem).where(ReviewItem.event_id == event.id, ReviewItem.hospital_id == user.hospital_id))
                    external.append(row(resource) | {'category': REVERSE_KINDS[resource.resource_type], 'fields': clinical_fields(resource.payload), 'source': row(s.get(Hospital, resource.hospital_id)), 'is_local': False, 'source_record_id': event.source_record_id, 'author': event.author, 'review_status': review.status if review else 'PENDING_REVIEW', 'review_id': review.id if review else None})
            issues = [conflict_view(s, c, user.hospital_id) for c in s.scalars(select(Conflict).where(Conflict.patient_id == member.patient_id, Conflict.active == True))] if member else []
            audit(s, user, 'READ_PATIENT_CHART', patient_id)
            all_records = own + external
            return row(patient) | {'shared_patient_id': member.patient_id if member else None, 'members': [row(m) | {'hospital': row(s.get(Hospital, m.hospital_id))} for m in members], 'records': all_records, 'conflicts': issues, 'latest_update': max([r['updated_at'] for r in all_records], default=patient.updated_at)}

    @router.get('/local/records/{record_id}/details', tags=['Clinical workspace'])
    def local_details(record_id: str, user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            record = local.get(LocalRecord, record_id)
            if not record:
                raise HTTPException(404, 'Record not found')
            require_local(s, user, record.patient_id)
            current = local_record_view(s, user, record)
            versions, events = [], []
            previous = None
            for version in local.scalars(select(LocalVersion).where(LocalVersion.record_id == record_id).order_by(LocalVersion.version)):
                translated = ADAPTERS[user.hospital_id].to_canonical(version.payload, source_version=version.version, updated_at=version.occurred_at)
                versions.append({'version': version.version, 'payload': translated.resource, 'original_payload': version.payload, 'fields': clinical_fields(translated.resource)})
                events.append({'id': version.id, 'event_type': version.event_type, 'source_version': version.version, 'author': version.author, 'occurred_at': version.occurred_at, 'diff': clinical_diff(previous, translated.resource)})
                previous = translated.resource
            audit(s, user, 'READ_LOCAL_RECORD_DETAILS', record_id)
            return current | {'local_patient_id': record.patient_id, 'original_payload': record.payload, 'versions': list(reversed(versions)), 'events': list(reversed(events)), 'provenance': [], 'destination_preview': ADAPTERS[user.hospital_id].from_canonical(current['payload']), 'preview_notice': 'Development-format preview only. No external EHR import.'}

    @router.get('/charts/{patient_id}/timeline', tags=['Clinical workspace'])
    def patient_timeline(patient_id: str, user=Depends(current_user)):
        with db.shared() as s, db.local(user.hospital_id) as local:
            require_local(s, user, patient_id)
            member = IdentityLinkingService.confirmed(s, user.hospital_id, patient_id)
            events = []
            for e in local.scalars(select(LocalTimelineEvent).where(LocalTimelineEvent.patient_id == patient_id)):
                events.append({'id': e.id, 'event_type': e.event_type, 'description': e.description, 'author': e.author, 'hospital_id': user.hospital_id, 'recorded_at': e.occurred_at, 'clinical_at': None, 'record_reference': f'local/{e.record_id}' if e.record_id else None, 'diff': []})
            own_ids = list(local.scalars(select(LocalRecord.id).where(LocalRecord.patient_id == patient_id)))
            for version in local.scalars(select(LocalVersion).where(LocalVersion.record_id.in_(own_ids)).order_by(LocalVersion.occurred_at.desc())):
                canonical = ADAPTERS[user.hospital_id].to_canonical(version.payload, source_version=version.version).resource
                fields = clinical_fields(canonical)
                events.append({'id': version.id, 'event_type': version.event_type, 'description': friendly_summary(fields, REVERSE_KINDS[canonical['resourceType']]), 'author': version.author, 'hospital_id': user.hospital_id, 'recorded_at': version.occurred_at, 'clinical_at': fields['Effective date'], 'record_reference': f'local/{version.record_id}', 'diff': []})
            if member:
                require_shared(s, user, member.patient_id)
                for event in s.scalars(select(ClinicalEvent).where(ClinicalEvent.patient_id == member.patient_id, ClinicalEvent.hospital_id != user.hospital_id)):
                    events.append({'id': event.id, 'event_type': 'EXTERNAL_' + event.event_type, 'description': friendly_summary(clinical_fields(event.after), REVERSE_KINDS[event.resource_type]), 'author': event.author, 'hospital_id': event.hospital_id, 'recorded_at': event.ingested_at, 'source_at': event.occurred_at, 'clinical_at': clinical_fields(event.after)['Effective date'], 'record_reference': event.resource_id, 'diff': event.diff})
                decisions = s.execute(select(ReviewDecision, ClinicalEvent).join(ReviewItem, ReviewDecision.review_id == ReviewItem.id).join(ClinicalEvent, ClinicalEvent.id == ReviewItem.event_id).where(ReviewItem.hospital_id == user.hospital_id, ClinicalEvent.patient_id == member.patient_id)).all()
                for decision, event in decisions:
                    events.append({'id': decision.id, 'event_type': 'REVIEW_' + decision.decision, 'description': f"External {clinical_fields(event.after)['Clinical concept']} reviewed: {decision.decision.lower()}", 'author': s.get(User, decision.user_id).name, 'hospital_id': user.hospital_id, 'recorded_at': decision.created_at, 'clinical_at': None, 'record_reference': event.resource_id, 'review_note': decision.note, 'diff': []})
            audit(s, user, 'READ_PATIENT_TIMELINE', patient_id)
            if member:
                decisions = s.execute(select(ConflictReviewDecision, Conflict).join(ConflictReview, ConflictReviewDecision.conflict_review_id == ConflictReview.id).join(Conflict, ConflictReview.conflict_id == Conflict.id).where(Conflict.patient_id == member.patient_id, ConflictReview.hospital_id == user.hospital_id)).all()
                for decision, conflict in decisions:
                    events.append({'id': decision.id, 'event_type': 'DIFFERENCE_' + decision.status, 'description': 'Clinical difference reviewed for this hospital', 'author': s.get(User, decision.user_id).name, 'hospital_id': user.hospital_id, 'recorded_at': decision.created_at, 'clinical_at': None, 'record_reference': None, 'review_note': decision.note, 'diff': []})
            for event in events:
                event['hospital_name'] = s.get(Hospital, event['hospital_id']).name
            return sorted(events, key=lambda event: (event['recorded_at'], event['id']), reverse=True)

    @router.post('/conflicts/{conflict_id}/reviews', tags=['Clinical reviews'])
    def review_conflict(conflict_id: str, body: ConflictReviewInput, user=Depends(current_user)):
        require_clinician(user)
        with db.shared() as s:
            conflict = s.get(Conflict, conflict_id)
            if not conflict:
                raise HTTPException(404, 'Review difference not found')
            require_shared(s, user, conflict.patient_id)
            review = s.scalar(select(ConflictReview).where(ConflictReview.conflict_id == conflict.id, ConflictReview.hospital_id == user.hospital_id))
            if review:
                result = s.execute(update(ConflictReview).where(ConflictReview.id == review.id, ConflictReview.revision == body.expected_revision).values(status=body.status, revision=body.expected_revision + 1, reviewed_fingerprint=review_fingerprint(conflict)))
                if result.rowcount != 1:
                    raise HTTPException(409, 'This difference was reviewed by someone else. Refresh before saving.')
                s.refresh(review)
            else:
                if body.expected_revision != 0:
                    raise HTTPException(409, 'Refresh this review before saving')
                review = ConflictReview(conflict_id=conflict.id, hospital_id=user.hospital_id, status=body.status, revision=1, reviewed_fingerprint=review_fingerprint(conflict))
                s.add(review)
                s.flush()
            s.add(ConflictReviewDecision(conflict_review_id=review.id, user_id=user.id, status=body.status, note=body.note))
            audit(s, user, 'CLINICAL_DIFFERENCE_' + body.status, conflict.id)
            s.flush()
            return conflict_view(s, conflict, user.hospital_id)

    @router.get('/identity/targets', tags=['Identity'])
    def identity_targets(q: str = Query(min_length=2, max_length=100), user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            audit(s, user, 'SEARCH_IDENTITY_LINK_TARGETS', 'identity-metadata')
            from .bridge_models import BridgePatient
            return [row(p) | {'members': [row(m) | {'hospital_name': s.get(Hospital, m.hospital_id).name} for m in s.scalars(select(LinkMember).where(LinkMember.patient_id == p.id, LinkMember.status == 'CONFIRMED'))]} for p in s.scalars(select(PatientLink).where(PatientLink.id.not_in(select(BridgePatient.id))).order_by(PatientLink.name)) if q.casefold() in (p.name + ' ' + p.id).casefold()][:20]

    @router.post('/identity/link-requests', status_code=201, tags=['Identity'])
    def request_identity_link(body: IdentityLinkRequest, user=Depends(current_user)):
        require_admin(user)
        with db.shared() as s:
            member = s.scalar(select(LinkMember).where(LinkMember.hospital_id == body.hospital_id, LinkMember.local_patient_id == body.local_patient_id))
            target = s.get(PatientLink, body.target_patient_id)
            from .bridge_models import BridgePatient
            if body.hospital_id in ('memorial', 'valley') or s.get(BridgePatient, body.target_patient_id):
                raise HTTPException(403, 'Bridge identities cannot be reassigned through legacy identity tools')
            if not member or not target:
                raise HTTPException(404, 'Source or target identity not found')
            if member.patient_id == target.id:
                raise HTTPException(409, 'These source identities are already linked')
            if s.scalar(select(IdentityCandidate).where(IdentityCandidate.member_id == member.id, IdentityCandidate.status == 'PENDING_REVIEW')):
                raise HTTPException(409, 'An identity request is already pending')
            candidate = IdentityCandidate(id='MATCH-' + uid()[:12].upper(), member_id=member.id, target_patient_id=target.id, status='PENDING_REVIEW', evidence={'source_name': s.get(PatientLink, member.patient_id).name, 'target_name': target.name, 'birth_date': target.birth_date, 'method': 'Explicit administrator link request', 'warning': body.evidence})
            s.add(candidate)
            audit(s, user, 'IDENTITY_LINK_REQUESTED', candidate.id)
            s.flush()
            return row(candidate)

    from .note_routes import add_note_routes
    add_note_routes(router, db, settings)
    return router
