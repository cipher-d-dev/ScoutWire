"""
backend/telegram_client.py

Telethon userbot client — read-only Telegram listener wired to the full
answer pipeline.

Message flow (Phase 5):
    NewMessage event
        -> state.listening check   (gate: off = ignore everything)
        -> is_from_quizmaster()    (gate: wrong sender/chat = skip + log)
        -> parse_question()        (strip leading number)
        -> asyncio.create_task()   (fire LLM call — never blocks event loop)
            -> get_answer()        (Groq streaming, ~300-600ms)
            -> state.add_entry()   (append to in-memory history)
            -> console log         (print result)

Run directly for a live console feed:
    python -m backend.telegram_client

First run: prompts for phone number verification code (and 2FA password if
enabled). Credentials are saved to session/user.session and reused on
subsequent runs — no re-login needed.

This module NEVER sends any message. It is strictly read-only.
"""

import asyncio
import logging
import sys
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Absolute path to session file so it works regardless of cwd.
_SESSION_PATH = str(
    Path(__file__).resolve().parent.parent / "session" / "user"
)


def build_client() -> TelegramClient:
    """
    Construct and return a TelegramClient using credentials from .env.
    Does NOT connect or start — call `await client.start()` separately.
    """
    from backend.config import settings  # deferred — validates .env on first use

    return TelegramClient(
        _SESSION_PATH,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )


def _get_sender_name(sender) -> str:
    """Return a human-readable display name for a sender object."""
    if sender is None:
        return "Unknown"
    if isinstance(sender, User):
        parts = [sender.first_name or "", sender.last_name or ""]
        full = " ".join(p for p in parts if p).strip()
        return full or sender.username or str(sender.id)
    # Chat / channel
    return getattr(sender, "title", None) or str(getattr(sender, "id", "?"))


async def _answer_question(
    sender_id: int,
    sender_name: str,
    chat_id: int,
    text: str,
) -> None:
    """
    Full answer pipeline — runs as an asyncio.create_task so it never
    blocks the Telethon event loop.

    Steps:
      1. parse_question()    — strip leading number
      2. get_answer()        — Groq streaming LLM call (~300-600ms)
      3. state.add_entry()   — store in history
      4. broadcaster.push()  — push to all connected WebSocket clients
      5. console log         — print result
    """
    from backend.broadcaster import broadcaster
    from backend.detector import parse_question
    from backend.llm_client import get_answer
    from backend.state import bot_state

    number, question = parse_question(text)

    log.info(
        "QUIZMASTER [%d] %s | Q%s: %r",
        sender_id,
        sender_name,
        f"{number}" if number is not None else "?",
        question,
    )

    answer = await get_answer(question)

    entry = bot_state.add_entry(number=number, question=question, answer=answer)

    # Push to all connected browser clients immediately.
    await broadcaster.push(entry)

    # Console output — secondary feedback, useful when browser isn't open.
    print(
        f"\n{'='*60}\n"
        f"  Q{entry.number if entry.number is not None else '?'}: {entry.question}\n"
        f"  A: {entry.answer}\n"
        f"  [{entry.timestamp}]\n"
        f"{'='*60}\n"
    )


async def _run_listener() -> None:
    """
    Connect to Telegram, register a NewMessage handler on TARGET_CHAT, and
    run the full pipeline for quizmaster messages until interrupted.
    """
    from backend.config import settings
    from backend.detector import is_from_quizmaster
    from backend.state import bot_state

    client = build_client()

    # `start()` handles interactive login on first run (phone + code + 2FA).
    await client.start(phone=settings.TELEGRAM_PHONE)
    log.info("Logged in. Listening on chat %s", settings.TARGET_CHAT)
    log.info(
        "Pipeline: %s | Press Ctrl+C to stop.\n",
        "ACTIVE" if bot_state.listening else "PAUSED (toggle listening to start)",
    )

    @client.on(events.NewMessage(chats=settings.TARGET_CHAT))
    async def _on_message(event: events.NewMessage.Event) -> None:
        sender = await event.get_sender()
        sender_id: int = sender.id if sender else 0
        sender_name: str = _get_sender_name(sender)
        chat_id: int = event.chat_id
        text: str = event.message.text or ""

        # Gate 1: global listening toggle.
        if not bot_state.listening:
            log.debug(
                "IGNORED [listening=off] [%d] %s: %r",
                sender_id, sender_name, text[:60],
            )
            return

        # Gate 2: quizmaster filter — sender-based, not content-based.
        if not is_from_quizmaster(sender_id, chat_id):
            log.info(
                "SKIPPED [not quizmaster] [%d] %s: %r",
                sender_id, sender_name, text[:60],
            )
            return

        # Fire the pipeline as a background task — event loop stays free.
        asyncio.create_task(
            _answer_question(sender_id, sender_name, chat_id, text),
            name=f"answer-{sender_id}-{event.message.id}",
        )

    await client.run_until_disconnected()


# ---------------------------------------------------------------------------
# Entry point: python -m backend.telegram_client
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(_run_listener())
    except KeyboardInterrupt:
        log.info("Stopped.")
        sys.exit(0)
