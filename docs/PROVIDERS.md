# Documentation providers

The documentation workflow separates audio capture, transcription, draft organization, clinician editing, explicit approval, and clinical publication. None of the provider interfaces can approve or save a clinical record. Only the authenticated note-approval endpoint creates the originating hospital’s document and outbox event.

## Default development mode

```dotenv
TRANSCRIPTION_PROVIDER=manual
NOTE_GENERATION_PROVIDER=local
AI_EXTERNAL_ENABLED=false
TRANSCRIPT_RETENTION_DAYS=7
```

Browser `MediaRecorder` captures actual audio after the clinician confirms recording authorization/consent and grants microphone access. The server records consent/start/stop/cancel audit metadata against the authorized patient and user, without audio content. Stop produces a playable Blob; Cancel discards it and stops the microphone tracks. The browser also stops tracks on navigation/unmount. Audio is kept in browser memory and is not uploaded automatically.

Without a transcription provider, the app clearly labels **Manual transcript mode**. Enter or upload a real synthetic test transcript. The app does not pretend to recognize speech, produce a fake recording, or substitute sample text for audio. A request to the unconfigured transcription endpoint returns 503 with the fallback instruction.

The local organizer is deterministic and is labeled **Local transcript organizer (no AI)**. It recognizes explicit Subjective, Objective, Assessment, and Plan headings; absent sections remain empty. Unstructured source text is explicitly marked unclassified. It performs no diagnosis, inference, prescribing, or completion of undocumented findings. Draft generation and draft saving do not change clinical entries.

## Implemented OpenAI adapters

Configuration is server-side only:

```dotenv
TRANSCRIPTION_PROVIDER=openai
NOTE_GENERATION_PROVIDER=openai
AI_EXTERNAL_ENABLED=true
AI_API_KEY=your_server_side_key
AI_BASE_URL=https://api.openai.com/v1
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
NOTE_MODEL=gpt-4.1-mini
```

Restart the local launcher or recreate the backend container after configuration. `.env` is ignored by Git; no `NEXT_PUBLIC_` credential is used. The browser sees provider availability, not the API key. The frontend requires separate authorization before external processing. The server independently enforces recording consent, external-processing consent, the enabled setting, credentials, patient care access, and the active hospital context.

`OpenAITranscriptionProvider` uses the documented [audio transcription API](https://developers.openai.com/api/docs/guides/speech-to-text). It sends the supplied audio bytes with an appropriate filename/content type and reads the returned transcript. HTTP failures, empty transcripts, or oversized text produce a clear failure; no fabricated fallback transcript is returned.

`OpenAINoteGenerationProvider` uses [structured output](https://developers.openai.com/api/docs/guides/structured-outputs) with four arrays of source excerpts. Instructions require exact transcript excerpts, no added clinical facts, no inferred assessments/plans, and empty undocumented sections. The server independently rejects any generated excerpt not present verbatim in the supplied source transcript. It sets `store: false` for the note-generation request. This setting does not by itself establish a provider privacy agreement or compliance status.

Only the consultation transcript is sent for note generation. Other patient-chart data is not automatically included. All configured external provider endpoints must be HTTPS. Authentication failures, provider errors, malformed output, and grounding failures are sanitized; errors do not log or display credentials or source transcript/audio content. Saved drafts remain unapproved when generation fails.

The interfaces `TranscriptionProvider` and `NoteGenerationProvider` are separate from clinical approval/storage. Additional provider adapters can implement the same methods without changing hospital charts or the note-approval boundary.

## Recording and retention boundaries

Raw audio uploads use `POST /api/local/patients/{local_id}/transcriptions` with an audio content type, `X-Recording-Consent: true`, and `X-External-Processing-Consent: true`. Session, CSRF, and workspace headers are still required. Supported types are WebM, Ogg, WAV, MP3, and M4A. `AUDIO_MAX_BYTES` defaults to 15 MiB and is enforced while reading the request stream. Audio is never written to a server file or database; the provider receives only the explicitly authorized request bytes.

The separate raw-transcript field expires after `TRANSCRIPT_RETENTION_DAYS`, default 7. Expired fields are cleared on relevant reads/generation, at application startup, and by a 60-second sweep. Set the value to 0 to avoid persisting that raw-transcript field. The current request can still supply a transcript for draft generation. Edited drafts and approved notes retain their content, which may include source excerpts; transcript expiry does not delete clinical documents, draft text, immutable events, or audit history. A complete deployment retention schedule requires independent policy and operational validation.

Saved unapproved drafts are private to their author in the originating hospital. Approval requires a clinician role, patient authorization, a fresh draft revision, nonempty reviewed content, and explicit confirmation. The approved document preserves author, approval time, source patient and record IDs, clinical date, source version, and history. Repeated approval is idempotent. Approved notes are shared through the existing outbox/review engine; no transcription or model response can directly alter a medication, allergy, diagnosis, vaccination, or receiving hospital chart.

## Verification and limits

Provider request/response handling is covered with controlled HTTP mock transports, including audio bytes and hallucinated-excerpt rejection. Browser tests record with the browser’s fake audio device, exercise manual transcript organization, edit and save a draft, reload it, approve it, and acknowledge the external document in another workspace.

**Live transcription and model calls were not performed because external credentials were unavailable.** Deployment must validate the selected provider/model, consent, agreements, data processing obligations, encryption, access governance, retention, clinical usability, and applicable law before using real consultations. This development implementation is not a HIPAA/compliance certification or a production clinical-signature system.
