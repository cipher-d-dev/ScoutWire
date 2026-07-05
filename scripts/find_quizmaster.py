"""
scripts/find_quizmaster.py

Scans recent message history in a chat and prints every sender's numeric ID
and display name. No waiting — works instantly from past messages.

Use this to find QUIZMASTER_USER_ID when the quizmaster has no @username.
As long as they've posted anything recently, their ID will appear.

Usage:
    python scripts/find_quizmaster.py              (scans last 50 messages in TARGET_CHAT)
    python scripts/find_quizmaster.py -1009999999  (specific chat, last 50 messages)
    python scripts/find_quizmaster.py -1009999999 200  (last 200 messages)

Output:
         Numeric ID  Display name
    --------------------------------------------------------
          111222333  QuizMaster Dave
          444555666  John Smith
          ...

    Copy the quizmaster's numeric ID and set it as QUIZMASTER_USER_ID in .env
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings
from backend.telegram_client import build_client, _get_sender_name


async def main(chat_id: int, limit: int) -> None:
    client = build_client()
    await client.start(phone=settings.TELEGRAM_PHONE)

    print(f"\nScanning last {limit} messages in chat {chat_id} …\n")
    print(f"{'Numeric ID':>15}  Display name")
    print("-" * 55)

    seen: dict[int, str] = {}  # sender_id -> display name, in order first seen

    async for message in client.iter_messages(chat_id, limit=limit):
        sender = await message.get_sender()
        if sender is None:
            continue
        sid: int = sender.id
        if sid in seen:
            continue
        name: str = _get_sender_name(sender)
        seen[sid] = name
        print(f"{sid:>15}  {name}")

    await client.disconnect()

    print("\n" + "-" * 55)
    print(f"Found {len(seen)} unique sender(s) in the last {limit} messages.")
    print("\nCopy the quizmaster's numeric ID and add it to your .env:")
    print("  QUIZMASTER_USER_ID=<their numeric ID>")


if __name__ == "__main__":
    _chat_id = int(sys.argv[1]) if len(sys.argv) > 1 else settings.TARGET_CHAT
    _limit   = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    try:
        asyncio.run(main(_chat_id, _limit))
    except KeyboardInterrupt:
        sys.exit(0)
