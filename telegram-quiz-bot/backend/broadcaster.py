"""
backend/broadcaster.py

WebSocket connection manager and broadcaster.

Tracks all active /ws connections and pushes JSON messages to every client
the moment a new answer is produced.  Designed for single-user local use —
no auth, no rooms, just a plain set of live connections.

Usage:
    from backend.broadcaster import broadcaster

    # In the WebSocket route handler:
    await broadcaster.connect(websocket)
    try:
        await websocket.receive_text()   # keep-alive / block until close
    finally:
        broadcaster.disconnect(websocket)

    # From the answer pipeline (telegram_client._answer_question):
    await broadcaster.push(entry)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    from backend.state import HistoryEntry

log = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe (asyncio-safe) WebSocket connection registry."""

    def __init__(self) -> None:
        self._active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await ws.accept()
        self._active.add(ws)
        log.info("WS connect — %d active connection(s)", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection (called after close or error)."""
        self._active.discard(ws)
        log.info("WS disconnect — %d active connection(s)", len(self._active))

    async def push(self, entry: "HistoryEntry") -> None:
        """
        Broadcast a new history entry to all connected clients as JSON.
        Silently drops any connection that errors on send (client already gone).
        """
        if not self._active:
            return

        payload = json.dumps(asdict(entry))
        dead: set[WebSocket] = set()

        for ws in list(self._active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(ws)

    async def send_history(self, ws: WebSocket, history: list["HistoryEntry"]) -> None:
        """
        Send the full current history to a single newly-connected client.
        Each entry is sent as a separate JSON message (same format as push()).
        """
        for entry in history:
            try:
                await ws.send_text(json.dumps(asdict(entry)))
            except Exception:
                self.disconnect(ws)
                return

    @property
    def connection_count(self) -> int:
        return len(self._active)


# Module-level singleton — import this everywhere.
broadcaster = ConnectionManager()
