# SecureNote

A local class and meeting recorder prototype for ECE 6540, Project Assignment 2.
Import audio or video, read the complete timestamped transcript, listen at a
selected passage, edit personal notes, and ask questions about the recording.
The recorder and processor are separate roles, emulated on one computer here.
No paid API or model server is needed. Inference runs locally after setup.

## Start here (Windows or Linux)

Use **64-bit Python 3.10-3.12; Python 3.12 is recommended**. This dependency set
and setup script target Windows and Linux x86-64. The laptop/server does the
model work; do not install the processor stack on a Pi Zero 2.

Install Python and FFmpeg once. FFmpeg must provide both `ffmpeg` and `ffprobe`
on PATH. On Ubuntu/Debian, with a supported Python version installed:

```bash
sudo apt update
sudo apt install python3-venv ffmpeg
python3 --version
```

If your distribution's default Python is newer than 3.12, use a separately
installed Python 3.12 and its venv package. Do not replace the system Python.
On Windows, install Python 3.12, then install FFmpeg:

```powershell
winget install --id Gyan.FFmpeg -e
```

Reopen the terminal after installation. Extract the project, enter its folder,
and run **one script**:

```bash
# Linux
python3 start.py
```

```powershell
# Windows (or double-click Start-SecureNote.cmd)
py -3.12 start.py
```

Choose **1: CPU** for the simplest setup, including on a Linux PC.

Choose **2: NVIDIA GPU** if the machine has a compatible NVIDIA GPU and driver.
The script creates `.venv`, installs pinned dependencies, downloads both models,
checks model inference, remembers the device choice, and opens the workspace.
Setup requires internet access and several GB of free disk space. GPU dependencies
are substantially larger. Existing recordings and models are preserved.


After setup, choose **3: Start workspace**. That path does not install or download
anything. Keep the terminal open; Ctrl+C stops the server. The private launch URL
opens a session on `127.0.0.1`; do not share it.

### Commands without menus

Use `python3` on Linux or `py -3.12` on Windows in these examples:

```bash
python3 start.py setup --device cpu --no-launch
python3 start.py run
python3 start.py run --device cpu --no-browser
python3 start.py setup --device cuda --no-launch
python3 start.py run --device cuda
python3 start.py demo
python3 start.py test
```

`--device` selects **Whisper transcription**: CPU int8 or NVIDIA CUDA float16.
FLAN-T5-small answers always run on CPU float32. GPU mode does not improve
answer quality. The assignment demo deliberately runs on CPU, regardless of
the saved setting, and creates a new evidence folder each time.

For a headless Linux host, use `--no-browser`; the app still listens on loopback.
If accessing it from another computer, forward the port through SSH, then open
the printed URL locally. This prototype is not a public web service.

## Quick verification

1. Run `python3 start.py`, select CPU setup, and let the model checks finish.
2. Import a supplied synthetic recording from `examples/` or run the demo.
3. Open its transcript, click a timestamp, and inspect the automatic notes.
4. Ask a narrow factual question and compare the answer to its source passage.
5. Run `python3 start.py demo` for all three examples plus failure injection.
6. Run `python3 start.py test` for the automated tests.

Model weights and virtual environments are intentionally not
included in the submission.

## What the prototype implements

Recording pipeline: input -> size/checksum/audio validation -> FFmpeg decoding
-> local Whisper inference -> segment validation and extractive notes -> output.
Question pipeline: question validation -> transcript retrieval -> prompt building
-> local FLAN-T5 inference -> evidence check -> answer and source timestamps.
Both pipelines log stages, input size, latency, status and output metadata.

**RAG is the additional AI component required by the assignment.** TF-IDF ranks
up to three transcript chunks with cosine score >= 0.20. The model receives that
retrieved context and generates an answer. Ordinary FFmpeg invocations are not
being presented as model-directed AI tool calls. There is no autonomous agent.

If retrieval returns nothing, generation is skipped and the UI reports that this
search found no relevant passages. If a model abstains or its answer cannot be
matched to supplied text, the code retries once with the strongest passage and a
simpler prompt. Another failure returns `needs_review`, preserving the evidence.

**Answer quality is limited.** Keyword retrieval can miss meaning; literal answer
matching can reject correct paraphrases or accept incomplete answers. In the
reported Wild West example the patch returned "late 2024" but omitted "early
2025." This is a partial fix, not a reliable general-purpose assistant. A stronger
answer model and semantic retrieval are future work. Check the source audio.

Automatic notes are selected and grouped transcript sentences, not a complete
LLM-generated meeting summary. Diarization and inferred owners are not implemented.

## Reviewing and keeping notes

Select a recording to see the full transcript. Click timestamps to seek the
recording. Add/edit personal notes and save useful answers to your notebook.
Search supports reviewing transcript and note content. Ask this recording uses
the separate RAG pipeline described above.

Trash hides a recording; Restore brings it back. Permanent deletion removes
that workspace's recording results, previews, notes and saved RAG answers. It
does not erase original imports, independent recorder copies, backups, or CLI
answer folders. It is not secure erasure. Active processing/answers block unsafe
deletion. Retention remains manual.

## Where the code and data live

| Path | Responsibility |
| --- | --- |
| `start.py` | Standard-library setup, menus and process launch |
| `device.py` | Recorder spool, manifest and authenticated transfer |
| `laptop.py` | Receiver, persistent queue and processing worker |
| `review.py` / `review_static/` | Local HTTP workspace and browser interface |
| `prototype/pipeline.py` | Validation, decoding, Whisper and per-run logging |
| `prototype/analysis.py` | Transcript contracts, sentence notes and lexical search |
| `prototype/rag.py` | Retrieval, prompt budget, local generation and evidence checks |
| `prototype/review.py` | Review storage, playback preparation, Trash and deletion |
| `prototype/transfer.py` | Wire contract, checksums and atomic state writes |
| `prototype/gpu.py` | Windows DLL setup and isolated CUDA inference probe |
| `tools/run_assignment_demo.py` | Real transfer/transcription/RAG examples and failure test |
| `tests/` | Contract, transfer, review, RAG and launcher regression tests |
| `models/` / `.venv/` | Downloaded models / isolated Python environment |
| `laptop-state/` | Default jobs, recordings, results, annotations and answers |
| `local-settings.json` | Saved CPU/CUDA selection; no credentials |

The recorder uses standard-library Python, separate from inference dependencies.
For the lower-level two-role commands, see `device.py --help`, `laptop.py --help`
and `docs/architecture.md`. Physical Pi capture is not hardware-tested.

## Privacy and security boundaries

All model inference uses local model files. Setup downloads packages and model
weights; it does not upload recordings. The review server binds to loopback and
checks its session, Host, Origin and CSRF token for mutations. Recorder transfer
uses a device token, byte count and checksum; HTTP is limited to loopback,
while remote transfer requires verified HTTPS.

Files are plaintext unless stored on an encrypted volume. Protect the machine,
its account, device tokens and backups. Default logs avoid transcript/answer
content; the synthetic assignment demo explicitly enables answer content for
inspection. Do not use content logging for private meetings. Local processing
alone does not make this a certified confidential-environment deployment.

## Troubleshooting

- **Missing FFmpeg/ffprobe:** install FFmpeg, reopen the terminal, and rerun setup.
- **No venv / ensurepip:** install your Python version's venv package on Linux.
- **Unsupported Python:** use Python 3.12. Do not copy `.venv` between machines or
  operating systems; create it locally using setup.
- **CUDA library/driver errors:** choose CPU to continue. GPU setup installs the
  pinned CUDA 12/cuDNN 9 libraries but not an NVIDIA driver. Check `nvidia-smi`.
  The launcher sets Linux `LD_LIBRARY_PATH` before inference; Windows registers
  DLL directories. GPU inference is probed in a child process because native
  library failures can terminate Python. Hardware CUDA validation is still needed
  on your machine; this release was tested on Linux CPU.
- **Port already in use:** stop the old workspace, or run
  `python3 start.py run --port 8788`. Do not run two receivers on the same state.
- **Incomplete download:** rerun setup. Existing completed model files are reused.
- **Unhelpful answer:** review retrieved passages. This is a known model/retrieval
  limitation, not proof that the recording lacks the information.

Technical setup references: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(CUDA libraries and Linux loader paths), [PyTorch version installation](https://pytorch.org/get-started/previous-versions/)
(CPU 2.8.0), and [FLAN-T5-small](https://huggingface.co/google/flan-t5-small).
