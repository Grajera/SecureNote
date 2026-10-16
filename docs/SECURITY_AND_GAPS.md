# Security, limitations and next steps

## Built

- Local CLI and optional desktop window; no network listener.
- Size/duration/audio-track validation and local-only media tool calls.
- Offline Whisper inference, contract checks and sentence reconstruction.
- Automatic importance-based extractive notes with dynamic nonempty sections.
- Local lexical retrieval with timestamped evidence and no-result behavior.
- Per-stage JSONL logs, output inventories/hashes and run summaries.
- Plaintext temporary audio cleanup on ordinary completion/error/cancellation.
- Real synthetic WAV, MP3 and MP4 examples; malformed-adapter and silence tests.

## Simplified or missing compared with Assignment 1

The notes engine is a working extractive replacement for the planned Qwen LLM,
not a mocked LLM response. There are no fake model calls. Whisper base.en
replaces large-v3 for CPU portability. There are no stubbed runtime stages;
future features are absent and marked as planned.

Missing: diarization, verified speaker identities, semantic topic segmentation,
implicit action extraction, local LLM, GPU optimization, cache/TTL, multiuser
access controls, automatic retention enforcement, secure transfer and dedicated
Pi recorder. Transcript retention intentionally differs from Part 1's deletion
plan because this version needs search and traceable note verification. No
original recording is automatically deleted. Format support is broader than
Part 1's WAV/MP3 restriction; limits are 2 GiB/2 hours for video practicality.

## Most fragile parts

ASR mistakes flow into otherwise valid notes. Importance cues miss indirect
commitments and can over-select quoted/hypothetical statements. TF-IDF misses
synonyms and cannot answer a semantic question. Synthetic short single-voice
examples are not evidence of real meeting accuracy. English-only base.en does
not cover arbitrary languages. Audio selection is the first track, and visual
slide content is not read. Stage latency logs are written after a stage ends;
ASR has no hard timeout, progress heartbeat or process isolation yet.

The basic shape checks can reject malformed data but cannot detect plausible
yet wrong ASR text. No accuracy or security certification claim is made.

## Dedicated recorder plan

A Pi Zero 2 W would capture mono audio from a USB microphone to local storage.
The initial deployment should use a deliberate USB/file transfer into the
laptop's input folder, avoiding a network service on the Pi. For network
offload, implement authenticated encrypted transfer with a pinned destination,
checksum/size manifest, acknowledgment before deletion, replay prevention,
storage quotas and a recovery queue. Recorder and transfer are not implemented
or tested by this deliverable; do not claim they run on a Pi.

## What real-user monitoring would need

Run IDs, stage status and timing are a starting point. Add process-level ASR
timeouts, heartbeats, queue age/depth, disk and memory telemetry, per-stage
failure rates, p50/p95 latency by recording length, missing-output alerts and
startup recovery of orphan temporary audio. Monitor model/configuration hashes
and drift in transcription quality using consented labeled test data. Have
humans review missed/incorrect action items, source support and attribution.
Keep operational metrics free of transcript bodies and private query strings.

## Security work before confidential deployment

An approved operating environment still needs encrypted storage, restrictive
ACLs, OS account separation, installation provenance, dependency review,
retention/deletion rules, backups, physical security and recording consent
procedures. Run FFmpeg as a low-privilege process; file-only protocol restrictions
are not a sandbox against malicious decoder inputs. Avoid accepting arbitrary
untrusted media or mounting sensitive directories into a shared service.
If adding an LLM, treat transcript text as untrusted data and keep tools
allowlisted; never let a recording authorize filesystem or network actions.
Do not introduce sensitive content into logs for debugging. A future server
requires authentication, authorization, TLS and tenant isolation before use.
