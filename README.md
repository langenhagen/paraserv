# Paraserv

Live speech to text client & server with parakeet.

The main use case for me is the ability to now talk to Claude Code, OpenCode,
pi, or Ollama hands-free. Speech from the microphone is transcribed by a local
[Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) server
and typed into the active CLI's prompt field as if typed by hand. Use `pclaude`
for Claude Code, `popencode` for OpenCode, `ppi` for pi, and `pollama` for
Ollama. A headset's mute button can be the off switch, alternatively Ctrl+\ in
any wrapper pauses and resumes listening.
Pairs with [barn-claude-jarvis](https://github.com/langenhagen/barn-claude-jarvis),
my Claude Code plugin that reads Claude's replies aloud, for a spoken
conversation both ways.

The project is structured as follows:

```
.
├── autostart/              Optional launchd agent and systemd user service for the server.
├── config.py               Personal settings; gitignored, reloaded on save.
├── config.sample.py        Documented template for config.py.
├── LICENSE                 License definition.
├── listener.py             Records the microphone and sends each spoken turn to the newest wrapper.
├── ollama_tts.py           Streams Ollama's replies to qtts.
├── parakeet_client.py      Talks to the server; transcribes a WAV file or stops the server.
├── parakeet_server.py      Loads the Parakeet model once and transcribes audio clips.
├── paraserv_protocol.py    Socket locations and the message format.
├── pclaude.py              Runs claude with speech input.
├── pclaude.sh              Runs pclaude.py through the project venv.
├── pi_tts.ts               Streams pi's replies to qtts.
├── ppi.py                  Runs pi with speech input and spoken replies.
├── ppi.sh                  Runs ppi.py through the project venv.
├── pollama.py              Runs ollama with speech input.
├── pollama.sh              Runs pollama.py through the project venv.
├── popencode.py            Runs opencode with speech input.
├── popencode.sh            Runs popencode.py through the project venv.
├── pty_agent.py            Shared pseudo-terminal wrapper for the four CLI wrappers.
├── pyproject.toml          Project metadata and dependencies.
├── README.md               You are here now.
├── settings.py             Loads config.py; the programs read settings.*.
└── vad.py                  Cuts the microphone stream into spoken turns with Silero VAD.
```

`vad.py` and the model loading come from
[parakeet-stt-hello](https://github.com/langenhagen/experiments-and-tutorials/tree/master/Python/parakeet-stt-hello).

## Setup

```bash
uv sync
cp config.sample.py config.py                           # create your personal config (gitignored)
sudo ln -sf "$PWD/pclaude.sh" /usr/local/bin/pclaude    # link the CLI so you can use it everywhere
sudo ln -sf "$PWD/popencode.sh" /usr/local/bin/popencode
sudo ln -sf "$PWD/pollama.sh" /usr/local/bin/pollama
sudo ln -sf "$PWD/ppi.sh" /usr/local/bin/ppi
```

On macOS, the terminal app needs microphone access, see System Settings >
Privacy & Security > Microphone.

## Usage

```bash
pclaude                                                     # run claude with speech input
pclaude --continue                                          # all arguments go to claude
popencode                                                   # run opencode with speech input
popencode --continue                                        # all arguments go to opencode
ppi                                                         # run pi with speech input and spoken replies
ppi --continue                                              # all arguments go to pi
pollama run qwen3.5:9b                                      # run Ollama with speech input
.venv/bin/python parakeet_client.py x.wav                   # transcribe a 16 kHz mono 16-bit WAV file
.venv/bin/python parakeet_client.py --stop-server           # stop the server and free its memory
printf 'hello' | nc -U ~/.cache/paraserv/inject-<pid>.sock  # type into the newest wrapper without voice
```

In `pclaude`, `popencode`, `ppi`, or `pollama`, speak and pause. Each spoken turn
appears in the prompt field of the wrapper you started most recently.

`pollama` reads each reply aloud as it arrives; `ppi` waits until the reply is
finished. Both use this command:

```bash
qtts --temperature 1.6 --prebuffer 0 --voice ~/Dev/barn-claude-jarvis/voices/anna/reference.wav
```

The prompt, your echoed input, and Ollama's spinner are not spoken. `ppi` uses
a pi extension, so thinking, tool calls, and code blocks are not spoken either.
`qtts` must be on `PATH`; its output goes to `~/.cache/paraserv/ollama-tts.log`
and `~/.cache/paraserv/pi-tts.log` on macOS, and to the matching files under
`$XDG_RUNTIME_DIR/paraserv/` on Linux.

| Key or word      | Effect                                               |
| ---------------- | ---------------------------------------------------- |
| `Ctrl+\`         | Pause or resume listening in all wrapper sessions.   |
| "roger"          | Submit the spoken message right away.                |
| "hold it"        | Wait for more speech before submitting.              |
| "clear message"  | Clear the whole message.                             |
| "stop listening" | Pause listening, like `Ctrl+\`.                      |

Your message is submitted after `SUBMIT_SILENCE_MS` of silence, 3.4 s by default.
Set `SUBMIT_SILENCE_MS = 0` to submit only with the submit keyword.

To submit right away, say the submit keyword ("roger" by default) as the last
word. The keyword itself does not reach the CLI; it only presses Enter. Change
the keyword via `SUBMIT_KEYWORD` in `config.py`.

If you want to think longer before sending off the message, end your message with
the hold phrase ("hold it" by default). This hold phrase does not reach the CLI
either. Your next voice input again submits after `SUBMIT_SILENCE_MS` and reacts
to the submit keyword and the hold phrase as before. Change the phrase via
`HOLD_PHRASE` in `config.py`.

Short utterances are ignored in two steps. A turn with less than
`MIN_SPEECH_MS` of speech, 416 ms by default, is dropped before transcription.
A transcript shorter than `MIN_SUBMIT_CHARS`, 6 characters by default, is typed
but not submitted after the silence. To send this off, say the submit keyword
or press Enter.

To start over, end your message with the clear phrase ("clear message" by
default). It clears the whole prompt field; in Claude Code, `Ctrl+Y` brings the
text back. Change the phrase via `CLEAR_PHRASE` in `config.py`.

Pause listening by saying the pause phrase ("stop listening" by default) as the
last words of your message. Press `Ctrl+\` to resume. Change the phrase via
`PAUSE_PHRASE` in `config.py`. The pause holds across wrapper restarts.

All settings live in `config.py`: timings, phrases, `REPLACEMENTS`, and
`KEYPHRASES`. `REPLACEMENTS` deletes fillers and fixes words that Parakeet
writes wrongly, as `"heard" = "replacement"` lines.

Put your own spoken commands in `KEYPHRASES` too. Define zero-argument action
functions and map a phrase to each function; `config.sample.py` has an example.
A turn ending with a phrase from that dict runs the action instead of typing the
phrase. Case and punctuation do not matter, and the longest matching phrase
wins.

The listener reloads `config.py` on save. If it fails to load, the listener logs
the error and keeps the previous values. After changing `DEVICE`, stop the
server; the next turn starts a fresh one.

## How It Works

`pclaude`, `popencode`, `ppi`, and `pollama` run their CLI in a pseudo-terminal,
so the CLI looks and works as before, typing included. They type the text they
receive on their inject socket into the prompt field. The listener cuts the
microphone stream into spoken turns at pauses, has the server transcribe each
turn, and sends the transcript to the newest running wrapper. While a turn runs,
a provisional transcript shows in the prompt field; the final transcript
replaces it at the pause. `pollama` also watches the CLI's output:
`ollama_tts.py` strips terminal codes and streams each assistant line to qtts.
`ppi` loads `pi_tts.ts`, which uses pi's message events to speak each finished
assistant reply with the same qtts command.

All programs talk over Unix domain sockets: file-system paths that only the
current user can open, with no TCP port and no network exposure. The sockets,
lock files, and log files live in `$XDG_RUNTIME_DIR/paraserv/` on Linux and in
`~/.cache/paraserv/` on macOS.

A wrapper starts the listener detached from the terminal; the listener starts
the server the same way if no server listens. Lock files guarantee at most one
listener and one server per user, so several wrapper sessions share one
microphone and one model. The listener exits once no wrapper runs. The server
keeps running after the last wrapper exits, so the next start skips the model
load. Nothing restarts the server after a crash; the next listener starts a
fresh one.

## Autostart On macOS

Optional; without it, the first wrapper starts the server. The launchd agent in
`autostart/` starts the server once per login and never restarts it. Run a
wrapper once first, so that the log directory exists.

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
