#!/usr/bin/env python3
"""Listen to the microphone and type each spoken turn into Claude Code.

Silero VAD (vad.py) cuts the microphone stream at pauses of
config.MIN_SILENCE_MS. Each turn goes to the Parakeet server, and the
transcript goes to the inject socket of the newest running pclaude, followed
by Enter if config.AUTO_SUBMIT is set. The headset mute button silences the
microphone, so muted speech never reaches Claude Code.

pclaude starts the listener detached. A lock file ensures that at most one
listener per user runs, so several pclaude sessions share one microphone. The
listener exits once no pclaude is running.

Usage:

    listener.py      listen until no pclaude is running anymore
"""

import fcntl
import logging
import socket
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import IO

import numpy as np
import sounddevice as sd

import config
from parakeet_client import connect_or_start_server, transcribe
from paraserv_protocol import (
    INJECT_SOCKET_GLOB,
    LISTENER_LOCK_PATH,
    SAMPLE_RATE,
    STATE_DIR,
    ensure_state_dir,
)
from vad import SpeechSegmenter

# Check this often whether any pclaude still runs.
SESSION_CHECK_INTERVAL_S = 2.0

logger = logging.getLogger("paraserv-listener")


def _acquire_single_instance_lock() -> IO[str] | None:
    """Return the locked lock file, or None if another listener holds the lock.

    The caller must keep the returned file object open for the listener's lifetime.
    """
    lock_file = LISTENER_LOCK_PATH.open("w")  # stays open to hold the lock
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    return lock_file


def _connect_inject(path: Path) -> socket.socket | None:
    """Connect to a pclaude inject socket; remove it and return None if stale."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(path))
    except FileNotFoundError:
        sock.close()
        return None
    except ConnectionRefusedError:
        # No process listens anymore: pclaude was killed before cleaning up.
        sock.close()
        logger.info("removing stale socket %s", path)
        path.unlink(missing_ok=True)
        return None
    return sock


def _connect_newest_inject() -> socket.socket | None:
    """Connect to the newest live pclaude inject socket, or return None."""
    paths = STATE_DIR.glob(INJECT_SOCKET_GLOB)
    # A socket can vanish between glob() and stat() when its pclaude exits.
    with_times = []
    for path in paths:
        with suppress(FileNotFoundError):
            with_times.append((path.stat().st_mtime, path))
    for _, path in sorted(with_times, reverse=True):
        if (sock := _connect_inject(path)) is not None:
            return sock
    return None


def _send(data: bytes) -> bool:
    """Send data to the newest pclaude; return False if none is running."""
    sock = _connect_newest_inject()
    if sock is None:
        return False
    with sock:
        sock.sendall(data)
    return True


def inject(text: str) -> bool:
    """Type the text into the newest pclaude; return False if none is running."""
    if not config.AUTO_SUBMIT:
        return _send(f"{text} ".encode())
    if not _send(text.encode()):
        return False
    time.sleep(config.SUBMIT_DELAY_S)
    return _send(b"\r")


def _any_session_running() -> bool:
    """Return whether any pclaude inject socket accepts connections."""
    sock = _connect_newest_inject()
    if sock is None:
        return False
    sock.close()
    return True


def listen() -> None:
    """Record, segment, transcribe, and inject until no pclaude runs anymore."""
    segmenter = SpeechSegmenter(config.MIN_SILENCE_MS, config.MAX_SEGMENT_SECONDS)
    pending_chunks: list[np.ndarray] = []
    lock = threading.Lock()

    def callback(
        indata: np.ndarray,
        _frames: int,
        _time: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Collect incoming microphone chunks from the stream callback."""
        if status:
            logger.warning("microphone: %s", status)
        with lock:
            pending_chunks.append(indata[:, 0].copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=callback,
    ):
        logger.info("listening")
        next_session_check = time.monotonic() + SESSION_CHECK_INTERVAL_S
        while True:
            sd.sleep(config.POLL_MS)
            with lock:
                fresh = pending_chunks.copy()
                pending_chunks.clear()
            if fresh:
                for segment in segmenter.feed(np.concatenate(fresh)):
                    text = transcribe(segment)
                    logger.info("heard: %r", text)
                    if text and not inject(text):
                        logger.info("no pclaude running; exiting")
                        return
            if time.monotonic() >= next_session_check:
                if not _any_session_running():
                    logger.info("no pclaude running; exiting")
                    return
                next_session_check = time.monotonic() + SESSION_CHECK_INTERVAL_S


def main() -> None:
    """Start the Parakeet server if needed, then listen."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    ensure_state_dir()
    lock_file = _acquire_single_instance_lock()
    if lock_file is None:
        logger.info("another listener is already running; exiting")
        return
    with lock_file:
        # Load the model before the first turn, not during it.
        connect_or_start_server().close()
        listen()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        main()
