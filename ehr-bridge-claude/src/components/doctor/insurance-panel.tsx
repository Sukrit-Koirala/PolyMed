"use client";

import { useState } from "react";
import { BadgeDollarSign, CheckCircle2, Download, Loader2, ShieldQuestion, XCircle, AlertTriangle } from "lucide-react";
import { useApp, useAuth } from "@/lib/store";
import type { InsuranceInfo } from "@/lib/types";
import { Badge, Button, Callout, Field, Input, Table, Td, Th } from "../ui";
import { DemoTag } from "../chips";
import { fmtDateTime } from "@/lib/utils";
import { toast } from "../toast";

const EMPTY: InsuranceInfo = { provider: "", plan: "", memberId: "", groupNumber: "", coverageStart: "", coverageEnd: "" };

export function InsurancePanel({ patientId, sessionId, onVerified, compact }: { patientId: string; sessionId?: string; onVerified?: (id: string) => void; compact?: boolean }) {
  const user = useAuth((s) => s.user)!;
  const patient = useApp((s) => s.patients.find((p) => p.id === patientId));
  const verifications = useApp((s) => s.insurance);
  const run = useApp((s) => s.runInsuranceCheck);
  const [info, setInfo] = useState<InsuranceInfo>(patient?.insurance ?? EMPTY);
  const [busy, setBusy] = useState(false);
  const latest = verifications.filter((v) => v.patientId === patientId && (!sessionId || v.sessionId === sessionId || !v.sessionId)).sort((a, b) => b.checkedAt - a.checkedAt)[0];

  const set = (k: keyof InsuranceInfo, v: string) => setInfo((i) => ({ ...i, [k]: v }));
  const check = async () => {
    setBusy(true);
    const v = await run(patientId, info, user, sessionId);
    setBusy(false);
    onVerified?.(v.id);
    toast(v.status === "eligible" ? "Simulated eligibility: active" : `Simulated eligibility: ${v.status}`, "Mock payer response — not a coverage guarantee.", v.status === "eligible" ? "success" : "warning");
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-slate-900"><BadgeDollarSign className="size-4 text-slate-500" /> Insurance assistant</p>
        <DemoTag>Mock payer — no real eligibility check</DemoTag>
      </div>
      <div className={`grid gap-3 ${compact ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}>
        <Field label="Insurance provider"><Input value={info.provider} onChange={(e) => set("provider", e.target.value)} placeholder="Unknown" /></Field>
        <Field label="Plan"><Input value={info.plan} onChange={(e) => set("plan", e.target.value)} placeholder="Unknown" /></Field>
        <Field label="Member ID"><Input value={info.memberId} onChange={(e) => set("memberId", e.target.value)} placeholder="Unknown" /></Field>
        <Field label="Group number"><Input value={info.groupNumber} onChange={(e) => set("groupNumber", e.target.value)} placeholder="Unknown" /></Field>
        <Field label="Coverage start"><Input type="date" value={info.coverageStart} onChange={(e) => set("coverageStart", e.target.value)} /></Field>
        <Field label="Coverage end"><Input type="date" value={info.coverageEnd} onChange={(e) => set("coverageEnd", e.target.value)} /></Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" disabled={!patient?.insurance} onClick={() => { setInfo(patient!.insurance!); toast("Imported from patient profile"); }}><Download /> Import from patient profile</Button>
        <Button variant="primary" size="sm" onClick={check} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <ShieldQuestion />} Run eligibility check (simulated)</Button>
      </div>

      {latest && (
        <div className="rounded-xl border border-slate-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
            <div className="flex items-center gap-2">
              {latest.status === "eligible" ? <CheckCircle2 className="size-4 text-emerald-600" /> : <XCircle className="size-4 text-rose-600" />}
              <span className="text-sm font-medium">{latest.status === "eligible" ? "Coverage appears active" : latest.status === "inactive" ? "Coverage appears inactive for today" : "Member not found"}</span>
              <Badge tone="amber">Simulated — not verified</Badge>
            </div>
            <span className="text-[11px] text-slate-500">{latest.source} · {fmtDateTime(latest.checkedAt)}</span>
          </div>
          <Table>
            <thead>
              <tr><Th>Service</Th><Th>Eligibility</Th><Th>Network</Th><Th>Copay / cost estimate</Th><Th>Deductible</Th><Th>Prior auth</Th></tr>
            </thead>
            <tbody>
              {latest.services.map((s) => (
                <tr key={s.service}>
                  <Td className="font-medium text-slate-800">{s.service}</Td>
                  <Td>{s.eligible === true ? <Badge tone="green">Eligible</Badge> : s.eligible === false ? <Badge tone="red">Not eligible</Badge> : <Badge>Unknown</Badge>}</Td>
                  <Td>{s.inNetwork === true ? "In-network" : s.inNetwork === false ? "Out-of-network" : "Unknown"}</Td>
                  <Td>{s.copay ?? "Not available"}</Td>
                  <Td className="text-xs">{s.deductible ?? "Not available"}</Td>
                  <Td>{s.priorAuth === "required" ? <Badge tone="amber"><AlertTriangle />Required</Badge> : s.priorAuth === "not-required" ? "Not required" : "Unknown"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Callout tone="slate" className="m-3" icon={<ShieldQuestion />}>
            Estimates come from a simulated payer service and are shown only to reduce administrative investigation. They are not a coverage determination or guarantee of payment, and they do not inform clinical decisions.
          </Callout>
        </div>
      )}
    </div>
  );
}
