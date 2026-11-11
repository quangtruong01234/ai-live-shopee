"""T013 (001), T006 (004) and T004 (008): Settings. Defaults are checked against `.env.example`, the reference list."""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from ai_live.core import config as config_module
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
        assert key in example, f"{key} missing from .env.example"
        expected = example[key]
        actual = getattr(defaults, name)
        if isinstance(actual, SecretStr) or actual is None:
            assert expected == "", f"{key}: a secret must be empty in .env.example"
            continue
        coerced = Settings(_env_file=None, **{name: expected}) if expected != "" else defaults
        assert getattr(coerced, name) == actual, f"{key}: default {actual!r} differs from .env.example {expected!r}"


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


SCRIPT_DEFAULTS = {
    "script_segment_min_sentences": 3,
    "script_segment_max_sentences": 6,
    "script_primary_share": 0.5,
    "script_fallback_after": 3,
    "script_llm_timeout_s": 10,
    "script_retry_timeout_s": 4,
    "script_history_sentences": 12,
    "script_max_tokens": 600,
    "platform_phrases_path": Path("data/rules/platform_phrases.txt"),
}


def test_feature_004_settings_defaults_match_env_example():
    example = parse_env_example()
    defaults = Settings(_env_file=None)
    for name, expected in SCRIPT_DEFAULTS.items():
        assert name.upper() in example, f"{name.upper()} missing from .env.example"
        assert getattr(defaults, name) == expected, name
        from_example = Settings(_env_file=None, **{name: example[name.upper()]})
        assert getattr(from_example, name) == expected, name


def test_segment_max_below_min_fails():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, script_segment_min_sentences=5, script_segment_max_sentences=4)
    s = Settings(_env_file=None, script_segment_min_sentences=4, script_segment_max_sentences=4)
    assert s.script_segment_min_sentences == s.script_segment_max_sentences == 4


def test_segment_min_below_one_fails():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, script_segment_min_sentences=0)


@pytest.mark.parametrize("share", [0.49, 0.91, 0, 1])
def test_primary_share_out_of_range_fails(share):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, script_primary_share=share)


@pytest.mark.parametrize("share", [0.5, 0.7, 0.9])
def test_primary_share_in_range_accepted(share):
    assert Settings(_env_file=None, script_primary_share=share).script_primary_share == share


def test_script_bounds_read_from_environment(monkeypatch):
    monkeypatch.setenv("SCRIPT_SEGMENT_MIN_SENTENCES", "7")
    monkeypatch.setenv("SCRIPT_SEGMENT_MAX_SENTENCES", "3")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


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


# ---------- Feature 008: LLM model chain (data-model §1, contracts/config.md §1–§2) ----------

DEFAULT_CHAIN = [
    {
        "label": "sealion",
        "base_url": "http://127.0.0.1:3001/v1",
        "model": "gemma-sea-lion-v4-27b",
        "key_env": "FREELLMAPI_KEY",
        "platform": "cloudflare",
        "first_sentence_timeout_s": 2.5,
        "params": {},
    },
    {
        "label": "qwen",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "qwen/qwen3.8-27b",
        "key_env": "GROQ_API_KEY",
        "platform": None,
        "first_sentence_timeout_s": 2.0,
        "params": {"reasoning_effort": "none"},
    },
]


def make_entry(**fields):
    # Looked up at call time so a missing class fails each test, not the whole module import.
    return config_module.ChainEntryConfig(**fields)


VALID_ENTRY = {
    "label": "e1",
    "base_url": "https://api.example.com/v1",
    "model": "m",
    "key_env": "GROQ_API_KEY",
    "first_sentence_timeout_s": 1.0,
}


def test_feature_008_defaults():
    s = Settings(_env_file=None)
    assert s.reply_engine == "chain"
    assert s.llm_chain_cooldown_s == 60
    assert s.freellmapi_key is None
    assert s.groq_api_key is None
    assert [entry.model_dump() for entry in s.llm_chain] == DEFAULT_CHAIN
    assert [entry.position for entry in s.llm_chain] == [1, 2]
    assert [entry.local for entry in s.llm_chain] == [True, False]


def test_feature_008_secrets_are_secretstr():
    gsk = "gsk_" + "A" * 40
    s = Settings(_env_file=None, freellmapi_key="freellmapi-" + "b" * 32, groq_api_key=gsk)
    assert isinstance(s.freellmapi_key, SecretStr)
    assert isinstance(s.groq_api_key, SecretStr)
    assert s.groq_api_key.get_secret_value() == gsk
    assert gsk not in repr(s)


@pytest.mark.parametrize("engine", ["chain", "gemini", "fake"])
def test_reply_engine_accepts_all_three(engine):
    assert Settings(_env_file=None, reply_engine=engine).reply_engine == engine


def test_llm_chain_read_from_environment_json(monkeypatch):
    chain = [VALID_ENTRY, {**VALID_ENTRY, "label": "e2", "base_url": "http://localhost:3001/v1", "platform": "groq"}]
    monkeypatch.setenv("LLM_CHAIN", json.dumps(chain))
    s = Settings(_env_file=None)
    assert [e.label for e in s.llm_chain] == ["e1", "e2"]
    assert [e.position for e in s.llm_chain] == [1, 2]
    assert [e.local for e in s.llm_chain] == [False, True]


def test_llm_chain_from_env_example_file_matches_default():
    # The unquoted one-line JSON in `.env.example` must survive the dotenv reader (008 card TODO on unquoted JSON).
    from_file = Settings(_env_file=ENV_EXAMPLE)
    assert from_file.llm_chain == Settings(_env_file=None).llm_chain


@pytest.mark.parametrize("raw", ["[{bad json", '{"label": "x"}', "123"])
def test_malformed_llm_chain_names_the_variable(monkeypatch, raw):
    monkeypatch.setenv("LLM_CHAIN", raw)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "LLM_CHAIN" in str(exc.value)


def test_llm_chain_cooldown_must_not_be_negative():
    assert Settings(_env_file=None, llm_chain_cooldown_s=0).llm_chain_cooldown_s == 0
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_chain_cooldown_s=-1)


def test_chain_entry_minimal_defaults():
    entry = make_entry(**VALID_ENTRY)
    assert entry.platform is None
    assert entry.params == {}
    assert entry.local is False


@pytest.mark.parametrize("label", ["sealion", "a", "x" * 24, "qwen-3_b", "0"])
def test_chain_entry_label_accepted(label):
    assert make_entry(**{**VALID_ENTRY, "label": label}).label == label


@pytest.mark.parametrize("label", ["", "x" * 25, "SeaLion", "sea lion", "sea.lion", "mục1"])
def test_chain_entry_label_rejected(label):
    with pytest.raises(ValidationError):
        make_entry(**{**VALID_ENTRY, "label": label})


@pytest.mark.parametrize("url", ["", "ftp://x/v1", "127.0.0.1:3001/v1", "api.groq.com", "  "])
def test_chain_entry_base_url_must_be_http(url):
    with pytest.raises(ValidationError):
        make_entry(**{**VALID_ENTRY, "base_url": url})


@pytest.mark.parametrize(
    ("url", "local"),
    [
        ("http://127.0.0.1:3001/v1", True),
        ("http://localhost:3001/v1", True),
        ("http://[::1]:3001/v1", True),
        ("https://api.groq.com/openai/v1", False),
        ("http://10.0.0.5:3001/v1", False),
    ],
)
def test_chain_entry_local_derived_from_base_url(url, local):
    assert make_entry(**{**VALID_ENTRY, "base_url": url}).local is local


@pytest.mark.parametrize("timeout", [0, -1])
def test_chain_entry_timeout_must_be_positive(timeout):
    with pytest.raises(ValidationError):
        make_entry(**{**VALID_ENTRY, "first_sentence_timeout_s": timeout})


@pytest.mark.parametrize("platform", ["cloudflare", "groq", "x" * 32, "open-router_2"])
def test_chain_entry_platform_accepted(platform):
    assert make_entry(**{**VALID_ENTRY, "platform": platform}).platform == platform


@pytest.mark.parametrize("platform", ["", "x" * 33, "Groq", "cloud flare"])
def test_chain_entry_platform_rejected(platform):
    with pytest.raises(ValidationError):
        make_entry(**{**VALID_ENTRY, "platform": platform})


def test_chain_entry_forbids_extra_fields():
    with pytest.raises(ValidationError):
        make_entry(**VALID_ENTRY, temperature=0.2)


@pytest.mark.parametrize("missing", ["label", "base_url", "model", "key_env", "first_sentence_timeout_s"])
def test_chain_entry_required_fields(missing):
    data = {k: v for k, v in VALID_ENTRY.items() if k != missing}
    with pytest.raises(ValidationError):
        make_entry(**data)


def test_fixture_settings_are_offline(settings, tmp_path):
    assert settings.reply_engine == "fake"
    assert settings.tts_provider == "fake"
    assert settings.avatar_mode == "static"
    assert settings.gemini_api_key is None
    assert Path(settings.session_data_dir).is_relative_to(tmp_path)


# ---------- Feature 005: avatar / LiveTalking (data-model §1, contracts/events.md §5) ----------

AVATAR_DEFAULTS = {
    "customer_id": "",
    "avatar_id": "",
    "avatar_dir": Path("assets/avatars/demo_host_01"),
    "avatar_fallback_after": 2,
    "livetalking_url": "http://127.0.0.1:8010",
    "livetalking_python": Path("vendor/livetalking/.venv/Scripts/python.exe"),
    "livetalking_first_frame_timeout_s": 10,
    "livetalking_reconnect_max_s": 10,
    "livetalking_lead_s": 0,
}

# Read only by the fork through scripts/livetalking/run.ps1, so they live in `.env.example` but not in Settings.
FORK_ONLY_VARS = (
    "LIVETALKING_BATCH_SIZE",
    "LIVETALKING_LIP_EVERY_N",
    "LIVETALKING_TRANSITION_S",
    "LIVETALKING_HOLD_S",
    "AILIVE_RECORD_DIR",
    "AILIVE_RECORD_MAX_S",
)

LIPSYNC_OK = {"avatar_mode": "livetalking", "customer_id": "demo_customer_01", "avatar_id": "demo_host_01"}


def test_feature_005_settings_defaults_match_env_example():
    example = parse_env_example()
    defaults = Settings(_env_file=None)
    for name, expected in AVATAR_DEFAULTS.items():
        assert name.upper() in example, f"{name.upper()} missing from .env.example"
        assert getattr(defaults, name) == expected, name
        if example[name.upper()]:
            from_example = Settings(_env_file=None, **{name: example[name.upper()]})
            assert getattr(from_example, name) == expected, name


def test_fork_only_vars_are_in_env_example_but_not_settings():
    example = parse_env_example()
    fields = {name.upper() for name in Settings.model_fields}
    for key in FORK_ONLY_VARS:
        assert key in example, f"{key} missing from .env.example"
        assert key not in fields, f"{key} is read by the fork only and must not be a Settings field"


def test_static_mode_needs_no_customer_or_avatar():
    s = Settings(_env_file=None, avatar_mode="static")
    assert s.customer_id == ""
    assert s.avatar_id == ""


def test_livetalking_mode_accepts_full_identity():
    s = Settings(_env_file=None, **LIPSYNC_OK)
    assert s.avatar_mode == "livetalking"
    assert s.customer_id == "demo_customer_01"


@pytest.mark.parametrize("missing", ["customer_id", "avatar_id"])
def test_livetalking_mode_requires_customer_and_avatar(missing):
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, **{**LIPSYNC_OK, missing: ""})
    assert missing.upper() in str(exc.value)


@pytest.mark.parametrize("customer", ["Demo", "khách_01", "a b", "x" * 65, "a.b"])
def test_customer_id_pattern_rejected(customer):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, customer_id=customer)


@pytest.mark.parametrize("customer", ["a", "demo_customer_01", "shop-2", "x" * 64])
def test_customer_id_pattern_accepted(customer):
    assert Settings(_env_file=None, customer_id=customer).customer_id == customer


@pytest.mark.parametrize("url", ["http://127.0.0.1:8010", "http://localhost:9000", "http://127.0.0.1:8010/"])
def test_livetalking_url_loopback_accepted(url):
    assert Settings(_env_file=None, livetalking_url=url).livetalking_url == url.rstrip("/")


@pytest.mark.parametrize(
    "url", ["http://10.0.0.5:8010", "http://example.com:8010", "127.0.0.1:8010", "ftp://127.0.0.1:8010"]
)
def test_livetalking_url_must_be_loopback_http(url):
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, livetalking_url=url)
    assert "LIVETALKING_URL" in str(exc.value)


@pytest.mark.parametrize("label", ["AI", "AI host", "AI-generated"])
def test_livetalking_label_ascii_accepted(label):
    assert Settings(_env_file=None, **LIPSYNC_OK, ai_label_text=label).ai_label_text == label


@pytest.mark.parametrize("label", ["Người dẫn AI", "AI\tx", "", "  "])
def test_livetalking_label_must_be_printable_ascii(label):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **LIPSYNC_OK, ai_label_text=label)


def test_static_label_still_accepts_vietnamese():
    assert Settings(_env_file=None, ai_label_text="Người dẫn AI").ai_label_text == "Người dẫn AI"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("livetalking_first_frame_timeout_s", 0),
        ("livetalking_first_frame_timeout_s", -1),
        ("livetalking_reconnect_max_s", 0),
        ("livetalking_lead_s", -0.1),
        ("avatar_fallback_after", 0),
    ],
)
def test_avatar_bounds_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_avatar_bounds_edges_accepted():
    s = Settings(_env_file=None, livetalking_lead_s=0, avatar_fallback_after=1, livetalking_reconnect_max_s=0.5)
    assert (s.livetalking_lead_s, s.avatar_fallback_after, s.livetalking_reconnect_max_s) == (0, 1, 0.5)


# ---------- Feature 003: Vietnamese TTS (data-model §1, contracts/events.md §4) ----------

TTS_DEFAULTS = {
    "tts_provider": "fake",
    "tts_sample_rate": 16000,
    "tts_timeout_s": 5,
    "tts_quota_cooldown_s": 60,
    "fake_tts_delay_ms": 0,
    "vieneu_voice": "Thùy Dung",
    "vieneu_ref_audio": None,
    "vieneu_cpu_threads": 4,
    "vieneu_model_cache": Path.home() / ".cache" / "ai-live" / "hf",
    "gemini_tts_model": "gemini-3.8-flash-tts",
    "gemini_tts_voice": "Leda",
    "tts_abbreviations_path": Path("data/rules/tts_abbreviations.json"),
}

REMOVED_TTS_VARS = ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL_ID", "OSS_TTS_MODEL_PATH")


def test_feature_003_settings_defaults_match_env_example():
    example = parse_env_example()
    defaults = Settings(_env_file=None)
    for name, expected in TTS_DEFAULTS.items():
        assert name.upper() in example, f"{name.upper()} missing from .env.example"
        assert getattr(defaults, name) == expected, name
        from_example = Settings(_env_file=None, **{name: example[name.upper()]})
        assert getattr(from_example, name) == expected, name


def test_removed_tts_vars_not_in_env_example():
    example = parse_env_example()
    for key in REMOVED_TTS_VARS:
        assert key not in example, f"{key} has no adapter and must leave .env.example (ADR-024)"


@pytest.mark.parametrize("provider", ["fake", "vieneu", "gemini"])
def test_tts_provider_accepts_three_sources(provider):
    assert Settings(_env_file=None, tts_provider=provider).tts_provider == provider


@pytest.mark.parametrize("provider", ["elevenlabs", "oss", "azure", ""])
def test_tts_provider_rejects_others(provider):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tts_provider=provider)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tts_quota_cooldown_s", -1),
        ("vieneu_cpu_threads", 0),
        ("tts_sample_rate", 0),
        ("vieneu_voice", ""),
        ("vieneu_voice", "   "),
        ("gemini_tts_model", ""),
        ("gemini_tts_voice", " "),
    ],
)
def test_tts_bounds_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_tts_bounds_edges_accepted():
    s = Settings(_env_file=None, tts_quota_cooldown_s=0, vieneu_cpu_threads=1)
    assert (s.tts_quota_cooldown_s, s.vieneu_cpu_threads) == (0, 1)


def test_vieneu_model_cache_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("VIENEU_MODEL_CACHE", "~/models/hf")
    assert Settings(_env_file=None).vieneu_model_cache == Path.home() / "models" / "hf"
    assert Settings(_env_file=None, vieneu_model_cache=tmp_path).vieneu_model_cache == tmp_path


def test_tts_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "vieneu")
    monkeypatch.setenv("VIENEU_VOICE", "Mỹ Duyên")
    monkeypatch.setenv("VIENEU_CPU_THREADS", "6")
    s = Settings(_env_file=None)
    assert (s.tts_provider, s.vieneu_voice, s.vieneu_cpu_threads) == ("vieneu", "Mỹ Duyên", 6)


def test_vieneu_ref_audio_is_optional_and_expands_home():
    assert Settings(_env_file=None).vieneu_ref_audio is None
    assert Settings(_env_file=None, vieneu_ref_audio="").vieneu_ref_audio is None
    expanded = Settings(_env_file=None, vieneu_ref_audio="~/voices/mau.wav").vieneu_ref_audio
    assert expanded == Path.home() / "voices" / "mau.wav"
