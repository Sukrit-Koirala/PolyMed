import type {
  AccessGrant, AccessRequest, Admin, AuditEvent, Category, Doctor, EHRConnection, EncounterSession,
  ExchangeEvent, Hospital, InsuranceVerification, Patient, PatientHospitalIdentity, RecordEvent,
  ReviewAnnotation, SessionTask, TranslationMapping, OneTimeCode, EhrVendor,
} from "./types";
import type { SourceRecord } from "./adapters";
import { CATEGORY_SPECS, denormalize } from "./adapters/translation";
import { shortHash } from "./utils";

// All people, hospitals, payers and clinical facts below are fictional.

export const HOSPITALS: Hospital[] = [
  { id: "h-memorial", name: "Memorial Hospital", shortName: "Memorial", vendor: "Epic", city: "Springfield", npi: "1000000001" },
  { id: "h-valley", name: "Valley Medical", shortName: "Valley", vendor: "Oracle Health", city: "Riverton", npi: "1000000002" },
  { id: "h-northside", name: "Northside Clinic", shortName: "Northside", vendor: "Mock FHIR", city: "Lakeview", npi: "1000000003" },
];

export interface MockSourceSystem {
  hospitalId: string;
  mrn: string;
  records: SourceRecord[];
}

export interface SeedState {
  seededAt: number;
  seq: number;
  hospitals: Hospital[];
  connections: EHRConnection[];
  doctors: Doctor[];
  admins: Admin[];
  patients: Patient[];
  identities: PatientHospitalIdentity[];
  events: RecordEvent[];
  annotations: ReviewAnnotation[];
  sessions: EncounterSession[];
  tasks: SessionTask[];
  requests: AccessRequest[];
  codes: OneTimeCode[];
  grants: AccessGrant[];
  exchanges: ExchangeEvent[];
  mappings: TranslationMapping[];
  insurance: InsuranceVerification[];
  audit: AuditEvent[];
  sourceSystems: MockSourceSystem[];
  weeklyBaseline: Record<string, number[]>; // doctorId -> sessions for the previous 6 days
  workloadTrend: { week: string; documentation: number; administrative: number }[];
  exchangeTrend: { day: string; rate: number; total: number }[];
  feedback: { average: number; responses: number; distribution: number[] };
}

export function buildSeed(now = Date.now()): SeedState {
  const DAY = 86_400_000;
  const HOUR = 3_600_000;
  const ago = (days: number, hours = 0) => now - days * DAY - hours * HOUR;
  const isoDay = (t: number) => new Date(t).toISOString().slice(0, 10);
  let seq = 0;

  const connections: EHRConnection[] = [
    { id: "c-memorial", hospitalId: "h-memorial", adapterId: "mock-epic-fhir", label: "Epic — FHIR R4 (mock)", mode: "Mock adapter (demo)", fhirVersion: "R4", status: "connected", lastSyncAt: ago(0, 0.3) },
    { id: "c-valley", hospitalId: "h-valley", adapterId: "mock-oracle-style", label: "Oracle Health — FHIR R4 (mock)", mode: "Mock adapter (demo)", fhirVersion: "R4", status: "connected", lastSyncAt: ago(0, 1.2) },
    { id: "c-northside", hospitalId: "h-northside", adapterId: "mock-generic-fhir", label: "Generic FHIR R4 (mock)", mode: "Mock adapter (demo)", fhirVersion: "R4", status: "degraded", lastSyncAt: ago(0, 5) },
  ];

  const doctors: Doctor[] = [
    { id: "d-carter", name: "Dr. Emily Carter", title: "MD", department: "Internal Medicine", hospitalIds: ["h-memorial"], primaryHospitalId: "h-memorial", email: "e.carter@memorial.example", active: true, role: "Attending physician" },
    { id: "d-alvarez", name: "Dr. Miguel Alvarez", title: "MD", department: "Family Medicine", hospitalIds: ["h-memorial"], primaryHospitalId: "h-memorial", email: "m.alvarez@memorial.example", active: true, role: "Attending physician" },
    { id: "d-kim", name: "Dr. Hannah Kim", title: "DO", department: "Internal Medicine", hospitalIds: ["h-memorial"], primaryHospitalId: "h-memorial", email: "h.kim@memorial.example", active: true, role: "Resident" },
    { id: "d-osei", name: "Nana Osei", title: "NP", department: "Cardiology", hospitalIds: ["h-memorial"], primaryHospitalId: "h-memorial", email: "n.osei@memorial.example", active: false, role: "Nurse practitioner" },
    { id: "d-reed", name: "Dr. Daniel Reed", title: "MD", department: "Cardiology", hospitalIds: ["h-valley"], primaryHospitalId: "h-valley", email: "d.reed@valley.example", active: true, role: "Attending physician" },
    { id: "d-patel", name: "Dr. Anjali Patel", title: "MD", department: "Cardiology", hospitalIds: ["h-valley"], primaryHospitalId: "h-valley", email: "a.patel@valley.example", active: true, role: "Attending physician" },
    { id: "d-ross", name: "Dr. Owen Ross", title: "MD", department: "Obstetrics", hospitalIds: ["h-northside"], primaryHospitalId: "h-northside", email: "o.ross@northside.example", active: true, role: "Attending physician" },
  ];

  const admins: Admin[] = [{ id: "a-memorial", name: "Jordan Blake", hospitalId: "h-memorial", email: "it-admin@memorial.example" }];

  const p = (x: Partial<Patient> & Pick<Patient, "id" | "name" | "dob" | "sexRecorded">): Patient => ({
    phone: "(555) 010-0000", email: `${x.name.split(" ")[0].toLowerCase()}@mail.example`, address: "Unknown",
    emergencyContact: "Unknown", preferredLanguage: "English", reportedBloodGroup: "Unknown", discoverable: false,
    createdAt: ago(400), ...x,
  });

  const patients: Patient[] = [
    p({
      id: "EHB-20417", name: "Sarah Mitchell", dob: "1978-04-12", sexRecorded: "Female", genderIdentity: "Woman",
      phone: "(555) 014-2290", email: "sarah.mitchell@mail.example", address: "42 Alder Lane, Springfield",
      emergencyContact: "Mark Mitchell (spouse) · (555) 014-8812", reportedBloodGroup: "Unknown", discoverable: true,
      insurance: { provider: "Blue Harbor Health (fictional)", plan: "Harbor PPO Gold", memberId: "BHH-7782-0145", groupNumber: "GRP-55120", coverageStart: "2026-01-01", coverageEnd: "2026-12-31" },
      assignedDoctorId: "d-carter",
    }),
    p({ id: "EHB-11853", name: "James Okafor", dob: "1964-09-03", sexRecorded: "Male", phone: "(555) 018-4471", address: "9 Birch Rd, Springfield", assignedDoctorId: "d-carter",
      insurance: { provider: "Summit Mutual (fictional)", plan: "Summit HMO Select", memberId: "SMM-33-9921", groupNumber: "GRP-10021", coverageStart: "2026-01-01", coverageEnd: "2026-12-31" } }),
    p({ id: "EHB-30982", name: "Maria Gonzalez", dob: "1991-02-17", sexRecorded: "Female", preferredLanguage: "Spanish", discoverable: true, assignedDoctorId: "d-carter",
      insurance: { provider: "Blue Harbor Health (fictional)", plan: "Harbor EPO Silver", memberId: "BHH-1120-7765", groupNumber: "GRP-55120", coverageStart: "2026-03-01", coverageEnd: "2027-02-28" } }),
    p({ id: "EHB-45120", name: "Robert Chen", dob: "1955-11-28", sexRecorded: "Male", assignedDoctorId: "d-carter",
      insurance: { provider: "Medicare (simulated)", plan: "Part B", memberId: "1EG4-TE5-MK72", groupNumber: "—", coverageStart: "2020-12-01", coverageEnd: "2099-12-31" } }),
    p({ id: "EHB-52266", name: "Aisha Rahman", dob: "1997-06-08", sexRecorded: "Female", assignedDoctorId: "d-carter",
      insurance: { provider: "Crestline Health (fictional)", plan: "Crestline Bronze HDHP", memberId: "CRH-502-118", groupNumber: "GRP-88014", coverageStart: "2026-01-01", coverageEnd: "2026-12-31" } }),
    p({ id: "EHB-60731", name: "Thomas Wright", dob: "1972-01-19", sexRecorded: "Male", assignedDoctorId: "d-carter" }),
    p({ id: "EHB-61408", name: "Linda Nguyen", dob: "1959-08-30", sexRecorded: "Female", preferredLanguage: "Vietnamese", assignedDoctorId: "d-carter" }),
    p({ id: "EHB-70214", name: "Helen Park", dob: "1968-05-05", sexRecorded: "Female", assignedDoctorId: "d-carter" }),
    p({ id: "EHB-71990", name: "Marcus Bell", dob: "1986-12-12", sexRecorded: "Male", assignedDoctorId: "d-carter" }),
    p({ id: "EHB-80356", name: "Kevin Brooks", dob: "1981-03-22", sexRecorded: "Male", assignedDoctorId: "d-reed" }),
    p({ id: "EHB-81177", name: "Priya Shah", dob: "1974-07-14", sexRecorded: "Female", assignedDoctorId: "d-reed" }),
    p({ id: "EHB-90045", name: "Grace Lee", dob: "1993-10-01", sexRecorded: "Female", assignedDoctorId: "d-ross" }),
  ];

  const identities: PatientHospitalIdentity[] = [];
  const link = (patientId: string, hospitalId: string, mrn: string, linkedAt: number, linkMethod = "Hospital registration") =>
    identities.push({ id: `phi-${patientId}-${hospitalId}`, patientId, hospitalId, mrn, linkedAt, linkMethod });
  link("EHB-20417", "h-memorial", "MEM-102938", ago(2600));
  link("EHB-20417", "h-valley", "VM-554120", ago(165), "Patient-authorized account link");
  ["EHB-11853", "EHB-45120", "EHB-52266", "EHB-60731", "EHB-61408", "EHB-70214", "EHB-71990"].forEach((id, i) => link(id, "h-memorial", `MEM-2${String(41000 + i * 137)}`, ago(900 - i * 60)));
  link("EHB-30982", "h-memorial", "MEM-388120", ago(30));
  link("EHB-30982", "h-northside", "NS-00981", ago(420), "Patient-authorized account link");
  link("EHB-45120", "h-valley", "VM-220871", ago(60), "Hospital registration");
  link("EHB-80356", "h-valley", "VM-310045", ago(500));
  link("EHB-81177", "h-valley", "VM-318822", ago(700));
  link("EHB-90045", "h-northside", "NS-01544", ago(300));

  const vendorOf = (hid: string): EhrVendor => HOSPITALS.find((h) => h.id === hid)!.vendor;
  const originOf = (hid: string) => {
    const h = HOSPITALS.find((x) => x.id === hid)!;
    return `${h.name} · ${h.vendor} (mock adapter)`;
  };

  const events: RecordEvent[] = [];
  const versions: Record<string, number> = {};
  const add = (
    patientId: string, recordId: string, category: Category, titleText: string, data: Record<string, string>,
    hospitalId: string, author: string, recordedAt: number, opts: Partial<RecordEvent> = {},
  ) => {
    versions[recordId] = (versions[recordId] ?? 0) + 1;
    seq += 1;
    const ingestedAt = opts.ingestedAt ?? recordedAt + HOUR * 2;
    events.push({
      id: `ev-${seq}`, hash: shortHash(`${recordId}-${seq}-${ingestedAt}`), seq, patientId, recordId, version: versions[recordId],
      category, title: titleText, data, sourceHospitalId: hospitalId, author, originSystem: originOf(hospitalId),
      changeSource: "ehr-import", verification: category === "lab" || category === "bloodGroup" ? "verified-lab" : "imported",
      recordedAt, ingestedAt, fhirResourceType: CATEGORY_SPECS[category].fhirResource,
      sourcePayload: denormalize(category, vendorOf(hospitalId), data), ...opts,
    });
  };

  // ---------- Sarah Mitchell — Memorial Hospital (Epic) ----------
  const S = "EHB-20417";
  add(S, "rec-s-mem-allergy-pcn", "allergy", "Penicillin allergy", { substance: "Penicillin", reaction: "Rash", status: "Active" }, "h-memorial", "Dr. Miguel Alvarez", ago(2350));
  add(S, "rec-s-mem-allergy-pcn", "allergy", "Penicillin allergy", { substance: "Penicillin", reaction: "Rash, hives", severity: "Moderate", status: "Active" }, "h-memorial", "Dr. Miguel Alvarez", ago(1370), { note: "Reaction detail updated at annual visit" });
  add(S, "rec-s-mem-cond-htn", "condition", "Essential hypertension", { name: "Essential hypertension", status: "Active", onset: "2021-08-15" }, "h-memorial", "Dr. Miguel Alvarez", ago(1920));
  add(S, "rec-s-mem-med-lisinopril", "medication", "Lisinopril", { drug: "Lisinopril", dose: "10 mg", frequency: "Once daily", status: "Active", prescriber: "Dr. Miguel Alvarez" }, "h-memorial", "Dr. Miguel Alvarez", ago(250));
  add(S, "rec-s-mem-vitals", "vitals", "Vital signs — annual physical", { bloodPressure: "138/86 mmHg", heartRate: "78 bpm", height: "165 cm", weight: "68 kg", temperature: "36.8 °C", spo2: "98 %" }, "h-memorial", "RN Carla Diaz", ago(250));
  add(S, "rec-s-mem-lab-ldl", "lab", "LDL cholesterol", { test: "LDL cholesterol", value: "128", unit: "mg/dL", reference: "< 100", flag: "High" }, "h-memorial", "Memorial Core Lab", ago(249));
  add(S, "rec-s-mem-lab-a1c", "lab", "Hemoglobin A1c", { test: "Hemoglobin A1c", value: "5.6", unit: "%", reference: "4.0–5.6", flag: "Normal" }, "h-memorial", "Memorial Core Lab", ago(249));
  add(S, "rec-s-mem-imm-flu", "immunization", "Influenza vaccine", { vaccine: "Influenza, seasonal", date: isoDay(ago(44)), lot: "FL2611-B" }, "h-memorial", "RN Carla Diaz", ago(44));
  add(S, "rec-s-mem-imm-tdap", "immunization", "Tdap", { vaccine: "Tdap", date: "2020-05-11", lot: "TD0520-K" }, "h-memorial", "RN Carla Diaz", ago(2380));
  add(S, "rec-s-mem-enc-annual", "encounter", "Annual physical", { type: "Outpatient", reason: "Annual physical", department: "Family Medicine" }, "h-memorial", "Dr. Miguel Alvarez", ago(250));
  add(S, "rec-s-mem-fh-father", "familyHistory", "Father — myocardial infarction", { relation: "Father", condition: "Myocardial infarction at age 58" }, "h-memorial", "Dr. Miguel Alvarez", ago(1370), { verification: "patient-reported", changeSource: "patient-reported", note: "Reported by patient at visit" });
  add(S, "rec-s-mem-proc-appy", "procedure", "Appendectomy", { name: "Laparoscopic appendectomy", outcome: "Uncomplicated" }, "h-memorial", "Dr. Lena Fischer", ago(5200));

  // ---------- Sarah Mitchell — Valley Medical (Oracle Health) — previously retrieved via patient-authorized link ----------
  const valleyFirst = ago(165);
  add(S, "rec-s-val-bg", "bloodGroup", "Blood group A+", { abo: "A", rh: "Positive", method: "ABO/Rh typing" }, "h-valley", "Valley Medical Laboratory", valleyFirst, { ingestedAt: ago(164) });
  add(S, "rec-s-val-med-lisinopril", "medication", "Lisinopril", { drug: "Lisinopril", dose: "10 mg", frequency: "Once daily", status: "Active", prescriber: "Dr. Anjali Patel" }, "h-valley", "Dr. Anjali Patel", valleyFirst, { ingestedAt: ago(164) });
  add(S, "rec-s-val-allergy-pcn", "allergy", "Penicillin allergy", { substance: "Penicillin", reaction: "Rash", status: "Active" }, "h-valley", "Dr. Anjali Patel", valleyFirst, { ingestedAt: ago(164) });
  add(S, "rec-s-val-cond-htn", "condition", "Hypertension", { name: "Essential hypertension", status: "Active", onset: "2021-08" }, "h-valley", "Dr. Anjali Patel", valleyFirst, { ingestedAt: ago(164) });

  // ---------- Valley Medical's mock source system (what the adapter will return on retrieval) ----------
  const valleyVisit = ago(32);
  const src = (hospitalId: string, sourceId: string, category: Category, titleText: string, data: Record<string, string>, author: string, recordedAt: number): SourceRecord => ({
    sourceId, category, title: titleText, author, recordedAt, payload: denormalize(category, vendorOf(hospitalId), data),
  });
  const sourceSystems: MockSourceSystem[] = [
    {
      hospitalId: "h-valley", mrn: "VM-554120",
      records: [
        src("h-valley", "rec-s-val-bg", "bloodGroup", "Blood group A+", { abo: "A", rh: "Positive", method: "ABO/Rh typing" }, "Valley Medical Laboratory", valleyFirst),
        src("h-valley", "rec-s-val-allergy-pcn", "allergy", "Penicillin allergy", { substance: "Penicillin", reaction: "Rash", status: "Active" }, "Dr. Anjali Patel", valleyFirst),
        src("h-valley", "rec-s-val-cond-htn", "condition", "Hypertension", { name: "Essential hypertension", status: "Active", onset: "2021-08" }, "Dr. Anjali Patel", valleyFirst),
        src("h-valley", "rec-s-val-med-lisinopril", "medication", "Lisinopril", { drug: "Lisinopril", dose: "20 mg", frequency: "Once daily", status: "Active", prescriber: "Dr. Anjali Patel" }, "Dr. Anjali Patel", valleyVisit),
        src("h-valley", "rec-s-val-enc-cardio", "encounter", "Cardiology consultation", { type: "Outpatient", reason: "Exertional chest tightness", department: "Cardiology" }, "Dr. Anjali Patel", valleyVisit),
        src("h-valley", "rec-s-val-img-stress", "imaging", "Exercise stress test", { study: "Exercise treadmill stress test", conclusion: "No inducible ischemia at 10.1 METs. Hypertensive blood pressure response.", performer: "Dr. Anjali Patel" }, "Dr. Anjali Patel", valleyVisit),
        src("h-valley", "rec-s-val-img-echo", "imaging", "Transthoracic echocardiogram", { study: "Transthoracic echocardiogram", conclusion: "LVEF 60%. Mild concentric LVH. No significant valvular disease.", performer: "Dr. Daniel Reed" }, "Dr. Daniel Reed", valleyVisit),
        src("h-valley", "rec-s-val-lab-trop", "lab", "Troponin I", { test: "Troponin I (high sensitivity)", value: "< 3", unit: "ng/L", reference: "< 14", flag: "Normal" }, "Valley Medical Laboratory", valleyVisit),
        src("h-valley", "rec-s-val-lab-k", "lab", "Potassium", { test: "Potassium", value: "4.2", unit: "mmol/L", reference: "3.5–5.1", flag: "Normal" }, "Valley Medical Laboratory", valleyVisit),
        src("h-valley", "rec-s-val-vitals", "vitals", "Vital signs — cardiology visit", { bloodPressure: "146/92 mmHg", heartRate: "82 bpm", height: "165 cm", weight: "69.5 kg", spo2: "98 %" }, "RN Tom Becker", valleyVisit),
      ],
    },
    {
      hospitalId: "h-northside", mrn: "NS-00981",
      records: [
        src("h-northside", "rec-m-ns-preg", "condition", "Pregnancy, first trimester", { name: "Supervision of normal pregnancy", status: "Active", onset: isoDay(ago(70)) }, "Dr. Owen Ross", ago(40)),
        src("h-northside", "rec-m-ns-lab-hb", "lab", "Hemoglobin", { test: "Hemoglobin", value: "11.4", unit: "g/dL", reference: "12.0–15.5", flag: "Low" }, "Northside Lab", ago(40)),
      ],
    },
  ];

  // ---------- Other patients (brief, Memorial unless noted) ----------
  const brief: [string, Category, string, Record<string, string>, string, string, number][] = [
    ["EHB-11853", "condition", "Type 2 diabetes mellitus", { name: "Type 2 diabetes mellitus", status: "Active", onset: "2017-03" }, "h-memorial", "Dr. Emily Carter", 1600],
    ["EHB-11853", "medication", "Metformin", { drug: "Metformin", dose: "1000 mg", frequency: "Twice daily", status: "Active", prescriber: "Dr. Emily Carter" }, "h-memorial", "Dr. Emily Carter", 120],
    ["EHB-11853", "lab", "Hemoglobin A1c", { test: "Hemoglobin A1c", value: "7.4", unit: "%", reference: "4.0–5.6", flag: "High" }, "h-memorial", "Memorial Core Lab", 5],
    ["EHB-11853", "allergy", "Sulfonamide allergy", { substance: "Sulfonamides", reaction: "Hives", status: "Active" }, "h-memorial", "Dr. Emily Carter", 1500],
    ["EHB-30982", "allergy", "No known drug allergies", { substance: "No known drug allergies", status: "Active" }, "h-memorial", "Dr. Hannah Kim", 30],
    ["EHB-45120", "condition", "Heart failure with reduced EF", { name: "Heart failure with reduced ejection fraction", status: "Active", onset: "2023-06" }, "h-memorial", "Dr. Emily Carter", 900],
    ["EHB-45120", "medication", "Furosemide", { drug: "Furosemide", dose: "40 mg", frequency: "Once daily", status: "Active", prescriber: "Dr. Emily Carter" }, "h-memorial", "Dr. Emily Carter", 90],
    ["EHB-45120", "medication", "Furosemide", { drug: "Furosemide", dose: "20 mg", frequency: "Once daily", status: "Active", prescriber: "Hospitalist team" }, "h-valley", "Valley Hospitalist Team", 12],
    ["EHB-45120", "encounter", "Inpatient admission", { type: "Inpatient", reason: "Acute decompensated heart failure", department: "Hospital Medicine" }, "h-valley", "Valley Hospitalist Team", 14],
    ["EHB-52266", "condition", "Migraine without aura", { name: "Migraine without aura", status: "Active", onset: "2019" }, "h-memorial", "Dr. Hannah Kim", 400],
    ["EHB-52266", "medication", "Sumatriptan", { drug: "Sumatriptan", dose: "50 mg", frequency: "As needed", status: "Active", prescriber: "Dr. Hannah Kim" }, "h-memorial", "Dr. Hannah Kim", 400],
    ["EHB-60731", "vitals", "Vital signs", { bloodPressure: "124/80 mmHg", heartRate: "70 bpm", weight: "84 kg", height: "180 cm" }, "h-memorial", "RN Carla Diaz", 0.2],
    ["EHB-60731", "lab", "Lipid panel — LDL", { test: "LDL cholesterol", value: "96", unit: "mg/dL", reference: "< 100", flag: "Normal" }, "h-memorial", "Memorial Core Lab", 0.15],
    ["EHB-61408", "condition", "COPD", { name: "Chronic obstructive pulmonary disease", status: "Active", onset: "2015" }, "h-memorial", "Dr. Miguel Alvarez", 2000],
    ["EHB-61408", "medication", "Tiotropium inhaler", { drug: "Tiotropium", dose: "18 mcg", frequency: "Once daily", status: "Active", prescriber: "Dr. Miguel Alvarez" }, "h-memorial", "Dr. Miguel Alvarez", 300],
    ["EHB-70214", "condition", "Hypertension", { name: "Essential hypertension", status: "Active", onset: "2018" }, "h-memorial", "Dr. Emily Carter", 1100],
    ["EHB-71990", "encounter", "Sports medicine visit", { type: "Outpatient", reason: "Right knee pain", department: "Orthopedics" }, "h-memorial", "Dr. Hannah Kim", 200],
    ["EHB-80356", "condition", "Atrial fibrillation", { name: "Paroxysmal atrial fibrillation", status: "Active", onset: "2024-02" }, "h-valley", "Dr. Daniel Reed", 600],
    ["EHB-80356", "medication", "Apixaban", { drug: "Apixaban", dose: "5 mg", frequency: "Twice daily", status: "Active", prescriber: "Dr. Daniel Reed" }, "h-valley", "Dr. Daniel Reed", 100],
    ["EHB-81177", "condition", "Hyperlipidemia", { name: "Hyperlipidemia", status: "Active", onset: "2020" }, "h-valley", "Dr. Daniel Reed", 800],
    ["EHB-90045", "condition", "Asthma", { name: "Mild intermittent asthma", status: "Active", onset: "2005" }, "h-northside", "Dr. Owen Ross", 900],
  ];
  brief.forEach(([pid, cat, t, data, hid, author, days], i) => add(pid, `rec-${pid}-${i}`, cat, t, data, hid, author, ago(days)));

  // ---------- Translation mappings (destination import capabilities) ----------
  const allCats = Object.keys(CATEGORY_SPECS) as Category[];
  const mappings: TranslationMapping[] = [];
  const unsupported: Record<string, Partial<Record<Category, string[] | "all">>> = {
    "h-memorial": { bloodGroup: "all", vitals: ["spo2"] },
    "h-valley": { familyHistory: "all", immunization: ["lot"] },
    "h-northside": { imaging: "all", document: "all", allergy: ["severity"], medication: ["prescriber"] },
  };
  for (const h of HOSPITALS) for (const c of allCats) {
    const u = unsupported[h.id][c];
    mappings.push({ id: `map-${h.id}-${c}`, hospitalId: h.id, category: c, supported: u !== "all", unsupportedFields: Array.isArray(u) ? u : [] });
  }

  // ---------- Sessions & tasks ----------
  const sessions: EncounterSession[] = [];
  const tasks: SessionTask[] = [];
  const mk = (id: string, patientId: string, doctorId: string, hospitalId: string, reason: string, status: EncounterSession["status"], createdAt: number, extra: Partial<EncounterSession> = {}) =>
    sessions.push({ id, patientId, doctorId, hospitalId, reason, status, createdAt, updatedAt: extra.updatedAt ?? createdAt, vitals: {}, reported: [], questions: [], answers: [], notes: "", ...extra });
  const tk = (id: string, sessionId: string | undefined, patientId: string, doctorId: string, type: SessionTask["type"], titleText: string, status: SessionTask["status"], createdAt: number, completedAt?: number) =>
    tasks.push({ id, sessionId, patientId, doctorId, type, title: titleText, status, createdAt, completedAt });

  mk("s-okafor", "EHB-11853", "d-carter", "h-memorial", "Diabetes follow-up — A1c review", "active", ago(0, 2.5), { vitals: { bloodPressure: "132/84 mmHg", heartRate: "76 bpm", weight: "92 kg" }, notes: "A1c trending up. Discuss adherence and GLP-1 options." });
  tk("t-okafor-doc", "s-okafor", "EHB-11853", "d-carter", "documentation", "Complete visit note for diabetes follow-up", "pending", ago(0, 2.4));
  tk("t-okafor-fu", "s-okafor", "EHB-11853", "d-carter", "follow-up", "Order repeat A1c in 3 months", "pending", ago(0, 2.4));

  mk("s-gonzalez", "EHB-30982", "d-carter", "h-memorial", "New patient intake — prenatal history", "active", ago(0, 1.6), { accessRequestId: "ar-gonzalez" });
  tk("t-gonzalez-appr", "s-gonzalez", "EHB-30982", "d-carter", "patient-approval", "Awaiting patient approval for Northside Clinic records", "pending", ago(0, 1.6));
  tk("t-gonzalez-missing", "s-gonzalez", "EHB-30982", "d-carter", "missing-info", "Collect emergency contact and address", "pending", ago(0, 1.6));

  mk("s-chen", "EHB-45120", "d-carter", "h-memorial", "Post-discharge follow-up (Valley Medical admission)", "active", ago(0, 4));
  tk("t-chen-review", "s-chen", "EHB-45120", "d-carter", "record-review", "Reconcile furosemide dose (40 mg vs 20 mg)", "pending", ago(0, 3.9));
  tk("t-chen-doc", "s-chen", "EHB-45120", "d-carter", "documentation", "Transitional care documentation", "in-progress", ago(0, 3.9));

  mk("s-rahman", "EHB-52266", "d-carter", "h-memorial", "Migraine evaluation — imaging consideration", "active", ago(0, 3));
  tk("t-rahman-ins", "s-rahman", "EHB-52266", "d-carter", "insurance", "Check MRI prior authorization requirement", "pending", ago(0, 2.9));

  mk("s-wright", "EHB-60731", "d-carter", "h-memorial", "Annual physical", "completed", ago(0, 6), { completedAt: ago(0, 5), updatedAt: ago(0, 5) });
  tk("t-wright-doc", "s-wright", "EHB-60731", "d-carter", "documentation", "Annual physical note", "done", ago(0, 6), ago(0, 5.1));
  tk("t-wright-ins", "s-wright", "EHB-60731", "d-carter", "insurance", "Confirm preventive visit coverage", "done", ago(0, 6), ago(0, 5.5));

  mk("s-nguyen", "EHB-61408", "d-carter", "h-memorial", "COPD maintenance check", "completed", ago(0, 5), { completedAt: ago(0, 3.6), updatedAt: ago(0, 3.6) });
  tk("t-nguyen-doc", "s-nguyen", "EHB-61408", "d-carter", "documentation", "COPD visit note", "done", ago(0, 5), ago(0, 3.7));
  tk("t-nguyen-fu", "s-nguyen", "EHB-61408", "d-carter", "follow-up", "Send spirometry referral", "done", ago(0, 5), ago(0, 3.6));
  tk("t-nguyen-interp", "s-nguyen", "EHB-61408", "d-carter", "missing-info", "Confirm interpreter preference (Vietnamese)", "done", ago(0, 5), ago(0, 4.8));

  mk("s-park", "EHB-70214", "d-carter", "h-memorial", "Hypertension follow-up", "scheduled", ago(1), { scheduledFor: now + DAY + 2 * HOUR });
  tk("t-park-prep", "s-park", "EHB-70214", "d-carter", "record-review", "Review home BP log before visit", "pending", ago(1));

  mk("s-bell", "EHB-71990", "d-carter", "h-memorial", "Knee pain intake", "draft", ago(1, 3), { reported: [{ id: "ri-bell-1", label: "Symptom", value: "Right knee pain after running", source: "patient-reported", status: "accepted", at: ago(1, 3) }] });
  tk("t-bell-doc", "s-bell", "EHB-71990", "d-carter", "documentation", "Finish intake draft for knee pain", "pending", ago(1, 3));

  // Earlier completed tasks this week (for charts)
  for (let i = 0; i < 9; i++) tk(`t-hist-${i}`, undefined, "EHB-11853", "d-carter", (["documentation", "insurance", "record-review"] as const)[i % 3], "Archived task", "done", ago(2 + (i % 5), 3), ago(2 + (i % 5), 1));

  // Dr. Reed (Valley)
  mk("s-brooks", "EHB-80356", "d-reed", "h-valley", "Atrial fibrillation — anticoagulation review", "active", ago(0, 1));
  tk("t-brooks-doc", "s-brooks", "EHB-80356", "d-reed", "documentation", "Anticoagulation visit note", "pending", ago(0, 1));
  mk("s-shah", "EHB-81177", "d-reed", "h-valley", "Lipid management", "completed", ago(0, 4), { completedAt: ago(0, 3) });
  tk("t-shah-doc", "s-shah", "EHB-81177", "d-reed", "documentation", "Lipid visit note", "done", ago(0, 4), ago(0, 3));
  mk("s-mitchell-valley", "EHB-20417", "d-patel", "h-valley", "Cardiology consultation — exertional chest tightness", "completed", valleyVisit, { completedAt: valleyVisit + 2 * HOUR });

  // ---------- Access requests / grants ----------
  const requests: AccessRequest[] = [
    {
      id: "ar-gonzalez", patientId: "EHB-30982", doctorId: "d-carter", hospitalId: "h-memorial", department: "Internal Medicine",
      purpose: "Continuity of care for new patient", encounterReason: "New patient intake with prenatal history",
      categories: ["condition", "lab", "medication", "allergy"], sourceHospitalIds: ["h-northside"], durationHours: 72,
      status: "pending", createdAt: ago(0, 1.6), sessionId: "s-gonzalez",
    },
    {
      id: "ar-patel-sarah", patientId: S, doctorId: "d-patel", hospitalId: "h-valley", department: "Cardiology",
      purpose: "Cardiology consultation", encounterReason: "Exertional chest tightness — review prior medications and labs",
      categories: ["medication", "allergy", "lab", "condition"], sourceHospitalIds: ["h-memorial"], durationHours: 72,
      status: "expired", createdAt: valleyVisit - DAY, respondedAt: valleyVisit - DAY + 600_000,
    },
    {
      id: "ar-chen", patientId: "EHB-45120", doctorId: "d-carter", hospitalId: "h-memorial", department: "Internal Medicine",
      purpose: "Post-discharge follow-up", encounterReason: "Transitional care after Valley Medical admission",
      categories: ["encounter", "medication"], sourceHospitalIds: ["h-valley"], durationHours: 168,
      status: "active", createdAt: ago(1, 2), respondedAt: ago(1, 1.8), sessionId: "s-chen",
    },
  ];
  const grants: AccessGrant[] = [
    { id: "g-patel-sarah", requestId: "ar-patel-sarah", patientId: S, doctorId: "d-patel", hospitalId: "h-valley", categories: ["medication", "allergy", "lab", "condition"], sourceHospitalIds: ["h-memorial"], grantedAt: valleyVisit - DAY + 900_000, expiresAt: valleyVisit + 2 * DAY },
    { id: "g-chen", requestId: "ar-chen", patientId: "EHB-45120", doctorId: "d-carter", hospitalId: "h-memorial", categories: ["encounter", "medication"], sourceHospitalIds: ["h-valley"], grantedAt: ago(1, 1.7), expiresAt: ago(1, 1.7) + 168 * HOUR },
  ];

  // ---------- Exchanges ----------
  const exchanges: ExchangeEvent[] = [];
  let ex = 0;
  const xe = (e: Omit<ExchangeEvent, "id">) => exchanges.push({ id: `ex-${++ex}`, ...e });
  xe({ patientId: S, sourceHospitalId: "h-valley", destinationHospitalId: "h-memorial", initiatedBy: S, initiatedByName: "Sarah Mitchell (patient link)", requestedAt: ago(164), categories: ["bloodGroup", "medication", "allergy", "condition"], recordCount: 4, translation: "partial", delivery: "stored-no-writeback", preservedFields: ["Blood group → ABO group", "Blood group → Rh factor", "Blood group → Method"] });
  xe({ patientId: S, sourceHospitalId: "h-memorial", destinationHospitalId: "h-valley", initiatedBy: "d-patel", initiatedByName: "Dr. Anjali Patel", requestedAt: valleyVisit - DAY + 950_000, categories: ["medication", "allergy", "lab", "condition"], recordCount: 6, translation: "success", delivery: "delivered-accepted", preservedFields: [] });
  xe({ patientId: "EHB-45120", sourceHospitalId: "h-valley", destinationHospitalId: "h-memorial", initiatedBy: "system", initiatedByName: "Discharge notification (system)", requestedAt: ago(12), categories: ["encounter", "medication"], recordCount: 2, translation: "success", delivery: "stored-no-writeback", preservedFields: [] });
  xe({ patientId: "EHB-30982", sourceHospitalId: "h-northside", destinationHospitalId: "h-memorial", initiatedBy: "system", initiatedByName: "Scheduled sync (system)", requestedAt: ago(1, 4), categories: ["document"], recordCount: 0, translation: "failed", delivery: "not-attempted", preservedFields: [], error: "Source adapter timeout after 30s (simulated)" });
  xe({ patientId: "EHB-11853", sourceHospitalId: "h-memorial", destinationHospitalId: "h-northside", initiatedBy: "d-alvarez", initiatedByName: "Dr. Miguel Alvarez", requestedAt: ago(3, 2), categories: ["allergy"], recordCount: 1, translation: "partial", delivery: "rejected", preservedFields: ["Allergy → Severity"], error: "Destination rejected payload: unknown coding system (simulated)" });
  for (let i = 0; i < 10; i++) {
    xe({ patientId: ["EHB-11853", "EHB-61408", "EHB-60731", "EHB-52266"][i % 4], sourceHospitalId: "h-memorial", destinationHospitalId: i % 3 === 0 ? "h-northside" : "h-valley", initiatedBy: "system", initiatedByName: "Referral packet (system)", requestedAt: ago(2 + i, i % 5), categories: [(["medication", "lab", "condition", "immunization"] as Category[])[i % 4]], recordCount: 1 + (i % 4), translation: "success", delivery: i % 4 === 1 ? "delivered-pending" : "delivered-accepted", preservedFields: i % 4 === 3 ? ["Immunization → Lot number"] : [] });
  }

  // ---------- Insurance ----------
  const insurance: InsuranceVerification[] = [];

  // ---------- Audit ----------
  const audit: AuditEvent[] = [];
  let au = 0;
  const ae = (e: Omit<AuditEvent, "id">) => audit.push({ id: `au-${++au}`, ...e });
  ae({ at: valleyVisit - DAY, actorId: "d-patel", actorName: "Dr. Anjali Patel", actorRole: "doctor", hospitalId: "h-valley", patientId: S, action: "access.request.created", detail: "Requested Medications, Allergies, Lab results, Diagnoses from Memorial Hospital (72h)" });
  ae({ at: valleyVisit - DAY + 600_000, actorId: S, actorName: "Sarah Mitchell", actorRole: "patient", patientId: S, action: "access.request.approved", detail: "One-time code issued (expires in 10 min)" });
  ae({ at: valleyVisit - DAY + 900_000, actorId: "d-patel", actorName: "Dr. Anjali Patel", actorRole: "doctor", hospitalId: "h-valley", patientId: S, action: "access.grant.activated", detail: "Code verified; scope: Medications, Allergies, Lab results, Diagnoses" });
  ae({ at: valleyVisit, actorId: "d-patel", actorName: "Dr. Anjali Patel", actorRole: "doctor", hospitalId: "h-valley", patientId: S, action: "records.viewed", detail: "Viewed Medications, Allergies (source: Memorial Hospital)" });
  ae({ at: ago(0, 1.6), actorId: "d-carter", actorName: "Dr. Emily Carter", actorRole: "doctor", hospitalId: "h-memorial", patientId: "EHB-30982", action: "access.request.created", detail: "Requested Diagnoses, Lab results, Medications, Allergies from Northside Clinic (72h)" });
  ae({ at: ago(1, 4), actorId: "system", actorName: "Exchange service", actorRole: "system", hospitalId: "h-memorial", action: "exchange.failed", detail: "Northside Clinic → Memorial Hospital document sync timed out" });
  ae({ at: ago(2), actorId: "a-memorial", actorName: "Jordan Blake", actorRole: "admin", hospitalId: "h-memorial", action: "user.deactivated", detail: "Deactivated account for Nana Osei, NP" });
  ae({ at: ago(0, 6), actorId: "d-carter", actorName: "Dr. Emily Carter", actorRole: "doctor", hospitalId: "h-memorial", action: "auth.login", detail: "Signed in (demo authentication)" });

  const annotations: ReviewAnnotation[] = [];

  const dayLabel = (t: number) => new Date(t).toLocaleDateString("en-US", { weekday: "short" });
  const weeklyBaseline = { "d-carter": [11, 14, 9, 13, 12, 6], "d-reed": [8, 10, 7, 9, 11, 4] };
  void dayLabel;
  const workloadTrend = [
    { week: "W-7", documentation: 14.5, administrative: 9.0 },
    { week: "W-6", documentation: 15.2, administrative: 9.4 },
    { week: "W-5", documentation: 14.8, administrative: 8.7 },
    { week: "W-4", documentation: 13.1, administrative: 7.9 },
    { week: "W-3", documentation: 12.4, administrative: 7.1 },
    { week: "W-2", documentation: 11.0, administrative: 6.2 },
    { week: "W-1", documentation: 10.2, administrative: 5.8 },
    { week: "This wk", documentation: 9.6, administrative: 5.1 },
  ];
  const exchangeTrend = Array.from({ length: 14 }, (_, i) => {
    const rates = [88, 90, 86, 91, 93, 89, 92, 94, 90, 95, 93, 96, 94, 95];
    const totals = [42, 38, 51, 47, 33, 29, 45, 52, 48, 44, 39, 31, 46, 22];
    const t = ago(13 - i);
    return { day: new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric" }), rate: rates[i], total: totals[i] };
  });

  return {
    seededAt: now, seq, hospitals: HOSPITALS, connections, doctors, admins, patients, identities, events, annotations,
    sessions, tasks, requests, codes: [], grants, exchanges, mappings, insurance, audit, sourceSystems,
    weeklyBaseline, workloadTrend, exchangeTrend, feedback: { average: 4.7, responses: 38, distribution: [0, 1, 2, 6, 29] },
  };
}

export const SAMPLE_TRANSCRIPT =
  "I have been experiencing chest discomfort for three days. I visited Valley Medical last month and had a heart test. I currently take lisinopril.";

export const DEFAULT_QUESTIONS = [
  { id: "q-before", text: "Have you experienced these symptoms before?", type: "yesno" as const },
  { id: "q-newmeds", text: "Have you started any new medications?", type: "yesno" as const },
  { id: "q-family", text: "Do you have a family history of heart disease?", type: "yesno" as const },
  { id: "q-otherhosp", text: "Have you recently visited another hospital?", type: "yesno" as const },
];
