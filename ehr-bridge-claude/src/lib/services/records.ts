import type { Discrepancy, MaterializedRecord, RecordEvent, ReviewAnnotation } from "../types";

/** Build the current view of each record from its append-only event log. */
export function materialize(events: RecordEvent[]): MaterializedRecord[] {
  const byRecord = new Map<string, RecordEvent[]>();
  for (const e of events) {
    const list = byRecord.get(e.recordId) ?? [];
    list.push(e);
    byRecord.set(e.recordId, list);
  }
  const out: MaterializedRecord[] = [];
  for (const [recordId, list] of byRecord) {
    list.sort((a, b) => a.version - b.version);
    const last = list[list.length - 1];
    if (last.retracted) continue;
    out.push({
      recordId, patientId: last.patientId, category: last.category, title: last.title, data: last.data,
      sourceHospitalId: last.sourceHospitalId, author: last.author, originSystem: last.originSystem,
      changeSource: last.changeSource, verification: last.verification, recordedAt: last.recordedAt,
      version: last.version, latestEventId: last.id, events: list, fhirResourceType: last.fhirResourceType,
    });
  }
  return out.sort((a, b) => b.recordedAt - a.recordedAt);
}

const norm = (s: string | undefined) => (s ?? "").trim().toLowerCase();

/**
 * Surface possible conflicts between sources. EHR Bridge never decides which
 * value is correct; it only points at the disagreement.
 */
export function findDiscrepancies(records: MaterializedRecord[]): Discrepancy[] {
  const out: Discrepancy[] = [];
  const groups = new Map<string, MaterializedRecord[]>();
  for (const r of records) {
    if (r.category !== "medication") continue;
    if (norm(r.data.status) && norm(r.data.status) !== "active") continue;
    const key = `${r.patientId}|${norm(r.data.drug)}`;
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  for (const [key, list] of groups) {
    const doses = new Set(list.map((r) => norm(r.data.dose)));
    if (list.length > 1 && doses.size > 1) {
      out.push({
        id: `disc-${key.replace(/[^a-z0-9]/gi, "-")}`,
        patientId: list[0].patientId, category: "medication", title: `${list[0].data.drug} dose differs between sources`, field: "dose",
        values: list.map((r) => ({ recordId: r.recordId, value: r.data.dose, sourceHospitalId: r.sourceHospitalId, recordedAt: r.recordedAt, author: r.author })),
      });
    }
  }
  return out;
}

export function reviewStatus(annotations: ReviewAnnotation[], targetId: string): { reviewed?: ReviewAnnotation; flagged?: ReviewAnnotation } {
  const list = annotations.filter((a) => a.targetId === targetId).sort((a, b) => b.at - a.at);
  return { reviewed: list.find((a) => a.type === "reviewed"), flagged: list.find((a) => a.type === "flagged") };
}

export interface FieldDiff { field: string; before?: string; after?: string; kind: "added" | "removed" | "modified" | "unchanged" }

export function diffData(a: Record<string, string> | undefined, b: Record<string, string>): FieldDiff[] {
  const keys = Array.from(new Set([...Object.keys(a ?? {}), ...Object.keys(b)]));
  return keys.map((k) => {
    const before = a?.[k];
    const after = b[k];
    const kind = before === undefined ? "added" : after === undefined ? "removed" : before !== after ? "modified" : "unchanged";
    return { field: k, before, after, kind } as FieldDiff;
  });
}

export function completeness(records: MaterializedRecord[], hasInsurance: boolean, hasEmergency: boolean): number {
  const want = ["allergy", "medication", "condition", "vitals", "lab", "immunization"];
  const have = want.filter((c) => records.some((r) => r.category === c)).length;
  const score = (have + (hasInsurance ? 1 : 0) + (hasEmergency ? 1 : 0)) / (want.length + 2);
  return Math.round(score * 100);
}
