/** Entry labels and display units, not an exhaustive terminology or FHIR profile. */
export type MeasurementDefinition = {
  key: string; label: string; category: string; units: string[]; aliases: string[];
  kind: 'number' | 'blood-pressure' | 'text';
};

function measure(key: string, category: string, units: string[], aliases: string[] = [], kind: MeasurementDefinition['kind'] = 'number', label = key): MeasurementDefinition {
  return {key, label, category, units, aliases, kind};
}

export const MEASUREMENTS: MeasurementDefinition[] = [
  measure('Blood pressure', 'Vital signs', ['mmHg', 'kPa'], ['BP', 'blood_pressure', 'bloodPressure'], 'blood-pressure'),
  measure('Heart rate', 'Vital signs', ['beats/min'], ['HR', 'heart_rate']),
  measure('Respiratory rate', 'Vital signs', ['breaths/min'], ['RR', 'respiration rate']),
  measure('Temperature', 'Vital signs', ['°C', '°F'], ['Body temperature', 'Temp']),
  measure('Oxygen saturation', 'Vital signs', ['%'], ['SpO2', 'SpO₂', 'SPO2', 'pulse oximetry'], 'number', 'Oxygen saturation (SpO2)'),
  measure('Height', 'Vital signs', ['cm', 'm', 'in'], ['Body height']),
  measure('Weight', 'Vital signs', ['kg', 'lb', 'g'], ['Body weight']),
  measure('Pain score', 'Vital signs', ['/10'], ['Pain score 0-10']),

  measure('Hemoglobin', 'Blood count', ['g/dL', 'g/L'], ['Hb', 'Hgb']),
  measure('Hematocrit', 'Blood count', ['%', 'L/L'], ['Hct']),
  measure('White blood cell count', 'Blood count', ['x 10^9/L', 'cells/uL'], ['WBC', 'white cells']),
  measure('Red blood cell count', 'Blood count', ['x 10^12/L', 'million/uL'], ['RBC', 'red cells']),
  measure('Platelet count', 'Blood count', ['x 10^9/L', 'cells/uL'], ['Platelets', 'PLT']),
  measure('Mean corpuscular volume', 'Blood count', ['fL'], ['MCV']),
  measure('Mean corpuscular hemoglobin', 'Blood count', ['pg'], ['MCH']),
  measure('Mean corpuscular hemoglobin concentration', 'Blood count', ['g/dL', 'g/L'], ['MCHC']),
  measure('Red cell distribution width', 'Blood count', ['%'], ['RDW']),
  measure('Neutrophil count', 'Blood count', ['x 10^9/L', 'cells/uL'], ['Absolute neutrophils', 'ANC']),
  measure('Lymphocyte count', 'Blood count', ['x 10^9/L', 'cells/uL'], ['Absolute lymphocytes']),
  measure('Eosinophil count', 'Blood count', ['x 10^9/L', 'cells/uL'], ['Absolute eosinophils']),

  measure('Sodium', 'Kidney & electrolytes', ['mmol/L', 'mEq/L'], ['Na']),
  measure('Potassium', 'Kidney & electrolytes', ['mmol/L', 'mEq/L'], ['K']),
  measure('Chloride', 'Kidney & electrolytes', ['mmol/L', 'mEq/L'], ['Cl']),
  measure('Bicarbonate', 'Kidney & electrolytes', ['mmol/L', 'mEq/L'], ['HCO3']),
  measure('Blood urea nitrogen', 'Kidney & electrolytes', ['mg/dL', 'mmol/L'], ['BUN']),
  measure('Urea', 'Kidney & electrolytes', ['mmol/L', 'mg/dL']),
  measure('Creatinine', 'Kidney & electrolytes', ['mg/dL', 'umol/L'], ['Serum creatinine']),
  measure('Estimated GFR', 'Kidney & electrolytes', ['mL/min/1.73 m2'], ['eGFR', 'estimated glomerular filtration rate']),
  measure('Calcium', 'Kidney & electrolytes', ['mg/dL', 'mmol/L']),
  measure('Magnesium', 'Kidney & electrolytes', ['mg/dL', 'mmol/L']),
  measure('Phosphate', 'Kidney & electrolytes', ['mg/dL', 'mmol/L'], ['Phosphorus']),
  measure('Uric acid', 'Kidney & electrolytes', ['mg/dL', 'umol/L'], ['Urate']),

  measure('Glucose', 'Glucose & metabolism', ['mg/dL', 'mmol/L'], ['Blood glucose']),
  measure('Fasting blood glucose', 'Glucose & metabolism', ['mg/dL', 'mmol/L'], ['Fasting glucose', 'FBS']),
  measure('Random blood glucose', 'Glucose & metabolism', ['mg/dL', 'mmol/L'], ['Random glucose', 'RBS']),
  measure('Hemoglobin A1c', 'Glucose & metabolism', ['%', 'mmol/mol'], ['HbA1c', 'A1c', 'Glycated hemoglobin']),
  measure('Lactate', 'Glucose & metabolism', ['mmol/L', 'mg/dL']),
  measure('Serum osmolality', 'Glucose & metabolism', ['mOsm/kg']),

  measure('ALT', 'Liver & proteins', ['U/L'], ['Alanine aminotransferase', 'SGPT']),
  measure('AST', 'Liver & proteins', ['U/L'], ['Aspartate aminotransferase', 'SGOT']),
  measure('Alkaline phosphatase', 'Liver & proteins', ['U/L'], ['ALP']),
  measure('GGT', 'Liver & proteins', ['U/L'], ['Gamma glutamyl transferase']),
  measure('Total bilirubin', 'Liver & proteins', ['mg/dL', 'umol/L']),
  measure('Direct bilirubin', 'Liver & proteins', ['mg/dL', 'umol/L']),
  measure('Albumin', 'Liver & proteins', ['g/dL', 'g/L']),
  measure('Total protein', 'Liver & proteins', ['g/dL', 'g/L']),

  measure('Total cholesterol', 'Lipids', ['mg/dL', 'mmol/L']),
  measure('LDL cholesterol', 'Lipids', ['mg/dL', 'mmol/L'], ['LDL']),
  measure('HDL cholesterol', 'Lipids', ['mg/dL', 'mmol/L'], ['HDL']),
  measure('Triglycerides', 'Lipids', ['mg/dL', 'mmol/L'], ['TG']),

  measure('Prothrombin time', 'Coagulation', ['s'], ['PT']),
  measure('INR', 'Coagulation', [''], ['International normalized ratio']),
  measure('Activated partial thromboplastin time', 'Coagulation', ['s'], ['aPTT', 'PTT']),
  measure('Fibrinogen', 'Coagulation', ['mg/dL', 'g/L']),
  measure('D-dimer', 'Coagulation', ['ng/mL FEU', 'mg/L FEU', 'ng/mL DDU', 'mg/L DDU']),

  measure('C-reactive protein', 'Inflammation', ['mg/L', 'mg/dL'], ['CRP']),
  measure('Erythrocyte sedimentation rate', 'Inflammation', ['mm/h'], ['ESR']),
  measure('Procalcitonin', 'Inflammation', ['ng/mL', 'ug/L']),

  measure('TSH', 'Thyroid & nutrients', ['mIU/L', 'uIU/mL'], ['Thyroid stimulating hormone']),
  measure('Free T4', 'Thyroid & nutrients', ['ng/dL', 'pmol/L'], ['FT4', 'Free thyroxine']),
  measure('Free T3', 'Thyroid & nutrients', ['pg/mL', 'pmol/L'], ['FT3']),
  measure('Ferritin', 'Thyroid & nutrients', ['ng/mL', 'ug/L']),
  measure('Serum iron', 'Thyroid & nutrients', ['ug/dL', 'umol/L']),
  measure('Transferrin saturation', 'Thyroid & nutrients', ['%'], ['TSAT']),
  measure('Total iron binding capacity', 'Thyroid & nutrients', ['ug/dL', 'umol/L'], ['TIBC']),
  measure('Vitamin B12', 'Thyroid & nutrients', ['pg/mL', 'pmol/L'], ['B12']),
  measure('Folate', 'Thyroid & nutrients', ['ng/mL', 'nmol/L']),
  measure('25-hydroxy vitamin D', 'Thyroid & nutrients', ['ng/mL', 'nmol/L'], ['Vitamin D', '25 OH vitamin D']),

  measure('Arterial pH', 'Respiratory & blood gas', [''], ['Blood gas pH']),
  measure('PaO2', 'Respiratory & blood gas', ['mmHg', 'kPa'], ['Arterial oxygen partial pressure']),
  measure('PaCO2', 'Respiratory & blood gas', ['mmHg', 'kPa'], ['Arterial carbon dioxide partial pressure']),
  measure('Peak expiratory flow', 'Respiratory & blood gas', ['L/min'], ['Peak flow', 'PEF']),
  measure('FEV1', 'Respiratory & blood gas', ['L'], ['Forced expiratory volume in one second']),
  measure('FVC', 'Respiratory & blood gas', ['L'], ['Forced vital capacity']),
  measure('FEV1/FVC ratio', 'Respiratory & blood gas', ['%', 'ratio']),
  measure('End-tidal CO2', 'Respiratory & blood gas', ['mmHg', 'kPa'], ['EtCO2']),

  measure('Troponin I', 'Cardiac markers', ['ng/L', 'ng/mL']),
  measure('Troponin T', 'Cardiac markers', ['ng/L', 'ng/mL']),
  measure('BNP', 'Cardiac markers', ['pg/mL', 'ng/L'], ['B-type natriuretic peptide']),
  measure('NT-proBNP', 'Cardiac markers', ['pg/mL', 'ng/L']),
  measure('Pulse rate', 'Cardiac markers', ['beats/min'], ['Pulse']),

  measure('Urine pH', 'Urine & fluids', ['']),
  measure('Urine specific gravity', 'Urine & fluids', [''], ['Specific gravity']),
  measure('Urine albumin/creatinine ratio', 'Urine & fluids', ['mg/g', 'mg/mmol'], ['UACR', 'ACR']),
  measure('Urine output', 'Urine & fluids', ['mL/h', 'mL/24 h', 'mL']),
  measure('Fluid intake', 'Urine & fluids', ['mL', 'L']),
  measure('Fluid balance', 'Urine & fluids', ['mL', 'L']),
  measure('Urine protein', 'Urine & fluids', ['', 'mg/dL', 'g/L'], [], 'text'),
  measure('Urine ketones', 'Urine & fluids', ['', 'mmol/L'], [], 'text'),

  measure('Body mass index', 'Body measurements & scores', ['kg/m2'], ['BMI']),
  measure('Head circumference', 'Body measurements & scores', ['cm', 'in']),
  measure('Waist circumference', 'Body measurements & scores', ['cm', 'in']),
  measure('Glasgow Coma Scale', 'Body measurements & scores', ['/15'], ['GCS']),
  measure('Capillary refill time', 'Body measurements & scores', ['s']),
  measure('Wound length', 'Body measurements & scores', ['cm', 'mm']),
  measure('Wound width', 'Body measurements & scores', ['cm', 'mm']),
  measure('Wound depth', 'Body measurements & scores', ['cm', 'mm']),
];

export const measurementToken = (value: string) => value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

const definitions = new Map<string, MeasurementDefinition>();
for (const definition of MEASUREMENTS) {
  for (const name of [definition.key, definition.label, ...definition.aliases]) definitions.set(measurementToken(name), definition);
}

export function findMeasurement(name: string) { return definitions.get(measurementToken(name)); }

export type MeasurementSuggestion = {key: string; label: string; category: string; definition?: MeasurementDefinition};
export function suggestMeasurements(query: string, previousKeys: string[] = []): MeasurementSuggestion[] {
  const search = measurementToken(query);
  const options = MEASUREMENTS.map(definition => ({key: definition.key, label: definition.label, category: definition.category, definition} as MeasurementSuggestion));
  const seen = new Set(options.map(option => measurementToken(option.key)));
  for (const key of previousKeys) {
    const identity = measurementToken(findMeasurement(key)?.key || key);
    if (!seen.has(identity)) { seen.add(identity);options.push({key, label: key, category: 'Previously recorded'}); }
  }
  function rank(option: MeasurementSuggestion) {
    const names = [option.key, option.label, ...(option.definition?.aliases || [])].map(measurementToken);
    return names.some(name => name === search) ? 0 : names.some(name => name.startsWith(search)) ? 1 : 2;
  }
  return options.filter(option => !search || [option.key, option.label, ...(option.definition?.aliases || [])].some(name => measurementToken(name).includes(search)))
    .sort((a, b) => rank(a) - rank(b) || a.label.localeCompare(b.label)).slice(0, 8);
}
