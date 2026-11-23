"""Example configuration for the Parakeet server and the microphone listener.

Copy this file to config.py and edit that copy. config.py is gitignored, so
your settings, replacements, and keyphrases stay on this machine. The listener
reloads config.py on save; the server reads its setting once at start. Apply a
server setting by stopping the server with `parakeet_client.py --stop-server`;
the next transcription starts a fresh one.

Every uppercase name here becomes an attribute of settings.py, which is what
the programs read.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# Server setting. Parakeet backend. "cpu": int8 ONNX via onnx-asr (0.7 GB
# download). "gpu": MLX via mlx-audio (2.5 GB download).
DEVICE: str = "cpu"

# Listener setting. A pause of this length ends a spoken turn and sends it to
# the active CLI.
MIN_SILENCE_MS: int = 1500

# Listener setting. Cut a turn at this length even without a pause.
MAX_SEGMENT_SECONDS: float = 30.0

# Listener setting. A turn that ends with this word submits the prompt to
# the active CLI right away, without waiting for SUBMIT_SILENCE_MS. The keyword
# itself is not sent to the CLI, and a turn of only this word just presses
# Enter. Case and trailing punctuation do not matter. "" disables it.
SUBMIT_KEYWORD: str = "roger"

# Listener setting. Submit the prompt after this much silence since your last
# word. Each turn is typed after MIN_SILENCE_MS already; speaking again before
# SUBMIT_SILENCE_MS adds to the same prompt. 0 disables it, so only
# SUBMIT_KEYWORD submits, and turns pile up in the prompt field until then.
SUBMIT_SILENCE_MS: int = 3400

# Listener setting. Drop a turn with less speech than this before it reaches
# Parakeet, so nothing is typed. Speech counts in 32 ms Silero frames, so use a
# multiple of 32. Other values round down, e.g. 400 acts as 384. 0 keeps every
# turn.
# See also MIN_SUBMIT_CHARS.
MIN_SPEECH_MS: int = 416

# Listener setting. A turn with fewer characters than this, such as "Okay" or a
# misheard noise, gets no Enter after SUBMIT_SILENCE_MS; it stays in the prompt
# field. It is still sent along if longer text before it waits for its Enter.
# The submit keyword and the Enter key still submit it. 0 disables it.
# See also MIN_SPEECH_MS.
MIN_SUBMIT_CHARS: int = 6

# Listener setting. A turn that ends with this phrase gets no Enter after
# SUBMIT_SILENCE_MS, however long the silence lasts. The next turn without the
# phrase submits everything typed so far. The phrase itself is not typed. Case
# and punctuation do not matter. "" disables it.
HOLD_PHRASE: str = "hold it"

# Listener setting. A turn that ends with this phrase clears the whole prompt
# field, including earlier turns and text typed by hand, and cancels a
# pending Enter. In Claude Code, Ctrl+Y brings the text back. Case and
# punctuation do not matter. "" disables it.
CLEAR_PHRASE: str = "clear message"

# Listener setting. A turn that ends with this phrase pauses listening, like
# Ctrl+\ in any wrapper; Ctrl+\ resumes it. The text before the phrase is typed
# as usual, the phrase itself is not. Case and punctuation do not matter. ""
# disables it. The pause holds across wrapper restarts.
PAUSE_PHRASE: str = "stop listening"

# Listener setting. Wait at least this long between the transcript and its
# Enter.
# The CLI may treat text and Enter that arrive together as a paste and
# insert a line break. Leave it as is; raise it only if a turn lands as an
# extra line instead of being submitted.
SUBMIT_DELAY_S: float = 0.1

# Listener setting. Sound played when a message is submitted by emulated Enter,
# either from SUBMIT_KEYWORD or after SUBMIT_SILENCE_MS. Set to a path to an
# audio file, or to None to play no sound. Relative paths are resolved from the
# repository directory.
SUBMIT_SOUND: str | None = "sounds/submit.mp3"

# Listener setting. Microphone polling interval.
POLL_MS: int = 150

# Listener setting. Re-transcribe the audio of an unfinished turn after this
# much new speech and show it in the prompt field as a provisional transcript,
# replaced at the pause by the final one. 0 disables provisional transcripts.
PARTIAL_SECONDS: float = 1.0

# Listener setting. Phrases to replace in each turn before it is typed, as
# "heard": "replacement". Whole words, any case. An empty replacement deletes
# the phrase. Every entry applies to every language.
REPLACEMENTS: dict[str, str] = {
    # Fillers.
    "um": "",
    "uh": "",
    "äh": "",
    "ähm": "",
    "hmm": "",
    "Mm-.": "",
    # Names that Parakeet writes wrongly.
    "parasurf": "paraserv",
    "paraserve": "paraserv",
    "para kit": "Parakeet",
    "parakit": "Parakeet",
    "parachet": "Parakeet",
    "p cloud": "pclaude",
    "pcloud": "pclaude",
    "p claude": "pclaude",
    "p claud": "pclaude",
    "p clawed": "pclaude",
    "p open code": "popencode",
    "p opencode": "popencode",
    "p lama": "pollama",
    "p llama": "pollama",
    "p ollama": "pollama",
    "ol lama": "ollama",
    "o llama": "ollama",
    "open code": "opencode",
    "cloud code": "Claude Code",
    "cloud haiku": "Claude Haiku",
    "cloud hiq": "Claude Haiku",
    "cloud conversation": "Claude conversation",
    # Version numbers that Parakeet spells out.
    "v two": "V2",
    "v three": "V3",
    "v four": "V4",
}


# Listener setting. Spoken commands. A turn ending with a phrase runs its
# action instead of typing the phrase. Actions take no arguments. The longest
# matching phrase wins, and a failing action is logged without stopping the
# listener. Replace this example with your own phrase and action.
def announce_keyphrase() -> None:
    """Log a line when the example keyphrase is heard."""
    logging.getLogger("paraserv-listener").info("example keyphrase")


KEYPHRASES: dict[str, Callable[[], object]] = {
    "example phrase": announce_keyphrase,
}
