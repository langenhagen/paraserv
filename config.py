"""User settings for the Parakeet server, the microphone listener, and pclaude.

Edit the values here; all three programs read them at start.
"""

# Parakeet backend of the server. "cpu": int8 ONNX via onnx-asr (0.7 GB
# download). "gpu": MLX via mlx-audio (2.5 GB download).
DEVICE = "cpu"

# A pause of this length ends a spoken turn and sends it to Claude Code.
MIN_SILENCE_MS = 1000

# Cut a turn at this length even without a pause.
MAX_SEGMENT_SECONDS = 30.0

# Press Enter after each transcript, so Claude Code receives it right away.
# Without it, transcripts pile up in the prompt field, separated by spaces.
AUTO_SUBMIT = True

# Wait this long between the transcript and its Enter. Claude Code may treat
# text and Enter that arrive together as a paste and insert a line break.
SUBMIT_DELAY_S = 0.1

# Microphone polling interval of the listener.
POLL_MS = 150
