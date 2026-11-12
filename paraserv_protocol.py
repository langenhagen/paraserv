r"""Shared file locations and message framing for paraserv's programs.

The Parakeet server listens on a Unix domain socket. Every message in both
directions is one frame:

    4 bytes     big-endian length of the JSON header
    N bytes     JSON header (UTF-8)
    M bytes     raw payload; M is the header's "audio_bytes" value (default 0)

Requests (client -> server), one frame per connection:

    {"command": "transcribe", "audio_bytes": M} followed by M bytes of mono
    float32 PCM at SAMPLE_RATE
    {"command": "stop"}

Responses (server -> client):

    to "transcribe": {"type": "text", "text": "..."}
    to "stop": {"type": "done"}, then the server exits

Each pclaude process listens on its own inject socket,
STATE_DIR/inject-<pid>.sock. It types the raw UTF-8 bytes of every connection
into Claude Code's prompt field; "\r" submits.

While the marker file STATE_DIR/listener-paused exists, the listener discards
the microphone audio. Ctrl+\ in pclaude creates or removes it; the
listener creates it when it hears config.PAUSE_PHRASE.
"""

import json
import os
import struct
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import io
    import socket

# Parakeet and Silero VAD both take 16 kHz audio.
SAMPLE_RATE = 16000

HEADER_LENGTH = struct.Struct(">I")


def _state_dir() -> Path:
    """Return the per-user directory for the sockets, lock files, and log files.

    Uses $XDG_RUNTIME_DIR on Linux (set by systemd for login sessions and user
    services) and ~/.cache elsewhere, e.g. on macOS.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime_dir) if runtime_dir else Path.home() / ".cache"
    return base / "paraserv"


STATE_DIR = _state_dir()
SERVER_SOCKET_PATH = STATE_DIR / "parakeet-server.sock"
SERVER_LOCK_PATH = STATE_DIR / "parakeet-server.lock"
SERVER_LOG_PATH = STATE_DIR / "parakeet-server.log"
LISTENER_LOCK_PATH = STATE_DIR / "listener.lock"
LISTENER_LOG_PATH = STATE_DIR / "listener.log"
LISTENER_PAUSED_PATH = STATE_DIR / "listener-paused"
INJECT_SOCKET_GLOB = "inject-*.sock"


def inject_socket_path(pid: int) -> Path:
    """Return the inject socket path of the pclaude process with this pid."""
    return STATE_DIR / f"inject-{pid}.sock"


def ensure_state_dir() -> None:
    """Create the state directory, readable by the current user only."""
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def send_frame(sock: socket.socket, header: dict[str, Any], audio: bytes = b"") -> None:
    """Send one frame with the given JSON header and optional audio payload."""
    if audio:
        header = header | {"audio_bytes": len(audio)}
    header_bytes = json.dumps(header).encode()
    sock.sendall(HEADER_LENGTH.pack(len(header_bytes)) + header_bytes + audio)


def _exactly(data: bytes, expected_length: int) -> bytes:
    """Return data, or raise if the connection ended in the middle of a frame."""
    if len(data) != expected_length:
        msg = f"connection closed mid-frame ({len(data)} of {expected_length} bytes)"
        raise ConnectionError(msg)
    return data


def read_frame(rfile: io.BufferedIOBase) -> tuple[dict[str, Any], bytes] | None:
    """Read one frame; return (header, audio), or None if the peer closed the
    connection cleanly before the frame started.
    """
    length_bytes = rfile.read(HEADER_LENGTH.size)
    if not length_bytes:
        return None
    (header_length,) = HEADER_LENGTH.unpack(_exactly(length_bytes, HEADER_LENGTH.size))
    header = json.loads(_exactly(rfile.read(header_length), header_length))
    audio_length = header.get("audio_bytes", 0)
    audio = _exactly(rfile.read(audio_length), audio_length) if audio_length else b""
    return header, audio
