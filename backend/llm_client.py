"""
backend/llm_client.py

Three-step answer engine:
  1. _build_search_query  — LLM converts verbose question to a tight 5-8 word query
  2. _serper_search       — Searches Google via Serper.dev (2500 free searches)
  3. _extract_answer      — LLM reads snippets and returns a one-phrase answer

async get_answer(question: str) -> str
"""

import asyncio
import re
import time
import logging

import httpx

log = logging.getLogger(__name__)

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT    = httpx.Timeout(15.0)
_MAX_TOKENS = 40
_MODEL      = "llama-3.3-70b-versatile"


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
# Step 1 — Convert question to tight search query
# ---------------------------------------------------------------------------

async def _build_search_query(client: httpx.AsyncClient, question: str) -> str:
    """
    Ask the LLM to distil the trivia question into a focused 5-8 word
    Google search query. Avoids sending wrong years or verbose phrasing
    directly to Serper.
    """
    from backend.config import settings

    payload = {
        "model": _MODEL,
        "max_tokens": 20,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": (
                f"Convert this football trivia question into a short Google search query "
                f"(5-8 words, key facts only, no question words):\n\n{question}\n\nSearch query:"
            ),
        }],
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        r = await client.post(_GROQ_URL, json=payload, headers=headers)
        if r.status_code == 200:
            raw = r.json()["choices"][0]["message"].get("content", "").strip()
            query = raw.strip('"').strip("'").strip()
            if query:
                return f"football {query}"
    except Exception:
        pass

    return f"football soccer {question}"


# ---------------------------------------------------------------------------
# Step 2 — Serper Google search
# ---------------------------------------------------------------------------

async def _serper_search(client: httpx.AsyncClient, query: str) -> str:
    """
    Search Google via Serper.dev and return a plain-text summary.
    Prioritises the answer box, then knowledge graph, then organic snippets.
    """
    from backend.config import settings

    try:
        response = await client.post(
            _SERPER_URL,
            json={"q": query, "num": 5, "gl": "us", "hl": "en"},
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
# Step 3 — Extract answer from search results
# ---------------------------------------------------------------------------

async def _extract_answer(client: httpx.AsyncClient, question: str, search_results: str) -> str:
    """
    Pass the question and search snippets to the LLM and get a one-phrase answer.
    """
    from backend.config import settings

    prompt = (
        f"You are a football trivia assistant. Use ONLY the search results below to answer.\n"
        f"Reply with ONLY the answer — name, club, number, or short phrase. No sentences.\n"
        f"If multiple answers are possible, use the question's own context (competition, year, country) "
        f"to pick the most relevant one.\n"
        f"If the search results don't contain a clear answer, reply: Not sure\n\n"
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
    """
    Searches Google via Serper, then extracts the answer with llama-3.3-70b.
    Always uses live search — never relies on training data alone.
    """
    t0 = time.perf_counter()

    clean_q = question.replace("**", "").replace("*", "").strip()
    clean_q = re.sub(r'^\d+\.\s*', '', clean_q).strip()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:

            search_query = await _build_search_query(client, clean_q)
            log.info("   ↳ Searching: %r", search_query[:80])

            search_results = await _serper_search(client, search_query)
            elapsed_search = (time.perf_counter() - t0) * 1000
            log.info("   ↳ Search done in %.0fms — extracting answer", elapsed_search)

            answer = await _extract_answer(client, clean_q, search_results)

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
