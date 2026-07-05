"""
backend/config.py

Loads and validates all required environment variables from a .env file.
Import `settings` from this module anywhere in the backend.

Usage:
    from backend.config import settings
    print(settings.GEMINI_API_KEY)
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {name}\n"
            f"  -> Add it to your .env file. See .env.example for details."
        )
    return value


def _require_int(name: str) -> int:
    raw = _require(name)
    try:
        return int(raw)
    except ValueError:
        raise EnvironmentError(
            f"Environment variable {name} must be an integer, got: {raw!r}"
        )


@dataclass(frozen=True)
class Settings:
    # --- Telegram ---
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_PHONE: str

    # --- Gemini (primary LLM) ---
    GEMINI_API_KEY: str
    GEMINI_MODEL: str

    # --- Groq (fallback LLM) ---
    GROQ_API_KEY: str
    GROQ_FALLBACK_MODEL: str

    # --- Serper (fallback search) ---
    SERPER_API_KEY: str

    # --- Bot targeting ---
    TARGET_CHAT: int
    QUIZMASTER_USER_ID: int


def _load_settings() -> Settings:
    return Settings(
        TELEGRAM_API_ID=_require_int("TELEGRAM_API_ID"),
        TELEGRAM_API_HASH=_require("TELEGRAM_API_HASH"),
        TELEGRAM_PHONE=_require("TELEGRAM_PHONE"),
        GEMINI_API_KEY=_require("GEMINI_API_KEY"),
        GEMINI_MODEL=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        GROQ_API_KEY=_require("GROQ_API_KEY"),
        GROQ_FALLBACK_MODEL=os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile"),
        SERPER_API_KEY=_require("SERPER_API_KEY"),
        TARGET_CHAT=_require_int("TARGET_CHAT"),
        QUIZMASTER_USER_ID=_require_int("QUIZMASTER_USER_ID"),
    )


settings = _load_settings()
