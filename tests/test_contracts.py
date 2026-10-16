"""Boundary, provenance, and failure tests; no model download required."""

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prototype.analysis import automatic_notes, search_passages, sentence_passages, validate_segments
from prototype.pipeline import RunLog, call_tool, inspect_media, run_recording


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.segments = [
            {"start": 0., "end": 4., "text": "We decided to use the local server."},
            {"start": 4., "end": 8., "text": "Alice will send the budget by Friday."},
            {"start": 8., "end": 12., "text": "How do we protect the backup?"},
            {"start": 12., "end": 15., "text": "We have not decided on wireless."},
        ]

    def test_bad_model_shape_and_nonfinite_times_rejected(self):
        for bad in [None, {}, [{"start": 0, "end": 1, "text": 5}],
                    [{"start": 0, "end": math.nan, "text": "hello"}],
                    [{"start": 4, "end": 2, "text": "hello"}]]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_segments(bad, 20)

    def test_notes_keep_source_evidence_and_do_not_invent_owners(self):
        passages = sentence_passages(validate_segments(self.segments, 20))
        notes = automatic_notes(passages)
        self.assertEqual(len(notes["Decisions"]), 1)
        self.assertEqual(notes["Action items"][0]["text"], self.segments[1]["text"])
        for items in notes.values():
            for item in items:
                self.assertIn(item["text"], [passage["text"] for passage in passages])

    def test_search_returns_evidence_or_explicit_empty(self):
        passages = sentence_passages(self.segments)
        self.assertEqual(search_passages(passages, "budget")[0]["id"], 1)
        self.assertEqual(search_passages(passages, "unicorns"), [])
        self.assertEqual(search_passages([], "budget"), [])
        for query in ["", " " * 10, "a" * 513, 42]:
            with self.assertRaises(ValueError):
                search_passages(passages, query)

    def test_sentence_crossing_asr_segments_is_not_fragmented(self):
        passages = sentence_passages([
            {"start": 0., "end": 2., "text": "Remember the discount factor controls how"},
            {"start": 2., "end": 4., "text": "much future rewards matter. Homework is due Friday."}])
        self.assertEqual(passages[0]["text"], "Remember the discount factor controls how much future rewards matter.")
        self.assertEqual((passages[0]["start"], passages[0]["end"]), (0., 4.))
        self.assertEqual(passages[1]["start"], 2.)

    def test_malformed_tool_response_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = RunLog(Path(temporary))
            with patch("prototype.pipeline.search_passages", return_value=[{"id": 99, "score": 1.0}]):
                with self.assertRaises(ValueError):
                    call_tool("search_transcript", log, passages=sentence_passages(self.segments), query="budget")

    def test_empty_file_fails_before_model_and_logs_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "empty.wav"
            source.touch()
            with patch("prototype.pipeline.transcribe") as model:
                directory, result = run_recording(source, root / "missing-model", root / "runs")
            model.assert_not_called()
            self.assertEqual(result["status"], "failed")
            self.assertFalse((directory / "notes.md").exists())
            events = [json.loads(line) for line in (directory / "run.jsonl").read_text().splitlines()]
            self.assertTrue(any(event["stage"] == "validation" and event["event"] == "failed" for event in events))
            self.assertNotIn("empty.wav", (directory / "run.jsonl").read_text())

    def test_missing_tokenizer_rejected_without_model_download_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_directory = root / "model"
            model_directory.mkdir()
            (model_directory / "model.bin").write_bytes(b"placeholder")
            (model_directory / "config.json").write_text("{}")
            media = {"input_bytes": 1, "duration_seconds": 1., "container": "wav"}
            with patch("prototype.pipeline.inspect_media", return_value=media), patch("prototype.pipeline.transcribe") as model:
                directory, result = run_recording(root / "input.wav", model_directory, root / "runs")
            model.assert_not_called()
            self.assertEqual(result["status"], "failed")
            self.assertIn("incomplete", result["error"])


if __name__ == "__main__":
    unittest.main()
