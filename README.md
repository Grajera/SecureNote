# SecureNote 0.4 - local recording review

A workspace for recordings, useful notes and the **full transcript**, with
clickable timestamps and built-in audio playback. The lightweight recorder and
laptop/server processor remain separate roles. AI inference stays local.

## Upgrade your Windows installation

Copy the files inside the ZIP's SecureNote folder into your existing project,
such as D:\Repos\SecureNotes, replacing application files. **Keep your .venv,
models, laptop-state, device-spool and demo folders.** Stop an old laptop.py
receiver before opening this workspace against the same state directory.

In PowerShell from the project folder:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe securenote.py doctor
.\.venv\Scripts\python.exe review.py
~~~

The Windows requirements pin setuptools to 80.9.0, fixing the CTranslate2
pkg_resources import failure. Reuse your downloaded model. After setup,
double-click **Start-SecureNote.cmd**. Running desktop.py opens the same UI.
Keep the terminal open; Ctrl+C stops the local workspace.

## NVIDIA GPU setup on Windows

The missing `cudnn_ops64_9.dll` error means the native cuDNN 9 runtime was not
loadable. The `pkg_resources` deprecation warning is separate and is not the
cause of that CUDA failure. This version uses CUDA 12 libraries with CTranslate2
4.6. Keep an up-to-date NVIDIA driver installed. These are large, one-time
package downloads; they do not send recordings anywhere.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cuda.txt
.\.venv\Scripts\python.exe review.py --device cuda
```

Or double-click **Start-SecureNote-GPU.cmd** after installing the optional
packages. The app registers the NVIDIA DLL directories inside this venv for
its own process, then runs a real CUDA inference probe in a separate process.
A missing DLL/native crash fails startup with diagnostic output instead of
starting a broken transcription worker. The top-right badge shows **CUDA ·
float16** when configured; each new run's summary records the backend. CPU
launches show **CPU · int8**. Existing transcripts are not rerun automatically.

CPU fallback: `.\.venv\Scripts\python.exe review.py --device cpu`.
GPU mode accelerates transcription; decoding, search and note selection remain
CPU work. The model is reused between recordings in the worker. CUDA inference
has not been hardware-tested on this release's CPU-only test machine; the
startup probe validates it on your laptop. For a later Linux GPU server, install
its NVIDIA runtime libraries using that platform's instructions; automatic pip
DLL discovery here targets Windows.

References: [faster-whisper GPU requirements](https://github.com/SYSTRAN/faster-whisper#gpu),
[NVIDIA cuDNN Windows installation](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.5.1/installation/windows.html).

## New notebook, search and deletion controls

- **Search everything** searches personal notes, visible automatic highlights,
  and transcript segments across recordings. Results show their recording,
  source and timestamp. Personal/automatic notes appear before transcript hits.
  All entered words must occur in the same note/segment; this is literal search,
  not an LLM answer. Results are capped at 100 and exclude Trash.
- **Your notebook** has an inline editor. Save with the button or Ctrl+Enter.
  Notes attach to the current playback position, support edit/remove, persist
  on disk and appear in Markdown exports. Unsaved drafts are kept in this
  browser tab's session storage when switching recordings. Saved notes stay
  on disk; drafts may be lost when closing the tab. The note filter searches
  both personal and automatic notes within the open recording.
- **Move to Trash** hides completed/failed recordings and notes without removing
  their files. **Open Trash → Restore** brings them back. Queued/processing jobs
  cannot be deleted until processing finishes.
- **Delete permanently** requires a second confirmation and removes the selected
  managed inbox copy, its result directory, this workspace's playback preview,
  annotations, and browser-import recorder copy. It also applies to explicitly
  included/demo state folders. Original imported files, independently managed
  recorder spools, other workspace previews, backups, browser drafts and historic
  metadata logs are not erased. It is file deletion, not secure disk erasure.

Existing annotations and recordings remain compatible. Stop all old app
instances before upgrading; use one processor for a state directory.

## First installation

Use 64-bit Python 3.12 or 3.11 and FFmpeg/ffprobe. Install FFmpeg with
winget install --id Gyan.FFmpeg -e, then reopen PowerShell to refresh PATH.

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe securenote.py download-model --model base.en
.\.venv\Scripts\python.exe securenote.py doctor
.\.venv\Scripts\python.exe review.py
~~~

Use py -3.11 if needed. Setup downloads packages/weights; normal inference uses
local files. CPU mode needs no CUDA/GPU, API key, subscription or model server.

## Review a recording

- **Import recording:** choose audio/video. It enters the emulated recorder's
  persistent queue, transfers over authenticated loopback HTTP to the processor,
  then is transcribed locally. Import progress and job state remain visible.
- **Record microphone:** explicitly grant browser microphone access, then stop
  and process, or cancel. Recording starts only after you click. Keep the tab
  open: microphone chunks are held in memory until stopped and imported.
- **Full transcript:** visible beside notes without a search or download.
  Click a note, transcript timestamp or search result to seek the player,
  scroll the complete transcript and highlight the matching segment.
- **Playback:** play/pause, scrub, skip 10 seconds, speed from 0.75-2x, optional
  follow-along highlighting and browser-local resume position. Keyboard:
  Space play/pause; arrows skip 5 seconds; / focuses transcript search.
- **Search:** matches include surrounding context. Search never removes the
  complete transcript. Search is lexical, so try words used in the recording.
- **Review:** rename recordings, edit/reset notes, hide/restore low-value notes,
  add timestamped personal notes/bookmarks, and mark recordings reviewed.
  Edits are labeled and never overwrite the original ASR transcript.
- **Export:** reviewed Markdown notes include bookmarks and the full transcript.
  A separate plain-text transcript download is also available.

Audio from video is played using a local MP3 preview. The video's picture/slides
are **not displayed** in this release. Original media is retained unchanged.
Preview encoding preserves the full audio sequence, including silence. Source
timestamps remain approximate ASR segment times, not word-perfect alignments.

## Questions and important notes

Ordinary questions stay in the transcript but are no longer automatically
promoted to a Questions section or recycled into Key points. Only explicit
unresolved-issue cues produce Follow-ups. Decisions, commitments and useful
takeaways are prioritized. This is an English extractive heuristic, not semantic
rhetorical-question classification; add a bookmark when an omitted question
matters. Existing receiver transcripts use the new selection without ASR.

## Existing recordings and device/server compatibility

Default state is laptop-state. Known demo*/laptop directories beneath the
project are discovered automatically. Add another receiver state if needed:

~~~powershell
.\.venv\Scripts\python.exe review.py --include-state "demo-two-role-2/laptop"
~~~

The app owns a receiver/worker on loopback port 8787; change it with --port.
Only one processor may own a state directory. The device protocol still works:

~~~powershell
.\.venv\Scripts\python.exe device.py enqueue "D:\Recordings\class.mp4"
.\.venv\Scripts\python.exe device.py send --endpoint http://127.0.0.1:8787 --token-file laptop-state/device.token
~~~

For separate Pi/server placement, use laptop.py serve and HTTPS as documented
in docs/TWO_ROLE_DEPLOYMENT.md. The recorder still needs only standard-library
Python; AI dependencies remain on the processor. The review UI is loopback-only;
remote user accounts and remote review access are future work.

## Privacy and storage

The browser is a local interface, not a cloud service. Do not share its private
launch link. Review media/APIs need a session cookie; mutations require CSRF
validation. Host/Origin checks, a restrictive CSP and no-store responses protect
the local session. There are no external assets, CDNs or app telemetry.

Recordings, previews, transcripts, annotations and exports are sensitive
**plaintext**. Use an approved encrypted, access-controlled local volume outside
cloud sync. Review metadata is in laptop-state/reviews and previews are in
laptop-state/previews. Browser storage holds playback position and speed.
Device copies, receiver media and generated results are retained. No secure
erasure, retention automation, certification or multiuser authorization is
claimed. Use synthetic/public data for the assignment.

## Verification and limitations

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/run_distributed_demo.py --output demo-v03
~~~

Tests cover contracts, transfer, local session/CSRF boundaries, exact media byte
ranges, actual audio-preview generation, annotation persistence/conflicts,
question selection and original-transcript preservation. Browser checks cover
playback/seeking, notes, search, export, reload, mobile layout, real MP4 import
and ASR. Microphone capture was tested with a synthetic browser device;
actual Windows microphone and Pi hardware remain untested here.

Whisper base.en, extractive notes and lexical search remain the baseline.
No diarization, reliable speaker names, semantic summaries, slide understanding
or production service hardening is claimed. The Assignment 2 report and archived
execution evidence describe the v0.2 milestone; see docs/RELEASE_NOTES_0_4.md
for this newer product release.
