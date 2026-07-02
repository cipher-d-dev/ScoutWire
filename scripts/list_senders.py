"""
scripts/list_senders.py

Listens on a specified chat for a short window and prints the numeric user ID
and display name of every sender whose message is seen.

Use this to find QUIZMASTER_USER_ID. Ask the quizmaster to send any message
during the window (or wait for them to post naturally), then copy their
numeric ID into .env.

Why numeric ID and not @username?
  Usernames can be changed by the account holder at any time. Numeric IDs
  are permanent and cannot be reassigned — using them prevents the filter
  from silently breaking if the quizmaster ever renames their account.

Usage:
    python scripts/list_senders.py [CHAT_ID] [SECONDS]

Arguments (both optional, fall back to .env / defaults):
    CHAT_ID   Numeric chat ID to monitor (defaults to TARGET_CHAT from .env)
    SECONDS   How long to listen (default: 60)

Example:
    python scripts/list_senders.py -1001234567890 120
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.telegram_client import build_client, _get_sender_name
from backend.config import settings
from telethon import events


async def main(chat_id: int, duration: int) -> None:
    client = build_client()
    await client.start(phone=settings.TELEGRAM_PHONE)

    seen: dict[int, str] = {}  # sender_id -> display name

    print(f"\nListening on chat {chat_id} for {duration}s …")
    print("Ask the quizmaster to send a message now.\n")
    print(f"{'Numeric ID':>15}  Display name")
    print("-" * 50)

    @client.on(events.NewMessage(chats=chat_id))
    async def _on_message(event: events.NewMessage.Event) -> None:
        sender = await event.get_sender()
        if sender is None:
            return
        sid: int = sender.id
        name: str = _get_sender_name(sender)
        if sid not in seen:
            seen[sid] = name
            print(f"{sid:>15}  {name}")

    await asyncio.sleep(duration)
    await client.disconnect()

    print("\n--- Summary ---")
    for sid, name in seen.items():
        print(f"{sid:>15}  {name}")
    print(
        "\nCopy the quizmaster's numeric ID and set it as "
        "QUIZMASTER_USER_ID in .env"
    )


if __name__ == "__main__":
    _chat_id = int(sys.argv[1]) if len(sys.argv) > 1 else settings.TARGET_CHAT
    _duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    try:
        asyncio.run(main(_chat_id, _duration))
    except KeyboardInterrupt:
        sys.exit(0)
