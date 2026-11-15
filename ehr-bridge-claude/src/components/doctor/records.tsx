"use client";

import { AlertTriangle, Layers, GitCommitHorizontal } from "lucide-react";
import type { Category, Discrepancy, MaterializedRecord } from "@/lib/types";
import { CATEGORY_SPECS } from "@/lib/adapters/translation";
import { preservedFieldsFor } from "@/lib/adapters/translation";
import { useApp } from "@/lib/store";
import { useCurrentDoctor } from "@/lib/hooks";
import { fmtDate } from "@/lib/utils";
import { Badge, EmptyState } from "../ui";
import { HospitalChip, VerificationChip } from "../chips";

export function fieldLabel(category: Category, key: string) {
  return CATEGORY_SPECS[category].fields.find((f) => f.norm === key)?.label ?? key;
}

export function recordSummary(r: MaterializedRecord): string {
  const d = r.data;
  switch (r.category) {
    case "medication": return [d.dose, d.frequency, d.status].filter(Boolean).join(" · ");
    case "allergy": return [d.reaction && `Reaction: ${d.reaction}`, d.severity, d.status].filter(Boolean).join(" · ");
    case "lab": return `${d.value ?? ""} ${d.unit ?? ""}${d.reference ? ` (ref ${d.reference})` : ""}${d.flag ? ` · ${d.flag}` : ""}`;
    case "bloodGroup": return `${d.abo ?? "?"} ${d.rh ?? ""} · ${d.method ?? ""}`;
    case "condition": return [d.status, d.onset && `Onset ${d.onset}`].filter(Boolean).join(" · ");
    case "vitals": return Object.entries(d).map(([k, v]) => `${fieldLabel("vitals", k)} ${v}`).join(" · ");
    case "imaging": return d.conclusion ?? "";
    case "procedure": return d.outcome ?? "";
    case "immunization": return [d.date && `Given ${d.date}`, d.lot && `Lot ${d.lot}`].filter(Boolean).join(" · ");
    case "encounter": return [d.type, d.reason, d.department].filter(Boolean).join(" · ");
    case "familyHistory": return `${d.relation}: ${d.condition}`;
    default: return Object.values(d).join(" · ");
  }
}

/** "Preserved — not mapped to destination" marker relative to the viewing doctor's hospital mapping. */
export function PreservedMarker({ r }: { r: MaterializedRecord }) {
  const doc = useCurrentDoctor();
  const mapping = useApp((s) => s.mappings.find((m) => m.hospitalId === doc?.primaryHospitalId && m.category === r.category));
  const hospital = useApp((s) => s.hospitals.find((h) => h.id === doc?.primaryHospitalId));
  if (!doc || r.sourceHospitalId === doc.primaryHospitalId) return null;
  const fields = preservedFieldsFor(r.category, r.data, mapping);
  if (!fields.length) return null;
  return (
    <Badge tone="amber" title={`${hospital?.name}'s configured import mapping cannot accept: ${fields.join(", ")}. EHR Bridge keeps the value in the normalized record with full provenance.`}>
      <Layers />Preserved — not mapped to {hospital?.shortName} ({hospital?.vendor})
    </Badge>
  );
}

export function RecordRow({ r, onHistory, discrepancy }: { r: MaterializedRecord; onHistory?: (r: MaterializedRecord) => void; discrepancy?: Discrepancy }) {
  return (
    <div className={`rounded-lg border bg-white p-3 ${discrepancy ? "border-rose-200 ring-1 ring-rose-100" : "border-slate-200"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900">{r.title}</p>
          <p className="mt-0.5 text-[13px] text-slate-600">{recordSummary(r)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {discrepancy && <Badge tone="red"><AlertTriangle />Possible conflict</Badge>}
          <VerificationChip v={r.verification} />
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
        <HospitalChip hospitalId={r.sourceHospitalId} />
        <span>Recorded {fmtDate(r.recordedAt)}</span>
        <span>·</span>
        <span>{r.author}</span>
        <PreservedMarker r={r} />
        {onHistory && (
          <button onClick={() => onHistory(r)} className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-[#2a5bd7] hover:bg-blue-50">
            <GitCommitHorizontal className="size-3.5" /> v{r.version} · history
          </button>
        )}
      </div>
    </div>
  );
}

export function RecordList({ records, empty, onHistory, discrepancies = [] }: { records: MaterializedRecord[]; empty?: string; onHistory?: (r: MaterializedRecord) => void; discrepancies?: Discrepancy[] }) {
  if (!records.length) return <EmptyState title={empty ?? "No records in this category"} description="Only information you're permitted to see is shown." />;
  return (
    <div className="space-y-2">
      {records.map((r) => (
        <RecordRow key={r.recordId} r={r} onHistory={onHistory} discrepancy={discrepancies.find((d) => d.values.some((v) => v.recordId === r.recordId))} />
      ))}
    </div>
  );
}

export function DiscrepancyCard({ d, onHistory, actions }: { d: Discrepancy; onHistory?: (recordId: string) => void; actions?: React.ReactNode }) {
  const hospitals = useApp((s) => s.hospitals);
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-semibold text-rose-900"><AlertTriangle className="size-4" /> {d.title}</p>
          <p className="mt-0.5 text-xs text-rose-800/80">EHR Bridge does not decide which value is correct. Review the sources and reconcile with the patient.</p>
        </div>
        {actions}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {d.values.map((v) => (
          <div key={v.recordId} className="rounded-lg border border-rose-100 bg-white p-3">
            <div className="flex items-center justify-between">
              <span className="text-lg font-semibold text-slate-900">{v.value}</span>
              <HospitalChip hospitalId={v.sourceHospitalId} />
            </div>
            <p className="mt-1 text-xs text-slate-500">Recorded {fmtDate(v.recordedAt)} by {v.author} · {hospitals.find((h) => h.id === v.sourceHospitalId)?.vendor}</p>
            {onHistory && <button className="mt-1.5 text-xs font-medium text-[#2a5bd7] hover:underline" onClick={() => onHistory(v.recordId)}>View version timeline →</button>}
          </div>
        ))}
      </div>
    </div>
  );
}
