import copy
from itertools import combinations

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .adapters import ADAPTERS, TRANSFORMATION_VERSION, clinical_diff, clinical_fields, code_concept, fingerprint
from .models import (CanonicalResource, CareRelationship, ClinicalEvent, Conflict, DeliveryEvent, LinkMember, LocalRecord, LocalVersion, OutboxEvent, Provenance, ResourceVersion, ReviewItem, SourceRecord, SyncJob, now, uid)


class ChangeDetectionService:
    @staticmethod
    def save(local, hospital, patient_id, category, payload, author, record_id=None, expected_version=None, event_type='CREATED', lineage=None, timestamp=None):
        record_id = record_id or uid()
        timestamp = timestamp or now()
        adapter = ADAPTERS[hospital]
        # Mapping must succeed before persisting a source mutation.
        adapter.to_canonical(payload)
        record = local.get(LocalRecord, record_id)
        if record:
            if expected_version != record.version:
                raise HTTPException(409, 'This record changed. Refresh before saving.')
            if record.patient_id != patient_id or record.category != category:
                raise HTTPException(409, 'Record identity and category are immutable')
            if record.state == 'WITHDRAWN':
                raise HTTPException(409, 'Withdrawn records retain history and cannot be edited')
            if fingerprint(record.payload) == fingerprint(payload) and event_type == 'UPDATED':
                return record, False
            version = record.version + 1
            # Atomic compare-and-swap also protects concurrent HTTP requests.
            result = local.execute(update(LocalRecord).where(LocalRecord.id == record_id, LocalRecord.version == expected_version).values(version=version, payload=payload, state='WITHDRAWN' if event_type == 'WITHDRAWN' else 'ACTIVE', author=author, updated_at=timestamp))
            if result.rowcount != 1:
                raise HTTPException(409, 'Concurrent source update. Refresh before saving.')
            local.refresh(record)
        else:
            if event_type != 'CREATED':
                raise HTTPException(404, 'Source record not found')
            version = 1
            record = LocalRecord(id=record_id, patient_id=patient_id, category=category, payload=payload, author=author, updated_at=timestamp, version=1, state='ACTIVE')
            local.add(record)
            local.flush()
        local.add(LocalVersion(record_id=record_id, version=version, event_type=event_type, payload=copy.deepcopy(payload), author=author, occurred_at=timestamp))
        local.add(OutboxEvent(record_id=record_id, patient_id=patient_id, category=category, source_version=version, event_type=event_type, payload=copy.deepcopy(payload), author=author, occurred_at=timestamp, lineage=lineage or []))
        local.flush()
        return record, True


class IdentityLinkingService:
    @staticmethod
    def confirmed(s, hospital, local_patient):
        return s.scalar(select(LinkMember).where(LinkMember.hospital_id == hospital, LinkMember.local_patient_id == local_patient, LinkMember.status == 'CONFIRMED'))

    @staticmethod
    def receivers(s, patient_id, origin):
        return set(s.scalars(select(LinkMember.hospital_id).join(CareRelationship, (CareRelationship.hospital_id == LinkMember.hospital_id) & (CareRelationship.local_patient_id == LinkMember.local_patient_id)).where(LinkMember.patient_id == patient_id, LinkMember.status == 'CONFIRMED', LinkMember.hospital_id != origin)))


class ProvenanceService:
    @staticmethod
    def create(event, original_id):
        return {'resourceType': 'Provenance', 'target': [{'reference': f'{event.resource_type}/{event.resource_id}/_history/{event.source_version}'}], 'recorded': event.ingested_at, 'occurredDateTime': event.occurred_at, 'agent': [{'type': {'text': 'Source author'}, 'who': {'display': event.author}}, {'type': {'text': 'Transforming organization'}, 'who': {'reference': f'Organization/{event.hospital_id}'}}], 'entity': [{'role': 'source', 'what': {'identifier': {'system': f'urn:clinicalsync:{event.hospital_id}', 'value': original_id}}}], 'activity': {'text': event.event_type}}


def code_key(resource):
    r = resource.payload
    coding = code_concept(r)['coding'][0]
    return coding['system'], coding['code']


def effective_range(r):
    payload = r.payload
    return (clinical_fields(payload)['Effective date'], payload.get('effectivePeriod', {}).get('end', payload.get('abatementDateTime', '9999-12-31')))


class ConflictDetectionService:
    @staticmethod
    def detect(s, patient_id):
        records = list(s.scalars(select(CanonicalResource).where(CanonicalResource.patient_id == patient_id)))
        existing = {c.id: c for c in s.scalars(select(Conflict).where(Conflict.patient_id == patient_id))}
        seen = set()
        for a, b in combinations(records, 2):
            if a.hospital_id == b.hospital_id or a.resource_type != b.resource_type:
                continue
            if a.status == 'WITHDRAWN' or b.status == 'WITHDRAWN':
                continue
            fa, fb = clinical_fields(a.payload), clinical_fields(b.payload)
            if fa['Status'] in ('entered-in-error', 'cancelled') or fb['Status'] in ('entered-in-error', 'cancelled'):
                continue
            if fa.get('Verification') == 'refuted' or fb.get('Verification') == 'refuted':
                continue
            same = code_key(a) == code_key(b)
            start_a, end_a = effective_range(a)
            start_b, end_b = effective_range(b)
            overlap = max(start_a, start_b) <= min(end_a or '9999-12-31', end_b or '9999-12-31')
            category = None
            explanation = ''
            if same and fa == fb:
                category = 'CLINICALLY_EQUIVALENT'
                explanation = 'Matching clinical facts from independent sources. Both provenance chains are retained.'
            elif a.resource_type == 'MedicationStatement' and same and overlap and fa['Status'] == fb['Status'] == 'active' and any(fa.get(k) != fb.get(k) for k in ('Dose', 'Unit', 'Frequency')):
                category = 'MEDICATION_DOSE_DISCREPANCY'
                explanation = 'Potential discrepancy — review required. The same medication has different documented dosing during overlapping effective periods.'
            elif a.resource_type == 'Observation' and same and start_a == start_b and any(fa.get(k) != fb.get(k) for k in ('Result', 'Unit')):
                category = 'LAB_RESULT_DISCREPANCY'
                explanation = 'Potential discrepancy — review required. The same test at the same collection time has differing results.'
            elif a.resource_type == 'Immunization' and same and fa['Status'] == fb['Status'] == 'completed' and start_a[:10] == start_b[:10] and fa.get('Dose number') == fb.get('Dose number') and not (fa.get('Lot number') and fb.get('Lot number') and fa['Lot number'] != fb['Lot number']):
                category = 'POSSIBLE_VACCINATION_DUPLICATE'
                explanation = 'Possible duplicate vaccination. Both hospitals report the same vaccine on the same date with matching dose context. Review both sources; no record was removed.'
            elif a.resource_type == 'AllergyIntolerance' and overlap and fa['Status'] == fb['Status'] == 'active' and ((code_key(a)[1] == 'NO_KNOWN_ALLERGIES') != (code_key(b)[1] == 'NO_KNOWN_ALLERGIES')):
                category = 'ALLERGY_ASSERTION_DISCREPANCY'
                explanation = 'Potential discrepancy — review required. An explicit no-known-allergy assertion differs from a documented allergy. Missing information alone is never a negative assertion.'
            elif same and overlap and (a.resource_type in ('MedicationStatement', 'AllergyIntolerance', 'Condition') or a.resource_type == 'Immunization' and start_a[:10] == start_b[:10] and fa.get('Dose number') == fb.get('Dose number')) and fa.get('Status') != fb.get('Status'):
                category = 'CLINICAL_STATUS_DISCREPANCY'
                explanation = 'Potential discrepancy — review required. Related facts have contradictory documented statuses.'
            if category:
                conflict_id = fingerprint([sorted([a.id, b.id]), category])[:32]
                seen.add(conflict_id)
                differences = clinical_diff(a.payload, b.payload)
                if conflict_id in existing:
                    c = existing[conflict_id]
                    c.active, c.differences = True, differences
                else:
                    s.add(Conflict(id=conflict_id, patient_id=patient_id, record_ids=[a.id, b.id], category=category, differences=differences, explanation=explanation))
        for c in existing.values():
            if c.id not in seen:
                c.active = False


class SynchronizationService:
    def __init__(self, db):
        self.db = db

    def run(self, hospital):
        with self.db.shared() as s:
            job = SyncJob(hospital_id=hospital, status='RUNNING')
            s.add(job)
            s.flush()
            job_id = job.id
        counts = {'published': 0, 'suppressed': 0, 'failed': 0, 'waiting': 0}
        with self.db.local(hospital) as local:
            events = list(local.scalars(select(OutboxEvent).where(OutboxEvent.state.in_(['PENDING', 'FAILED', 'WAITING_IDENTITY'])).order_by(OutboxEvent.occurred_at, OutboxEvent.source_version)))
            event_ids = [e.id for e in events]
        blocked_records = set()
        for event_id in event_ids:
            with self.db.local(hospital) as local:
                e = local.get(OutboxEvent, event_id)
                if e.record_id in blocked_records:
                    counts['waiting'] += 1
                    continue
                try:
                    outcome = self.publish(hospital, e)
                    e.state = 'WAITING_IDENTITY' if outcome == 'waiting' else 'PUBLISHED' if outcome == 'published' else 'SUPPRESSED'
                    e.last_error = None
                    counts[outcome] += 1
                except Exception:
                    # Never include source payloads or exception text in error logs.
                    e.state = 'FAILED'
                    e.retry_count += 1
                    e.last_error = 'TRANSLATION_OR_PUBLICATION_FAILED'
                    counts['failed'] += 1
                    blocked_records.add(e.record_id)
        with self.db.shared() as s:
            job = s.get(SyncJob, job_id)
            for key, value in counts.items():
                setattr(job, key, value)
            job.completed_at = now()
            job.status = 'FAILED' if counts['failed'] else 'WAITING_IDENTITY' if counts['waiting'] else 'SUCCEEDED'
        return {'id': job_id, 'hospital_id': hospital, 'status': job.status, **counts}

    def publish(self, hospital, e):
        with self.db.shared() as s:
            if s.get(ClinicalEvent, e.id):
                return 'suppressed'
            # Imported lineage is not a new original source assertion.
            for origin in e.lineage:
                if isinstance(origin, str) and s.get(ClinicalEvent, origin):
                    return 'suppressed'
                if isinstance(origin, dict) and origin.get('hospital_id') == hospital and origin.get('source_record_id') == e.record_id:
                    return 'suppressed'
            member = IdentityLinkingService.confirmed(s, hospital, e.patient_id)
            if not member:
                return 'waiting'
            resource_id = f'{hospital}-{e.record_id}'
            source_id = resource_id
            existing_event = s.scalar(select(ClinicalEvent).where(ClinicalEvent.hospital_id == hospital, ClinicalEvent.source_record_id == e.record_id, ClinicalEvent.source_version == e.source_version))
            if existing_event:
                return 'suppressed'
            resource = s.get(CanonicalResource, resource_id)
            if resource and e.source_version <= resource.source_version:
                return 'suppressed'
            translated = ADAPTERS[hospital].to_canonical(e.payload, member.patient_id, resource_id, e.source_version, e.occurred_at)
            before = copy.deepcopy(resource.payload) if resource else None
            source = s.get(SourceRecord, source_id)
            if not source:
                source = SourceRecord(id=source_id, hospital_id=hospital, source_record_id=e.record_id, local_patient_id=e.patient_id, latest_version=e.source_version, last_observed_at=e.occurred_at)
                s.add(source)
                s.flush()
            else:
                source.latest_version, source.last_observed_at = e.source_version, e.occurred_at
            if not resource:
                resource = CanonicalResource(id=resource_id, source_id=source_id, patient_id=member.patient_id, hospital_id=hospital, local_patient_id=e.patient_id, resource_type=translated.resource['resourceType'], source_version=e.source_version, status='ACTIVE', effective_at=clinical_fields(translated.resource)['Effective date'], updated_at=e.occurred_at, payload=translated.resource, original_payload=e.payload, warnings=translated.warnings)
                s.add(resource)
            resource.source_version = e.source_version
            resource.resource_type = translated.resource['resourceType']
            resource.status = 'WITHDRAWN' if e.event_type == 'WITHDRAWN' else 'ACTIVE'
            resource.effective_at = clinical_fields(translated.resource)['Effective date']
            resource.updated_at, resource.payload, resource.original_payload, resource.warnings = e.occurred_at, translated.resource, e.payload, translated.warnings
            s.flush()
            s.add(ResourceVersion(resource_id=resource_id, version=e.source_version, payload=translated.resource, original_payload=e.payload, warnings=translated.warnings))
            parent = s.scalar(select(ClinicalEvent).where(ClinicalEvent.resource_id == resource_id).order_by(ClinicalEvent.source_version.desc()))
            event = ClinicalEvent(id=e.id, patient_id=member.patient_id, hospital_id=hospital, source_record_id=e.record_id, resource_id=resource_id, resource_type=resource.resource_type, source_version=e.source_version, event_type=e.event_type, before=before, after=translated.resource, diff=clinical_diff(before, translated.resource), parent_id=parent.id if parent else None, author=e.author, occurred_at=e.occurred_at, ingested_at=now(), transformation_version=TRANSFORMATION_VERSION, correlation_id=e.id, lineage=[*e.lineage, {'hospital_id': hospital, 'source_record_id': e.record_id, 'source_version': e.source_version}], fingerprint=fingerprint(clinical_fields(translated.resource)))
            s.add(event)
            s.flush()
            s.add(Provenance(event_id=event.id, payload=ProvenanceService.create(event, e.record_id)))
            self.deliver(s, event)
            s.flush()
            ConflictDetectionService.detect(s, member.patient_id)
            return 'published'

    @staticmethod
    def deliver(s, event):
        for destination in IdentityLinkingService.receivers(s, event.patient_id, event.hospital_id):
            exists = s.scalar(select(ReviewItem).where(ReviewItem.event_id == event.id, ReviewItem.hospital_id == destination))
            if not exists:
                s.add(DeliveryEvent(event_id=event.id, hospital_id=destination, state='DELIVERED'))
                s.add(ReviewItem(event_id=event.id, hospital_id=destination))

    def backfill_deliveries(self, patient_id):
        with self.db.shared() as s:
            for event in s.scalars(select(ClinicalEvent).where(ClinicalEvent.patient_id == patient_id)):
                self.deliver(s, event)
                s.flush()
