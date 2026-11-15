"use client";

import { AlertTriangle, BadgeCheck, Bot, Building2, CheckCircle2, CircleDashed, Clock, FlaskConical, FileWarning, Hourglass, Lock, ShieldAlert, ShieldCheck, Stethoscope, User, XCircle, Archive, CalendarClock, PencilLine, FlaskRound } from "lucide-react";
import { Badge } from "./ui";
import { useApp } from "@/lib/store";
import type { AccessRequest, FieldMapStatus, ItemSource, Verification } from "@/lib/types";
import type { QueueStatus } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export function HospitalChip({ hospitalId, className, showVendor = true }: { hospitalId?: string; className?: string; showVendor?: boolean }) {
  const h = useApp((s) => s.hospitals.find((x) => x.id === hospitalId));
  if (!h) return <Badge tone="outline" className={className}>Unknown source</Badge>;
  const tone = h.id === "h-memorial" ? "navy" : h.id === "h-valley" ? "teal" : "violet";
  return (
    <Badge tone={tone} className={className}>
      <Building2 />
      {h.shortName}
      {showVendor && <span className="opacity-60">· {h.vendor}</span>}
    </Badge>
  );
}

export const VERIFICATION_META: Record<Verification, { label: string; tone: "green" | "blue" | "amber" | "navy" | "violet"; icon: React.ReactNode; help: string }> = {
  "verified-lab": { label: "Verified lab value", tone: "green", icon: <FlaskConical />, help: "Resulted laboratory value from the originating hospital's lab system." },
  imported: { label: "Imported hospital record", tone: "blue", icon: <Building2 />, help: "Imported from a hospital EHR via a (mock) adapter. Not re-verified by EHR Bridge." },
  "patient-reported": { label: "Patient-reported", tone: "amber", icon: <User />, help: "Stated by the patient. Not a verified clinical fact." },
  "doctor-entered": { label: "Clinician-entered", tone: "navy", icon: <Stethoscope />, help: "Entered or confirmed by a clinician in EHR Bridge." },
  "ai-draft": { label: "Extracted draft", tone: "violet", icon: <Bot />, help: "Automatically extracted suggestion. Must be reviewed before use." },
};

export function VerificationChip({ v, className }: { v: Verification; className?: string }) {
  const m = VERIFICATION_META[v];
  return (
    <Badge tone={m.tone} className={className} title={m.help}>
      {m.icon}
      {m.label}
    </Badge>
  );
}

export function ItemSourceChip({ source, status }: { source: ItemSource; status?: "draft" | "accepted" | "rejected" }) {
  if (source === "ai-extracted")
    return (
      <Badge tone={status === "accepted" ? "amber" : "violet"} title={status === "accepted" ? "Patient-reported, captured from voice memo and confirmed by clinician" : "Automatically extracted — draft"}>
        {status === "accepted" ? <User /> : <Bot />}
        {status === "accepted" ? "Patient-reported · via voice memo" : "Extracted draft"}
      </Badge>
    );
  if (source === "doctor-entered") return <Badge tone="navy"><Stethoscope />Clinician-entered</Badge>;
  return <Badge tone="amber"><User />Patient-reported</Badge>;
}

const QS: Record<QueueStatus, { tone: "amber" | "green" | "red" | "blue" | "slate" | "violet" | "navy"; icon: React.ReactNode }> = {
  "Awaiting patient approval": { tone: "amber", icon: <Hourglass /> },
  "Record discrepancy": { tone: "red", icon: <AlertTriangle /> },
  "Insurance verification needed": { tone: "amber", icon: <ShieldAlert /> },
  "Missing information": { tone: "amber", icon: <FileWarning /> },
  "Documentation pending": { tone: "blue", icon: <PencilLine /> },
  "Ready for review": { tone: "navy", icon: <CircleDashed /> },
  Completed: { tone: "green", icon: <CheckCircle2 /> },
  Draft: { tone: "slate", icon: <Archive /> },
  Scheduled: { tone: "violet", icon: <CalendarClock /> },
};
export function QueueStatusBadge({ status }: { status: QueueStatus }) {
  const m = QS[status];
  return <Badge tone={m.tone}>{m.icon}{status}</Badge>;
}

export function RequestStatusBadge({ status }: { status: AccessRequest["status"] }) {
  const map: Record<AccessRequest["status"], [string, "amber" | "green" | "red" | "slate" | "blue" | "violet", React.ReactNode]> = {
    pending: ["Awaiting patient", "amber", <Clock key="i" />],
    investigating: ["Patient has questions", "violet", <ShieldAlert key="i" />],
    approved: ["Approved — code issued", "blue", <BadgeCheck key="i" />],
    active: ["Access active", "green", <ShieldCheck key="i" />],
    denied: ["Denied", "red", <XCircle key="i" />],
    expired: ["Expired", "slate", <Hourglass key="i" />],
    revoked: ["Revoked", "slate", <Lock key="i" />],
  };
  const [label, tone, icon] = map[status];
  return <Badge tone={tone}>{icon}{label}</Badge>;
}

export function MapStatusBadge({ s, className }: { s: FieldMapStatus; className?: string }) {
  const map: Record<FieldMapStatus, [string, "green" | "blue" | "slate" | "amber" | "red"]> = {
    mapped: ["Mapped", "green"],
    transformed: ["Transformed", "blue"],
    missing: ["Missing", "slate"],
    preserved: ["Preserved — not mapped", "amber"],
    failed: ["Failed", "red"],
  };
  const [l, t] = map[s];
  return <Badge tone={t} className={className}>{l}</Badge>;
}

export function DemoTag({ children = "Demo simulation", className }: { children?: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded border border-dashed border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800", className)}>
      <FlaskRound className="size-3" />
      {children}
    </span>
  );
}
