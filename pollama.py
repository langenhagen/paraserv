#!/usr/bin/env python3
r"""Run Ollama with speech input and spoken replies.

The wrapper runs `ollama` in a pseudo-terminal, so Ollama looks and works as
before, typing included. It types the text of every connection on the inject
socket STATE_DIR/inject-<pid>.sock into Ollama's prompt field; "\r" submits.
Each assistant reply is also piped to qtts and read aloud.

Ctrl+\ pauses or resumes the listener for all wrapper sessions.

Usage:

    pollama.py run MODEL [OLLAMA_ARGS...]     run Ollama with these arguments

Test without voice:

    printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock
"""

import sys

from ollama_tts import ResponseSpeaker
from pty_agent import run

if __name__ == "__main__":
    speaker = ResponseSpeaker()
    try:
        sys.exit(run("ollama", "pollama", speaker))
    finally:
        speaker.close()
