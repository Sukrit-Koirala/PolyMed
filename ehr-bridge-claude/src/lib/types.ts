// EHR Bridge domain model. Mirrors HL7 FHIR concepts where appropriate
// (Patient, Observation, Condition, MedicationRequest, AllergyIntolerance,
// Encounter, Immunization, Provenance, AuditEvent) without claiming to be a
// conformant FHIR implementation.

export type Role = "doctor" | "patient" | "admin";

export type EhrVendor = "Epic" | "Oracle Health" | "Mock FHIR";

export interface Hospital {
  id: string;
  name: string;
  shortName: string;
  vendor: EhrVendor;
  city: string;
  npi: string;
}

export interface EHRConnection {
  id: string;
  hospitalId: string;
  adapterId: AdapterId;
  label: string;
  /** Every connection in this prototype is a mock adapter. */
  mode: "Mock adapter (demo)";
  fhirVersion: "R4";
  status: "connected" | "degraded" | "paused";
  lastSyncAt: number;
  lastTestAt?: number;
  lastTestResult?: string;
}

export type AdapterId = "mock-epic-fhir" | "mock-oracle-style" | "mock-generic-fhir";

export interface Doctor {
  id: string;
  name: string;
  title: string;
  department: string;
  hospitalIds: string[];
  primaryHospitalId: string;
  email: string;
  active: boolean;
  role: "Attending physician" | "Resident" | "Nurse practitioner";
}

export interface Admin {
  id: string;
  name: string;
  hospitalId: string;
  email: string;
}

export interface InsuranceInfo {
  provider: string;
  plan: string;
  memberId: string;
  groupNumber: string;
  coverageStart: string;
  coverageEnd: string;
}

export interface Patient {
  id: string; // EHR Bridge patient ID, independent of hospital MRNs
  name: string;
  dob: string; // ISO date
  sexRecorded: "Female" | "Male" | "Intersex" | "Unknown";
  genderIdentity?: string;
  phone: string;
  email: string;
  address: string;
  emergencyContact: string;
  preferredLanguage: string;
  reportedBloodGroup: string; // patient-reported, "Unknown" if not known
  insurance?: InsuranceInfo;
  /** Patient has allowed treating clinicians to see *that* linked records exist (not their content). */
  discoverable: boolean;
  createdAt: number;
  assignedDoctorId?: string;
}

export interface PatientHospitalIdentity {
  id: string;
  patientId: string;
  hospitalId: string;
  mrn: string;
  linkedAt: number;
  linkMethod: string;
}

export type Category =
  | "condition"
  | "medication"
  | "allergy"
  | "vitals"
  | "bloodGroup"
  | "lab"
  | "imaging"
  | "immunization"
  | "encounter"
  | "procedure"
  | "familyHistory"
  | "document";

export type ChangeSource =
  | "ehr-import"
  | "doctor-entered"
  | "patient-reported"
  | "ai-extracted"
  | "lab-verified";

/** How trustworthy / what kind of fact this is. Drives the visible provenance chip. */
export type Verification =
  | "verified-lab"
  | "imported"
  | "patient-reported"
  | "doctor-entered"
  | "ai-draft";

/**
 * Append-only record event. The current state of a record is materialized
 * from the latest event for its recordId. Earlier events are never mutated.
 */
export interface RecordEvent {
  id: string;
  hash: string; // short commit-like id
  seq: number; // global sequence number per store
  patientId: string;
  recordId: string;
  version: number; // per-record version
  category: Category;
  title: string;
  data: Record<string, string>;
  sourceHospitalId?: string;
  author: string;
  originSystem: string;
  changeSource: ChangeSource;
  verification: Verification;
  recordedAt: number; // clinical/recorded time at source
  ingestedAt: number; // time EHR Bridge received it
  fhirResourceType: string;
  note?: string;
  exchangeEventId?: string;
  /** Raw source payload as received from the (mock) adapter, kept for "original source view". */
  sourcePayload?: Record<string, unknown>;
  retracted?: boolean; // a later event can mark a record entered-in-error; never deletes
}

export interface ReviewAnnotation {
  id: string;
  targetType: "event" | "discrepancy";
  targetId: string;
  patientId: string;
  type: "reviewed" | "flagged";
  by: string;
  byName: string;
  at: number;
  note?: string;
}

export interface MaterializedRecord {
  recordId: string;
  patientId: string;
  category: Category;
  title: string;
  data: Record<string, string>;
  sourceHospitalId?: string;
  author: string;
  originSystem: string;
  changeSource: ChangeSource;
  verification: Verification;
  recordedAt: number;
  version: number;
  latestEventId: string;
  events: RecordEvent[];
  fhirResourceType: string;
}

export interface Discrepancy {
  id: string;
  patientId: string;
  category: Category;
  title: string;
  field: string;
  values: { recordId: string; value: string; sourceHospitalId?: string; recordedAt: number; author: string }[];
}

export type SessionStatus = "draft" | "active" | "scheduled" | "completed";

export type ItemSource = "patient-reported" | "ai-extracted" | "doctor-entered";

export interface ReportedItem {
  id: string;
  label: string;
  value: string;
  source: ItemSource;
  status: "draft" | "accepted" | "rejected";
  confirmedBy?: string;
  at: number;
}

export interface ExtractedField {
  id: string;
  label: string;
  value: string;
  status: "draft" | "accepted" | "rejected";
}

export interface VoiceMemo {
  id: string;
  transcript: string;
  transcriptSource: "browser-speech" | "sample" | "manual";
  durationSec: number;
  recordedAt: number;
  hadAudio: boolean;
  extracted: ExtractedField[];
}

export type QuestionType = "text" | "yesno" | "choice" | "number";

export interface IntakeQuestion {
  id: string;
  text: string;
  type: QuestionType;
  options?: string[];
}

export interface IntakeAnswer {
  questionId: string;
  value: string;
  addedToReported: boolean;
}

export interface EncounterSession {
  id: string;
  patientId: string;
  doctorId: string;
  hospitalId: string;
  reason: string;
  status: SessionStatus;
  scheduledFor?: number;
  createdAt: number;
  updatedAt: number;
  completedAt?: number;
  accessRequestId?: string;
  vitals: Record<string, string>;
  reported: ReportedItem[];
  voiceMemo?: VoiceMemo;
  questions: IntakeQuestion[];
  answers: IntakeAnswer[];
  notes: string;
  insuranceVerificationId?: string;
}

export type TaskType =
  | "documentation"
  | "record-review"
  | "missing-info"
  | "patient-approval"
  | "insurance"
  | "follow-up";

export interface SessionTask {
  id: string;
  sessionId?: string;
  patientId: string;
  doctorId: string;
  type: TaskType;
  title: string;
  status: "pending" | "in-progress" | "done";
  createdAt: number;
  completedAt?: number;
  dueAt?: number;
}

export type AccessRequestStatus =
  | "pending"
  | "investigating"
  | "approved" // code issued, not yet redeemed
  | "active" // code redeemed, grant active
  | "denied"
  | "expired"
  | "revoked";

export interface AccessRequest {
  id: string;
  patientId: string;
  doctorId: string;
  hospitalId: string;
  department: string;
  purpose: string;
  encounterReason: string;
  categories: Category[];
  sourceHospitalIds: string[];
  durationHours: number;
  status: AccessRequestStatus;
  createdAt: number;
  respondedAt?: number;
  patientQuestion?: string;
  reported?: boolean;
  doctorReply?: string;
  sessionId?: string;
}

export interface OneTimeCode {
  id: string;
  requestId: string;
  /** Demo only: stored in clear so the patient view can display it. Production would store a salted hash. */
  code: string;
  issuedAt: number;
  expiresAt: number;
  used: boolean;
  attempts: number;
  maxAttempts: number;
}

export interface AccessGrant {
  id: string;
  requestId: string;
  patientId: string;
  doctorId: string;
  hospitalId: string;
  categories: Category[];
  sourceHospitalIds: string[];
  grantedAt: number;
  expiresAt: number;
  revokedAt?: number;
}

export type FieldMapStatus = "mapped" | "transformed" | "missing" | "preserved" | "failed";

export interface ExchangeEvent {
  id: string;
  patientId: string;
  sourceHospitalId: string;
  destinationHospitalId: string;
  initiatedBy: string;
  initiatedByName: string;
  requestedAt: number;
  categories: Category[];
  recordCount: number;
  translation: "success" | "partial" | "failed";
  delivery: "stored-no-writeback" | "delivered-accepted" | "delivered-pending" | "rejected" | "not-attempted";
  preservedFields: string[];
  relatedSeq?: number;
  error?: string;
  retriedFrom?: string;
}

export interface TranslationMapping {
  id: string;
  hospitalId: string; // destination hospital whose import mapping this is
  category: Category;
  supported: boolean;
  unsupportedFields: string[];
}

export interface ServiceBenefit {
  service: string;
  eligible: boolean | "unknown";
  inNetwork: boolean | "unknown";
  copay?: string;
  deductible?: string;
  priorAuth: "required" | "not-required" | "unknown";
}

export interface InsuranceVerification {
  id: string;
  patientId: string;
  sessionId?: string;
  info: InsuranceInfo;
  status: "eligible" | "inactive" | "not-found";
  checkedAt: number;
  source: string;
  services: ServiceBenefit[];
}

export interface AuditEvent {
  id: string;
  at: number;
  actorId: string;
  actorName: string;
  actorRole: Role | "system";
  hospitalId?: string;
  patientId?: string;
  action: string;
  detail: string;
}

export interface DemoUser {
  id: string;
  role: Role;
  name: string;
  hospitalId?: string;
}
