#!/usr/bin/env python3
r"""Run Ollama with speech input from the microphone listener.

The wrapper runs `ollama` in a pseudo-terminal, so Ollama looks and works as
before, typing included. It types the text of every connection on the inject
socket STATE_DIR/inject-<pid>.sock into Ollama's prompt field; "\r" submits.

Ctrl+\ pauses or resumes the listener for all wrapper sessions.

Usage:

    pollama.py run MODEL [OLLAMA_ARGS...]     run Ollama with these arguments

Test without voice:

    printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock
"""

import sys

from pty_agent import run

if __name__ == "__main__":
    sys.exit(run("ollama", "pollama"))
