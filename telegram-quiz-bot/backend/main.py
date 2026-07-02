"""
backend/main.py

FastAPI application — HTTP routes, WebSocket, and combined asyncio startup.

Routes:
  GET  /          -> serves frontend/index.html
  POST /toggle    -> flip state.listening, returns {listening: bool}
  GET  /status    -> returns {listening: bool, history: [...]}
  WS   /ws        -> on connect: send full history; then push new answers live

Startup:
  Telethon client and Uvicorn share a single asyncio event loop via
  asyncio.gather() so there is exactly one loop managing all I/O.

Run:
  python -m backend.main
  -- or --
  uvicorn backend.main:app   (web server only, no Telegram listener)
"""

import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="ScoutWire — Football Quiz Bot")

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=FileResponse)
async def serve_frontend() -> FileResponse:
    """Serve the single-page frontend UI."""
    return FileResponse(_FRONTEND, media_type="text/html")


@app.post("/toggle")
async def toggle_listening() -> JSONResponse:
    """
    Flip the listening state on/off.
    Returns: {"listening": bool}
    """
    from backend.state import bot_state

    new_state = bot_state.toggle()
    log.info("Listening toggled -> %s", new_state)
    return JSONResponse({"listening": new_state})


@app.get("/status")
async def get_status() -> JSONResponse:
    """
    Return current bot state and full history.
    Returns: {"listening": bool, "history": [...]}
    """
    from backend.state import bot_state

    history = [asdict(e) for e in bot_state.get_history()]
    return JSONResponse({"listening": bot_state.listening, "history": history})


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """
    On connect:  accept, send current history (one message per entry).
    While open:  push new {number, question, answer, timestamp} entries as
                 they arrive from the Telegram pipeline.
    On close:    deregister cleanly.
    """
    from backend.broadcaster import broadcaster
    from backend.state import bot_state

    await broadcaster.connect(ws)
    try:
        # Send existing history so the client is up to date immediately.
        await broadcaster.send_history(ws, bot_state.get_history())

        # Keep the connection alive. The server pushes; client only needs to
        # stay connected (we still receive to detect clean closes).
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        broadcaster.disconnect(ws)


# ---------------------------------------------------------------------------
# Combined startup: Telethon + Uvicorn in one asyncio loop
# ---------------------------------------------------------------------------

async def _start_telegram() -> None:
    """Start the Telethon listener as a long-running async task."""
    from backend.config import settings
    from backend.telegram_client import build_client, _get_sender_name
    from backend.detector import is_from_quizmaster
    from backend.state import bot_state
    from backend.telegram_client import _answer_question
    from telethon import events

    client = build_client()
    await client.start(phone=settings.TELEGRAM_PHONE)
    log.info("Telegram: logged in. Monitoring chat %s", settings.TARGET_CHAT)

    @client.on(events.NewMessage(chats=settings.TARGET_CHAT))
    async def _on_message(event: events.NewMessage.Event) -> None:
        sender = await event.get_sender()
        sender_id: int = sender.id if sender else 0
        sender_name: str = _get_sender_name(sender)
        chat_id: int = event.chat_id
        text: str = event.message.text or ""

        if not bot_state.listening:
            log.debug("IGNORED [listening=off] [%d] %s", sender_id, sender_name)
            return

        if not is_from_quizmaster(sender_id, chat_id):
            log.info("SKIPPED [not quizmaster] [%d] %s: %r", sender_id, sender_name, text[:60])
            return

        asyncio.create_task(
            _answer_question(sender_id, sender_name, chat_id, text),
            name=f"answer-{event.message.id}",
        )

    await client.run_until_disconnected()


async def _main() -> None:
    """Run Telethon and Uvicorn concurrently in the same event loop."""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        loop="none",   # don't let uvicorn create its own loop
    )
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        _start_telegram(),
    )


# ---------------------------------------------------------------------------
# Entry point: python -m backend.main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
        sys.exit(0)
