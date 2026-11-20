#!/usr/bin/env python3
r"""Listen to the microphone and type each spoken turn into Claude Code.

Silero VAD (vad.py) cuts the microphone stream at pauses of
config.MIN_SILENCE_MS. Each turn goes to the Parakeet server, and the transcript
goes to the inject socket of the newest running pclaude.

A turn that ends with config.CLEAN_PHRASE cleans the text typed by the listener
with the local Ollama model and leaves the result in the prompt for review.
config.SEND_RAW_PHRASE sends without cleaning. config.SUBMIT_KEYWORD cleans and
sends right away. Otherwise Enter follows after config.SUBMIT_SILENCE_MS of
silence, unless the last turn ends with config.HOLD_PHRASE. None of these
phrases is sent to Claude. A turn that ends with config.CLEAR_PHRASE clears the
whole prompt field with Ctrl+U. Cleaning uses the same backspace-and-retype
write as provisional transcripts, so it replaces only listener-typed text; text
typed by hand keeps its place.

Two settings ignore short utterances. config.MIN_SPEECH_MS drops a turn with
too little speech before transcription (vad.py), so nothing is typed.
config.MIN_SUBMIT_CHARS keeps a short transcript that passed it from
triggering the Enter after config.SUBMIT_SILENCE_MS.

While a turn is still running, every config.PARTIAL_SECONDS of new speech
re-transcribes the audio so far and shows it in the prompt field as a
provisional transcript: backspace over the previous provisional text, then
type the new one. The pause at the end of the turn replaces it with the
final transcript the same way. config.PARTIAL_SECONDS = 0 disables
provisional transcripts.

While the marker file LISTENER_PAUSED_PATH exists, the listener discards the
microphone audio and drops an unfinished turn together with its provisional
transcript. Ctrl+\ in pclaude creates or removes the marker file. A turn
that ends with config.PAUSE_PHRASE creates it: the listener types the text
before the phrase as usual, drops the phrase, and pauses.

The listener reloads config.py when the file changes, so listener settings
apply without a restart. If the new config.py fails to load, the listener
logs the error and keeps the old settings.

Personal replacements live in USER_REPLACEMENTS_PATH, a TOML file of
"heard" = "replacement" pairs that the listener reloads the same way. They
add to config.REPLACEMENTS and win on a clash.

pclaude starts the listener detached. A lock file ensures that at most one
listener per user runs, so several pclaude sessions share one microphone. The
listener exits once no pclaude is running.

Usage:

    listener.py      listen until no pclaude is running anymore
"""

import fcntl
import importlib
import logging
import re
import socket
import sys
import threading
import time
import tomllib
from contextlib import suppress
from pathlib import Path
from typing import IO

import numpy as np
import ollama
import sounddevice as sd

import config
from parakeet_client import connect_or_start_server, transcribe
from paraserv_protocol import (
    INJECT_SOCKET_GLOB,
    LISTENER_LOCK_PATH,
    LISTENER_PAUSED_PATH,
    SAMPLE_RATE,
    STATE_DIR,
    ensure_state_dir,
)
from vad import SpeechSegmenter

# Check this often whether any pclaude still runs.
SESSION_CHECK_INTERVAL_S = 2.0

# Check this often whether config.py or the user replacements file changed.
FILE_CHECK_INTERVAL_S = 5.0

# The terminal's delete-previous-character keystroke, same as a real backspace.
BACKSPACE = b"\x7f"

# Ctrl+U: Claude Code deletes one line of the prompt field, as shown on screen.
# Text longer than the terminal is wide continues on the next line, so a long
# message fills several. 50 Ctrl+U clear messages of up to 50 lines, also text
# typed by hand; extra ones on an empty prompt do nothing. Ctrl+Y brings the
# whole text back. Claude Code ignores 100 in one write as a paste.
CLEAR_PROMPT = b"\x15" * 50

CONFIG_PATH = Path(config.__file__)

# Optional per-machine replacements, outside the repository.
USER_REPLACEMENTS_PATH = Path.home() / ".config" / "paraserv" / "replacements.toml"

# Contents of USER_REPLACEMENTS_PATH; empty while the file is missing.
user_replacements: dict[str, str] = {}

logger = logging.getLogger("paraserv-listener")


def _reload_config() -> bool:
    """Reload config.py; on failure log the error, keep the old values, return False."""
    try:
        importlib.reload(config)
    except Exception:
        # The user edits config.py while the listener runs; a typo must not
        # kill the listener.
        logger.exception("cannot reload %s; keeping the old settings", CONFIG_PATH)
        return False
    logger.info("reloaded %s", CONFIG_PATH)
    return True


def _mtime(path: Path) -> float | None:
    """Return the modification time of path, or None if it does not exist."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def _reload_user_replacements() -> None:
    """Load USER_REPLACEMENTS_PATH; on failure log the error and keep the old ones."""
    global user_replacements
    try:
        with USER_REPLACEMENTS_PATH.open("rb") as file:
            loaded = tomllib.load(file)
    except FileNotFoundError:
        loaded = {}
    except Exception:
        # Same as config.py: a typo while editing must not kill the listener.
        logger.exception(
            "cannot load %s; keeping the old replacements", USER_REPLACEMENTS_PATH
        )
        return
    user_replacements = loaded
    logger.info("loaded %d replacements from %s", len(loaded), USER_REPLACEMENTS_PATH)


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


def _apply_replacements(text: str) -> str:
    """Apply config.REPLACEMENTS and the user file to text; an empty replacement deletes the phrase."""
    replacements = {**config.REPLACEMENTS, **user_replacements}
    for heard, replacement in sorted(
        replacements.items(), key=lambda item: len(item[0]), reverse=True
    ):
        suffix = "" if replacement else r",?\s*"
        pattern = rf"(?<!\w){re.escape(heard)}(?!\w){suffix}"
        text = re.sub(
            pattern, lambda _match, value=replacement: value, text, flags=re.IGNORECASE
        )
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    return text.strip()


def _clean(text: str) -> str:
    """Return text rewritten by Ollama, or the original when cleaning fails."""
    if not config.CLEANER_ENABLED or not text.strip():
        return text
    try:
        response = ollama.generate(
            model=config.CLEANER_MODEL,
            prompt=text,
            think=False,
            stream=False,
        )
    # pylint: disable-next=broad-exception-caught
    except Exception as error:  # noqa: BLE001 - any Ollama error must keep the text
        # A failed cleanup must not lose the message.
        logger.warning("cleaner failed: %s", error)
        return text
    return response["response"].strip() or text


def _rewrite_typed(composed: str) -> tuple[bool, str]:
    """Replace listener-typed text with its cleaned version.

    Uses the same backspace-and-retype write as _update_partial, so text typed
    by hand is not touched. Returns the new composed text for later turns.
    """
    cleaned = _clean(composed)
    if not cleaned or cleaned == composed:
        return True, composed
    rewritten = f"{cleaned} "
    if not _send(BACKSPACE * len(composed) + rewritten.encode()):
        return False, composed
    logger.info("cleaned: %r", rewritten)
    return True, rewritten


def _submit(composed: str, *, clean: bool) -> tuple[bool, str]:
    """Send Enter, optionally replacing listener-typed text with cleaned text."""
    if clean:
        running, composed = _rewrite_typed(composed)
        if not running:
            return False, composed
    return _send(b"\r"), ""


def _strip_trailing_phrase(text: str, phrase: str) -> tuple[str, bool]:
    """Remove the phrase from the end of text; return the rest and whether it was there.

    Case and punctuation between and after the phrase's words do not matter.
    Commas and spaces before the phrase go too, so for "roger", "Fix it, Roger."
    becomes "Fix it" and "Fix it. Roger." becomes "Fix it.".
    """
    words = r"\W+".join(re.escape(word) for word in phrase.split())
    match = re.search(rf"[\s,]*\b{words}\W*$", text, flags=re.IGNORECASE)
    if match is None:
        return text, False
    return text[: match.start()], True


def _take_command(text: str) -> tuple[str, str | None]:
    """Strip a trailing spoken command; return the rest and its action name."""
    if config.CLEAR_PHRASE:
        text, clear_said = _strip_trailing_phrase(text, config.CLEAR_PHRASE)
        if clear_said:
            return text, "clear"
    for phrase, action in (
        (config.CLEAN_PHRASE, "clean"),
        (config.SEND_RAW_PHRASE, "raw"),
        (config.SUBMIT_KEYWORD, "submit"),
        (config.HOLD_PHRASE, "hold"),
    ):
        if not phrase:
            continue
        text, said = _strip_trailing_phrase(text, phrase)
        if said:
            return text, action
    return text, None


def _submit_wait_s() -> float:
    """Return how long after a turn ends Enter follows without the submit keyword."""
    extra_silence_s = (config.SUBMIT_SILENCE_MS - config.MIN_SILENCE_MS) / 1000
    return max(config.SUBMIT_DELAY_S, extra_silence_s)


def _type_turn(
    text: str,
    turn_end: float,
    enter_due: float | None,
    composed: str,
) -> tuple[bool, float | None, str]:
    """Type a finished turn and decide what follows.

    Returns whether pclaude is running, when Enter is due, and the text the
    listener has typed for the current prompt.
    """
    text, action = _take_command(text)
    if action == "clear":
        return _send(CLEAR_PROMPT), None, ""

    if text:
        typed = f"{text} "
        if not _send(typed.encode()):
            return False, None, composed
        composed += typed

    if action == "clean":
        running, composed = _rewrite_typed(composed)
        return running, None, composed
    if action in ("raw", "submit"):
        time.sleep(config.SUBMIT_DELAY_S)
        running, composed = _submit(composed, clean=action == "submit")
        return running, None, composed

    # A short turn alone, such as "Okay.", gets no Enter; it joins the Enter of
    # longer text before it that still waits.
    due = None
    if (
        not action
        and config.SUBMIT_SILENCE_MS > 0
        and ((text and len(text) >= config.MIN_SUBMIT_CHARS) or enter_due is not None)
    ):
        due = turn_end + _submit_wait_s()
    return True, due, composed


def _clear_partial(shown: str) -> bool:
    """Backspace over a provisional transcript typed by _update_partial."""
    return _send(BACKSPACE * len(shown)) if shown else True


def _update_partial(shown: str, text: str) -> bool:
    """Replace a provisional transcript with a new one in a single write."""
    return _send(BACKSPACE * len(shown) + text.encode())


def _any_session_running() -> bool:
    """Return whether any pclaude inject socket accepts connections."""
    sock = _connect_newest_inject()
    if sock is None:
        return False
    sock.close()
    return True


def listen() -> None:
    """Record, segment, transcribe, and inject until no pclaude runs anymore."""
    segmenter = SpeechSegmenter(
        config.MIN_SILENCE_MS,
        config.MAX_SEGMENT_SECONDS,
        config.MIN_SPEECH_MS,
    )
    pending_chunks: list[np.ndarray] = []
    lock = threading.Lock()
    partial_shown = ""
    # Text the listener has typed for the current prompt, cleaned on submit.
    composed = ""
    partial_checked_samples = 0
    partial_audio_samples = int(config.PARTIAL_SECONDS * SAMPLE_RATE)
    paused = False
    # When to press Enter for the typed turns after SUBMIT_SILENCE_MS, or None.
    enter_due: float | None = None

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
        config_mtime = CONFIG_PATH.stat().st_mtime
        _reload_user_replacements()
        user_mtime = _mtime(USER_REPLACEMENTS_PATH)
        next_file_check = time.monotonic() + FILE_CHECK_INTERVAL_S
        while True:
            sd.sleep(config.POLL_MS)
            if time.monotonic() >= next_file_check:
                next_file_check = time.monotonic() + FILE_CHECK_INTERVAL_S
                if (mtime := _mtime(USER_REPLACEMENTS_PATH)) != user_mtime:
                    user_mtime = mtime
                    _reload_user_replacements()
                if (mtime := CONFIG_PATH.stat().st_mtime) != config_mtime:
                    config_mtime = mtime
                    if _reload_config():
                        segmenter.set_limits(
                            config.MIN_SILENCE_MS,
                            config.MAX_SEGMENT_SECONDS,
                            config.MIN_SPEECH_MS,
                        )
                        partial_audio_samples = int(
                            config.PARTIAL_SECONDS * SAMPLE_RATE
                        )
            with lock:
                fresh = pending_chunks.copy()
                pending_chunks.clear()
            if LISTENER_PAUSED_PATH.exists() != paused:
                paused = not paused
                logger.info("paused" if paused else "resumed")
                if paused:
                    segmenter.flush()  # drop the unfinished turn
                    if not _clear_partial(partial_shown):
                        logger.info("no pclaude running; exiting")
                        return
                    partial_shown = ""
                    partial_checked_samples = 0
            if fresh and not paused:
                for segment in segmenter.feed(np.concatenate(fresh)):
                    turn_end = time.monotonic()
                    if not _clear_partial(partial_shown):
                        logger.info("no pclaude running; exiting")
                        return
                    partial_shown = ""
                    partial_checked_samples = 0
                    text = _apply_replacements(transcribe(segment))
                    logger.info("heard: %r", text)
                    pause_said = False
                    if config.PAUSE_PHRASE:
                        text, pause_said = _strip_trailing_phrase(
                            text,
                            config.PAUSE_PHRASE,
                        )
                    running, enter_due, composed = _type_turn(
                        text,
                        turn_end,
                        enter_due,
                        composed,
                    )
                    if not running:
                        logger.info("no pclaude running; exiting")
                        return
                    if pause_said:
                        LISTENER_PAUSED_PATH.touch()
                        paused = True
                        segmenter.flush()  # drop the speech after the pause phrase
                        logger.info("paused by the pause phrase")
                        break

                current = segmenter.current_segment
                if current is None and partial_shown:
                    # The segmenter dropped the turn for too little speech.
                    if not _clear_partial(partial_shown):
                        logger.info("no pclaude running; exiting")
                        return
                    partial_shown = ""
                    partial_checked_samples = 0
                if (
                    not paused
                    and config.PARTIAL_SECONDS > 0
                    and current is not None
                    and len(current) - partial_checked_samples >= partial_audio_samples
                ):
                    partial_checked_samples = len(current)
                    partial_text = _apply_replacements(transcribe(current))
                    if partial_text != partial_shown:
                        if not _update_partial(partial_shown, partial_text):
                            logger.info("no pclaude running; exiting")
                            return
                        partial_shown = partial_text
            # Speaking again before enter_due adds the new turn to the same prompt.
            if (
                enter_due is not None
                and time.monotonic() >= enter_due
                and segmenter.current_segment is None
            ):
                enter_due = None
                running, composed = _submit(composed, clean=True)
                if not running:
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
