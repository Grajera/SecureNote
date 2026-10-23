"""Laptop processor service; same role can move unchanged to a server later."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from prototype.transfer import (
    MAX_BYTES,
    atomic_json,
    digest_file,
    event,
    loopback,
    now,
    read_token,
    validate_manifest,
)


def initialize(state):
    os.umask(0o077)
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    (state / "inbox").mkdir(exist_ok=True)
    (state / "results").mkdir(exist_ok=True)
    token_path = state / "device.token"
    if not token_path.exists():
        descriptor = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(secrets.token_hex(32))
    read_token(token_path)
    return state


class Processor:
    def __init__(
        self, state, model_directory, queries=None, log_content=False, device="cpu"
    ):
        self.state = initialize(state)
        self.model_directory = Path(model_directory)
        self.device = device
        self.compute_type = "float16" if device == "cuda" else "int8"
        self.queries = queries
        self.log_content = log_content
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.wakeup = threading.Event()
        self.thread = None
        self.state_lock = None

    def start(self):
        # Only one processing worker may own this state directory, whether it
        # was launched through laptop.py or the local review workspace.
        handle = (self.state / ".processor.lock").open("a+b")
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise RuntimeError(
                "This receiver state is already in use. Stop the other receiver/review window before starting it again."
            ) from error
        self.state_lock = handle
        # A previous process may have stopped during ASR. Reprocess the persisted
        # recording on restart; abandoned result folders are left for inspection.
        with self.lock:
            for path in (self.state / "inbox").glob("*/job.json"):
                job = json.loads(path.read_text())
                if job["status"] == "processing":
                    job.update(status="queued", recovered_at=now())
                    atomic_json(path, job)
            # Cleanup upload staging directories, never published recordings.
            for partial in (self.state / "inbox").glob("*.pending"):
                shutil.rmtree(partial)
        self.thread = threading.Thread(
            target=self.worker, name="local-inference-worker", daemon=True
        )
        self.thread.start()

    def worker(self):
        """Process queued recordings serially to bound simultaneous model memory."""
        from prototype.pipeline import run_recording

        while not self.stop.is_set():
            next_job = None
            with self.lock:
                for path in sorted((self.state / "inbox").glob("*/job.json")):
                    job = json.loads(path.read_text())
                    if job["status"] == "queued":
                        job.update(status="processing", started_at=now())
                        atomic_json(path, job)
                        next_job = (path, job)
                        break
            if next_job is None:
                self.wakeup.wait(0.5)
                self.wakeup.clear()
                continue
            path, job = next_job
            event(
                self.state / "receiver.jsonl",
                "processor",
                "started",
                recording_id=job["recording_id"],
            )
            try:
                # Recheck integrity after disk queueing, before giving data to ASR.
                payload = path.parent / "recording.media"
                if (
                    payload.stat().st_size != job["input_bytes"]
                    or digest_file(payload) != job["sha256"]
                ):
                    raise ValueError("Persisted recording failed integrity check")
                result_directory, summary = run_recording(
                    payload,
                    self.model_directory,
                    self.state / "results",
                    self.queries,
                    log_content=self.log_content,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                job.update(
                    status=(
                        "completed"
                        if summary["status"] in ("ok", "no_speech")
                        else "failed"
                    ),
                    pipeline_status=summary["status"],
                    result_directory=result_directory.name,
                    latency_ms=summary["latency_ms"],
                )
            except Exception as error:
                job.update(status="failed", error_type=type(error).__name__)
            job["finished_at"] = now()
            with self.lock:
                atomic_json(path, job)
            event(
                self.state / "receiver.jsonl",
                "processor",
                "finished",
                recording_id=job["recording_id"],
                status=job["status"],
                result_directory=job.get("result_directory"),
                latency_ms=job.get("latency_ms"),
            )

    def close(self):
        self.stop.set()
        self.wakeup.set()
        if self.thread:
            # Graceful shutdown waits for the one active model call. No artificial
            # timeout claim: process isolation is a documented next step.
            self.thread.join()
        if self.state_lock:
            self.state_lock.close()
            self.state_lock = None


class Receiver(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, processor):
        self.processor = processor
        self.token = read_token(processor.state / "device.token")
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "SecureNote/0.2"

    def setup(self):
        super().setup()
        self.connection.settimeout(60)

    def log_message(self, *arguments):
        pass  # No request headers, private source names or tokens in access logs.

    def reply(self, status, value):
        encoded = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    def authorized(self):
        candidate = self.headers.get("Authorization", "")
        valid = hmac.compare_digest(
            candidate.encode("utf-8"), ("Bearer " + self.server.token).encode("ascii")
        )
        if not valid:
            event(
                self.server.processor.state / "receiver.jsonl",
                "authentication",
                "rejected",
            )
            self.reply(401, {"error": "unauthorized"})
        return valid

    def do_GET(self):
        if not self.authorized():
            return
        prefix = "/v1/jobs/"
        identifier = self.path[len(prefix) :] if self.path.startswith(prefix) else ""
        if len(identifier) != 32 or any(
            character not in "abcdef0123456789" for character in identifier
        ):
            return self.reply(404, {"error": "not_found"})
        path = self.server.processor.state / "inbox" / identifier / "job.json"
        with self.server.processor.lock:
            if not path.exists():
                return self.reply(404, {"error": "not_found"})
            job = json.loads(path.read_text())
        # The device gets a receipt/status, not transcript content or host paths.
        return self.reply(
            200,
            {
                key: job[key]
                for key in (
                    "recording_id",
                    "status",
                    "pipeline_status",
                    "input_bytes",
                    "sha256",
                    "result_directory",
                )
                if key in job
            },
        )

    def do_POST(self):
        started = time.perf_counter()
        processor = self.server.processor
        if not self.authorized():
            return
        if self.path != "/v1/recordings":
            return self.reply(404, {"error": "not_found"})
        staging = None
        try:
            if (
                self.headers.get("Transfer-Encoding")
                or len(self.headers.get_all("Content-Length", [])) != 1
            ):
                raise ValueError("One explicit Content-Length is required")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= MAX_BYTES:
                raise ValueError("Invalid upload size")
            encoded = self.headers.get("X-SecureNote-Manifest", "")
            if not 0 < len(encoded) <= 2048:
                raise ValueError("Missing or oversized manifest")
            manifest = validate_manifest(
                json.loads(base64.b64decode(encoded, validate=True))
            )
            if length != manifest["input_bytes"]:
                raise ValueError("Manifest/body size disagreement")
            identifier = manifest["recording_id"]
            # Serialize ingestion and job publication in this minimal service.
            with processor.lock:
                final = processor.state / "inbox" / identifier
                staging = processor.state / "inbox" / (identifier + ".pending")
                staging.mkdir(mode=0o700)
                digest = hashlib.sha256()
                remaining = length
                with (staging / "recording.media").open("wb") as output:
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("Incomplete upload")
                        output.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if digest.hexdigest() != manifest["sha256"]:
                    raise ValueError("Checksum mismatch")
                duplicate = final.exists()
                if duplicate:
                    existing = json.loads((final / "manifest.json").read_text())
                    if existing != manifest:
                        raise ValueError(
                            "Recording ID is already used by a different manifest"
                        )
                    shutil.rmtree(staging)
                else:
                    atomic_json(staging / "manifest.json", manifest)
                    atomic_json(
                        staging / "job.json",
                        {**manifest, "status": "queued", "received_at": now()},
                    )
                    staging.rename(final)
                staging = None
            event(
                processor.state / "receiver.jsonl",
                "transfer_validation",
                "accepted",
                recording_id=identifier,
                input_bytes=length,
                duplicate=duplicate,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            processor.wakeup.set()
            self.reply(
                200 if duplicate else 201,
                {
                    key: manifest[key]
                    for key in ("recording_id", "input_bytes", "sha256")
                }
                | {"status": "accepted"},
            )
        except (ValueError, OSError, KeyError, TypeError) as error:
            if staging:
                shutil.rmtree(staging, ignore_errors=True)
                staging = None
            event(
                processor.state / "receiver.jsonl",
                "transfer_validation",
                "rejected",
                error_type=type(error).__name__,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            self.reply(400, {"error": "upload_rejected"})
        finally:
            if staging:
                shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="SecureNote laptop/server receiver")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--state", default="laptop-state")
    serve = commands.add_parser("serve")
    serve.add_argument("--state", default="laptop-state")
    serve.add_argument("--model-dir", default="models/base.en")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--cert")
    serve.add_argument("--key")
    serve.add_argument("--query", action="append")
    args = parser.parse_args()
    if args.command == "init":
        state = initialize(args.state)
        print("Receiver initialized. Device token file:", state / "device.token")
        return
    if bool(args.cert) != bool(args.key) or (
        not loopback(args.host) and not (args.cert and args.key)
    ):
        parser.error(
            "Non-loopback listeners require --cert and --key; plaintext is for same-computer emulation only"
        )
    processor = Processor(args.state, args.model_dir, args.query)
    server = Receiver((args.host, args.port), processor)
    if args.cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.cert, args.key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    processor.start()
    print(
        "Receiver ready:",
        args.host,
        server.server_port,
        "- one local inference worker",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("Stopping; waiting for active inference to finish.")
    finally:
        server.server_close()
        processor.close()


if __name__ == "__main__":
    main()
