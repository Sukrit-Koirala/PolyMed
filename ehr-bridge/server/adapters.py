"""Explicit demo formats, not official Epic/Oracle schemas or vendor connections."""
import copy
import json
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Medication(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    dose: str = Field(default='Not documented', max_length=120)
    unit: str = Field(default='', max_length=40)
    frequency: str = Field(default='Not documented', max_length=120)


class GeneralVisit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    patient_id: str
    visit_date: date
    reason: str = Field(min_length=3, max_length=300)
    notes: str = Field(default='', max_length=20000)
    medications: list[Medication] = Field(default_factory=list, max_length=100)
    allergies: list[str] = Field(default_factory=list, max_length=100)
    observations: dict[str, str] = Field(default_factory=dict)
    additional: dict = Field(default_factory=dict)

    @field_validator('reason')
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 3:
            raise ValueError('Enter a visit reason')
        return value.strip()


class Adapter:
    """Replace this interface implementation with a supported vendor connector later."""
    kind = ''

    def normalize(self, payload, patient_id):
        raise NotImplementedError

    def represent(self, canonical, local_id):
        raise NotImplementedError


class EpicDemo(Adapter):
    kind = 'epic'

    def normalize(self, payload, patient_id):
        if payload.get('patientId') != patient_id:
            raise ValueError('Payload patient ID must match the selected patient')
        known = {'patientId','visitDate','chiefComplaint','clinicalNotes','medications','allergies','observations','additionalInformation'}
        extra = copy.deepcopy(payload.get('additionalInformation', {}))
        extra.update({key:value for key,value in payload.items() if key not in known})
        return GeneralVisit(patient_id=patient_id, visit_date=payload.get('visitDate'), reason=payload.get('chiefComplaint'), notes=payload.get('clinicalNotes',''), medications=payload.get('medications',[]), allergies=payload.get('allergies',[]), observations=payload.get('observations',{}), additional=extra).model_dump(mode='json')

    def represent(self, canonical, local_id):
        return {'patientId':local_id,'visitDate':canonical['visit_date'],'chiefComplaint':canonical['reason'],'clinicalNotes':canonical['notes'],'medications':canonical['medications'],'allergies':canonical['allergies'],'observations':canonical['observations']}, canonical.get('additional',{})


class OracleDemo(Adapter):
    kind = 'oracle'

    def normalize(self, payload, patient_id):
        if payload.get('personId') != patient_id:
            raise ValueError('Payload patient ID must match the selected patient')
        encounter = payload.get('encounter',{})
        known = {'personId','encounter','drugList','allergyList','measurements','extraClinicalData'}
        extra = copy.deepcopy(payload.get('extraClinicalData',{}))
        extra.update({key:value for key,value in payload.items() if key not in known})
        if isinstance(encounter, dict):
            unmapped = {k:v for k,v in encounter.items() if k not in ('date','reason','note')}
            if unmapped:extra['sourceEncounterFields'] = unmapped
        medication_extras=[{key:value for key,value in item.items() if key not in ('drug','strength','unit','schedule')} for item in payload.get('drugList',[])]
        if any(medication_extras):extra['sourceMedicationFields']=medication_extras
        return GeneralVisit(patient_id=patient_id,visit_date=encounter.get('date'),reason=encounter.get('reason'),notes=encounter.get('note',''),medications=[{'name':m['drug'],'dose':str(m.get('strength','Not documented')),'unit':m.get('unit',''),'frequency':m.get('schedule','Not documented')} for m in payload.get('drugList',[])],allergies=payload.get('allergyList',[]),observations=payload.get('measurements',{}),additional=extra).model_dump(mode='json')

    def represent(self, canonical, local_id):
        return {'personId':local_id,'encounter':{'date':canonical['visit_date'],'reason':canonical['reason'],'note':canonical['notes']},'drugList':[{'drug':m['name'],'strength':m['dose'],'unit':m['unit'],'schedule':m['frequency']} for m in canonical['medications']],'allergyList':canonical['allergies'],'measurements':canonical['observations'],'extraClinicalData':canonical.get('additional',{})}, {}


ADAPTERS = {'epic':EpicDemo(),'oracle':OracleDemo()}


def make_native(kind, canonical, patient_id):
    payload, preserved = ADAPTERS[kind].represent(canonical, patient_id)
    if preserved:payload['additionalInformation'] = preserved
    return payload


def changes(before, after, prefix=''):
    out=[]
    for key in sorted(set(before)|set(after)):
        a,b=before.get(key),after.get(key)
        if a==b:continue
        label=f'{prefix}{key}'
        if isinstance(a,dict) and isinstance(b,dict):out.extend(changes(a,b,label+'.'))
        else:out.append({'field':label,'before':a,'after':b,'change':'added' if key not in before else 'removed' if key not in after else 'modified'})
    return out
