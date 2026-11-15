import type { AccessGrant, AccessRequest, OneTimeCode } from "../types";

/** SIMULATED OTP service — demonstration only. Codes are generated locally and never sent over SMS/email. */
export const OTP_TTL_MS = 10 * 60 * 1000;
export const OTP_MAX_ATTEMPTS = 5;

export function generateCode(): string {
  const arr = new Uint32Array(1);
  crypto.getRandomValues(arr);
  return String(arr[0] % 1_000_000).padStart(6, "0");
}

export type OtpFailure = "no-request" | "wrong-doctor" | "wrong-hospital" | "not-approved" | "denied" | "no-code" | "expired" | "used" | "locked" | "invalid";

export type OtpCheck = { ok: true } | { ok: false; reason: OtpFailure; message: string; attemptsLeft?: number };

export function verifyOtp(input: {
  request?: AccessRequest; code?: OneTimeCode; doctorId: string; hospitalId: string; patientId: string; entered: string; now: number;
}): OtpCheck {
  const { request: r, code: c, now } = input;
  if (!r || r.patientId !== input.patientId) return { ok: false, reason: "no-request", message: "No matching access request for this patient." };
  if (r.doctorId !== input.doctorId) return { ok: false, reason: "wrong-doctor", message: "This request belongs to a different clinician." };
  if (r.hospitalId !== input.hospitalId) return { ok: false, reason: "wrong-hospital", message: "Request was made from a different hospital." };
  if (r.status === "denied") return { ok: false, reason: "denied", message: "The patient denied this request." };
  if (r.status === "active") return { ok: false, reason: "used", message: "This request has already been activated." };
  if (r.status !== "approved") return { ok: false, reason: "not-approved", message: "The patient has not approved this request yet." };
  if (!c) return { ok: false, reason: "no-code", message: "No code has been issued for this request." };
  if (c.used) return { ok: false, reason: "used", message: "This code has already been used." };
  if (c.attempts >= c.maxAttempts) return { ok: false, reason: "locked", message: "Too many incorrect attempts. Ask the patient to approve again." };
  if (now > c.expiresAt) return { ok: false, reason: "expired", message: "This code has expired. Ask the patient to approve again for a new code." };
  if (input.entered.trim() !== c.code) return { ok: false, reason: "invalid", message: "Incorrect code.", attemptsLeft: c.maxAttempts - c.attempts - 1 };
  return { ok: true };
}

export function grantFromRequest(r: AccessRequest, now: number, id: string): AccessGrant {
  return {
    id, requestId: r.id, patientId: r.patientId, doctorId: r.doctorId, hospitalId: r.hospitalId,
    categories: r.categories, sourceHospitalIds: r.sourceHospitalIds, grantedAt: now, expiresAt: now + r.durationHours * 3_600_000,
  };
}
