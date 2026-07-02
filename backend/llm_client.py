"""
backend/llm_client.py

Groq LLM answer engine.

async get_answer(question: str) -> str

Calls Groq's OpenAI-compatible chat completions endpoint with streaming
enabled so the first tokens arrive in ~150ms rather than waiting for the
full response. The caller receives the complete assembled string; streaming
is an internal transport detail that keeps latency low.

Speed contract (from PLAN.md):
  - Streaming: yes — stream=true, tokens assembled as they arrive.
  - Token cap: 80 tokens max — enough for 1-2 sentences, keeps response fast.
  - No caching — quiz questions are unique each round, hit rate ≈ 0.
  - httpx timeout: 8s total (Groq is typically <1s; this is a hard ceiling).

Error handling:
  - Timeout              → "Sorry, the answer timed out — try again."
  - 429 rate-limit       → "Rate limited — retry in {n}s" (reads Retry-After header)
  - Non-200 (other)      → "Error {status}: could not get an answer."
  - Unexpected exception → "Unexpected error: {type}."
  All errors return a string; nothing is ever raised into the caller.
"""

import json
import time
import logging
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT   = httpx.Timeout(8.0)   # hard ceiling; Groq typically replies in <1s
_MAX_TOKENS = 80                   # ~1-2 sentences; keeps latency low

_SYSTEM_PROMPT = """\
You are a football (soccer) trivia assistant. Rules:
- Answer ONLY football-related trivia questions.
- Be concise: one to two sentences maximum. State the fact and brief context, nothing else.
- No preamble. Do not start with "Sure", "Great question", or any filler.
- If the question asks for a specific stat, record, or obscure detail you are not
  confident about, say so explicitly (e.g. "I'm not certain of the exact figure")
  rather than guessing. Accuracy matters more than sounding confident.
- If the question is not about football, reply: "This doesn't appear to be a football question."\
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _stream_completion(client: httpx.AsyncClient, question: str, model: str) -> str:
    """
    POST to Groq with stream=true and assemble tokens as they arrive.
    Returns the full answer string.
    Raises httpx exceptions — caller handles them.
    """
    payload = {
        "model": model,
        "stream": True,
        "max_tokens": _MAX_TOKENS,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": question},
        ],
    }

    from backend.config import settings
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    chunks: list[str] = []

    async with client.stream("POST", _GROQ_URL, json=payload, headers=headers) as response:
        if response.status_code == 429:
            # Read body so we can extract retry-after from headers before raising.
            await response.aread()
            retry_after = response.headers.get("retry-after") or response.headers.get("x-ratelimit-reset-requests")
            raise _RateLimitError(retry_after)

        if response.status_code != 200:
            await response.aread()
            raise _HttpError(response.status_code)

        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data.strip() == "[DONE]":
                break
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"].get("content", "")
                if delta:
                    chunks.append(delta)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue  # malformed chunk — skip silently

    return "".join(chunks).strip()


# ---------------------------------------------------------------------------
# Custom internal exception types (not exposed to callers)
# ---------------------------------------------------------------------------

class _RateLimitError(Exception):
    def __init__(self, retry_after: str | None):
        self.retry_after = retry_after


class _HttpError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_answer(question: str) -> str:
    """
    Given a football trivia question, return a short answer string.

    Always returns a string — never raises. Errors produce a human-readable
    fallback that the frontend can display directly.

    Typical latency: 300-600ms end-to-end (Groq first token ~150ms + assembly).
    """
    from backend.config import settings

    t0 = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            answer = await _stream_completion(client, question, settings.GROQ_MODEL)

        elapsed = (time.perf_counter() - t0) * 1000
        log.info("Groq answered in %.0fms: %r", elapsed, answer[:80])
        return answer

    except _RateLimitError as e:
        if e.retry_after:
            log.warning("Groq rate-limited. Retry-After: %s", e.retry_after)
            return f"Rate limited \u2014 retry in {e.retry_after}s"
        log.warning("Groq rate-limited (no Retry-After header).")
        return "Rate limited \u2014 please retry in a moment"

    except _HttpError as e:
        log.error("Groq returned HTTP %d", e.status_code)
        return f"Error {e.status_code}: could not get an answer."

    except httpx.TimeoutException:
        elapsed = (time.perf_counter() - t0) * 1000
        log.error("Groq timed out after %.0fms", elapsed)
        return "Sorry, the answer timed out \u2014 try again."

    except Exception as e:  # noqa: BLE001
        log.exception("Unexpected error in get_answer")
        return f"Unexpected error: {type(e).__name__}."
