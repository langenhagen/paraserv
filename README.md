# Paraserv

Live speech to text client & server with parakeet.

The main use case for me is the ability to now talk to Claude Code hands-free.
Speech from the microphone is transcribed by a local [Parakeet TDT 0.6B
v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) server and typed into
Claude Code's prompt field as if typed by hand. A headset's mute button can be
the off switch, alternatively Ctrl+\ in `pclaude` pauses and resumes
listening. Pairs with [barn-claude-jarvis](https://github.com/langenhagen/barn-claude-jarvis),
my Claude Code plugin that reads Claude's replies aloud, for a spoken
conversation both ways.

The project is structured as follows:

```
.
├── autostart/              Optional launchd agent and systemd user service for the server.
├── config.py               Settings; the listener reloads them on save.
├── LICENSE                 License definition.
├── listener.py             Records the microphone and sends each spoken turn to pclaude.
├── parakeet_client.py      Talks to the server; transcribes a WAV file or stops the server.
├── parakeet_server.py      Loads the Parakeet model once and transcribes audio clips.
├── paraserv_protocol.py    Socket locations and the message format.
├── pclaude.py              Runs claude with speech input.
├── pclaude.sh              Runs pclaude.py through the project venv.
├── pyproject.toml          Project metadata and dependencies.
├── README.md               You are here now.
└── vad.py                  Cuts the microphone stream into spoken turns with Silero VAD.
```

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
pclaude                                                     # run claude with speech input
pclaude --continue                                          # all arguments go to claude
.venv/bin/python parakeet_client.py x.wav                   # transcribe a 16 kHz mono 16-bit WAV file
.venv/bin/python parakeet_client.py --stop-server           # stop the server and free its memory
printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock  # type into pclaude without voice
```

In `pclaude`, speak and pause. Each spoken turn appears in the prompt field.

| Key or word      | Effect                                               |
| ---------------- | ---------------------------------------------------- |
| `Ctrl+\`         | Pause or resume listening in all `pclaude` sessions. |
| "roger"          | Submit the spoken message to Claude right away.      |
| "hold it"        | Wait for more speech before submitting.              |
| "clear message"  | Clear the whole message.                             |
| "stop listening" | Pause listening, like `Ctrl+\`.                      |

Your message is submitted after `SUBMIT_SILENCE_MS` of silence, 3.4 s by default.  
To submit right away, say the submit keyword ("roger" by default) as the last
word. The keyword itself does not reach Claude; it only presses Enter. Change
the keyword via `SUBMIT_KEYWORD` in `config.py`.  
To think longer, end your message with the hold phrase ("hold it" by default).
The phrase does not reach Claude either. Your next voice input again submits
after `SUBMIT_SILENCE_MS` and reacts to the submit keyword and the hold phrase
as before. Change the phrase via `HOLD_PHRASE` in `config.py`.  
Set `SUBMIT_SILENCE_MS = 0` to submit only with the submit keyword.  
Short utterances are ignored in two steps. A turn with less than
`MIN_SPEECH_MS` of speech, 416 ms by default, is dropped before transcription.
A transcript shorter than `MIN_SUBMIT_CHARS`, 6 characters by default, is typed
but not submitted after the silence. To send this off, say the submit keyword
or press Enter.  
To start over, end your message with the clear phrase ("clear message" by
default). It clears the whole prompt field; `Ctrl+Y` brings the text back.
Change the phrase via `CLEAR_PHRASE` in `config.py`.  
Pause listening by saying the pause phrase ("stop listening" by default) as the
last words of your message. Press `Ctrl+\` to resume. Change the phrase via
`PAUSE_PHRASE` in `config.py`. The pause holds across `pclaude` restarts.  
The listener reloads `config.py` on save.  
After changing `DEVICE`, stop the server; the next turn starts a fresh one.

## How It Works

`pclaude` runs `claude` in a pseudo-terminal, so Claude Code looks and works as
before, typing included. It types the text it receives on its inject socket into
the prompt field. The listener cuts the microphone stream into spoken turns at
pauses, has the server transcribe each turn, and sends the transcript to the
newest running `pclaude`. While a turn runs, a provisional transcript shows in
the prompt field; the final transcript replaces it at the pause.

All programs talk over Unix domain sockets: file-system paths that only the
current user can open, with no TCP port and no network exposure. The sockets,
lock files, and log files live in `$XDG_RUNTIME_DIR/paraserv/` on Linux and in
`~/.cache/paraserv/` on macOS.

`pclaude` starts the listener detached from the terminal; the listener starts
the server the same way if no server listens. Lock files guarantee at most one
listener and one server per user, so several `pclaude` sessions share one
microphone and one model. The listener exits once no `pclaude` runs. The server
keeps running after the last `pclaude` exits, so the next start skips the model
load. Nothing restarts the server after a crash; the next listener starts a
fresh one.

## Autostart On macOS

Optional; without it, the first `pclaude` starts the server. The launchd agent
in `autostart/` starts the server once per login and never restarts it. Run
`pclaude` once first, so that the log directory exists.

```bash
cp autostart/com.andreasl.parakeet-server.plist ~/Library/LaunchAgents/
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.andreasl.parakeet-server.plist
```

Remove it again:

```bash
launchctl bootout "gui/$(id -u)/com.andreasl.parakeet-server"
rm ~/Library/LaunchAgents/com.andreasl.parakeet-server.plist
```

## Autostart On Linux

Optional; same behavior as on macOS, via a systemd user service.

```bash
mkdir --parents ~/.config/systemd/user
cp autostart/parakeet-server.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now parakeet-server.service
journalctl --user --unit parakeet-server.service  # view the log
```

Remove it again:

```bash
systemctl --user disable --now parakeet-server.service
rm ~/.config/systemd/user/parakeet-server.service
```

## License

See [LICENSE](LICENSE) file.
