"""Run with Python 3.10-3.12. No network listener or hosted inference API."""

import argparse
import importlib.metadata
import json
import os
import shutil
import sys
from pathlib import Path

from prototype.pipeline import run_recording, search_existing


def main():
    parser = argparse.ArgumentParser(
        description="SecureNote: private local recording notes and search"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser(
        "download-model", help="SETUP ONLY: download model weights, no recording input"
    )
    download.add_argument(
        "--model",
        choices=["tiny.en", "base.en", "small.en", "base", "small"],
        default="base.en",
    )
    download.add_argument("--destination", type=Path)
    commands.add_parser("doctor", help="Check dependencies; never downloads a model")
    run = commands.add_parser("run", help="Process one local media file offline")
    run.add_argument("input", type=Path)
    run.add_argument("--model-dir", type=Path, default=Path("models/base.en"))
    run.add_argument(
        "--output",
        default="runs",
        help="Parent directory, ideally on an encrypted volume",
    )
    run.add_argument(
        "--query", action="append", help="Repeat to search multiple questions/keywords"
    )
    run.add_argument(
        "--language", default="en", help="Use auto only with a multilingual model"
    )
    run.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    run.add_argument(
        "--compute-type",
        choices=["int8", "float32", "float16", "int8_float16"],
        default="int8",
    )
    run.add_argument("--threads", type=int, default=4)
    run.add_argument(
        "--log-content",
        action="store_true",
        help="Synthetic demos ONLY: duplicate notes into log",
    )
    run.add_argument(
        "--inject-invalid-segment",
        action="store_true",
        help="FAILURE TEST: corrupt the ASR adapter result",
    )
    search = commands.add_parser(
        "search", help="Search an existing transcript locally, without rerunning ASR"
    )
    search.add_argument("run_directory", type=Path)
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.command == "doctor":
        for executable in ("ffmpeg", "ffprobe"):
            print(
                f"{executable}: {shutil.which(executable) or 'MISSING - install FFmpeg'}"
            )
        for package in ("faster-whisper", "ctranslate2", "huggingface-hub"):
            try:
                print(f"{package}: {importlib.metadata.version(package)}")
            except importlib.metadata.PackageNotFoundError:
                print(f"{package}: MISSING - install requirements.txt")
        print(
            "Default model: models/base.en -",
            "present" if Path("models/base.en/model.bin").is_file() else "MISSING",
        )
        try:
            from faster_whisper import WhisperModel

            print("Whisper runtime import: OK")
        except (ImportError, OSError) as error:
            print("Whisper runtime import FAILED:", str(error))
            return 2
        return 0
    if args.command == "download-model":
        # This is the only application command permitted to access the internet.
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from huggingface_hub import snapshot_download

        destination = args.destination or Path("models") / args.model
        snapshot_download(
            "Systran/faster-whisper-" + args.model,
            local_dir=destination,
            allow_patterns=["*.json", "*.bin", "*.txt"],
        )
        print("Model ready:", destination)
        return 0
    if args.command == "search":
        matches = search_existing(args.run_directory, args.query, args.limit)
        print(
            json.dumps(matches, ensure_ascii=False, indent=2)
            if matches
            else "No matching passages found."
        )
        return 0
    if args.threads < 1 or args.threads > 64:
        parser.error("--threads must be between 1 and 64")
    directory, summary = run_recording(
        args.input,
        args.model_dir,
        args.output,
        args.query,
        None if args.language == "auto" else args.language,
        args.device,
        args.compute_type,
        args.threads,
        args.log_content,
        args.inject_invalid_segment,
    )
    print("Run directory:", directory)
    print("Status:", summary["status"])
    print("Elapsed seconds:", summary["latency_ms"] / 1000)
    if summary["status"] in ("failed", "cancelled"):
        print("Error:", summary["error"], file=sys.stderr)
        return 2
    print("Notes:", directory / "notes.md")
    print("Transcript:", directory / "transcript.txt")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(
            "Command failed:",
            type(error).__name__,
            "- check paths and arguments.",
            file=sys.stderr,
        )
        raise SystemExit(2)
