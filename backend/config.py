"""
backend/config.py

Loads and validates all required environment variables from a .env file.
Import `settings` from this module anywhere in the backend.

Usage:
    from backend.config import settings
    print(settings.GROQ_MODEL)
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Return the env var value, or raise a descriptive error if it's missing."""
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {name}\n"
            f"  -> Add it to your .env file. See .env.example for details."
        )
    return value


def _require_int(name: str) -> int:
    """Return the env var as an int, or raise a descriptive error."""
    raw = _require(name)
    try:
        return int(raw)
    except ValueError:
        raise EnvironmentError(
            f"Environment variable {name} must be an integer, got: {raw!r}"
        )


@dataclass(frozen=True)
class Settings:
    # --- Telegram credentials (from https://my.telegram.org) ---
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_PHONE: str  # E.164 format, e.g. +447700900000

    # --- Groq credentials (from https://console.groq.com) ---
    GROQ_API_KEY: str
    GROQ_MODEL: str  # defaults to llama-3.1-8b-instant

    # --- Bot targeting ---
    TARGET_CHAT: int       # numeric Telegram chat/channel ID
    QUIZMASTER_USER_ID: int  # numeric Telegram user ID — permanent, unlike @username


def _load_settings() -> Settings:
    """Read all env vars and return a validated Settings instance."""
    return Settings(
        TELEGRAM_API_ID=_require_int("TELEGRAM_API_ID"),
        TELEGRAM_API_HASH=_require("TELEGRAM_API_HASH"),
        TELEGRAM_PHONE=_require("TELEGRAM_PHONE"),
        GROQ_API_KEY=_require("GROQ_API_KEY"),
        GROQ_MODEL=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        TARGET_CHAT=_require_int("TARGET_CHAT"),
        QUIZMASTER_USER_ID=_require_int("QUIZMASTER_USER_ID"),
    )


# Module-level singleton — imported by the rest of the backend.
# Loading happens once at import time; a missing var fails immediately
# rather than silently at runtime.
settings = _load_settings()
