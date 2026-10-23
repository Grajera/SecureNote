"""Review catalog and annotations; original transcripts remain unchanged."""

import json
import math
import re
import threading
import uuid
from pathlib import Path

from .analysis import automatic_notes, safe_markdown, sentence_passages, timestamp, validate_segments
from .pipeline import execute_media_tool, inspect_media
from .transfer import atomic_json


def validate_identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid recording identifier")
    return value


def parse_range(header, size):
    """Single HTTP byte range, including suffix/open ranges, for media seeking."""
    if header is None:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match or not any(match.groups()):
        raise ValueError("Invalid media range")
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix <= 0:
            raise ValueError("Invalid suffix range")
        return max(0, size - suffix), size - 1, True
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError("Unsatisfiable media range")
    return start, end, True


class ReviewStore:
    def __init__(self, state, roots):
        self.state = Path(state).absolute()
        self.roots = list(dict.fromkeys([self.state, *(Path(root).absolute() for root in roots)]))
        self.lock = threading.RLock()
        self.previews = {}
        self.durations = {}
        self.titles = {}
        (self.state / "reviews").mkdir(parents=True, exist_ok=True)
        (self.state / "previews").mkdir(exist_ok=True)

    def locate(self, identifier):
        validate_identifier(identifier)
        for root in self.roots:
            path = root / "inbox" / identifier / "job.json"
            if path.is_file():
                return root, json.loads(path.read_text(encoding="utf-8"))
        raise FileNotFoundError("Recording not found")

    def annotation(self, identifier):
        validate_identifier(identifier)
        path = self.state / "reviews" / (identifier + ".json")
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"version": 0, "title": "", "reviewed": False, "edits": {}, "hidden": [], "bookmarks": []}

    def suggested_title(self, root, job):
        key = (job["recording_id"], job.get("result_directory"))
        if key in self.titles:
            return self.titles[key]
        name = job.get("result_directory", "")
        if re.fullmatch(r"\d{8}T\d{6}-[a-f0-9]{8}", name):
            path = root / "results" / name / "transcript.json"
            if path.is_file():
                segments = json.loads(path.read_text(encoding="utf-8")).get("segments", [])
                if segments:
                    text = str(segments[0].get("text", "")).strip()
                    title = text[:80] + ("…" if len(text) > 80 else "")
                    if title:
                        self.titles[key] = title
                        return title
        return "Recording · " + job.get("captured_at", "")[:16].replace("T", " ")

    def catalog(self):
        recordings = {}
        for root in self.roots:
            for path in (root / "inbox").glob("*/job.json"):
                try:
                    job = json.loads(path.read_text(encoding="utf-8"))
                    identifier = validate_identifier(job["recording_id"])
                    annotation = self.annotation(identifier)
                    recordings.setdefault(identifier, {"id": identifier, "title": annotation["title"] or self.suggested_title(root, job),
                        "status": job["status"], "reviewed": annotation["reviewed"],
                        "created_at": job.get("captured_at", ""), "input_bytes": job["input_bytes"],
                        "device": job.get("device_id", "Recorder")})
                except (OSError, ValueError, KeyError, TypeError):
                    continue  # An unrelated/broken job never hides the rest of the library.
        return sorted(recordings.values(), key=lambda recording: recording["created_at"], reverse=True)

    def detail(self, identifier):
        root, job = self.locate(identifier)
        annotation = self.annotation(identifier)
        result = {"id": identifier, "title": annotation["title"] or self.suggested_title(root, job),
                  "status": job["status"], "device": job.get("device_id", "Recorder"),
                  "created_at": job.get("captured_at"), "annotation": annotation,
                  "segments": [], "notes": [], "duration": self.durations.get(identifier, 0), "error": None,
                  "preview": self.preview_status(identifier)}
        directory_name = job.get("result_directory", "")
        # A result directory name is an internal ID, never a client-supplied path.
        if not re.fullmatch(r"\d{8}T\d{6}-[a-f0-9]{8}", directory_name):
            return result
        directory = root / "results" / directory_name
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        result["error"] = summary.get("error")
        result["duration"] = summary.get("decoded_audio", {}).get("duration_seconds", 0)
        if not (directory / "transcript.json").is_file():
            return result
        transcript = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
        segments = validate_segments(transcript["segments"], result["duration"])
        result["segments"] = segments
        # Re-derive current selection from evidence: upgrading old runs needs no ASR.
        sections = automatic_notes(sentence_passages(segments))
        for category, passages in sections.items():
            for passage in passages:
                note_id = str(passage["id"])
                result["notes"].append({**passage, "id": note_id, "category": category,
                    "text": annotation["edits"].get(note_id, passage["text"]),
                    "source_text": passage["text"], "edited": note_id in annotation["edits"],
                    "hidden": note_id in annotation["hidden"]})
        return result

    def save_annotation(self, identifier, changes):
        with self.lock:
            self.locate(identifier)
            annotation = self.annotation(identifier)
            if not isinstance(changes, dict) or set(changes) - {"version", "title", "reviewed", "edits", "hidden", "bookmarks"}:
                raise ValueError("Invalid review update")
            if type(changes.get("version")) is not int or changes["version"] != annotation["version"]:
                raise RuntimeError("This review changed in another tab. Reload before saving.")
            updated = {**annotation, **changes, "version": annotation["version"] + 1}
            if not isinstance(updated["title"], str) or len(updated["title"]) > 200 or type(updated["reviewed"]) is not bool:
                raise ValueError("Invalid recording title or review state")
            detail = self.detail(identifier)
            note_ids = {note["id"] for note in detail["notes"]}
            if not isinstance(updated["edits"], dict) or any(key not in note_ids or not isinstance(value, str)
                or not 1 <= len(value.strip()) <= 5000 for key, value in updated["edits"].items()):
                raise ValueError("Invalid note edit")
            if not isinstance(updated["hidden"], list) or any(value not in note_ids for value in updated["hidden"]):
                raise ValueError("Invalid hidden note")
            if not isinstance(updated["bookmarks"], list) or len(updated["bookmarks"]) > 1000:
                raise ValueError("Invalid bookmarks")
            seen = set()
            for bookmark in updated["bookmarks"]:
                if not isinstance(bookmark, dict) or set(bookmark) != {"id", "start", "text"}:
                    raise ValueError("Invalid bookmark")
                validate_identifier(bookmark["id"])
                if (bookmark["id"] in seen or type(bookmark["start"]) not in (float, int)
                    or not math.isfinite(bookmark["start"]) or not 0 <= bookmark["start"] <= max(detail["duration"], 0)
                    or not isinstance(bookmark["text"], str) or not 1 <= len(bookmark["text"].strip()) <= 1000):
                    raise ValueError("Invalid bookmark content")
                seen.add(bookmark["id"])
            atomic_json(self.state / "reviews" / (identifier + ".json"), updated)
            return updated

    def preview_path(self, identifier):
        validate_identifier(identifier)
        return self.state / "previews" / (identifier + ".mp3")

    def preview_status(self, identifier):
        if self.preview_path(identifier).is_file():
            return "ready"
        return self.previews.get(identifier, "not_prepared")

    def prepare_preview(self, identifier):
        root, job = self.locate(identifier)
        with self.lock:
            if self.preview_status(identifier) in ("ready", "preparing"):
                return self.preview_status(identifier)
            self.previews[identifier] = "preparing"
        def convert():
            temporary = self.preview_path(identifier).with_suffix(".pending.mp3")
            try:
                self.durations[identifier] = inspect_media(root / "inbox" / identifier / "recording.media")["duration_seconds"]
                execute_media_tool(["ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file",
                    "-i", str(root / "inbox" / identifier / "recording.media"), "-map", "0:a:0",
                    "-vn", "-sn", "-dn", "-t", "7201", "-ac", "1", "-ar", "44100",
                    "-c:a", "libmp3lame", "-b:a", "128k", "-map_metadata", "-1", str(temporary)], timeout=1800)
                metadata = json.loads(execute_media_tool(["ffprobe", "-v", "error", "-protocol_whitelist", "file",
                    "-show_entries", "format=duration", "-of", "json", str(temporary)], timeout=30))
                preview_duration = float(metadata["format"]["duration"])
                if not math.isfinite(preview_duration) or preview_duration > 7200.1:
                    raise ValueError("Playback exceeds the recording duration limit")
                if not self.durations.get(identifier):
                    self.durations[identifier] = preview_duration
                temporary.replace(self.preview_path(identifier))
                self.previews[identifier] = "ready"
            except Exception:
                self.previews[identifier] = "failed"
            finally:
                temporary.unlink(missing_ok=True)
        threading.Thread(target=convert, name="playback-preview", daemon=True).start()
        return "preparing"

    def export(self, identifier, transcript_only=False):
        detail = self.detail(identifier)
        if transcript_only:
            return "\n".join(f"[{timestamp(segment['start'])}] {segment['text']}" for segment in detail["segments"])
        lines = ["# " + safe_markdown(detail["title"]), "", "Reviewed: " + str(detail["annotation"]["reviewed"]), ""]
        for category in ("Decisions", "Action items", "Key points", "Follow-ups"):
            notes = [note for note in detail["notes"] if note["category"] == category and not note["hidden"]]
            if notes:
                lines += ["## " + category, ""]
                lines += [f"- [{timestamp(note['start'])}] {safe_markdown(note['text'])}" + (" (edited)" if note["edited"] else "") for note in notes]
                lines.append("")
        if detail["annotation"]["bookmarks"]:
            lines += ["## Personal bookmarks", ""]
            lines += [f"- [{timestamp(bookmark['start'])}] {safe_markdown(bookmark['text'])}" for bookmark in detail["annotation"]["bookmarks"]]
        lines += ["", "## Full transcript", "", "\n".join(safe_markdown(line) for line in self.export(identifier, True).splitlines())]
        return "\n".join(lines)
