"""Integration fixtures: Settings pointing at a temporary valid content file, and a JSON log collector."""

from __future__ import annotations

import json
import logging

import pytest

from ai_live.core.logging import JsonFormatter
from fixtures.content_builder import valid_docx


@pytest.fixture
def content_path(tmp_path):
    path = tmp_path / "valid.docx"
    path.write_bytes(valid_docx())
    return path


@pytest.fixture
def app_settings(settings, content_path):
    return settings.model_copy(update={"product_data_path": content_path})


@pytest.fixture
def json_log_lines():
    """Every `ai_live.*` log record, formatted by the real JSON formatter and parsed back.

    App startup (`configure_logging`) replaces the `ai_live` handlers, so with a TestClient request this fixture
    after the client fixture.
    """
    lines: list[dict] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(json.loads(self.format(record)))

    handler = Collect()
    handler.setFormatter(JsonFormatter("test-session"))
    root = logging.getLogger("ai_live")
    saved_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(saved_level)
