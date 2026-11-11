"""T009 (001) and T009 (008): mask secrets before anything is logged (FR-021, research R12, SC-008)."""

import json
import logging

import pytest
from pydantic import SecretStr

from ai_live.security import redact as redact_module
from ai_live.security.redact import MASK, redact, redact_text

GOOGLE_KEY = "AIza" + "S" * 35
GROQ_KEY = "gsk_" + "Ab3" * 17
FREELLMAPI_KEY = "freellmapi-" + "c0ffee12" * 4
OPENAI_KEY = "sk-proj-" + "Zx9_" * 10


def redact_secret_values(text, secrets):
    # Looked up at call time so a missing function fails each test, not the whole module import.
    return redact_module.redact_secret_values(text, secrets)


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


# ---------- Feature 008: provider key patterns and masking by value (research R12) ----------


@pytest.mark.parametrize("key", [GROQ_KEY, FREELLMAPI_KEY, OPENAI_KEY, "sk-" + "a" * 48])
def test_provider_key_patterns_are_masked(key):
    # A provider may echo the key back in an error body, with no "key=" in front of it.
    text = f'{{"error": {{"message": "Invalid API Key {key} provided"}}}}'
    out = redact_text(text)
    assert key not in out
    assert MASK in out
    assert out.startswith('{"error": {"message": "Invalid API Key ')


@pytest.mark.parametrize("key", [GROQ_KEY, FREELLMAPI_KEY, OPENAI_KEY])
def test_provider_key_patterns_are_masked_in_mappings(key):
    out = redact({"detail": f"401 {key}", "items": [key]})
    assert key not in json.dumps(out)


@pytest.mark.parametrize(
    "text",
    [
        "Dịch vụ freellmapi-server chưa chạy ở http://127.0.0.1:3001/v1",
        "task-runner và desk-lamp không phải key",
        "model qwen/qwen3.8-27b, gpt-oss-120b, gemma-sea-lion-v4-27b",
        "LLM_CHAIN mục 1 (sealion): kiểm model trả status 500",
        "Retry after 60 s; platform groq, X-Routed-Via: cloudflare/gemma-sea-lion-v4-27b",
    ],
)
def test_text_without_keys_is_unchanged(text):
    assert redact_text(text) == text
    assert redact_secret_values(text, [GROQ_KEY, SecretStr(FREELLMAPI_KEY), None, ""]) == text


def test_exact_secret_values_are_masked_even_without_a_pattern():
    odd_key = "iteracompute.9f8e7d6c5b4a3210"
    other = SecretStr("Q7w!e9R#t2Y$u4")
    text = f"401 Unauthorized: key {odd_key} rejected; retried with {other.get_secret_value()}"
    out = redact_secret_values(text, [odd_key, other])
    assert odd_key not in out
    assert other.get_secret_value() not in out
    assert out == f"401 Unauthorized: key {MASK} rejected; retried with {MASK}"


def test_secret_values_masked_every_occurrence_and_patterns_still_apply():
    odd_key = "plainvalue-without-prefix-123"
    text = f"{odd_key} / {odd_key} / {GROQ_KEY} / GEMINI_API_KEY=abc123"
    out = redact_secret_values(text, [odd_key])
    for leaked in (odd_key, GROQ_KEY, "abc123"):
        assert leaked not in out


def test_overlapping_secret_values_mask_the_longer_first():
    short = "abcd1234"
    long = short + "efgh5678"
    out = redact_secret_values(f"k={long}!", [short, long])
    assert short not in out
    assert "efgh5678" not in out


def test_empty_and_missing_secret_values_are_ignored():
    text = "không có key nào ở đây"
    assert redact_secret_values(text, []) == text
    assert redact_secret_values(text, [None, "", SecretStr("")]) == text
