import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def app(tmp_path):
    settings = Settings(shared_url=f'sqlite:///{tmp_path / "clinicalsync_shared.db"}', hospital_a_url=f'sqlite:///{tmp_path / "clinicalsync_northstar.db"}', hospital_b_url=f'sqlite:///{tmp_path / "clinicalsync_riverside.db"}')
    application = create_app(settings)
    with TestClient(application):
        yield application


@pytest.fixture
def clients(app):
    result = {}
    for key, email in [('a', 'northstar'), ('b', 'riverside'), ('admin', 'admin')]:
        client = TestClient(app)
        response = client.post('/api/auth/login', json={'email': f'{email}@clinicalsync.demo', 'password': app.state.settings.demo_password})
        assert response.status_code == 200
        client.headers['x-csrf-token'] = response.json()['csrf_token']
        client.headers['x-workspace-id'] = response.json()['user']['hospital_id']
        result[key] = client
    yield result
    for client in result.values():
        client.close()


@pytest.fixture
def clinical_body():
    return {'category': 'medication', 'display': 'Metformin', 'code': 'METFORMIN', 'status': 'active', 'effective': '2026-11-01', 'dose': 750, 'unit': 'mg', 'frequency': 'BID', 'note': 'Synthetic test update'}
