# Security and gaps: recorder/processor prototype

## Implemented

A lightweight recorder role imports existing media to emulate capture. It keeps
persistent media/manifest/delivery state, uploads to the processor and marks a
recording delivered only after an exact size/hash/ID receipt. Retries retain the
recording. The receiver authenticates, validates byte count and checksum,
publishes a queued job atomically and runs one local inference worker. Repeated
identical uploads do not create duplicate jobs. Queued jobs survive restarts;
interrupted processing is retried on startup. Logs track capture, transfers,
job states, inference stages, output summaries and timing without content by
default. The previous standalone pipeline remains a diagnostic utility.

Inference, note extraction and search remain local. The portable device role
requires only Python standard-library code; the processor owns FFmpeg and AI
dependencies. Remote HTTP clients and non-loopback plaintext listeners are
refused. HTTPS supports certificate loading/verification and custom trust CAs.
Tokens are read from files, not put directly in command-line arguments.

## Emulated, simplified and missing

Microphone capture is replayed from a file. An optional Linux arecord adapter is
provided but Pi microphone hardware, continuous capture service, power/storage
management and recording indicators are untested/missing. The real transfer
protocol and queue are implemented now, not deferred. CPU Whisper base.en and
extractive notes replace the proposed large ASR/LLM pair. Diarization, verified
speakers, semantic summaries/search, per-device enrollment, key rotation,
retention automation, disk quotas and production server hardening remain work.
Actual remote TLS deployment has not been tested on the user's network.

## Most fragile behavior

Plausible ASR errors and English cue-based importance selection can produce
valid-looking wrong/missing notes. Lexical retrieval misses paraphrases. Short
synthetic single-voice recordings do not establish meeting accuracy. First audio
track only; no slide vision or subtitle ingestion. Existing files, device copies,
received payloads and outputs are intentionally retained for search and review.
Structural/checksum validation cannot establish content accuracy.

The minimal HTTP server has limited denial-of-service protection. A shared
bearer token is not per-device authorization or authenticated physical capture.
Interrupted ASR recovery can leave abandoned result folders. Atomic files and
normal cleanup do not guarantee filesystem durability on power loss. Worker
isolation, inference hard timeouts and progress heartbeats are not implemented.

## Needed before confidential real-user deployment

Use approved encrypted storage and restrictive ACLs on device and processor.
Add protected secret provisioning, individual device credentials, token rotation,
recording consent/indicators, authenticated TLS deployment, retention enforcement,
backups, signed dependency/model provenance review and a low-privilege decoder
sandbox. File-only FFmpeg protocol limits do not sandbox malicious media.
No security certification, secure erasure or plaintext-at-rest protection is
claimed. Use public/synthetic assignment data.

Monitor queue age/depth, upload rejection/authentication failures, retries,
checksum failures, stage failure rates, disk/memory, job heartbeats and p50/p95
latency by audio length. Alert on stalled jobs and orphan staging files. Use
consented labeled meetings to audit missed actions and source support. Do not
put transcript bodies or private search queries into operational metrics.

For later Pi/server placement and commands, see TWO_ROLE_DEPLOYMENT.md.
