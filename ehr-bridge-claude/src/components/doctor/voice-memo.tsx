"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, Pause, Play, Square, Wand2, Check, X, FileText, RotateCcw, AudioLines, Info, Pencil } from "lucide-react";
import type { ExtractedField, ReportedItem, VoiceMemo } from "@/lib/types";
import { extractFields } from "@/lib/services/voice";
import { SAMPLE_TRANSCRIPT } from "@/lib/seed";
import { cn, uid } from "@/lib/utils";
import { Badge, Button, Callout, Input, Textarea } from "../ui";
import { DemoTag } from "../chips";

/* eslint-disable @typescript-eslint/no-explicit-any */
type SR = any;

function getSpeechRecognition(): (new () => SR) | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
}

export function VoiceMemoPanel({ value, onChange, onAcceptFields, doctorName }: {
  value?: VoiceMemo;
  onChange: (m: VoiceMemo) => void;
  onAcceptFields: (items: ReportedItem[]) => void;
  doctorName: string;
}) {
  const memo: VoiceMemo = value ?? { id: uid("vm"), transcript: "", transcriptSource: "manual", durationSec: 0, recordedAt: Date.now(), hadAudio: false, extracted: [] };
  const [state, setState] = useState<"idle" | "recording" | "paused" | "stopped">(memo.hadAudio ? "stopped" : "idle");
  const [elapsed, setElapsed] = useState(memo.durationSec);
  const [audioUrl, setAudioUrl] = useState<string>();
  const [micError, setMicError] = useState<string>();
  const [liveText, setLiveText] = useState("");
  const [useSpeech, setUseSpeech] = useState(true);
  const [editingTranscript, setEditingTranscript] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const srRef = useRef<SR | null>(null);
  const finalText = useRef("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const [levels, setLevels] = useState<number[]>(Array(32).fill(0.1));
  const analyser = useRef<{ ctx: AudioContext; an: AnalyserNode; raf: number } | null>(null);

  const SpeechRec = getSpeechRecognition();
  const canRecord = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";

  useEffect(() => () => cleanup(), []); // eslint-disable-line react-hooks/exhaustive-deps

  function cleanup() {
    if (timer.current) clearInterval(timer.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    try { srRef.current?.stop(); } catch { /* noop */ }
    if (analyser.current) { cancelAnimationFrame(analyser.current.raf); analyser.current.ctx.close().catch(() => {}); analyser.current = null; }
  }

  const update = (patch: Partial<VoiceMemo>) => onChange({ ...memo, ...patch });

  async function start() {
    setMicError(undefined);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const rec = new MediaRecorder(stream);
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = () => {
        const blob = new Blob(chunks.current, { type: rec.mimeType || "audio/webm" });
        setAudioUrl(URL.createObjectURL(blob));
      };
      rec.start(250);
      recRef.current = rec;
      setElapsed(0);
      timer.current = setInterval(() => setElapsed((e) => e + 1), 1000);
      setState("recording");
      // level meter
      const ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(stream);
      const an = ctx.createAnalyser();
      an.fftSize = 64;
      src.connect(an);
      const data = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        an.getByteFrequencyData(data);
        setLevels(Array.from(data).slice(0, 32).map((v) => Math.max(0.08, v / 255)));
        analyser.current!.raf = requestAnimationFrame(tick);
      };
      analyser.current = { ctx, an, raf: requestAnimationFrame(tick) };
      // optional live transcription
      finalText.current = "";
      setLiveText("");
      if (SpeechRec && useSpeech) {
        const sr = new SpeechRec();
        sr.continuous = true;
        sr.interimResults = true;
        sr.lang = "en-US";
        sr.onresult = (ev: any) => {
          let interim = "";
          for (let i = ev.resultIndex; i < ev.results.length; i++) {
            const r = ev.results[i];
            if (r.isFinal) finalText.current += r[0].transcript.trim() + ". ";
            else interim += r[0].transcript;
          }
          setLiveText((finalText.current + interim).replace(/\.\s*\./g, "."));
        };
        sr.onerror = () => {};
        try { sr.start(); srRef.current = sr; } catch { /* noop */ }
      }
    } catch (e) {
      setMicError(e instanceof Error ? `Microphone unavailable: ${e.message}` : "Microphone unavailable.");
    }
  }

  function pause() {
    recRef.current?.pause();
    if (timer.current) clearInterval(timer.current);
    try { srRef.current?.stop(); } catch { /* noop */ }
    setState("paused");
  }
  function resume() {
    recRef.current?.resume();
    timer.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    try { srRef.current?.start(); } catch { /* noop */ }
    setState("recording");
  }
  function stop() {
    recRef.current?.stop();
    cleanup();
    setState("stopped");
    const text = (finalText.current || liveText).trim();
    update({ hadAudio: true, durationSec: elapsed, recordedAt: Date.now(), transcript: text || memo.transcript, transcriptSource: text ? "browser-speech" : memo.transcriptSource });
  }
  function resetAll() {
    cleanup();
    setAudioUrl(undefined);
    setState("idle");
    setElapsed(0);
    setLiveText("");
    onChange({ id: uid("vm"), transcript: "", transcriptSource: "manual", durationSec: 0, recordedAt: Date.now(), hadAudio: false, extracted: [] });
  }

  const runExtraction = () => update({ extracted: extractFields(memo.transcript) });
  const setField = (id: string, patch: Partial<ExtractedField>) => update({ extracted: memo.extracted.map((f) => (f.id === id ? { ...f, ...patch } : f)) });
  const acceptAll = () => {
    const pending = memo.extracted.filter((f) => f.status === "draft");
    update({ extracted: memo.extracted.map((f) => (f.status === "draft" ? { ...f, status: "accepted" } : f)) });
    onAcceptFields(pending.map((f) => toReported(f, doctorName)));
  };
  const acceptOne = (f: ExtractedField) => {
    setField(f.id, { status: "accepted" });
    onAcceptFields([toReported(f, doctorName)]);
  };

  const mm = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  const srcBadge = {
    "browser-speech": <Badge tone="blue"><AudioLines />Transcribed by browser speech recognition</Badge>,
    sample: <Badge tone="amber"><Info />Sample transcript — no transcription was performed</Badge>,
    manual: <Badge tone="slate"><Pencil />Typed / edited by clinician</Badge>,
  }[memo.transcriptSource];

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-navy-900 to-navy-800 p-5 text-white">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Voice memo intake</p>
            <p className="text-xs text-navy-200">Record locally in your browser. Audio never leaves this device{SpeechRec && useSpeech ? " (except the browser's own speech service if live transcription is on)" : ""}.</p>
          </div>
          <div className="tabular rounded-lg bg-white/10 px-3 py-1.5 font-mono text-lg">{mm}</div>
        </div>
        <div className="my-5 flex h-14 items-center justify-center gap-[3px]">
          {levels.map((l, i) => (
            <motion.div key={i} className={cn("w-1.5 rounded-full", state === "recording" ? "bg-[#7fb3ff]" : "bg-white/25")} animate={{ height: state === "recording" ? `${Math.round(l * 100)}%` : "12%" }} transition={{ duration: 0.08 }} />
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {state === "idle" && (
            <Button size="lg" className="bg-rose-500 hover:bg-rose-600" onClick={start} disabled={!canRecord}>
              <Mic /> Start recording
            </Button>
          )}
          {state === "recording" && (
            <>
              <Button size="lg" variant="outline" className="border-white/20 bg-white/10 text-white hover:bg-white/20" onClick={pause}><Pause /> Pause</Button>
              <Button size="lg" className="bg-rose-500 hover:bg-rose-600" onClick={stop}><Square /> Stop</Button>
            </>
          )}
          {state === "paused" && (
            <>
              <Button size="lg" variant="outline" className="border-white/20 bg-white/10 text-white hover:bg-white/20" onClick={resume}><Play /> Resume</Button>
              <Button size="lg" className="bg-rose-500 hover:bg-rose-600" onClick={stop}><Square /> Stop</Button>
            </>
          )}
          {state === "stopped" && (
            <Button size="lg" variant="outline" className="border-white/20 bg-white/10 text-white hover:bg-white/20" onClick={resetAll}><RotateCcw /> Record again</Button>
          )}
        </div>
        {state === "recording" && <p className="mt-3 flex items-center justify-center gap-2 text-xs text-rose-200"><span className="size-2 animate-pulse-dot rounded-full bg-rose-400" /> Recording…</p>}
        {SpeechRec && state === "idle" && (
          <label className="mt-4 flex items-center justify-center gap-2 text-xs text-navy-200">
            <input type="checkbox" checked={useSpeech} onChange={(e) => setUseSpeech(e.target.checked)} className="accent-[#7fb3ff]" />
            Live transcription with the browser's built-in speech recognition (Web Speech API)
          </label>
        )}
        {(state === "recording" || state === "paused") && liveText && <p className="mt-3 rounded-lg bg-white/10 p-3 text-sm text-navy-50">{liveText}</p>}
        {audioUrl && <audio controls src={audioUrl} className="mt-4 w-full" />}
        {!canRecord && <p className="mt-3 text-center text-xs text-amber-200">Audio recording is not supported in this browser. You can type a transcript or load the sample below.</p>}
        {micError && <p className="mt-3 text-center text-xs text-amber-200">{micError}. You can still type a transcript or use the sample.</p>}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-semibold text-slate-900"><FileText className="size-4 text-slate-500" /> Transcript</p>
          <div className="flex flex-wrap items-center gap-2">
            {memo.transcript && srcBadge}
            <Button size="sm" variant="ghost" onClick={() => update({ transcript: SAMPLE_TRANSCRIPT, transcriptSource: "sample", extracted: [] })}>Load sample transcript</Button>
            <Button size="sm" variant="outline" onClick={() => setEditingTranscript((e) => !e)}><Pencil />{editingTranscript ? "Done" : "Edit"}</Button>
          </div>
        </div>
        {editingTranscript || !memo.transcript ? (
          <Textarea className="mt-3 min-h-[90px]" value={memo.transcript} placeholder={state === "stopped" && !memo.transcript ? "No transcription provider is configured and the browser returned no speech. Type what the patient said, or load the sample transcript." : "Transcript will appear here. You can also type it."}
            onChange={(e) => update({ transcript: e.target.value, transcriptSource: "manual" })} />
        ) : (
          <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">{memo.transcript}</p>
        )}
        {memo.transcriptSource === "sample" && (
          <Callout tone="amber" className="mt-3" icon={<Info />}>This is seeded demo text, not a transcription of any recording.</Callout>
        )}
        <div className="mt-3 flex items-center justify-between gap-2">
          <p className="text-[11px] text-slate-500">Extraction runs locally with simple rules (no AI model). Results are drafts until you accept them.</p>
          <Button size="sm" variant="primary" disabled={!memo.transcript.trim()} onClick={runExtraction}><Wand2 /> Extract intake fields</Button>
        </div>
      </div>

      {memo.extracted.length > 0 && (
        <div className="rounded-xl border border-violet-200 bg-violet-50/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-slate-900">Suggested intake fields <DemoTag className="ml-2">Rule-based extraction</DemoTag></p>
            <Button size="sm" variant="success" disabled={!memo.extracted.some((f) => f.status === "draft")} onClick={acceptAll}><Check /> Accept all drafts</Button>
          </div>
          <div className="mt-3 space-y-2">
            {memo.extracted.map((f) => (
              <div key={f.id} className={cn("flex flex-wrap items-center gap-2 rounded-lg border bg-white p-2.5", f.status === "accepted" ? "border-emerald-200" : f.status === "rejected" ? "border-slate-200 opacity-50" : "border-violet-200")}>
                <span className="w-48 shrink-0 text-xs font-medium text-slate-500">{f.label}</span>
                <Input value={f.value} disabled={f.status !== "draft"} onChange={(e) => setField(f.id, { value: e.target.value })} className="h-8 min-w-[160px] flex-1" />
                {f.status === "draft" ? (
                  <>
                    <Badge tone="violet">Draft</Badge>
                    <Button size="sm" variant="outline" onClick={() => acceptOne(f)}><Check className="text-emerald-600" /> Accept</Button>
                    <Button size="sm" variant="ghost" onClick={() => setField(f.id, { status: "rejected" })}><X /> Reject</Button>
                  </>
                ) : f.status === "accepted" ? (
                  <Badge tone="green"><Check />Accepted → patient-reported</Badge>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => setField(f.id, { status: "draft" })}>Undo</Button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function toReported(f: ExtractedField, doctorName: string): ReportedItem {
  return { id: uid("ri"), label: f.label, value: f.value, source: "ai-extracted", status: "accepted", confirmedBy: doctorName, at: Date.now() };
}
