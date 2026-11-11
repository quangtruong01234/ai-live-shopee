"""Turn a written sentence into what a Southern Vietnamese host would say (003 data-model §3, FR-006 to FR-008).

Voice sources read "259.000đ" or "15%" badly or not at all, so every sentence is rewritten into words before it is
sent. The subtitle keeps the written form (FR-009); only the voice source sees this text. Pure functions, standard
library only (constitution VII), and the rules run in the fixed order of data-model §3.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path

_DIGITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")
_GROUPS = ("tỷ", "triệu", "ngàn", "")
# Above this a number is more likely a code than an amount, and "nghìn tỷ" is not how a host reads it.
_MAX_READ = 999_999_999_999

# Letters as a Southern speaker spells them in a code; the first two TODOs of data-model §3 cover the choices.
_LETTERS = {
    "A": "a", "B": "bê", "C": "xê", "D": "đê", "Đ": "đê", "E": "e", "F": "ép", "G": "giê", "H": "hát", "I": "i",
    "J": "giây", "K": "ca", "L": "eo", "M": "em", "N": "en", "O": "o", "P": "pê", "Q": "qui", "R": "e rờ",
    "S": "ét", "T": "tê", "U": "u", "V": "vê", "W": "vê kép", "X": "ích", "Y": "i dài", "Z": "dét",
}  # fmt: skip
_SIZES = {"S": "ét", "M": "em", "L": "eo", "XL": "ích eo", "XXL": "hai ích eo"}
_UNITS = {"ml": "mi li lít", "l": "lít", "g": "gam", "kg": "ki lô gam", "cm": "xen ti mét", "m": "mét"}

# A number as written: digits with optional "." or "," groups ("1.250.000", "3,75", "1.5").
_NUM = r"\d+(?:[.,]\d+)*"
# Not glued to a word or to another number, so "GIAM50" and the tail of "1.5" are left to their own rules.
_START = r"(?<![\w.,])"
_CURRENCY = r"(?:đồng|vnđ|vnd|đ|₫)"
_ANY_UNIT = rf"(?:\s?(?:{_CURRENCY}|%|ml|kg|cm|k|g|l|m))?"

_LINK = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMOJI_CATEGORIES = {"So", "Sk", "Cs", "Co", "Cn", "Cf", "Me"}
_EMOJI_EXTRA = {"\N{VARIATION SELECTOR-15}", "\N{VARIATION SELECTOR-16}"}
_SIZE = re.compile(r"\bsize\s+(XXL|XL|S|M|L)(?!\w)", re.IGNORECASE)
_RANGE = re.compile(rf"{_START}({_NUM}{_ANY_UNIT})\s*[–\-—~]\s*({_NUM}{_ANY_UNIT})(?!\w)", re.IGNORECASE)
_ENDS_WITH_TU = re.compile(r"(?<!\w)từ\s*$", re.IGNORECASE)
_PRICE = re.compile(rf"{_START}({_NUM})\s?{_CURRENCY}(?!\w)", re.IGNORECASE)
_THOUSAND = re.compile(rf"{_START}({_NUM})k(?!\w)", re.IGNORECASE)
_PERCENT = re.compile(rf"{_START}({_NUM})\s?%")
_UNIT = re.compile(rf"{_START}({_NUM})\s?(ml|kg|cm|g|l|m)(?!\w)", re.IGNORECASE)
_CODE = re.compile(r"(?<!\w)(?=\w*\d)(?=\w*[^\W\d_])\w+")
_DIGIT_RUN = re.compile(r"(?<![\w.,])\d+(?![\w]|[.,]\d)")
_NUMBER = re.compile(rf"{_START}{_NUM}")
_THOUSANDS_SEPARATED = re.compile(r"\d{1,3}(?:\.\d{3})+")


def load_abbreviations(path: Path) -> dict[str, str]:
    """Read the abbreviation table (`TTS_ABBREVIATIONS_PATH`); a missing file raises OSError, a bad one ValueError."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError('bảng viết tắt phải là một đối tượng JSON dạng {"viết tắt": "cách đọc"}')
    seen: set[str] = set()
    for key, value in data.items():
        if not key.strip():
            raise ValueError("bảng viết tắt có khóa rỗng")
        if key.casefold() in seen:
            raise ValueError(f"bảng viết tắt có khóa trùng (không phân biệt hoa thường): {key!r}")
        seen.add(key.casefold())
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"cách đọc của {key!r} phải là chữ, không được rỗng")
        # The value is read as is; a digit in it would bypass the number rules.
        if any(ch.isdigit() for ch in value):
            raise ValueError(f"cách đọc của {key!r} không được chứa chữ số: {value!r}")
    return data


def normalize_for_speech(text: str, abbreviations: Mapping[str, str] | None = None) -> str:
    """The sentence in words: only letters, spaces and `, . ? !` are left; empty if nothing is left to say."""
    text = unicodedata.normalize("NFC", text)
    text = _drop_links_and_emoji(text)  # 1
    text = _expand_abbreviations(text, abbreviations or {})  # 2
    text = _SIZE.sub(lambda m: "sai " + _SIZES[m.group(1).upper()], text)  # 3
    text = _RANGE.sub(_range, text)  # 4
    text = _PRICE.sub(lambda m: f"{read_number(m.group(1))} đồng", text)  # 5
    text = _THOUSAND.sub(lambda m: f"{read_number(m.group(1))} ngàn", text)  # 6
    text = _PERCENT.sub(lambda m: f"{read_number(m.group(1))} phần trăm", text)  # 7
    text = _UNIT.sub(lambda m: f"{read_number(m.group(1))} {_UNITS[m.group(2).lower()]}", text)  # 8
    text = _CODE.sub(lambda m: _spell(m.group(0)), text)  # 9
    text = _DIGIT_RUN.sub(_digit_run, text)  # 9
    text = _NUMBER.sub(lambda m: read_number(m.group(0)), text)  # 10
    return _clean(text)


def read_number(written: str) -> str:
    """A written number in words: "1.250.000", "3,75" (phẩy), "1.5" (chấm) or plain digits."""
    whole, *fractions = written.split(",")
    if _THOUSANDS_SEPARATED.fullmatch(whole):
        words = _read_digits_as_number(whole.replace(".", ""))
    else:
        words = " chấm ".join(_read_digits_as_number(part) for part in whole.split("."))
    for fraction in fractions:
        # "0,05" is "không phẩy không năm": a leading zero would vanish if the part were read as a number.
        part = _spell_digits(fraction) if fraction.startswith("0") else _read_digits_as_number(fraction)
        words += " phẩy " + part
    return words


def _read_digits_as_number(digits: str) -> str:
    value = int(digits)
    return _read_int(value) if value <= _MAX_READ else _spell_digits(digits)


def _read_int(value: int) -> str:
    if value == 0:
        return _DIGITS[0]
    groups = [(value // 10**9) % 1000, (value // 10**6) % 1000, (value // 1000) % 1000, value % 1000]
    words: list[str] = []
    for group, name in zip(groups, _GROUPS, strict=True):
        if group == 0:
            continue  # "một triệu không trăm lẻ năm": a group of only zeros is not read at all
        words += _read_hundreds(group, after_higher_group=bool(words))
        if name:
            words.append(name)
    return " ".join(words)


def _read_hundreds(value: int, *, after_higher_group: bool) -> list[str]:
    hundreds, tens, units = value // 100, value // 10 % 10, value % 10
    words: list[str] = []
    if hundreds or after_higher_group:
        words += [_DIGITS[hundreds], "trăm"]
    if tens == 0:
        if units:
            words += ["lẻ", _DIGITS[units]] if words else [_DIGITS[units]]
    elif tens == 1:
        words.append("mười")
        if units:
            words.append("lăm" if units == 5 else _DIGITS[units])
    else:
        words += [_DIGITS[tens], "mươi"]
        if units:
            words.append({1: "mốt", 5: "lăm"}.get(units, _DIGITS[units]))
    return words


def _spell_digits(digits: str) -> str:
    return " ".join(_DIGITS[int(d)] for d in digits)


def _drop_links_and_emoji(text: str) -> str:
    text = _LINK.sub(" ", text)
    return "".join(" " if ch in _EMOJI_EXTRA or unicodedata.category(ch) in _EMOJI_CATEGORIES else ch for ch in text)


def _expand_abbreviations(text: str, abbreviations: Mapping[str, str]) -> str:
    if not abbreviations:
        return text
    by_key = {key.casefold(): value for key, value in abbreviations.items()}
    # Longest first, so a key that starts another ("KM" vs "KMS") never shadows it.
    keys = sorted(abbreviations, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in keys) + r")(?!\w)", re.IGNORECASE)
    return pattern.sub(lambda m: by_key[m.group(0).casefold()], text)


def _range(match: re.Match[str]) -> str:
    before = match.string[: match.start()]
    prefix = "" if _ENDS_WITH_TU.search(before) else "từ "
    return f"{prefix}{match.group(1)} đến {match.group(2)}"


def _spell(token: str) -> str:
    """A code like "GIAM50K", letter by letter and digit by digit."""
    words = []
    for ch in token:
        if ch.isdigit():
            words.append(_DIGITS[int(ch)])
        else:
            words.append(_LETTERS.get(ch.upper(), ch))
    return " ".join(words)


def _digit_run(match: re.Match[str]) -> str:
    digits = match.group(0)
    # A phone number or an order code: read digit by digit, as nobody says it as one amount.
    if (digits.startswith("0") and len(digits) >= 4) or len(digits) >= 9:
        return _spell_digits(digits)
    return digits


def _clean(text: str) -> str:
    text = text.replace(":", ",").replace(";", ",").replace("…", ".")
    # Rules 9 and 10 read every number; a stray digit here (".5") is still said rather than dropped.
    text = re.sub(r"\d", lambda m: f" {_DIGITS[int(m.group(0))]} ", text)
    text = "".join(ch if ch.isalpha() or ch in " ,.?!" else " " for ch in text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r" ([,.?!])", r"\1", text)
    text = re.sub(r",(?:\s*,)+", ",", text)
    text = text.strip(" ,")
    return text if any(ch.isalpha() for ch in text) else ""
