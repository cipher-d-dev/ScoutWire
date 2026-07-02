# ScoutWire — Telegram Football Quiz Answer Bot

A personal, local-only tool that monitors a Telegram quiz chat, detects questions posted by a designated quizmaster, asks Groq's LLM for an answer, and displays it in a fast browser UI — ready to copy and paste into Telegram in under a second.

> **This is a single-user tool for local use. It never sends any message automatically.**
> All answers are copy-pasted manually. See the [ToS note](#important--telegram-tos-note) below.

---

## Contents

1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Getting credentials](#getting-credentials)
4. [Installation](#installation)
5. [First-run setup](#first-run-setup)
6. [Running the bot](#running-the-bot)
7. [Using the UI](#using-the-ui)
8. [Architecture decisions](#architecture-decisions)
9. [Troubleshooting](#troubleshooting)
10. [Important — Telegram ToS note](#important--telegram-tos-note)

---

## How it works

```
Telegram chat
    │  quizmaster sends "15. Which club won the 1999-2000 La Liga?"
    ▼
Telethon (userbot — listens as you)
    │  sender ID matches QUIZMASTER_USER_ID?
    ▼
Groq API  ──streaming──►  answer in ~300-600ms
    ▼
WebSocket push
    ▼
Browser UI  →  tap to copy  →  paste into Telegram
```

Detection is **sender-based**: any message from the configured quizmaster in the target chat is treated as a question. No keyword matching, no LLM classification — this cannot misfire on ordinary football chat.

---

## Requirements

- Python 3.11+
- A Telegram account (your own — this is a userbot, not a BotFather bot)
- A free [Groq API key](https://console.groq.com)
- Internet connection

---

## Getting credentials

### Telegram API credentials

1. Go to [https://my.telegram.org](https://my.telegram.org) and log in with your phone number.
2. Click **"API development tools"**.
3. Create an app (name and platform don't matter — use anything).
4. Copy your **App api_id** (a number) and **App api_hash** (a hex string).

### Groq API key

1. Go to [https://console.groq.com](https://console.groq.com) and sign up (free).
2. Navigate to **API Keys** → **Create API Key**.
3. Copy the key — it starts with `gsk_`.

---

## Installation

```bash
git clone <your-repo-url>
cd telegram-quiz-bot

pip install -r requirements.txt
```

Copy the example env file and fill it in:

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in all six values. See the comments in `.env.example` for exactly what goes where.

---

## First-run setup

You need two pieces of information before the bot can filter correctly:
the **chat ID** of the quiz group, and the **user ID** of the quizmaster.

### Step 1 — Find the chat ID

```bash
python scripts/list_chats.py
```

This logs in (triggering the phone code prompt on first run — see below), then
prints every chat your account can see with its numeric ID:

```
               ID  Name
------------------------------------------------------------
  -1001234567890  Football Quiz Championship
       987654321  John (DM)
             ...
```

Copy the ID of the quiz group (it will be a large negative number for groups/channels)
and set it as `TARGET_CHAT` in `.env`.

### Step 2 — Find the quizmaster's user ID

```bash
python scripts/list_senders.py -1001234567890 120
```

Replace `-1001234567890` with your `TARGET_CHAT`. This listens for 120 seconds
and prints every sender's numeric ID and display name as messages arrive.
Ask the quizmaster to send any message during the window, or wait for them to post naturally.

```
Listening on chat -1001234567890 for 120s …
Ask the quizmaster to send a message now.

     Numeric ID  Display name
--------------------------------------------------
      111222333  QuizMaster Dave
      444555666  Regular Player
```

Copy the quizmaster's numeric ID and set it as `QUIZMASTER_USER_ID` in `.env`.

**Why numeric ID and not @username?** Usernames can be changed by the account
holder at any time. A renamed quizmaster account would silently break the filter.
Numeric IDs are permanent and cannot be reassigned.

### Step 3 — First-run Telegram login

The first time any script or the main bot connects, Telethon will prompt:

```
Please enter your phone (or bot token): +447700900000
Please enter the code you received: 12345
```

Enter your phone number in E.164 format (e.g. `+447700900000`), then enter
the verification code Telegram sends. If your account has 2FA enabled, you'll
also be prompted for your cloud password.

Your session is saved to `session/user.session`. Subsequent runs skip this step entirely.

---

## Running the bot

```bash
python -m backend.main
```

This starts both the Telegram listener and the web server together in one process.
Open your browser to:

```
http://localhost:8000
```

For development (auto-reload on code changes — restarts Telegram login each time,
so prefer the above for normal use):

```bash
uvicorn backend.main:app --reload
```

---

## Using the UI

**Status bar (top):** Green dot = WebSocket connected. If it goes red, the UI
reconnects automatically — no action needed.

**Start / Stop button:** Tap to toggle whether incoming quizmaster messages get
processed. The dot pulses green when listening is active.

**Latest answer card:** The most recent answer appears here, large and readable.
Tap anywhere on the card to copy the answer to clipboard. A green flash confirms
the copy. If the answer is rate-limited (amber border, "RATE LIMITED" badge),
it means Groq temporarily throttled the request — wait a moment and manually
retry by checking the question number and re-asking if needed.

**History:** All answered questions for the current session, newest at top,
each with its own Copy button. Loads from the server on page open and updates
live as new answers arrive.

**Mobile use:** Open `http://<your-local-ip>:8000` on your phone (same Wi-Fi).
The UI is designed for one-tap copy under time pressure — large tap targets,
minimal chrome.

---

## Architecture decisions

### Sender-based detection (not keyword/LLM)

The quizmaster filter checks `sender_id == QUIZMASTER_USER_ID` and nothing else.
This is intentional:

- **Cannot misfire** on ordinary football chat, banter, or score disputes.
- **Zero cost** — a single integer comparison, no API calls for non-quizmaster messages.
- **Simple to debug** — either the ID matches or it doesn't.

The trade-off: if multiple people ever take turns asking questions, you'd need
to update `QUIZMASTER_USER_ID` (or extend the config to a list). That's a one-line
change if the quiz format ever changes.

### Single asyncio event loop (Telethon + Uvicorn)

Both the Telegram client and the web server run in one `asyncio.gather()` loop.
This avoids thread synchronisation and means the WebSocket push happens in the
same coroutine that just received the LLM answer — no queues, no locks for the
happy path.

### Streaming LLM responses

`get_answer()` uses Groq's `stream: true` endpoint. The first token arrives in
~150ms; the answer is assembled as chunks land. This is faster than waiting for
a complete response and is why end-to-end latency is typically 300-600ms.

### No persistence

History resets on restart. This is intentional — quizzes are ephemeral, and
persisting history adds complexity for zero practical benefit in a local tool.

---

## Troubleshooting

**`Missing required environment variable: X`**
Open `.env` and make sure every variable is set with no quotes around values.

**`SessionPasswordNeededError` during login**
Your Telegram account has 2FA enabled. Enter your cloud password when prompted.

**The UI shows "Reconnecting…" and never connects**
Make sure `python -m backend.main` is running. The WebSocket endpoint is served
by the same process — it won't work with `uvicorn backend.main:app` alone if
the Telegram client failed to start.

**Answers are coming from the wrong person / false positives**
Double-check `QUIZMASTER_USER_ID` in `.env`. Run `scripts/list_senders.py` again
to confirm the numeric ID. Make sure you're using the ID, not a username.

**Groq returns wrong or hallucinated answers**
The model is `llama-3.1-8b-instant` by default — fast but not infallible on obscure
stats. Set `GROQ_MODEL=llama3-70b-8192` in `.env` for a more accurate (but slower)
model, or check the Groq console for other available models.

**`ModuleNotFoundError: No module named 'telethon'`**
Run `pip install -r requirements.txt` from inside the `telegram-quiz-bot/` directory.

---

## Important — Telegram ToS note

This bot operates as a **userbot** — it authenticates as your personal Telegram
account using the MTProto API, not as a bot created via BotFather.

Telegram's Terms of Service restrict automated actions on personal accounts.
This tool is designed to stay within acceptable use:

- It is **strictly read-only** — it never sends, forwards, or reacts to any message.
- All responses are **manually copy-pasted** by the user.
- It runs **locally on your own machine** for personal use only.
- It makes **one LLM API call per question** from the quizmaster — very low volume.

You are responsible for ensuring your use complies with Telegram's ToS.
Do not modify this tool to send messages automatically.
