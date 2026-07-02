"""
backend/state.py

In-memory bot state — single source of truth for the running process.

Contents:
  - listening: bool  — gates whether incoming Telegram messages get processed
  - history: list    — recent Q&A entries, capped at HISTORY_CAP (oldest dropped)

No persistence: resets on restart, by design (PLAN.md Phase 4).

Usage:
    from backend.state import bot_state

    bot_state.listening          # -> bool
    bot_state.toggle()           # -> new bool
    bot_state.add_entry(...)     # append to history, drops oldest if over cap
    bot_state.get_history()      # -> list[HistoryEntry] (newest last)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

HISTORY_CAP = 20  # max Q&A pairs kept in memory


@dataclass
class HistoryEntry:
    """One answered quiz question."""
    number: Optional[int]   # parsed question number (None if unnumbered)
    question: str           # cleaned question text (leading number stripped)
    answer: str             # LLM answer (may be an error/fallback string)
    timestamp: str          # ISO-8601 UTC string, e.g. "2026-07-02T21:00:00Z"


class BotState:
    """
    Thread-safe singleton holding all mutable runtime state.

    Thread safety: a single asyncio event loop runs the Telethon + FastAPI
    code, so contention is minimal. The lock guards against the rare case
    where FastAPI's /toggle endpoint and a Telethon handler fire concurrently
    across threads (e.g. during testing or with a thread-pool executor).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listening: bool = False
        self._history: list[HistoryEntry] = []

    # ------------------------------------------------------------------
    # Listening toggle
    # ------------------------------------------------------------------

    @property
    def listening(self) -> bool:
        with self._lock:
            return self._listening

    @listening.setter
    def listening(self, value: bool) -> None:
        with self._lock:
            self._listening = value

    def toggle(self) -> bool:
        """Flip the listening flag and return the new value."""
        with self._lock:
            self._listening = not self._listening
            return self._listening

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def add_entry(
        self,
        *,
        number: Optional[int],
        question: str,
        answer: str,
        timestamp: Optional[str] = None,
    ) -> HistoryEntry:
        """
        Append a new Q&A entry. If history is at HISTORY_CAP, the oldest
        entry is dropped first (FIFO). Returns the new entry.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        entry = HistoryEntry(
            number=number,
            question=question,
            answer=answer,
            timestamp=timestamp,
        )

        with self._lock:
            if len(self._history) >= HISTORY_CAP:
                self._history.pop(0)  # drop oldest
            self._history.append(entry)

        return entry

    def get_history(self) -> list[HistoryEntry]:
        """Return a shallow copy of the history list (newest last)."""
        with self._lock:
            return list(self._history)

    def clear_history(self) -> None:
        """Wipe history — used in tests and potential future admin endpoint."""
        with self._lock:
            self._history.clear()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all state to defaults — used in tests."""
        with self._lock:
            self._listening = False
            self._history.clear()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"BotState(listening={self._listening}, "
            f"history_len={len(self._history)})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere.
# ---------------------------------------------------------------------------
bot_state = BotState()
