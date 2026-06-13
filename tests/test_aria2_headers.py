"""Test that Aria2RPC.add_uri() forwards custom headers to aria2."""
import json
from unittest.mock import MagicMock, patch

from cove.aria2 import Aria2RPC
from cove.config import Settings


def _make_rpc() -> Aria2RPC:
    s = Settings()
    s.rpc_port = 16800
    s.rpc_secret = "test-secret"
    return Aria2RPC(s)


def test_add_uri_without_headers():
    """Baseline: no headers param sends opts without 'header' key."""
    rpc = _make_rpc()
    with patch.object(rpc, "_call", return_value="gid-abc") as mock:
        gid = rpc.add_uri(["https://example.com/f.zip"], "/tmp", 4)
        assert gid == "gid-abc"
        args = mock.call_args[0]
        opts = args[1][1]
        assert "header" not in opts


def test_add_uri_with_headers():
    """Headers list is forwarded as aria2's 'header' option."""
    rpc = _make_rpc()
    with patch.object(rpc, "_call", return_value="gid-def") as mock:
        headers = ["Cookie: session=abc123", "Referer: https://example.com/page"]
        gid = rpc.add_uri(
            ["https://example.com/f.zip"], "/tmp", 4, headers=headers
        )
        assert gid == "gid-def"
        args = mock.call_args[0]
        opts = args[1][1]
        assert opts["header"] == headers


def test_add_uri_with_empty_headers():
    """Empty headers list is not forwarded."""
    rpc = _make_rpc()
    with patch.object(rpc, "_call", return_value="gid-ghi") as mock:
        gid = rpc.add_uri(
            ["https://example.com/f.zip"], "/tmp", 4, headers=[]
        )
        args = mock.call_args[0]
        opts = args[1][1]
        assert "header" not in opts
