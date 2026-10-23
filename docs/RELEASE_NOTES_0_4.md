# SecureNote 0.4 — notebook, deletion and CUDA setup

Added reversible Trash, restore and confirmed permanent deletion; processing jobs are protected.
Added an inline personal notebook with Ctrl+Enter save and per-tab drafts, note filtering,
and search across saved personal notes, visible highlights and transcripts (up to 100 hits).
Added explicit review.py --device cuda, float16 worker inference, a backend badge,
Windows venv NVIDIA DLL registration, optional pinned CUDA requirements and a GPU launcher.
The CUDA startup probe runs a real one-second inference in a child process so native
DLL aborts cannot take down a running review workspace during startup checks.
Model reuse avoids reconstructing Whisper for each queued recording.

Validation: 27 Python tests passed on Linux CPU. Headless Chromium exercised a real
MP4 import, local CPU transcription, fake-device browser microphone recording, media
seeking, edits, export, persistence, responsive layout, notebook save, global search,
Trash, restore and permanent deletion, with zero browser errors. GPU/native Windows
execution remains unverified here; run the provided startup probe on the target machine.

Security: existing session/CSRF/host checks apply to deletion and notes. Search stays
local and excludes Trash. Trash retains files until permanent deletion. Deletion is
ordinary file removal, not cryptographic erasure; see README for copy/backup scope.
Historical assignment evidence remains the v0.2 snapshot; the original assignment
write-up should not be represented as a measured v0.4 GPU benchmark.
