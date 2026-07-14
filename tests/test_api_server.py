import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib import error as urlerror
from urllib import request as urlrequest

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QThread

from cove.api_server import (
    MAX_BODY_BYTES,
    ApiProblem,
    LocalApiServer,
    QueueApiBridge,
    validate_add_payload,
)
from cove import config
from cove import db
from cove.config import Settings
from cove.queue import QueueManager
from cove.queue import DownloadTask


TOKEN = "t" * 43


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.download = {
            "task_id": 7,
            "gid": None,
            "url": "https://example.com/file.bin",
            "filename": None,
            "directory": "C:\\Downloads",
            "status": "queued",
            "backend": "aria2",
            "connections": 16,
            "speed_limit_kbps": 0,
            "completed_bytes": 0,
            "total_bytes": 0,
            "speed_bytes_per_second": 0,
            "progress_percent": 0.0,
            "error": None,
            "created_at": 1.0,
            "finished_at": None,
        }

    def invoke(self, action, payload=None):
        self.calls.append((action, payload or {}))
        if action == "settings":
            return {"download_directory": "C:\\Downloads", "api_port": 17681}
        if action == "list":
            return [self.download]
        if action in {"add", "status", "pause", "resume", "cancel"}:
            result = dict(self.download)
            if action == "cancel":
                result["status"] = "removed"
            return result
        raise AssertionError(action)


@pytest.fixture
def api_server():
    settings = SimpleNamespace(api_token=TOKEN, api_port=0)
    bridge = FakeBridge()
    server = LocalApiServer(settings, SimpleNamespace(), port=0, bridge=bridge)
    server.start()
    try:
        yield server, bridge
    finally:
        server.stop()


def call(server, method, path, *, body=None, headers=None):
    data = body
    request_headers = dict(headers or {})
    if isinstance(body, dict):
        data = json.dumps(body).encode()
        request_headers.setdefault("Content-Type", "application/json")
    req = urlrequest.Request(
        f"http://127.0.0.1:{server.bound_port}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urlrequest.urlopen(req, timeout=2) as response:
            return response.status, json.loads(response.read())
    except urlerror.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_health_is_minimal_and_unauthenticated(api_server):
    server, _ = api_server
    status, payload = call(server, "GET", "/api/v1/health")
    assert status == 200
    assert payload["ok"] is True
    assert "token" not in json.dumps(payload).lower()


@pytest.mark.parametrize(
    ("header", "code"),
    [
        (None, "missing_auth"),
        ("Basic abc", "malformed_auth"),
        ("Bearer wrong", "invalid_token"),
    ],
)
def test_operational_endpoints_require_bearer_token(api_server, header, code):
    server, _ = api_server
    headers = {} if header is None else {"Authorization": header}
    status, payload = call(server, "GET", "/api/v1/downloads", headers=headers)
    assert status == 401
    assert payload["error"]["code"] == code


def test_rejects_browser_origin_even_with_valid_token(api_server):
    server, _ = api_server
    status, payload = call(
        server,
        "GET",
        "/api/v1/downloads",
        headers={**auth(), "Origin": "https://hostile.example"},
    )
    assert status == 403
    assert payload["error"]["code"] == "origin_not_allowed"


def test_rejects_wrong_content_type_malformed_and_oversized_json(api_server):
    server, _ = api_server
    status, payload = call(server, "POST", "/api/v1/downloads", body=b"{}", headers=auth())
    assert (status, payload["error"]["code"]) == (415, "unsupported_content_type")

    status, payload = call(
        server,
        "POST",
        "/api/v1/downloads",
        body=b"{bad",
        headers={**auth(), "Content-Type": "application/json"},
    )
    assert (status, payload["error"]["code"]) == (400, "malformed_json")

    status, payload = call(
        server,
        "POST",
        "/api/v1/downloads",
        body=b"x" * (MAX_BODY_BYTES + 1),
        headers={**auth(), "Content-Type": "application/json"},
    )
    assert (status, payload["error"]["code"]) == (413, "body_too_large")


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "invalid_url"),
        ({"url": "file:///C:/secret.txt"}, "invalid_url"),
        ({"url": "https://example.com/a", "filename": "../a"}, "invalid_filename"),
        ({"url": "https://example.com/a", "directory": "relative"}, "directory_not_absolute"),
        ({"url": "https://example.com/a", "connections": 0}, "invalid_connections"),
        ({"url": "https://example.com/a", "connections": True}, "invalid_connections"),
        ({"url": "https://example.com/a", "create_directory": True}, "invalid_create_directory"),
        ({"url": "https://example.com/a", "surprise": 1}, "unknown_fields"),
    ],
)
def test_add_validation(payload, code):
    with pytest.raises(ApiProblem) as caught:
        validate_add_payload(payload)
    assert caught.value.code == code


def test_add_keeps_omitted_defaults_for_queue_thread(api_server):
    server, bridge = api_server
    status, payload = call(
        server,
        "POST",
        "/api/v1/downloads",
        body={"url": "https://example.com/file.bin"},
        headers=auth(),
    )
    assert status == 202
    assert payload["download"]["task_id"] == 7
    assert payload["download"]["gid"] is None
    action, passed = bridge.calls[-1]
    assert action == "add"
    assert passed["directory"] is None
    assert passed["connections"] is None


def test_list_status_pause_resume_and_safe_cancel(api_server):
    server, bridge = api_server
    status, listing = call(server, "GET", "/api/v1/downloads", headers=auth())
    assert status == 200 and listing["count"] == 1
    status, detail = call(server, "GET", "/api/v1/downloads/7", headers=auth())
    assert status == 200 and detail["download"]["task_id"] == 7
    for action in ("pause", "resume", "cancel"):
        status, result = call(
            server,
            "POST",
            f"/api/v1/downloads/7/{action}",
            body={},
            headers=auth(),
        )
        assert status == 200
        assert result["download"]["task_id"] == 7
    assert bridge.calls[-1] == ("cancel", {"task_id": 7})


def test_invalid_and_missing_task_paths_are_structured(api_server):
    server, _ = api_server
    status, payload = call(server, "GET", "/api/v1/downloads/0", headers=auth())
    assert (status, payload["error"]["code"]) == (400, "invalid_task_id")


def test_port_collision_and_clean_shutdown():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    settings = SimpleNamespace(api_token=TOKEN, api_port=port)
    server = LocalApiServer(settings, SimpleNamespace(), bridge=FakeBridge())
    with pytest.raises(OSError):
        server.start()
    listener.close()

    server = LocalApiServer(settings, SimpleNamespace(), bridge=FakeBridge())
    server.start()
    server.stop()
    replacement = socket.socket()
    replacement.bind(("127.0.0.1", port))
    replacement.close()


def test_qt_bridge_executes_add_on_queue_owning_thread():
    app = QCoreApplication.instance() or QCoreApplication([])

    class FakeQueue(QObject):
        def __init__(self):
            super().__init__()
            self.settings = SimpleNamespace()
            self.tasks = {}
            self.called_thread = None

        def add_url(self, url, **kwargs):
            self.called_thread = QThread.currentThread()
            self.tasks[1] = DownloadTask(id=1, url=url, out_dir="C:\\Downloads")
            return 1

    queue = FakeQueue()
    bridge = QueueApiBridge(queue, timeout=2)
    result = {}

    def worker():
        result["download"] = bridge.invoke(
            "add",
            {
                "url": "https://example.com/a",
                "directory": None,
                "filename": None,
                "connections": None,
                "speed_limit_kbps": 0,
            },
        )

    thread = threading.Thread(target=worker)
    thread.start()
    deadline = time.monotonic() + 2
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    thread.join(timeout=0.1)
    assert not thread.is_alive()
    assert queue.called_thread is queue.thread()
    assert result["download"]["task_id"] == 1


def test_bridge_cancel_never_deletes_and_hides_inflight_task_immediately():
    QCoreApplication.instance() or QCoreApplication([])

    class FakeQueue(QObject):
        def __init__(self):
            super().__init__()
            self.settings = SimpleNamespace()
            self.tasks = {
                9: DownloadTask(
                    id=9,
                    url="https://example.com/a",
                    out_dir="C:\\Downloads",
                    status="active",
                )
            }
            self.remove_call = None

        def remove(self, task_id, delete_file=False):
            self.remove_call = (task_id, delete_file)
            # QueueManager deliberately retains an add-in-flight task until
            # its gid arrives; the API must still hide it immediately.

    queue = FakeQueue()
    bridge = QueueApiBridge(queue)
    removed = bridge.invoke("cancel", {"task_id": 9})
    assert removed["status"] == "removed"
    assert queue.remove_call == (9, False)
    assert bridge.invoke("list") == []
    with pytest.raises(ApiProblem) as caught:
        bridge.invoke("status", {"task_id": 9})
    assert caught.value.code == "task_not_found"


def test_http_add_enters_real_queue_sqlite_and_ui_signal_immediately(tmp_path, monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication([])
    database = tmp_path / "cove.db"
    original_init = db.init
    original_connect = db.connect
    monkeypatch.setattr(db, "init", lambda: original_init(database))
    monkeypatch.setattr(db, "connect", lambda: original_connect(database))
    settings = Settings(
        download_dir=str(tmp_path),
        connections_per_server=16,
        api_token=TOKEN,
        api_port=0,
    )
    queue = QueueManager(settings, SimpleNamespace())
    queue._scheduler_allows = False
    added = []
    queue.task_added.connect(added.append)
    server = LocalApiServer(settings, queue, port=0)
    server.start()
    outcome = {}

    def worker():
        outcome["response"] = call(
            server,
            "POST",
            "/api/v1/downloads",
            body={
                "url": "https://example.com/model.gguf",
                "directory": str(tmp_path),
                "filename": "renamed.gguf",
                "connections": 8,
            },
            headers=auth(),
        )

    thread = threading.Thread(target=worker)
    thread.start()
    deadline = time.monotonic() + 3
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    thread.join(timeout=0.1)
    try:
        assert not thread.is_alive()
        status, payload = outcome["response"]
        assert status == 202
        task_id = payload["download"]["task_id"]
        assert added == [task_id]
        task = queue.tasks[task_id]
        assert task.status == "queued"
        assert task.filename == "renamed.gguf"
        assert task.connections == 8
        with original_connect(database) as connection:
            row = connection.execute("SELECT * FROM downloads WHERE id=?", (task_id,)).fetchone()
        assert row["status"] == "queued"
        assert row["filename"] == "renamed.gguf"
        assert row["connections"] == 8
    finally:
        server.stop()
        queue._poll.stop()
        queue._ext_poll.stop()
        queue._drop_poll.stop()


def test_settings_migration_creates_distinct_api_token_without_changing_rpc_secret(
    tmp_path, monkeypatch
):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    settings_path = config_dir / "settings.json"
    config_dir.mkdir()
    rpc_secret = "r" * 32
    settings_path.write_text(json.dumps({"rpc_secret": rpc_secret, "rpc_port": 6800}))
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", settings_path)

    settings = config.Settings.load()

    assert settings.rpc_secret == rpc_secret
    assert len(settings.api_token) >= 24
    assert settings.api_token != rpc_secret
    persisted = json.loads(settings_path.read_text())
    assert persisted["rpc_secret"] == rpc_secret
    assert persisted["api_token"] == settings.api_token


def test_settings_migration_repairs_invalid_api_types(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    settings_path = config_dir / "settings.json"
    config_dir.mkdir()
    settings_path.write_text(
        json.dumps(
            {
                "rpc_secret": "r" * 32,
                "api_token": "t" * 43,
                "api_port": True,
                "api_enabled": "yes",
            }
        )
    )
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", settings_path)

    settings = config.Settings.load()

    assert settings.api_port == config.DEFAULT_API_PORT
    assert settings.api_enabled is True
    persisted = json.loads(settings_path.read_text())
    assert persisted["api_port"] == config.DEFAULT_API_PORT
    assert persisted["api_enabled"] is True


def test_windows_packaging_explicitly_includes_api_server_and_client():
    root = Path(__file__).resolve().parents[1]
    wine_script = root / "scripts" / "build-windows-wine.sh"
    native_script = root / "scripts" / "build-windows.ps1"
    workflow = root / ".github" / "workflows" / "release.yml"
    assert "--hidden-import cove.api_server" in wine_script.read_text(encoding="utf-8")
    assert "--hidden-import\", \"cove.api_server" in native_script.read_text(encoding="utf-8")
    workflow_text = workflow.read_text(encoding="utf-8")
    assert workflow_text.count("--hidden-import cove.api_server") == 2
    assert "Cove-AI-Client-${{ steps.ver.outputs.version }}.zip" in workflow_text
    for name in ("cove_api.py", "cove-api.cmd", "wrapper_config.json", "README.md"):
        assert (root / "tools" / "cove-api" / name).is_file()
