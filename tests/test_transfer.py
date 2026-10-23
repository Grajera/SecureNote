"""Real HTTP transfer tests; no model needed for ingestion and security tests."""

import base64
import http.client
import json
import tempfile
import threading
import unittest
import socket
from pathlib import Path

from device import enqueue, remote_status, send_one
from laptop import Processor, Receiver
from prototype.transfer import atomic_json, validate_endpoint, validate_manifest


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "input.wav"
        self.source.write_bytes(b"synthetic recording bytes for transport test")
        self.processor = Processor(self.root / "laptop", self.root / "unused-model")
        self.server = Receiver(("127.0.0.1", 0), self.processor)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.02},
            daemon=True,
        )
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        self.token = self.processor.state / "device.token"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def capture(self):
        return enqueue(self.source, self.root / "device")

    def test_delivered_only_after_exact_ack_and_duplicate_is_idempotent(self):
        capture = self.capture()
        delivered = send_one(capture, self.endpoint, self.token)
        self.assertEqual(delivered["status"], "delivered")
        self.assertTrue((capture / "recording.media").is_file())
        # Simulate a lost receipt: retry must not create another processor job.
        atomic_json(capture / "delivery.json", {"status": "queued", "attempts": 1})
        self.assertEqual(
            send_one(capture, self.endpoint, self.token)["status"], "delivered"
        )
        self.assertEqual(
            len(list((self.processor.state / "inbox").glob("*/job.json"))), 1
        )
        status = remote_status(capture.name, self.endpoint, self.token)
        self.assertEqual(status["status"], "queued")

    def test_wrong_authentication_keeps_device_recording_queued(self):
        capture = self.capture()
        wrong_token = self.root / "wrong-token"
        wrong_token.write_text("0" * 64)
        result = send_one(capture, self.endpoint, wrong_token)
        self.assertEqual(result["status"], "queued")
        self.assertFalse(list((self.processor.state / "inbox").glob("*/job.json")))
        self.assertTrue((capture / "recording.media").is_file())

    def test_corrupted_network_body_rejected_at_receiver(self):
        capture = self.capture()
        manifest = json.loads((capture / "manifest.json").read_text())
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        client.request(
            "POST",
            "/v1/recordings",
            body=b"x" * manifest["input_bytes"],
            headers={
                "Authorization": "Bearer " + self.token.read_text(),
                "X-SecureNote-Manifest": base64.b64encode(
                    json.dumps(manifest).encode()
                ).decode(),
            },
        )
        response = client.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        client.close()
        self.assertFalse(list((self.processor.state / "inbox").glob("*/job.json")))
        self.assertFalse(list((self.processor.state / "inbox").glob("*.pending")))

    def test_local_mutation_keeps_queue(self):
        capture = self.capture()
        (capture / "recording.media").write_bytes(b"changed")
        self.assertEqual(
            send_one(capture, self.endpoint, self.token)["status"], "queued"
        )
        self.assertFalse(list((self.processor.state / "inbox").glob("*/job.json")))

    def test_unavailable_receiver_keeps_queue(self):
        capture = self.capture()
        with socket.socket() as closed_listener:
            closed_listener.bind(("127.0.0.1", 0))
            address = f"http://127.0.0.1:{closed_listener.getsockname()[1]}"
            self.assertEqual(send_one(capture, address, self.token)["status"], "queued")
        self.assertTrue((capture / "recording.media").is_file())

    def test_queue_and_token_survive_receiver_restart(self):
        capture = self.capture()
        self.assertEqual(
            send_one(capture, self.endpoint, self.token)["status"], "delivered"
        )
        original_token = self.token.read_text()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.processor = Processor(self.processor.state, self.root / "unused-model")
        self.server = Receiver(("127.0.0.1", 0), self.processor)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.02},
            daemon=True,
        )
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.token.read_text(), original_token)
        self.assertEqual(
            remote_status(capture.name, self.endpoint, self.token)["status"], "queued"
        )

    def test_rejects_remote_plaintext_and_path_traversal(self):
        with self.assertRaises(ValueError):
            validate_endpoint("http://192.168.1.4:8765")
        capture = self.capture()
        manifest = json.loads((capture / "manifest.json").read_text())
        manifest["recording_id"] = "../escape"
        with self.assertRaises(ValueError):
            validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
