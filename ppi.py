#!/usr/bin/env python3
r"""Run pi with speech input from the microphone listener.

The wrapper runs `pi` in a pseudo-terminal, so pi looks and works as before,
typing included. It types the text of every connection on the inject socket
STATE_DIR/inject-<pid>.sock into pi's prompt field; "\r" submits.

Ctrl+\ pauses or resumes the listener for all wrapper sessions.

Usage:

    ppi.py [PI_ARGS...]     run pi with these arguments

Test without voice:

    printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock
"""

import sys

from pty_agent import run

if __name__ == "__main__":
    sys.exit(run("pi", "ppi"))
