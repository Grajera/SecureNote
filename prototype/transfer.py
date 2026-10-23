"""Portable device/processor wire contract. Standard library only."""

import hashlib
import ipaddress
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 2 * 1024 ** 3


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    """Publish complete state; readers never see a partially written JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def digest_file(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported recording manifest version")
    if not isinstance(manifest.get("recording_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", manifest["recording_id"]):
        raise ValueError("Invalid recording ID")
    if not isinstance(manifest.get("device_id"), str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", manifest["device_id"]):
        raise ValueError("Invalid device ID")
    if type(manifest.get("input_bytes")) is not int or not 0 < manifest["input_bytes"] <= MAX_BYTES:
        raise ValueError("Invalid recording size")
    if not isinstance(manifest.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", manifest["sha256"]):
        raise ValueError("Invalid checksum")
    if not isinstance(manifest.get("captured_at"), str) or len(manifest["captured_at"]) > 64:
        raise ValueError("Invalid capture timestamp")
    datetime.fromisoformat(manifest["captured_at"])
    if set(manifest) != {"schema_version", "recording_id", "device_id", "input_bytes", "sha256", "captured_at"}:
        raise ValueError("Unexpected manifest fields")
    return manifest


def loopback(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_endpoint(endpoint):
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Use a server origin such as https://laptop.example:8765")
    if parsed.scheme == "http" and not loopback(parsed.hostname):
        raise ValueError("HTTP is permitted only for same-computer loopback emulation; use HTTPS across machines")
    return parsed


def read_token(path):
    value = Path(path).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Expected a SecureNote token file created by laptop.py init")
    return value


def event(path, stage, event_name, **fields):
    record = {"timestamp": now(), "stage": stage, "event": event_name, **fields}
    with Path(path).open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, allow_nan=False) + "\n")
