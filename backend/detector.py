"""
backend/detector.py

Quizmaster message filter and question parser.

Intentionally dependency-free — no telethon, no httpx, no network calls.
This module must stay fast and unit-testable in isolation.

Design note (from PLAN.md):
  Detection is sender-based, not content-based. Any message from the
  configured quizmaster in the configured chat is treated as a question.
  This is simpler, cheaper, and cannot misfire on ordinary football chat.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Compiled once at import time — zero cost per call.
# Matches an optional leading number+period/dot at the start of a message,
# e.g. "15. Which club..." or "3) Who scored..." or "7 - What year..."
# ---------------------------------------------------------------------------
_LEADING_NUMBER_RE = re.compile(
    r"^\s*(\d+)\s*[.):\-]\s*(.+)$",
    re.DOTALL,
)


def is_from_quizmaster(sender_id: int, chat_id: int) -> bool:
    """
    Return True only if the message comes from the quizmaster in the target chat.

    Both conditions must hold:
      - sender_id matches QUIZMASTER_USER_ID from config
      - chat_id   matches TARGET_CHAT from config

    This is the primary (and only required) detection gate.
    It cannot misfire: it is a direct integer equality check, not a heuristic.
    """
    from backend.config import settings  # deferred — keeps module importable in tests

    return sender_id == settings.QUIZMASTER_USER_ID and chat_id == settings.TARGET_CHAT


def parse_question(text: str) -> tuple[Optional[int], str]:
    """
    Strip a leading question number from quiz message text for cleaner display.

    Examples:
        "15. Which club won the 1999-2000 La Liga?" -> (15, "Which club won the 1999-2000 La Liga?")
        "3) Who scored the winner?"                 -> (3,  "Who scored the winner?")
        "7 - What year was UEFA founded?"           -> (7,  "What year was UEFA founded?")
        "Just chatting"                             -> (None, "Just chatting")

    Returns:
        (question_number, cleaned_text)
        question_number is None if no leading number was found.
    """
    text = text.strip()
    match = _LEADING_NUMBER_RE.match(text)
    if match:
        number = int(match.group(1))
        body = match.group(2).strip()
        return number, body
    return None, text
