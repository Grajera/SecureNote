"""Recorder role: queue, retain, transfer and acknowledge. No AI dependencies.

File replay emulates capture now. The optional ALSA capture adapter uses
arecord on Linux/Pi later. This program never imports the inference pipeline.
"""

import argparse
import base64
import http.client
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from prototype.transfer import (
    MAX_BYTES,
    atomic_json,
    digest_file,
    event,
    now,
    read_token,
    validate_endpoint,
    validate_manifest,
)


def enqueue(source, spool="device-spool", device_id="pi-emulator-01"):
    """Copy a recording into durable spool storage before attempting delivery."""
    os.umask(0o077)
    source = Path(source)
    if (
        not source.is_file()
        or source.is_symlink()
        or not 0 < source.stat().st_size <= MAX_BYTES
    ):
        raise ValueError("Capture input must be a nonempty regular file up to 2 GiB")
    spool = Path(spool)
    spool.mkdir(parents=True, exist_ok=True)
    recording_id = uuid.uuid4().hex
    final = spool / recording_id
    staging = spool / (recording_id + ".pending")
    staging.mkdir(mode=0o700)
    started = time.perf_counter()
    try:
        payload = staging / "recording.media"
        with source.open("rb") as incoming, payload.open("wb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        manifest = validate_manifest(
            {
                "schema_version": "1.0",
                "recording_id": recording_id,
                "device_id": device_id,
                "captured_at": now(),
                "input_bytes": payload.stat().st_size,
                "sha256": digest_file(payload),
            }
        )
        atomic_json(staging / "manifest.json", manifest)
        atomic_json(staging / "delivery.json", {"status": "queued", "attempts": 0})
        staging.rename(final)
        event(
            spool / "device.jsonl",
            "capture_emulation",
            "queued",
            recording_id=recording_id,
            input_bytes=manifest["input_bytes"],
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def connection(endpoint, ca_file=None):
    address = validate_endpoint(endpoint)
    if address.scheme == "https":
        context = ssl.create_default_context(cafile=ca_file)
        return http.client.HTTPSConnection(
            address.hostname, address.port or 443, context=context, timeout=60
        )
    return http.client.HTTPConnection(address.hostname, address.port or 80, timeout=60)


def send_one(directory, endpoint, token_file, ca_file=None):
    """Retain the local copy until the receiver acknowledges matching size and hash."""
    directory = Path(directory)
    manifest = validate_manifest(json.loads((directory / "manifest.json").read_text()))
    delivery = json.loads((directory / "delivery.json").read_text())
    if delivery["status"] == "delivered":
        return delivery
    delivery.update(status="queued", attempts=delivery.get("attempts", 0) + 1)
    atomic_json(directory / "delivery.json", delivery)
    started = time.perf_counter()
    client = None
    try:
        payload = directory / "recording.media"
        if (
            payload.stat().st_size != manifest["input_bytes"]
            or digest_file(payload) != manifest["sha256"]
        ):
            raise ValueError("Local recording changed after capture; transfer refused")
        token = read_token(token_file)
        client = connection(endpoint, ca_file)
        client.putrequest("POST", "/v1/recordings")
        client.putheader("Authorization", "Bearer " + token)
        client.putheader("Content-Type", "application/octet-stream")
        client.putheader("Content-Length", str(manifest["input_bytes"]))
        encoded = base64.b64encode(json.dumps(manifest).encode()).decode()
        client.putheader("X-SecureNote-Manifest", encoded)
        client.endheaders()
        with payload.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                client.send(chunk)
        response = client.getresponse()
        receipt = json.loads(response.read(65536))
        if (
            response.status not in (200, 201)
            or receipt.get("status") != "accepted"
            or any(
                receipt.get(key) != manifest[key]
                for key in ("recording_id", "input_bytes", "sha256")
            )
        ):
            raise ValueError("Receiver did not acknowledge the exact recording")
        delivery = {
            "status": "delivered",
            "attempts": delivery["attempts"],
            "receipt": receipt,
            "acknowledged_at": now(),
        }
        atomic_json(directory / "delivery.json", delivery)
        event(
            directory.parent / "device.jsonl",
            "transfer",
            "acknowledged",
            recording_id=manifest["recording_id"],
            input_bytes=manifest["input_bytes"],
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except Exception as error:
        delivery.update(status="queued", last_error_type=type(error).__name__)
        atomic_json(directory / "delivery.json", delivery)
        event(
            directory.parent / "device.jsonl",
            "transfer",
            "retry_pending",
            recording_id=manifest["recording_id"],
            error_type=type(error).__name__,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    finally:
        if client:
            client.close()
    # Sources and spool copies are retained even after acknowledgment.
    return delivery


def remote_status(recording_id, endpoint, token_file, ca_file=None):
    if len(recording_id) != 32 or any(
        character not in "abcdef0123456789" for character in recording_id
    ):
        raise ValueError("Invalid recording ID")
    client = connection(endpoint, ca_file)
    try:
        client.request(
            "GET",
            "/v1/jobs/" + recording_id,
            headers={"Authorization": "Bearer " + read_token(token_file)},
        )
        response = client.getresponse()
        if response.status != 200:
            raise ValueError("Status request rejected")
        return json.loads(response.read(65536))
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="SecureNote recorder / Pi emulator")
    subcommands = parser.add_subparsers(dest="command", required=True)
    capture = subcommands.add_parser(
        "enqueue", help="Emulate capture using an existing local recording"
    )
    capture.add_argument("input", type=Path)
    capture.add_argument("--spool", default="device-spool")
    capture.add_argument("--device-id", default="pi-emulator-01")
    record = subcommands.add_parser(
        "record", help="Optional Linux/Pi ALSA capture adapter; needs arecord"
    )
    record.add_argument("--seconds", type=int, default=30)
    record.add_argument("--alsa-device", default="default")
    record.add_argument("--spool", default="device-spool")
    record.add_argument("--device-id", default="pi-recorder-01")
    send = subcommands.add_parser(
        "send", help="Send queued recordings; failures remain queued"
    )
    send.add_argument("--spool", default="device-spool")
    status = subcommands.add_parser("status")
    status.add_argument("recording_id")
    for command in (send, status):
        command.add_argument("--endpoint", default="http://127.0.0.1:8765")
        command.add_argument("--token-file", required=True)
        command.add_argument("--ca-file")
    args = parser.parse_args()
    if args.command == "enqueue":
        print(enqueue(args.input, args.spool, args.device_id))
    elif args.command == "record":
        if not 1 <= args.seconds <= 7200:
            raise ValueError("Capture must last 1-7200 seconds")
        Path(args.spool).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="capture-", dir=args.spool
        ) as temporary:
            path = Path(temporary) / "recording.wav"
            subprocess.run(
                [
                    "arecord",
                    "-q",
                    "-D",
                    args.alsa_device,
                    "-f",
                    "S16_LE",
                    "-r",
                    "16000",
                    "-c",
                    "1",
                    "-d",
                    str(args.seconds),
                    str(path),
                ],
                check=True,
                timeout=args.seconds + 15,
            )
            print(enqueue(path, args.spool, args.device_id))
    elif args.command == "send":
        failures = 0
        for path in sorted(Path(args.spool).glob("*/manifest.json")):
            if len(path.parent.name) != 32 or any(
                character not in "abcdef0123456789" for character in path.parent.name
            ):
                continue  # An interrupted capture staging directory is not queued.
            result = send_one(path.parent, args.endpoint, args.token_file, args.ca_file)
            print(path.parent.name, result["status"])
            failures += result["status"] != "delivered"
        return 2 if failures else 0
    else:
        print(
            json.dumps(
                remote_status(
                    args.recording_id, args.endpoint, args.token_file, args.ca_file
                ),
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(
            "Recorder command failed:",
            type(error).__name__,
            "- check local configuration",
        )
        raise SystemExit(2)
