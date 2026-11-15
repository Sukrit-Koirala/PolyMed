from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .models import LocalBase, SharedBase


def engine_for(url):
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def pragmas(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    return engine


class Databases:
    def __init__(self, settings):
        self.settings = settings
        from .adapters import ADAPTERS, EpicMockAdapter, OracleMockAdapter
        adapter_types = {'epic-mock': EpicMockAdapter, 'oracle-mock': OracleMockAdapter}
        for hospital_id, definition in settings.extra_hospitals.items():
            adapter = adapter_types[definition['adapter']]()
            adapter.hospital_id = hospital_id
            ADAPTERS[hospital_id] = adapter
        self.shared_engine = engine_for(settings.shared_url)
        self.local_engines = {h: engine_for(url) for h, url in settings.hospital_urls.items()}
        self.shared_factory = sessionmaker(self.shared_engine, expire_on_commit=False)
        self.local_factories = {h: sessionmaker(e, expire_on_commit=False) for h, e in self.local_engines.items()}

    def create_schema(self):
        SharedBase.metadata.create_all(self.shared_engine)
        for engine in self.local_engines.values():
            LocalBase.metadata.create_all(engine)

    @contextmanager
    def shared(self):
        with self.shared_factory.begin() as session:
            yield session

    @contextmanager
    def local(self, hospital):
        with self.local_factories[hospital].begin() as session:
            yield session

    def dispose(self):
        self.shared_engine.dispose()
        for engine in self.local_engines.values():
            engine.dispose()
