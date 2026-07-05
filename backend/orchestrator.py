"""
backend/orchestrator.py

Hybrid answer engine: Gemini 2.5 Flash (primary) with Serper + Groq fallback.

Flow:
    get_answer(question)
        ├── Gemini 2.5 Flash              (~400-700ms, uses training knowledge)
        │     ↓ on error / rate-limit / empty response / timeout
        └── Serper web search → Groq 70b  (~2-4s, grounded in live results)

Groq is used (not Gemini) in the fallback so rate limits on Gemini
do not affect the fallback path. Groq free tier is effectively unlimited
for quiz use (30 req/min, 14,400/day).

Public API:
    async get_answer(question: str, on_fast_result=None) -> str
        on_fast_result: optional async callback(answer) — not used in this
                        architecture but kept for API compatibility with main.py
"""

import asyncio
import logging
import re
import time
from collections import deque

import httpx
from google import genai
from google.genai import types as genai_types

log = logging.getLogger(__name__)

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT    = httpx.Timeout(10.0)

_recent_questions: deque = deque(maxlen=5)

# ---------------------------------------------------------------------------
# Shared answer rules
# ---------------------------------------------------------------------------

_ANSWER_RULES = (
    "Follow these rules strictly:\n"
    "- If the question asks 'how many' or expects a count: reply with the digit only. Example: '4' not 'four' not '4 times'.\n"
    "- If the question asks for a person's name: reply with their full name. Example: 'Thierry Henry' not 'Henry'.\n"
    "- If the question asks for a club, country, or competition: reply with the full official name. Example: 'Manchester United' not 'Man Utd'.\n"
    "- No sentences, no explanation, no punctuation at the end, no markdown.\n"
    "- Reply with ONLY the answer. Nothing else."
)

# ---------------------------------------------------------------------------
# Primary: Gemini 2.5 Flash
# ---------------------------------------------------------------------------

_GEMINI_SYSTEM = (
    "You are a football trivia expert. "
    "Answer quiz questions with ONLY the answer.\n"
    + _ANSWER_RULES
)


async def _gemini_answer(question: str, context_hint: str) -> str:
    """Query Gemini 2.5 Flash. Returns answer string or raises on failure."""
    from backend.config import settings

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = f"{context_hint}\n\nQuestion: {question}" if context_hint else question

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=_GEMINI_SYSTEM,
            temperature=0.0,
            max_output_tokens=150,
        ),
    )
    # Use candidates directly to avoid truncation from response.text shortcut
    text = ""
    if response.candidates:
        for part in response.candidates[0].content.parts:
            text += part.text or ""
    text = text.strip()
    if not text:
        raise ValueError("Gemini returned empty response")
    return text


# ---------------------------------------------------------------------------
# Fallback: Serper search
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "who", "what", "which", "where", "when", "how", "many", "is", "was",
    "are", "were", "the", "a", "an", "in", "of", "for", "to", "and", "or",
    "that", "this", "their", "his", "her", "its", "by", "with", "from",
    "has", "have", "had", "did", "does", "do", "be", "been", "after",
    "before", "during", "at", "on", "ever", "also", "but", "not", "no",
}


def _build_search_query(question: str) -> str:
    q = re.sub(r"[*_`~]", "", question).strip()
    q = re.sub(r"^\d+[.):\-]\s*", "", q)
    tokens = re.findall(r"[\w'-]+", q)
    filtered = [t for t in tokens if t.lower() not in _STOP_WORDS and len(t) > 1]
    return "football " + " ".join(filtered)


async def _serper_search(client: httpx.AsyncClient, query: str) -> str:
    from backend.config import settings

    try:
        response = await client.post(
            _SERPER_URL,
            json={"q": query, "num": 5, "gl": "us", "hl": "en"},
            headers={
                "X-API-KEY": settings.SERPER_API_KEY,
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            log.warning("Serper HTTP %d", response.status_code)
            return ""

        data = response.json()
        lines: list[str] = []

        if data.get("answerBox"):
            box = data["answerBox"]
            direct = box.get("answer") or box.get("snippet") or box.get("title")
            if direct:
                lines.append(f"Direct answer: {direct}")

        if data.get("knowledgeGraph"):
            desc = data["knowledgeGraph"].get("description") or data["knowledgeGraph"].get("title")
            if desc:
                lines.append(f"Knowledge graph: {desc}")

        for r in data.get("organic", [])[:3]:
            snippet = r.get("snippet", "").strip()
            title = r.get("title", "").strip()
            if snippet:
                lines.append(f"- {title}: {snippet}")

        return "\n".join(lines)

    except Exception as exc:
        log.warning("Serper error: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Fallback: Groq 70b interprets Serper results
# ---------------------------------------------------------------------------

_GROQ_SYSTEM = (
    "You are a football trivia assistant. "
    "Given web search results and a question, extract the single correct answer. "
    "Prefer the search results over your own knowledge when they conflict.\n"
    + _ANSWER_RULES
)


async def _groq_answer(
    client: httpx.AsyncClient,
    question: str,
    search_results: str,
    context_hint: str,
) -> str:
    from backend.config import settings

    user_content = (
        f"{context_hint}\n\n" if context_hint else ""
    ) + (
        f"Question: {question}\n\n"
        f"Search results:\n{search_results}\n\n"
        f"Answer:"
    )

    payload = {
        "model": settings.GROQ_FALLBACK_MODEL,
        "max_tokens": 40,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _GROQ_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    response = await client.post(_GROQ_URL, json=payload, headers=headers)

    if response.status_code == 429:
        retry = response.headers.get("retry-after") or "soon"
        return f"Rate limited — retry in {retry}"

    if response.status_code != 200:
        log.error("Groq HTTP %d — %s", response.status_code, response.text[:200])
        return f"Error {response.status_code}"

    return (
        response.json()["choices"][0]["message"].get("content") or "Not sure"
    ).strip()


async def _serper_groq_pipeline(question: str, context_hint: str) -> str:
    query = _build_search_query(question)
    log.info("   🔍 [fallback] Searching: %r", query[:80])

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        search_results = await _serper_search(client, query)
        if not search_results:
            log.warning("   ⚠️  [fallback] Serper returned nothing — trying Groq alone")
        log.info("   🔍 [fallback] Search done — sending to Groq (%s)", "llama-3.3-70b-versatile")
        answer = await _groq_answer(client, question, search_results, context_hint)

    return answer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_answer(
    question: str,
    on_fast_result=None,  # kept for API compatibility, not used here
) -> str:
    """
    Try Gemini 2.5 Flash first. Fall back to Serper + Groq if Gemini
    errors, rate-limits, returns empty, or times out. Never raises.
    """
    _recent_questions.append(question)
    recent = list(_recent_questions)[:-1]
    context_hint = (
        f"This is a football quiz. Recent questions: {'; '.join(recent[-3:])}. "
        f"Use this context to resolve any ambiguity."
        if recent else ""
    )

    t0 = time.perf_counter()

    # ── Primary: Gemini ──────────────────────────────────────────────────────
    log.info("   🤖 [1/2] Gemini (%s) …", "gemini-2.5-flash")
    try:
        answer = await asyncio.wait_for(_gemini_answer(question, context_hint), timeout=8.0)
        elapsed = (time.perf_counter() - t0) * 1000
        log.info("   ✅ Gemini responded in %.0fms → %r", elapsed, answer[:80])
        return answer

    except asyncio.TimeoutError:
        elapsed = (time.perf_counter() - t0) * 1000
        log.warning("   ⏱️  Gemini timed out after %.0fms — falling back", elapsed)

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        # Surface rate limit clearly
        msg = str(exc)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            log.warning("   ⚠️  Gemini rate limit hit (%.0fms) — falling back to Serper + Groq", elapsed)
        else:
            log.warning("   ⚠️  Gemini error (%.0fms): %s — falling back", elapsed, exc)

    # ── Fallback: Serper + Groq ───────────────────────────────────────────────
    log.info("   🔄 [2/2] Serper + Groq …")
    try:
        answer = await asyncio.wait_for(
            _serper_groq_pipeline(question, context_hint),
            timeout=15.0,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        log.info("   ✅ Fallback responded in %.0fms → %r", elapsed, answer[:80])
        return answer

    except asyncio.TimeoutError:
        elapsed = (time.perf_counter() - t0) * 1000
        log.error("   ❌ Fallback timed out after %.0fms", elapsed)
        return "Timed out — no answer"

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        log.error("   ❌ Fallback error (%.0fms): %s", elapsed, exc)
        return f"Error: {type(exc).__name__}"
