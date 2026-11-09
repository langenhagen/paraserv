#!/usr/bin/env python3
"""Parakeet speech-to-text client that talks to a running parakeet_server.py.

The microphone listener imports transcribe() from here. As a command, it
transcribes a WAV file or stops the server. Starts the server in the
background if it is not running; the server then keeps running after this
client exits. The server is never restarted automatically after a failure.

Usage:

    parakeet_client.py FILE.wav        print the transcript of a 16 kHz mono
                                       16-bit WAV file
    parakeet_client.py --stop-server   stop the running server, freeing its memory
    parakeet_client.py --help          show help
"""

import argparse
import socket
import subprocess
import sys
import time
import wave
from contextlib import suppress
from pathlib import Path

import numpy as np

from paraserv_protocol import (
    SAMPLE_RATE,
    SERVER_LOG_PATH,
    SERVER_SOCKET_PATH,
    ensure_state_dir,
    read_frame,
    send_frame,
)

SERVER_SCRIPT = Path(__file__).resolve().parent / "parakeet_server.py"
# First start downloads the model if it is not cached yet.
STARTUP_TIMEOUT_S = 600
STARTUP_POLL_INTERVAL_S = 0.1


def _connect() -> socket.socket:
    """Connect to the server socket; raise OSError if no server listens."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(SERVER_SOCKET_PATH))
    except OSError:
        sock.close()
        raise
    return sock


def _start_server() -> subprocess.Popen[bytes]:
    """Start the server detached from this terminal, logging to SERVER_LOG_PATH."""
    ensure_state_dir()
    print(f"paraserv: starting server, log: {SERVER_LOG_PATH}", file=sys.stderr)
    with SERVER_LOG_PATH.open("ab") as log_file:
        return subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT)],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,  # Ctrl-C in this terminal must not reach the server
        )


def connect_or_start_server() -> socket.socket:
    """Connect to the running server, starting it first if necessary."""
    with suppress(FileNotFoundError, ConnectionRefusedError):
        return _connect()

    server_process = _start_server()
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while True:
        with suppress(FileNotFoundError, ConnectionRefusedError):
            return _connect()
        # Exit code 0 means another server won the start race; keep waiting for it.
        returncode = server_process.poll()
        if returncode not in {None, 0}:
            sys.exit(
                f"paraserv: server exited with code {returncode}, see {SERVER_LOG_PATH}"
            )
        if time.monotonic() > deadline:
            sys.exit(
                f"paraserv: server not ready in {STARTUP_TIMEOUT_S} s, "
                f"see {SERVER_LOG_PATH}"
            )
        time.sleep(STARTUP_POLL_INTERVAL_S)


def transcribe(audio: np.ndarray) -> str:
    """Return the transcript of mono float32 audio at SAMPLE_RATE."""
    with connect_or_start_server() as sock, sock.makefile("rb") as rfile:
        send_frame(sock, {"command": "transcribe"}, audio.astype(np.float32).tobytes())
        frame = read_frame(rfile)
    if frame is None:
        sys.exit(f"paraserv: server hung up mid-request, see {SERVER_LOG_PATH}")
    header, _ = frame
    return header["text"]


def stop_server() -> None:
    """Ask the running server to exit; do nothing if none is running."""
    try:
        sock = _connect()
    except FileNotFoundError, ConnectionRefusedError:
        print("paraserv: server is not running", file=sys.stderr)
        return
    with sock, sock.makefile("rb") as rfile:
        send_frame(sock, {"command": "stop"})
        read_frame(rfile)
    print("paraserv: server stopped", file=sys.stderr)


def read_wav(path: str) -> np.ndarray:
    """Return a 16 kHz mono 16-bit WAV file as float32 samples in [-1, 1]."""
    with wave.open(path, "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
            SAMPLE_RATE,
            1,
            2,
        ):
            sys.exit(f"paraserv: {path} is not a {SAMPLE_RATE} Hz mono 16-bit WAV file")
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    return samples.astype(np.float32) / 32768


def main() -> None:
    """Transcribe a WAV file, or stop the server."""
    parser = argparse.ArgumentParser(
        description="Transcribe speech with the background Parakeet server.",
    )
    parser.add_argument("file", nargs="?", help="16 kHz mono 16-bit WAV file")
    parser.add_argument(
        "--stop-server",
        action="store_true",
        help="stop the running Parakeet server and exit",
    )
    args = parser.parse_args()

    if args.stop_server:
        stop_server()
    elif args.file:
        print(transcribe(read_wav(args.file)))
    else:
        parser.print_usage()
        sys.exit(2)


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        main()
