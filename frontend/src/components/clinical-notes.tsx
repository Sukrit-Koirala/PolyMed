'use client';
import { useEffect, useRef, useState } from 'react';
import { Check, FilePenLine, FileText, Loader2, Mic, Plus, Save, ShieldCheck, Square, Upload, WandSparkles, X } from 'lucide-react';
import { api, date, post } from '@/lib/api';
import { Badge, Button, Empty, Modal } from './ui';

const blankSections = () => ({ subjective: '', objective: '', assessment: '', plan: '' });

export default function ClinicalNotes({ patient, user, onChanged, onSource, notify }: any) {
  const [config, setConfig] = useState<any>(null);
  const [drafts, setDrafts] = useState<any[]>([]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<any>(null);
  const [title, setTitle] = useState('Consultation note');
  const [transcript, setTranscript] = useState('');
  const [sections, setSections] = useState<any>(blankSections());
  const [warnings, setWarnings] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [externalConsent, setExternalConsent] = useState(false);
  const [recording, setRecording] = useState(false);
  const [audio, setAudio] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState('');
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approval, setApproval] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const cancelCapture = useRef<(() => void) | null>(null);
  const recordingGeneration = useRef(0);
  const alive = useRef(true);
  const fileInput = useRef<HTMLInputElement>(null);
  const load = () => api(`/local/patients/${encodeURIComponent(patient.id)}/note-drafts`).then(setDrafts);
  useEffect(() => {
    alive.current = true;
    Promise.all([api('/notes/config'), api(`/local/patients/${encodeURIComponent(patient.id)}/note-drafts`)]).then(([c, d]) => { if (alive.current) { setConfig(c); setDrafts(d); } }).catch(e => alive.current && setError(e.message));
    return () => { alive.current = false; recordingGeneration.current += 1; cancelCapture.current?.(); cancelCapture.current = null; };
  }, [patient.id, user.hospital_id]);
  useEffect(() => { if (audio) { const url = URL.createObjectURL(audio); setAudioUrl(url); return () => URL.revokeObjectURL(url); } setAudioUrl(''); }, [audio]);
  useEffect(() => { if (!recording) return; const start = Date.now(); setSeconds(0); const interval = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 500); return () => clearInterval(interval); }, [recording]);
  function openDraft(item?: any) {
    cancelRecording();
    setRecording(false); setAudio(null); setEditing(true); setDraft(item || null); setTitle(item?.title || 'Consultation note'); setTranscript(item?.transcript || ''); setSections(item?.sections || blankSections()); setWarnings(item?.generation_warnings || []); setError(''); setConsent(false); setExternalConsent(false);
  }
  async function startRecording() {
    if (!consent) { setError('Confirm consultation recording consent before starting.'); return; }
    setError('');
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Recording is unavailable in this browser. Use localhost or HTTPS, or enter/upload a transcript.'); return; }
    setBusy('microphone');
    const generation = ++recordingGeneration.current;
    let capturedStream: MediaStream | null = null;
    let media: MediaRecorder | null = null;
    let cancelled = false;
    let auditStarted = false;
    let auditFinished = false;
    const sessionId = crypto.randomUUID();
    const current = () => alive.current && generation === recordingGeneration.current;
    const auditEvent = (action: string) => api(`/local/patients/${encodeURIComponent(patient.id)}/recording-events`, { method: 'POST', headers: { 'X-Workspace-ID': user.hospital_id }, body: JSON.stringify({ recording_id: sessionId, action, consent_confirmed: true }) });
    const finishAudit = (action: 'STOPPED' | 'CANCELLED') => {
      if (!auditStarted || auditFinished) return;
      auditFinished = true;
      auditEvent(action).catch(() => { if (current()) setError('Recording stopped locally, but its final audit update could not be saved.'); });
    };
    const cancel = () => {
      cancelled = true;
      if (media?.state === 'recording') media.stop();
      capturedStream?.getTracks().forEach(track => track.stop());
      finishAudit('CANCELLED');
    };
    cancelCapture.current = cancel;
    try {
      capturedStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!current()) { cancel(); return; }
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      const capture = new MediaRecorder(capturedStream, mime ? { mimeType: mime } : {});
      media = capture;
      const chunks: BlobPart[] = []; let bytes = 0;
      await auditEvent('STARTED');
      auditStarted = true;
      if (!current()) { cancel(); return; }
      capture.ondataavailable = event => { if (event.data.size && !cancelled && current()) { bytes += event.data.size; if (bytes > (config?.max_audio_bytes || 15728640)) { cancel(); setError('Recording reached the configured size limit. Try a shorter recording.'); } else chunks.push(event.data); } };
      capture.onstop = () => {
        capturedStream?.getTracks().forEach(track => track.stop());
        finishAudit(cancelled || !current() ? 'CANCELLED' : 'STOPPED');
        if (!current()) return;
        cancelCapture.current = null; recorder.current = null;
        setRecording(false);
        if (!cancelled && chunks.length) setAudio(new Blob(chunks, { type: capture.mimeType || 'audio/webm' }));
      };
      capture.onerror = () => { cancel(); if (current()) { setRecording(false); setError('The browser could not complete the recording. Enter or upload a transcript instead.'); } };
      recorder.current = capture; setAudio(null); capture.start(1000); setRecording(true);
    } catch (e: any) { cancel(); if (current()) setError(e.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow microphone access in your browser, or enter a transcript.' : e.status ? e.message : 'No microphone recording could be started. Check the device or use a transcript.'); } finally { if (current()) setBusy(''); }
  }
  function cancelRecording() { recordingGeneration.current += 1; cancelCapture.current?.(); cancelCapture.current = null; recorder.current = null; setRecording(false); setAudio(null); setBusy(value => value === 'microphone' ? '' : value); }
  async function transcribe() {
    if (!audio) return; setBusy('transcribing'); setError('');
    try { const response = await api(`/local/patients/${encodeURIComponent(patient.id)}/transcriptions`, { method: 'POST', body: audio, headers: { 'Content-Type': audio.type || 'audio/webm', 'X-Recording-Consent': String(consent), 'X-External-Processing-Consent': String(externalConsent) } }); setTranscript(response.transcript); notify('Recording transcribed. Review the transcript before creating a draft.'); } catch (e: any) { setError(e.message); } finally { setBusy(''); }
  }
  async function persist() {
    const body = { title, transcript, sections };
    const saved = draft ? await api(`/note-drafts/${draft.id}`, { method: 'PUT', body: JSON.stringify({ ...body, expected_revision: draft.revision }) }) : await post(`/local/patients/${encodeURIComponent(patient.id)}/note-drafts`, body);
    setDraft(saved); await load(); return saved;
  }
  async function save() { setBusy('saving'); setError(''); try { await persist(); notify('Draft saved privately. It is not part of the approved clinical record.'); } catch (e: any) { setError(e.message); } finally { setBusy(''); } }
  async function generate() {
    setBusy('generating'); setError('');
    try { const saved = await persist(); const generated = await post(`/note-drafts/${saved.id}/generate`, { expected_revision: saved.revision, external_processing_consent: externalConsent, transcript }); setDraft(generated); setSections(generated.sections); setWarnings(generated.generation_warnings); await load(); } catch (e: any) { setError(e.message); } finally { setBusy(''); }
  }
  async function approve() {
    setBusy('approving'); setError('');
    try { const saved = await persist(); await post(`/note-drafts/${saved.id}/approve`, { expected_revision: saved.revision, approval_confirmed: approval }); setApprovalOpen(false); setEditing(false); cancelRecording(); await load(); try { await post('/sync'); notify('Note approved and saved to this patient’s hospital chart. Authorized hospitals can review the published note.'); } catch { notify('Note approved in your hospital chart. Sharing is delayed; try Sync updates.'); } onChanged(); } catch (e: any) { setError(e.message); setApprovalOpen(false); } finally { setBusy(''); }
  }
  const approved = patient.records.filter((record: any) => record.category === 'note' && record.status !== 'WITHDRAWN' && record.fields.Status !== 'entered-in-error');
  const unapproved = drafts.filter(item => item.status === 'DRAFT');
  return <div className="notes-workspace"><div className="section-heading"><div><h2>Clinical notes</h2><p>Capture the consultation. Review every word. Approve when ready.</p></div>{user.role === 'clinician' && <Button disabled={!!busy && busy !== "microphone"} onClick={() => openDraft()}><Plus size={16} />New note</Button>}</div>{error && <div className="alert error" role="alert">{error}</div>}{!editing ? <>{!!unapproved.length && <section className="panel"><div className="panel-heading"><h3>Your private drafts</h3><Badge>{unapproved.length}</Badge></div>{unapproved.map(item => <button className="draft-row" key={item.id} onClick={() => openDraft(item)}><FilePenLine size={19} /><div><strong>{item.title}</strong><p>Saved {date(item.updated_at, true)} · Not approved or shared</p></div><Badge tone="amber">Draft</Badge></button>)}</section>}<section className="panel"><div className="panel-heading"><h3>Approved notes</h3><span className="small muted">Original source preserved</span></div>{!approved.length ? <Empty title="No approved notes yet">Drafts appear in the clinical chart and timeline only after explicit clinician approval.</Empty> : approved.map((record: any) => <article className="approved-note" key={record.id}><div className="between"><div><h3>{record.fields['Clinical concept']}</h3><p>{record.source.name} · {date(record.fields['Approved at'], true)}</p></div><Button variant="ghost" size="sm" onClick={() => onSource(record.id)}>View details</Button></div><p className="note-preview">{record.fields.Subjective || record.fields.Assessment || record.fields.Plan || 'Approved consultation document'}</p></article>)}</section></> : <><div className="draft-context"><div><Badge tone="amber">Unapproved draft</Badge><span>{patient.name} · {patient.id}</span></div><Button variant="ghost" size="sm" disabled={!!busy && busy !== "microphone"} onClick={() => { cancelRecording(); setEditing(false); }}>Back to notes</Button></div><label className="note-title-label">Note title<input disabled={!!busy} maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label><div className="note-authoring-grid"><section className="panel capture-panel"><div className="panel-heading"><h3>1. Capture the consultation</h3><Mic size={18} /></div><div className="capture-body"><label className="check-label"><input type="checkbox" checked={consent} onChange={e => { setConsent(e.target.checked); if (!e.target.checked) cancelRecording(); }} /><span>I confirm authorization and the required consent to record this consultation.</span></label><div className={`recording-console ${recording ? 'is-recording' : ''}`}><div className="microphone-orb"><Mic size={26} /></div><strong>{recording ? 'Recording in progress' : audio ? 'Recording captured' : 'Ready when you are'}</strong><span>{recording ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : 'Audio stays in this browser until you choose to transcribe it.'}</span><div className="inline">{!recording ? <Button disabled={!consent || !!busy} onClick={startRecording}><Mic size={15} />Start recording</Button> : <><Button onClick={() => recorder.current?.stop()}><Square size={14} />Stop recording</Button><Button variant="outline" onClick={cancelRecording}><X size={14} />Cancel recording</Button></>}</div></div>{audio && <div className="audio-preview"><audio controls src={audioUrl || undefined} /><div className="inline"><Button size="sm" variant="outline" disabled={!config?.transcription_available || !externalConsent || !!busy || !consent} busy={busy === 'transcribing'} onClick={transcribe}>Transcribe recording</Button><Button size="sm" variant="ghost" onClick={cancelRecording}>Discard audio</Button></div></div>}{!config?.transcription_available && <div className="fallback-notice"><strong>Manual transcript mode</strong><p>No transcription service is configured. Enter or upload a test transcript below. A recording is never replaced with made-up text.</p></div>}{config?.external_processing_enabled && <label className="check-label"><input type="checkbox" checked={externalConsent} onChange={e => setExternalConsent(e.target.checked)} /><span>I authorize sending this synthetic consultation to the configured external transcription or note provider.</span></label>}<label>Consultation transcript<textarea aria-label="Consultation transcript" disabled={!!busy} rows={9} maxLength={60000} value={transcript} onChange={e => setTranscript(e.target.value)} placeholder="Enter the actual source transcript. You can use Subjective:, Objective:, Assessment:, and Plan: headings for the local organizer." /></label><input ref={fileInput} hidden type="file" accept=".txt,text/plain" aria-label="Upload test transcript" onChange={async e => { const file = e.target.files?.[0]; if (!file) return; if (file.size > 100000) { setError('Test transcript must be smaller than 100 KB.'); return; } const text = await file.text(); if (text.length > 60000) { setError('Transcript exceeds 60,000 characters.'); return; } setTranscript(text); e.target.value = ''; }} /><div className="between capture-actions"><Button variant="ghost" size="sm" onClick={() => fileInput.current?.click()}><Upload size={15} />Upload test transcript</Button><Button variant="outline" size="sm" busy={busy === 'generating'} disabled={!transcript.trim() || !!busy || recording || (config?.note_generation_provider === 'openai' && !externalConsent)} onClick={generate}><WandSparkles size={15} />{config?.note_generation_provider === 'local' ? 'Organize draft' : 'Generate draft'}</Button></div><p className="retention-note">{config?.generation_label}. Audio is not stored on the server. {config?.transcript_retention_days === 0 ? 'Transcript persistence is disabled.' : `Saved transcripts expire after ${config?.transcript_retention_days ?? 7} days.`}</p></div></section><section className="panel soap-panel"><div className="panel-heading"><h3>2. Review and edit the draft</h3><FileText size={18} /></div><div className="soap-body">{warnings.length > 0 && <div className="draft-notices">{warnings.map((warning, i) => <p key={i}>{warning}</p>)}</div>}{['subjective', 'objective', 'assessment', 'plan'].map(section => <label key={section}><span className="soap-label"><span aria-hidden="true">{section[0].toUpperCase()}</span>{section[0].toUpperCase() + section.slice(1)}</span><textarea disabled={!!busy} aria-label={section[0].toUpperCase() + section.slice(1)} rows={4} value={sections[section]} maxLength={60000} placeholder="Not documented. Add only supported information after review." onChange={e => setSections({ ...sections, [section]: e.target.value })} /></label>)}</div></section></div><div className="note-approval-bar"><div><ShieldCheck size={21} /><div><strong>Your approval is required</strong><p>Saving a draft does not finalize, share, prescribe, or change structured clinical entries.</p></div></div><div className="inline"><Button variant="outline" busy={busy === 'saving'} disabled={!!busy || recording || !title.trim()} onClick={save}><Save size={16} />Save draft</Button><Button disabled={!!busy || recording || !Object.values(sections).some((text: any) => text.trim())} onClick={() => { setApproval(false); setApprovalOpen(true); }}><Check size={16} />Approve note</Button></div></div></>}<Modal open={approvalOpen} onClose={() => setApprovalOpen(false)} title="Approve this clinical note" description={`Reviewing for ${patient.name}, ${patient.id}, at ${user.hospital.name}.`}><p className="muted">This saves the reviewed note to this development hospital chart and makes it eligible for authorized sharing. It does not modify medications, allergies, diagnoses, or any external EHR.</p><label className="check-label approval-attestation"><input type="checkbox" checked={approval} onChange={e => setApproval(e.target.checked)} /><span>I have reviewed and corrected every section and explicitly approve this note as {user.name}.</span></label><div className="modal-footer"><Button variant="outline" onClick={() => setApprovalOpen(false)}>Continue editing</Button><Button busy={busy === 'approving'} disabled={!approval} onClick={approve}>Approve and save note</Button></div></Modal></div>;
}
