#!/usr/bin/env python3
r"""Run Claude Code with speech input from the microphone listener.

The wrapper runs `claude` in a pseudo-terminal, so Claude Code looks and works
as before, typing included. It types the text of every connection on the inject
socket STATE_DIR/inject-<pid>.sock into Claude Code's prompt field; "\r" submits.

Ctrl+\ pauses or resumes the listener for all wrapper sessions.

Usage:

    pclaude.py [CLAUDE_ARGS...]     run claude with these arguments

Test without voice:

    printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock
"""

import sys

from pty_agent import run

if __name__ == "__main__":
    sys.exit(run("claude", "pclaude"))
