"""Exercise the intended two-role deployment as separate processes on one PC."""

import argparse
import base64
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from device import enqueue, remote_status
from prototype.transfer import atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("demo-two-role"))
    parser.add_argument("--model-dir", type=Path, default=Path("models/base.en"))
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists():
        raise SystemExit(
            "Choose a new --output folder to preserve previous demo evidence"
        )
    output.mkdir(parents=True)
    state = output / "laptop"
    spool = output / "device"
    python = sys.executable
    subprocess.run(
        [python, str(ROOT / "laptop.py"), "init", "--state", str(state)], check=True
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    endpoint = f"http://127.0.0.1:{port}"
    token = state / "device.token"
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
    output_log = (output / "receiver-console.txt").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [
            python,
            str(ROOT / "laptop.py"),
            "serve",
            "--state",
            str(state),
            "--model-dir",
            str(args.model_dir.absolute()),
            "--port",
            str(port),
        ],
        stdout=output_log,
        stderr=subprocess.STDOUT,
        env=environment,
    )
    evidence = {
        "deployment": "two independent processes, recorder -> loopback HTTP -> processor",
        "model_inference": "local CPU int8, no hosted API",
        "runs": [],
    }
    try:
        deadline = time.monotonic() + 20
        while True:
            if server.poll() is not None:
                raise RuntimeError("Receiver exited; inspect receiver-console.txt")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError("Receiver did not start")
                time.sleep(0.1)
        for label, filename in [
            ("business", "business.wav"),
            ("lecture", "lecture.mp3"),
            ("planning", "planning.mp4"),
        ]:
            before = set(spool.glob("*/manifest.json"))
            source = ROOT / "examples" / "media" / filename
            started = time.perf_counter()
            subprocess.run(
                [
                    python,
                    str(ROOT / "device.py"),
                    "enqueue",
                    str(source),
                    "--spool",
                    str(spool),
                ],
                check=True,
            )
            manifest_path = next(iter(set(spool.glob("*/manifest.json")) - before))
            manifest = json.loads(manifest_path.read_text())
            subprocess.run(
                [
                    python,
                    str(ROOT / "device.py"),
                    "send",
                    "--spool",
                    str(spool),
                    "--endpoint",
                    endpoint,
                    "--token-file",
                    str(token),
                ],
                check=True,
            )
            identifier = manifest["recording_id"]
            deadline = time.monotonic() + 300
            while True:
                status = remote_status(identifier, endpoint, token)
                if status["status"] in ("completed", "failed"):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Processor did not finish in five minutes")
                time.sleep(0.1)
            assert status["status"] == "completed", status
            summary_path = (
                state / "results" / status["result_directory"] / "summary.json"
            )
            summary = json.loads(summary_path.read_text())
            evidence["runs"].append(
                {
                    "label": label,
                    "input": filename,
                    "manifest": manifest,
                    "job": status,
                    "summary": summary,
                    "transfer_and_processing_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                }
            )
            print(
                label,
                status["status"],
                summary["output"]["note_count"],
                "notes",
                flush=True,
            )
        # Intentional failure: corrupt upload bytes after constructing a valid
        # device manifest. The receiver must reject before publishing any job.
        failure_device = enqueue(
            ROOT / "examples/media/business.wav", output / "failure-device"
        )
        manifest = json.loads((failure_device / "manifest.json").read_text())
        payload = bytearray((failure_device / "recording.media").read_bytes())
        payload[0] ^= 1
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        client.request(
            "POST",
            "/v1/recordings",
            body=payload,
            headers={
                "Authorization": "Bearer " + token.read_text(),
                "X-SecureNote-Manifest": base64.b64encode(
                    json.dumps(manifest).encode()
                ).decode(),
            },
        )
        response = client.getresponse()
        assert response.status == 400
        response.read()
        client.close()
        assert not (state / "inbox" / manifest["recording_id"]).exists()
        assert (
            json.loads((failure_device / "delivery.json").read_text())["status"]
            == "queued"
        )
        evidence["failure"] = {
            "change": "one upload byte flipped, original manifest checksum retained",
            "http_status": 400,
            "published_job": False,
            "device_status": "queued",
            "recording_id": manifest["recording_id"],
        }
        atomic_json(output / "evidence.json", evidence)
        lines = [
            "# Two-role prototype evidence",
            "",
            "Separate recorder and receiver processes; actual local HTTP upload and local model inference.",
            "",
        ]
        for example in evidence["runs"]:
            summary = example["summary"]
            result = state / "results" / example["job"]["result_directory"]
            lines += [
                "## " + example["label"],
                "",
                f"Input: {example['input']}; bytes: {example['manifest']['input_bytes']}",
                f"Job: {example['job']['status']}; pipeline: {summary['status']}",
                f"Capture/transfer/processing wall time: {example['transfer_and_processing_ms']} ms",
                "",
                (result / "notes.md").read_text(encoding="utf-8"),
                "",
            ]
        (output / "EVIDENCE.md").write_text("\n".join(lines), encoding="utf-8")
        print("Demo complete. Device queue:", spool)
        print("Laptop outputs:", state / "results")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        output_log.close()
        # A reusable authentication token is a local deployment secret, not
        # submission evidence. Production/manual deployments retain their token.
        token.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
