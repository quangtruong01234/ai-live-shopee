"""T013: Settings (FR-015, FR-021, research R3). Giá trị mặc định đối chiếu với `.env.example` (nguồn chuẩn)."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from ai_live.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def parse_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, rest = line.partition("=")
        values[key.strip()] = rest.split("#", 1)[0].strip()
    return values


def test_every_setting_exists_in_env_example_with_same_default():
    example = parse_env_example()
    defaults = Settings(_env_file=None)
    for name in Settings.model_fields:
        key = name.upper()
        assert key in example, f"{key} chưa có trong .env.example"
        expected = example[key]
        actual = getattr(defaults, name)
        if isinstance(actual, SecretStr) or actual is None:
            assert expected == "", f"{key}: secret phải để trống trong .env.example"
            continue
        coerced = Settings(_env_file=None, **{name: expected}) if expected != "" else defaults
        assert getattr(coerced, name) == actual, f"{key}: mặc định {actual!r} khác .env.example {expected!r}"


def test_feature_001_settings_present():
    required = {
        "app_env",
        "reply_engine",
        "gemini_api_key",
        "llm_model",
        "llm_thinking_level",
        "llm_max_tokens",
        "llm_timeout_s",
        "tts_provider",
        "tts_sample_rate",
        "tts_timeout_s",
        "fake_tts_delay_ms",
        "avatar_mode",
        "avatar_static_image",
        "ai_label_text",
        "ai_label_position",
        "renderer_ack_timeout_s",
        "comment_max_age_s",
        "comment_queue_max",
        "comment_dedup_window_s",
        "comment_max_chars",
        "profanity_list_path",
        "priority_rules_path",
        "product_data_path",
        "content_max_bytes",
        "session_data_dir",
    }
    assert required <= set(Settings.model_fields)


def test_reads_environment(monkeypatch):
    monkeypatch.setenv("COMMENT_MAX_AGE_S", "10")
    monkeypatch.setenv("REPLY_ENGINE", "fake")
    s = Settings(_env_file=None)
    assert s.comment_max_age_s == 10
    assert s.reply_engine == "fake"


@pytest.mark.parametrize(
    ("field", "value"),
    [("comment_queue_max", "nhiều"), ("llm_timeout_s", "abc"), ("reply_engine", "claude"), ("app_env", "staging")],
)
def test_invalid_value_fails_at_init(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize("label", ["", "   "])
def test_empty_ai_label_fails(label):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_label_text=label)


def test_secret_not_in_repr_or_str():
    secret = "AIza" + "Q" * 35
    s = Settings(_env_file=None, gemini_api_key=secret)
    assert secret not in repr(s)
    assert secret not in str(s)
    assert s.gemini_api_key is not None
    assert s.gemini_api_key.get_secret_value() == secret


def test_fixture_settings_are_offline(settings, tmp_path):
    assert settings.reply_engine == "fake"
    assert settings.tts_provider == "fake"
    assert settings.avatar_mode == "static"
    assert settings.gemini_api_key is None
    assert Path(settings.session_data_dir).is_relative_to(tmp_path)
