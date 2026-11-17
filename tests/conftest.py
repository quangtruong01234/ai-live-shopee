"""Shared fixtures: test Settings needing no network/key/GPU, the anyio backend, a fake clock."""

from __future__ import annotations

import os

import pytest

# Variables a dev machine may already export; removed so tests never pick up a real key or personal config.
_ENV_PREFIXES = (
    "APP_",
    "LOG_",
    "COMMENT_",
    "TTS_",
    "AVATAR_",
    "OUTPUT_",
    "QUEUE_",
    "REPLY_",
    "GEMINI_",
    "GOOGLE_API_KEY",
    "FREELLMAPI_",
    "GROQ_",
    "LLM_",
    "FAKE_",
    "AI_LABEL_",
    "RENDERER_",
    "PROFANITY_",
    "PRIORITY_",
    "PRODUCT_",
    "CONTENT_",
    "SESSION_",
    "VIENEU_",
    "SCENE_",
    "CUSTOMER_ID",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.upper().startswith(_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path):
    """Test Settings: fake engine/TTS, static renderer, no GEMINI_API_KEY, the real `.env` is not read."""
    from ai_live.core.config import Settings

    return Settings(
        _env_file=None,
        reply_engine="fake",
        tts_provider="fake",
        avatar_mode="static",
        app_env="dev",
        session_data_dir=tmp_path / "sessions",
    )


class FakeClock:
    """Fake clock standing in for `time.monotonic` in expiry tests (dedup, stale comments)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
