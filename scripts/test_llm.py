"""
scripts/test_llm.py

Manual smoke-test for the LLM answer engine.

Sends 5 football trivia questions to Groq and prints each answer with latency.
Includes at least one deliberately obscure question to verify the model hedges
rather than confidently hallucinating.

Usage:
    python scripts/test_llm.py

Requires a valid GROQ_API_KEY in .env.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.llm_client import get_answer

QUESTIONS = [
    # 1 — well-known fact, should answer confidently
    "Which country has won the most FIFA World Cups?",

    # 2 — specific season record, should answer confidently
    "Who scored the winning goal in the 2005 Champions League final?",

    # 3 — moderately obscure, tests accuracy
    "Which club won their only La Liga title in the 1999-2000 season?",

    # 4 — deliberately obscure stat — model should hedge if unsure
    "How many hat-tricks did Dixie Dean score in the 1927-28 First Division season?",

    # 5 — non-football question — model should refuse politely per system prompt
    "What is the capital of France?",
]


async def main() -> None:
    print("ScoutWire — LLM answer engine test")
    print("=" * 60)

    total_start = time.perf_counter()

    for i, question in enumerate(QUESTIONS, 1):
        print(f"\nQ{i}: {question}")
        t0 = time.perf_counter()
        answer = await get_answer(question)
        latency_ms = (time.perf_counter() - t0) * 1000
        print(f"A{i}: {answer}")
        print(f"    [{latency_ms:.0f}ms]")

    total_ms = (time.perf_counter() - total_start) * 1000
    print("\n" + "=" * 60)
    print(f"All 5 questions answered. Total time: {total_ms:.0f}ms")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
