import copy

import pytest

from backend.app.adapters import ADAPTERS, CanonicalClinicalModel, TranslationValidator, clinical_fields, fingerprint
from backend.app.seed import source_payload

FIXTURES = [('medication', {'dose': 500, 'unit': 'mg', 'frequency': 'BID', 'end': '2026-12-01'}), ('allergy', {'reaction': 'Hives', 'severity': 'severe', 'criticality': 'high', 'verification': 'confirmed'}), ('diagnosis', {'verification': 'confirmed', 'end': '2026-12-01'}), ('lab', {'value': 6.8, 'unit': '%', 'status': 'final', 'effective': '2026-11-01T08:00:00+00:00'})]


@pytest.mark.parametrize('origin', ADAPTERS)
@pytest.mark.parametrize('destination', ADAPTERS)
@pytest.mark.parametrize('kind,details', FIXTURES)
def test_bidirectional_roundtrip_preserves_meaning(origin, destination, kind, details):
    source = source_payload(origin, 'record-1', 'LOCAL-1', kind, 'Synthetic concept', 'DEMO_TEST', **details)
    canonical = ADAPTERS[origin].to_canonical(source, 'PAT-001')
    mapped = ADAPTERS[destination].from_canonical(canonical, 'DEST-1')
    roundtrip = ADAPTERS[destination].to_canonical(mapped, 'PAT-001')
    assert clinical_fields(canonical.resource) == clinical_fields(roundtrip.resource)
    assert canonical.resource['resourceType'] != 'MedicationRequest'
    assert canonical.original_payload == source


@pytest.mark.parametrize('hospital', ADAPTERS)
def test_unknown_frequency_and_nested_fields_preserved(hospital):
    source = source_payload(hospital, 'r', 'p', 'medication', 'Synthetic medicine', 'DEMO', dose=10, unit='mg', frequency='UNRECOGNIZED-QX')
    source['customClinicalContext'] = {'important': 'Preserve this clinical source evidence'}
    if 'medication' in source:
        source['medication']['specialInstruction'] = 'Synthetic unknown instruction'
    else:
        source['entry']['details']['specialInstruction'] = 'Synthetic unknown instruction'
    canonical = ADAPTERS[hospital].to_canonical(source)
    codes = [w['code'] for w in canonical.warnings]
    assert 'UNKNOWN_FREQUENCY' in codes
    assert 'UNMAPPED_SOURCE_FIELD' in codes
    assert canonical.original_payload == source
    assert 'timing' not in canonical.resource['dosage'][0]
    reverse = ADAPTERS[hospital].from_canonical(canonical)
    assert ADAPTERS[hospital].unpack(reverse)[0]['frequency'] == 'UNRECOGNIZED-QX'


def test_json_order_is_not_a_change():
    assert fingerprint({'a': 1, 'b': {'x': 2, 'y': 3}}) == fingerprint({'b': {'y': 3, 'x': 2}, 'a': 1})


def test_invalid_fhir_subset_is_rejected():
    with pytest.raises(ValueError):
        TranslationValidator.validate({'resourceType': 'MedicationRequest'})


def test_ambiguous_date_not_guessed():
    payload = source_payload('northstar', 'r', 'p', 'diagnosis', 'Synthetic condition', 'DEMO', verification='confirmed')
    payload['effective'] = 'next Tuesday'
    with pytest.raises(ValueError):
        ADAPTERS['northstar'].to_canonical(payload)


def test_unknown_unit_kept_without_claiming_ucum_mapping():
    source = source_payload('northstar', 'r', 'p', 'medication', 'Synthetic medicine', 'DEMO', dose=1, unit='unknown-scoop', frequency='BID')
    result = ADAPTERS['northstar'].to_canonical(source)
    assert any(w['code'] == 'UNMAPPED_UNIT' for w in result.warnings)
    assert result.resource['dosage'][0]['doseAndRate'][0]['doseQuantity'] == {'value': 1, 'unit': 'unknown-scoop'}


@pytest.mark.parametrize('kind', ['allergy', 'diagnosis'])
def test_entered_in_error_omits_clinical_status_and_roundtrips(kind):
    source = source_payload('northstar', 'r', 'p', kind, 'Synthetic erroneous assertion', 'DEMO', verification='entered-in-error')
    result = ADAPTERS['northstar'].to_canonical(source)
    assert 'clinicalStatus' not in result.resource
    assert clinical_fields(result.resource)['Status'] == 'entered-in-error'
    reverse = ADAPTERS['riverside'].from_canonical(result)
    assert clinical_fields(ADAPTERS['riverside'].to_canonical(reverse).resource) == clinical_fields(result.resource)


def test_timestamps_normalize_equivalent_instants_and_reject_missing_timezone():
    from backend.app.adapters import date_iso
    assert date_iso('2026-11-01T03:30:00-05:00') == date_iso('2026-11-01T08:30:00Z')
    with pytest.raises(ValueError, match='timezone'):
        date_iso('2026-11-01T08:30:00')
