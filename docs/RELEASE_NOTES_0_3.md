# SecureNote 0.3 - recording review workspace

The default entry point is review.py, also launched by Start-SecureNote.cmd and
desktop.py. Runtime needs no Node/npm or frontend build: locally served
HTML/CSS/JavaScript uses the existing Python recorder/processor.

## Improvements

- Recording library, import progress, title search, job status and review marks.
- Full transcript beside notes with timestamp-linked audio seeking/highlighting.
- Seekable local audio previews for recordings and audio tracks from video.
- Play/pause, scrubbing, speed, skip controls, keyboard shortcuts, follow playback
  and browser-local resume positions.
- Search results with neighboring context, keeping the complete transcript visible.
- Editable/resettable notes, hide/restore, personal timestamped notes/bookmarks,
  rename and review state with persistent, versioned annotations.
- Exports include reviewed notes, bookmarks and the complete transcript.
- Explicit browser microphone capture with stop/cancel and local import.
- Ordinary questions no longer become automatic highlights. Explicit unresolved
  cues can form Follow-ups; no claim of semantic rhetorical-question detection.

## Compatibility and storage

Keep the existing environment, model weights and state/spool directories.
Reinstall requirements for the Windows setuptools compatibility pin. Doctor
now imports Whisper, and missing modules are identified in failure summaries.
Only one receiver/review worker can own a state directory at a time.
Browser recordings without duration tags are bounded-decoded and checked before
inference; their decoded duration is authoritative.

Existing receiver transcripts remain readable. Current candidate notes are
derived without ASR and do not rewrite old generated artifacts. User edits are
stored separately; stale tabs cannot silently overwrite newer annotation edits.

The workspace adds reviews, previews, browser-uploads and review-device folders
inside receiver state. Imports still use the recorder queue and real authenticated
HTTP transfer. Original device copies, receiver media and outputs are retained.

## Boundaries and limitations

The UI is restricted to 127.0.0.1. It uses private fragment-based launch keys,
HttpOnly SameSite cookies, mutation CSRF checks, Host/Origin checks, no-store
responses, a restrictive CSP, and no third-party assets. This is a single-user
local workspace; remote user access needs a separate design.

Inputs/previews/results remain plaintext. Video frames/slides are not shown;
audio is previewed. Timestamps are approximate ASR segment boundaries.
Microphone chunks are not durable until stopped/imported. Actual Windows
microphone hardware, Pi deployment, semantic notes, speaker attribution,
encryption-at-rest, retention automation and production hardening remain work.
