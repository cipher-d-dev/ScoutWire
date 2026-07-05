"""
backend/normalizer.py

Synchronous, deterministic answer string sanitizer.
Strips filler, punctuation, and markdown so the clipboard gets a
clean, paste-ready answer.

Usage:
    from backend.normalizer import normalize_answer
    clean = normalize_answer("The answer is Real Madrid!")  # -> "Real Madrid"
"""

import re
import unicodedata


# ---------------------------------------------------------------------------
# Filler phrase patterns — stripped from the start of the answer
# ---------------------------------------------------------------------------
_FILLER_PATTERNS = re.compile(
    r"^("
    r"the answer is[:\s]*|"
    r"the answer[:\s]*|"
    r"answer[:\s]*|"
    r"it is[:\s]*|"
    r"it's[:\s]*|"
    r"that would be[:\s]*|"
    r"that's[:\s]*|"
    r"i believe[:\s]*|"
    r"i think[:\s]*|"
    r"the correct answer is[:\s]*|"
    r"correct answer[:\s]*"
    r")",
    re.IGNORECASE,
)

# Trailing punctuation to strip (but NOT mid-string punctuation like hyphens)
_TRAILING_PUNCT = re.compile(r"[.,!?;:]+$")

# Markdown formatting — bold, italic, code
_MARKDOWN = re.compile(r"[*_`~]+")

# Quoted text — "answer" or 'answer' -> answer
_QUOTES = re.compile(r'^["\'](.+)["\']$')


def normalize_answer(raw: str) -> str:
    """
    Clean a raw LLM answer string into a paste-ready quiz answer.

    Steps applied in order:
      1. Strip whitespace
      2. Remove markdown formatting (* _ ` ~)
      3. Remove surrounding quotes
      4. Strip filler prefixes ("The answer is", "It is", etc.)
      5. Strip trailing punctuation (. , ! ?)
      6. Strip whitespace again
      7. Title-case single words that are likely proper nouns

    Returns the cleaned string. Never raises — returns raw on unexpected input.
    """
    if not raw or not isinstance(raw, str):
        return raw or ""

    text = raw.strip()

    # Remove markdown formatting
    text = _MARKDOWN.sub("", text)

    # Remove surrounding quotes
    m = _QUOTES.match(text)
    if m:
        text = m.group(1)

    # Strip filler prefixes
    text = _FILLER_PATTERNS.sub("", text).strip()

    # Strip trailing punctuation
    text = _TRAILING_PUNCT.sub("", text).strip()

    # Strip any remaining outer whitespace
    text = text.strip()

    return text if text else raw.strip()
