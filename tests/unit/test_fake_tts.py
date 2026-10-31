"""T033: FakeTTS (research R11)."""

from __future__ import annotations

import array
import time

import pytest

from ai_live.tts.fake_tts import FakeTTS, FakeTTSError

pytestmark = pytest.mark.anyio


async def _collect(tts: FakeTTS, text: str) -> list[bytes]:
    return [chunk async for chunk in tts.synthesize(text)]


async def test_pcm16_mono_100ms_chunks():
    tts = FakeTTS(sample_rate=16000)
    assert tts.sample_rate == 16000
    chunks = await _collect(tts, "Dạ chào bạn Lan")
    bytes_per_chunk = 16000 // 10 * 2
    assert all(len(c) == bytes_per_chunk for c in chunks[:-1])
    assert 0 < len(chunks[-1]) <= bytes_per_chunk
    assert all(len(c) % 2 == 0 for c in chunks)


async def test_duration_about_quarter_second_per_syllable():
    tts = FakeTTS(sample_rate=16000)
    audio = b"".join(await _collect(tts, "Dạ kem chống nắng giá hai trăm năm mươi nghìn nha"))  # 11 syllables
    seconds = len(audio) / 2 / 16000
    assert seconds == pytest.approx(11 * 0.25, abs=0.05)


async def test_quiet_tone_not_silence():
    tts = FakeTTS(sample_rate=16000)
    samples = array.array("h", b"".join(await _collect(tts, "xin chào")))
    peak = max(abs(s) for s in samples)
    # About -30 dBFS: ~1,036 on the 32,767 scale. Not silent, so the operator can hear when audio is playing.
    assert 500 < peak < 2000


async def test_first_chunk_delay():
    tts = FakeTTS(sample_rate=16000, delay_ms=150)
    start = time.perf_counter()
    agen = tts.synthesize("xin chào")
    await agen.__anext__()
    # asyncio may wake a timer up to one monotonic tick early (~15.6 ms on Windows), so allow exactly that much.
    early = time.get_clock_info("monotonic").resolution
    assert time.perf_counter() - start >= 0.15 - early - 0.001
    await agen.aclose()


async def test_error_flag_raises():
    tts = FakeTTS(sample_rate=16000, fail=True)
    with pytest.raises(FakeTTSError):
        await _collect(tts, "xin chào")


async def test_empty_text_still_yields_minimum_audio():
    chunks = await _collect(FakeTTS(sample_rate=16000), "...")
    assert sum(len(c) for c in chunks) == int(0.25 * 16000) * 2
