# SecureNote - first local prototype

**This guide covers the standalone processing/diagnostic path.** The intended
two-role recorder/receiver deployment is documented in README.md and
TWO_ROLE_DEPLOYMENT.md. References below to no listener describe only this
standalone CLI; `laptop.py serve` adds the authenticated receiver.

Turns a local audio/video recording into a timestamped transcript, automatic
candidate notes, and searchable passages. Includes a CLI and an optional desktop
window. No OpenAI/Anthropic API, subscription, browser upload, or model server.
The model is open-source Whisper running on this computer.

**Prototype scope:** Whisper is the AI model. Notes are an automatic extractive
baseline using importance scoring and language cues, not an LLM summary. It
selects source sentences and displays only nonempty Decisions, Action items,
Questions and Key points sections. It can miss implicit commitments, confuse
quoted decisions, or miss paraphrases. It never deliberately invents an owner
or deadline. Review notes and ASR text against the recording.

## Windows laptop quick start

Use Windows 11, 64-bit Python **3.11 or 3.12**, and a folder such as
`C:\SecureNote` outside OneDrive/Dropbox. Extract the ZIP and open PowerShell
inside the folder containing `securenote.py`. No administrator access is needed
for Python packages. Install Python with Tcl/Tk support for the optional window.

1. Install FFmpeg (both `ffmpeg.exe` and `ffprobe.exe` are needed):

   ```powershell
   winget install --id Gyan.FFmpeg -e
   ```

   Close and reopen PowerShell after installation, return to the project folder,
   then check `ffmpeg -version` and `ffprobe -version`. If winget is unavailable,
   install a Windows build linked from https://ffmpeg.org/download.html and add
   its `bin` folder to your user PATH.

2. Create an isolated Python environment, install packages, and download weights:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe securenote.py download-model --model base.en
   .\.venv\Scripts\python.exe securenote.py doctor
   ```

   If using Python 3.11, replace `py -3.12` with `py -3.11`. These setup steps
   need internet access. Downloads contain code/model weights, not recordings.
   Model files occupy about 141 MiB; allow additional space for packages and audio.
   Models are not embedded in the submission ZIP.

3. Run the supplied meeting first:

   ```powershell
   .\.venv\Scripts\python.exe securenote.py run .\examples\media\business.wav --query "budget deadline"
   ```

4. Run your recording, or open the desktop window:

   ```powershell
   .\.venv\Scripts\python.exe securenote.py run "C:\Recordings\my-class.mp4" --query "homework exam"
   .\.venv\Scripts\python.exe desktop.py
   ```

   You can also double-click `Start-SecureNote.cmd` after setup. Browse to a file,
   click **Transcribe + make notes**, then enter search words and click
   **Search transcript**. Keep the window open while it processes. The window
   displays notes as text; outputs also remain in the run folder.

CPU/int8 is the tested default. It fits the intended 32 GB RAM laptop without
using its RTX 4050, CUDA, or NVIDIA drivers. Processing was tested on a Linux
CPU host, not on your actual laptop. The Windows window is provided but was
not interactively tested here. No Pi hardware was tested.

## CLI and output

Every input receives its own `runs/<timestamp>-<id>/` folder:

| File | Contents |
|---|---|
| `notes.md` | Automatically selected notes, dynamic sections, timestamps and search results |
| `notes.json` | Same candidate notes as structured source passages |
| `transcript.txt` | Complete ASR transcript with segment timestamps |
| `transcript.json` | Validated ASR segments and derived sentence passages |
| `search.json` | Initial search results and cosine scores |
| `run.jsonl` | Stage starts/completions/failures, times and output summaries |
| `summary.json` | Status, sizes, model configuration, runtime and output inventory |

Search a previous run without retranscribing (replace the example folder):

```powershell
.\.venv\Scripts\python.exe securenote.py search ".\runs\YOUR-RUN-FOLDER" "budget Friday"
```

Queries are lexical TF-IDF retrieval, not semantic question answering. Try
specific words that occur in the recording. Scores are similarities, not
confidence probabilities. No positive score produces an explicit empty result.
Searches are saved as `search-<id>.json` with a log event. Notes are not overwritten.
You can repeat `--query` during processing. No query supplied uses a generic
importance query; automatic note selection never requires a query.

The runtime only opens local paths. Supports common FFmpeg-decodable WAV, MP3,
M4A, MP4, MOV, MKV, WebM, FLAC, OGG, AAC, WMA/ASF, AVI, MPEG/TS, AIFF, AU, AMR,
CAF, WavPack, APE and FLV files. It uses the **first audio track**, ignores video
frames and subtitles, and checks actual media content. This does not promise
every codec or damaged/encrypted/DRM file. URL inputs and streaming playlists
are excluded. A video without audio fails clearly. Limits: **2 GiB and 2 hours**.
Split longer files before processing. Source timestamps are preserved; silence
is not manually removed from the recording timeline.

For improved transcription, download a larger local model during setup:

```powershell
.\.venv\Scripts\python.exe securenote.py download-model --model small.en
.\.venv\Scripts\python.exe securenote.py run "C:\Recordings\meeting.mkv" --model-dir models/small.en
```

For non-English audio, download `base` or `small` (without `.en`) and specify
`--model-dir models/small --language auto`. This path is available but the
included evidence is English only. GPU flags are advanced options and were not
tested: `--device cuda --compute-type float16` requires compatible CUDA/cuDNN.
The CPU path is the supported first setup; a working GPU is unnecessary.

## Offline use and confidentiality

After setup, disconnect networking and run the same processing/search commands.
`run` requires an existing model directory, uses `local_files_only=True` and
sets Hugging Face offline mode. `download-model` is the only command designed
to contact the internet. The example test additionally blocks Python socket
connections. FFmpeg/ffprobe tools use a file-only protocol allowlist; there is
no shell interpolation, remote URL input, agent command execution, or listener.

Recordings, transcripts and notes are sensitive **plaintext**. Choose an
approved encrypted local volume for sources, `--output` and model installation;
use restrictive Windows folder permissions and avoid cloud-synced folders.
POSIX run folders are created private; Windows inherits its parent's ACL.
No application encryption, authentication, organization policy enforcement,
certification, or access-controlled sharing is implemented. This prototype is
not an approval to process employer or classified data. Use synthetic/public
recordings for the assignment and follow the environment's recording rules.

Default logs omit source filenames, queries, transcript text and note bodies.
They retain input size/duration, status, stage latency, counts, output filenames
and a notes hash. The actual notes/transcripts remain separate local outputs.
`--log-content` duplicates the note body into logs **only when requested**;
included synthetic demo runs use it to demonstrate logged output. Never use
that flag with confidential recordings. Search JSON files do retain the query.

Temporary decoded WAVs are created inside the chosen output volume and removed
on success, handled errors and Ctrl+C. Power loss/forced termination may leave
them; inspect incomplete run folders before reuse. Deletion is not secure
erasure and does not cover swap, backups or OS caches. Originals and generated
transcripts are intentionally retained for search/review; delete run folders
and recordings under your own retention policy. No automatic source deletion.

## Reproduce assignment evidence

Three included synthetic recordings: business WAV, lecture MP3, planning MP4.
They contain no real meeting data. The authoritative measured evidence is
`examples/verified/EVIDENCE.md`, full artifacts and `evidence.json`.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/run_examples.py --model-dir models/base.en
```

The latter runs real ASR for all three files, injects malformed model output,
tests silence, and blocks Python socket connections throughout. Choose a new
`--output` on subsequent invocations. Timings and ASR wording can vary by
hardware/library behavior; model and file hashes are recorded. Raw evidence is
not fabricated. A separate failed empty-input test verifies the model is never
called for invalid files. Full model ASR is not mocked in the example script.

Intentional failure from the CLI:

```powershell
.\.venv\Scripts\python.exe securenote.py run examples/media/business.wav --inject-invalid-segment
```

After actual inference this replaces a transcript text field with integer 123.
The ASR/postprocessing contract rejects it, returns exit code 2, logs the failed
stage and writes a failure summary. No misleading notes are emitted.

Optional audio regeneration (not necessary to run the examples): install
`espeakng-loader==0.2.4` and run `python tools/make_demo_audio.py`. The example
source texts are included. Model accuracy is not measured by these short demos.

## Linux

Install system Python 3.10-3.12, Python venv support and FFmpeg. On Ubuntu:

```bash
sudo apt install python3-venv ffmpeg
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python securenote.py download-model --model base.en
.venv/bin/python securenote.py run examples/media/business.wav --query "budget"
```

Desktop mode also needs `python3-tk` and a graphical session. It is optional.

## Dedicated device roadmap and assignment mapping

This version implements the laptop/server side. A future Pi Zero 2 W records
through a USB microphone, stores audio locally, then transfers it for processing.
There is **no Pi recording service, transfer service, live microphone capture,
speaker diarization, speaker naming, LLM summarization or semantic search** in
this prototype. The code does not invent device or security capabilities.

`docs/Project_Assignment_2.pdf` is the four-page submission. `docs/architecture.md`
contains the implemented architecture and contracts. The local controller
invokes allowlisted `inspect_media`, `decode_audio` and `search_transcript`
tools, with input/result validation and logged calls. This is the implemented
**tool-call** requirement. Search is retrieval but is not advertised as full
RAG; no LLM is selecting tools and there is no autonomous agent loop.

Code is small enough to explain: `securenote.py` dispatches CLI commands;
`prototype/pipeline.py` handles stages, tools and logging;
`prototype/analysis.py` implements notes and retrieval; `desktop.py` wraps these
functions in a local window. Consult `docs/SECURITY_AND_GAPS.md` for next steps.

References: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[model card](https://huggingface.co/Systran/faster-whisper-base.en),
[Whisper models](https://github.com/openai/whisper),
[FFmpeg protocol allowlists](https://ffmpeg.org/ffmpeg-protocols.html).
