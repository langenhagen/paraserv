"""User settings for the Parakeet server and the microphone listener.

Each program reads these values once at start; nothing reloads them. The
comment on each setting says which program reads it.

Apply a server setting by stopping the server with
`parakeet_client.py --stop-server`; the next transcription starts a fresh one.

Apply a listener setting by restarting pclaude with no other pclaude open;
wait about 3 s between exit and relaunch so the old listener exits first.
"""

# Server setting. Parakeet backend. "cpu": int8 ONNX via onnx-asr (0.7 GB
# download). "gpu": MLX via mlx-audio (2.5 GB download).
DEVICE = "cpu"

# Listener setting. A pause of this length ends a spoken turn and sends it to
# Claude Code.
MIN_SILENCE_MS = 1500

# Listener setting. Cut a turn at this length even without a pause.
MAX_SEGMENT_SECONDS = 30.0

# Listener setting. Press Enter after each transcript, so Claude Code receives
# it right away. Without it, transcripts pile up in the prompt field,
# separated by spaces.
AUTO_SUBMIT = True

# Listener setting. Wait this long between the transcript and its Enter.
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
