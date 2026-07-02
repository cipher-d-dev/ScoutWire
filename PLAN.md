# Build Guide: Telegram Football Quiz Answer Bot

**Instructions for the AI agent:** Build this in the exact phase order below. Do not start phase N+1 until phase N's acceptance criteria all pass. After each phase, stop and report what was built, how it was tested, and any deviations from spec. Keep changes scoped to the current phase only — no scope creep into later phases.

## Stack (fixed, do not substitute)
- **Language:** Python 3.11+
- **Telegram client:** Telethon (userbot via MTProto, not BotFather) — user listens as themselves
- **LLM:** Groq API (free tier, fast inference) — model `llama-3.1-8b-instant` by default, configurable via env var
- **Backend/web server:** FastAPI + Uvicorn, WebSocket for live push to frontend
- **Frontend:** single static HTML/JS page served by FastAPI, no build step, no framework
- **Config:** `.env` file (python-dotenv), never hardcode secrets
- **Scope:** single-user, runs locally on one person's machine, no auth/multi-tenant needed

## Speed requirement (decided up front, informs Phases 3, 5, 6, 7)
**Target:** Answer visible on screen within ~300–700ms of the quizmaster sending a message. Every phase must be built with this in mind.
- **Phase 3 (LLM):** Use Groq streaming (`stream: true`). Cap output tokens at ~80. First token lands in ~150ms; do not wait for the full response before pushing to the client.
- **Phase 5 (pipeline):** Fire the LLM call via `asyncio.create_task` immediately on message receipt — no queuing or intermediate steps.
- **Phase 6 (WebSocket):** Push streamed tokens to the browser as they arrive, not after the full answer is assembled.
- **Phase 7 (frontend):** Render tokens progressively as they stream in. Copy button activates on completion but the answer is readable during streaming.
- Do not add caching (quiz questions are unique, hit rate ≈ 0). Do not downgrade the model for speed — `llama-3.1-8b-instant` is already the fastest option that maintains accuracy on obscure football facts.

---

## Detection model (decided up front, informs Phase 2)
The quiz format is: one designated quizmaster account sends only numbered questions during a quiz round (e.g. `15. Which club won their only La Liga title in the 1999–2000 season?`), and a separate moderator handles scoring disputes. Detection is therefore **sender-based, not content-based**: any message from the configured quizmaster in the target chat is treated as a question. No keyword matching or LLM classification is needed as the primary mechanism — this is simpler and cannot misfire on ordinary football chat.

---

## Phase 0 — Project scaffold

**Goal:** Empty but runnable skeleton.

Tasks:
- Create project structure:
  ```
  telegram-quiz-bot/
    backend/
      __init__.py
      main.py
      config.py
    frontend/
      index.html
    requirements.txt
    .env.example
    README.md
    .gitignore   (ignore .env, *.session, __pycache__)
  ```
- `requirements.txt`: telethon, fastapi, uvicorn[standard], python-dotenv, httpx
- `config.py`: loads env vars:
  - `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`
  - `GROQ_API_KEY`, `GROQ_MODEL` (default `llama-3.1-8b-instant`)
  - `TARGET_CHAT` — the chat ID to monitor
  - `QUIZMASTER_USER_ID` — numeric Telegram user ID of the question-asker (see note below on why not username)
  - Raise a clear error if any required var is missing.
- `.env.example` with placeholder values and a comment on where to get each (my.telegram.org for Telegram, console.groq.com for Groq).

**Acceptance criteria:**
- `pip install -r requirements.txt` succeeds.
- `python -c "from backend.config import settings"` runs without error when `.env` is filled in, and fails with a clear message when it's missing a required var.

---

## Phase 1 — Telegram listener (read-only, console output)

**Goal:** Prove Telegram auth works and messages can be read live.

Tasks:
- In `backend/telegram_client.py`, create a Telethon `TelegramClient` using session file `session/user.session`.
- First-run interactive login (phone + code, and 2FA password if enabled) via terminal — this is expected to be manual, one-time.
- Add a standalone script `scripts/list_chats.py` that prints all dialogs (chat name + ID), so the user can find `TARGET_CHAT`.
- Add a second standalone script `scripts/list_senders.py` that listens on a given chat for a short window and prints each sender's display name + **numeric user ID** for every message seen, so the user can identify `QUIZMASTER_USER_ID` without guessing. Use numeric ID, not `@username` — usernames can be changed by the account holder at any time and would silently break the filter; numeric IDs are permanent.
- Add a `NewMessage` event handler scoped to `TARGET_CHAT` that just prints sender ID, sender name, and message text to console. No filtering logic yet.

**Acceptance criteria:**
- Running `python -m backend.telegram_client` logs in (or reuses saved session) and prints live messages from the target chat as they arrive.
- `scripts/list_senders.py` correctly identifies the quizmaster's numeric user ID from a real test message.
- Confirm no messages are ever sent by the script — read-only.

---

## Phase 2 — Quizmaster message filter

**Goal:** Pure function, fully unit-testable, no network calls. Sender-based, not content-based.

Tasks:
- `backend/detector.py`: primary function `is_from_quizmaster(sender_id: int, chat_id: int) -> bool` — returns True only if `sender_id == QUIZMASTER_USER_ID` and `chat_id == TARGET_CHAT`. That's the whole check.
- Add a helper `parse_question(text: str) -> tuple[int | None, str]` that strips a leading number/period (e.g. `"15. Which club..."` → `(15, "Which club...")`) for cleaner display in the UI later, falling back to `(None, text)` if there's no leading number.
- Optional (build only if time allows, not required for MVP correctness): a secondary content-based sanity check — a lightweight keyword+question-mark heuristic — as a belt-and-suspenders flag if the quizmaster ever sends a non-question message (e.g. "brb 5 mins"), so it doesn't get treated as a question needing an answer. If built, this is advisory only (e.g. logs a warning) and does not replace the sender check as the primary gate.
- Write `tests/test_detector.py`: cases for correct sender/chat match, wrong sender, wrong chat, numbered and non-numbered question parsing.

**Acceptance criteria:**
- `pytest tests/test_detector.py` passes all cases.
- Confirm a message from the moderator (scoring disputes) in the same chat is correctly ignored.
- No import of telethon/httpx in this module — it must stay dependency-free and fast.

---

## Phase 3 — LLM answer engine (Groq)

**Goal:** Given a question string, return a short, accurate, fast answer — isolated from Telegram entirely.

Tasks:
- `backend/llm_client.py`: async function `get_answer(question: str) -> str` that calls Groq's `/openai/v1/chat/completions` endpoint via `httpx.AsyncClient`.
- System prompt must instruct the model to:
  - Answer only football-related trivia, concisely (1–2 sentences max, just the fact + brief context).
  - If not confident about an obscure/specific stat (e.g. exact counts, specific season records), say so explicitly rather than guessing — accuracy over confident-sounding answers.
  - No preamble like "Sure, here's the answer."
- Error handling, explicitly covering:
  - Timeout → return a clear fallback string.
  - Non-200 response generally → return a clear fallback string, never raise unhandled into the caller.
  - **429 rate-limit specifically** → read the `retry-after` header if present, and return a distinct fallback like `"Rate limited — retry in {n}s"` so the frontend (Phase 7) can surface this differently from a generic error. Given sender-based filtering keeps request volume very low (only real quiz questions trigger a call), this should be rare in practice, but must fail gracefully rather than silently when it happens.
- Write a manual test script `scripts/test_llm.py` that sends 5 sample football questions and prints answers + latency for each.

**Acceptance criteria:**
- `python scripts/test_llm.py` returns answers for all 5 sample questions in well under 2 seconds each.
- Confirm at least one deliberately obscure/tricky question in the sample set to check the model hedges appropriately instead of confidently hallucinating.
- Simulate/mock a 429 response and confirm the rate-limit fallback string and retry-after parsing work without raising.

---

## Phase 4 — Start/stop control state

**Goal:** In-memory toggle that gates whether incoming messages get processed.

Tasks:
- `backend/state.py`: simple class/singleton holding `listening: bool = False` plus a short in-memory history list of recent `{number, question, answer, timestamp}` entries (cap at ~20). Include the parsed question number from Phase 2's `parse_question` for display purposes.
- No persistence needed — resets on restart, that's fine.

**Acceptance criteria:**
- Unit test: toggling state on/off works as expected; history list caps correctly and drops oldest entries.

---

## Phase 5 — Wire it together (listener → quizmaster filter → LLM → state)

**Goal:** End-to-end pipeline, still console-only output.

Tasks:
- In the Telethon message handler: if `state.listening` is True, check `is_from_quizmaster(sender_id, chat_id)`; if True, parse the question number/text, `await get_answer(text)`, append result to state history, print to console.
- Make sure this doesn't block the Telethon event loop — use `asyncio.create_task` for the LLM call so other messages keep being read while one answer is generating.

**Acceptance criteria:**
- With `state.listening = True` set manually in code for this phase, send a real numbered quiz question from the quizmaster account and confirm an answer appears in console within ~1-2 seconds.
- Confirm messages from anyone else (including the moderator) are correctly ignored — check via a log line.

---

## Phase 6 — FastAPI backend + WebSocket

**Goal:** Expose state and live updates over HTTP/WebSocket, run alongside the Telethon client in the same event loop.

Tasks:
- `backend/main.py`: FastAPI app with:
  - `GET /` → serves `frontend/index.html`
  - `POST /toggle` → flips `state.listening`, returns new status
  - `GET /status` → returns `{listening, history}`
  - `WS /ws` → on connect, send current history; then push each new `{number, question, answer, timestamp}` as it's produced
- Run Telethon client and Uvicorn concurrently in one asyncio loop (`asyncio.gather` or Telethon's `client.start()` + `uvicorn.Server(...).serve()` together).
- Replace Phase 5's manual `state.listening = True` with the real toggle from `/toggle`.

**Acceptance criteria:**
- `uvicorn backend.main:app` starts both the Telegram listener and the web server.
- Hitting `POST /toggle` twice enables then disables processing — verify via `/status` and by sending a test question from the quizmaster account.
- A WebSocket test client (or browser console) receives a push message when a new answer is produced.

---

## Phase 7 — Frontend UI

**Goal:** Minimal, fast, single-page UI for the actual use case: see the answer, copy it in one gesture, paste into Telegram.

Tasks:
- `frontend/index.html`: single file, inline CSS/JS, no build tooling.
- Elements:
  - Connection/listening status indicator
  - Start/Stop button calling `POST /toggle`
  - Large "latest answer" card — question number + question + answer, with a big tap-to-copy area (`navigator.clipboard.writeText`), visual confirmation flash on copy (e.g. brief color change), works via single tap/click
  - Distinct visual treatment for a rate-limited response (from Phase 3's fallback string) vs. a normal answer, so it's obvious at a glance this one needs a manual retry
  - Scrollable history of previous Q&A pairs (from `/status` on load, appended live via WebSocket), each with its own small copy button
- WebSocket client with basic auto-reconnect (retry after a short delay if connection drops).
- Design should be dark, high-contrast, legible at a glance mid-quiz — this is used under time pressure, not browsed leisurely. Favor large tap targets and minimal chrome over decoration.

**Acceptance criteria:**
- Open `http://localhost:8000` in a browser, toggle listening on, send a numbered quiz question from the quizmaster account, see the answer appear live without refreshing, and successfully copy it with one tap/click (verify paste works).
- Works on both desktop and mobile viewport sizes (this will be used from a phone browser too).

---

## Phase 8 — Config polish & docs

**Goal:** Someone else (the user's brother) can clone this and run their own independent instance.

Tasks:
- Finish `README.md` covering:
  - How to get Telegram `api_id`/`api_hash` (my.telegram.org) and a free Groq API key (console.groq.com)
  - First-run login flow (what to expect from the interactive phone/code prompt)
  - How to use `scripts/list_chats.py` and `scripts/list_senders.py` to find `TARGET_CHAT` and `QUIZMASTER_USER_ID`
  - How to run it (`uvicorn backend.main:app --reload` for dev, plain for normal use)
  - Explicit note: this automates a personal account (userbot), not a BotFather bot — keep usage read-only/manual-paste as designed, and be aware Telegram's ToS restricts automating personal accounts, so avoid high-volume automated sending.
  - Note on why sender-based filtering was chosen over keyword/LLM detection (simpler, cheaper, cannot misfire on ordinary football chat), and what to do if the quiz format ever changes (e.g. multiple people asking questions).
- Double check `.gitignore` actually excludes `.env` and `*.session` files (these contain secrets/auth).

**Acceptance criteria:**
- A fresh clone + `.env` fill-in + `pip install` + first-run login, following only the README, gets to a working `localhost:8000` UI with no undocumented steps.

---

## Phase 9 — Manual end-to-end soak test

**Goal:** Confirm real-world reliability before calling it done.

Tasks:
- Run for an extended live session (target: at least 30–60 minutes) during a real quiz round, toggling start/stop a few times.
- Confirm the quizmaster filter has zero false positives/negatives across a full round (should be trivial to verify since it's a simple ID match, but confirm in practice — e.g. check the quizmaster didn't post anything meant as banter that got treated as a question).
- Confirm the process survives a dropped WebSocket connection and a Telegram reconnect without crashing.
- If a 429 was ever hit during the session, confirm the UI surfaced it clearly and a manual retry worked.

**Acceptance criteria:**
- No unhandled exceptions during the soak test.
- Quizmaster filter accuracy confirmed at 100% by the user (this should hold by construction, since it's a direct ID match, not a heuristic).
- Document any issues/tuning in a short `NOTES.md`.

---

## Explicitly out of scope (do not build unless asked)
- Auto-sending answers into Telegram (the design is manual copy-paste on purpose)
- Live scores/stats API integration (general knowledge only, per spec)
- Content-based (keyword/LLM) question detection as the primary mechanism — sender-based filtering is the chosen design; only build the optional keyword sanity-check in Phase 2 if there's spare time
- Multi-user auth, hosting, or deployment beyond one person's local machine
- Model fine-tuning or training of any kind
