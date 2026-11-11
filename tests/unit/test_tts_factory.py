"""T009 (003): `create_tts()` always returns the `SpeechTTS` wrapper (contracts/adapters.md §4)."""

from __future__ import annotations

import sys

import pytest

from ai_live.core.config import Settings
from ai_live.tts.factory import TTSConfigError, create_tts
from ai_live.tts.fake_tts import FakeTTS
from ai_live.tts.speech import SpeechTTS

pytestmark = pytest.mark.anyio


def test_fake_provider_is_wrapped():
    tts = create_tts(Settings(_env_file=None, tts_provider="fake"))
    assert isinstance(tts, SpeechTTS)
    assert isinstance(tts.engine, FakeTTS)
    assert tts.usage.provider == "fake"
    assert tts.sample_rate == 16000


async def test_fake_provider_streams_and_counts_usage():
    tts = create_tts(Settings(_env_file=None, tts_provider="fake"))
    chunks = [c async for c in tts.synthesize("Dạ chào chị")]
    assert chunks
    assert (tts.usage.requests, tts.usage.chars) == (1, len("Dạ chào chị"))


# ---------- T022: vieneu (contracts/adapters.md §4) ----------


def test_vieneu_provider_wraps_vieneu_tts_without_loading(tmp_path, monkeypatch):
    from ai_live.tts import vieneu_tts

    def no_import(name: str):
        raise AssertionError(f"create_tts must not import {name}: the model loads only in warm_up()")

    monkeypatch.setattr(vieneu_tts, "import_module", no_import)
    settings = Settings(
        _env_file=None,
        tts_provider="vieneu",
        vieneu_voice="Mỹ Duyên",
        vieneu_cpu_threads=2,
        vieneu_model_cache=tmp_path,
        vieneu_ref_audio=tmp_path / "mau.wav",
    )
    tts = create_tts(settings)
    assert isinstance(tts, SpeechTTS)
    assert isinstance(tts.engine, vieneu_tts.VieneuTTS)
    assert (tts.engine.voice, tts.engine.cpu_threads, tts.engine.model_cache) == ("Mỹ Duyên", 2, tmp_path)
    assert tts.engine.ref_audio == tmp_path / "mau.wav"
    assert tts.usage.provider == "vieneu"
    assert tts.sample_rate == 16000


def test_vieneu_package_missing_is_config_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "vieneu", None)
    with pytest.raises(TTSConfigError) as exc:
        create_tts(Settings(_env_file=None, tts_provider="vieneu"))
    assert "uv sync" in str(exc.value)
    assert "TTS_PROVIDER=fake" in str(exc.value)


# ---------- T028: every provider reads normalized text (FR-006, contracts/adapters.md §4) ----------


class _RecordingEngine(FakeTTS):
    """Stands in for any source behind the wrapper and keeps the text it was asked to speak."""

    def __init__(self) -> None:
        super().__init__(sample_rate=16000, delay_ms=0)
        self.received: list[str] = []

    def synthesize(self, text: str):
        self.received.append(text)
        return super().synthesize(text)


def _settings(provider: str, tmp_path, monkeypatch, **overrides) -> Settings:
    if provider == "vieneu":
        from ai_live.tts import vieneu_tts

        monkeypatch.setattr(vieneu_tts, "import_module", lambda name: None)
        overrides["vieneu_model_cache"] = tmp_path
    return Settings(_env_file=None, tts_provider=provider, **overrides)


@pytest.mark.parametrize("provider", ["fake", "vieneu"])
async def test_engine_receives_normalized_text(provider, tmp_path, monkeypatch):
    tts = create_tts(_settings(provider, tmp_path, monkeypatch))
    tts.engine = recorder = _RecordingEngine()
    [c async for c in tts.synthesize("Giá chỉ 259.000đ")]
    assert recorder.received == ["Giá chỉ hai trăm năm mươi chín ngàn đồng"]


async def test_abbreviations_come_from_the_configured_file(tmp_path, monkeypatch):
    path = tmp_path / "abbr.json"
    path.write_text('{"MSP": "mã sản phẩm"}', encoding="utf-8")
    tts = create_tts(_settings("fake", tmp_path, monkeypatch, tts_abbreviations_path=path))
    tts.engine = recorder = _RecordingEngine()
    [c async for c in tts.synthesize("MSP này")]
    assert recorder.received == ["mã sản phẩm này"]


@pytest.mark.parametrize("provider", ["fake", "vieneu"])
@pytest.mark.parametrize(
    "content",
    [
        pytest.param(None, id="missing"),
        pytest.param("{not json", id="not-json"),
        pytest.param('{"SP": "sản phẩm 2"}', id="digit-in-value"),
    ],
)
def test_bad_abbreviations_file_is_config_error(tmp_path, monkeypatch, content, provider):
    path = tmp_path / "abbr.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(TTSConfigError) as exc:
        create_tts(_settings(provider, tmp_path, monkeypatch, tts_abbreviations_path=path))
    assert "TTS_ABBREVIATIONS_PATH" in str(exc.value)


# ---------- T037: gemini, and switching voices by config only (FR-011, FR-016, contracts/adapters.md §4) ----------


def test_gemini_provider_wraps_gemini_tts_with_model_and_voice():
    from ai_live.tts.gemini_tts import GeminiTTS

    settings = Settings(
        _env_file=None,
        tts_provider="gemini",
        gemini_api_key="test-key",
        gemini_tts_model="gemini-3.8-flash-tts",
        gemini_tts_voice="Kore",
    )
    tts = create_tts(settings)
    assert isinstance(tts, SpeechTTS)
    assert isinstance(tts.engine, GeminiTTS)
    assert (tts.engine.model, tts.engine.voice) == ("gemini-3.8-flash-tts", "Kore")
    assert tts.usage.provider == "gemini"
    assert tts.sample_rate == 16000


def test_gemini_without_api_key_is_config_error():
    with pytest.raises(TTSConfigError) as exc:
        create_tts(Settings(_env_file=None, tts_provider="gemini", gemini_api_key=None))
    message = str(exc.value)
    assert "GEMINI_API_KEY" in message
    assert ".env" in message


async def test_gemini_engine_receives_normalized_text():
    tts = create_tts(Settings(_env_file=None, tts_provider="gemini", gemini_api_key="test-key"))
    tts.engine = recorder = _RecordingEngine()
    [c async for c in tts.synthesize("Giá chỉ 259.000đ")]
    assert recorder.received == ["Giá chỉ hai trăm năm mươi chín ngàn đồng"]


@pytest.mark.parametrize(
    ("provider", "env_var", "voice"),
    [("vieneu", "VIENEU_VOICE", "Mỹ Duyên"), ("gemini", "GEMINI_TTS_VOICE", "Puck")],
)
def test_voice_changes_through_the_environment_only(provider, env_var, voice, tmp_path, monkeypatch):
    if provider == "vieneu":
        from ai_live.tts import vieneu_tts

        monkeypatch.setattr(vieneu_tts, "import_module", lambda name: None)
        monkeypatch.setenv("VIENEU_MODEL_CACHE", str(tmp_path))
    monkeypatch.setenv("TTS_PROVIDER", provider)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv(env_var, voice)
    assert create_tts(Settings(_env_file=None)).engine.voice == voice
