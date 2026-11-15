import copy

from sqlalchemy import func, select

from backend.app.adapters import ADAPTERS
from backend.app.models import *
from backend.app.seed import source_payload
from backend.app.services import ChangeDetectionService, ConflictDetectionService, SynchronizationService


def counts(db):
    with db.shared() as s:
        return {model.__tablename__: s.scalar(select(func.count()).select_from(model)) for model in (ClinicalEvent, ReviewItem, ResourceVersion, Provenance)}


def test_shared_view_and_source_attribution(clients):
    response = clients['b'].get('/api/patients/PAT-001')
    assert response.status_code == 200
    patient = response.json()
    assert patient['name'] == 'Maya Bennett'
    assert {m['local_patient_id'] for m in patient['members']} == {'NS-1001', 'RG-8824'}
    assert {r['hospital_id'] for r in patient['records']} == {'northstar', 'riverside'}
    assert len(patient['records']) == 10
    assert all(r['original_payload'] for r in patient['records'])
    filtered = clients['a'].get('/api/patients/PAT-001?resource_type=MedicationStatement&source=northstar&date_from=2026-11-01&date_to=2026-11-01').json()
    assert len(filtered['records']) == 1


def test_full_judge_workflow_accept_never_writes_destination(clients, app):
    a, b = clients['a'], clients['b']
    local_before = b.get('/api/local/patients/RG-8824').json()
    simulated = a.post('/api/demo/scenario')
    assert simulated.status_code == 200
    assert simulated.json()['sync']['published'] == 1
    reviews = b.get('/api/reviews').json()
    item = next(r for r in reviews if r['event']['source_record_id'] == 'allergy-penicillin' and r['event']['source_version'] == 2)
    assert item['event']['event_type'] == 'CORRECTED'
    assert any(d['field'] == 'Severity' for d in item['event']['diff'])
    assert item['local_comparison'] == []
    assert a.post(f"/api/reviews/{item['id']}/decisions", json={'decision': 'ACCEPTED', 'note': '', 'expected_revision': 1}).status_code == 403
    decision = b.post(f"/api/reviews/{item['id']}/decisions", json={'decision': 'ACCEPTED', 'note': 'Reviewed synthetic source evidence', 'expected_revision': 1})
    assert decision.status_code == 200
    assert decision.json()['ehr_updated'] is False
    refreshed = b.get(f"/api/reviews/{item['id']}").json()
    assert refreshed['status'] == 'ACCEPTED'
    assert refreshed['decisions'][0]['reviewer'] == 'Dr. Daniel Reed'
    assert local_before == b.get('/api/local/patients/RG-8824').json()
    source = b.get('/api/records/northstar-allergy-penicillin').json()
    assert len(source['versions']) == 2
    assert len(source['provenance']) == 2
    assert source['review_status'] == 'ACCEPTED'
    assert source['destination_preview']['clinicalType'] == 'ALLERGY'
    diff = b.get('/api/records/northstar-allergy-penicillin/compare?before=1&after=2').json()
    assert any(d['field'] == 'Criticality' and d['after'] == 'high' for d in diff['diff'])
    before_replay = counts(app.state.db)
    replay = clients['admin'].post('/api/demo/replay').json()
    assert replay['published'] == 0 and replay['suppressed'] == 1
    assert counts(app.state.db) == before_replay


def test_create_update_correct_withdraw_and_local_history(clients, app, clinical_body):
    a, b = clients['a'], clients['b']
    before_b = b.get('/api/local/patients/RG-8824').json()
    created = a.post('/api/local/patients/NS-1001/records', json=clinical_body)
    assert created.status_code == 201
    rid = created.json()['id']
    assert a.post('/api/sync').json()[0]['published'] == 1
    changed = clinical_body | {'dose': 850, 'expected_version': 1}
    assert a.put(f'/api/local/records/{rid}', json=changed).status_code == 200
    assert a.put(f'/api/local/records/{rid}', json=changed).status_code == 409
    assert a.post(f'/api/local/records/{rid}/correct', json=changed | {'dose': 900, 'expected_version': 2}).status_code == 200
    assert a.post(f'/api/local/records/{rid}/withdraw', json={'expected_version': 3, 'note': 'Synthetic documentation withdrawn'}).status_code == 200
    assert a.post('/api/sync').json()[0]['published'] == 3
    history = a.get(f'/api/local/records/{rid}/history').json()
    assert [v['event_type'] for v in history] == ['WITHDRAWN', 'CORRECTED', 'UPDATED', 'CREATED']
    shared = a.get(f'/api/records/northstar-{rid}').json()
    assert shared['status'] == 'WITHDRAWN'
    assert len(shared['versions']) == len(shared['events']) == len(shared['provenance']) == 4
    assert b.get('/api/local/patients/RG-8824').json() == before_b


def test_same_clinical_update_is_a_noop(clients):
    a = clients['a']
    before = a.get('/api/local/patients/NS-1001').json()['records'][0]
    d = before['input']
    body = {k: d[k] for k in ['display', 'code', 'system', 'status', 'effective', 'note', 'dose', 'unit', 'frequency'] if k in d}
    body.update(category='medication', expected_version=1)
    result = a.put(f"/api/local/records/{before['id']}", json=body)
    assert result.status_code == 200
    assert result.json()['version'] == 1
    assert result.json()['outbox_pending'] is False


def test_rejection_preserves_source_and_review_history(clients):
    b = clients['b']
    r = b.get('/api/reviews').json()[0]
    for revision, decision in enumerate(['DEFERRED', 'INVESTIGATING', 'REJECTED'], 1):
        result = b.post(f"/api/reviews/{r['id']}/decisions", json={'decision': decision, 'note': 'Synthetic reviewer note', 'expected_revision': revision})
        assert result.status_code == 200
    assert b.get(f"/api/reviews/{r['id']}").json()['status'] == 'REJECTED'
    assert len(b.get(f"/api/reviews/{r['id']}").json()['decisions']) == 3
    assert b.get(f"/api/records/{r['event']['resource_id']}").status_code == 200


def test_stale_review_rejected(clients):
    b = clients['b']
    r = b.get('/api/reviews').json()[0]
    body = {'decision': 'DEFERRED', 'note': '', 'expected_revision': 1}
    assert b.post(f"/api/reviews/{r['id']}/decisions", json=body).status_code == 200
    assert b.post(f"/api/reviews/{r['id']}/decisions", json=body).status_code == 409


def test_medication_conflict_but_missing_allergy_is_not_negative(clients):
    conflicts = clients['a'].get('/api/patients/PAT-001/conflicts').json()
    medication = [c for c in conflicts if c['category'] == 'MEDICATION_DOSE_DISCREPANCY']
    assert len(medication) == 1
    assert not any(c['category'] == 'ALLERGY_ASSERTION_DISCREPANCY' for c in conflicts)
    assert any(d['field'] == 'Dose' and {d['before'], d['after']} == {500, 1000} for d in medication[0]['differences'])


def test_different_medications_not_conflicting(clients, clinical_body):
    before = {c['id'] for c in clients['a'].get('/api/patients/PAT-001/conflicts').json()}
    body = clinical_body | {'display': 'Synthetic other medicine', 'code': 'OTHER_MEDICINE'}
    assert clients['b'].post('/api/local/patients/RG-8824/records', json=body).status_code == 201
    clients['b'].post('/api/sync')
    conflicts = clients['a'].get('/api/patients/PAT-001/conflicts').json()
    assert {c['id'] for c in conflicts} == before


def test_nonoverlapping_medications_not_dose_conflict(clients, clinical_body):
    a = clients['a']
    body = clinical_body | {'dose': 100, 'effective': '2025-01-01', 'end': '2025-02-01', 'expected_version': 1}
    assert a.put('/api/local/records/med-metformin', json=body).status_code == 200
    a.post('/api/sync')
    assert not any(c['active'] and c['category'] == 'MEDICATION_DOSE_DISCREPANCY' for c in a.get('/api/patients/PAT-001/conflicts').json())


def test_explicit_negative_allergy_conflicts(clients):
    b = clients['b']
    body = {'category': 'allergy', 'display': 'No known allergies (synthetic assertion)', 'code': 'NO_KNOWN_ALLERGIES', 'status': 'active', 'effective': '2026-11-01', 'reaction': '', 'criticality': 'unable-to-assess'}
    assert b.post('/api/local/patients/RG-8824/records', json=body).status_code == 201
    b.post('/api/sync')
    assert any(c['category'] == 'ALLERGY_ASSERTION_DISCREPANCY' for c in b.get('/api/patients/PAT-001/conflicts').json())


def test_same_collection_lab_discrepancy(clients):
    body = {'category': 'lab', 'display': 'Hemoglobin A1c', 'code': '4548-4', 'system': 'http://loinc.org', 'status': 'final', 'effective': '2026-11-01T08:30:00+00:00', 'value': 8.0, 'unit': '%'}
    assert clients['b'].post('/api/local/patients/RG-8824/records', json=body).status_code == 201
    clients['b'].post('/api/sync')
    assert any(c['category'] == 'LAB_RESULT_DISCREPANCY' for c in clients['a'].get('/api/patients/PAT-001/conflicts').json())


def test_equivalent_entries_keep_provenance(clients, clinical_body):
    body = clinical_body | {'dose': 500, 'note': 'Synthetic demonstration fixture.', 'expected_version': 1}
    assert clients['b'].put('/api/local/records/med-metformin', json=body).status_code == 200
    clients['b'].post('/api/sync')
    conflicts = clients['a'].get('/api/patients/PAT-001/conflicts').json()
    assert any(c['active'] and c['category'] == 'CLINICALLY_EQUIVALENT' for c in conflicts)
    patient = clients['a'].get('/api/patients/PAT-001').json()
    assert len([r for r in patient['records'] if r['resource_type'] == 'MedicationStatement']) == 2


def test_failed_publication_retry_and_freshness(app, clients):
    db = app.state.db
    previous = clients['a'].get('/api/sync').json()['sources'][0]['last_successful_sync']
    with db.local('northstar') as local:
        record = local.get(LocalRecord, 'med-metformin')
        event = OutboxEvent(record_id=record.id, patient_id=record.patient_id, category='medication', source_version=2, event_type='UPDATED', payload={'malformed': 'synthetic fixture'}, author='Test author', occurred_at=now(), lineage=[])
        local.add(event)
        local.flush()
        event_id = event.id
        repaired_payload = copy.deepcopy(record.payload)
        repaired_payload['medication']['dose'] = 750
    job = SynchronizationService(db).run('northstar')
    assert job['failed'] == 1
    status = clients['a'].get('/api/sync').json()
    northstar = next(s for s in status['sources'] if s['id'] == 'northstar')
    assert northstar['freshness'] == 'FAILED'
    assert northstar['last_successful_sync'] == previous
    assert status['outbox_attention'][0]['retry_count'] == 1
    with db.local('northstar') as local:
        local.get(OutboxEvent, event_id).payload = repaired_payload
    assert SynchronizationService(db).run('northstar')['published'] == 1
    before = counts(db)
    assert SynchronizationService(db).run('northstar')['published'] == 0
    assert counts(db) == before


def test_origin_lineage_prevents_circular_publication(app):
    db = app.state.db
    with db.shared() as s:
        original = s.scalar(select(ClinicalEvent).where(ClinicalEvent.hospital_id == 'northstar'))
        original_id = original.id
    with db.local('riverside') as local:
        payload = source_payload('riverside', 'imported-loop', 'RG-8824', 'diagnosis', 'Synthetic imported assertion', 'IMPORTED', verification='confirmed')
        ChangeDetectionService.save(local, 'riverside', 'RG-8824', 'diagnosis', payload, 'Demo test', 'imported-loop', lineage=[original_id])
    before = counts(db)
    result = SynchronizationService(db).run('riverside')
    assert result['suppressed'] == 1
    assert counts(db) == before
    for _ in range(3):
        SynchronizationService(db).run('northstar')
        SynchronizationService(db).run('riverside')
    assert counts(db) == before


def test_history_is_append_only(app):
    import pytest
    with pytest.raises(ValueError, match='append-only'):
        with app.state.db.shared() as s:
            e = s.scalar(select(ClinicalEvent))
            e.author = 'Attempt to rewrite history'


def test_concurrent_source_updates_have_one_winner(clients, clinical_body):
    from concurrent.futures import ThreadPoolExecutor
    body = clinical_body | {'expected_version': 1}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda dose: clients['a'].put('/api/local/records/med-metformin', json=body | {'dose': dose}).status_code, [700, 800]))
    assert sorted(results) == [200, 409]
