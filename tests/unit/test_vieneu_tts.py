"""T020 (003): `VieneuTTS` with a fake model (contracts/adapters.md §2, research R1, R5, R6).

No model download: the loader is injected, or `import_module` is replaced for the cache-environment tests.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import types
import wave
from collections.abc import AsyncIterator
from pathlib import Path

import anyio
import numpy as np
import pytest

from ai_live.core.protocols import TTSEngineError
from ai_live.tts import vieneu_tts
from ai_live.tts.vieneu_tts import VieneuTTS
from fixtures.fake_vieneu import REF_CODES, FakeVieneuModel

pytestmark = pytest.mark.anyio


def _make(
    model: FakeVieneuModel,
    *,
    voice: str = "Thục Đoan",
    threads: int = 4,
    loads: list[int] | None = None,
    ref_audio: Path | None = None,
):
    def load(cpu_threads: int) -> FakeVieneuModel:
        if loads is not None:
            loads.append(cpu_threads)
        return model

    return VieneuTTS(voice=voice, cpu_threads=threads, model_cache=Path("unused"), load_model=load, ref_audio=ref_audio)


async def _collect(stream: AsyncIterator[bytes]) -> list[bytes]:
    with anyio.fail_after(5):
        return [c async for c in stream]


def _samples(chunk: bytes) -> np.ndarray:
    return np.frombuffer(chunk, dtype="<i2")


async def test_output_is_pcm16_16khz_with_one_third_of_the_samples():
    model = FakeVieneuModel(chunks=3, chunk_samples=4800)
    tts = _make(model)
    assert tts.sample_rate == 16000
    await tts.warm_up()
    chunks = await _collect(tts.synthesize("Dạ chào chị"))
    assert len(chunks) == 3
    assert [len(c) for c in chunks] == [1600 * 2] * 3


async def test_chunks_keep_model_order():
    model = FakeVieneuModel(chunks=4, values=[0.1, 0.3, 0.5, 0.7])
    tts = _make(model)
    chunks = await _collect(tts.synthesize("abc"))
    means = [float(_samples(c)[200:].mean()) for c in chunks]
    assert means == sorted(means)
    assert means[-1] == pytest.approx(0.7 * 32767, rel=0.01)


async def test_values_are_clipped_to_int16():
    tts = _make(FakeVieneuModel(chunks=2, values=[2.0, -2.0]))
    chunks = await _collect(tts.synthesize("abc"))
    loud, quiet = _samples(chunks[0]), _samples(chunks[1])
    assert loud.max() == 32767
    assert quiet.min() >= -32768
    assert quiet[200:].max() <= -32767


async def test_text_and_voice_reach_the_model():
    model = FakeVieneuModel()
    tts = _make(model, voice="Mỹ Duyên")
    await tts.warm_up()
    await _collect(tts.synthesize("Dạ chị ơi"))
    assert model.calls[-1] == ("Dạ chị ơi", "Mỹ Duyên")


async def test_first_chunk_arrives_before_the_model_finishes():
    # FR-004: the first sentence plays while the rest is still being generated.
    model = FakeVieneuModel(chunks=3)
    tts = _make(model)
    await tts.warm_up()
    hold = threading.Event()
    model.hold_last = hold  # only the sentence below waits, not the warm-up read
    before = model.produced
    stream = tts.synthesize("abc")
    with anyio.fail_after(5):
        first = await anext(stream)
    assert first
    assert model.produced - before < 3
    hold.set()
    rest = await _collect(stream)
    assert len(rest) == 2


async def test_aclose_stops_the_worker_thread():
    # FR-014: skipping a sentence must stop generation, not just drop the audio.
    model = FakeVieneuModel(chunks=3)
    tts = _make(model)
    await tts.warm_up()
    model.chunks, model.delay_s = 200, 0.01  # a long sentence after a short warm-up read
    before = model.produced
    stream = tts.synthesize("abc")
    with anyio.fail_after(5):
        await anext(stream)
        await stream.aclose()
    assert model.finished_streams == 2  # warm-up read and this sentence
    produced = model.produced
    await asyncio.sleep(0.1)  # the worker would have produced ~10 more chunks by now
    assert model.produced == produced
    assert produced - before < 200


async def test_two_calls_run_one_after_the_other():
    model = FakeVieneuModel(chunks=3, delay_s=0.02)
    tts = _make(model)
    await tts.warm_up()
    with anyio.fail_after(5):
        a, b = await asyncio.gather(_collect(tts.synthesize("một")), _collect(tts.synthesize("hai")))
    assert len(a) == len(b) == 3
    assert model.max_active == 1


async def test_model_error_becomes_tts_engine_error():
    model = FakeVieneuModel(fail_after_calls=1)  # the warm-up read passes, the next sentence fails
    tts = _make(model)
    await tts.warm_up()
    with pytest.raises(TTSEngineError) as exc:
        await _collect(tts.synthesize("abc"))
    assert exc.value.kind == "model_error"
    assert exc.value.message.startswith("VieNeu lỗi khi đọc câu: ")
    assert "onnx hỏng" in exc.value.message


async def test_warm_up_loads_once_reads_a_test_sentence_and_passes_threads():
    model = FakeVieneuModel()
    loads: list[int] = []
    tts = _make(model, threads=6, loads=loads)
    await tts.warm_up()
    await tts.warm_up()
    assert loads == [6]
    assert model.calls == [("Dạ.", "Thục Đoan")]


async def test_unknown_voice_is_config_error():
    tts = _make(FakeVieneuModel(), voice="Không Có")
    with pytest.raises(TTSEngineError) as exc:
        await tts.warm_up()
    assert exc.value.kind == "config_error"
    assert "Không Có" in exc.value.message


async def test_loader_failure_is_config_error():
    def broken(_threads: int) -> FakeVieneuModel:
        raise OSError("không tìm thấy file onnx")

    tts = VieneuTTS(voice="Thục Đoan", cpu_threads=4, model_cache=Path("unused"), load_model=broken)
    with pytest.raises(TTSEngineError) as exc:
        await tts.warm_up()
    assert exc.value.kind == "config_error"
    assert "không tìm thấy file onnx" in exc.value.message


async def test_failed_warm_up_is_raised_again_without_reloading():
    loads: list[int] = []
    tts = _make(FakeVieneuModel(), voice="Không Có", loads=loads)
    with pytest.raises(TTSEngineError) as first:
        await tts.warm_up()
    with pytest.raises(TTSEngineError) as again:
        await _collect(tts.synthesize("abc"))
    assert again.value is first.value
    with pytest.raises(TTSEngineError) as third:
        await tts.warm_up()
    assert third.value is first.value
    assert loads == [4]


async def test_synthesize_without_warm_up_loads_first():
    model = FakeVieneuModel()
    loads: list[int] = []
    tts = _make(model, loads=loads)
    assert await _collect(tts.synthesize("abc"))
    assert loads == [4]


async def test_slow_model_does_not_block_the_event_loop():
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.005)
            ticks += 1

    def slow_load(_threads: int) -> FakeVieneuModel:
        time.sleep(0.1)
        return FakeVieneuModel(chunks=4, delay_s=0.03)

    tts = VieneuTTS(voice="Thục Đoan", cpu_threads=4, model_cache=Path("unused"), load_model=slow_load)
    task = asyncio.create_task(ticker())
    try:
        await tts.warm_up()
        after_warm_up = ticks
        await _collect(tts.synthesize("abc"))
    finally:
        task.cancel()
    assert after_warm_up >= 5
    assert ticks - after_warm_up >= 5


# ---------- Default loader: model cache environment (research R1) ----------


def _fake_vieneu_module(seen: dict) -> types.ModuleType:
    module = types.ModuleType("vieneu")

    def factory(**kwargs):
        seen["kwargs"] = kwargs
        return FakeVieneuModel()

    module.Vieneu = factory
    return module


@pytest.fixture
def clean_hf_env(monkeypatch):
    # monkeypatch restores whatever the adapter writes into os.environ.
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_SYMLINKS", raising=False)
    monkeypatch.delitem(sys.modules, "huggingface_hub", raising=False)
    return monkeypatch


async def test_default_loader_sets_cache_env_before_import(clean_hf_env, tmp_path):
    seen: dict = {}

    def fake_import(name: str):
        import os

        assert name == "vieneu"
        seen["env"] = (os.environ.get("HF_HUB_CACHE"), os.environ.get("HF_HUB_DISABLE_SYMLINKS"))
        return _fake_vieneu_module(seen)

    clean_hf_env.setattr(vieneu_tts, "import_module", fake_import)
    tts = VieneuTTS(voice="Thục Đoan", cpu_threads=3, model_cache=tmp_path / "hf")
    await tts.warm_up()
    assert seen["env"] == (str(tmp_path / "hf"), "1")
    assert seen["kwargs"] == {"mode": "v3turbo", "backend": "onnx", "threads": 3}


async def test_huggingface_hub_imported_earlier_is_config_error(clean_hf_env, tmp_path):
    imported: list[str] = []
    clean_hf_env.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))
    clean_hf_env.setattr(vieneu_tts, "import_module", lambda name: imported.append(name))
    tts = VieneuTTS(voice="Thục Đoan", cpu_threads=3, model_cache=tmp_path / "hf")
    with pytest.raises(TTSEngineError) as exc:
        await tts.warm_up()
    assert exc.value.kind == "config_error"
    assert "VIENEU_MODEL_CACHE" in exc.value.message
    assert imported == []


async def test_huggingface_hub_already_on_our_cache_is_fine(clean_hf_env, tmp_path):
    # A second VieneuTTS in the same process (CLI, tests) finds the hub imported with our own settings.
    seen: dict = {}
    clean_hf_env.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    clean_hf_env.setenv("HF_HUB_DISABLE_SYMLINKS", "1")
    clean_hf_env.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))
    clean_hf_env.setattr(vieneu_tts, "import_module", lambda name: _fake_vieneu_module(seen))
    tts = VieneuTTS(voice="Thục Đoan", cpu_threads=3, model_cache=tmp_path / "hf")
    await tts.warm_up()
    assert seen["kwargs"]["threads"] == 3


# ---------- Reference clip `VIENEU_REF_AUDIO` (FR-002, contracts/adapters.md §2, research R1) ----------


def _write_wav(path: Path, seconds: float, *, rate: int = 16000, channels: int = 1, width: int = 2) -> Path:
    frames = int(seconds * rate)
    sample = b"\x00\x40" if width == 2 else b"\x80"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(sample * frames * channels)
    return path


async def test_ref_audio_is_encoded_once_and_used_for_every_sentence(tmp_path):
    model = FakeVieneuModel()
    tts = _make(model, ref_audio=_write_wav(tmp_path / "mau.wav", 2.0))
    await tts.warm_up()
    await _collect(tts.synthesize("Kem chống nắng"))
    await _collect(tts.synthesize("Dạ"))
    assert len(model.engine.encoded) == 1
    wav, rate = model.engine.encoded[0]
    assert rate == 16000
    assert wav.dtype == np.float32
    assert wav.shape == (32000,)
    assert wav[0] == pytest.approx(0x4000 / 32768)
    assert [text for text, _ in model.calls] == ["Dạ.", "Kem chống nắng", "Dạ"]
    for _text, used in model.calls:
        assert used["speaker_emb"] == model.get_preset_voice("Thục Đoan")["speaker_emb"]
        assert used["codes"] is REF_CODES


async def test_ref_audio_is_mixed_to_mono_and_cut_to_8_s(tmp_path):
    model = FakeVieneuModel()
    tts = _make(model, ref_audio=_write_wav(tmp_path / "dai.wav", 10.0, rate=24000, channels=2))
    await tts.warm_up()
    wav, rate = model.engine.encoded[0]
    assert rate == 24000
    assert wav.shape == (8 * 24000,)


async def test_without_ref_audio_the_preset_name_is_used():
    model = FakeVieneuModel()
    tts = _make(model, voice="Mỹ Duyên")
    await tts.warm_up()
    assert model.engine.encoded == []
    assert model.calls == [("Dạ.", "Mỹ Duyên")]


async def test_missing_ref_audio_is_config_error_and_nothing_is_spoken(tmp_path):
    model = FakeVieneuModel()
    tts = _make(model, ref_audio=tmp_path / "khong_co.wav")
    with pytest.raises(TTSEngineError) as exc:
        await tts.warm_up()
    assert exc.value.kind == "config_error"
    assert "VIENEU_REF_AUDIO" in exc.value.message
    assert "khong_co.wav" in exc.value.message
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("Dạ"))
    assert model.calls == []


@pytest.mark.parametrize("kind", ["garbage", "8bit"])
async def test_unreadable_ref_audio_is_config_error(tmp_path, kind):
    path = tmp_path / "hong.wav"
    if kind == "garbage":
        path.write_bytes(b"not a wav file")
    else:
        _write_wav(path, 1.0, width=1)
    model = FakeVieneuModel()
    tts = _make(model, ref_audio=path)
    with pytest.raises(TTSEngineError) as exc:
        await tts.warm_up()
    assert exc.value.kind == "config_error"
    assert "VIENEU_REF_AUDIO" in exc.value.message
    assert model.calls == []


async def test_vieneu_without_the_private_encoder_is_config_error(tmp_path):
    model = FakeVieneuModel(engine=object())
    tts = _make(model, ref_audio=_write_wav(tmp_path / "mau.wav", 1.0))
    with pytest.raises(TTSEngineError) as exc:
        await tts.warm_up()
    assert exc.value.kind == "config_error"
    assert "vieneu" in exc.value.message
    assert model.calls == []
