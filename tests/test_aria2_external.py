"""Tests for the concurrency cap and external-download discovery."""
from unittest.mock import MagicMock, patch

from cove.aria2 import Aria2Daemon, Aria2RPC, MAX_CONCURRENT_DOWNLOADS
from cove.config import Settings


def test_daemon_lifts_max_concurrent_downloads():
    """aria2 defaults to 5; the daemon must pass an explicit higher cap."""
    daemon = Aria2Daemon(Settings())
    with patch("cove.aria2._resolve_aria2c", return_value="aria2c"), \
         patch("cove.aria2.DATA_DIR", MagicMock()), \
         patch("cove.aria2.ARIA2_SESSION", MagicMock()), \
         patch("cove.aria2.subprocess.Popen") as popen, \
         patch.object(Aria2RPC, "get_version", return_value={"version": "1.37"}):
        daemon.start()

    args = popen.call_args[0][0]
    assert f"--max-concurrent-downloads={MAX_CONCURRENT_DOWNLOADS}" in args
    assert MAX_CONCURRENT_DOWNLOADS > 5


def _rpc() -> Aria2RPC:
    s = Settings()
    s.rpc_secret = "test"
    return Aria2RPC(s)


def test_tell_external_snapshot_combines_active_and_stopped():
    rpc = _rpc()
    with patch.object(rpc, "_call", side_effect=[[{"gid": "a"}], [{"gid": "b"}]]) as m:
        out = rpc.tell_external_snapshot()
    assert out == [{"gid": "a"}, {"gid": "b"}]
    methods = [c.args[0] for c in m.call_args_list]
    assert methods == ["aria2.tellActive", "aria2.tellStopped"]


def test_tell_stopped_passes_offset_num_keys():
    rpc = _rpc()
    with patch.object(rpc, "_call", return_value=[]) as m:
        rpc.tell_stopped()
    method, params = m.call_args[0]
    assert method == "aria2.tellStopped"
    assert params[0] == 0 and params[1] == 1000
    assert "gid" in params[2] and "status" in params[2]
