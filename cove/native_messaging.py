"""Native messaging host for Firefox extension integration.

Communicates via stdin/stdout using the WebExtension native messaging
protocol (4-byte little-endian length prefix + JSON body). Reads Cove's
settings to connect to aria2 RPC and queue downloads.

Usage:
    python -m cove.native_messaging
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys
from typing import Any

from . import __version__
from .aria2 import Aria2RPC, Aria2Error
from .config import Settings

MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MB


def decode_message(stream: io.BufferedIOBase) -> dict | None:
    raw_length = stream.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    length = struct.unpack("@I", raw_length)[0]
    if length > MAX_MESSAGE_SIZE:
        return None
    data = stream.read(length)
    if len(data) < length:
        return None
    return json.loads(data)


def encode_message(msg: dict) -> bytes:
    body = json.dumps(msg).encode("utf-8")
    return struct.pack("@I", len(body)) + body


def validate_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    lower = url.lower().strip()
    if lower.startswith(("http://", "https://", "ftp://")):
        return True
    return False


def handle_message(
    msg: dict,
    rpc: Aria2RPC | None,
    settings: Settings | None,
) -> dict:
    action = msg.get("action", "")

    if action == "ping":
        return {"status": "ok", "version": __version__}

    if action == "download":
        url = msg.get("url", "")
        if not validate_url(url):
            return {"status": "error", "message": f"Invalid or blocked URL: {url!r}"}
        if rpc is None or settings is None:
            return {"status": "error", "message": "Cove is not configured"}

        headers: list[str] = []
        cookies = msg.get("cookies", "")
        if cookies:
            headers.append(f"Cookie: {cookies}")
        referrer = msg.get("referrer", "")
        if referrer:
            headers.append(f"Referer: {referrer}")
        user_agent = msg.get("userAgent", "")
        if user_agent:
            headers.append(f"User-Agent: {user_agent}")

        out_dir = msg.get("directory") or settings.download_dir
        filename = msg.get("filename") or None

        try:
            gid = rpc.add_uri(
                [url],
                out_dir,
                settings.connections_per_server,
                headers=headers if headers else None,
                filename=filename,
            )
            return {"status": "ok", "gid": gid, "message": "Download added to Cove"}
        except Aria2Error as e:
            return {"status": "error", "message": str(e)}

    if action == "status":
        if rpc is None:
            return {"status": "error", "message": "Cove is not configured"}
        try:
            active = rpc.tell_active()
            return {"status": "ok", "downloads": active}
        except Aria2Error as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Unknown action: {action!r}"}


def _binary_stdio() -> tuple[io.BufferedReader, io.BufferedWriter]:
    """Return binary (stdin, stdout) streams for the native messaging pipe.

    A console/dev launch exposes ``sys.stdin.buffer`` directly. But the
    packaged Windows app is a GUI-subsystem (``--windowed``) build, where
    ``sys.stdin``/``sys.stdout`` are ``None`` even though Firefox passed
    real pipe handles. In that case reconstruct binary streams from the
    inherited OS std handles, otherwise the protocol can't be read at all.
    """
    stdin = getattr(sys.stdin, "buffer", None)
    stdout = getattr(sys.stdout, "buffer", None)
    if stdin is not None and stdout is not None:
        return stdin, stdout

    if sys.platform == "win32":
        import msvcrt
        from ctypes import windll

        STD_INPUT_HANDLE = -10
        STD_OUTPUT_HANDLE = -11
        h_in = windll.kernel32.GetStdHandle(STD_INPUT_HANDLE)
        h_out = windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        fd_in = msvcrt.open_osfhandle(h_in, os.O_RDONLY | os.O_BINARY)
        fd_out = msvcrt.open_osfhandle(h_out, os.O_WRONLY | os.O_BINARY)
        return os.fdopen(fd_in, "rb"), os.fdopen(fd_out, "wb")

    return os.fdopen(0, "rb"), os.fdopen(1, "wb")


def main() -> None:
    try:
        settings = Settings.load()
        rpc = Aria2RPC(settings)
    except Exception as e:
        settings = None
        rpc = None

    stdin, stdout = _binary_stdio()

    while True:
        msg = decode_message(stdin)
        if msg is None:
            break
        response = handle_message(msg, rpc, settings)
        stdout.write(encode_message(response))
        stdout.flush()


if __name__ == "__main__":
    main()
