#!/usr/bin/env python3
"""Keep the Parakeet speech-to-text model loaded and transcribe audio clips.

Loads NVIDIA Parakeet TDT 0.6B v3 once, then serves requests on a Unix domain
socket, one at a time. See paraserv_protocol.py for the socket location and
the message format, and config.DEVICE for the backend.

A lock file ensures that at most one server per user runs. A second server
exits with code 0 right away, without loading the model.

Usage:

    parakeet_server.py      load the model, then serve until stopped

Stop the server with:

    parakeet_client.py --stop-server

    ...or send a SIGTERM, or press Ctrl-C.
"""

import fcntl
import logging
import signal
import socketserver
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import IO, cast

import numpy as np

import config
from paraserv_protocol import (
    SAMPLE_RATE,
    SERVER_LOCK_PATH,
    SERVER_LOG_PATH,
    SERVER_SOCKET_PATH,
    ensure_state_dir,
    read_frame,
    send_frame,
)

MLX_REPO = "mlx-community/parakeet-tdt-0.6b-v3"
ONNX_MODEL = "nemo-parakeet-tdt-0.6b-v3"

logger = logging.getLogger("parakeet-server")

type Transcriber = Callable[[np.ndarray], str]


def _resolve_mlx_model_path(repo: str) -> Path:
    """Return the local model directory, downloading only if it is not cached.

    mlx-audio contacts Hugging Face whenever it gets a repo name, even for a
    cached model. Passing the cached directory instead keeps runs offline.
    """
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from mlx_audio.utils import (
        DEFAULT_ALLOW_PATTERNS,
        get_model_path,
    )

    try:
        # mlx-audio downloads only these patterns. Without them the cache
        # counts as incomplete because README.md and .gitattributes are missing.
        return Path(
            snapshot_download(
                repo,
                local_files_only=True,
                allow_patterns=DEFAULT_ALLOW_PATTERNS,
            )
        )
    except LocalEntryNotFoundError:
        logger.info("%s is not cached yet, downloading", repo)
        return get_model_path(repo)


def _load_transcriber(device: str) -> Transcriber:
    """Load Parakeet for `device` and return a mono float32 audio -> text function."""
    # Import only the selected backend; each takes seconds to load.
    if device == "gpu":
        import mlx.core as mx
        from mlx_audio.stt import load

        logger.info("device: gpu (MLX %s)", mx.default_device())
        model = load(_resolve_mlx_model_path(MLX_REPO))
        return lambda audio: model.generate(mx.array(audio)).text.strip()

    import onnx_asr

    # Without an explicit provider, onnxruntime on macOS also uses CoreML.
    logger.info("device: cpu (onnxruntime CPUExecutionProvider)")
    # onnx-asr looks in the Hugging Face cache before downloading.
    model = onnx_asr.load_model(
        ONNX_MODEL,
        quantization="int8",
        providers=["CPUExecutionProvider"],
    )
    return lambda audio: model.recognize(audio, sample_rate=SAMPLE_RATE).strip()


class TranscribeHandler(socketserver.StreamRequestHandler):
    """Handle one request: transcribe an audio clip, or stop."""

    def handle(self) -> None:
        """Read the request frame and dispatch on its command."""
        server = cast("ParakeetServer", self.server)
        frame = read_frame(self.rfile)
        if frame is None:
            return
        request, audio_bytes = frame
        if request["command"] == "stop":
            logger.info("stop requested")
            server.stop_requested = True
            send_frame(self.request, {"type": "done"})
            return
        audio = np.frombuffer(audio_bytes, dtype=np.float32)
        text = server.transcribe(audio)
        logger.info(
            "transcribe: %.1f s -> %d characters", len(audio) / SAMPLE_RATE, len(text)
        )
        try:
            send_frame(self.request, {"type": "text", "text": text})
        except BrokenPipeError, ConnectionResetError:
            logger.info("client disconnected before the transcript was sent")


class ParakeetServer(socketserver.UnixStreamServer):
    """Unix socket server that holds the loaded Parakeet model."""

    def __init__(self, transcribe: Transcriber) -> None:
        """Bind the socket and keep the transcriber for the request handler."""
        super().__init__(str(SERVER_SOCKET_PATH), TranscribeHandler)
        self.transcribe = transcribe
        self.stop_requested = False


def _acquire_single_instance_lock() -> IO[str] | None:
    """Return the locked lock file, or None if another server holds the lock.

    The caller must keep the returned file object open for the server's lifetime.
    """
    lock_file = SERVER_LOCK_PATH.open("w")  # stays open to hold the lock
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    return lock_file


def _raise_keyboard_interrupt(_signum: int, _frame: object) -> None:
    """Turn SIGTERM into the same clean shutdown path as Ctrl-C."""
    raise KeyboardInterrupt


def main() -> None:
    """Load the model once, then serve requests until stopped."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    ensure_state_dir()
    lock_file = _acquire_single_instance_lock()
    if lock_file is None:
        logger.info("another parakeet server is already running; exiting")
        return

    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    logger.info("loading model (log file for started servers: %s)", SERVER_LOG_PATH)
    transcribe = _load_transcriber(config.DEVICE)
    # Run the model once, so that the first real request is as fast as later ones.
    transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))

    # A socket file left over from a crashed server blocks bind(). Holding the
    # lock guarantees that no live server uses it.
    SERVER_SOCKET_PATH.unlink(missing_ok=True)
    server = ParakeetServer(transcribe)
    logger.info("ready on %s", SERVER_SOCKET_PATH)
    try:
        while not server.stop_requested:
            server.handle_request()
    except KeyboardInterrupt:
        logger.info("interrupted")
    finally:
        server.server_close()
        SERVER_SOCKET_PATH.unlink(missing_ok=True)
        lock_file.close()
        logger.info("stopped")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        main()
