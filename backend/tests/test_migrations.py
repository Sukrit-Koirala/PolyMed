from argparse import Namespace

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, inspect, select

from backend.app.models import LocalBase, SharedBase


def test_migrations_create_three_independent_schemas(tmp_path, monkeypatch):
    for target, env, metadata in [('shared', 'SHARED_DATABASE_URL', SharedBase.metadata), ('northstar', 'HOSPITAL_A_DATABASE_URL', LocalBase.metadata), ('riverside', 'HOSPITAL_B_DATABASE_URL', LocalBase.metadata)]:
        url = f'sqlite:///{tmp_path / (target + ".db")}'
        monkeypatch.setenv(env, url)
        config = Config('backend/alembic.ini')
        config.cmd_opts = Namespace(x=[f'target={target}'])
        command.upgrade(config, 'head')
        engine = create_engine(url)
        try:
            inspector = inspect(engine)
            assert set(metadata.tables) <= set(inspector.get_table_names())
            for name, table in metadata.tables.items():
                assert set(table.c.keys()) == {c['name'] for c in inspector.get_columns(name)}
            unique_table = 'clinical_events' if target == 'shared' else 'outbox_events'
            assert inspector.get_unique_constraints(unique_table)
        finally:
            engine.dispose()


def test_workspace_upgrade_preserves_existing_accounts_sessions_and_source_payloads(tmp_path, monkeypatch):
    for target, env in [('shared', 'SHARED_DATABASE_URL'), ('northstar', 'HOSPITAL_A_DATABASE_URL'), ('riverside', 'HOSPITAL_B_DATABASE_URL')]:
        url = f'sqlite:///{tmp_path / (target + "-upgrade.db")}'
        monkeypatch.setenv(env, url)
        config = Config('backend/alembic.ini')
        config.cmd_opts = Namespace(x=[f'target={target}'])
        command.upgrade(config, '0001')
        engine = create_engine(url)
        try:
            old = MetaData()
            old.reflect(engine)
            with engine.begin() as connection:
                if target == 'shared':
                    connection.execute(old.tables['hospitals'].insert(), {'id': 'northstar', 'name': 'Preserved hospital', 'ehr': 'epic-mock'})
                    connection.execute(old.tables['users'].insert(), {'id': 'existing-user', 'email': 'existing@example.test', 'name': 'Existing clinician', 'password_hash': 'preserve-this-hash', 'hospital_id': 'northstar', 'role': 'clinician'})
                    connection.execute(old.tables['sessions'].insert(), {'token_hash': 'preserve-session', 'user_id': 'existing-user', 'csrf': 'preserve-csrf', 'expires_at': '2027-01-01T00:00:00Z'})
                else:
                    connection.execute(old.tables['patients'].insert(), {'id': 'existing-patient', 'name': 'Existing fictional patient', 'birth_date': '1981-06-02', 'synthetic': True})
                    connection.execute(old.tables['clinical_records'].insert(), {'id': 'existing-record', 'patient_id': 'existing-patient', 'category': 'medication', 'version': 3, 'state': 'ACTIVE', 'payload': {'original': {'dose': 42, 'unmapped': 'preserve exactly'}}, 'author': 'Original author', 'updated_at': '2026-10-01T10:00:00Z'})
            command.upgrade(config, 'head')
            current = MetaData()
            current.reflect(engine)
            with engine.connect() as connection:
                if target == 'shared':
                    user = connection.execute(select(current.tables['users'])).mappings().one()
                    assert user['password_hash'] == 'preserve-this-hash'
                    session = connection.execute(select(current.tables['sessions'])).mappings().one()
                    assert session['token_hash'] == 'preserve-session' and session['csrf'] == 'preserve-csrf'
                    assert session['active_hospital_id'] == 'northstar'
                    membership = connection.execute(select(current.tables['hospital_memberships'])).mappings().one()
                    assert (membership['user_id'], membership['hospital_id'], membership['role'], membership['active']) == ('existing-user', 'northstar', 'clinician', True)
                else:
                    patient = connection.execute(select(current.tables['patients'])).mappings().one()
                    assert patient['name'] == 'Existing fictional patient' and patient['care_status'] == 'active'
                    record = connection.execute(select(current.tables['clinical_records'])).mappings().one()
                    assert record['version'] == 3 and record['author'] == 'Original author'
                    assert record['payload'] == {'original': {'dose': 42, 'unmapped': 'preserve exactly'}}
        finally:
            engine.dispose()
