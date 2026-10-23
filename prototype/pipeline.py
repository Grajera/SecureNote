"""Explicit stages and registered local tools, with content-minimal JSONL logs."""

import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
import wave
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .analysis import (
    automatic_notes,
    render_notes,
    search_passages,
    sentence_passages,
    timestamp,
    validate_segments,
)

MAX_BYTES = 2 * 1024**3
MAX_SECONDS = 7200
# A bounded set of common self-contained media demuxers. Manifests are excluded.
MEDIA_FORMATS = "mov,matroska,webm,wav,mp3,flac,ogg,aac,asf,avi,mpeg,mpegts,aiff,au,amr,caf,wv,ape,flv"


def save_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


class RunLog:
    def __init__(self, directory, log_content=False):
        self.directory = directory
        self.log_content = log_content
        self.started = time.perf_counter()
        self.run_id = directory.name

    def emit(self, stage, event, **fields):
        record = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "event": event,
            **fields,
        }
        with (self.directory / "run.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    @contextmanager
    def stage(self, name):
        started = time.perf_counter()
        self.emit(name, "started")
        try:
            yield
        except BaseException as error:
            self.emit(
                name,
                "failed",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(error).__name__,
            )
            raise
        else:
            self.emit(
                name,
                "completed",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )


def execute_media_tool(arguments, timeout):
    """No shell, no URLs, no inherited stdin, no transcript-driven commands."""
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError as error:
        raise ValueError("FFmpeg and ffprobe must be installed and on PATH.") from error
    except subprocess.TimeoutExpired as error:
        raise ValueError("Media tool timed out.") from error
    if result.returncode:
        # Raw stderr can contain sensitive source names and embedded metadata.
        raise ValueError(
            "Media tool rejected this file. Check its format, audio track, and integrity."
        )
    return result.stdout


def inspect_media(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Input must be a regular local file, not a symbolic link.")
    size = path.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise ValueError("Input must be nonempty and no larger than 2 GiB.")
    raw = execute_media_tool(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-format_whitelist",
            MEDIA_FORMATS,
            "-show_entries",
            "format=duration,format_name:stream=codec_type,duration",
            "-of",
            "json",
            str(path),
        ],
        timeout=30,
    )
    metadata = json.loads(raw)
    audio_streams = [
        stream
        for stream in metadata.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise ValueError("Recording has no audio track.")
    try:
        duration = float(
            metadata["format"].get("duration", audio_streams[0].get("duration", "nan"))
        )
    except (ValueError, KeyError, TypeError) as error:
        duration = float("nan")
    # Browser MediaRecorder WebM files may have no container duration. They
    # still pass through bounded decoding below; ASR never receives unchecked
    # audio. Do not reject a valid local microphone recording for missing tags.
    duration_known = math.isfinite(duration)
    if duration_known and not 0 < duration <= MAX_SECONDS:
        raise ValueError("Recording must have a known duration of at most 2 hours.")
    return {
        "input_bytes": size,
        "duration_seconds": duration if duration_known else None,
        "source_duration_known": duration_known,
        "container": metadata["format"]["format_name"],
    }


def decode_audio(path, destination):
    execute_media_tool(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file",
            "-format_whitelist",
            MEDIA_FORMATS,
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-t",
            str(MAX_SECONDS + 1),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            str(destination),
        ],
        timeout=1800,
    )
    with wave.open(str(destination), "rb") as recording:
        duration = recording.getnframes() / recording.getframerate()
        if (
            recording.getnchannels(),
            recording.getframerate(),
            recording.getsampwidth(),
        ) != (1, 16000, 2):
            raise ValueError("Decoder returned the wrong audio format.")
        if not 0 < duration <= MAX_SECONDS:
            raise ValueError("Decoded audio exceeds the duration contract.")
    return {
        "duration_seconds": duration,
        "sample_rate_hz": 16000,
        "channels": 1,
        "sample_width_bytes": 2,
    }


def call_tool(name, log, **arguments):
    """Allowlisted tool-call boundary with fixed signatures; no arbitrary eval.

    The controller selects these tools. There is no LLM-selected agent loop.
    """
    registry = {
        "inspect_media": inspect_media,
        "decode_audio": decode_audio,
        "search_transcript": search_passages,
    }
    if name not in registry:
        raise ValueError("Unknown tool.")
    with log.stage("tool:" + name):
        result = registry[name](**arguments)
        if name == "search_transcript":
            # Enforce the second documented boundary, even for a replacement adapter.
            limit = arguments.get("limit", 5)
            if not isinstance(result, list) or len(result) > limit:
                raise ValueError("Retrieval tool returned an invalid result list.")
            by_id = {passage["id"]: passage for passage in arguments["passages"]}
            for match in result:
                if not isinstance(match, dict) or type(match.get("id")) is not int:
                    raise ValueError("Retrieval tool returned an invalid passage.")
                original = by_id.get(match["id"])
                score = match.get("score")
                if (
                    original is None
                    or any(match.get(key) != original[key] for key in original)
                    or type(score) not in (float, int)
                    or not math.isfinite(score)
                    or not 0 <= score <= 1.000001
                ):
                    raise ValueError(
                        "Retrieval result did not match the source transcript."
                    )
        log.emit(
            "tool:" + name,
            "result",
            result_count=len(result) if isinstance(result, list) else 1,
        )
        return result


def create_run(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    name = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    directory = root / name
    directory.mkdir(mode=0o700)
    return directory


from functools import lru_cache


@lru_cache(maxsize=1)
def load_model(model_path, device, compute_type, threads):
    """Reuse loaded weights between runs while keeping inference fully local."""
    from .gpu import configure_dlls

    configure_dlls()
    from faster_whisper import WhisperModel

    return WhisperModel(
        str(model_path),
        device=device,
        compute_type=compute_type,
        cpu_threads=threads,
        num_workers=1,
        local_files_only=True,
    )


def transcribe(audio_path, model_path, language, device, compute_type, threads):
    # Set offline mode before the model libraries are imported. An explicit
    # directory is required; run() never interprets the path as a Hub model ID.
    """Consume the lazy segment iterator so inference errors occur inside the stage."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from .gpu import configure_dlls

    configure_dlls()
    from faster_whisper import WhisperModel
    import numpy as np

    # Already-decoded PCM avoids doing a second media decode and makes the
    # model boundary explicit: a one-dimensional float32 waveform at 16 kHz.
    with wave.open(str(audio_path), "rb") as audio:
        samples = (
            np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(
                np.float32
            )
            / 32768.0
        )
    model = load_model(str(model_path), device, compute_type, threads)
    segments, info = model.transcribe(
        samples,
        language=language,
        beam_size=5,
        temperature=0,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    # faster-whisper is lazy: iteration is inside this inference timing boundary.
    result = [
        {
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip(),
        }
        for segment in segments
        if segment.text.strip()
    ]
    return result, {
        "language": info.language,
        "language_probability": info.language_probability,
    }


def run_recording(
    input_path,
    model_path,
    output_root="runs",
    queries=None,
    language="en",
    device="cpu",
    compute_type="int8",
    threads=4,
    log_content=False,
    inject_invalid_segment=False,
):
    os.umask(0o077)  # POSIX defense; Windows permissions come from the parent ACL.
    directory = create_run(output_root)
    log = RunLog(directory, log_content)
    original = Path(input_path).expanduser().absolute()
    model_path = Path(model_path).expanduser().absolute()
    summary = {
        "schema_version": "1.0",
        "run_id": directory.name,
        "status": "running",
        "runtime": {
            "os": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "model": {
            "directory_name": model_path.name,
            "device": device,
            "compute_type": compute_type,
            "cpu_threads": threads,
        },
        "content_logging": log_content,
        "failure_injection": inject_invalid_segment,
    }
    log.emit(
        "input",
        "received",
        input_bytes=original.stat().st_size if original.is_file() else 0,
    )
    try:
        with log.stage("validation"):
            for query in queries or []:
                if not query.strip() or len(query) > 512:
                    raise ValueError("Search query must contain 1 to 512 characters.")
            media = call_tool("inspect_media", log, path=original)
            required_model_files = ("model.bin", "config.json", "tokenizer.json")
            if not model_path.is_dir() or not all(
                (model_path / name).is_file() for name in required_model_files
            ):
                raise ValueError(
                    "Local model is incomplete. Run download-model during setup first."
                )
            summary.update(media)
            log.emit("validation", "accepted", **media)
        # Keep plaintext intermediates inside the selected output volume. Temporary
        # data is deleted on normal completion and handled exceptions, not power loss.
        with tempfile.TemporaryDirectory(prefix="audio-", dir=directory) as temporary:
            audio_path = Path(temporary) / "recording.wav"
            with log.stage("preprocessing"):
                decoded = call_tool(
                    "decode_audio", log, path=original, destination=audio_path
                )
                summary["decoded_audio"] = decoded
                summary["duration_seconds"] = decoded["duration_seconds"]
            with log.stage("model_inference"):
                segments, recognition = transcribe(
                    audio_path, model_path, language, device, compute_type, threads
                )
                summary["recognition"] = recognition
        with log.stage("postprocessing"):
            if inject_invalid_segment:
                segments = [{"start": 0.0, "end": 1.0, "text": 123}]
            validate_segments(segments, decoded["duration_seconds"])
            passages = sentence_passages(segments)
            sections = automatic_notes(passages)
            summary["segment_count"] = len(segments)
            summary["transcript_characters"] = sum(
                len(segment["text"]) for segment in segments
            )
        with log.stage("retrieval"):
            results = {
                query: call_tool(
                    "search_transcript", log, passages=passages, query=query
                )
                for query in queries
                or ["decision action deadline important definition risk"]
            }
        with log.stage("output"):
            notes = render_notes(sections, results, bool(segments))
            save_json(
                directory / "transcript.json",
                {"schema_version": "1.0", "segments": segments, "passages": passages},
            )
            (directory / "transcript.txt").write_text(
                "\n".join(
                    f"[{timestamp(segment['start'])} - {timestamp(segment['end'])}] {segment['text']}"
                    for segment in segments
                ),
                encoding="utf-8",
            )
            save_json(directory / "notes.json", sections)
            save_json(directory / "search.json", results)
            (directory / "notes.md").write_text(notes, encoding="utf-8")
            summary["output"] = {
                "files": [
                    "notes.md",
                    "notes.json",
                    "transcript.txt",
                    "transcript.json",
                    "search.json",
                ],
                "note_count": sum(map(len, sections.values())),
                "notes_sha256": hashlib.sha256(notes.encode()).hexdigest(),
                "search_matches": sum(map(len, results.values())),
            }
            log.emit(
                "output",
                "result",
                **summary["output"],
                **({"notes": notes} if log_content else {}),
            )
        summary["status"] = "ok" if segments else "no_speech"
    except (Exception, KeyboardInterrupt) as error:
        summary["status"] = (
            "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
        )
        summary["error_type"] = type(error).__name__
        if isinstance(error, ModuleNotFoundError):
            summary["missing_module"] = error.name
        log.emit("run", "failed", error_type=type(error).__name__)
        # Console uses a safe generic message for third-party errors, since model
        # and subprocess exceptions can contain user paths or recording content.
        summary["error"] = (
            "Missing Python module: "
            + str(error.name)
            + ". Reinstall requirements.txt."
            if isinstance(error, ModuleNotFoundError)
            else (
                "Processing was cancelled."
                if isinstance(error, KeyboardInterrupt)
                else (
                    str(error)
                    if type(error) is ValueError
                    else "Processing failed. Check dependencies, local model files, and available memory."
                )
            )
        )
    finally:
        summary["latency_ms"] = round((time.perf_counter() - log.started) * 1000, 2)
        log.emit(
            "run",
            "finished",
            status=summary["status"],
            latency_ms=summary["latency_ms"],
        )
        save_json(directory / "summary.json", summary)
    return directory, summary


def search_existing(directory, query, limit=5, log_content=False):
    directory = Path(directory)
    transcript = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    validate_segments(
        transcript["segments"], summary["decoded_audio"]["duration_seconds"]
    )
    passages = sentence_passages(transcript["segments"])
    log = RunLog(directory, log_content)
    log.emit("search", "received", input_characters=len(query))
    results = call_tool(
        "search_transcript", log, passages=passages, query=query, limit=limit
    )
    search_id = uuid.uuid4().hex[:8]
    result_name = "search-" + search_id + ".json"
    save_json(directory / result_name, {"query": query, "results": results})
    log.emit(
        "search",
        "result",
        matches=len(results),
        output=result_name,
        latency_ms=round((time.perf_counter() - log.started) * 1000, 2),
        **({"query": query, "results": results} if log_content else {}),
    )
    return results
