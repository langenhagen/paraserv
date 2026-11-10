# Paraserv

Talk to Claude Code hands-free. Speech from the microphone is transcribed by a
local [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
server and typed into Claude Code's prompt field as if typed by hand. The
headset mute button is the off switch, and Ctrl+\ in a `pclaude` pauses and
resumes listening. Pairs with kokoserv, the Kokoro text-to-speech server, for
voice output.

- `pclaude.py` runs `claude` in a pseudo-terminal, so Claude Code looks and
  works as before, typing included. It types text from its inject socket into
  the prompt field and starts the listener. Ctrl+\ toggles the marker file
  `listener-paused`, which pauses the listener for all `pclaude` sessions.
- `listener.py` records the microphone, cuts it at pauses with Silero VAD
  (`vad.py`), sends each spoken turn to the server, and sends the transcript to
  the newest running `pclaude`. It exits once no `pclaude` runs.
- `parakeet_server.py` loads the model once and transcribes audio clips, one at
  a time.
- `parakeet_client.py` talks to the server; as a command it transcribes a WAV
  file or stops the server.
- `paraserv_protocol.py` holds the socket locations and the message format.
- `config.py` holds the settings: the backend, the pause that ends a turn, and
  whether each transcript is submitted with Enter.
- `pclaude.sh` runs `pclaude.py` through the project venv; link it into `PATH`
  as `pclaude`.

`vad.py` and the model loading come from
[parakeet-stt-hello](https://github.com/langenhagen/experiments-and-tutorials/tree/master/Python/parakeet-stt-hello).

## Setup

```bash
uv sync
sudo ln -sf "$PWD/pclaude.sh" /usr/local/bin/pclaude  # link the CLI so you can use it everywhere
```

On macOS, the terminal app needs microphone access, see System Settings >
Privacy & Security > Microphone.

## Usage

```bash
pclaude                                       # run claude with speech input
pclaude --continue                            # all arguments go to claude
.venv/bin/python parakeet_client.py x.wav     # transcribe a 16 kHz mono 16-bit WAV file
.venv/bin/python parakeet_client.py --stop-server  # stop the server and free its memory
printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock  # type into a pclaude without voice
```

Create a test WAV file on macOS with
`say -o x.wav --data-format=LEI16@16000 "Hello Claude"`.

## How It Works

All programs talk over Unix domain sockets: file-system paths that only the
current user can open, with no TCP port and no network exposure. The sockets,
lock files, and log files live in `$XDG_RUNTIME_DIR/paraserv/` on Linux and in
`~/.cache/paraserv/` on macOS.

`pclaude` starts the listener detached from the terminal; the listener starts
the server the same way if no server listens. Lock files guarantee at most one
listener and one server per user, so several `pclaude` sessions share one
microphone and one model. The server keeps running after the last `pclaude`
exits, so the next start skips the model load. Nothing restarts the server
after a crash; the next listener starts a fresh one.

## License

See [LICENSE](LICENSE) file.
