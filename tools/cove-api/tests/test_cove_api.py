import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cove_api


class ValidationTests(unittest.TestCase):
    def test_valid_https_url(self):
        value = "https://example.com/file.zip?download=true"
        self.assertEqual(cove_api.validate_url(value), value)

    def test_rejects_file_url(self):
        with self.assertRaises(cove_api.CoveApiError) as caught:
            cove_api.validate_url("file:///C:/Windows/win.ini")
        self.assertEqual(caught.exception.code, "invalid_url")

    def test_rejects_header_injection(self):
        with self.assertRaises(cove_api.CoveApiError):
            cove_api.validate_url("https://example.com/file\r\nX-Test: bad")

    def test_filename_is_a_basename(self):
        self.assertEqual(cove_api.validate_filename("model.gguf"), "model.gguf")
        for value in (
            "..",
            "folder/file.zip",
            "C:\\file.zip",
            "NUL.txt",
            "bad. ",
            "bad?.zip",
            "x" * 256,
        ):
            with self.subTest(value=value), self.assertRaises(cove_api.CoveApiError):
                cove_api.validate_filename(value)

    def test_task_id_validation(self):
        self.assertEqual(cove_api.validate_task_id("123"), 123)
        with self.assertRaises(cove_api.CoveApiError):
            cove_api.validate_task_id("not-an-id")


class DirectoryTests(unittest.TestCase):
    def test_rejects_relative_directory(self):
        config = {"allow_any_absolute_directory": True}
        with self.assertRaises(cove_api.CoveApiError) as caught:
            cove_api.resolve_directory("relative-folder", {}, config)
        self.assertEqual(caught.exception.code, "directory_not_absolute")

    def test_unrestricted_mode_allows_outside_configured_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            settings = {"download_dir": root}
            config = {
                "allow_any_absolute_directory": True,
                "allowed_download_roots": [root],
                "allow_cove_default_directory": True,
            }
            child = Path(root) / "models"
            resolved = cove_api.resolve_directory(str(child), settings, config, create=True)
            self.assertTrue(resolved.is_dir())
            self.assertEqual(cove_api.resolve_directory(outside, settings, config), Path(outside).resolve())

    def test_restricted_mode_still_enforces_configured_roots(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            settings = {"download_dir": root}
            config = {
                "allow_any_absolute_directory": False,
                "allowed_download_roots": [root],
                "allow_cove_default_directory": True,
            }
            with self.assertRaises(cove_api.CoveApiError) as caught:
                cove_api.resolve_directory(outside, settings, config)
            self.assertEqual(caught.exception.code, "directory_not_allowed")


class SettingsTests(unittest.TestCase):
    def test_rejects_boolean_api_port(self):
        with tempfile.TemporaryDirectory() as root:
            settings_path = Path(root) / "settings.json"
            settings_path.write_text(
                json.dumps({"api_token": "x" * 43, "api_port": True}),
                encoding="utf-8",
            )
            with self.assertRaises(cove_api.CoveApiError) as caught:
                cove_api.load_settings(str(settings_path))
            self.assertEqual(caught.exception.code, "settings_invalid")


class ExecutableDiscoveryTests(unittest.TestCase):
    def test_source_client_finds_portable_in_repository_release_directory(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            app_dir = repo / "tools" / "cove-api"
            release = repo / "release"
            app_dir.mkdir(parents=True)
            release.mkdir()
            executable = release / "Cove-Download-Manager-2.0.0-Portable.exe"
            executable.touch()
            with patch.object(cove_api, "APP_DIR", app_dir):
                self.assertEqual(cove_api.resolve_cove_executable({}), executable)

    def test_explicit_executable_takes_precedence(self):
        with tempfile.TemporaryDirectory() as root:
            executable = Path(root) / "Cove-Test.exe"
            executable.touch()
            resolved = cove_api.resolve_cove_executable(
                {"cove_executable": str(executable)}
            )
            self.assertEqual(resolved, executable.resolve())


class AddCommandTests(unittest.TestCase):
    def test_add_uses_current_cove_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            settings = cove_api.LoadedSettings(
                Path(root) / "settings.json",
                {
                    "download_dir": root,
                    "connections_per_server": 12,
                    "max_concurrent": 2,
                    "api_port": 17681,
                    "api_token": "x" * 43,
                },
            )
            config = {
                "allowed_download_roots": [root],
                "allow_cove_default_directory": True,
                "max_connections": 32,
            }

            class FakeClient:
                def __init__(self):
                    self.calls = []

                def request(self, method, path, payload=None):
                    self.calls.append((method, path, payload))
                    return {"download": {
                        "task_id": 17,
                        "gid": None,
                        "status": "queued",
                        "directory": root,
                        "filename": None,
                        "connections": 12,
                        "speed_limit_kbps": 0,
                    }}

            client = FakeClient()
            args = SimpleNamespace(
                url="https://example.com/file.bin",
                directory=None,
                name=None,
                connections=None,
                speed_limit_kbps=None,
                create_directory=False,
            )
            result = cove_api.command_add(args, client, settings, config)
            self.assertTrue(result["ok"])
            self.assertEqual(result["effective"]["connections"], 12)
            self.assertEqual(result["task_id"], 17)
            payload = client.calls[0][2]
            self.assertNotIn("directory", payload)
            self.assertNotIn("connections", payload)


class CoveStartupTests(unittest.TestCase):
    def test_does_not_launch_when_rpc_is_already_ready(self):
        client = SimpleNamespace(health=lambda: {"ok": True})
        with patch.object(cove_api.subprocess, "Popen") as popen:
            self.assertFalse(cove_api.ensure_cove_running(client, {"auto_start_cove": True}))
        popen.assert_not_called()

    def test_launches_and_waits_for_rpc(self):
        with tempfile.TemporaryDirectory() as root:
            executable = Path(root) / "Cove.exe"
            executable.touch()

            class StartingClient:
                def __init__(self):
                    self.calls = 0

                def health(self):
                    self.calls += 1
                    if self.calls == 1:
                        raise cove_api.CoveApiError("cove_not_running", "offline", exit_code=3)
                    return {"ok": True}

            config = {
                "auto_start_cove": True,
                "cove_executable": str(executable),
                "cove_startup_timeout_seconds": 2,
            }
            with patch.object(cove_api.subprocess, "Popen") as popen, patch.object(cove_api.time, "sleep"):
                self.assertTrue(cove_api.ensure_cove_running(StartingClient(), config))
            popen.assert_called_once()


class ControlCommandTests(unittest.TestCase):
    def test_cancel_uses_task_id_endpoint_and_keeps_files(self):
        class FakeClient:
            def __init__(self):
                self.call = None

            def request(self, method, path, payload=None):
                self.call = (method, path, payload)
                return {"download": {"task_id": 42, "gid": None, "status": "removed"}}

        client = FakeClient()
        result = cove_api.command_cancel(SimpleNamespace(task_id="42"), client)
        self.assertEqual(client.call, ("POST", "/downloads/42/cancel", {}))
        self.assertTrue(result["partial_file_kept"])
        self.assertEqual(result["task_id"], 42)


if __name__ == "__main__":
    unittest.main()
