import math
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .adapters import DEMO_SYSTEM, date_iso


class LoginInput(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ClinicalInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Literal['medication', 'allergy', 'diagnosis', 'lab', 'vaccination']
    display: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=100)
    system: str = Field(default=DEMO_SYSTEM, max_length=200)
    status: str = Field(default='active', max_length=40)
    effective: str
    end: str | None = None
    dose: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    unit: str = Field(default='mg', min_length=1, max_length=40)
    frequency: str = Field(default='BID', max_length=100)
    reaction: str = Field(default='', max_length=300)
    severity: Literal['mild', 'moderate', 'severe'] = 'moderate'
    criticality: Literal['low', 'high', 'unable-to-assess'] = 'unable-to-assess'
    verification: Literal['unconfirmed', 'confirmed', 'refuted', 'entered-in-error'] = 'confirmed'
    value: float | None = Field(default=None, allow_inf_nan=False)
    note: str = Field(default='', max_length=2000)
    expected_version: int | None = Field(default=None, ge=1)
    dose_number: int | None = Field(default=None, ge=1, le=100)
    dose_amount: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    dose_unit: str = Field(default='mL', max_length=40)
    route: str = Field(default='', max_length=100)
    site: str = Field(default='', max_length=100)
    lot_number: str = Field(default='', max_length=100)
    provider: str = Field(default='', max_length=200)
    historical: bool = False
    status_reason: str = Field(default='', max_length=300)

    @model_validator(mode='after')
    def valid_clinical_fields(self):
        self.effective = date_iso(self.effective)
        if self.end:
            self.end = date_iso(self.end)
            if self.end < self.effective:
                raise ValueError('End date must follow effective date')
        if self.category == 'medication' and self.dose is None:
            raise ValueError('Documented medication dose is required')
        if self.category == 'lab' and self.value is None:
            raise ValueError('Laboratory result is required')
        allowed = {'medication': {'active', 'completed', 'entered-in-error', 'intended', 'stopped', 'on-hold', 'unknown', 'not-taken'}, 'allergy': {'active', 'inactive', 'resolved'}, 'diagnosis': {'active', 'recurrence', 'relapse', 'inactive', 'remission', 'resolved'}, 'lab': {'registered', 'preliminary', 'final', 'amended', 'corrected', 'cancelled', 'entered-in-error', 'unknown'}, 'vaccination': {'completed', 'not-done', 'entered-in-error', 'planned'}}
        if self.status not in allowed[self.category]:
            raise ValueError('Invalid status for this clinical category')
        if self.category == 'vaccination' and self.status in ('completed', 'not-done') and self.effective[:10] > datetime.now(ZoneInfo('America/Chicago')).date().isoformat():
            raise ValueError('Future vaccinations must be planned, not recorded as completed or not administered')
        return self


class WithdrawInput(BaseModel):
    expected_version: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)


class ReviewInput(BaseModel):
    decision: Literal['ACCEPTED', 'DEFERRED', 'REJECTED', 'INVESTIGATING']
    note: str = Field(default='', max_length=2000)
    expected_revision: int = Field(ge=1)


class IdentityInput(BaseModel):
    decision: Literal['CONFIRMED', 'REJECTED']
    note: str = Field(min_length=5, max_length=2000)


class ResetInput(BaseModel):
    confirmation: Literal['RESET SYNTHETIC DEMO']


class WorkspaceInput(BaseModel):
    hospital_id: str = Field(min_length=1, max_length=100)


class PatientRegistration(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    birth_date: date
    administrative_gender: Literal['male', 'female', 'other', 'unknown'] = 'unknown'
    contact: str = Field(default='', max_length=200)
    local_patient_id: str | None = Field(default=None, min_length=2, max_length=60, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]+$')
    synthetic_confirmed: Literal[True]
    match_token: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def valid_demographics(self):
        if self.birth_date > datetime.now(ZoneInfo('America/Chicago')).date():
            raise ValueError('Date of birth cannot be in the future')
        return self


class SOAPSections(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subjective: str = Field(default='', max_length=60000)
    objective: str = Field(default='', max_length=60000)
    assessment: str = Field(default='', max_length=60000)
    plan: str = Field(default='', max_length=60000)


class NoteDraftInput(BaseModel):
    title: str = Field(default='Consultation note', min_length=1, max_length=200)
    transcript: str = Field(default='', max_length=60000)
    sections: SOAPSections = Field(default_factory=SOAPSections)

    @field_validator('title', mode='before')
    @classmethod
    def title_is_present(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('A note title is required')
        return value.strip()


class NoteDraftUpdate(NoteDraftInput):
    expected_revision: int = Field(ge=1)


class NoteGenerateInput(BaseModel):
    expected_revision: int = Field(ge=1)
    external_processing_consent: bool = False
    transcript: str | None = Field(default=None, max_length=60000)


class NoteApproveInput(BaseModel):
    expected_revision: int = Field(ge=1)
    approval_confirmed: Literal[True]


class RecordingEventInput(BaseModel):
    recording_id: UUID
    action: Literal['STARTED', 'STOPPED', 'CANCELLED']
    consent_confirmed: Literal[True]


class ConflictReviewInput(BaseModel):
    status: Literal['NEEDS_REVIEW', 'INVESTIGATING', 'RESOLVED']
    note: str = Field(min_length=3, max_length=2000)
    expected_revision: int = Field(ge=0)


class IdentityLinkRequest(BaseModel):
    hospital_id: str = Field(min_length=1, max_length=100)
    local_patient_id: str = Field(min_length=1, max_length=60)
    target_patient_id: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=5, max_length=2000)
