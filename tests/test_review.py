"""Review, persistence, media-range, and local browser access boundaries."""

import http.client
import json
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from laptop import Processor
from review import WorkspaceServer
from prototype.analysis import automatic_notes, sentence_passages
from prototype.review import ReviewStore, parse_range
from prototype.pipeline import decode_audio, execute_media_tool, inspect_media
from prototype.transfer import atomic_json


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name) / "laptop"
        self.processor = Processor(self.state, "unused-model")
        self.identifier = "a" * 32
        job_path = self.state / "inbox" / self.identifier
        job_path.mkdir()
        self.result = self.state / "results" / "20261023T000000-aaaaaaaa"
        self.result.mkdir()
        self.segments = [
            {
                "start": 0.0,
                "end": 3.0,
                "text": "We decided not to upload recordings to the cloud.",
            },
            {"start": 3.0, "end": 6.0, "text": "Alice will send the budget by Friday."},
            {"start": 6.0, "end": 9.0, "text": "Why would anyone do otherwise?"},
            {
                "start": 9.0,
                "end": 12.0,
                "text": "The storage limit remains an unresolved issue.",
            },
            {
                "start": 12.0,
                "end": 15.0,
                "text": "The discount factor controls future rewards.",
            },
        ]
        atomic_json(
            self.result / "summary.json",
            {"status": "ok", "decoded_audio": {"duration_seconds": 15}},
        )
        atomic_json(self.result / "transcript.json", {"segments": self.segments})
        atomic_json(
            job_path / "job.json",
            {
                "recording_id": self.identifier,
                "status": "completed",
                "captured_at": "2026-10-23T00:00:00+00:00",
                "input_bytes": 480044,
                "result_directory": self.result.name,
                "device_id": "test-recorder",
            },
        )
        with wave.open(str(job_path / "recording.media"), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\0\0" * 15 * 16000)
        self.server = WorkspaceServer(("127.0.0.1", 0), self.processor)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.02},
            daemon=True,
        )
        self.thread.start()
        self.cookie = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def request(self, method, path, data=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        values = {"Cookie": self.cookie, **(headers or {})}
        body = json.dumps(data).encode() if data is not None else None
        client.request(method, path, body=body, headers=values)
        response = client.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        client.close()
        return result

    def login(self):
        status, headers, body = self.request(
            "POST",
            "/api/session",
            headers={
                "Origin": self.server.origin,
                "X-Session-Key": self.server.launch_key,
            },
        )
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        return json.loads(body)["csrf"]

    def test_question_selection_keeps_evidence_but_does_not_promote_rhetorical_questions(
        self,
    ):
        notes = automatic_notes(sentence_passages(self.segments))
        self.assertNotIn("Questions", notes)
        self.assertEqual(len(notes["Decisions"]), 1)
        self.assertIn("decided not", notes["Decisions"][0]["text"])
        self.assertEqual(len(notes["Follow-ups"]), 1)
        self.assertFalse(
            any(
                "otherwise?" in note["text"]
                for group in notes.values()
                for note in group
            )
        )
        self.assertEqual(len(self.server.store.detail(self.identifier)["segments"]), 5)
        opposing = sentence_passages(
            [
                {"start": 0.0, "end": 2.0, "text": "We decided to use cloud storage."},
                {
                    "start": 2.0,
                    "end": 4.0,
                    "text": "We decided not to use cloud storage.",
                },
            ]
        )
        self.assertEqual(len(automatic_notes(opposing)["Decisions"]), 2)

    def test_browser_webm_without_duration_is_validated_by_bounded_decode(self):
        source = self.state / "inbox" / self.identifier / "recording.media"
        payload = execute_media_tool(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(source),
                "-t",
                "0.3",
                "-c:a",
                "libopus",
                "-f",
                "webm",
                "pipe:1",
            ],
            timeout=30,
        )
        streaming = Path(self.temporary.name) / "browser.webm"
        streaming.write_bytes(payload)
        # FFmpeg builds differ in whether they infer duration by scanning a
        # streaming WebM. Simulate missing MediaRecorder metadata, then exercise
        # actual bounded decoding of the valid bytes.
        with patch(
            "prototype.pipeline.execute_media_tool",
            return_value=b'{"format":{"format_name":"matroska,webm"},"streams":[{"codec_type":"audio"}]}',
        ):
            metadata = inspect_media(streaming)
        self.assertFalse(metadata["source_duration_known"])
        decoded = decode_audio(streaming, Path(self.temporary.name) / "decoded.wav")
        self.assertGreater(decoded["duration_seconds"], 0.2)
        self.assertLess(decoded["duration_seconds"], 0.5)

    def test_access_requires_session_and_rejects_foreign_hosts_and_csrf(self):
        self.assertEqual(self.request("GET", "/api/jobs")[0], 401)
        self.assertEqual(
            self.request("GET", "/", headers={"Host": "attacker.invalid"})[0], 403
        )
        csrf = self.login()
        self.assertEqual(self.request("GET", "/api/jobs")[0], 200)
        path = "/api/jobs/" + self.identifier + "/review"
        self.assertEqual(
            self.request("POST", path, {"version": 0, "title": "Changed"})[0], 403
        )
        self.assertEqual(
            self.request(
                "POST",
                path,
                {"version": 0, "title": "Changed"},
                {"Origin": "https://attacker.invalid", "X-Review-CSRF": csrf},
            )[0],
            403,
        )
        self.assertEqual(self.server.store.annotation(self.identifier)["title"], "")

    def test_edits_bookmarks_hide_and_title_survive_reload_without_modifying_transcript(
        self,
    ):
        before = (self.result / "transcript.json").read_bytes()
        detail = self.server.store.detail(self.identifier)
        note_id = detail["notes"][0]["id"]
        updated = self.server.store.save_annotation(
            self.identifier,
            {
                "version": 0,
                "title": "Team review",
                "reviewed": True,
                "edits": {note_id: "An edited note"},
                "hidden": [note_id],
                "bookmarks": [
                    {"id": "b" * 32, "start": 4.5, "text": "Check this commitment"}
                ],
            },
        )
        reloaded = ReviewStore(self.state, []).detail(self.identifier)
        self.assertTrue(reloaded["annotation"]["reviewed"])
        self.assertEqual(reloaded["title"], "Team review")
        self.assertEqual(reloaded["annotation"]["bookmarks"][0]["start"], 4.5)
        self.assertTrue(reloaded["notes"][0]["edited"])
        self.assertTrue(reloaded["notes"][0]["hidden"])
        self.assertEqual(before, (self.result / "transcript.json").read_bytes())
        with self.assertRaises(RuntimeError):
            self.server.store.save_annotation(
                self.identifier, {"version": 0, "title": "Stale tab"}
            )
        with self.assertRaises(ValueError):
            self.server.store.save_annotation(
                self.identifier,
                {
                    "version": updated["version"],
                    "bookmarks": [
                        {"id": "b" * 32, "start": float("nan"), "text": "Bad timestamp"}
                    ],
                },
            )

    def test_media_serves_exact_byte_ranges_and_rejects_invalid_ranges(self):
        self.login()
        payload = b"0123456789abcdef"
        self.server.store.preview_path(self.identifier).write_bytes(payload)
        path = "/api/jobs/" + self.identifier + "/media"
        status, headers, body = self.request(
            "GET", path, headers={"Range": "bytes=3-7"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(headers["Content-Range"], "bytes 3-7/16")
        self.assertEqual(body, b"34567")
        self.assertEqual(
            self.request("GET", path, headers={"Range": "bytes=-3"})[2], b"def"
        )
        self.assertEqual(
            self.request("GET", path, headers={"Range": "bytes=40-"})[0], 416
        )
        self.assertEqual(
            self.request("GET", path, headers={"Range": "bytes=0-1,3-4"})[0], 416
        )
        self.assertEqual(self.request("HEAD", path)[2], b"")

    def test_preview_generated_from_retained_audio(self):
        self.assertEqual(
            self.server.store.prepare_preview(self.identifier), "preparing"
        )
        deadline = time.monotonic() + 10
        while (
            self.server.store.preview_status(self.identifier) == "preparing"
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertEqual(self.server.store.preview_status(self.identifier), "ready")
        self.assertGreater(
            self.server.store.preview_path(self.identifier).stat().st_size, 1000
        )

    def test_exports_include_full_transcript_and_escape_markup(self):
        note_id = self.server.store.detail(self.identifier)["notes"][0]["id"]
        self.server.store.save_annotation(
            self.identifier,
            {"version": 0, "edits": {note_id: "<script>unsafe</script>"}},
        )
        text = self.server.store.export(self.identifier)
        self.assertIn("Full transcript", text)
        self.assertIn("Why would anyone do otherwise?", text)
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_trash_restore_purge_and_search(self):
        store = self.server.store
        store.save_annotation(
            self.identifier,
            {
                "version": 0,
                "bookmarks": [
                    {"id": "b" * 32, "start": 4, "text": "My budget reminder"}
                ],
            },
        )
        self.assertEqual(store.search("budget")[0]["kind"], "Your note")
        store.trash(self.identifier)
        self.assertEqual(store.catalog(), [])
        self.assertEqual(store.search("budget"), [])
        self.assertEqual(len(store.catalog(True)), 1)
        store.trash(self.identifier, restore=True)
        self.assertEqual(len(store.catalog()), 1)
        self.assertEqual(
            len(store.detail(self.identifier)["annotation"]["bookmarks"]), 1
        )
        store.trash(self.identifier)
        store.purge(self.identifier)
        self.assertFalse(self.result.exists())
        self.assertFalse((self.state / "inbox" / self.identifier).exists())
        self.assertEqual(store.catalog(True), [])

    def test_delete_protects_active_jobs_and_requires_csrf(self):
        self.login()
        self.assertEqual(
            self.request("POST", "/api/jobs/" + self.identifier + "/trash")[0], 403
        )
        path = self.state / "inbox" / self.identifier / "job.json"
        job = json.loads(path.read_text())
        job["status"] = "processing"
        atomic_json(path, job)
        with self.assertRaises(RuntimeError):
            self.server.store.trash(self.identifier)

    def test_cuda_probe_handles_native_crash_without_inprocess_inference(self):
        from prototype.gpu import check_cuda
        from subprocess import CompletedProcess

        with patch(
            "prototype.gpu.subprocess.run",
            return_value=CompletedProcess([], 1, "", "Missing cudnn_ops64_9.dll"),
        ):
            with self.assertRaisesRegex(SystemExit, "requirements-cuda"):
                check_cuda("unused-model")
        gpu = Processor(Path(self.temporary.name) / "gpu", "unused", device="cuda")
        self.assertEqual((gpu.device, gpu.compute_type), ("cuda", "float16"))

    def test_rag_endpoint_requires_session_csrf_and_completed_recording(self):
        path = "/api/jobs/" + self.identifier + "/ask"
        self.assertEqual(self.request("POST", path, {"question": "budget"})[0], 401)
        csrf = self.login()
        self.assertEqual(self.request("POST", path, {"question": "budget"})[0], 403)
        headers = {"Origin": self.server.origin, "X-Review-CSRF": csrf}
        from prototype.rag import NOT_FOUND

        with patch("prototype.rag.load_answer_model") as model:
            response = self.request(
                "POST", path, {"question": "quartz volcano"}, headers
            )
        model.assert_not_called()
        self.assertEqual(response[0], 200)
        self.assertEqual(json.loads(response[2])["answer"], NOT_FOUND)
        self.server.store.trash(self.identifier)
        self.assertEqual(
            self.request("POST", path, {"question": "budget"}, headers)[0], 400
        )

    def test_purge_removes_saved_rag_artifacts(self):
        folder = self.state / "answers" / self.identifier / "example"
        folder.mkdir(parents=True)
        (folder / "answer.json").write_text('{"answer":"private note"}')
        self.server.store.trash(self.identifier)
        self.server.store.purge(self.identifier)
        self.assertFalse(folder.exists())

    def test_range_parser_edge_cases(self):
        self.assertEqual(parse_range("bytes=4-", 10), (4, 9, True))
        self.assertEqual(parse_range("bytes=-100", 10), (0, 9, True))
        for header in ("bytes=-0", "bytes=7-3", "items=0-2", "bytes=-"):
            with self.assertRaises(ValueError):
                parse_range(header, 10)

    def test_only_one_processor_can_own_a_state_directory(self):
        first = Processor(Path(self.temporary.name) / "exclusive", "unused-model")
        second = Processor(first.state, "unused-model")
        try:
            first.start()
            with self.assertRaises(RuntimeError):
                second.start()
            first.close()
            second.start()
        finally:
            first.close()
            second.close()


if __name__ == "__main__":
    unittest.main()
