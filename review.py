"""Local review workspace. Launch: python review.py

The existing recorder/receiver protocol remains intact. Browser imports use the
same recorder spool and actual authenticated HTTP transfer into the processor.
This viewer binds only to loopback; it is not a network deployment frontend.
"""

import argparse
import hmac
import json
import os
import secrets
import shutil
import tempfile
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from device import enqueue, send_one
from laptop import Handler, Processor
from prototype.analysis import search_passages, sentence_passages
from prototype.review import ReviewStore, parse_range, validate_identifier
from prototype.transfer import MAX_BYTES, read_token

ROOT = Path(__file__).resolve().parent


class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, processor, roots=()):
        self.processor = processor
        self.token = read_token(processor.state / "device.token")
        self.store = ReviewStore(processor.state, roots)
        self.launch_key = secrets.token_hex(32)
        self.session = secrets.token_hex(32)
        self.csrf = secrets.token_hex(32)
        super().__init__(address, WorkspaceHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.cookie_name = "securenote_" + str(self.server_port)

    def ingest(self, source, title):
        capture = enqueue(source, self.processor.state / "review-device", "laptop-recorder-emulator")
        delivery = send_one(capture, self.origin, self.processor.state / "device.token")
        if delivery["status"] != "delivered":
            raise ValueError("Transfer failed; the recorder copy remains queued locally")
        annotation = self.store.annotation(capture.name)
        self.store.save_annotation(capture.name, {"version": annotation["version"], "title": title[:200]})
        return capture.name


class WorkspaceHandler(Handler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def host_ok(self):
        if self.headers.get("Host") != urlsplit(self.server.origin).netloc:
            self.reply(403, {"error": "Unrecognized local host"})
            return False
        return True

    def session_ok(self, mutation=False):
        if not self.host_ok():
            return False
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            self.reply(401, {"error": "Invalid local review session"})
            return False
        value = cookies.get(self.server.cookie_name)
        if not value or not hmac.compare_digest(value.value.encode(), self.server.session.encode()):
            self.reply(401, {"error": "Open the launch link printed by review.py to reconnect"})
            return False
        if mutation and (self.headers.get("Origin") != self.server.origin or
                not hmac.compare_digest(self.headers.get("X-Review-CSRF", "").encode(), self.server.csrf.encode())):
            self.reply(403, {"error": "Review session validation failed"})
            return False
        return True

    def send_bytes(self, data, content_type, status=200, extra=None, head=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if self.headers.get("Transfer-Encoding") or not 0 < length <= 131072:
            raise ValueError("Invalid review request size")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("Expected a review object")
        return value

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        if self.path.startswith("/v1/"):
            if not self.host_ok():
                return
            return super().do_GET()
        parsed = urlsplit(self.path)
        if parsed.path == "/favicon.ico":
            if not self.host_ok():
                return
            return self.send_bytes(b"", "image/x-icon", 204, head=head)
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if parsed.path in assets:
            if not self.host_ok():
                return
            filename, content_type = assets[parsed.path]
            return self.send_bytes((ROOT / "review_static" / filename).read_bytes(), content_type, head=head)
        if not self.session_ok():
            return
        try:
            if parsed.path == "/api/session":
                return self.reply(200, {"csrf": self.server.csrf})
            if parsed.path == "/api/search":
                return self.reply(200, self.server.store.search(parse_qs(parsed.query).get("q", [""])[0]))
            if parsed.path == "/api/engine":
                return self.reply(200, {"device": self.server.processor.device, "compute_type": self.server.processor.compute_type})
            if parsed.path == "/api/jobs":
                return self.reply(200, self.server.store.catalog(parse_qs(parsed.query).get("trash") == ["1"]))
            parts = parsed.path.strip("/").split("/")
            if len(parts) not in (3, 4) or parts[:2] != ["api", "jobs"]:
                return self.reply(404, {"error": "Not found"})
            identifier = validate_identifier(parts[2])
            if len(parts) == 3:
                return self.reply(200, self.server.store.detail(identifier))
            if parts[3] == "media":
                self.server.store.locate(identifier)
                path = self.server.store.preview_path(identifier)
                if not path.is_file():
                    return self.reply(404, {"error": "Playback preview is not ready"})
                size = path.stat().st_size
                try:
                    start, end, partial = parse_range(self.headers.get("Range"), size)
                except ValueError:
                    return self.send_bytes(b"", "audio/mpeg", 416, {"Content-Range": f"bytes */{size}"}, head)
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if not head:
                    with path.open("rb") as media:
                        media.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            chunk = media.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                return
            if parts[3] == "search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                detail = self.server.store.detail(identifier)
                matches = search_passages(sentence_passages(detail["segments"]), query, 20)
                return self.reply(200, matches)
            if parts[3] == "export":
                transcript_only = parse_qs(parsed.query).get("format") == ["transcript"]
                text = self.server.store.export(identifier, transcript_only)
                name = "transcript.txt" if transcript_only else "meeting-notes.md"
                return self.send_bytes(text.encode(), "text/plain; charset=utf-8", extra={
                    "Content-Disposition": 'attachment; filename="' + name + '"'}, head=head)
            return self.reply(404, {"error": "Not found"})
        except FileNotFoundError:
            self.reply(404, {"error": "Recording not found"})
        except (ValueError, KeyError, TypeError):
            self.reply(400, {"error": "Invalid request or incomplete recording data"})
        except (BrokenPipeError, ConnectionResetError):
            pass  # Media seeking commonly cancels a previous byte-range response.

    def do_POST(self):
        if self.path.startswith("/v1/"):
            if not self.host_ok():
                return
            return super().do_POST()
        if self.path == "/api/session":
            if not self.host_ok():
                return
            valid = self.headers.get("Origin") == self.server.origin and hmac.compare_digest(
                self.headers.get("X-Session-Key", "").encode(), self.server.launch_key.encode())
            if not valid:
                return self.reply(401, {"error": "Invalid launch session"})
            return self.send_bytes(json.dumps({"csrf": self.server.csrf}).encode(), "application/json", extra={
                "Set-Cookie": self.server.cookie_name + "=" + self.server.session + "; HttpOnly; SameSite=Strict; Path=/"})
        if not self.session_ok(mutation=True):
            return
        try:
            if self.path == "/api/import":
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= MAX_BYTES:
                    raise ValueError("Recording must be nonempty and no larger than 2 GiB")
                title = unquote(self.headers.get("X-Recording-Title", "New recording"))[:200]
                directory = self.server.processor.state / "browser-uploads"
                directory.mkdir(exist_ok=True)
                with tempfile.TemporaryDirectory(dir=directory) as temporary:
                    source = Path(temporary) / "recording.media"
                    with source.open("wb") as output:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("Recording import was interrupted")
                            output.write(chunk)
                            remaining -= len(chunk)
                    identifier = self.server.ingest(source, title)
                return self.reply(201, {"id": identifier})
            if self.path == "/api/example":
                identifier = self.server.ingest(ROOT / "examples/media/business.wav", "Project sync · sample meeting")
                return self.reply(201, {"id": identifier})
            parts = self.path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "jobs"]:
                return self.reply(404, {"error": "Not found"})
            identifier = validate_identifier(parts[2])
            if parts[3] in ("trash", "restore", "purge"):
                with self.server.processor.lock:
                    result = self.server.store.purge(identifier) if parts[3] == "purge" else self.server.store.trash(identifier, parts[3] == "restore")
                return self.reply(200, result)
            if parts[3] == "review":
                return self.reply(200, self.server.store.save_annotation(identifier, self.read_json()))
            if parts[3] == "prepare":
                return self.reply(202, {"status": self.server.store.prepare_preview(identifier)})
            if parts[3] == "retry":
                root, job = self.server.store.locate(identifier)
                title = self.server.store.annotation(identifier)["title"] or "Retried recording"
                new_identifier = self.server.ingest(root / "inbox" / identifier / "recording.media", title)
                return self.reply(201, {"id": new_identifier})
            return self.reply(404, {"error": "Not found"})
        except RuntimeError as error:
            self.reply(409, {"error": str(error)})
        except (ValueError, KeyError, TypeError) as error:
            self.reply(400, {"error": str(error)})
        except OSError:
            self.reply(500, {"error": "Unable to access local recording storage"})


def main():
    parser = argparse.ArgumentParser(description="SecureNote local review workspace")
    parser.add_argument("--state", default="laptop-state")
    parser.add_argument("--model-dir", default="models/base.en")
    parser.add_argument("--include-state", action="append", default=[])
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    if args.device == "cuda":
        from prototype.gpu import check_cuda
        check_cuda(args.model_dir)
    # Discover only known demo directories beneath this project, not arbitrary disks.
    roots = args.include_state + [str(path) for path in Path.cwd().glob("demo*/laptop")]
    processor = Processor(args.state, args.model_dir, device=args.device)
    server = WorkspaceServer(("127.0.0.1", args.port), processor, roots)
    processor.start()
    launch_url = server.origin + "/#session=" + server.launch_key
    print("SecureNote review is running locally. Open this private launch link:", flush=True)
    print(launch_url, flush=True)
    print("Keep this terminal open. Ctrl+C stops the workspace.", flush=True)
    if not args.no_browser:
        webbrowser.open(launch_url)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        print("Stopping after any active transcription finishes.")
    finally:
        server.server_close()
        processor.close()


if __name__ == "__main__":
    main()
