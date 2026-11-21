"""Load the gitignored config.py and expose its uppercase names.

Copy config.sample.py to config.py to get started. The programs read settings,
not config.py directly, so the listener can reload it on save. A failed reload
keeps the values from the last successful load.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

CONFIG_PATH = Path(__file__).resolve().parent / "config.py"

logger = logging.getLogger("paraserv-settings")

# Names expected in config.py. Declared for static checkers; load() fills them.
DEVICE: str
MIN_SILENCE_MS: int
MAX_SEGMENT_SECONDS: float
SUBMIT_KEYWORD: str
SUBMIT_SILENCE_MS: int
MIN_SPEECH_MS: int
MIN_SUBMIT_CHARS: int
HOLD_PHRASE: str
CLEAR_PHRASE: str
PAUSE_PHRASE: str
SUBMIT_DELAY_S: float
POLL_MS: int
PARTIAL_SECONDS: float
REPLACEMENTS: dict[str, str]
KEYPHRASES: dict[str, Callable[[], object]]


def _read_config() -> dict[str, object]:
    """Execute config.py in a fresh namespace and return its uppercase names."""
    if not CONFIG_PATH.exists():
        message = f"missing {CONFIG_PATH}; copy config.sample.py to config.py"
        raise FileNotFoundError(message)
    namespace: dict[str, object] = {
        "__name__": "paraserv_user_config",
        "__file__": str(CONFIG_PATH),
    }
    # Compile the source directly so a same-second save with the same file size
    # cannot be served from stale bytecode cache. W0122, S102 and B102 all flag
    # this deliberate exec of the user's Python config.
    code = compile(CONFIG_PATH.read_text(encoding="utf-8"), str(CONFIG_PATH), "exec")
    exec(code, namespace)  # noqa: S102  # nosec B102  # pylint: disable=exec-used
    loaded = {name: value for name, value in namespace.items() if name.isupper()}
    keyphrases = loaded.get("KEYPHRASES")
    if not isinstance(keyphrases, dict) or not all(
        isinstance(phrase, str) and callable(action)
        for phrase, action in keyphrases.items()
    ):
        message = "KEYPHRASES in config.py must map strings to callables"
        raise ValueError(message)
    return loaded


def load() -> None:
    """Load config.py into this module; fail loudly if it is missing or broken."""
    globals().update(_read_config())


def reload() -> bool:
    """Reload config.py; on failure log the error, keep old values, return False."""
    try:
        loaded = _read_config()
    except Exception:  # pylint: disable=broad-exception-caught
        # The user edits config.py while the listener runs; a typo must not
        # kill the listener.
        logger.exception("cannot reload %s; keeping the old settings", CONFIG_PATH)
        return False
    globals().update(loaded)
    logger.info("reloaded %s", CONFIG_PATH)
    return True


load()
