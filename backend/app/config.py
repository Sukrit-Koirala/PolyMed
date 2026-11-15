import os
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    shared_url: str = field(default_factory=lambda: os.getenv('SHARED_DATABASE_URL', 'sqlite:///.data/clinicalsync_shared.db'))
    hospital_a_url: str = field(default_factory=lambda: os.getenv('HOSPITAL_A_DATABASE_URL', 'sqlite:///.data/clinicalsync_northstar.db'))
    hospital_b_url: str = field(default_factory=lambda: os.getenv('HOSPITAL_B_DATABASE_URL', 'sqlite:///.data/clinicalsync_riverside.db'))
    demo_mode: bool = field(default_factory=lambda: os.getenv('DEMO_MODE', 'true').lower() == 'true')
    secure_cookie: bool = field(default_factory=lambda: os.getenv('SECURE_COOKIE', 'false').lower() == 'true')
    demo_password: str = field(default_factory=lambda: os.getenv('DEMO_PASSWORD', 'ClinicalSync-demo-2026!'))
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,http://testserver').split(',')))
    transcription_provider: str = field(default_factory=lambda: os.getenv('TRANSCRIPTION_PROVIDER', 'manual'))
    note_provider: str = field(default_factory=lambda: os.getenv('NOTE_GENERATION_PROVIDER', 'local'))
    ai_external_enabled: bool = field(default_factory=lambda: os.getenv('AI_EXTERNAL_ENABLED', 'false').lower() == 'true')
    ai_api_key: str = field(default_factory=lambda: os.getenv('AI_API_KEY', ''), repr=False)
    ai_base_url: str = field(default_factory=lambda: os.getenv('AI_BASE_URL', 'https://api.openai.com/v1'))
    transcription_model: str = field(default_factory=lambda: os.getenv('TRANSCRIPTION_MODEL', 'gpt-4o-mini-transcribe'))
    note_model: str = field(default_factory=lambda: os.getenv('NOTE_MODEL', 'gpt-4.1-mini'))
    transcript_retention_days: int = field(default_factory=lambda: int(os.getenv('TRANSCRIPT_RETENTION_DAYS', '7')))
    audio_max_bytes: int = field(default_factory=lambda: int(os.getenv('AUDIO_MAX_BYTES', '15728640')))
    extra_hospitals: dict = field(default_factory=lambda: json.loads(os.getenv('HOSPITAL_CONFIG_JSON', '{}')), repr=False)
    bridge_enabled: bool = field(default_factory=lambda: os.getenv('BRIDGE_ENABLED', 'true').lower() == 'true')
    bridge_password: str = field(default_factory=lambda: os.getenv('EHR_BRIDGE_DEMO_PASSWORD', 'EHRBridge-demo-2026!'), repr=False)

    def __post_init__(self):
        for hospital_id, definition in self.extra_hospitals.items():
            if hospital_id in ('northstar', 'riverside', 'memorial', 'valley') or not re.fullmatch(r'[a-z][a-z0-9-]{1,19}', hospital_id):
                raise ValueError('Additional hospital identifiers must be unique lowercase slugs')
            if definition.get('adapter') not in ('epic-mock', 'oracle-mock') or not definition.get('name') or not definition.get('database_url'):
                raise ValueError('Additional hospitals require name, adapter, and database_url')
            if any(role not in ('clinician', 'admin') for role in definition.get('memberships', {}).values()):
                raise ValueError('Unsupported configured hospital role')
        if self.transcription_provider not in ('manual', 'openai') or self.note_provider not in ('local', 'openai'):
            raise ValueError('Unsupported documentation provider configuration')
        if not 0 <= self.transcript_retention_days <= 365 or not 1024 <= self.audio_max_bytes <= 25 * 1024 * 1024:
            raise ValueError('Invalid documentation retention or upload limit')
        urls = [self.shared_url, *self.hospital_urls.values()]
        if len(set(urls)) != len(urls):
            raise ValueError('ClinicalSync requires a distinct database for the shared layer and each hospital')
        for url in urls:
            if url.startswith('sqlite:///'):
                Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)

    @property
    def hospital_urls(self):
        bridge = {}
        if self.bridge_enabled:
            from sqlalchemy.engine import make_url
            base = make_url(self.shared_url)
            for hospital in ('memorial', 'valley'):
                database = str(Path(base.database).with_name('ehrbridge_' + hospital + '.db')) if base.drivername.startswith('sqlite') else 'ehrbridge_' + hospital
                bridge[hospital] = os.getenv(hospital.upper() + '_DATABASE_URL') or base.set(database=database).render_as_string(hide_password=False)
        return {'northstar': self.hospital_a_url, 'riverside': self.hospital_b_url, **bridge, **{hospital_id: definition['database_url'] for hospital_id, definition in self.extra_hospitals.items()}}
