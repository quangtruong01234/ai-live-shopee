"""Fixture dùng chung: Settings test không cần mạng/key/GPU, backend anyio, đồng hồ giả."""

from __future__ import annotations

import os

import pytest

# Biến có thể có sẵn trong máy dev; xóa để test không vô tình dùng key thật hay cấu hình cá nhân.
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
    "LLM_",
    "FAKE_",
    "AI_LABEL_",
    "RENDERER_",
    "PROFANITY_",
    "PRIORITY_",
    "PRODUCT_",
    "CONTENT_",
    "SESSION_",
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
    """Settings cho test: engine/TTS giả, renderer tĩnh, không có GEMINI_API_KEY, không đọc `.env` thật."""
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
    """Đồng hồ giả thay cho `time.monotonic` trong test hết hạn (dedup, comment quá cũ)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
