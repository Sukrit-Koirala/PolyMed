"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, Save, PlayCircle } from "lucide-react";
import { useApp } from "@/lib/store";
import { useCurrentDoctor } from "@/lib/hooks";
import { useUI } from "@/lib/ui-store";
import { DEFAULT_QUESTIONS } from "@/lib/seed";
import type { IntakeAnswer, IntakeQuestion, ReportedItem, VoiceMemo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button, Dialog, DialogContent } from "../../ui";
import { toast } from "../../toast";
import { PatientStep, RecordsStep, AccessStep, IntakeStep, VoiceStep, QuestionsStep, ReviewStep } from "./steps";

export interface Draft {
  patientId?: string;
  reason: string;
  requestId?: string;
  requestedSources: string[];
  vitals: Record<string, string>;
  reported: ReportedItem[];
  voiceMemo?: VoiceMemo;
  questions: IntakeQuestion[];
  answers: IntakeAnswer[];
  notes: string;
  insuranceVerificationId?: string;
}

const STEPS = ["Patient", "Records", "Access", "Intake", "Voice memo", "Questions", "Review"] as const;

const freshDraft = (patientId?: string): Draft => ({
  patientId, reason: "", requestedSources: [], vitals: {}, reported: [], questions: DEFAULT_QUESTIONS.map((q) => ({ ...q })), answers: [], notes: "",
});

export function NewSessionModal() {
  const open = useUI((s) => s.newSessionOpen);
  const presetPatient = useUI((s) => s.newSessionPatientId);
  const resumeId = useUI((s) => s.resumeSessionId);
  const close = useUI((s) => s.closeNewSession);
  const doc = useCurrentDoctor();
  const sessions = useApp((s) => s.sessions);
  const saveSession = useApp((s) => s.saveSession);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(freshDraft());

  useEffect(() => {
    if (!open) return;
    if (resumeId) {
      const s = sessions.find((x) => x.id === resumeId);
      if (s) {
        setDraft({ patientId: s.patientId, reason: s.reason, requestId: s.accessRequestId, requestedSources: [], vitals: s.vitals, reported: s.reported, voiceMemo: s.voiceMemo, questions: s.questions.length ? s.questions : DEFAULT_QUESTIONS.map((q) => ({ ...q })), answers: s.answers, notes: s.notes, insuranceVerificationId: s.insuranceVerificationId });
        setStep(3);
        return;
      }
    }
    setDraft(freshDraft(presetPatient));
    setStep(presetPatient ? 1 : 0);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!doc) return null;
  const patch = (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p }));
  const canAdvance = step === 0 ? !!draft.patientId && draft.reason.trim().length > 2 : true;

  const finish = (status: "draft" | "active") => {
    if (!draft.patientId) return;
    const s = saveSession({
      patientId: draft.patientId, doctorId: doc.id, reason: draft.reason.trim() || "Encounter", status, accessRequestId: draft.requestId,
      vitals: draft.vitals, reported: draft.reported, voiceMemo: draft.voiceMemo, questions: draft.questions, answers: draft.answers,
      notes: draft.notes, insuranceVerificationId: draft.insuranceVerificationId, existingSessionId: resumeId,
    });
    toast(status === "draft" ? "Draft saved" : "Session started", status === "draft" ? "Resume it any time from Sessions & Tasks." : `${s.reason} — tasks added to your queue.`);
    close();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent size="full" title={resumeId ? "Resume session" : "New session"} description="Find the patient, retrieve authorized records, capture intake and review — without leaving this window." className="h-[92vh]">
        <div className="flex h-full min-h-0 flex-col">
          <div className="border-b border-slate-100 bg-slate-50/60 px-6 py-3">
            <ol className="flex gap-1 overflow-x-auto">
              {STEPS.map((label, i) => {
                const done = i < step;
                const enabled = i === 0 || !!draft.patientId;
                return (
                  <li key={label} className="flex shrink-0 items-center">
                    <button disabled={!enabled} onClick={() => setStep(i)} className={cn("flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors", i === step ? "bg-white text-navy-900 shadow-sm ring-1 ring-slate-200" : enabled ? "text-slate-600 hover:bg-white/70" : "text-slate-300")}>
                      <span className={cn("flex size-5 items-center justify-center rounded-full text-[10px]", i === step ? "bg-navy-800 text-white" : done ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-600")}>
                        {done ? <Check className="size-3" /> : i + 1}
                      </span>
                      {label}
                    </button>
                    {i < STEPS.length - 1 && <span className="mx-1 h-px w-4 bg-slate-200" />}
                  </li>
                );
              })}
            </ol>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50/30">
            <AnimatePresence mode="wait">
              <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.16 }} className="p-6">
                {step === 0 && <PatientStep draft={draft} patch={patch} />}
                {step === 1 && <RecordsStep draft={draft} patch={patch} goTo={setStep} />}
                {step === 2 && <AccessStep draft={draft} patch={patch} goTo={setStep} />}
                {step === 3 && <IntakeStep draft={draft} patch={patch} />}
                {step === 4 && <VoiceStep draft={draft} patch={patch} />}
                {step === 5 && <QuestionsStep draft={draft} patch={patch} />}
                {step === 6 && <ReviewStep draft={draft} patch={patch} goTo={setStep} />}
              </motion.div>
            </AnimatePresence>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-white px-6 py-3">
            <div className="flex gap-2">
              <Button variant="ghost" onClick={close}>Cancel</Button>
              {step > 0 && <Button variant="outline" onClick={() => setStep(step - 1)}><ArrowLeft /> Back</Button>}
            </div>
            <div className="flex gap-2">
              {draft.patientId && <Button variant="outline" onClick={() => finish("draft")}><Save /> Save Draft</Button>}
              {step < STEPS.length - 1 ? (
                <Button variant="primary" disabled={!canAdvance} onClick={() => setStep(step + 1)}>
                  {step === 0 && !canAdvance ? (draft.patientId ? "Enter a session reason" : "Select a patient") : <>Next: {STEPS[step + 1]} <ArrowRight /></>}
                </Button>
              ) : (
                <Button variant="success" onClick={() => finish("active")}><PlayCircle /> {resumeId ? "Save & mark active" : "Start Session"}</Button>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
