"""
scripts/list_chats.py

Prints all Telegram dialogs (chats, groups, channels) the account can see,
with their numeric ID and display name.

Use this to find the value for TARGET_CHAT in your .env.

Usage:
    python scripts/list_chats.py

Note: group/channel IDs are shown as negative integers (e.g. -1001234567890).
Use that full negative value as TARGET_CHAT.
"""

import asyncio
import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.telegram_client import build_client
from backend.config import settings


async def main() -> None:
    client = build_client()
    await client.start(phone=settings.TELEGRAM_PHONE)

    print(f"\n{'ID':>20}  Name")
    print("-" * 60)

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        # Peer ID — groups/channels are negative, users are positive.
        peer_id: int = dialog.id
        name: str = dialog.name or "(no name)"
        print(f"{peer_id:>20}  {name}")

    await client.disconnect()
    print("\nDone. Copy the ID of your quiz chat and set it as TARGET_CHAT in .env")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
