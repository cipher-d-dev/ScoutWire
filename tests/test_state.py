"""
tests/test_state.py

Unit tests for backend/state.py.

Covers: toggle on/off, history cap enforcement, oldest-entry dropping,
entry field correctness, thread safety basics, and reset behaviour.

Run with: pytest tests/test_state.py -v
"""

import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.state import BotState, HistoryEntry, HISTORY_CAP


# ---------------------------------------------------------------------------
# Each test gets a fresh BotState so tests are fully isolated.
# ---------------------------------------------------------------------------

@pytest.fixture
def state() -> BotState:
    s = BotState()
    return s


# ===========================================================================
# Toggle tests
# ===========================================================================

class TestToggle:

    def test_starts_false(self, state):
        assert state.listening is False

    def test_toggle_false_to_true(self, state):
        result = state.toggle()
        assert result is True
        assert state.listening is True

    def test_toggle_true_to_false(self, state):
        state.listening = True
        result = state.toggle()
        assert result is False
        assert state.listening is False

    def test_toggle_twice_returns_to_original(self, state):
        state.toggle()
        state.toggle()
        assert state.listening is False

    def test_toggle_returns_new_value(self, state):
        """toggle() return value must match the post-toggle state."""
        v1 = state.toggle()
        assert v1 == state.listening
        v2 = state.toggle()
        assert v2 == state.listening

    def test_listening_setter(self, state):
        state.listening = True
        assert state.listening is True
        state.listening = False
        assert state.listening is False

    def test_toggle_return_type_is_bool(self, state):
        result = state.toggle()
        assert type(result) is bool


# ===========================================================================
# History tests
# ===========================================================================

class TestHistory:

    def test_starts_empty(self, state):
        assert state.get_history() == []

    def test_add_single_entry(self, state):
        entry = state.add_entry(number=1, question="Who won?", answer="Brazil")
        history = state.get_history()
        assert len(history) == 1
        assert history[0] is entry

    def test_entry_fields_stored_correctly(self, state):
        state.add_entry(
            number=7,
            question="Which club?",
            answer="Real Madrid",
            timestamp="2026-07-02T21:00:00Z",
        )
        e = state.get_history()[0]
        assert e.number == 7
        assert e.question == "Which club?"
        assert e.answer == "Real Madrid"
        assert e.timestamp == "2026-07-02T21:00:00Z"

    def test_unnumbered_entry_has_none_number(self, state):
        state.add_entry(number=None, question="Some question", answer="Some answer")
        assert state.get_history()[0].number is None

    def test_timestamp_auto_generated_if_not_provided(self, state):
        state.add_entry(number=1, question="Q", answer="A")
        ts = state.get_history()[0].timestamp
        assert ts  # non-empty
        assert "T" in ts  # ISO format
        assert ts.endswith("Z")

    def test_history_order_is_oldest_first(self, state):
        for i in range(1, 4):
            state.add_entry(number=i, question=f"Q{i}", answer=f"A{i}")
        nums = [e.number for e in state.get_history()]
        assert nums == [1, 2, 3]

    def test_get_history_returns_copy(self, state):
        """Mutating the returned list must not affect internal state."""
        state.add_entry(number=1, question="Q", answer="A")
        h = state.get_history()
        h.clear()
        assert len(state.get_history()) == 1

    # ------------------------------------------------------------------
    # Cap enforcement
    # ------------------------------------------------------------------

    def test_history_at_cap_length(self, state):
        for i in range(HISTORY_CAP):
            state.add_entry(number=i, question=f"Q{i}", answer=f"A{i}")
        assert len(state.get_history()) == HISTORY_CAP

    def test_adding_beyond_cap_does_not_exceed_cap(self, state):
        for i in range(HISTORY_CAP + 5):
            state.add_entry(number=i, question=f"Q{i}", answer=f"A{i}")
        assert len(state.get_history()) == HISTORY_CAP

    def test_oldest_entry_dropped_when_cap_exceeded(self, state):
        """Entry with number=0 (first added) must be gone after cap+1 inserts."""
        for i in range(HISTORY_CAP + 1):
            state.add_entry(number=i, question=f"Q{i}", answer=f"A{i}")
        numbers = [e.number for e in state.get_history()]
        assert 0 not in numbers                      # oldest dropped
        assert HISTORY_CAP in numbers                # newest present

    def test_only_one_entry_dropped_per_overflow(self, state):
        """Each overflow drops exactly one entry — the oldest."""
        for i in range(HISTORY_CAP + 3):
            state.add_entry(number=i, question=f"Q{i}", answer=f"A{i}")
        numbers = [e.number for e in state.get_history()]
        # First 3 entries (0, 1, 2) should be gone; entry 3 should be present
        assert 0 not in numbers
        assert 1 not in numbers
        assert 2 not in numbers
        assert 3 in numbers

    def test_newest_entry_is_last(self, state):
        for i in range(HISTORY_CAP + 1):
            state.add_entry(number=i, question=f"Q{i}", answer=f"A{i}")
        assert state.get_history()[-1].number == HISTORY_CAP

    # ------------------------------------------------------------------
    # clear / reset
    # ------------------------------------------------------------------

    def test_clear_history(self, state):
        state.add_entry(number=1, question="Q", answer="A")
        state.clear_history()
        assert state.get_history() == []

    def test_reset_clears_history_and_listening(self, state):
        state.listening = True
        state.add_entry(number=1, question="Q", answer="A")
        state.reset()
        assert state.listening is False
        assert state.get_history() == []


# ===========================================================================
# HistoryEntry dataclass
# ===========================================================================

class TestHistoryEntry:

    def test_is_dataclass(self, state):
        entry = state.add_entry(number=5, question="Q?", answer="A.")
        assert isinstance(entry, HistoryEntry)

    def test_entry_fields_exist(self):
        e = HistoryEntry(number=1, question="Q", answer="A", timestamp="ts")
        assert hasattr(e, "number")
        assert hasattr(e, "question")
        assert hasattr(e, "answer")
        assert hasattr(e, "timestamp")


# ===========================================================================
# Thread safety smoke test
# ===========================================================================

class TestThreadSafety:

    def test_concurrent_toggles_do_not_crash(self, state):
        """100 threads all toggling simultaneously — must not raise."""
        errors = []

        def _toggle():
            try:
                for _ in range(10):
                    state.toggle()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_toggle) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_concurrent_add_entry_stays_at_cap(self, state):
        """50 threads each adding 5 entries — history must not exceed cap."""
        def _add(n):
            for i in range(5):
                state.add_entry(number=n * 5 + i, question="Q", answer="A")

        threads = [threading.Thread(target=_add, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(state.get_history()) <= HISTORY_CAP
