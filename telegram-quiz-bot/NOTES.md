# Phase 9 — Soak Test Notes

Fill this in during / after a real quiz session.

---

## Session details

| Field | Value |
|---|---|
| Date | |
| Session duration | |
| Questions in round | |
| Start/stop toggles | |
| Browser used | |
| Phone or desktop? | |

---

## Quizmaster filter accuracy

> Expected: 100% — it's a direct ID match, not a heuristic.

| Check | Result | Notes |
|---|---|---|
| All quizmaster questions triggered an answer | ☐ Yes / ☐ No | |
| Any non-quizmaster messages incorrectly triggered | ☐ No / ☐ Yes → describe below | |
| Quizmaster posted any banter/non-question that got treated as a question | ☐ No / ☐ Yes → describe below | |

**False positives (if any):**


**False negatives (if any):**


---

## Latency

> Target: answer visible on screen within ~700ms of quizmaster sending.

| Observation | Value |
|---|---|
| Typical end-to-end latency (subjective) | |
| Slowest single answer (if notable) | |
| Any answers that felt noticeably slow | |

---

## Rate limiting

| Check | Result |
|---|---|
| Any 429 rate-limit responses from Groq? | ☐ No / ☐ Yes |
| If yes — did the amber "RATE LIMITED" badge appear? | ☐ Yes / ☐ No |
| If yes — did a manual retry work? | ☐ Yes / ☐ No / ☐ N/A |

---

## Stability

| Check | Result | Notes |
|---|---|---|
| Any unhandled exceptions / crashes | ☐ No / ☐ Yes → describe | |
| WebSocket dropped and auto-reconnected | ☐ No / ☐ Yes — recovered fine / ☐ Yes — needed manual reload | |
| Telegram reconnect survived without crash | ☐ Not tested / ☐ Yes | |
| Process survived full session without restart | ☐ Yes / ☐ No | |

---

## Answer quality (spot check)

Pick 3-5 questions and note whether the answer was correct, hedged, or wrong.

| Q# | Question (brief) | Answer quality | Notes |
|---|---|---|---|
| | | ☐ Correct / ☐ Hedged / ☐ Wrong | |
| | | ☐ Correct / ☐ Hedged / ☐ Wrong | |
| | | ☐ Correct / ☐ Hedged / ☐ Wrong | |
| | | ☐ Correct / ☐ Hedged / ☐ Wrong | |
| | | ☐ Correct / ☐ Hedged / ☐ Wrong | |

---

## UI / UX notes

- Copy-to-clipboard worked reliably? ☐ Yes / ☐ No
- Anything confusing or slow about the UI?
- History scroll worked correctly?
- Any layout issues on mobile?

---

## Issues found / tuning needed

List anything that needs fixing before calling the bot production-ready:

1.
2.
3.

---

## Overall verdict

☐ Ready to use as-is
☐ Minor fixes needed (listed above) — usable in the meantime
☐ Blocking issue found — do not use until fixed
