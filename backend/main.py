"""
backend/main.py

ScoutWire — headless terminal runner.

Pipeline per question:
    📨 Quizmaster message received
        → F9 locked + low beep (processing started)
        → Pipeline A (Gemini fast) + Pipeline B (Serper→Gemini) run in parallel
        → Pipeline A result logged immediately when ready
        → Cross-check completes, final answer chosen
        → Answer normalised, copied to clipboard
        → F9 unlocked + double beep (ready to paste)

Run:
    python -m backend.main

Stop:
    Ctrl+C
"""

import asyncio
import logging
import sys

from telethon import events

from backend.config import settings
from backend.detector import is_from_quizmaster, parse_question
from backend.hotkey import copy_to_clipboard, lock, start_hotkey_listener, unlock
from backend.normalizer import normalize_answer
from backend.orchestrator import get_answer
from backend.telegram_client import build_client, _get_sender_name

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Per-question pipeline
# ---------------------------------------------------------------------------

async def _handle_question(
    sender_id: int,
    sender_name: str,
    text: str,
) -> None:
    """
    Full pipeline for one quizmaster message.
    Runs as a background asyncio task.
    """
    number, question = parse_question(text)
    q_label = f"Q{number}" if number is not None else "Q?"

    # Step 1 — received, lock F9 immediately
    log.info("📨 [1/3] Quizmaster message received | %s from %s (ID %d)", q_label, sender_name, sender_id)
    log.info("         Question: %s", question)
    lock()   # disables F9 + plays low beep

    # Step 2 — run both pipelines in parallel
    log.info("🤖 [2/3] Sending to answer engine …")

    async def _on_fast_result(fast_answer: str) -> None:
        """Called as soon as Pipeline A (Gemini alone) returns."""
        log.info("   ⚡ [A] Fast answer: %r — waiting for cross-check …", fast_answer[:60])

    raw_answer = await get_answer(question, on_fast_result=_on_fast_result)

    # Step 3 — normalise, copy, unlock F9
    answer = normalize_answer(raw_answer)
    log.info("✅ [3/3] Final answer | %s → %s", q_label, answer)

    unlock(answer)   # copies to clipboard + plays double beep + re-enables F9
    log.info("         Press F9 in Telegram to paste, or Ctrl+V (already in clipboard).\n")


# ---------------------------------------------------------------------------
# Telegram listener
# ---------------------------------------------------------------------------

async def _run() -> None:
    start_hotkey_listener()

    client = build_client()
    await client.start(phone=settings.TELEGRAM_PHONE)

    log.info("=" * 60)
    log.info("ScoutWire started — monitoring chat %s", settings.TARGET_CHAT)
    log.info("Quizmaster ID: %s", settings.QUIZMASTER_USER_ID)
    log.info("Primary LLM:   %s", settings.GEMINI_MODEL)
    log.info("Fallback:      Serper + %s", settings.GROQ_FALLBACK_MODEL)
    log.info("Hotkey:        F9 — paste last answer into focused window")
    log.info("Alert:         3-tone beep = answer ready, press F9 to paste")
    log.info("Stop:          Ctrl+C")
    log.info("=" * 60 + "\n")

    @client.on(events.NewMessage(chats=settings.TARGET_CHAT))
    async def _on_message(event: events.NewMessage.Event) -> None:
        sender = await event.get_sender()
        sender_id: int = sender.id if sender else 0
        sender_name: str = _get_sender_name(sender)
        chat_id: int = event.chat_id
        text: str = (event.message.text or "").strip()

        if not text:
            return

        if not is_from_quizmaster(sender_id, chat_id):
            log.debug("SKIPPED [not quizmaster] [%d] %s: %r", sender_id, sender_name, text[:60])
            return

        asyncio.create_task(
            _handle_question(sender_id, sender_name, text),
            name=f"answer-{event.message.id}",
        )

    await client.run_until_disconnected()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        log.info("ScoutWire stopped.")
        sys.exit(0)
