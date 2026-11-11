"""T023 (008 US1): `create_reply_engine` picks the engine from `REPLY_ENGINE`; no network calls."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from ai_live.brain import factory
from ai_live.brain.chain_engine import ChainReplyEngine
from ai_live.brain.factory import create_reply_engine
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.gemini_engine import GeminiReplyEngine
from ai_live.core.config import Settings
from ai_live.core.protocols import ReplyEngineError
from fixtures import fake_openai as fo

pytestmark = pytest.mark.anyio


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "freellmapi_key": fo.FAKE_KEYS["FREELLMAPI_KEY"],
        "groq_api_key": fo.FAKE_KEYS["GROQ_API_KEY"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_fake_builds_the_fake_engine():
    assert isinstance(create_reply_engine(_settings(reply_engine="fake")), FakeReplyEngine)


def test_gemini_is_an_explicit_choice():
    engine = create_reply_engine(_settings(reply_engine="gemini", gemini_api_key="AIza-test-only-not-a-key"))
    assert isinstance(engine, GeminiReplyEngine)


def test_gemini_without_key_is_still_a_config_error():
    with pytest.raises(ReplyEngineError) as exc:
        create_reply_engine(_settings(reply_engine="gemini"))
    assert exc.value.kind == "config_error"


async def test_chain_is_the_default_and_builds_the_chain_engine():
    settings = _settings()
    assert settings.reply_engine == "chain"
    engine = create_reply_engine(settings)
    try:
        assert isinstance(engine, ChainReplyEngine)
        assert [e.label for e in engine.entries] == ["sealion", "qwen"]
    finally:
        await engine.aclose()


async def test_chain_with_only_builds_a_one_entry_chain():
    engine = create_reply_engine(_settings(groq_api_key=None), only="sealion")
    try:
        assert isinstance(engine, ChainReplyEngine)
        assert [e.label for e in engine.entries] == ["sealion"]
        assert engine.cooldown_s == 0
    finally:
        await engine.aclose()


def test_chain_config_errors_come_from_from_settings():
    with pytest.raises(ReplyEngineError) as exc:
        create_reply_engine(_settings(llm_chain=[]))
    assert exc.value.kind == "config_error"
    assert str(exc.value).startswith("LLM_CHAIN trống")


def test_only_and_fault_hook_reach_from_settings(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_from_settings(settings: Settings, **kw: Any) -> str:
        seen.update(kw, settings=settings)
        return "engine"

    monkeypatch.setattr(ChainReplyEngine, "from_settings", staticmethod(fake_from_settings))

    def hook(label: str) -> str | None:
        return None

    settings = _settings()
    assert create_reply_engine(settings, only="qwen", fault_hook=hook) == "engine"
    assert seen == {"settings": settings, "only": "qwen", "fault_hook": hook}


@pytest.mark.parametrize("engine", ["fake", "gemini"])
def test_only_is_refused_outside_the_chain(engine):
    with pytest.raises(ReplyEngineError) as exc:
        create_reply_engine(_settings(reply_engine=engine, gemini_api_key="AIza-test-only-not-a-key"), only="qwen")
    assert exc.value.kind == "config_error"
    assert "REPLY_ENGINE=chain" in str(exc.value)


def test_unknown_engine_is_a_config_error_not_a_silent_gemini():
    # `Settings` already refuses unknown values; a copy without validation reaches the factory's own check.
    settings = _settings().model_copy(update={"reply_engine": "openai"})
    with pytest.raises(ReplyEngineError) as exc:
        create_reply_engine(settings)
    assert exc.value.kind == "config_error"
    assert "openai" in str(exc.value)


def test_engine_modules_are_imported_lazily():
    # A fresh interpreter: importing the factory must not load the Gemini SDK or the chain engine.
    code = (
        "import sys, ai_live.brain.factory\n"
        "print(sorted(m for m in ('ai_live.brain.chain_engine', 'ai_live.brain.gemini_engine', 'google.genai')"
        " if m in sys.modules))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60)
    assert result.stdout.strip() == "[]"
    assert factory.create_reply_engine is create_reply_engine
