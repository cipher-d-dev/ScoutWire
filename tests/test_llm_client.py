"""
tests/test_llm_client.py

Unit tests for backend/llm_client.py.

All tests mock the httpx transport — no real network calls, no Groq API key needed.

Run with: pytest tests/test_llm_client.py -v
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject dummy env vars so config.py loads without a real .env
# ---------------------------------------------------------------------------
os.environ.setdefault("TELEGRAM_API_ID", "11111111")
os.environ.setdefault("TELEGRAM_API_HASH", "testhash")
os.environ.setdefault("TELEGRAM_PHONE", "+440000000000")
os.environ.setdefault("GROQ_API_KEY", "gsk_testkey")
os.environ.setdefault("TARGET_CHAT", "-100987654321")
os.environ.setdefault("QUIZMASTER_USER_ID", "111222333")
os.environ.setdefault("GROQ_MODEL", "llama-3.1-8b-instant")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.llm_client import get_answer


# ---------------------------------------------------------------------------
# Helpers to build mock SSE responses
# ---------------------------------------------------------------------------

def _make_sse_chunk(content: str) -> str:
    """Build a single SSE data line containing a streamed token."""
    obj = {
        "choices": [{"delta": {"content": content}, "finish_reason": None}]
    }
    return f"data: {json.dumps(obj)}"


def _make_sse_lines(*tokens: str) -> list[str]:
    """Build a list of SSE lines ending with [DONE]."""
    lines = [_make_sse_chunk(t) for t in tokens]
    lines.append("data: [DONE]")
    return lines


def _mock_stream_response(status_code: int, lines: list[str], headers: dict | None = None):
    """
    Return an async context manager that yields a mock httpx streaming response.

    Mimics the interface used by `async with client.stream(...) as response`.
    """
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = headers or {}

    # Use an async iterator class instead of an async generator function to
    # avoid Python 3.14 RuntimeWarning about unawaited aclose() on teardown.
    class _AsyncLineIter:
        def __init__(self, data):
            self._iter = iter(data)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    mock_response.aiter_lines = lambda: _AsyncLineIter(lines)
    mock_response.aread = AsyncMock(return_value=b"")

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_response)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# Tests — successful response
# ---------------------------------------------------------------------------

class TestGetAnswerSuccess:

    @pytest.mark.asyncio
    async def test_returns_assembled_answer(self):
        """Tokens streamed in multiple chunks are assembled into one string."""
        lines = _make_sse_lines("Brazil", " has won ", "five World Cups.")

        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(200, lines)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Which country has won the most World Cups?")

        assert result == "Brazil has won five World Cups."

    @pytest.mark.asyncio
    async def test_skips_non_data_lines(self):
        """SSE lines without 'data: ' prefix are silently ignored."""
        lines = [
            ": keep-alive",
            "",
            _make_sse_chunk("Arsenal"),
            "data: [DONE]",
        ]

        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(200, lines)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Name a Premier League club.")

        assert result == "Arsenal"

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_answer(self):
        lines = _make_sse_lines("  Real Madrid.  ")

        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(200, lines)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Who has won the most Champions League titles?")

        assert result == "Real Madrid."


# ---------------------------------------------------------------------------
# Tests — 429 rate-limit
# ---------------------------------------------------------------------------

class TestGetAnswerRateLimit:

    @pytest.mark.asyncio
    async def test_429_with_retry_after_header(self):
        """429 with Retry-After header → distinct fallback string with seconds."""
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(
                429, [], headers={"retry-after": "30"}
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Who won Euro 2020?")

        assert "Rate limited" in result
        assert "30" in result          # retry-after value surfaced in message
        assert "retry" in result.lower()

    @pytest.mark.asyncio
    async def test_429_without_retry_after_header(self):
        """429 with no Retry-After header → generic rate-limit fallback, no crash."""
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(429, [], headers={})
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Who won Euro 2020?")

        assert "Rate limited" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_429_does_not_raise(self):
        """get_answer must never raise — a 429 must produce a string."""
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(
                429, [], headers={"retry-after": "60"}
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            try:
                result = await get_answer("Any question")
                assert isinstance(result, str)
            except Exception as e:
                pytest.fail(f"get_answer raised unexpectedly: {e}")

    @pytest.mark.asyncio
    async def test_429_different_from_generic_error(self):
        """Rate-limit response must be distinguishable from a generic HTTP error."""
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()

            mock_client.stream.return_value = _mock_stream_response(
                429, [], headers={"retry-after": "10"}
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            rate_limit_result = await get_answer("Q1")

        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(500, [])
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            error_result = await get_answer("Q2")

        assert rate_limit_result != error_result
        assert "Rate limited" in rate_limit_result
        assert "Rate limited" not in error_result


# ---------------------------------------------------------------------------
# Tests — timeout
# ---------------------------------------------------------------------------

class TestGetAnswerTimeout:

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback_string(self):
        """httpx.TimeoutException → clear fallback string, no raise."""
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.side_effect = httpx_timeout_error()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Who is the all-time top scorer in the Premier League?")

        assert "timed out" in result.lower()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_timeout_does_not_raise(self):
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.side_effect = httpx_timeout_error()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            try:
                result = await get_answer("Any question")
                assert isinstance(result, str)
            except Exception as e:
                pytest.fail(f"get_answer raised on timeout: {e}")


# ---------------------------------------------------------------------------
# Tests — non-200 HTTP errors (not 429)
# ---------------------------------------------------------------------------

class TestGetAnswerHttpErrors:

    @pytest.mark.asyncio
    async def test_500_returns_error_string(self):
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(500, [])
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Any question")

        assert "500" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_503_returns_error_string(self):
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(503, [])
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Any question")

        assert "503" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_non_200_does_not_raise(self):
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(502, [])
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            try:
                result = await get_answer("Any question")
                assert isinstance(result, str)
            except Exception as e:
                pytest.fail(f"get_answer raised on non-200: {e}")

    @pytest.mark.asyncio
    async def test_401_returns_error_string(self):
        """Bad API key should not crash — return error string."""
        with patch("backend.llm_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.stream.return_value = _mock_stream_response(401, [])
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await get_answer("Any question")

        assert "401" in result


# ---------------------------------------------------------------------------
# Helper — build a real httpx.TimeoutException without making a real request
# ---------------------------------------------------------------------------

import httpx as _httpx

def httpx_timeout_error() -> _httpx.TimeoutException:
    return _httpx.TimeoutException("Request timed out")
