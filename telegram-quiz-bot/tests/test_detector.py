"""
tests/test_detector.py

Unit tests for backend/detector.py.

No network calls, no Telethon, no Groq — pure function tests.
Run with: pytest tests/test_detector.py -v
"""

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Inject dummy env vars before importing anything from the backend so that
# config.py's module-level _load_settings() call succeeds without a real .env.
# ---------------------------------------------------------------------------
os.environ.setdefault("TELEGRAM_API_ID", "11111111")
os.environ.setdefault("TELEGRAM_API_HASH", "testhash")
os.environ.setdefault("TELEGRAM_PHONE", "+440000000000")
os.environ.setdefault("GROQ_API_KEY", "gsk_testkey")
os.environ.setdefault("TARGET_CHAT", "-100987654321")
os.environ.setdefault("QUIZMASTER_USER_ID", "111222333")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.detector import is_from_quizmaster, parse_question

# ---------------------------------------------------------------------------
# Values that match the dummy env vars above.
# ---------------------------------------------------------------------------
QUIZMASTER_ID = 111222333
TARGET_CHAT   = -100987654321

# A different user in the same chat (the moderator, or any other participant).
MODERATOR_ID  = 444555666
OTHER_CHAT    = -100111111111


# ===========================================================================
# is_from_quizmaster tests
# ===========================================================================

class TestIsFromQuizmaster:

    def test_correct_sender_and_chat_returns_true(self):
        assert is_from_quizmaster(QUIZMASTER_ID, TARGET_CHAT) is True

    def test_wrong_sender_same_chat_returns_false(self):
        """A moderator or any other participant in the quiz chat is ignored."""
        assert is_from_quizmaster(MODERATOR_ID, TARGET_CHAT) is False

    def test_correct_sender_wrong_chat_returns_false(self):
        """Quizmaster posting in a different chat is not treated as a question."""
        assert is_from_quizmaster(QUIZMASTER_ID, OTHER_CHAT) is False

    def test_wrong_sender_wrong_chat_returns_false(self):
        assert is_from_quizmaster(MODERATOR_ID, OTHER_CHAT) is False

    def test_zero_sender_id_returns_false(self):
        """Edge case: unresolved sender falls back to 0 in telegram_client."""
        assert is_from_quizmaster(0, TARGET_CHAT) is False

    def test_return_type_is_bool(self):
        """Must return a strict bool, not a truthy int."""
        result = is_from_quizmaster(QUIZMASTER_ID, TARGET_CHAT)
        assert type(result) is bool


# ===========================================================================
# parse_question tests
# ===========================================================================

class TestParseQuestion:

    # --- Numbered formats ---

    def test_period_separator(self):
        num, text = parse_question("15. Which club won their only La Liga title in the 1999-2000 season?")
        assert num == 15
        assert text == "Which club won their only La Liga title in the 1999-2000 season?"

    def test_parenthesis_separator(self):
        num, text = parse_question("3) Who scored the winner in the 1966 World Cup final?")
        assert num == 3
        assert text == "Who scored the winner in the 1966 World Cup final?"

    def test_colon_separator(self):
        num, text = parse_question("7: What year was UEFA founded?")
        assert num == 7
        assert text == "What year was UEFA founded?"

    def test_dash_separator(self):
        num, text = parse_question("7 - What year was UEFA founded?")
        assert num == 7
        assert text == "What year was UEFA founded?"

    def test_large_question_number(self):
        num, text = parse_question("42. Name the only African country to reach a World Cup semi-final.")
        assert num == 42
        assert text == "Name the only African country to reach a World Cup semi-final."

    def test_leading_whitespace_stripped(self):
        num, text = parse_question("  10. Which country hosted the 2010 World Cup?")
        assert num == 10
        assert text == "Which country hosted the 2010 World Cup?"

    def test_question_body_whitespace_stripped(self):
        num, text = parse_question("5.   Who won the Ballon d'Or in 2023?  ")
        assert num == 5
        assert text == "Who won the Ballon d'Or in 2023?"

    # --- Non-numbered formats ---

    def test_plain_text_no_number(self):
        num, text = parse_question("Who won the Champions League in 2012?")
        assert num is None
        assert text == "Who won the Champions League in 2012?"

    def test_banter_message_no_number(self):
        """Non-question quizmaster message — number is None, text preserved."""
        num, text = parse_question("brb 5 mins")
        assert num is None
        assert text == "brb 5 mins"

    def test_empty_string(self):
        num, text = parse_question("")
        assert num is None
        assert text == ""

    def test_whitespace_only(self):
        num, text = parse_question("   ")
        assert num is None
        assert text == ""

    # --- Return type checks ---

    def test_numbered_returns_int_not_string(self):
        num, _ = parse_question("1. Test question?")
        assert isinstance(num, int)

    def test_unnumbered_returns_none_not_zero(self):
        num, _ = parse_question("No number here")
        assert num is None

    def test_returns_tuple_of_two(self):
        result = parse_question("8. Anything?")
        assert isinstance(result, tuple)
        assert len(result) == 2

    # --- No-import guard ---

    def test_no_telethon_imported(self):
        """detector.py must not import telethon — stays dependency-free."""
        import backend.detector as det_module
        import inspect
        source = inspect.getsource(det_module)
        assert "import telethon" not in source
        assert "from telethon" not in source

    def test_no_httpx_imported(self):
        """detector.py must not import httpx — stays dependency-free."""
        import backend.detector as det_module
        import inspect
        source = inspect.getsource(det_module)
        assert "import httpx" not in source
        assert "from httpx" not in source
