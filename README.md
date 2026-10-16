# SecureNote - local prototype

Local audio/video -> timestamped transcript -> automatic candidate notes and
searchable passages. Includes a CLI, optional desktop window, synthetic demos,
execution logs and a four-page assignment PDF. No hosted inference API,
subscription, model server or browser upload.

Whisper is the AI model. Notes use automatic extractive importance scoring and
English language cues; they are not LLM-generated summaries. Review outputs
against the recording. Speaker recognition and the future Pi recorder/offload
are not implemented. Search matches transcript words, not semantic paraphrases.

## Windows quick start

Use **64-bit Python 3.12** (or 3.11) and Windows 11. Extract into a local folder
outside OneDrive/Dropbox, such as `C:\SecureNote`. Open PowerShell in the folder
containing `securenote.py`.

Install FFmpeg:

```powershell
winget install --id Gyan.FFmpeg -e
```

Close and reopen PowerShell, return to this folder, and verify both
`ffmpeg -version` and `ffprobe -version`. Then:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe securenote.py download-model --model base.en
.\.venv\Scripts\python.exe securenote.py doctor
.\.venv\Scripts\python.exe securenote.py run examples/media/business.wav --query "budget deadline"
.\.venv\Scripts\python.exe desktop.py
```

Use `py -3.11` if that is your installed version. After setup, double-click
`Start-SecureNote.cmd` to open the window. Choose a recording and click
**Transcribe + make notes**. Enter search words and click **Search transcript**.
Setup downloads packages/weights; subsequent processing and search work offline.
Weights are not bundled in the ZIP.

## Your recordings and outputs

```powershell
.\.venv\Scripts\python.exe securenote.py run "C:\Recordings\class.mp4" --query "homework exam"
.\.venv\Scripts\python.exe securenote.py search "runs\YOUR-RUN-FOLDER" "budget Friday"
```

The command prints its run folder. Open `notes.md` for notes, `transcript.txt`
for the transcript, and `search.json` for passages. JSON data, `run.jsonl` stage
logs and `summary.json` are saved alongside them. Existing-run search does not
rerun transcription. The desktop can also open old runs.

Common formats include WAV, MP3, M4A, MP4, MOV, MKV, WebM, FLAC, OGG and AVI,
subject to FFmpeg codecs. Limits: 2 GiB / 2 hours; first audio track only.
Unsupported/corrupt/DRM media and video without audio may be rejected.
CPU/int8 is the default; your 32 GB laptop does not need CUDA or its GPU.

## Verification and assignment files

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/run_examples.py --model-dir models/base.en
```

Seven contract tests pass. The example runner performs real ASR on WAV, MP3
and MP4 with Python socket connections blocked, then tests malformed model
output and silence. Included results: `examples/verified/EVIDENCE.md` and full
run folders. Processing was verified on a Linux CPU host, not this laptop;
the Windows desktop window was not interactively tested here.

- `docs/Project_Assignment_2.pdf`: four-page submission with the diagram,
  three runs, contracts, model assumptions, failure test and gap analysis.
- `docs/USER_GUIDE.md`: fuller Windows/Linux instructions and troubleshooting.
- `docs/architecture.md`: implemented stages and exact interfaces.
- `docs/SECURITY_AND_GAPS.md`: security limitations and Pi/server roadmap.

## Confidentiality

Runtime requires local model files, disables model downloads and uses local-only
media protocols. Logs omit transcript/note bodies by default. Transcripts,
notes and recordings remain **plaintext sensitive files**: choose an approved
encrypted local volume and restrictive folder permissions. `--output` selects
the destination. Use synthetic/public data for this demonstration. No built-in
encryption, authentication, certification or Pi transfer is claimed. Temporary
WAVs are cleaned up on handled completion/error; originals and searchable
outputs are retained. Detailed controls are in the user guide.
