"""Strip formatting symbols from a line before it is spoken (004 research R9, contracts/adapters.md §3; FR-009).

Formatting is a form error, not false information, so it is cleaned instead of blocked: losing a correct sentence
because of one asterisk would be worse. The cleaned text is both what TTS reads and the subtitle (ADR-031), and it
is what the guard checks. Runs on both the script path and the comment path.
"""

from __future__ import annotations

import re
import unicodedata

# Invisible emoji glue: variation selectors, zero-width joiner, combining keycap. Removed with the emoji around them.
_EMOJI_GLUE = {"︎", "️", "‍", "⃣"}
# Skin tone modifiers are category `Sk`, not `So`, but are only ever part of an emoji.
_SKIN_TONES = range(0x1F3FB, 0x1F400)

# Markers that are never spoken. Removing every occurrence (not only matched pairs) keeps the function idempotent
# and also drops an unpaired `**` left by a token stream that was cut.
_MARKERS = re.compile(r"\*+|__+|`+|#+")
# List bullets and numbering at the start of a line. A number needs a space after `1.` / `1)`, so a price that
# opens a sentence ("1.250.000đ là giá ...") is kept.
_LEADING = re.compile(r"^[ \t]*(?:(?:[-–—•·▪●◦]+|\d{1,2}[.)](?=\s))[ \t]*)+", re.MULTILINE)
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,!?;:…])")
_WHITESPACE = re.compile(r"\s+")


def _is_emoji(ch: str) -> bool:
    return ch in _EMOJI_GLUE or unicodedata.category(ch) == "So" or ord(ch) in _SKIN_TONES


def clean_spoken(text: str) -> str:
    """Pure and idempotent: `clean_spoken(clean_spoken(x)) == clean_spoken(x)`.

    Keeps Vietnamese diacritics, numbers with their dots and commas (`1.250.000`), `%` and ordinary punctuation.
    Emoji go first, so a bullet hidden behind an emoji ("😀 - Kem") is at the line start when bullets are stripped.
    """
    out = unicodedata.normalize("NFC", text)
    out = "".join(" " if _is_emoji(ch) else ch for ch in out)
    out = _MARKERS.sub("", out)
    out = _LEADING.sub("", out)
    out = _WHITESPACE.sub(" ", out).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", out)
