"""Chọn TTS theo `TTS_PROVIDER`. Feature 001 chỉ có `fake`; giọng thật thêm ở feature 002 (ADR, rủi ro license)."""

from __future__ import annotations

from ai_live.core.config import Settings
from ai_live.core.protocols import TTSEngine


class TTSConfigError(ValueError):
    """`TTS_PROVIDER` chọn nhà cung cấp chưa có adapter."""


def create_tts(settings: Settings) -> TTSEngine:
    if settings.tts_provider == "fake":
        from ai_live.tts.fake_tts import FakeTTS

        return FakeTTS(sample_rate=settings.tts_sample_rate, delay_ms=settings.fake_tts_delay_ms)
    raise TTSConfigError(
        f"TTS_PROVIDER={settings.tts_provider!r} chưa có adapter trong bản này; đặt TTS_PROVIDER=fake trong .env"
    )
