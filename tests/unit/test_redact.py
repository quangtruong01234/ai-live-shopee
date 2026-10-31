"""T009: che secret trước khi ghi log (FR-021)."""

import json
import logging

from ai_live.security.redact import MASK, redact, redact_text

GOOGLE_KEY = "AIza" + "S" * 35


def test_secret_keys_in_mapping_are_masked():
    data = {
        "GEMINI_API_KEY": "abc123",
        "rtmp_stream_key": "live_xyz",
        "SOME_TOKEN": "t0k",
        "client_secret": "s3cr3t",
        "author": "Lan",
    }
    out = redact(data)
    assert out["GEMINI_API_KEY"] == MASK
    assert out["rtmp_stream_key"] == MASK
    assert out["SOME_TOKEN"] == MASK
    assert out["client_secret"] == MASK
    assert out["author"] == "Lan"


def test_google_key_pattern_in_text_is_masked():
    text = f"gọi API lỗi với key={GOOGLE_KEY} rồi thử lại"
    out = redact_text(text)
    assert GOOGLE_KEY not in out
    assert MASK in out


def test_key_assignment_in_text_is_masked():
    out = redact_text("cấu hình GEMINI_API_KEY=abc123 sai")
    assert "abc123" not in out


def test_plain_text_kept():
    text = "Kem chống nắng X giá 250.000đ, bạn Lan nhé"
    assert redact_text(text) == text
    assert redact({"text": text}) == {"text": text}


def test_nested_structures_are_masked():
    out = redact({"cfg": {"api_key": "x"}, "items": [GOOGLE_KEY, "ok"]})
    assert out["cfg"]["api_key"] == MASK
    assert out["items"] == [MASK, "ok"]


def test_json_formatter_redacts_every_record():
    from ai_live.core.logging import JsonFormatter

    formatter = JsonFormatter(session_id="20261030-100000")
    record = logging.LogRecord("ai_live.test", logging.ERROR, __file__, 1, "llm_error", None, None)
    record.fields = {"message": f"401 key {GOOGLE_KEY}", "GEMINI_API_KEY": "abc123"}
    line = formatter.format(record)
    assert GOOGLE_KEY not in line
    assert "abc123" not in line
    parsed = json.loads(line)
    assert parsed["event"] == "llm_error"
    assert parsed["session_id"] == "20261030-100000"
    assert parsed["level"] == "ERROR"
    assert {"ts", "logger"} <= parsed.keys()
