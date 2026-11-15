from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .bridge_seed import CATEGORIES


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Registration(Strict):
    name: str = Field(min_length=2, max_length=120)
    birth_date: date
    sex: str = Field(default='unknown', max_length=40)
    gender_identity: str = Field(default='Not provided', max_length=100)
    phone: str = Field(default='Unknown', max_length=80)
    email: str = Field(default='Unknown', max_length=160)
    address: str = Field(default='Unknown', max_length=300)
    emergency_contact: str = Field(default='Unknown', max_length=200)
    language: str = Field(default='Unknown', max_length=80)
    reported_blood_group: str = Field(default='Unknown', max_length=40)
    insurance_provider: str = Field(default='Unknown', max_length=120)
    insurance_plan: str = Field(default='Unknown', max_length=120)
    synthetic_confirmed: Literal[True]
    separate_identity_confirmed: bool = False

    @field_validator('birth_date')
    @classmethod
    def valid_birth(cls, value):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        if value > datetime.now(ZoneInfo('America/Chicago')).date() or value.year < 1900:
            raise ValueError('Enter a valid date of birth')
        return value

    @field_validator('name')
    @classmethod
    def trim_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('Enter a full name')
        return value.strip()


class AccessInput(Strict):
    patient_id: str
    source_hospitals: list[str] = Field(min_length=1, max_length=5)
    categories: list[str] = Field(min_length=1, max_length=10)
    purpose: str = Field(min_length=5, max_length=1000)
    encounter_reason: str = Field(min_length=3, max_length=1000)
    duration_hours: int = Field(default=4, ge=1, le=24)

    @field_validator('purpose', 'encounter_reason')
    @classmethod
    def meaningful_scope(cls, value):
        if len(value.strip()) < 5:
            raise ValueError('Explain the purpose and encounter reason clearly')
        return value.strip()

    @field_validator('categories')
    @classmethod
    def categories_valid(cls, value):
        if any(c not in CATEGORIES for c in value):
            raise ValueError('Unsupported requested category')
        return sorted(set(value))


class Decision(Strict):
    action: Literal['APPROVE', 'DENY', 'INVESTIGATE', 'REVOKE', 'NEW_CODE']
    message: str = Field(default='', max_length=1000)


class Redeem(Strict):
    code: str = Field(pattern=r'^\d{6}$')


class SessionInput(Strict):
    patient_id: str
    reason: str = Field(min_length=3, max_length=1000)
    status: Literal['DRAFT', 'SCHEDULED', 'ACTIVE', 'COMPLETED'] = 'DRAFT'
    intake: dict = Field(default_factory=dict)
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Enter a session reason')
        return value.strip()

    @field_validator('intake')
    @classmethod
    def bounded_json(cls, value):
        import json
        if len(json.dumps(value)) > 120000:
            raise ValueError('Intake exceeds the development size limit')
        return value


class TaskInput(Strict):
    status: Literal['TODO', 'IN_PROGRESS', 'DONE']


class TaskCreate(Strict):
    kind: Literal['documentation', 'record_review', 'missing_info', 'patient_approval', 'insurance', 'follow_up']
    title: str = Field(min_length=3, max_length=160)

    @field_validator('title')
    @classmethod
    def meaningful_title(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Enter a task title')
        return value.strip()


class TranscriptInput(Strict):
    transcript: str = Field(min_length=1, max_length=60000)


class RecordReviewInput(Strict):
    action: Literal['REVIEWED', 'FLAGGED']
    note: str = Field(min_length=3, max_length=1000)

    @field_validator('note')
    @classmethod
    def meaningful_note(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Enter a review note')
        return value.strip()


class InsuranceInput(Strict):
    provider: str = Field(min_length=2, max_length=120)
    plan: str = Field(min_length=2, max_length=120)
    member_id: str = Field(min_length=2, max_length=120)
    group_number: str = Field(default='Unknown', max_length=120)
    coverage_start: date | None = None
    coverage_end: date | None = None


class StaffInput(Strict):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=12, max_length=200)
    role: Literal['clinician', 'admin']


class MembershipInput(Strict):
    active: bool
    role: Literal['clinician', 'admin']


class ConnectionInput(Strict):
    status: Literal['CONNECTED', 'PAUSED']
    department: str = Field(min_length=2, max_length=120)
    supported_categories: list[str] | None = None

    @field_validator('supported_categories')
    @classmethod
    def supported_valid(cls, value):
        if value is not None and any(c not in CATEGORIES for c in value):
            raise ValueError('Unsupported mock category')
        return sorted(set(value)) if value is not None else None
