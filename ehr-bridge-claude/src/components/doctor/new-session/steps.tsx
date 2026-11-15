"use client";

import { useMemo, useState } from "react";
import { Search, UserPlus, Building2, Lock, ShieldCheck, CircleSlash, Send, Plus, Trash2, User, Stethoscope, HeartPulse, ClipboardList, AlertTriangle, BadgeDollarSign, Mic, ListChecks, Pencil, CheckCircle2, FileWarning, Database, Info } from "lucide-react";
import { useApp } from "@/lib/store";
import { effectiveRequestStatus, useCurrentDoctor, useNow, usePatientSummary, useVisiblePatients } from "@/lib/hooks";
import { CATEGORY_LABELS, CATEGORY_PLAIN } from "@/lib/adapters/translation";
import type { Category, IntakeQuestion, Patient, QuestionType, ReportedItem } from "@/lib/types";
import { ageFrom, cn, fmtDate, uid } from "@/lib/utils";
import { Badge, Button, Callout, Card, CardBody, CardHeader, Checkbox, EmptyState, Field, Input, KV, Select, Textarea } from "../../ui";
import { HospitalChip, ItemSourceChip, RequestStatusBadge, VerificationChip } from "../../chips";
import { AccessCodePanel } from "../code-entry";
import { VoiceMemoPanel } from "../voice-memo";
import { InsurancePanel } from "../insurance-panel";
import { DiscrepancyCard, RecordRow } from "../records";
import type { Draft } from "./modal";
import { toast } from "../../toast";

type StepProps = { draft: Draft; patch: (p: Partial<Draft>) => void; goTo?: (s: number) => void };

const Unknown = () => <span className="rounded border border-dashed border-amber-300 bg-amber-50 px-1.5 text-[11px] font-medium text-amber-800">Unknown</span>;
const val = (v?: string) => (!v || v === "Unknown" ? <Unknown /> : v);

/* ======================= STEP 1 — PATIENT ======================= */
export function PatientStep({ draft, patch }: StepProps) {
  const doc = useCurrentDoctor()!;
  const visible = useVisiblePatients();
  const hospitals = useApp((s) => s.hospitals);
  const identities = useApp((s) => s.identities);
  const register = useApp((s) => s.registerPatient);
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<"search" | "register">("search");
  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return visible.slice(0, 8);
    return visible.filter((p) => p.name.toLowerCase().includes(t) || p.id.toLowerCase().includes(t));
  }, [q, visible]);
  const selected = visible.find((p) => p.id === draft.patientId);
  const hospital = hospitals.find((h) => h.id === doc.primaryHospitalId)!;

  return (
    <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-900">Find or register a patient</h3>
          <Button variant={mode === "register" ? "outline" : "ghost"} size="sm" onClick={() => setMode(mode === "register" ? "search" : "register")}>
            {mode === "register" ? <><Search /> Back to search</> : <><UserPlus /> Create new patient</>}
          </Button>
        </div>
        {mode === "search" ? (
          <>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
              <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by patient name or unique patient ID (e.g. Sarah Mitchell, EHB-20417)" className="h-11 pl-9" />
            </div>
            <p className="mt-1.5 text-[11px] text-slate-500">Searching patients registered at {hospital.name} or who have granted you access. Knowing another hospital's patient ID does not reveal that patient.</p>
            <div className="mt-3 space-y-1.5">
              {results.length === 0 && (
                <EmptyState icon={<Search />} title="No matching patient you're permitted to see" description="Register the patient at your hospital to start a session. Records at other organizations can then be requested with the patient's approval."
                  action={<Button size="sm" variant="outline" onClick={() => setMode("register")}><UserPlus /> Create new patient</Button>} />
              )}
              {results.map((p) => {
                const ids = identities.filter((i) => i.patientId === p.id);
                return (
                  <button key={p.id} onClick={() => patch({ patientId: p.id, requestId: undefined })} className={cn("flex w-full items-center gap-3 rounded-xl border bg-white p-3 text-left transition-all", draft.patientId === p.id ? "border-navy-400 ring-2 ring-navy-100" : "border-slate-200 hover:border-slate-300")}>
                    <div className="flex size-9 items-center justify-center rounded-full bg-navy-50 text-xs font-semibold text-navy-800">{p.name.split(" ").map((x) => x[0]).join("")}</div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-900">{p.name}</p>
                      <p className="text-xs text-slate-500">{p.id} · {ageFrom(p.dob)} y · {p.sexRecorded} · DOB {fmtDate(p.dob)}</p>
                    </div>
                    <div className="hidden gap-1 sm:flex">
                      {ids.filter((i) => doc.hospitalIds.includes(i.hospitalId)).map((i) => <HospitalChip key={i.id} hospitalId={i.hospitalId} showVendor={false} />)}
                    </div>
                    {draft.patientId === p.id && <CheckCircle2 className="size-5 text-navy-700" />}
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <RegisterForm onCreated={(p) => { patch({ patientId: p.id }); setMode("search"); setQ(p.name); }} register={(input) => register(input, doc.id)} />
        )}
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader title="Session reason" description="Shown on your work queue and used to pre-fill access requests." icon={<ClipboardList />} />
          <CardBody>
            <Input value={draft.reason} onChange={(e) => patch({ reason: e.target.value })} placeholder="e.g. Chest discomfort — evaluation" />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {["Chest discomfort — evaluation", "Follow-up visit", "New patient intake", "Medication review"].map((r) => (
                <button key={r} onClick={() => patch({ reason: r })} className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:border-navy-300 hover:text-navy-800">{r}</button>
              ))}
            </div>
          </CardBody>
        </Card>
        {selected ? (
          <Card>
            <CardHeader title={selected.name} description={`${selected.id} · selected patient`} icon={<User />} />
            <CardBody className="divide-y divide-slate-100">
              <KV k="Date of birth" v={`${fmtDate(selected.dob)} (${ageFrom(selected.dob)} y)`} />
              <KV k="Sex as recorded" v={selected.sexRecorded} />
              <KV k="Phone" v={val(selected.phone)} />
              <KV k="Preferred language" v={selected.preferredLanguage} />
              <KV k="Insurance" v={selected.insurance ? `${selected.insurance.provider}` : <Unknown />} />
            </CardBody>
          </Card>
        ) : (
          <EmptyState icon={<User />} title="No patient selected" description="Choose a patient from the results or register a new one." />
        )}
      </div>
    </div>
  );
}

function RegisterForm({ register, onCreated }: { register: (i: Omit<Patient, "id" | "createdAt" | "discoverable">) => Patient; onCreated: (p: Patient) => void }) {
  const [f, setF] = useState({ name: "", dob: "", sexRecorded: "Unknown" as Patient["sexRecorded"], genderIdentity: "", phone: "", email: "", address: "", emergencyContact: "", preferredLanguage: "English", reportedBloodGroup: "Unknown", provider: "", plan: "", memberId: "", groupNumber: "" });
  const [err, setErr] = useState<string>();
  const s = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const submit = () => {
    if (f.name.trim().split(" ").length < 2) return setErr("Enter the patient's full name.");
    if (!f.dob) return setErr("Date of birth is required.");
    const u = (v: string) => v.trim() || "Unknown";
    const p = register({
      name: f.name.trim(), dob: f.dob, sexRecorded: f.sexRecorded, genderIdentity: f.genderIdentity.trim() || undefined, phone: u(f.phone), email: u(f.email),
      address: u(f.address), emergencyContact: u(f.emergencyContact), preferredLanguage: u(f.preferredLanguage), reportedBloodGroup: f.reportedBloodGroup,
      insurance: f.provider.trim() ? { provider: f.provider, plan: u(f.plan), memberId: f.memberId, groupNumber: f.groupNumber, coverageStart: "", coverageEnd: "" } : undefined,
    });
    toast("Patient registered", `${p.name} · ${p.id}`);
    onCreated(p);
  };
  return (
    <Card>
      <CardBody className="pt-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Full name *"><Input value={f.name} onChange={s("name")} /></Field>
          <Field label="Date of birth *"><Input type="date" value={f.dob} onChange={s("dob")} /></Field>
          <Field label="Sex as recorded"><Select value={f.sexRecorded} onChange={s("sexRecorded")}>{["Unknown", "Female", "Male", "Intersex"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Gender identity" hint="optional, voluntarily provided"><Input value={f.genderIdentity} onChange={s("genderIdentity")} placeholder="Not provided" /></Field>
          <Field label="Phone"><Input value={f.phone} onChange={s("phone")} placeholder="Unknown" /></Field>
          <Field label="Email"><Input value={f.email} onChange={s("email")} placeholder="Unknown" /></Field>
          <Field label="Address" className="sm:col-span-2"><Input value={f.address} onChange={s("address")} placeholder="Unknown" /></Field>
          <Field label="Emergency contact"><Input value={f.emergencyContact} onChange={s("emergencyContact")} placeholder="Unknown" /></Field>
          <Field label="Preferred language"><Input value={f.preferredLanguage} onChange={s("preferredLanguage")} /></Field>
          <Field label="Blood group" hint="patient-reported, if known"><Select value={f.reportedBloodGroup} onChange={s("reportedBloodGroup")}>{["Unknown", "A+", "A−", "B+", "B−", "AB+", "AB−", "O+", "O−"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Insurance provider"><Input value={f.provider} onChange={s("provider")} placeholder="Unknown" /></Field>
          <Field label="Plan"><Input value={f.plan} onChange={s("plan")} placeholder="Unknown" /></Field>
          <Field label="Member ID"><Input value={f.memberId} onChange={s("memberId")} placeholder="Unknown" /></Field>
        </div>
        <p className="mt-3 text-[11px] text-slate-500">Blank fields are stored as <Unknown /> rather than assumed. Patient-reported blood group is never treated as a verified lab value.</p>
        {err && <p className="mt-2 text-sm text-rose-600">{err}</p>}
        <div className="mt-4 flex justify-end"><Button variant="primary" onClick={submit}><UserPlus /> Register patient</Button></div>
      </CardBody>
    </Card>
  );
}

/* ======================= STEP 2 — RECORDS ======================= */
export function RecordsStep({ draft, patch, goTo }: StepProps) {
  const doc = useCurrentDoctor()!;
  const patient = useApp((s) => s.patients.find((p) => p.id === draft.patientId));
  const hospitals = useApp((s) => s.hospitals);
  const connections = useApp((s) => s.connections);
  const identities = useApp((s) => s.identities);
  const summary = usePatientSummary(patient);
  if (!patient || !summary) return null;
  const byCat = summary.records.reduce<Record<string, number>>((m, r) => ({ ...m, [r.category]: (m[r.category] ?? 0) + 1 }), {});

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold text-slate-900">Retrieve existing medical records</h3>
        <p className="text-sm text-slate-500">Connected organizations and what you are currently permitted to see for {patient.name}.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {hospitals.map((h) => {
          const conn = connections.find((c) => c.hospitalId === h.id)!;
          const home = doc.hospitalIds.includes(h.id);
          const hasIdentity = identities.some((i) => i.patientId === patient.id && i.hospitalId === h.id);
          const locked = summary.locked.find((l) => l.hospitalId === h.id);
          const count = summary.records.filter((r) => r.sourceHospitalId === h.id).length;
          const selectable = !!locked;
          const checked = draft.requestedSources.includes(h.id);
          return (
            <div key={h.id} className={cn("rounded-xl border bg-white p-4", checked ? "border-navy-400 ring-2 ring-navy-100" : "border-slate-200")}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-900"><Building2 className="size-4 text-slate-400" />{h.name}</p>
                  <p className="text-xs text-slate-500">{h.vendor} · {conn.label}</p>
                </div>
                <span className={cn("mt-1 size-2 rounded-full", conn.status === "connected" ? "bg-emerald-500" : conn.status === "paused" ? "bg-slate-400" : "bg-amber-500")} title={conn.status} />
              </div>
              <div className="mt-3">
                {home && hasIdentity ? (
                  <Badge tone="green"><ShieldCheck />Your organization · {count} records accessible</Badge>
                ) : locked ? (
                  locked.grantedCategories.length ? (
                    <Badge tone="green"><ShieldCheck />Access active · {count} records</Badge>
                  ) : (
                    <Badge tone="amber"><Lock />Linked record found · patient approval required</Badge>
                  )
                ) : (
                  <Badge tone="slate"><CircleSlash />No discoverable linked record</Badge>
                )}
              </div>
              {locked && !locked.grantedCategories.length && <p className="mt-2 text-xs text-slate-500">{patient.name} allows treating clinicians to see that a record exists here. Contents stay hidden until the patient approves.</p>}
              {selectable && (
                <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm font-medium text-navy-800">
                  <input type="checkbox" className="accent-navy-700" checked={checked} onChange={(e) => patch({ requestedSources: e.target.checked ? [...draft.requestedSources, h.id] : draft.requestedSources.filter((x) => x !== h.id) })} />
                  Request records from {h.shortName}
                </label>
              )}
            </div>
          );
        })}
      </div>

      <Card>
        <CardHeader title="Currently accessible information" description="Counts reflect only records you're permitted to see." icon={<Database />} />
        <CardBody>
          {Object.keys(byCat).length ? (
            <div className="flex flex-wrap gap-2">
              {Object.entries(byCat).map(([c, n]) => <Badge key={c} tone="navy">{CATEGORY_LABELS[c as Category]} · {n}</Badge>)}
            </div>
          ) : <p className="text-sm text-slate-500">No records accessible yet.</p>}
        </CardBody>
      </Card>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => goTo?.(3)}>Continue without external records</Button>
        <Button variant="primary" disabled={!draft.requestedSources.length && !draft.requestId} onClick={() => goTo?.(2)}><Send /> {draft.requestId ? "View access request" : "Prepare access request"}</Button>
      </div>
    </div>
  );
}

/* ======================= STEP 3 — ACCESS ======================= */
const PURPOSES = ["Treatment — evaluation of current symptoms", "Continuity of care", "Medication reconciliation", "Pre-procedure assessment"];
const ALL_CATS: Category[] = ["medication", "allergy", "condition", "lab", "imaging", "encounter", "bloodGroup", "vitals", "immunization", "procedure", "familyHistory"];

export function AccessStep({ draft, patch, goTo }: StepProps) {
  const doc = useCurrentDoctor()!;
  const patient = useApp((s) => s.patients.find((p) => p.id === draft.patientId))!;
  const hospitals = useApp((s) => s.hospitals);
  const create = useApp((s) => s.createAccessRequest);
  const summary = usePatientSummary(patient);
  const lockable = summary?.locked.map((l) => l.hospitalId) ?? [];
  const [purpose, setPurpose] = useState(PURPOSES[0]);
  const [customPurpose, setCustomPurpose] = useState("");
  const [reason, setReason] = useState(draft.reason ? `${draft.reason}. Patient reports chest discomfort and previous cardiac testing at Valley Medical.`.replace(/^Chest discomfort — evaluation\. /, "") : "");
  const [cats, setCats] = useState<Category[]>(["medication", "allergy", "condition", "lab", "imaging", "encounter", "bloodGroup", "vitals"]);
  const [sources, setSources] = useState<string[]>(draft.requestedSources.length ? draft.requestedSources : lockable);
  const [duration, setDuration] = useState(72);
  const myHospital = hospitals.find((h) => h.id === doc.primaryHospitalId)!;

  if (draft.requestId) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <h3 className="text-base font-semibold text-slate-900">Patient access request</h3>
        <AccessCodePanel requestId={draft.requestId} onActivated={() => {}} />
        <div className="flex justify-end"><Button variant="primary" onClick={() => goTo?.(3)}>Continue to intake</Button></div>
      </div>
    );
  }

  if (!lockable.length) {
    return (
      <div className="mx-auto max-w-xl">
        <EmptyState icon={<Lock />} title="No external sources need approval" description="All accessible information is already available, or the patient has no discoverable records elsewhere." action={<Button onClick={() => goTo?.(3)}>Continue to intake</Button>} />
      </div>
    );
  }

  const finalPurpose = purpose === "__custom" ? customPurpose : purpose;
  const srcNames = sources.map((s) => hospitals.find((h) => h.id === s)?.name).join(" and ");
  const durLabel = duration < 48 ? `${duration} hours` : `${Math.round(duration / 24)} days`;
  const preview = `${doc.name} (${doc.department}, ${myHospital.name}) is asking to see your ${cats.map((c) => CATEGORY_PLAIN[c].toLowerCase()).join(", ")} from ${srcNames || "—"} for ${durLabel}.\n\nWhy: ${finalPurpose || "—"}. ${reason}\n\nNothing is shared unless you approve. You can deny, ask a question, or revoke access later.`;

  const send = () => {
    const r = create({
      patientId: patient.id, doctorId: doc.id, hospitalId: doc.primaryHospitalId, department: doc.department, purpose: finalPurpose,
      encounterReason: reason, categories: cats, sourceHospitalIds: sources, durationHours: duration,
    });
    patch({ requestId: r.id });
    toast("Access request sent", `${patient.name} will see it in the patient app.`, "info");
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
      <div className="space-y-4">
        <h3 className="text-base font-semibold text-slate-900">Request access from the patient</h3>
        <Field label="Purpose of access">
          <Select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            {PURPOSES.map((p) => <option key={p}>{p}</option>)}
            <option value="__custom">Other — write a purpose</option>
          </Select>
        </Field>
        {purpose === "__custom" && <Input value={customPurpose} onChange={(e) => setCustomPurpose(e.target.value)} placeholder="Describe the purpose" />}
        <Field label="Encounter reason (shown to the patient)"><Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-600">Source hospitals</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {lockable.map((h) => (
              <Checkbox key={h} checked={sources.includes(h)} onChange={(v) => setSources(v ? [...sources, h] : sources.filter((x) => x !== h))} label={hospitals.find((x) => x.id === h)?.name} description={hospitals.find((x) => x.id === h)?.vendor + " (mock adapter)"} />
            ))}
          </div>
        </div>
        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-600">Requested categories — request only what you need</p>
          <div className="flex flex-wrap gap-1.5">
            {ALL_CATS.map((c) => {
              const on = cats.includes(c);
              return (
                <button key={c} onClick={() => setCats(on ? cats.filter((x) => x !== c) : [...cats, c])} className={cn("rounded-full border px-3 py-1 text-xs font-medium", on ? "border-navy-300 bg-navy-50 text-navy-800" : "border-slate-200 bg-white text-slate-500")}>
                  {on && "✓ "}{CATEGORY_PLAIN[c]}
                </button>
              );
            })}
          </div>
        </div>
        <Field label="Access duration">
          <Select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
            <option value={24}>24 hours</option>
            <option value={72}>72 hours</option>
            <option value={168}>7 days</option>
            <option value={720}>30 days</option>
          </Select>
        </Field>
      </div>
      <div className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">What {patient.name.split(" ")[0]} will see</p>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card">
          <p className="text-sm font-semibold text-slate-900">Access request from {doc.name}</p>
          <p className="text-xs text-slate-500">{myHospital.name} · {doc.department}</p>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-700">{preview}</p>
        </div>
        <Callout tone="blue" icon={<Info />}>Before approval you can see only that a linked record exists — not its contents. A patient OTP is an additional consent workflow, not a replacement for disclosure rules or emergency-access procedures.</Callout>
        <Button variant="primary" size="lg" className="w-full" disabled={!cats.length || !sources.length || !finalPurpose.trim() || !reason.trim()} onClick={send}><Send /> Send request to patient</Button>
      </div>
    </div>
  );
}

/* ======================= STEP 4 — INTAKE ======================= */
const VITALS: [string, string, string][] = [["bloodPressure", "Blood pressure", "e.g. 142/90 mmHg"], ["heartRate", "Heart rate", "bpm"], ["temperature", "Temperature", "°C"], ["spo2", "Oxygen saturation", "%"], ["height", "Height", "cm"], ["weight", "Weight", "kg"]];
const HISTORY_CATS: Category[] = ["condition", "allergy", "medication", "lab", "imaging", "procedure", "encounter", "immunization", "familyHistory"];

export function IntakeStep({ draft, patch }: StepProps) {
  const doc = useCurrentDoctor()!;
  const patient = useApp((s) => s.patients.find((p) => p.id === draft.patientId))!;
  const summary = usePatientSummary(patient)!;
  const latestVitals = summary.records.filter((r) => r.category === "vitals").sort((a, b) => b.recordedAt - a.recordedAt)[0];
  const [rep, setRep] = useState({ symptoms: "", duration: "", severity: "", lifestyle: "", concerns: "", statements: "" });
  const addReported = () => {
    const items: ReportedItem[] = (
      [["Symptom", rep.symptoms], ["Duration", rep.duration], ["Severity", rep.severity && `${rep.severity}/10`], ["Lifestyle", rep.lifestyle], ["Current concern", rep.concerns], ["Patient statement", rep.statements]] as [string, string][]
    ).filter(([, v]) => v && v.trim()).map(([label, value]) => ({ id: uid("ri"), label, value: value.trim(), source: "patient-reported", status: "accepted", at: Date.now() }));
    if (!items.length) return;
    patch({ reported: [...draft.reported, ...items] });
    setRep({ symptoms: "", duration: "", severity: "", lifestyle: "", concerns: "", statements: "" });
  };
  const age = ageFrom(patient.dob);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">Patient intake record</h3>
        <div className="flex flex-wrap gap-1.5"><VerificationChip v="verified-lab" /><VerificationChip v="imported" /><VerificationChip v="patient-reported" /><VerificationChip v="doctor-entered" /><VerificationChip v="ai-draft" /></div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Demographics" icon={<User />} description="From the EHR Bridge patient profile" />
          <CardBody className="divide-y divide-slate-100">
            <KV k="Name" v={patient.name} />
            <KV k="Age / date of birth" v={`${age} y · ${fmtDate(patient.dob)}`} />
            <KV k="Sex as recorded" v={patient.sexRecorded} />
            {patient.genderIdentity && <KV k="Gender identity" v={patient.genderIdentity} />}
            <KV k="Phone" v={val(patient.phone)} />
            <KV k="Email" v={val(patient.email)} />
            <KV k="Address" v={val(patient.address)} />
            <KV k="Emergency contact" v={val(patient.emergencyContact)} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Clinical characteristics" icon={<HeartPulse />} description="Today's measurements are clinician-entered" />
          <CardBody>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-2.5">
              <span className="text-sm text-slate-600">Blood type & Rh</span>
              {summary.bloodGroupSource ? (
                <span className="flex items-center gap-2"><span className="text-sm font-semibold">{summary.bloodGroup}</span><VerificationChip v="verified-lab" /><HospitalChip hospitalId={summary.bloodGroupSource.sourceHospitalId} showVendor={false} /></span>
              ) : patient.reportedBloodGroup !== "Unknown" ? (
                <span className="flex items-center gap-2"><span className="text-sm font-semibold">{patient.reportedBloodGroup}</span><VerificationChip v="patient-reported" /></span>
              ) : (
                <span className="flex items-center gap-2"><Unknown /><span className="text-[11px] text-slate-500">No verified result accessible</span></span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              {VITALS.map(([k, label, ph]) => (
                <Field key={k} label={label} hint={latestVitals?.data[k] ? `last: ${latestVitals.data[k]}` : undefined}>
                  <Input value={draft.vitals[k] ?? ""} placeholder={ph} onChange={(e) => patch({ vitals: { ...draft.vitals, [k]: e.target.value } })} />
                </Field>
              ))}
            </div>
            {latestVitals && <p className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-slate-500">“last” values: {latestVitals.title}, {fmtDate(latestVitals.recordedAt)} · <HospitalChip hospitalId={latestVitals.sourceHospitalId} showVendor={false} /></p>}
          </CardBody>
        </Card>
      </div>

      {summary.discrepancies.map((d) => <DiscrepancyCard key={d.id} d={d} />)}

      <Card>
        <CardHeader title="Medical history" icon={<Stethoscope />} description="Imported and verified records you are permitted to see, with source and date" />
        <CardBody className="space-y-4">
          {HISTORY_CATS.map((c) => {
            const rs = summary.records.filter((r) => r.category === c);
            if (!rs.length) return null;
            return (
              <div key={c}>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{CATEGORY_PLAIN[c]}</p>
                <div className="grid gap-2 md:grid-cols-2">
                  {rs.map((r) => <RecordRow key={r.recordId} r={r} discrepancy={summary.discrepancies.find((d) => d.values.some((v) => v.recordId === r.recordId))} />)}
                </div>
              </div>
            );
          })}
          {!summary.records.length && <p className="text-sm text-slate-500">No accessible history.</p>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Patient-reported information" icon={<User />} description="What the patient tells you. Stored as patient-reported — never as a verified clinical fact." />
        <CardBody>
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Current symptoms"><Input value={rep.symptoms} onChange={(e) => setRep({ ...rep, symptoms: e.target.value })} placeholder="e.g. Chest discomfort" /></Field>
            <Field label="Symptom duration"><Input value={rep.duration} onChange={(e) => setRep({ ...rep, duration: e.target.value })} placeholder="e.g. 3 days" /></Field>
            <Field label="Pain / severity (0–10)"><Input type="number" min={0} max={10} value={rep.severity} onChange={(e) => setRep({ ...rep, severity: e.target.value })} /></Field>
            <Field label="Lifestyle"><Input value={rep.lifestyle} onChange={(e) => setRep({ ...rep, lifestyle: e.target.value })} placeholder="Smoking, alcohol, activity…" /></Field>
            <Field label="Current concerns"><Input value={rep.concerns} onChange={(e) => setRep({ ...rep, concerns: e.target.value })} /></Field>
            <Field label="Additional statements"><Input value={rep.statements} onChange={(e) => setRep({ ...rep, statements: e.target.value })} /></Field>
          </div>
          <div className="mt-3 flex justify-end"><Button variant="outline" size="sm" onClick={addReported}><Plus /> Add to patient-reported section</Button></div>
          <ReportedList draft={draft} patch={patch} />
          <Field label="Clinician notes" className="mt-4"><Textarea rows={2} value={draft.notes} onChange={(e) => patch({ notes: e.target.value })} placeholder={`Notes by ${doc.name}`} /></Field>
        </CardBody>
      </Card>
    </div>
  );
}

export function ReportedList({ draft, patch }: StepProps) {
  const items = draft.reported.filter((r) => r.status !== "rejected");
  if (!items.length) return <p className="mt-3 text-xs text-slate-400">No patient-reported items yet.</p>;
  return (
    <div className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
      {items.map((r) => (
        <div key={r.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
          <span className="w-40 text-xs font-medium text-slate-500">{r.label}</span>
          <span className="flex-1 text-sm text-slate-800">{r.value}</span>
          <ItemSourceChip source={r.source} status={r.status} />
          {r.confirmedBy && <span className="text-[11px] text-slate-400">confirmed by {r.confirmedBy}</span>}
          <button aria-label="Remove" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-rose-600" onClick={() => patch({ reported: draft.reported.filter((x) => x.id !== r.id) })}><Trash2 className="size-3.5" /></button>
        </div>
      ))}
    </div>
  );
}

/* ======================= STEP 5 — VOICE ======================= */
export function VoiceStep({ draft, patch }: StepProps) {
  const doc = useCurrentDoctor()!;
  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <VoiceMemoPanel value={draft.voiceMemo} onChange={(m) => patch({ voiceMemo: m })} doctorName={doc.name} onAcceptFields={(items) => patch({ reported: [...draft.reported, ...items] })} />
      <Card className="h-fit">
        <CardHeader title="Patient-reported section" description="Accepted fields land here, labelled with their origin." icon={<Mic />} />
        <CardBody><ReportedList draft={draft} patch={patch} /></CardBody>
      </Card>
    </div>
  );
}

/* ======================= STEP 6 — QUESTIONS ======================= */
export function QuestionsStep({ draft, patch }: StepProps) {
  const [nq, setNq] = useState<{ text: string; type: QuestionType; options: string }>({ text: "", type: "text", options: "" });
  const answerOf = (id: string) => draft.answers.find((a) => a.questionId === id);
  const setAnswer = (q: IntakeQuestion, value: string) => {
    const existing = answerOf(q.id);
    const answers = existing ? draft.answers.map((a) => (a.questionId === q.id ? { ...a, value } : a)) : [...draft.answers, { questionId: q.id, value, addedToReported: false }];
    const reported = existing?.addedToReported ? draft.reported.map((r) => (r.id === `qa-${q.id}` ? { ...r, value } : r)) : draft.reported;
    patch({ answers, reported });
  };
  const toggleReported = (q: IntakeQuestion, on: boolean) => {
    const a = answerOf(q.id);
    if (!a?.value) return;
    patch({
      answers: draft.answers.map((x) => (x.questionId === q.id ? { ...x, addedToReported: on } : x)),
      reported: on ? [...draft.reported, { id: `qa-${q.id}`, label: q.text, value: a.value, source: "patient-reported", status: "accepted", at: Date.now() }] : draft.reported.filter((r) => r.id !== `qa-${q.id}`),
    });
  };
  const addQuestion = () => {
    if (!nq.text.trim()) return;
    const q: IntakeQuestion = { id: uid("q"), text: nq.text.trim(), type: nq.type, options: nq.type === "choice" ? nq.options.split(",").map((o) => o.trim()).filter(Boolean) : undefined };
    patch({ questions: [...draft.questions, q] });
    setNq({ text: "", type: "text", options: "" });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
      <div className="space-y-3">
        <h3 className="text-base font-semibold text-slate-900">Custom intake questions</h3>
        {draft.questions.map((q, i) => {
          const a = answerOf(q.id);
          return (
            <div key={q.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-slate-900">{i + 1}. {q.text}</p>
                <div className="flex items-center gap-1">
                  <Badge tone="slate">{{ text: "Text", yesno: "Yes / No", choice: "Multiple choice", number: "Numeric" }[q.type]}</Badge>
                  <button aria-label="Remove question" className="rounded p-1 text-slate-400 hover:text-rose-600" onClick={() => patch({ questions: draft.questions.filter((x) => x.id !== q.id), answers: draft.answers.filter((x) => x.questionId !== q.id), reported: draft.reported.filter((r) => r.id !== `qa-${q.id}`) })}><Trash2 className="size-3.5" /></button>
                </div>
              </div>
              <div className="mt-2.5">
                {q.type === "yesno" && (
                  <div className="flex gap-2">{["Yes", "No", "Unsure"].map((o) => <Button key={o} size="sm" variant={a?.value === o ? "default" : "outline"} onClick={() => setAnswer(q, o)}>{o}</Button>)}</div>
                )}
                {q.type === "choice" && (
                  <div className="flex flex-wrap gap-2">{q.options?.map((o) => <Button key={o} size="sm" variant={a?.value === o ? "default" : "outline"} onClick={() => setAnswer(q, o)}>{o}</Button>)}</div>
                )}
                {q.type === "text" && <Input value={a?.value ?? ""} onChange={(e) => setAnswer(q, e.target.value)} placeholder="Patient's answer" />}
                {q.type === "number" && <Input type="number" className="max-w-[160px]" value={a?.value ?? ""} onChange={(e) => setAnswer(q, e.target.value)} />}
              </div>
              <label className={cn("mt-2.5 flex items-center gap-2 text-xs", a?.value ? "text-slate-600" : "text-slate-300")}>
                <input type="checkbox" disabled={!a?.value} checked={!!a?.addedToReported} onChange={(e) => toggleReported(q, e.target.checked)} className="accent-navy-700" />
                Add answer to patient-reported section
              </label>
            </div>
          );
        })}
      </div>
      <div className="space-y-4">
        <Card>
          <CardHeader title="Add a question" icon={<ListChecks />} />
          <CardBody className="space-y-3">
            <Field label="Question"><Input value={nq.text} onChange={(e) => setNq({ ...nq, text: e.target.value })} placeholder="e.g. Does the discomfort occur with exertion?" /></Field>
            <Field label="Response type">
              <Select value={nq.type} onChange={(e) => setNq({ ...nq, type: e.target.value as QuestionType })}>
                <option value="text">Text</option><option value="yesno">Yes / No</option><option value="choice">Multiple choice</option><option value="number">Numeric</option>
              </Select>
            </Field>
            {nq.type === "choice" && <Field label="Options" hint="comma-separated"><Input value={nq.options} onChange={(e) => setNq({ ...nq, options: e.target.value })} placeholder="At rest, With exertion, Both" /></Field>}
            <Button variant="outline" className="w-full" onClick={addQuestion} disabled={!nq.text.trim()}><Plus /> Add question</Button>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Patient-reported section" icon={<User />} />
          <CardBody><ReportedList draft={draft} patch={patch} /></CardBody>
        </Card>
      </div>
    </div>
  );
}

/* ======================= STEP 7 — REVIEW ======================= */
export function ReviewStep({ draft, patch, goTo }: StepProps) {
  const patient = useApp((s) => s.patients.find((p) => p.id === draft.patientId))!;
  const req = useApp((s) => s.requests.find((r) => r.id === draft.requestId));
  const codes = useApp((s) => s.codes);
  const grants = useApp((s) => s.grants);
  const insurance = useApp((s) => s.insurance);
  const summary = usePatientSummary(patient)!;
  const now = useNow(5000);
  const [showIns, setShowIns] = useState(false);
  const ins = insurance.find((i) => i.id === draft.insuranceVerificationId) ?? insurance.filter((i) => i.patientId === patient.id).sort((a, b) => b.checkedAt - a.checkedAt)[0];
  const reqStatus = req ? effectiveRequestStatus(req, codes, grants, now) : undefined;
  const missing = [
    patient.address === "Unknown" && "Address",
    patient.emergencyContact === "Unknown" && "Emergency contact",
    !patient.insurance && "Insurance details",
    !summary.bloodGroupSource && "Verified blood group",
    !summary.records.some((r) => r.category === "allergy") && "Allergy status",
    !draft.vitals.bloodPressure && "Today's blood pressure",
    !draft.reported.some((r) => r.label === "Symptom") && "Current symptoms",
  ].filter(Boolean) as string[];
  const sources = Array.from(new Set(summary.records.map((r) => r.sourceHospitalId)));
  const accepted = draft.reported.filter((r) => r.status === "accepted");
  const edit = (s: number) => <Button size="sm" variant="ghost" onClick={() => goTo?.(s)}><Pencil /> Edit</Button>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">Review session</h3>
        <span className="text-xs text-slate-500">Nothing is written back to any hospital EHR.</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Patient profile" icon={<User />} action={edit(0)} />
          <CardBody className="divide-y divide-slate-100">
            <KV k="Patient" v={`${patient.name} · ${patient.id}`} />
            <KV k="Age / sex" v={`${ageFrom(patient.dob)} y · ${patient.sexRecorded}`} />
            <KV k="Blood group" v={summary.bloodGroup ? <span>{summary.bloodGroup} <span className="text-[11px] text-emerald-700">(verified lab)</span></span> : <Unknown />} />
            <KV k="Session reason" v={draft.reason || <Unknown />} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Imported records & sources" icon={<Database />} action={edit(1)} />
          <CardBody>
            <p className="text-2xl font-semibold text-slate-900">{summary.records.length}<span className="ml-1 text-sm font-normal text-slate-500">records accessible</span></p>
            <div className="mt-2 flex flex-wrap gap-1.5">{sources.map((s) => <HospitalChip key={s} hospitalId={s} />)}</div>
            {req && reqStatus && <div className="mt-3 flex items-center gap-2 text-xs text-slate-600">External access: <RequestStatusBadge status={reqStatus} /></div>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Insurance verification" icon={<BadgeDollarSign />} action={<Button size="sm" variant="ghost" onClick={() => setShowIns((s) => !s)}>{showIns ? "Hide" : "Check"}</Button>} />
          <CardBody>
            {ins ? (
              <div className="space-y-1.5 text-sm">
                <p className="flex items-center gap-2">{ins.status === "eligible" ? <Badge tone="green">Appears eligible</Badge> : <Badge tone="red">{ins.status}</Badge>}<Badge tone="amber">Simulated</Badge></p>
                <p className="text-xs text-slate-500">{ins.info.provider} · {ins.info.plan}</p>
                <p className="text-xs text-slate-500">Imaging prior auth: {ins.services.find((s) => s.service.startsWith("Imaging"))?.priorAuth}</p>
              </div>
            ) : (
              <p className="flex items-center gap-2 text-sm text-amber-700"><AlertTriangle className="size-4" /> Not verified yet</p>
            )}
          </CardBody>
        </Card>
      </div>
      {showIns && <Card><CardBody className="pt-5"><InsurancePanel patientId={patient.id} onVerified={(id) => patch({ insuranceVerificationId: id })} /></CardBody></Card>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Patient-reported symptoms & answers" icon={<User />} action={edit(3)} />
          <CardBody>
            {accepted.length ? (
              <div className="divide-y divide-slate-100">
                {accepted.map((r) => (
                  <div key={r.id} className="flex flex-wrap items-center gap-2 py-1.5">
                    <span className="w-40 text-xs text-slate-500">{r.label}</span>
                    <span className="flex-1 text-sm font-medium">{r.value}</span>
                    <ItemSourceChip source={r.source} status={r.status} />
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-slate-500">None recorded.</p>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Voice memo summary" icon={<Mic />} action={edit(4)} />
          <CardBody>
            {draft.voiceMemo?.transcript ? (
              <>
                <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">“{draft.voiceMemo.transcript}”</p>
                <p className="mt-2 text-xs text-slate-500">
                  {draft.voiceMemo.transcriptSource === "sample" ? "Sample transcript (no transcription performed)" : draft.voiceMemo.transcriptSource === "browser-speech" ? "Browser speech recognition" : "Typed by clinician"} ·
                  {" "}{draft.voiceMemo.extracted.filter((f) => f.status === "accepted").length} accepted · {draft.voiceMemo.extracted.filter((f) => f.status === "draft").length} still draft · {draft.voiceMemo.extracted.filter((f) => f.status === "rejected").length} rejected
                </p>
              </>
            ) : <p className="text-sm text-slate-500">No voice memo.</p>}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Clinician-entered" icon={<Stethoscope />} action={edit(3)} />
          <CardBody>
            {Object.entries(draft.vitals).filter(([, v]) => v).length ? (
              <div className="flex flex-wrap gap-2">{Object.entries(draft.vitals).filter(([, v]) => v).map(([k, v]) => <Badge key={k} tone="navy">{VITALS.find((x) => x[0] === k)?.[1]}: {v}</Badge>)}</div>
            ) : <p className="text-sm text-slate-500">No measurements entered today.</p>}
            {draft.notes && <p className="mt-2 text-sm text-slate-700">{draft.notes}</p>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Missing information" icon={<FileWarning />} />
          <CardBody>
            {missing.length ? <div className="flex flex-wrap gap-1.5">{missing.map((m) => <Badge key={m} tone="amber">{m}</Badge>)}</div> : <p className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 className="size-4" /> Nothing obvious missing</p>}
          </CardBody>
        </Card>
      </div>
      {summary.discrepancies.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Discrepancies</p>
          {summary.discrepancies.map((d) => <DiscrepancyCard key={d.id} d={d} />)}
        </div>
      )}
    </div>
  );
}
