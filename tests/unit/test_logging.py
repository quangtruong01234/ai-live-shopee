"""Log JSON phải ghi được tiếng Việt kể cả khi stdout không phải UTF-8 (Windows chuyển hướng ra file dùng cp1252)."""

from __future__ import annotations

import io
import json
import logging
import sys

import pytest

from ai_live.core.logging import configure_logging, log_event


def test_vietnamese_log_survives_non_utf8_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw, encoding="cp1252", write_through=True)
    monkeypatch.setattr(sys, "stdout", stdout)
    logger = logging.getLogger("ai_live.test_logging")
    root = logging.getLogger("ai_live")
    saved = (root.handlers[:], root.level, root.propagate)
    errors: list[str] = []
    monkeypatch.setattr(logging, "raiseExceptions", True)
    monkeypatch.setattr(logging.Handler, "handleError", lambda self, record: errors.append(record.getMessage()))
    try:
        configure_logging("INFO", "s1")
        log_event(logger, "turn_error", logging.WARNING, message="Renderer lỗi: chưa mở màn hình host")
        stdout.flush()
    finally:
        root.handlers[:], root.level, root.propagate = saved

    assert errors == []
    line = json.loads(raw.getvalue().decode("utf-8").strip())
    assert line["message"] == "Renderer lỗi: chưa mở màn hình host"
