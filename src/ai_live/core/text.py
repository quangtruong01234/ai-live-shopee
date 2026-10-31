"""Vietnamese text normalization, link/phrase matching and money extraction (research R8, R9).

Shared by the comment filter, the output guard, the content loader and the grader, so all of them match by one rule set.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_WHITESPACE = re.compile(r"\s+")

# URLs, `www.` and bare domains. Reading a link aloud on live advertises for someone else (risk Q5).
_LINK = re.compile(r"https?://|www\.|\.(?:com|net|org|vn|info|xyz|io|me|shop|store|link)\b", re.IGNORECASE)

# Numbers with thousand groups (1.250.000 / 1,250,000), decimals (2,5) or plain digits (250000).
_NUMBER = r"\d{1,3}(?:[.,]\d{3})+(?![.,]?\d)|\d+(?:[.,]\d+)?"

# Money units in match form (diacritics removed, đ -> d), with their VND multiplier.
_MONEY_UNITS: dict[str, int] = {
    "trieu": 1_000_000,
    "tr": 1_000_000,
    "nghin": 1_000,
    "ngan": 1_000,
    "k": 1_000,
    "vnd": 1,
    "d": 1,
    "₫": 1,
}
_UNIT_PATTERN = "|".join(sorted((re.escape(u) for u in _MONEY_UNITS), key=len, reverse=True))
_AMOUNT = re.compile(rf"(?<![\w.,])({_NUMBER})\s*(?:({_UNIT_PATTERN})(?![a-z0-9]))?")

# A measurement unit after a large number means it is not money ("1.000 ml").
_OTHER_UNIT = re.compile(r"\s*(?:ml|l|lit|g|gr|gram|kg|mg|cm|mm|m|%|vien|goi|hop|chai|tuyp|mieng|cai)(?![a-z0-9])")


def normalize_text(text: str, max_chars: int | None = None) -> str:
    """NFC, collapse all whitespace to one space, strip both ends, cut to at most `max_chars` characters."""
    out = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()
    if max_chars is not None and len(out) > max_chars:
        out = out[:max_chars].rstrip()
    return out


def strip_diacritics(text: str) -> str:
    """Remove Vietnamese diacritics; `đ`/`Đ` is not a combining mark so it is replaced separately."""
    decomposed = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return no_marks.replace("đ", "d").replace("Đ", "D")


def match_form(text: str) -> str:
    """Match form: normalized, lowercase, no diacritics. Viewers often skip diacritics, so all matching uses it."""
    return strip_diacritics(normalize_text(text)).lower()


def contains_link(text: str) -> bool:
    return bool(_LINK.search(text))


def phrase_pattern(phrases: Iterable[str]) -> re.Pattern[str] | None:
    """One regex matching any phrase as whole words on the match form; `None` when there is nothing to match."""
    forms = sorted({f for p in phrases if (f := match_form(p))}, key=len, reverse=True)
    if not forms:
        return None
    return re.compile(rf"(?<!\w)(?:{'|'.join(re.escape(f) for f in forms)})(?!\w)")


def contains_phrase(text: str, pattern: re.Pattern[str] | None) -> bool:
    """`pattern` comes from `phrase_pattern`; matching runs on the match form so "đụ má" hits "du ma"."""
    return pattern is not None and pattern.search(match_form(text)) is not None


def _parse_number(raw: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    return float(raw.replace(",", "."))


def extract_amounts(text: str) -> list[int]:
    """Extract money amounts (VND) in order of appearance.

    A number is money when it has a money unit (`đ`, `₫`, `vnd`, `k`, `nghìn`, `ngàn`, `triệu`), or is >= 1,000
    without another measurement unit. "đồng" is not a unit because its match form equals "dòng"
    ("2 dòng kem" would become 2 VND).
    """
    form = match_form(text)
    amounts: list[int] = []
    for m in _AMOUNT.finditer(form):
        raw, unit = m.group(1), m.group(2)
        value = _parse_number(raw)
        if unit:
            amounts.append(round(value * _MONEY_UNITS[unit]))
        elif value >= 1000 and value.is_integer() and not _OTHER_UNIT.match(form, m.end(1)):
            amounts.append(int(value))
    return amounts


def extract_numbers(text: str) -> list[int]:
    """Every integer in the text (thousand groups understood), plus the converted money amounts.

    Used to build the set of known numbers for the guard.
    """
    form = match_form(text)
    numbers = [int(v) for raw in re.findall(_NUMBER, form) if (v := _parse_number(raw)).is_integer()]
    return numbers + extract_amounts(text)
