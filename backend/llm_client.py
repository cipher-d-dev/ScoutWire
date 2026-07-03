"""
backend/llm_client.py

Three-step answer engine:
  1. Smart query builder  — extracts noun phrases, drops years that may be wrong
  2. _serper_search       — searches Google via Serper.dev (2500 free searches)
  3. _extract_answer      — LLM reads snippets with quiz context and returns answer

async get_answer(question: str) -> str
"""

import re
import time
import logging
from collections import deque

import httpx

log = logging.getLogger(__name__)

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT    = httpx.Timeout(15.0)
_MAX_TOKENS = 40
_MODEL      = "llama-3.3-70b-versatile"

# Track last 5 questions to infer quiz theme for the extraction prompt
_recent_questions: deque = deque(maxlen=5)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class _RateLimitError(Exception):
    def __init__(self, retry_after: str | None):
        self.retry_after = retry_after

class _HttpError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Step 1 — Build a focused search query without using an LLM call
# ---------------------------------------------------------------------------

# Words to strip from the question before searching
_STOP_WORDS = {
    "who", "what", "which", "where", "when", "how", "many", "is", "was",
    "are", "were", "the", "a", "an", "in", "of", "for", "to", "and", "or",
    "that", "this", "their", "his", "her", "its", "by", "with", "from",
    "has", "have", "had", "did", "does", "do", "be", "been", "after",
    "before", "during", "at", "on", "ever", "also", "but", "not", "no",
    "made", "made", "headlines", "club", "team", "player", "manager",
}

def _build_search_query(question: str) -> str:
    """
    Build a focused search query by preserving key football phrases,
    stripping stop words, and dropping years (often wrong in trivia questions).
    """
    q = question.replace("**", "").replace("*", "").strip()
    q = re.sub(r'^\d+\.\s*', '', q)

    # Drop years — they're often wrong in quiz questions
    q = re.sub(r'\b(19|20)\d{2}\b', '', q)

    # Remove punctuation and stop words, keep meaningful tokens
    tokens = re.findall(r"[\w'-]+", q)
    filtered = [t for t in tokens if t.lower() not in _STOP_WORDS and len(t) > 1]

    query = " ".join(filtered).strip()
    return f"football {query}"


# ---------------------------------------------------------------------------
# Step 2 — Serper Google search
# ---------------------------------------------------------------------------

async def _serper_search(client: httpx.AsyncClient, query: str) -> str:
    from backend.config import settings

    try:
        response = await client.post(
            _SERPER_URL,
            json={"q": query, "num": 6, "gl": "us", "hl": "en"},
            headers={
                "X-API-KEY":    settings.SERPER_API_KEY,
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            log.warning("Serper returned HTTP %d", response.status_code)
            return "Search unavailable."

        data = response.json()
        lines = []

        if data.get("answerBox"):
            box = data["answerBox"]
            answer = box.get("answer") or box.get("snippet") or box.get("title")
            if answer:
                lines.append(f"Direct answer: {answer}")

        if data.get("knowledgeGraph"):
            desc = data["knowledgeGraph"].get("description") or data["knowledgeGraph"].get("title")
            if desc:
                lines.append(f"Knowledge graph: {desc}")

        for r in data.get("organic", []):
            snippet = r.get("snippet", "")
            title   = r.get("title", "")
            if snippet:
                lines.append(f"- {title}: {snippet}")

        return "\n".join(lines) if lines else "No search results found."

    except Exception as e:
        log.warning("Serper search failed: %s", e)
        return "Search unavailable."


# ---------------------------------------------------------------------------
# Step 3 — Extract answer using quiz context
# ---------------------------------------------------------------------------

async def _extract_answer(
    client: httpx.AsyncClient,
    question: str,
    search_results: str,
    recent_qs: list[str],
) -> str:
    from backend.config import settings

    # Build context hint from recent questions
    context_hint = ""
    if recent_qs:
        context_hint = (
            f"Context: This question is from a quiz. "
            f"Recent questions in this quiz: {'; '.join(recent_qs[-3:])}. "
            f"Use this to resolve any ambiguity (e.g. if recent questions mention La Liga, prefer La Liga answers).\n\n"
        )

    prompt = (
        f"You are a football trivia assistant. Answer the question using the search results below.\n"
        f"{context_hint}"
        f"Reply with ONLY the answer — name, club, number, or short phrase. No sentences.\n"
        f"If multiple answers are possible, use the question context to pick the most relevant one.\n"
        f"Rules:\n"
        f"- If the search results contain the answer clearly, use it.\n"
        f"- If the search results are vague but you know the answer confidently from your own knowledge, use that.\n"
        f"- Only reply 'Not sure' if you genuinely don't know and the search results don't help.\n\n"
        f"Question: {question}\n\n"
        f"Search results:\n{search_results}\n\n"
        f"Answer:"
    )

    payload = {
        "model": _MODEL,
        "max_tokens": _MAX_TOKENS,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    response = await client.post(_GROQ_URL, json=payload, headers=headers)

    if response.status_code == 429:
        raise _RateLimitError(
            response.headers.get("retry-after")
            or response.headers.get("x-ratelimit-reset-requests")
        )
    if response.status_code != 200:
        log.error("Groq HTTP %d — %s", response.status_code, response.text[:200])
        raise _HttpError(response.status_code)

    return (response.json()["choices"][0]["message"].get("content") or "Not sure").strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_answer(question: str) -> str:
    t0 = time.perf_counter()

    clean_q = question.replace("**", "").replace("*", "").strip()
    clean_q = re.sub(r'^\d+\.\s*', '', clean_q).strip()

    # Track for context
    _recent_questions.append(clean_q)
    recent_qs = list(_recent_questions)[:-1]  # all but current

    search_query = _build_search_query(clean_q)
    log.info("   ↳ Searching: %r", search_query[:80])

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:

            search_results = await _serper_search(client, search_query)
            elapsed_search = (time.perf_counter() - t0) * 1000
            log.info("   ↳ Search done in %.0fms — extracting answer", elapsed_search)

            answer = await _extract_answer(client, clean_q, search_results, recent_qs)

        elapsed_total = (time.perf_counter() - t0) * 1000
        log.info("   ↳ Done in %.0fms — answer: %r", elapsed_total, answer[:80])
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
