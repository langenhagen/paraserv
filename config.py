"""User settings for the Parakeet server and the microphone listener.

The comment on each setting says which program reads it.

The server reads its setting once at start. Apply a server setting by
stopping the server with `parakeet_client.py --stop-server`; the next
transcription starts a fresh one.

The listener reloads this file when it changes, so a listener setting applies
within about one poll interval after saving. If the file fails to load, the
listener logs the error and keeps the old settings.
"""

# Server setting. Parakeet backend. "cpu": int8 ONNX via onnx-asr (0.7 GB
# download). "gpu": MLX via mlx-audio (2.5 GB download).
DEVICE = "cpu"

# Listener setting. A pause of this length ends a spoken turn and sends it to
# Claude Code.
MIN_SILENCE_MS = 1500

# Listener setting. Cut a turn at this length even without a pause.
MAX_SEGMENT_SECONDS = 30.0

# Listener setting. A turn that ends with this word submits the prompt to
# Claude Code right away, without waiting for SUBMIT_SILENCE_MS. The keyword
# itself is not sent to Claude, and a turn of only this word just presses
# Enter. Case and trailing punctuation do not matter. "" disables it.
SUBMIT_KEYWORD = "roger"

# Listener setting. Submit the prompt after this much silence since your last
# word. Each turn is typed after MIN_SILENCE_MS already; speaking again before
# SUBMIT_SILENCE_MS adds to the same prompt. 0 disables it, so only
# SUBMIT_KEYWORD submits, and turns pile up in the prompt field until then.
SUBMIT_SILENCE_MS = 3400

# Listener setting. A turn that ends with this phrase gets no Enter after
# SUBMIT_SILENCE_MS, however long the silence lasts. The next turn without the
# phrase submits everything typed so far. The phrase itself is not typed. Case
# and punctuation do not matter. "" disables it.
HOLD_PHRASE = "hold it"

# Listener setting. A turn that ends with this phrase pauses listening, like
# Ctrl+\ in pclaude; Ctrl+\ resumes it. The text before the phrase is typed
# as usual, the phrase itself is not. Case and punctuation do not matter. ""
# disables it. The pause holds across pclaude restarts.
PAUSE_PHRASE = "stop listening"

# Listener setting. Wait at least this long between the transcript and its
# Enter.
# Claude Code may treat text and Enter that arrive together as a paste and
# insert a line break. Leave it as is; raise it only if a turn lands as an
# extra line instead of being submitted.
SUBMIT_DELAY_S = 0.1

# Listener setting. Microphone polling interval.
POLL_MS = 150

# Listener setting. Re-transcribe the audio of an unfinished turn after this
# much new speech and show it in the prompt field as a provisional transcript,
# replaced at the pause by the final one. 0 disables provisional transcripts.
PARTIAL_SECONDS = 1.0
