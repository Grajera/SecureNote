# SecureNote - local prototype

Two running roles: **recorder/Pi emulator -> authenticated transfer -> laptop
processor -> transcript, notes and search**. Both run as separate processes on
your laptop now. Later, move the recorder to a Pi and the processor to a server.
No hosted inference API, subscription or paid model service.

Whisper is the AI model. Notes use automatic extractive importance scoring and
English language cues; they are not LLM-generated summaries. Review outputs
against the recording. Speaker recognition is not implemented. Capture is
emulated by importing a recording; transfer, acknowledgment, queueing and local
processing are real. Search matches words, not semantic paraphrases.

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
.\.venv\Scripts\python.exe tools/run_distributed_demo.py
```

Use `py -3.11` if that is your installed version. The demo starts a receiver
process and invokes the recorder process to send WAV, MP3 and MP4 recordings.
It waits for real transcription/notes and runs a corrupt-transfer failure test.
Look in `demo-two-role/laptop/results/` for notes/transcripts and
`demo-two-role/EVIDENCE.md` for results. For a repeat, choose a fresh folder with
`--output demo-second`. `Run-TwoRole-Demo.cmd` runs the same demo after setup.
Setup downloads packages/weights; inference stays offline. Model weights are
not bundled. The device-to-laptop connection is local, not a cloud API.

## Keep the laptop receiver running

In PowerShell window 1 (leave open), or double-click `Start-Receiver.cmd`:

```powershell
.\.venv\Scripts\python.exe laptop.py serve
```

In PowerShell window 2, emulate the recorder capturing and sending a file:

```powershell
.\.venv\Scripts\python.exe device.py enqueue "C:\Recordings\class.mp4"
.\.venv\Scripts\python.exe device.py send --token-file laptop-state/device.token
.\.venv\Scripts\python.exe device.py status RECORDING-ID --token-file laptop-state/device.token
```

`enqueue` prints a folder ending in the recording ID; use that ID for `status`.
Queued files survive an unavailable receiver; run `send` again to retry.
Delivered means checksum-verified storage, not completed transcription. The
receiver processes each accepted job and status becomes `completed` or `failed`.
Notes live in `laptop-state/results/<result_directory>/notes.md`. The device
retains its copy even after acknowledgment. You can also drag a file onto
`Send-To-Recorder.cmd` while the receiver is running.

Search an output without retranscribing:

```powershell
.\.venv\Scripts\python.exe securenote.py search "laptop-state/results/RESULT-DIRECTORY" "homework exam"
.\.venv\Scripts\python.exe desktop.py
```

In the optional desktop window, use **Open existing run** to review receiver
outputs and search. Its direct-file processing button remains a diagnostic
shortcut; the intended deployment uses `device.py` and `laptop.py`.

Common formats include WAV, MP3, M4A, MP4, MOV, MKV, WebM, FLAC, OGG and AVI,
subject to FFmpeg codecs. Limits: 2 GiB / 2 hours; first audio track only.
Unsupported/corrupt/DRM media and video without audio may be rejected.
CPU/int8 is the default; your 32 GB laptop does not need CUDA or its GPU.

## Verification and assignment files

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/run_distributed_demo.py --output demo-second
```

Fourteen tests cover contracts, real HTTP transfers, authentication, checksum
rejection, retries, persistent queues and duplicate-upload handling. Included
two-role execution evidence is in `examples/distributed-verified/`. Older
single-pipeline offline/silence evidence remains in `examples/verified/`.
Processing was verified on a Linux CPU host, not this laptop;
the Windows desktop window was not interactively tested here.

- `docs/Project_Assignment_2.pdf`: four-page submission with the diagram,
  three runs, contracts, model assumptions, failure test and gap analysis.
- `docs/USER_GUIDE.md`: fuller Windows/Linux instructions and troubleshooting.
- `docs/architecture.md`: implemented stages and exact interfaces.
- `docs/SECURITY_AND_GAPS.md`: security limitations and Pi/server roadmap.
- `docs/TWO_ROLE_DEPLOYMENT.md`: Pi/server migration and transfer contract.

## Confidentiality

Inference requires local model files, disables model downloads and uses local-only
media decoding protocols. A token protects the receiver. HTTP is permitted
only on loopback for same-PC emulation; separate machines require HTTPS with
certificate verification. Logs omit transcript/note bodies by default. Transcripts,
notes and recordings remain **plaintext sensitive files**: choose an approved
encrypted local volume and restrictive folder permissions. `--output` selects
the destination. Use synthetic/public data for this demonstration. No built-in
disk encryption, per-device authorization, certification or tested Pi hardware is claimed. Temporary
WAVs are cleaned up on handled completion/error; originals and searchable
outputs are retained. Detailed controls are in the user guide.
