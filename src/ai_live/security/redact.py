"""Mask secrets before anything is logged or returned to a client (FR-021; secrets live only in `.env`)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import SecretStr

MASK = "***"

# Key names that hold a secret: GEMINI_API_KEY, rtmp_stream_key, *_TOKEN, client_secret...
_SECRET_NAME = re.compile(r"(?:^|_)(?:key|token|secret)$", re.IGNORECASE)
# Google keys start with "AIza" and are 39 characters long.
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
# Provider keys that an error body may echo back (feature 008, research R12): Groq "gsk_…", the freellmapi unified key
# "freellmapi-…", OpenAI-style "sk-…" (also "sk-proj-…"). The look-behind keeps words such as "task-runner" intact and
# the minimum length keeps names such as "freellmapi-server" intact.
_PROVIDER_KEYS = (
    re.compile(r"(?<![A-Za-z0-9_-])gsk_[A-Za-z0-9]{16,}"),
    re.compile(r"(?<![A-Za-z0-9_-])freellmapi-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}"),
)
# "KEY_NAME=value" or "api_key: value" leaking into an error message.
_ASSIGNMENT = re.compile(r"\b(\w*(?:key|token|secret))(\s*[=:]\s*)([^\s,;'\"]+)", re.IGNORECASE)
# Shorter values are not masked by value: masking "ab" everywhere would wreck the text and no real key is that short.
_MIN_SECRET_VALUE_LEN = 4


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(name))


def redact_text(text: str) -> str:
    text = _GOOGLE_KEY.sub(MASK, text)
    for pattern in _PROVIDER_KEYS:
        text = pattern.sub(MASK, text)
    return _ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


def redact_secret_values(text: str, secrets: Iterable[str | SecretStr | None]) -> str:
    """Mask every occurrence of the given secret values, then apply the patterns of `redact_text`.

    Catches keys of any shape (research R12): a provider may echo the key it received in its error body. `None`,
    empty and very short values are ignored. Longer values go first so a key containing another key is masked whole.
    """
    values = {s.get_secret_value() if isinstance(s, SecretStr) else s for s in secrets}
    for value in sorted((v for v in values if v and len(v) >= _MIN_SECRET_VALUE_LEN), key=len, reverse=True):
        text = text.replace(value, MASK)
    return redact_text(text)


def redact(value: Any) -> Any:
    """Mask secrets in strings and nested mappings / lists / tuples. Returns a copy; the original is never changed."""
    if isinstance(value, SecretStr):
        return MASK
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            k: (MASK if isinstance(k, str) and is_secret_name(k) and v not in (None, "") else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(redact(v) for v in value)
    return value
