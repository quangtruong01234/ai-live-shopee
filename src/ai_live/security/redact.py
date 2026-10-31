"""Che secret trước khi ghi log hay trả lỗi ra ngoài (FR-021, Hiến pháp: secret chỉ nằm trong `.env`)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

MASK = "***"

# Tên khóa chứa secret: GEMINI_API_KEY, rtmp_stream_key, *_TOKEN, client_secret...
_SECRET_NAME = re.compile(r"(?:^|_)(?:key|token|secret)$", re.IGNORECASE)
# Key Google bắt đầu bằng "AIza" và dài 39 ký tự.
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
# Dạng "TEN_KEY=giá trị" hoặc "api_key: giá trị" lọt vào thông báo lỗi.
_ASSIGNMENT = re.compile(r"\b(\w*(?:key|token|secret))(\s*[=:]\s*)([^\s,;'\"]+)", re.IGNORECASE)


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(name))


def redact_text(text: str) -> str:
    text = _GOOGLE_KEY.sub(MASK, text)
    return _ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


def redact(value: Any) -> Any:
    """Che secret trong chuỗi, mapping, list/tuple lồng nhau. Trả bản sao, không sửa đối tượng gốc."""
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
