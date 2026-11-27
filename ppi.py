#!/usr/bin/env python3
r"""Run pi with speech input and spoken replies.

The wrapper runs `pi` in a pseudo-terminal, so pi looks and works as before,
typing included. It types the text of every connection on the inject socket
STATE_DIR/inject-<pid>.sock into pi's prompt field; "\r" submits.
Each assistant reply is also piped to qtts and read aloud.

Ctrl+\ pauses or resumes the listener for all wrapper sessions.

Usage:

    ppi.py [PI_ARGS...]     run pi with these arguments

Test without voice:

    printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock
"""

import sys
from pathlib import Path

from pty_agent import run

TTS_EXTENSION = Path(__file__).resolve().parent / "pi_tts.ts"

if __name__ == "__main__":
    sys.exit(run("pi", "ppi", extra_args=("-e", str(TTS_EXTENSION))))
