"""
backend/llm_client.py

Uses llama-3.3-70b-versatile with a carefully tuned prompt for maximum
accuracy on football trivia. Search integration can be added once a
working search API key is available.

async get_answer(question: str) -> str
"""

import time
import logging
import json

import httpx

log = logging.getLogger(__name__)

_GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT      = httpx.Timeout(12.0)
_MAX_TOKENS   = 60
_MODEL        = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """\
You are a football (soccer) trivia expert with deep knowledge up to mid-2025.

RULES:
- Answer with ONLY the direct answer — a name, number, year, club, or short phrase. No sentences.
- Examples: "Iñaki Williams", "Real Madrid", "1966", "Pelé", "San Siro"
- For questions about specific records (most appearances, fastest hat-trick, top scorer in X):
  think carefully — do NOT substitute a famous player's name just because they are well-known.
  The record holder is often an unexpected player, not the most famous one.
- For events from 2024 or 2025, only answer if you are certain. Otherwise say: Not sure
- If not confident, say: Not sure. A wrong answer is worse than Not sure.\
"""


class _RateLimitError(Exception):
    def __init__(self, retry_after: str | None):
        self.retry_after = retry_after

class _HttpError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


async def get_answer(question: str) -> str:
    from backend.config import settings

    # Strip markdown formatting the quizmaster sometimes adds
    clean_q = question.replace("**", "").replace("*", "").strip()

    t0 = time.perf_counter()
    log.info("   ↳ Querying %s", _MODEL)

    payload = {
        "model": _MODEL,
        "max_tokens": _MAX_TOKENS,
        "temperature": 0,          # deterministic — no creative guessing
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": clean_q},
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(_GROQ_URL, json=payload, headers=headers)

        if response.status_code == 429:
            retry_after = (
                response.headers.get("retry-after")
                or response.headers.get("x-ratelimit-reset-requests")
            )
            raise _RateLimitError(retry_after)

        if response.status_code != 200:
            log.error("Groq HTTP %d — %s", response.status_code, response.text[:200])
            raise _HttpError(response.status_code)

        data = response.json()
        answer = (data["choices"][0]["message"].get("content") or "Not sure").strip()

        elapsed = (time.perf_counter() - t0) * 1000
        log.info("   ↳ Groq responded in %.0fms — answer: %r", elapsed, answer[:80])
        return answer

    except _RateLimitError as e:
        if e.retry_after:
            log.warning("Groq rate-limited. Retry-After: %s", e.retry_after)
            return f"Rate limited \u2014 retry in {e.retry_after}s"
        return "Rate limited \u2014 please retry in a moment"

    except _HttpError as e:
        return f"Error {e.status_code}: could not get an answer."

    except httpx.TimeoutException:
        elapsed = (time.perf_counter() - t0) * 1000
        log.error("Groq timed out after %.0fms", elapsed)
        return "Sorry, the answer timed out \u2014 try again."

    except Exception as e:  # noqa: BLE001
        log.exception("Unexpected error in get_answer")
        return f"Unexpected error: {type(e).__name__}."
