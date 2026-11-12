#!/usr/bin/env python3
r"""Run Claude Code with speech input from the microphone listener.

Starts `claude` in a pseudo-terminal and forwards keystrokes, output, and
window resizes unchanged, so Claude Code looks and works as before, typing
included. Also listens on the inject socket STATE_DIR/inject-<pid>.sock and
types the text of every connection into Claude Code's prompt field; "\r"
submits. Starts the microphone listener (listener.py) in the background if it
is not running.

Ctrl+\ pauses or resumes the listener for all pclaude sessions: it creates or
removes the marker file STATE_DIR/listener-paused and does not reach Claude
Code.

Usage:

    pclaude.py [CLAUDE_ARGS...]     run claude with these arguments

Test without voice:

    printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock
"""

import fcntl
import os
import pty
import select
import signal
import socket
import subprocess
import sys
import termios
import tty
from contextlib import suppress
from pathlib import Path

from paraserv_protocol import (
    LISTENER_LOG_PATH,
    LISTENER_PAUSED_PATH,
    ensure_state_dir,
    inject_socket_path,
)

LISTENER_SCRIPT = Path(__file__).resolve().parent / "listener.py"
READ_SIZE = 65536
# Upper bound for reading one inject connection, so a stuck sender cannot
# freeze the terminal.
INJECT_READ_TIMEOUT_S = 1.0

# Ctrl+\ as a plain control byte, and as the CSI u sequence that terminals and
# tmux send instead once Claude Code turns on extended key reporting.
PAUSE_KEYS = (b"\x1c", b"\x1b[92;5u")


def _write_all(fd: int, data: bytes) -> None:
    """Write all of data to fd, which may take several writes."""
    while data:
        written = os.write(fd, data)
        data = data[written:]


def _start_listener() -> None:
    """Start the microphone listener detached, logging to LISTENER_LOG_PATH.

    A listener that is already running makes the new one exit right away.
    """
    with LISTENER_LOG_PATH.open("ab") as log_file:
        subprocess.Popen(
            [sys.executable, str(LISTENER_SCRIPT)],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,  # Ctrl-C in this terminal must not reach it
        )


def _take_pause_keys(data: bytes) -> bytes:
    r"""Toggle the listener pause once per Ctrl+\ in data; return data without them."""
    for key in PAUSE_KEYS:
        for _ in range(data.count(key)):
            if LISTENER_PAUSED_PATH.exists():
                LISTENER_PAUSED_PATH.unlink()
            else:
                LISTENER_PAUSED_PATH.touch()
        data = data.replace(key, b"")
    return data


def _read_inject(server: socket.socket) -> bytes:
    """Accept one inject connection and return everything it sent."""
    conn, _ = server.accept()
    with conn:
        conn.settimeout(INJECT_READ_TIMEOUT_S)
        chunks = []
        with suppress(TimeoutError):
            while chunk := conn.recv(READ_SIZE):
                chunks.append(chunk)
    return b"".join(chunks)


def _relay(master_fd: int, server: socket.socket) -> None:
    """Shuttle bytes between the terminal, Claude, and the inject socket.

    Returns once Claude closes its side of the pseudo-terminal.
    """
    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    sources = [master_fd, stdin_fd, server]
    while True:
        readable, _, _ = select.select(sources, [], [])
        if master_fd in readable:
            try:
                data = os.read(master_fd, READ_SIZE)
            except OSError:  # EIO on Linux once the child closed the terminal
                return
            if not data:  # EOF on macOS once the child closed the terminal
                return
            _write_all(stdout_fd, data)
        if stdin_fd in readable:
            data = os.read(stdin_fd, READ_SIZE)
            if data:
                _write_all(master_fd, _take_pause_keys(data))
            else:
                sources.remove(stdin_fd)
        if server in readable:
            _write_all(master_fd, _read_inject(server))


def main() -> int:
    """Run claude in a pseudo-terminal and return its exit code."""
    if not sys.stdin.isatty():
        sys.exit("pclaude: standard input must be a terminal")
    stdin_fd = sys.stdin.fileno()
    window_size = fcntl.ioctl(stdin_fd, termios.TIOCGWINSZ, b"\0" * 8)

    pid, master_fd = pty.fork()
    if pid == 0:
        # Child: give the new terminal the real one's size before claude reads it.
        fcntl.ioctl(sys.stdin.fileno(), termios.TIOCSWINSZ, window_size)
        try:
            os.execvp("claude", ["claude", *sys.argv[1:]])
        except OSError as error:
            print(f"pclaude: cannot run claude: {error}", file=sys.stderr)
            os._exit(127)

    def forward_window_size(_signum: int, _frame: object) -> None:
        """Copy the real terminal's size to Claude's; the kernel then signals it."""
        size = fcntl.ioctl(stdin_fd, termios.TIOCGWINSZ, b"\0" * 8)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)

    ensure_state_dir()
    socket_path = inject_socket_path(os.getpid())
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen()
    _start_listener()

    signal.signal(signal.SIGWINCH, forward_window_size)
    saved_mode = tty.setraw(stdin_fd)
    try:
        _relay(master_fd, server)
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, saved_mode)
        server.close()
        socket_path.unlink(missing_ok=True)
        os.close(master_fd)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(main())
