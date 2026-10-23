"""Launcher tests exercise portability and failure behavior without downloading."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import start


class LauncherTests(unittest.TestCase):
    def test_linux_loader_paths_are_in_child_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder) / "nvidia/cudnn/lib"
            library.mkdir(parents=True)
            with patch.object(start.sys, "platform", "linux"), patch.object(
                start.subprocess, "check_output", return_value=json.dumps([folder])
            ), patch.dict(os.environ, {"LD_LIBRARY_PATH": "/existing"}):
                result = start.runtime_environment(Path("/venv/bin/python"))
            self.assertEqual(
                result["LD_LIBRARY_PATH"], str(library) + os.pathsep + "/existing"
            )

    def test_missing_media_tools_stops_before_installation(self):
        with patch.object(start.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Missing ffmpeg, ffprobe"):
                start.check_media_tools()

    def test_saved_device_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / "settings.json"
            with patch.object(start, "SETTINGS", settings):
                self.assertEqual(start.saved_device(), "cpu")
                settings.write_text('{"device":"cuda"}')
                self.assertEqual(start.saved_device(), "cuda")
                settings.write_text('{"device":"unexpected"}')
                with self.assertRaises(ValueError):
                    start.saved_device()

    def test_commands_are_argument_lists_with_fixed_working_directory(self):
        with patch.object(start.subprocess, "run") as execute:
            start.run([Path("/path with spaces/python"), "review.py"])
            execute.assert_called_once_with(
                ["/path with spaces/python", "review.py"],
                cwd=start.ROOT,
                env=None,
                check=True,
            )

    def test_failed_setup_does_not_save_device_or_start_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / "settings.json"
            with patch.object(start, "SETTINGS", settings), patch.object(
                start, "check_media_tools"
            ), patch.object(
                start.platform, "system", return_value="Linux"
            ), patch.object(
                start.platform, "machine", return_value="x86_64"
            ), patch.object(
                start, "environment_python", return_value=Path(__file__)
            ), patch.object(
                start, "run", side_effect=RuntimeError("installation failed")
            ):
                with self.assertRaisesRegex(RuntimeError, "installation failed"):
                    start.setup("cuda")
            self.assertFalse(settings.exists())
