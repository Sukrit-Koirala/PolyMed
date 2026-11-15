import type { InsuranceInfo, InsuranceVerification, ServiceBenefit } from "../types";

/**
 * MOCK payer eligibility service. Returns deterministic, clearly-labelled
 * simulated responses. No payer is contacted. A result here is NOT a coverage
 * determination or a guarantee of payment.
 */
export const INSURANCE_SOURCE = "Simulated payer response (demo) — no payer contacted";

export async function checkEligibility(info: InsuranceInfo, patientId: string, id: string, now: number, sessionId?: string): Promise<InsuranceVerification> {
  await new Promise((r) => setTimeout(r, 900));
  const today = new Date(now).toISOString().slice(0, 10);
  const blank = !info.memberId.trim() || !info.provider.trim();
  const inactive = !blank && (info.coverageEnd < today || info.coverageStart > today);
  const status: InsuranceVerification["status"] = blank ? "not-found" : inactive ? "inactive" : "eligible";
  const hdhp = /hdhp|bronze/i.test(info.plan);
  const hmo = /hmo/i.test(info.plan);
  const ok = status === "eligible";
  const services: ServiceBenefit[] = [
    { service: "Primary care visit", eligible: ok, inNetwork: ok, copay: ok ? (hdhp ? "Deductible applies" : "$25") : undefined, deductible: ok ? (hdhp ? "$3,200 remaining of $3,500" : "$450 remaining of $1,000") : undefined, priorAuth: "not-required" },
    { service: "Blood tests", eligible: ok, inNetwork: ok, copay: ok ? (hdhp ? "Deductible applies" : "$0 (in-network lab)") : undefined, deductible: ok ? "Applies after visit" : undefined, priorAuth: "not-required" },
    { service: "Imaging (MRI / CT)", eligible: ok, inNetwork: ok ? true : "unknown", copay: ok ? "20% coinsurance after deductible" : undefined, priorAuth: ok ? "required" : "unknown" },
    { service: "Specialist consultation", eligible: ok, inNetwork: ok ? (hmo ? "unknown" : true) : "unknown", copay: ok ? (hmo ? "$60 — referral required" : "$50") : undefined, priorAuth: hmo ? "required" : ok ? "not-required" : "unknown" },
  ];
  return { id, patientId, sessionId, info, status, checkedAt: now, source: INSURANCE_SOURCE, services };
}
