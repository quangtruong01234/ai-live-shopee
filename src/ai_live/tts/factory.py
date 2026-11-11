"""Pick the TTS source from `TTS_PROVIDER` and wrap it in `SpeechTTS` (003 contracts/adapters.md §4)."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from functools import partial

from ai_live.core.config import Settings
from ai_live.tts.normalize import load_abbreviations, normalize_for_speech
from ai_live.tts.speech import SpeechTTS


class TTSConfigError(ValueError):
    """`TTS_PROVIDER` names a source with no adapter, or the chosen source is not set up."""


def load_normalizer(settings: Settings) -> Callable[[str], str]:
    """`normalize_for_speech` bound to the abbreviation table, read once at startup (FR-006)."""
    path = settings.tts_abbreviations_path
    try:
        abbreviations = load_abbreviations(path)
    except (OSError, ValueError) as exc:
        raise TTSConfigError(f"TTS_ABBREVIATIONS_PATH={path} không dùng được: {exc}") from exc
    return partial(normalize_for_speech, abbreviations=abbreviations)


def create_tts(settings: Settings) -> SpeechTTS:
    if settings.tts_provider == "fake":
        from ai_live.tts.fake_tts import FakeTTS

        engine = FakeTTS(sample_rate=settings.tts_sample_rate, delay_ms=settings.fake_tts_delay_ms)
        return SpeechTTS(
            engine,
            provider="fake",
            normalize=load_normalizer(settings),
            quota_cooldown_s=settings.tts_quota_cooldown_s,
        )
    if settings.tts_provider == "vieneu":
        # Only check that the package is installed; the model itself loads in warm_up() so app start stays fast.
        if importlib.util.find_spec("vieneu") is None:
            raise TTSConfigError(
                "TTS_PROVIDER=vieneu nhưng chưa cài thư viện vieneu; "
                "chạy `uv sync` hoặc đặt TTS_PROVIDER=fake trong .env"
            )
        from ai_live.tts.vieneu_tts import VieneuTTS

        engine = VieneuTTS(
            voice=settings.vieneu_voice,
            cpu_threads=settings.vieneu_cpu_threads,
            model_cache=settings.vieneu_model_cache,
            sample_rate=settings.tts_sample_rate,
            ref_audio=settings.vieneu_ref_audio,
        )
        return SpeechTTS(
            engine,
            provider="vieneu",
            normalize=load_normalizer(settings),
            quota_cooldown_s=settings.tts_quota_cooldown_s,
        )
    if settings.tts_provider == "gemini":
        key = settings.gemini_api_key.get_secret_value().strip() if settings.gemini_api_key else ""
        if not key:
            raise TTSConfigError(
                "TTS_PROVIDER=gemini nhưng chưa có GEMINI_API_KEY; điền khóa vào .env "
                "hoặc đặt TTS_PROVIDER=fake/vieneu trong .env"
            )
        # Imported here so the other providers never pay for loading the SDK.
        from google import genai

        from ai_live.tts.gemini_tts import GeminiTTS

        engine = GeminiTTS(
            client=genai.Client(api_key=key),
            model=settings.gemini_tts_model,
            voice=settings.gemini_tts_voice,
            sample_rate=settings.tts_sample_rate,
        )
        return SpeechTTS(
            engine,
            provider="gemini",
            normalize=load_normalizer(settings),
            quota_cooldown_s=settings.tts_quota_cooldown_s,
        )
    raise TTSConfigError(
        f"TTS_PROVIDER={settings.tts_provider!r} chưa có adapter trong bản này; đặt TTS_PROVIDER=fake trong .env"
    )
