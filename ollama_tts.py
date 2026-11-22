r"""Speak Ollama's assistant replies with qtts.

A pollama wrapper passes each chunk of the CLI's output to ResponseSpeaker.
It drops the prompt, the echoed input, and terminal control sequences, then
streams each line of the assistant's reply to one qtts process. Starting the
next reply cancels the previous speech through qtts.
"""

from __future__ import annotations

import codecs
import re
import subprocess  # nosec B404
from contextlib import suppress
from pathlib import Path
from typing import IO, TYPE_CHECKING

from paraserv_protocol import STATE_DIR, ensure_state_dir

if TYPE_CHECKING:
    from collections.abc import Sequence

VOICE_PATH = Path.home() / "Dev/barn-claude-jarvis/voices/anna/reference.wav"
QTTS_COMMAND: Sequence[str] = (
    "qtts",
    "--temperature",
    "1.6",
    "--prebuffer",
    "0",
    "--voice",
    str(VOICE_PATH),
)
QTTS_LOG_PATH = STATE_DIR / "ollama-tts.log"

PROMPT = ">>>"
HINT = "Send a message (/? for help)"

_ANSI = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]",
)
_SPINNER = re.compile(r"[\u2800-\u28ff]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(text: str) -> str:
    """Remove terminal control sequences and spinner frames from text."""
    return _CONTROL.sub("", _SPINNER.sub("", _ANSI.sub("", text))).strip()


def _to_prose(text: str) -> str:
    """Remove the markdown markers that qtts would otherwise read aloud."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = text.replace("`", "")
    return re.sub(r"^\s*(?:#{1,6}|[-*+]|\d+\.)\s+", "", text).strip()


class ResponseSpeaker:  # pylint: disable=too-many-instance-attributes
    """Stream Ollama's replies from PTY output to qtts.

    The attributes hold reply state, the current qtts process, and finished
    processes waiting to be reaped.
    """

    def __init__(self, command: Sequence[str] = QTTS_COMMAND) -> None:
        """Store the qtts command and start with empty reply state."""
        self._command = tuple(command)
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._buffer = ""
        self._in_response = False
        self._skip_echo = False
        self._in_code_block = False
        self._process: subprocess.Popen[str] | None = None
        self._log_file: IO[str] | None = None
        self._finished: list[subprocess.Popen[str]] = []
        self._disabled = False

    def _finish_response(self) -> None:
        """Close the current reply's text stream and reset reply state."""
        process, self._process = self._process, None
        log_file, self._log_file = self._log_file, None
        self._in_response = False
        self._in_code_block = False
        self._skip_echo = False
        if process is not None:
            if process.stdin is not None:
                with suppress(OSError):
                    process.stdin.close()
            self._finished.append(process)
        if log_file is not None:
            log_file.close()

    def close(self) -> None:
        """End any open reply and reap finished qtts processes."""
        self._finish_response()
        for process in self._finished:
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=1)

    def _start_process(self) -> None:
        """Start qtts for one reply, logging its output beside the other logs."""
        ensure_state_dir()
        try:
            log_file = QTTS_LOG_PATH.open("a", encoding="utf-8")
            # Fixed local command; no shell and no untrusted arguments.
            # The process must outlive this call to finish speaking.
            # pylint: disable-next=consider-using-with
            process = subprocess.Popen(  # noqa: S603  # nosec B603
                self._command,
                stdin=subprocess.PIPE,
                stdout=log_file,
                stderr=log_file,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            self._disabled = True
            with QTTS_LOG_PATH.open("a", encoding="utf-8") as log_file:
                log_file.write(f"cannot start qtts: {error}\n")
            return
        self._process = process
        self._log_file = log_file

    def _speak(self, text: str) -> None:
        """Send one line of reply text to qtts."""
        if self._process is None:
            self._start_process()
        if self._process is None or self._process.stdin is None:
            return
        try:
            self._process.stdin.write(f"{text}\n")
            self._process.stdin.flush()
        except OSError:
            self._finish_response()

    def _handle_line(self, line: str) -> None:
        """Update state for one complete output line."""
        if _clean(line).startswith(PROMPT):
            self._finish_response()
            tail = _clean(line.rsplit("\x1b[K", 1)[-1])
            echo = tail.removeprefix(PROMPT).replace(HINT, "").strip()
            # The echoed input shares the prompt line unless the user pressed
            # Enter without typing, in which case the next line holds the echo.
            self._skip_echo = not echo
            self._in_response = not self._skip_echo
            return
        if self._skip_echo:
            self._skip_echo = False
            self._in_response = True
            return
        if not self._in_response:
            return
        text = _clean(line)
        if text.startswith("```"):
            self._in_code_block = not self._in_code_block
            return
        if self._in_code_block or not text:
            return
        self._speak(_to_prose(text))

    def _reap_finished(self) -> None:
        """Forget qtts processes that have finished speaking."""
        self._finished = [
            process for process in self._finished if process.poll() is None
        ]

    def __call__(self, data: bytes) -> None:
        """Inspect one chunk of CLI output without changing it."""
        if self._disabled:
            return
        self._buffer += self._decoder.decode(data)
        self._reap_finished()
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._handle_line(line)
        if self._in_response and _clean(self._buffer).startswith(PROMPT):
            # Ollama prints the next prompt without a trailing newline.
            self._finish_response()
