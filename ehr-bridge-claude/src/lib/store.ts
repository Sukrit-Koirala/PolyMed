"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { buildSeed, type SeedState } from "./seed";
import type {
  AccessRequest, AuditEvent, Category, DemoUser, Doctor, EncounterSession, InsuranceInfo, InsuranceVerification,
  OneTimeCode, Patient, RecordEvent, ReviewAnnotation, SessionTask, TaskType, ChangeSource, Verification,
} from "./types";
import { shortHash, uid } from "./utils";
import { ADAPTERS } from "./adapters";
import { CATEGORY_LABELS, CATEGORY_SPECS, denormalize, preservedFieldsFor } from "./adapters/translation";
import { generateCode, grantFromRequest, OTP_MAX_ATTEMPTS, OTP_TTL_MS, verifyOtp, type OtpCheck } from "./services/otp";
import { checkEligibility } from "./services/insurance";
import { filterRecords } from "./services/permissions";
import { findDiscrepancies, materialize } from "./services/records";

export interface ImportSummary {
  hospitalId: string;
  retrieved: number;
  newVersions: number;
  unchanged: number;
  preserved: string[];
  failed?: string;
}

export interface NewSessionInput {
  patientId: string;
  doctorId: string;
  reason: string;
  status: EncounterSession["status"];
  accessRequestId?: string;
  vitals: Record<string, string>;
  reported: EncounterSession["reported"];
  voiceMemo?: EncounterSession["voiceMemo"];
  questions: EncounterSession["questions"];
  answers: EncounterSession["answers"];
  notes: string;
  insuranceVerificationId?: string;
  existingSessionId?: string;
}

interface Actions {
  resetDemo: () => void;
  audit: (e: Omit<AuditEvent, "id" | "at">) => void;
  registerPatient: (input: Omit<Patient, "id" | "createdAt" | "discoverable">, doctorId: string) => Patient;
  updatePatient: (id: string, patch: Partial<Patient>, actor: DemoUser) => void;
  createAccessRequest: (input: Omit<AccessRequest, "id" | "status" | "createdAt">) => AccessRequest;
  approveRequest: (requestId: string) => OneTimeCode | undefined;
  denyRequest: (requestId: string) => void;
  investigateRequest: (requestId: string, question: string, report: boolean) => void;
  replyToPatient: (requestId: string, reply: string) => void;
  verifyAccessCode: (requestId: string, doctorId: string, entered: string) => Promise<{ check: OtpCheck; imports?: ImportSummary[] }>;
  revokeGrant: (grantId: string, actor: DemoUser) => void;
  saveSession: (input: NewSessionInput) => EncounterSession;
  updateSession: (id: string, patch: Partial<EncounterSession>) => void;
  completeSession: (id: string) => void;
  setTaskStatus: (id: string, status: SessionTask["status"]) => void;
  addTask: (t: { patientId: string; doctorId: string; sessionId?: string; type: TaskType; title: string }) => void;
  addRecordEvent: (input: {
    patientId: string; recordId?: string; category: Category; title: string; data: Record<string, string>;
    hospitalId: string; author: string; changeSource: ChangeSource; verification: Verification; note?: string;
  }) => RecordEvent;
  annotate: (a: Omit<ReviewAnnotation, "id" | "at">) => void;
  runInsuranceCheck: (patientId: string, info: InsuranceInfo, actor: DemoUser, sessionId?: string) => Promise<InsuranceVerification>;
  // admin
  toggleDoctorActive: (doctorId: string, actor: DemoUser) => void;
  inviteDoctor: (d: Omit<Doctor, "id" | "active">, actor: DemoUser) => void;
  testConnection: (connectionId: string, actor: DemoUser) => Promise<string>;
  setConnectionPaused: (connectionId: string, paused: boolean, actor: DemoUser) => void;
  retryExchange: (exchangeId: string, actor: DemoUser) => Promise<boolean>;
  toggleMappingField: (mappingId: string, field: string | "__category", actor: DemoUser) => void;
  logRecordView: (doctorId: string, patientId: string, detail: string) => void;
}

export type AppState = SeedState & Actions;

const DAY = 86_400_000;

export const useApp = create<AppState>()(
  persist(
    (set, get) => {
      const nextSeq = () => {
        const s = get().seq + 1;
        set({ seq: s });
        return s;
      };
      const pushAudit = (e: Omit<AuditEvent, "id" | "at">) =>
        set((st) => ({ audit: [{ id: uid("au"), at: Date.now(), ...e }, ...st.audit] }));
      const doctor = (id: string) => get().doctors.find((d) => d.id === id);
      const patientName = (id: string) => get().patients.find((p) => p.id === id)?.name ?? id;

      const ensureTask = (sessionId: string | undefined, patientId: string, doctorId: string, type: TaskType, title: string, status: SessionTask["status"] = "pending") => {
        const existing = get().tasks.find((t) => t.sessionId === sessionId && t.type === type && sessionId);
        if (existing) {
          if (existing.status !== status && status === "done") get().setTaskStatus(existing.id, "done");
          return;
        }
        set((st) => ({ tasks: [{ id: uid("t"), sessionId, patientId, doctorId, type, title, status, createdAt: Date.now(), completedAt: status === "done" ? Date.now() : undefined }, ...st.tasks] }));
      };

      const importFromSource = async (patientId: string, hospitalId: string, destHospitalId: string, categories: Category[], actor: { id: string; name: string }): Promise<ImportSummary> => {
        const st = get();
        const hospital = st.hospitals.find((h) => h.id === hospitalId)!;
        const conn = st.connections.find((c) => c.hospitalId === hospitalId);
        const identity = st.identities.find((i) => i.patientId === patientId && i.hospitalId === hospitalId);
        const sys = st.sourceSystems.find((s) => s.hospitalId === hospitalId && s.mrn === identity?.mrn);
        const exchangeId = uid("ex");
        if (!conn || conn.status === "paused") {
          const failed = "Connection paused by administrator";
          set((s) => ({ exchanges: [{ id: exchangeId, patientId, sourceHospitalId: hospitalId, destinationHospitalId: destHospitalId, initiatedBy: actor.id, initiatedByName: actor.name, requestedAt: Date.now(), categories, recordCount: 0, translation: "failed", delivery: "not-attempted", preservedFields: [], error: failed }, ...s.exchanges] }));
          return { hospitalId, retrieved: 0, newVersions: 0, unchanged: 0, preserved: [], failed };
        }
        const adapter = ADAPTERS[conn.adapterId];
        const res = await adapter.fetchPatientRecords(identity?.mrn ?? "", categories, sys?.records ?? []);
        if (!res.ok) {
          set((s) => ({ exchanges: [{ id: exchangeId, patientId, sourceHospitalId: hospitalId, destinationHospitalId: destHospitalId, initiatedBy: actor.id, initiatedByName: actor.name, requestedAt: Date.now(), categories, recordCount: 0, translation: "failed", delivery: "not-attempted", preservedFields: [], error: res.error }, ...s.exchanges] }));
          return { hospitalId, retrieved: 0, newVersions: 0, unchanged: 0, preserved: [], failed: res.error };
        }
        const mats = materialize(get().events);
        let newVersions = 0;
        let unchanged = 0;
        const preserved = new Set<string>();
        let lastSeq: number | undefined;
        for (const rec of res.records) {
          const { data } = adapter.normalize(rec);
          const mapping = get().mappings.find((m) => m.hospitalId === destHospitalId && m.category === rec.category);
          preservedFieldsFor(rec.category, data, mapping).forEach((f) => preserved.add(`${CATEGORY_LABELS[rec.category]} → ${f}`));
          const current = mats.find((m) => m.recordId === rec.sourceId);
          if (current && JSON.stringify(current.data) === JSON.stringify(data)) {
            unchanged++;
            continue;
          }
          const seq = nextSeq();
          lastSeq = seq;
          const ingestedAt = Date.now();
          const ev: RecordEvent = {
            id: uid("ev"), hash: shortHash(`${rec.sourceId}-${seq}-${ingestedAt}`), seq, patientId, recordId: rec.sourceId,
            version: (current?.version ?? 0) + 1, category: rec.category, title: rec.title, data, sourceHospitalId: hospitalId,
            author: rec.author, originSystem: `${hospital.name} · ${hospital.vendor} (mock adapter)`, changeSource: "ehr-import",
            verification: rec.category === "lab" || rec.category === "bloodGroup" ? "verified-lab" : "imported",
            recordedAt: rec.recordedAt, ingestedAt, fhirResourceType: CATEGORY_SPECS[rec.category].fhirResource,
            sourcePayload: rec.payload, exchangeEventId: exchangeId,
            note: current ? `Updated at source; retrieved via authorized exchange` : "Retrieved via authorized exchange",
          };
          set((s) => ({ events: [...s.events, ev] }));
          newVersions++;
        }
        const preservedList = Array.from(preserved);
        set((s) => ({
          exchanges: [{
            id: exchangeId, patientId, sourceHospitalId: hospitalId, destinationHospitalId: destHospitalId, initiatedBy: actor.id,
            initiatedByName: actor.name, requestedAt: Date.now(), categories, recordCount: res.records.length,
            translation: preservedList.length ? "partial" : "success", delivery: "stored-no-writeback", preservedFields: preservedList, relatedSeq: lastSeq,
          }, ...s.exchanges],
          connections: s.connections.map((c) => (c.id === conn.id ? { ...c, lastSyncAt: Date.now() } : c)),
        }));
        pushAudit({ actorId: "system", actorName: "Exchange service", actorRole: "system", hospitalId: destHospitalId, patientId, action: "exchange.completed", detail: `${res.records.length} records retrieved from ${hospital.name} (${newVersions} new versions, ${unchanged} unchanged, ${preservedList.length} preserved fields)` });
        return { hospitalId, retrieved: res.records.length, newVersions, unchanged, preserved: preservedList };
      };

      return {
        ...buildSeed(),

        resetDemo: () => set({ ...buildSeed() }),

        audit: pushAudit,

        registerPatient: (input, doctorId) => {
          const doc = doctor(doctorId)!;
          const id = `EHB-${String(10000 + Math.floor(Math.random() * 89999))}`;
          const patient: Patient = { ...input, id, createdAt: Date.now(), discoverable: false, assignedDoctorId: doctorId };
          set((st) => ({
            patients: [...st.patients, patient],
            identities: [...st.identities, { id: uid("phi"), patientId: id, hospitalId: doc.primaryHospitalId, mrn: `MEM-${Math.floor(400000 + Math.random() * 99999)}`, linkedAt: Date.now(), linkMethod: "Registered in EHR Bridge" }],
          }));
          pushAudit({ actorId: doctorId, actorName: doc.name, actorRole: "doctor", hospitalId: doc.primaryHospitalId, patientId: id, action: "patient.registered", detail: `Registered new patient ${input.name}` });
          return patient;
        },

        updatePatient: (id, patch, actor) => {
          set((st) => ({ patients: st.patients.map((p) => (p.id === id ? { ...p, ...patch } : p)) }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: actor.role, hospitalId: actor.hospitalId, patientId: id, action: "patient.updated", detail: `Updated ${Object.keys(patch).join(", ")}` });
        },

        createAccessRequest: (input) => {
          const req: AccessRequest = { ...input, id: uid("ar"), status: "pending", createdAt: Date.now() };
          const doc = doctor(input.doctorId)!;
          set((st) => ({ requests: [req, ...st.requests] }));
          const hospitals = input.sourceHospitalIds.map((h) => get().hospitals.find((x) => x.id === h)?.name).join(", ");
          pushAudit({ actorId: doc.id, actorName: doc.name, actorRole: "doctor", hospitalId: input.hospitalId, patientId: input.patientId, action: "access.request.created", detail: `Requested ${input.categories.map((c) => CATEGORY_LABELS[c]).join(", ")} from ${hospitals} (${input.durationHours}h)` });
          return req;
        },

        approveRequest: (requestId) => {
          const r = get().requests.find((x) => x.id === requestId);
          if (!r || !["pending", "investigating", "approved"].includes(r.status)) return undefined;
          const now = Date.now();
          const code: OneTimeCode = { id: uid("otp"), requestId, code: generateCode(), issuedAt: now, expiresAt: now + OTP_TTL_MS, used: false, attempts: 0, maxAttempts: OTP_MAX_ATTEMPTS };
          set((st) => ({
            codes: [...st.codes.map((c) => (c.requestId === requestId && !c.used ? { ...c, expiresAt: Math.min(c.expiresAt, now) } : c)), code],
            requests: st.requests.map((x) => (x.id === requestId ? { ...x, status: "approved", respondedAt: now } : x)),
          }));
          pushAudit({ actorId: r.patientId, actorName: patientName(r.patientId), actorRole: "patient", patientId: r.patientId, action: "access.request.approved", detail: `Approved request from ${doctor(r.doctorId)?.name}; single-use code issued (expires in 10 min)` });
          return code;
        },

        denyRequest: (requestId) => {
          const r = get().requests.find((x) => x.id === requestId);
          if (!r) return;
          set((st) => ({
            requests: st.requests.map((x) => (x.id === requestId ? { ...x, status: "denied", respondedAt: Date.now() } : x)),
            codes: st.codes.map((c) => (c.requestId === requestId ? { ...c, expiresAt: Math.min(c.expiresAt, Date.now()) } : c)),
          }));
          pushAudit({ actorId: r.patientId, actorName: patientName(r.patientId), actorRole: "patient", patientId: r.patientId, action: "access.request.denied", detail: `Denied request from ${doctor(r.doctorId)?.name}` });
        },

        investigateRequest: (requestId, question, report) => {
          const r = get().requests.find((x) => x.id === requestId);
          if (!r) return;
          set((st) => ({ requests: st.requests.map((x) => (x.id === requestId ? { ...x, status: x.status === "pending" ? "investigating" : x.status, patientQuestion: question || x.patientQuestion, reported: report || x.reported } : x)) }));
          pushAudit({ actorId: r.patientId, actorName: patientName(r.patientId), actorRole: "patient", patientId: r.patientId, action: report ? "access.request.reported" : "access.request.question", detail: report ? `Reported request from ${doctor(r.doctorId)?.name} for privacy review` : `Asked: “${question}”` });
        },

        replyToPatient: (requestId, reply) => {
          const r = get().requests.find((x) => x.id === requestId);
          if (!r) return;
          set((st) => ({ requests: st.requests.map((x) => (x.id === requestId ? { ...x, doctorReply: reply } : x)) }));
          pushAudit({ actorId: r.doctorId, actorName: doctor(r.doctorId)?.name ?? "", actorRole: "doctor", hospitalId: r.hospitalId, patientId: r.patientId, action: "access.request.reply", detail: "Replied to patient question" });
        },

        verifyAccessCode: async (requestId, doctorId, entered) => {
          const st = get();
          const doc = doctor(doctorId);
          const r = st.requests.find((x) => x.id === requestId);
          const codes = st.codes.filter((c) => c.requestId === requestId).sort((a, b) => b.issuedAt - a.issuedAt);
          const code = codes[0];
          const now = Date.now();
          const check = verifyOtp({ request: r, code, doctorId, hospitalId: doc?.primaryHospitalId ?? "", patientId: r?.patientId ?? "", entered, now });
          if (!check.ok) {
            if (check.reason === "invalid" && code) set((s) => ({ codes: s.codes.map((c) => (c.id === code.id ? { ...c, attempts: c.attempts + 1 } : c)) }));
            pushAudit({ actorId: doctorId, actorName: doc?.name ?? doctorId, actorRole: "doctor", hospitalId: doc?.primaryHospitalId, patientId: r?.patientId, action: "access.code.rejected", detail: check.message });
            return { check };
          }
          const req = r!;
          const grant = grantFromRequest(req, now, uid("g"));
          set((s) => ({
            codes: s.codes.map((c) => (c.id === code!.id ? { ...c, used: true } : c)),
            requests: s.requests.map((x) => (x.id === requestId ? { ...x, status: "active" } : x)),
            grants: [...s.grants, grant],
          }));
          pushAudit({ actorId: doctorId, actorName: doc!.name, actorRole: "doctor", hospitalId: doc!.primaryHospitalId, patientId: req.patientId, action: "access.grant.activated", detail: `Code verified (patient, request, clinician, hospital, expiry, scope). Scope: ${req.categories.map((c) => CATEGORY_LABELS[c]).join(", ")} until ${new Date(grant.expiresAt).toLocaleString()}` });
          if (req.sessionId) ensureTask(req.sessionId, req.patientId, doctorId, "patient-approval", "Patient approval received", "done");
          const imports: ImportSummary[] = [];
          for (const h of req.sourceHospitalIds) {
            imports.push(await importFromSource(req.patientId, h, doc!.primaryHospitalId, req.categories, { id: doctorId, name: doc!.name }));
          }
          // surface new discrepancies as review tasks
          const s2 = get();
          const visible = filterRecords({ doctors: s2.doctors, identities: s2.identities, grants: s2.grants, now: Date.now() }, doctorId, materialize(s2.events.filter((e) => e.patientId === req.patientId)));
          const disc = findDiscrepancies(visible);
          if (disc.length) ensureTask(req.sessionId, req.patientId, doctorId, "record-review", `Reconcile: ${disc[0].title}`);
          return { check, imports };
        },

        revokeGrant: (grantId, actor) => {
          const g = get().grants.find((x) => x.id === grantId);
          if (!g) return;
          set((st) => ({
            grants: st.grants.map((x) => (x.id === grantId ? { ...x, revokedAt: Date.now() } : x)),
            requests: st.requests.map((x) => (x.id === g.requestId ? { ...x, status: "revoked" } : x)),
          }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: actor.role, patientId: g.patientId, action: "access.grant.revoked", detail: `Revoked future access for ${doctor(g.doctorId)?.name}. Previously viewed information remains in the audit log.` });
        },

        saveSession: (input) => {
          const doc = doctor(input.doctorId)!;
          const now = Date.now();
          let session: EncounterSession;
          if (input.existingSessionId) {
            const prev = get().sessions.find((s) => s.id === input.existingSessionId)!;
            session = { ...prev, ...input, id: prev.id, updatedAt: now };
            set((st) => ({ sessions: st.sessions.map((s) => (s.id === prev.id ? session : s)) }));
          } else {
            session = {
              id: uid("s"), patientId: input.patientId, doctorId: input.doctorId, hospitalId: doc.primaryHospitalId, reason: input.reason,
              status: input.status, createdAt: now, updatedAt: now, accessRequestId: input.accessRequestId, vitals: input.vitals,
              reported: input.reported, voiceMemo: input.voiceMemo, questions: input.questions, answers: input.answers, notes: input.notes,
              insuranceVerificationId: input.insuranceVerificationId,
            };
            set((st) => ({ sessions: [session, ...st.sessions] }));
          }
          if (input.accessRequestId) set((st) => ({ requests: st.requests.map((r) => (r.id === input.accessRequestId ? { ...r, sessionId: session.id } : r)) }));
          const st = get();
          const patient = st.patients.find((p) => p.id === input.patientId)!;
          const req = st.requests.find((r) => r.id === input.accessRequestId);
          const ins = st.insurance.find((i) => i.id === input.insuranceVerificationId);
          ensureTask(session.id, patient.id, doc.id, "documentation", `Complete visit documentation — ${input.reason || "encounter"}`);
          if (req) ensureTask(session.id, patient.id, doc.id, "patient-approval", req.status === "active" ? "Patient approval received" : "Awaiting patient approval for external records", req.status === "active" ? "done" : "pending");
          ensureTask(session.id, patient.id, doc.id, "insurance", ins?.status === "eligible" ? "Insurance eligibility checked (simulated)" : "Verify insurance eligibility", ins?.status === "eligible" ? "done" : "pending");
          const missing = [patient.address === "Unknown" && "address", patient.emergencyContact === "Unknown" && "emergency contact", !patient.insurance && "insurance"].filter(Boolean);
          if (missing.length) ensureTask(session.id, patient.id, doc.id, "missing-info", `Collect missing ${missing.join(", ")}`);
          const visible = filterRecords({ doctors: st.doctors, identities: st.identities, grants: st.grants, now }, doc.id, materialize(st.events.filter((e) => e.patientId === patient.id)));
          const disc = findDiscrepancies(visible);
          if (disc.length) ensureTask(session.id, patient.id, doc.id, "record-review", `Reconcile: ${disc[0].title}`);
          const accepted = input.reported.filter((r) => r.status === "accepted");
          pushAudit({ actorId: doc.id, actorName: doc.name, actorRole: "doctor", hospitalId: doc.primaryHospitalId, patientId: patient.id, action: input.existingSessionId ? "session.updated" : "session.created", detail: `${input.status === "draft" ? "Draft saved" : "Session " + input.status}: ${input.reason} (${accepted.length} confirmed intake fields)` });
          return session;
        },

        updateSession: (id, patch) => set((st) => ({ sessions: st.sessions.map((s) => (s.id === id ? { ...s, ...patch, updatedAt: Date.now() } : s)) })),

        completeSession: (id) => {
          const s = get().sessions.find((x) => x.id === id);
          if (!s) return;
          const now = Date.now();
          set((st) => ({
            sessions: st.sessions.map((x) => (x.id === id ? { ...x, status: "completed", completedAt: now, updatedAt: now } : x)),
            tasks: st.tasks.map((t) => (t.sessionId === id && t.type === "documentation" && t.status !== "done" ? { ...t, status: "done", completedAt: now } : t)),
          }));
          const doc = doctor(s.doctorId)!;
          pushAudit({ actorId: doc.id, actorName: doc.name, actorRole: "doctor", hospitalId: s.hospitalId, patientId: s.patientId, action: "session.completed", detail: `Completed: ${s.reason}. No data was written back to the source EHR.` });
        },

        setTaskStatus: (id, status) => set((st) => ({ tasks: st.tasks.map((t) => (t.id === id ? { ...t, status, completedAt: status === "done" ? Date.now() : undefined } : t)) })),

        addTask: (t) => set((st) => ({ tasks: [{ id: uid("t"), status: "pending", createdAt: Date.now(), ...t }, ...st.tasks] })),

        addRecordEvent: (input) => {
          const mats = materialize(get().events);
          const recordId = input.recordId ?? uid("rec");
          const current = mats.find((m) => m.recordId === recordId);
          const seq = nextSeq();
          const h = get().hospitals.find((x) => x.id === input.hospitalId)!;
          const now = Date.now();
          const ev: RecordEvent = {
            id: uid("ev"), hash: shortHash(`${recordId}-${seq}-${now}`), seq, patientId: input.patientId, recordId, version: (current?.version ?? 0) + 1,
            category: input.category, title: input.title, data: input.data, sourceHospitalId: input.hospitalId, author: input.author,
            originSystem: `EHR Bridge · entered at ${h.name}`, changeSource: input.changeSource, verification: input.verification,
            recordedAt: now, ingestedAt: now, fhirResourceType: CATEGORY_SPECS[input.category].fhirResource, note: input.note,
            sourcePayload: denormalize(input.category, "Mock FHIR", input.data),
          };
          set((st) => ({ events: [...st.events, ev] }));
          return ev;
        },

        annotate: (a) => {
          set((st) => ({ annotations: [...st.annotations, { ...a, id: uid("ann"), at: Date.now() }] }));
          pushAudit({ actorId: a.by, actorName: a.byName, actorRole: "doctor", patientId: a.patientId, action: `record.${a.type}`, detail: `${a.type === "reviewed" ? "Marked reviewed" : "Flagged discrepancy"}${a.note ? `: ${a.note}` : ""}` });
          if (a.type === "reviewed" && a.targetType === "discrepancy") {
            const t = get().tasks.find((t) => t.patientId === a.patientId && t.type === "record-review" && t.status !== "done");
            if (t) get().setTaskStatus(t.id, "done");
          }
        },

        runInsuranceCheck: async (patientId, info, actor, sessionId) => {
          const v = await checkEligibility(info, patientId, uid("ins"), Date.now(), sessionId);
          set((st) => ({ insurance: [v, ...st.insurance], patients: st.patients.map((p) => (p.id === patientId ? { ...p, insurance: info } : p)) }));
          if (sessionId) {
            set((st) => ({ sessions: st.sessions.map((s) => (s.id === sessionId ? { ...s, insuranceVerificationId: v.id } : s)) }));
            if (v.status === "eligible") {
              const t = get().tasks.find((t) => t.sessionId === sessionId && t.type === "insurance" && t.status !== "done");
              if (t) get().setTaskStatus(t.id, "done");
            }
          }
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: actor.role, hospitalId: actor.hospitalId, patientId, action: "insurance.checked", detail: `Simulated eligibility check: ${v.status}` });
          return v;
        },

        toggleDoctorActive: (doctorId, actor) => {
          const d = doctor(doctorId);
          if (!d) return;
          set((st) => ({ doctors: st.doctors.map((x) => (x.id === doctorId ? { ...x, active: !x.active } : x)) }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: "admin", hospitalId: actor.hospitalId, action: d.active ? "user.deactivated" : "user.activated", detail: `${d.active ? "Deactivated" : "Activated"} account for ${d.name}` });
        },

        inviteDoctor: (d, actor) => {
          set((st) => ({ doctors: [...st.doctors, { ...d, id: uid("d"), active: true }] }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: "admin", hospitalId: actor.hospitalId, action: "user.invited", detail: `Invited ${d.name} (${d.role}, ${d.department})` });
        },

        testConnection: async (connectionId, actor) => {
          const c = get().connections.find((x) => x.id === connectionId)!;
          const res = await ADAPTERS[c.adapterId].testConnection();
          set((st) => ({ connections: st.connections.map((x) => (x.id === connectionId ? { ...x, lastTestAt: Date.now(), lastTestResult: res.message } : x)) }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: "admin", hospitalId: actor.hospitalId, action: "connection.tested", detail: res.message });
          return res.message;
        },

        setConnectionPaused: (connectionId, paused, actor) => {
          set((st) => ({ connections: st.connections.map((x) => (x.id === connectionId ? { ...x, status: paused ? "paused" : "connected" } : x)) }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: "admin", hospitalId: actor.hospitalId, action: paused ? "connection.paused" : "connection.resumed", detail: `${paused ? "Paused" : "Resumed"} sync for ${connectionId}` });
        },

        retryExchange: async (exchangeId, actor) => {
          const e = get().exchanges.find((x) => x.id === exchangeId);
          if (!e) return false;
          await new Promise((r) => setTimeout(r, 900));
          const ok = Math.random() > 0.25;
          const newEvent = {
            ...e, id: uid("ex"), requestedAt: Date.now(), initiatedBy: actor.id, initiatedByName: `${actor.name} (retry)`, retriedFrom: e.id,
            translation: ok ? ("success" as const) : ("failed" as const), delivery: ok ? ("delivered-pending" as const) : ("not-attempted" as const),
            recordCount: ok ? Math.max(1, e.recordCount) : 0, error: ok ? undefined : "Retry failed: source adapter timeout (simulated)",
          };
          set((st) => ({ exchanges: [newEvent, ...st.exchanges] }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: "admin", hospitalId: actor.hospitalId, action: ok ? "exchange.retry.succeeded" : "exchange.retry.failed", detail: `Retried exchange ${e.id}` });
          return ok;
        },

        toggleMappingField: (mappingId, field, actor) => {
          set((st) => ({
            mappings: st.mappings.map((m) => {
              if (m.id !== mappingId) return m;
              if (field === "__category") return { ...m, supported: !m.supported };
              const has = m.unsupportedFields.includes(field);
              return { ...m, unsupportedFields: has ? m.unsupportedFields.filter((f) => f !== field) : [...m.unsupportedFields, field] };
            }),
          }));
          pushAudit({ actorId: actor.id, actorName: actor.name, actorRole: "admin", hospitalId: actor.hospitalId, action: "mapping.changed", detail: `Updated import mapping ${mappingId}${field === "__category" ? "" : ` (${field})`}` });
        },

        logRecordView: (doctorId, patientId, detail) => {
          const recent = get().audit.find((a) => a.actorId === doctorId && a.patientId === patientId && a.action === "records.viewed" && Date.now() - a.at < 5 * 60_000 && a.detail === detail);
          if (recent) return;
          const d = doctor(doctorId);
          pushAudit({ actorId: doctorId, actorName: d?.name ?? doctorId, actorRole: "doctor", hospitalId: d?.primaryHospitalId, patientId, action: "records.viewed", detail });
        },
      };
    },
    {
      name: "ehr-bridge-state-v1",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => {
        // functions are excluded automatically by JSON; keep all data
        return s;
      },
    },
  ),
);

// -------- Per-tab demo login (sessionStorage so two tabs can be two different users) --------
interface AuthState {
  user: DemoUser | null;
  login: (u: DemoUser) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      login: (user) => {
        set({ user });
        useApp.getState().audit({ actorId: user.id, actorName: user.name, actorRole: user.role, hospitalId: user.hospitalId, action: "auth.login", detail: "Signed in (demo authentication — no password)" });
      },
      logout: () => set({ user: null }),
    }),
    { name: "ehr-bridge-user", storage: createJSONStorage(() => sessionStorage) },
  ),
);

export const DAY_MS = DAY;
