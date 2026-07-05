"""
backend/hotkey.py

Clipboard manager and F9 hotkey paste listener.

Features:
  - copy_to_clipboard(text)  : copies answer to clipboard, plays a beep,
                               and unlocks F9 so it's ready to paste
  - lock()                   : disables F9 while a question is processing
                               (prevents pasting a stale previous answer)
  - unlock(text)             : re-enables F9 and beeps to signal ready
  - start_hotkey_listener()  : registers the F9 global hotkey at startup

Paste safety:
  keyboard.write() types character by character with a small inter-key delay.
  After writing, a short post-paste sleep prevents Enter from firing before
  the last character has been received by the target window.

Beep codes (Windows winsound):
  Processing started : low short beep  (500Hz, 100ms) — "working on it"
  Answer ready       : double high beep (1000Hz, 120ms x2) — "ready to paste"
"""

import logging
import threading
import time
import winsound

import keyboard
import pyperclip

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_latest_answer: str = ""
_ready: bool = False          # True only when a fresh answer is waiting
_lock = threading.Lock()

# Paste timing constants
_CHAR_DELAY   = 0.012   # seconds between each typed character (12ms)
_POST_PASTE   = 0.15    # seconds to wait after typing before releasing (150ms)


# ---------------------------------------------------------------------------
# Beep helpers (winsound is Windows-only, built-in — no extra dependency)
# ---------------------------------------------------------------------------

def _beep_ready() -> None:
    """Single loud beep — answer is ready to paste."""
    try:
        winsound.Beep(1000, 400)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public lock / unlock API (called by main.py pipeline)
# ---------------------------------------------------------------------------

def lock() -> None:
    """
    Disable F9 while a question is being processed.
    Call this the moment a quizmaster message is received.
    """
    global _ready
    with _lock:
        _ready = False
    log.debug("🔒 F9 locked — processing question")


def unlock(answer: str) -> None:
    """
    Store the new answer, copy it to clipboard, enable F9, and beep.
    Call this the moment the final answer is ready.
    """
    global _latest_answer, _ready
    with _lock:
        _latest_answer = answer
        _ready = True

    try:
        pyperclip.copy(answer)
    except Exception as exc:
        log.warning("Clipboard copy failed: %s", exc)

    log.info("📋 Copied to clipboard: %r", answer[:80])
    threading.Thread(target=_beep_ready, daemon=True).start()


def copy_to_clipboard(text: str) -> None:
    """Alias for unlock() — convenience wrapper used by main.py."""
    unlock(text)


# ---------------------------------------------------------------------------
# F9 paste handler
# ---------------------------------------------------------------------------

def _paste_answer() -> None:
    """
    Triggered by F9. Types the last answer into the focused window.
    Silently ignored if F9 is locked (processing in progress).
    """
    with _lock:
        ready = _ready
        answer = _latest_answer

    if not ready:
        if answer:
            log.info("F9 blocked — still processing, please wait.")
        else:
            log.info("F9 pressed but no answer yet.")
        return

    if not answer:
        log.info("F9 pressed but clipboard is empty.")
        return

    log.info("⌨️  F9 paste: %r", answer[:80])
    try:
        # Type character by character with inter-key delay for reliability
        keyboard.write(answer, delay=_CHAR_DELAY)
        # Safety pause — lets the target window finish receiving all chars
        # before the user can press Enter
        time.sleep(_POST_PASTE)
    except Exception as exc:
        log.warning("keyboard.write failed: %s — falling back to Ctrl+V", exc)
        keyboard.send("ctrl+v")
        time.sleep(_POST_PASTE)


# ---------------------------------------------------------------------------
# Hotkey registration
# ---------------------------------------------------------------------------

def start_hotkey_listener() -> None:
    """
    Register F9 as a global hotkey. Safe to call multiple times.
    The hotkey is active immediately but F9 pastes nothing until
    unlock() is called with a fresh answer.
    """
    try:
        keyboard.remove_hotkey("f9")
    except (KeyError, ValueError):
        pass

    keyboard.add_hotkey("f9", _paste_answer, suppress=False)
    log.info("⌨️  F9 hotkey registered — press F9 in any window to paste the answer.")
