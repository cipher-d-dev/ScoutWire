# ScoutWire — Telegram Football Quiz Answer Bot

ScoutWire watches a Telegram quiz chat, detects questions posted by the quizmaster, asks Groq's AI for an answer, and shows it in your browser — ready to copy and paste into Telegram in under a second.

> **This tool never sends any message automatically. You always copy-paste the answer yourself.**

---

## What happens when it runs

```
Quizmaster posts a question in Telegram
    ↓
ScoutWire detects it (only quizmaster messages trigger this)
    ↓  [log] 📨 [1/3] Quizmaster message received | Q15 from Dave
    ↓  [log] 🤖 [2/3] Sending to Groq (llama-3.1-8b-instant) …
    ↓  [log]    ↳ Groq responded in 380ms
    ↓  [log] ✅ [3/3] Answer ready | Q15 → Real Madrid won La Liga in 1999-2000...
    ↓
Browser UI shows the answer — tap to copy — paste into Telegram
```

---

## Before you start — install Python

If you have never used Python before:

1. Go to [https://www.python.org/downloads/](https://www.python.org/downloads/) and download the latest **Python 3.11+** installer for Windows.
2. Run the installer. **On the first screen, tick "Add Python to PATH"** before clicking Install. This is important — without it, nothing will work.
3. Open a new Command Prompt (search "cmd" in the Start menu) and verify it worked:
   ```
   python --version
   ```
   You should see something like `Python 3.13.x`. If you get an error, you missed the PATH step — re-run the installer and tick it.

---

## Step 1 — Get your credentials

You need three things before running ScoutWire:

### A. Telegram API credentials

1. Go to [https://my.telegram.org](https://my.telegram.org) and log in with your phone number.
2. Click **"API development tools"**.
3. Create an app — the name and platform don't matter, use anything.
4. You'll see two values: **App api_id** (a number like `12345678`) and **App api_hash** (a long hex string). Copy both.

### B. Groq API key

1. Go to [https://console.groq.com](https://console.groq.com) and sign up — it's free.
2. Click **API Keys** → **Create API Key**.
3. Copy the key — it starts with `gsk_`.

### C. Your phone number

Your own Telegram phone number in international format, e.g. `+2348012345678` (no spaces).

---

## Step 2 — Set up the project

Open Command Prompt, navigate to the ScoutWire folder, and install dependencies:

```
cd C:\Users\YourName\Desktop\ScoutWire
pip install -r requirements.txt
```

> `pip` is Python's package installer — it downloads all the libraries ScoutWire needs. This only needs to be done once.

Then copy the example config file and fill it in:

```
copy .env.example .env
```

Open `.env` in Notepad (or any text editor) and fill in your values:

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+2348012345678
GROQ_API_KEY=gsk_your_groq_key_here
GROQ_MODEL=llama-3.1-8b-instant
TARGET_CHAT=-1001234567890
QUIZMASTER_USER_ID=987654321
```

You'll fill in `TARGET_CHAT` and `QUIZMASTER_USER_ID` in the next two steps.

---

## Step 3 — Find the quiz group's chat ID

Run this script to list all Telegram chats your account can see:

```
python scripts/list_chats.py
```

The first time you run any script, Telethon will ask you to log in:

```
Please enter your phone (or bot token): +2348012345678
Please enter the code you received: 12345
```

Enter your phone number, then enter the code Telegram sends you via SMS or the Telegram app. If you have 2-step verification enabled, you'll also be asked for your cloud password.

After login, you'll see a list like:

```
               ID  Name
------------------------------------------------------------
  -1001234567890  Football Quiz Championship
       987654321  John (DM)
```

Copy the ID of your quiz group (it will be a large negative number for groups). Set it as `TARGET_CHAT` in `.env`.

> Your login is saved to `session/user.session`. You won't be asked to log in again.

---

## Step 4 — Find the quizmaster's user ID

Run this to watch who sends messages in the chat:

```
python scripts/list_senders.py -1001234567890 120
```

Replace `-1001234567890` with your actual `TARGET_CHAT`. This listens for 120 seconds and prints every sender's numeric ID and name as messages arrive. Ask the quizmaster to send a message during the window.

```
Listening on chat -1001234567890 for 120s …
Ask the quizmaster to send a message now.

     Numeric ID  Display name
--------------------------------------------------
      111222333  QuizMaster Dave
      444555666  Regular Player
```

Copy the quizmaster's numeric ID and set it as `QUIZMASTER_USER_ID` in `.env`.

> We use the numeric ID instead of @username because usernames can be changed, which would silently break the filter. Numeric IDs are permanent.

---

## Step 5 — Run ScoutWire

```
python -m backend.main
```

You'll see startup logs in the terminal:

```
03:05:11 [INFO] uvicorn — Started server process
03:05:11 [INFO] uvicorn — Waiting for application startup.
03:05:13 [INFO] Telegram: logged in. Monitoring chat -1001234567890
```

Open your browser to:

```
http://localhost:8000
```

Click **"Start Listening"** in the browser. Now when the quizmaster posts a question, you'll see this in the terminal:

```
03:07:42 [INFO] 📨 [1/3] Quizmaster message received | Q15 from QuizMaster Dave (ID 111222333)
03:07:42 [INFO]         Question: Which club won the 1999-2000 La Liga?
03:07:42 [INFO] 🤖 [2/3] Sending to Groq (llama-3.1-8b-instant) …
03:07:42 [INFO]    ↳ Groq responded in 380ms
03:07:42 [INFO] ✅ [3/3] Answer ready | Q15 → Real Madrid won the 1999-2000 La Liga title.
```

And the answer appears in your browser immediately — tap to copy, paste into Telegram.

To stop the bot, press **Ctrl+C** in the terminal.

---

## Troubleshooting

**`python` is not recognized as a command**
You didn't tick "Add Python to PATH" during installation. Re-run the Python installer, choose "Modify", and tick the PATH option.

**`pip install` gives an error about permissions**
Try: `pip install --user -r requirements.txt`

**`Missing required environment variable: X`**
Open `.env` and make sure every variable has a value. No quotes needed around values.

**`SessionPasswordNeededError` during login**
Your Telegram account has 2-step verification. Enter your cloud password when prompted.

**The browser shows "Reconnecting…" and never connects**
The backend isn't running. Make sure `python -m backend.main` is running in the terminal and there are no errors printed.

**Answers are coming from the wrong person**
Double-check `QUIZMASTER_USER_ID` in `.env`. Run `scripts/list_senders.py` again and confirm the numeric ID.

**`ModuleNotFoundError: No module named 'telethon'`**
Run `pip install -r requirements.txt` from inside the ScoutWire folder.

---

## Telegram ToS note

ScoutWire operates as a **userbot** — it uses your personal Telegram account to read messages, not a BotFather bot.

It stays within acceptable use because:
- It is **strictly read-only** — it never sends, forwards, or reacts to any message.
- All responses are **manually copy-pasted** by you.
- It runs **locally on your machine** only.

You are responsible for ensuring your use complies with Telegram's Terms of Service.
