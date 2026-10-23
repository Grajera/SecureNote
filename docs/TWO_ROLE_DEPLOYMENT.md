# Intended deployment: recorder -> processor

This version runs both roles as real independent programs. On a single laptop,
the recorder uses recorded audio/video as its capture source and transfers it
over loopback HTTP. The receiver validates/stores the upload, acknowledges it,
and independently queues local model inference. Importing a file emulates the
microphone; the queue, transport, acknowledgment and processing are implemented.

| Responsibility | Recorder (`device.py`) | Processor (`laptop.py`) |
|---|---|---|
| Current location | Separate process on the laptop, emulating the Pi | Laptop process |
| Later location | Pi Zero 2 W | Laptop or server |
| Dependencies | Python standard library; optional `arecord` for ALSA | Python requirements, FFmpeg/ffprobe, local Whisper weights |
| Persistent data | Recording spool, manifest, delivery state, device log | Received media, job state, results, receiver/pipeline logs |
| AI work | None | ASR, importance selection, note formatting and retrieval |
| Offline behavior | Queue locally, retry `send` when receiver is available | Runs models locally; no hosted inference |

## One-PC emulation

Use README setup, then run `laptop.py serve` in one terminal. It creates
`laptop-state/device.token` and listens only on 127.0.0.1 by default. In another
terminal, enqueue a recording with `device.py enqueue FILE`, then
`device.py send --token-file laptop-state/device.token`. The recorder sends
only queued items. `device.py status ID --token-file laptop-state/device.token`
returns the job's current status without returning its transcript.

For automatic demonstration, `python tools/run_distributed_demo.py` starts the
receiver as a child process and invokes the recorder as separate processes.
Three recordings are transferred, processed and checked. The final injected
corrupt transfer must return HTTP 400 without publishing a processor job.
The script removes its generated authentication token after the demo. Manual
deployments keep their token across receiver restarts.

Device lifecycle: `queued -> delivered` only after verified acknowledgment.
Connection/authentication/integrity failures keep `queued`; rerun `send`.
Processor lifecycle: `queued -> processing -> completed | failed`. Uploaded
bytes can be accepted even if later media validation/transcription fails.
Delivery acknowledgment is not a promise that notes were generated.

The receiver uses an atomic rename to publish a fully written upload plus its
manifest/job state. Partial uploads are never processing jobs. Uploading the
same ID and identical manifest again returns a receipt without a second job;
the complete duplicate body is checked first. A conflicting manifest is
rejected. Queued jobs survive receiver restarts. Jobs interrupted during ASR
are requeued on startup; abandoned output folders may remain for inspection.
Power-loss durability of the filesystem itself is not guaranteed.

## Transfer contract (schema 1.0)

`POST /v1/recordings`: bearer token in the Authorization header, raw media body,
one Content-Length header, and X-SecureNote-Manifest containing base64 JSON:

```json
{
  "schema_version": "1.0",
  "recording_id": "32 lowercase hexadecimal characters",
  "device_id": "pi-emulator-01",
  "captured_at": "UTC ISO-8601 timestamp",
  "input_bytes": 826348,
  "sha256": "64 lowercase hexadecimal characters"
}
```

Size must be 1..2 GiB, device ID 1..64 letters/digits/underscore/hyphen, manifest
header <=2048 bytes, and received body length/hash must match. Device filenames
never select receiver paths. Unknown versions/fields and invalid IDs are
rejected. Verified storage returns HTTP 201 (or 200 for duplicate) with
`{recording_id, input_bytes, sha256, status: accepted}`. The device compares the
receipt before marking delivered. HTTP 400 means validation rejected; 401 means
authentication rejected. Interrupted transfers, missing ACKs and network errors
remain retryable on the recorder.

`GET /v1/jobs/<recording_id>` requires the same token. It returns status, hash,
size, recording ID and result directory ID if one exists; no private transcript
or absolute filesystem paths are sent to the device.

## Move the recorder to a Pi later

Copy **device.py**, **prototype/__init__.py**, and **prototype/transfer.py** to
the Pi, preserving that directory structure. No Whisper, NumPy, CUDA or model
weights are needed there. Create a private spool folder and provision a copy
of the receiver token securely. Use an approved HTTPS endpoint and a certificate
trusted by the Pi (custom CA via `--ca-file`). No TLS verification bypass exists.

Example, after configuring real hardware and server certificates:

```bash
python3 device.py record --seconds 60 --alsa-device plughw:1,0 --device-id pi-01
python3 device.py send --endpoint https://processor.example:8765 --token-file /secure/device.token --ca-file /secure/ca.pem
```

The optional `record` adapter invokes Linux `arecord` for 16 kHz mono PCM and
passes its output into the same queue. It is supplied but **not hardware-tested**.
USB microphone setup, storage management, physical enclosure, power management,
OS service installation and capture consent indicators remain future work.
Emulation uses `enqueue`, so no microphone or Pi is needed for the assignment.

## Move the processor to a server later

Install this project's processing dependencies, FFmpeg and model weights on the
server; copy the receiver state or initialize a new one. Launch the same code:

```bash
python laptop.py serve --state /secure/securenote --model-dir /models/base.en --host 0.0.0.0 --port 8765 --cert /secure/server.crt --key /secure/server.key
```

Update the recorder's `--endpoint` and trusted CA. The protocol and processing
pipeline do not change. Non-loopback service binding and client HTTP to remote
hosts are refused unless HTTPS is used. Actual remote TLS deployment has not
been tested on the user's network; certificates, routing and firewall policy
must be configured for that environment.

## Security limits

The demo token is shared, not per-device enrollment. There is no role-based
access control, disk encryption, key rotation, tamper-proof audit log, disk quota
or malicious media sandbox. The Python HTTP server is a minimal prototype;
production service hardening and denial-of-service protection remain work.
Bearer authentication without TLS is allowed only for loopback emulation.
Inputs, queue data and results remain sensitive plaintext; deploy on protected
encrypted volumes. Original/device copies are retained until deliberately
removed. Do not infer secure deletion or security certification from local AI.
