import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
import httpx
sys.path.insert(0, '.')
from backend.llm_client import _build_search_query

SERPER_URL = "https://google.serper.dev/search"
SERPER_KEY = os.getenv("SERPER_API_KEY")

async def search(client, query):
    r = await client.post(SERPER_URL,
        json={"q": query, "num": 5},
        headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"})
    d = r.json()
    lines = []
    if d.get("answerBox"):
        box = d["answerBox"]
        lines.append("ANSWER BOX: " + str(box.get("answer") or box.get("snippet") or ""))
    for res in d.get("organic", [])[:4]:
        lines.append(f"  - {res.get('title')}: {res.get('snippet','')[:200]}")
    return "\n".join(lines)

async def main():
    questions = [
        "In 2024, which club made headlines by qualifying for the UEFA Champions League for the first time in their history after finishing 3rd?",
        "Which stadium hosted the highest-scoring match in La Liga history, a 12-1 victory in 1933?",
        "How many Brazilians have scored in their first 3 WC games?",
        # Manual override to test better UCL query
        "La Liga club first time Champions League qualifying finishing 3rd 2024",
    ]
    async with httpx.AsyncClient(timeout=15) as client:
        for q in questions:
            query = _build_search_query(q)
            print(f"Q:      {q[:90]}")
            print(f"QUERY:  {query}")
            results = await search(client, query)
            print(f"RESULTS:\n{results}")
            print("-" * 60)

asyncio.run(main())
