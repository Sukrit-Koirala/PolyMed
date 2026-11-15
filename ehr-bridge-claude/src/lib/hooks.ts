"use client";

import { useEffect, useMemo, useState } from "react";
import { useApp, useAuth } from "./store";
import { canViewPatient, filterRecords, lockedSources, type PolicyContext } from "./services/permissions";
import { completeness, findDiscrepancies, materialize } from "./services/records";
import type { AccessRequest, EncounterSession, Patient, SessionTask } from "./types";

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function useHydrated() {
  const [h, setH] = useState(false);
  useEffect(() => {
    const done = () => setH(true);
    const unsub = useApp.persist.onFinishHydration(done);
    if (useApp.persist.hasHydrated() && useAuth.persist.hasHydrated()) done();
    return unsub;
  }, []);
  return h;
}

export function useCurrentDoctor() {
  const user = useAuth((s) => s.user);
  const doctors = useApp((s) => s.doctors);
  return user?.role === "doctor" ? doctors.find((d) => d.id === user.id) : undefined;
}

export function usePolicy(): PolicyContext {
  const doctors = useApp((s) => s.doctors);
  const identities = useApp((s) => s.identities);
  const grants = useApp((s) => s.grants);
  const now = useNow(15000);
  return useMemo(() => ({ doctors, identities, grants, now }), [doctors, identities, grants, now]);
}

export function useAllRecords() {
  const events = useApp((s) => s.events);
  return useMemo(() => materialize(events), [events]);
}

/** Records for a patient that the current doctor is permitted to see. */
export function useVisibleRecords(patientId: string | undefined) {
  const doc = useCurrentDoctor();
  const policy = usePolicy();
  const all = useAllRecords();
  return useMemo(() => {
    if (!doc || !patientId) return [];
    return filterRecords(policy, doc.id, all.filter((r) => r.patientId === patientId));
  }, [doc, patientId, policy, all]);
}

export function useVisiblePatients() {
  const doc = useCurrentDoctor();
  const policy = usePolicy();
  const patients = useApp((s) => s.patients);
  return useMemo(() => (doc ? patients.filter((p) => canViewPatient(policy, doc.id, p.id)) : []), [doc, patients, policy]);
}

export function usePatientSummary(patient: Patient | undefined) {
  const doc = useCurrentDoctor();
  const policy = usePolicy();
  const records = useVisibleRecords(patient?.id);
  const identities = useApp((s) => s.identities);
  const hospitals = useApp((s) => s.hospitals);
  return useMemo(() => {
    if (!patient || !doc) return undefined;
    const discrepancies = findDiscrepancies(records);
    const locked = lockedSources(policy, doc.id, patient.id, patient.discoverable);
    const connected = identities.filter((i) => i.patientId === patient.id).map((i) => hospitals.find((h) => h.id === i.hospitalId)!);
    const bg = records.find((r) => r.category === "bloodGroup" && r.verification === "verified-lab");
    const lastUpdated = records.reduce((m, r) => Math.max(m, r.events[r.events.length - 1].ingestedAt), 0);
    const comp = completeness(records, !!patient.insurance, patient.emergencyContact !== "Unknown");
    return { records, discrepancies, locked, connected, bloodGroup: bg ? `${bg.data.abo}${bg.data.rh === "Positive" ? "+" : bg.data.rh === "Negative" ? "−" : ""}` : undefined, bloodGroupSource: bg, lastUpdated, completeness: comp };
  }, [patient, doc, records, policy, identities, hospitals]);
}

export type QueueStatus =
  | "Awaiting patient approval"
  | "Record discrepancy"
  | "Insurance verification needed"
  | "Missing information"
  | "Documentation pending"
  | "Ready for review"
  | "Completed"
  | "Draft"
  | "Scheduled";

export function queueStatus(session: EncounterSession, tasks: SessionTask[], requests: AccessRequest[]): QueueStatus {
  if (session.status === "completed") return "Completed";
  if (session.status === "draft") return "Draft";
  if (session.status === "scheduled") return "Scheduled";
  const open = tasks.filter((t) => t.sessionId === session.id && t.status !== "done");
  const req = requests.find((r) => r.id === session.accessRequestId);
  if (req && ["pending", "investigating", "approved"].includes(req.status)) return "Awaiting patient approval";
  if (open.some((t) => t.type === "patient-approval")) return "Awaiting patient approval";
  if (open.some((t) => t.type === "record-review")) return "Record discrepancy";
  if (open.some((t) => t.type === "insurance")) return "Insurance verification needed";
  if (open.some((t) => t.type === "missing-info")) return "Missing information";
  if (open.some((t) => t.type === "documentation")) return "Documentation pending";
  return "Ready for review";
}

export function isToday(t: number | undefined, now = Date.now()) {
  if (!t) return false;
  const a = new Date(t);
  const b = new Date(now);
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** Effective request status, accounting for expiry of codes and grants. */
export function effectiveRequestStatus(r: AccessRequest, codes: { requestId: string; expiresAt: number; used: boolean }[], grants: { requestId: string; expiresAt: number; revokedAt?: number }[], now: number): AccessRequest["status"] {
  if (r.status === "approved") {
    const c = codes.filter((c) => c.requestId === r.id && !c.used).sort((a, b) => b.expiresAt - a.expiresAt)[0];
    if (!c || c.expiresAt < now) return "expired";
  }
  if (r.status === "active") {
    const g = grants.find((g) => g.requestId === r.id);
    if (g && !g.revokedAt && g.expiresAt < now) return "expired";
  }
  if ((r.status === "pending" || r.status === "investigating") && now - r.createdAt > 7 * 86_400_000) return "expired";
  return r.status;
}
