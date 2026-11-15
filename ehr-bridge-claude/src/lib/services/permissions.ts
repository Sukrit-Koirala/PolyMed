import type { AccessGrant, Category, Doctor, MaterializedRecord, PatientHospitalIdentity } from "../types";

/*
 * DEMO SECURITY SIMULATION.
 * These checks run in the browser against fictional data. They model the
 * intended server-side policy (tenant isolation + patient-specific grants)
 * but are NOT a production access-control implementation.
 */

export interface PolicyContext {
  doctors: Doctor[];
  identities: PatientHospitalIdentity[];
  grants: AccessGrant[];
  now: number;
}

export function activeGrants(ctx: PolicyContext, doctorId: string, patientId: string) {
  return ctx.grants.filter((g) => g.doctorId === doctorId && g.patientId === patientId && !g.revokedAt && g.expiresAt > ctx.now);
}

/** A doctor may see a patient if the patient is registered at one of the doctor's hospitals, or has granted access. */
export function canViewPatient(ctx: PolicyContext, doctorId: string, patientId: string): boolean {
  const doc = ctx.doctors.find((d) => d.id === doctorId);
  if (!doc || !doc.active) return false;
  const local = ctx.identities.some((i) => i.patientId === patientId && doc.hospitalIds.includes(i.hospitalId));
  return local || activeGrants(ctx, doctorId, patientId).length > 0;
}

export type RecordAccess = { allowed: true; via: "home-hospital" | "grant"; grantId?: string } | { allowed: false };

/** Record-level check: source must be the doctor's own tenant (patient registered there) or covered by an active grant's scope. */
export function canViewRecord(ctx: PolicyContext, doctorId: string, r: Pick<MaterializedRecord, "patientId" | "sourceHospitalId" | "category">): RecordAccess {
  const doc = ctx.doctors.find((d) => d.id === doctorId);
  if (!doc || !doc.active || !r.sourceHospitalId) return { allowed: false };
  if (doc.hospitalIds.includes(r.sourceHospitalId) && ctx.identities.some((i) => i.patientId === r.patientId && i.hospitalId === r.sourceHospitalId)) {
    return { allowed: true, via: "home-hospital" };
  }
  const g = activeGrants(ctx, doctorId, r.patientId).find((g) => g.sourceHospitalIds.includes(r.sourceHospitalId!) && g.categories.includes(r.category as Category));
  return g ? { allowed: true, via: "grant", grantId: g.id } : { allowed: false };
}

export function filterRecords<T extends Pick<MaterializedRecord, "patientId" | "sourceHospitalId" | "category">>(ctx: PolicyContext, doctorId: string, records: T[]) {
  return records.filter((r) => canViewRecord(ctx, doctorId, r).allowed);
}

/** Hospitals where the patient is known but the doctor has no access. Only names are revealed, and only if the patient opted into discovery. */
export function lockedSources(ctx: PolicyContext, doctorId: string, patientId: string, discoverable: boolean) {
  if (!discoverable) return [];
  const doc = ctx.doctors.find((d) => d.id === doctorId);
  if (!doc) return [];
  const grants = activeGrants(ctx, doctorId, patientId);
  return ctx.identities
    .filter((i) => i.patientId === patientId && !doc.hospitalIds.includes(i.hospitalId))
    .map((i) => ({ hospitalId: i.hospitalId, grantedCategories: Array.from(new Set(grants.filter((g) => g.sourceHospitalIds.includes(i.hospitalId)).flatMap((g) => g.categories))) }));
}
