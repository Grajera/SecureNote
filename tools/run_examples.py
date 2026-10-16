"""Reproduce three real ASR runs, a controlled failure, and silent audio.

Run from the project folder:
  python tools/run_examples.py --model-dir models/base.en
Use --output examples/verified for submission evidence. It never downloads.
"""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import socket
import sys
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prototype.pipeline import run_recording, save_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=Path("models/base.en"))
    parser.add_argument("--output", type=Path, default=Path("examples/reproduced"))
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Choose a new --output folder; existing evidence is never overwritten.")
    args.output.mkdir(parents=True)
    recordings = [("business", "business.wav", "budget deadline"),
                  ("lecture", "lecture.mp3", "discount factor homework"),
                  ("planning", "planning.mp4", "battery encrypted")]
    evidence = []

    def deny_network(*unused, **ignored):
        raise AssertionError("Python network access is forbidden during this offline test")

    # This blocks Python socket connections during real model inference. FFmpeg
    # is separately restricted to local file protocol and bounded demuxers.
    with patch.object(socket.socket, "connect", deny_network), patch.object(socket.socket, "connect_ex", deny_network):
        for label, filename, query in recordings:
            source = Path("examples/media") / filename
            directory, summary = run_recording(source, args.model_dir, args.output / "runs",
                                               [query], log_content=True)
            assert summary["status"] == "ok", summary
            evidence.append({"label": label, "input": str(source), "query": query,
                             "run_directory": str(directory), "summary": summary})
            print(label, summary["status"], summary["latency_ms"], "ms", flush=True)
        directory, summary = run_recording(Path("examples/media/business.wav"), args.model_dir,
                                           args.output / "runs", ["budget"],
                                           inject_invalid_segment=True)
        assert summary["status"] == "failed" and summary["error_type"] == "ValueError", summary
        assert not (directory / "notes.md").exists()
        evidence.append({"label": "malformed_model_output", "run_directory": str(directory), "summary": summary})
        silence = args.output / "silence.wav"
        with wave.open(str(silence), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\0\0" * 32000)
        directory, summary = run_recording(silence, args.model_dir, args.output / "runs")
        assert summary["status"] == "no_speech" and summary["output"]["note_count"] == 0, summary
        evidence.append({"label": "silence", "run_directory": str(directory), "summary": summary})
    manifest = {"python_socket_connections_blocked": True,
                "packages": {package: importlib.metadata.version(package) for package in
                             ["faster-whisper", "ctranslate2", "numpy", "onnxruntime", "av", "huggingface-hub", "tokenizers"]},
                "model_files": [{"name": path.name, "bytes": path.stat().st_size,
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                                 for path in sorted(args.model_dir.iterdir())
                                 if path.is_file() and path.name in {"model.bin", "config.json", "tokenizer.json", "vocabulary.txt", "vocabulary.json", "preprocessor_config.json"}],
                "runs": evidence}
    save_json(args.output / "evidence.json", manifest)
    lines = ["# Verified example evidence", "", "These are measured local CPU runs with Python socket connections blocked.",
             "Synthetic speech only. Full transcript, notes, logs and summaries are in each run folder.", ""]
    for example in evidence:
        directory = Path(example["run_directory"])
        summary = example["summary"]
        lines += ["## " + example["label"], "", f"Run folder: `{directory}`", "",
                  f"Status: {summary['status']}; elapsed: {summary['latency_ms']} ms", ""]
        if "input" in example:
            lines += [f"Input: `{example['input']}`; search: `{example['query']}`", "",
                      (directory / "notes.md").read_text(encoding="utf-8"), ""]
        logs = [json.loads(line) for line in (directory / "run.jsonl").read_text().splitlines()]
        excerpt = [event for event in logs if (event["event"] in ["completed", "failed", "finished"]
                   and event["stage"] in ["validation", "model_inference", "postprocessing", "retrieval", "run"])]
        # Compact fields are a presentation projection of genuine JSONL events.
        lines += ["```json", json.dumps([{key: event[key] for key in ("stage", "event", "latency_ms", "status", "error_type") if key in event}
                    for event in excerpt], indent=2), "```", ""]
    (args.output / "EVIDENCE.md").write_text("\n".join(lines), encoding="utf-8")
    print("Evidence:", args.output / "EVIDENCE.md")


if __name__ == "__main__":
    main()
