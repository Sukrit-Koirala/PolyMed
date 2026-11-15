"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Clock, KeyRound, Loader2, MessageCircleQuestion, ShieldCheck, XCircle, Hourglass, Layers, Send, Smartphone } from "lucide-react";
import { useApp, type ImportSummary } from "@/lib/store";
import { effectiveRequestStatus, useCurrentDoctor, useNow } from "@/lib/hooks";
import { useUI } from "@/lib/ui-store";
import { CATEGORY_PLAIN } from "@/lib/adapters/translation";
import { Button, Callout, Dialog, DialogContent, Input } from "../ui";
import { DemoTag, RequestStatusBadge } from "../chips";
import { countdown, relTime } from "@/lib/utils";
import { toast } from "../toast";

export function AccessCodePanel({ requestId, onActivated, compact }: { requestId: string; onActivated?: (imports: ImportSummary[]) => void; compact?: boolean }) {
  const doc = useCurrentDoctor();
  const req = useApp((s) => s.requests.find((r) => r.id === requestId));
  const codes = useApp((s) => s.codes);
  const grants = useApp((s) => s.grants);
  const hospitals = useApp((s) => s.hospitals);
  const patient = useApp((s) => s.patients.find((p) => p.id === req?.patientId));
  const verify = useApp((s) => s.verifyAccessCode);
  const reply = useApp((s) => s.replyToPatient);
  const now = useNow(1000);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [imports, setImports] = useState<ImportSummary[]>();
  const [replyText, setReplyText] = useState("");

  if (!req || !doc) return null;
  const status = effectiveRequestStatus(req, codes, grants, now);
  const latestCode = codes.filter((c) => c.requestId === req.id).sort((a, b) => b.issuedAt - a.issuedAt)[0];
  const grant = grants.find((g) => g.requestId === req.id);
  const srcNames = req.sourceHospitalIds.map((h) => hospitals.find((x) => x.id === h)?.name).join(", ");

  const submit = async () => {
    setBusy(true);
    setError(undefined);
    const res = await verify(req.id, doc.id, code);
    setBusy(false);
    if (!res.check.ok) {
      setError(res.check.message + (res.check.attemptsLeft !== undefined ? ` ${res.check.attemptsLeft} attempt${res.check.attemptsLeft === 1 ? "" : "s"} left.` : ""));
      return;
    }
    setImports(res.imports);
    toast("Access activated", `Approved scope from ${srcNames} is now available.`);
    onActivated?.(res.imports ?? []);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-slate-800">Request to {patient?.name}</span>
          <RequestStatusBadge status={status} />
        </div>
        <span className="text-xs text-slate-500">Sent {relTime(req.createdAt, now)}</span>
      </div>

      {(status === "pending" || status === "investigating") && (
        <Callout tone="amber" icon={<Clock className="animate-pulse" />} title="Waiting for the patient">
          {patient?.name} will see this request in the EHR Bridge patient app (try switching to the <strong>Sarah Mitchell</strong> account in another tab). Once approved, they will share a 6-digit single-use code with you.
        </Callout>
      )}
      {status === "investigating" && req.patientQuestion && (
        <div className="rounded-lg border border-violet-200 bg-violet-50/60 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-violet-800"><MessageCircleQuestion className="size-3.5" /> Patient question{req.reported ? " · reported for privacy review" : ""}</p>
          <p className="mt-1 text-sm text-slate-800">“{req.patientQuestion}”</p>
          {req.doctorReply ? (
            <p className="mt-2 text-xs text-slate-600"><span className="font-medium">Your reply:</span> {req.doctorReply}</p>
          ) : (
            <div className="mt-2 flex gap-2">
              <Input value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder="Reply to patient…" />
              <Button size="md" variant="outline" disabled={!replyText.trim()} onClick={() => { reply(req.id, replyText.trim()); setReplyText(""); toast("Reply sent to patient"); }}><Send /> Send</Button>
            </div>
          )}
        </div>
      )}

      {status === "approved" && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-2 text-sm font-medium text-blue-900"><Smartphone className="size-4" /> Patient approved — enter the code they share with you</p>
            {latestCode && <span className="tabular text-xs text-blue-700">Code expires in {countdown(latestCode.expiresAt - now)}</span>}
          </div>
          <div className="mt-3 flex gap-2">
            <Input inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="6-digit code" className="h-11 max-w-[200px] text-center font-mono text-lg tracking-[0.4em]" onKeyDown={(e) => e.key === "Enter" && code.length === 6 && submit()} />
            <Button size="lg" variant="primary" disabled={code.length !== 6 || busy} onClick={submit}>
              {busy ? <Loader2 className="animate-spin" /> : <KeyRound />} Verify & activate
            </Button>
          </div>
          {error && <p className="mt-2 flex items-center gap-1.5 text-sm text-rose-700"><XCircle className="size-4" />{error}</p>}
          {!compact && <p className="mt-2 text-[11px] text-blue-800/70">Checked: patient identity, request ID, clinician, hospital, code validity, expiry, single use, attempt limit and approved scope. <DemoTag className="ml-1">Simulated OTP service</DemoTag></p>}
        </div>
      )}

      {status === "denied" && <Callout tone="red" icon={<XCircle />} title="The patient denied this request">No records from {srcNames} are accessible. The denial has been recorded in the audit log. You can continue the session with information you're already permitted to see.</Callout>}
      {status === "expired" && <Callout tone="slate" icon={<Hourglass />} title="Request or code expired">Ask the patient to approve again to issue a new single-use code, or create a new request.</Callout>}
      {status === "revoked" && <Callout tone="slate" icon={<XCircle />} title="Access revoked by the patient">Future access has been withdrawn.</Callout>}

      {status === "active" && (
        <Callout tone="green" icon={<ShieldCheck />} title="Access active">
          Scope: {req.categories.map((c) => CATEGORY_PLAIN[c]).join(", ")} from {srcNames}. {grant && <>Expires {relTime(grant.expiresAt, now)}.</>}
        </Callout>
      )}

      {busy && (
        <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-600">
          <Loader2 className="size-4 animate-spin text-navy-600" /> Verifying code, then retrieving and translating records from {srcNames} via mock adapter…
        </div>
      )}
      <AnimatePresence>
        {imports && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-2">
            {imports.map((i) => {
              const h = hospitals.find((x) => x.id === i.hospitalId);
              return (
                <div key={i.hospitalId} className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 text-sm">
                  {i.failed ? (
                    <p className="text-rose-700">Retrieval from {h?.name} failed: {i.failed}</p>
                  ) : (
                    <>
                      <p className="flex items-center gap-1.5 font-medium text-emerald-900"><CheckCircle2 className="size-4" /> {h?.name}: {i.retrieved} records retrieved & translated</p>
                      <p className="mt-0.5 text-xs text-emerald-800">{i.newVersions} new versions recorded · {i.unchanged} unchanged · no write-back to any source EHR</p>
                      {i.preserved.length > 0 && (
                        <p className="mt-1 flex items-start gap-1.5 text-xs text-amber-800"><Layers className="mt-0.5 size-3.5 shrink-0" /> Preserved — not mapped to destination: {i.preserved.join("; ")}</p>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function CodeEntryDialog() {
  const id = useUI((s) => s.codeEntryRequestId);
  const close = useUI((s) => s.closeCodeEntry);
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && close()}>
      {id && (
        <DialogContent title="Patient access code" description="Enter the single-use code the patient received after approving your request." size="md">
          <div className="p-6"><AccessCodePanel requestId={id} /></div>
        </DialogContent>
      )}
    </Dialog>
  );
}
