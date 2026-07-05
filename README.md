# ScoutWire — Headless Football Quiz Assistant

ScoutWire watches a Telegram quiz chat, detects questions from the quizmaster, and gets an answer in under a second using Gemini 2.5 Flash. The answer is automatically copied to your clipboard. Press **F9** in any window to type it.

> **ScoutWire never sends any message. You always paste the answer yourself.**

---

## What happens when it runs

```
Quizmaster posts a question in Telegram
    ↓
ScoutWire detects it (only quizmaster messages trigger this)
    ↓  [log] 📨 [1/3] Quizmaster message received | Q15 from Dave
    ↓  [log] 🤖 [2/3] Sending to answer engine …
    ↓  [log]    ✅ Gemini responded in 487ms → 'Real Madrid'
    ↓  [log] ✅ [3/3] Answer ready | Q15 → Real Madrid
    ↓  [log] 📋 Copied to clipboard — press F9 in Telegram to paste.
    ↓
Press F9 → answer is typed into Telegram instantly
```

### Answer engine (primary → fallback)

1. **Gemini 2.5 Flash** — fast, highly accurate, recent knowledge. Used for ~95% of questions.
2. **Serper web search → Groq 70b** — fires only if Gemini times out or errors. Grounds the answer in live search results.

---

## Before you start — install Python

1. Go to [https://www.python.org/downloads/](https://www.python.org/downloads/) and download Python 3.11+.
2. Run the installer. **Tick "Add Python to PATH"** on the first screen.
3. Verify in a new Command Prompt:
   ```
   python --version
   ```

---

## Step 1 — Get your credentials

### A. Telegram API credentials
1. Go to [https://my.telegram.org](https://my.telegram.org) and log in.
2. Click **"API development tools"** → create an app (any name).
3. Copy your **App api_id** and **App api_hash**.

### B. Gemini API key (primary LLM)
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Click **Create API key**.
3. Copy the key — it starts with `AIzaSy`.

### C. Groq API key (fallback LLM)
1. Go to [https://console.groq.com](https://console.groq.com) and sign up — free.
2. Click **API Keys** → **Create API Key**.
3. Copy the key — it starts with `gsk_`.

### D. Serper API key (fallback web search)
1. Go to [https://serper.dev](https://serper.dev) and sign up — 2500 free searches.
2. Copy your API key from the dashboard.

### E. Your phone number
Your Telegram phone number in international format, e.g. `+2348012345678`.

---

## Step 2 — Set up the project

```
cd C:\Users\YourName\Desktop\ScoutWire
pip install -r requirements.txt
```

Then copy and fill in the config file:

```
copy .env.example .env
```

Open `.env` and fill in your values:

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+2348012345678

GEMINI_API_KEY=AIzaSy_your_key_here
GEMINI_MODEL=gemini-2.5-flash

GROQ_API_KEY=gsk_your_key_here
GROQ_FALLBACK_MODEL=llama-3.3-70b-versatile

SERPER_API_KEY=your_serper_key_here

TARGET_CHAT=-1001234567890
QUIZMASTER_USER_ID=987654321
```

You'll fill in `TARGET_CHAT` and `QUIZMASTER_USER_ID` in the next steps.

---

## Step 3 — Find the quiz group's chat ID

```
python scripts/list_chats.py
```

The first time, Telethon will ask you to log in:

```
Please enter your phone: +2348012345678
Please enter the code you received: 12345
```

You'll see a list like:

```
               ID  Name
------------------------------------------------------------
  -1001234567890  Football Quiz Championship
       987654321  John (DM)
```

Copy the quiz group's ID (large negative number) and set it as `TARGET_CHAT` in `.env`.

> Your login is saved to `session/user.session`. You won't be asked again.

---

## Step 4 — Find the quizmaster's user ID

```
python scripts/find_quizmaster.py
```

This scans the last 50 messages in `TARGET_CHAT` and instantly prints every sender's numeric ID and display name — no waiting, no username needed:

```
Scanning last 50 messages in chat -1001234567890 …

     Numeric ID  Display name
-------------------------------------------------------
      111222333  QuizMaster Dave
      444555666  John Smith
      777888999  Sarah Jones

Found 3 unique sender(s) in the last 50 messages.

Copy the quizmaster's numeric ID and add it to your .env:
  QUIZMASTER_USER_ID=111222333
```

If the quizmaster hasn't posted recently, scan further back:

```
python scripts/find_quizmaster.py -1001234567890 200
```

---

## Step 5 — Run ScoutWire

```
python -m backend.main
```

Startup output:

```
============================================================
ScoutWire started — monitoring chat -1001234567890
Quizmaster ID: 111222333
Primary LLM:   gemini-2.5-flash
Fallback:      Serper + llama-3.3-70b-versatile
Hotkey:        F9 — paste last answer into focused window
Stop:          Ctrl+C
============================================================
```

When the quizmaster posts a question:

```
14:07:42 📨 [1/3] Quizmaster message received | Q15 from QuizMaster Dave (ID 111222333)
14:07:42          Question: Which club won the 1999-2000 La Liga?
14:07:42 🤖 [2/3] Sending to answer engine …
14:07:43    ✅ Gemini responded in 487ms → 'Real Madrid'
14:07:43 ✅ [3/3] Answer ready | Q15 → Real Madrid
14:07:43 📋 Copied to clipboard — press F9 in Telegram to paste.
```

Click into your Telegram chat and press **F9** — the answer is typed for you.

To stop: **Ctrl+C**.

---

## Troubleshooting

**`Missing required environment variable: GEMINI_API_KEY`**
Open `.env` and add your Gemini API key. See Step 1B above.

**`python` is not recognized**
You didn't tick "Add Python to PATH" during installation. Re-run the installer and tick it.

**`database is locked` error on startup**
Another ScoutWire process is running (or crashed and left the session locked). Run:
```
taskkill /F /IM python.exe
del session\user.session
```
Then run again — you'll be asked to log in once.

**F9 doesn't paste**
Make sure ScoutWire is still running in the terminal (not stopped). The hotkey only works while the process is alive.

**Gemini hits rate limits mid-quiz**
The fallback (Serper + Groq) kicks in automatically. Free tier is 10 requests/minute on Gemini — plenty for a typical quiz spread over 30+ minutes.

**`ModuleNotFoundError: No module named 'google'`**
Run `pip install -r requirements.txt` from inside the ScoutWire folder.

---

## Telegram ToS note

ScoutWire operates as a **userbot** — it uses your personal Telegram account to read messages, not a BotFather bot. It is **strictly read-only** — it never sends, forwards, or reacts to any message. You are responsible for ensuring your use complies with Telegram's Terms of Service.
