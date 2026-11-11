"""T025 (003): real voice sources, skipped by default (marker `live_tts`).

VieNeu needs the model already in `VIENEU_MODEL_CACHE` (research R1); this test never downloads on its own:
`uv run pytest -m live_tts tests/integration/test_tts_live.py -k vieneu`

T044 (003): Gemini spends free quota (one request per run); ask before running it:
`uv run pytest -m live_tts tests/integration/test_tts_live.py -k gemini`
"""

from __future__ import annotations

import importlib.util
import time

import anyio
import pytest

from ai_live.core.config import Settings
from ai_live.tts.factory import create_tts

pytestmark = [pytest.mark.anyio, pytest.mark.live_tts]

SENTENCE = "Dạ, chị ơi, sản phẩm này đang có sẵn ạ."


async def test_vieneu_reads_a_sentence():
    if importlib.util.find_spec("vieneu") is None:
        pytest.skip("vieneu chưa cài (uv sync)")
    settings = Settings(tts_provider="vieneu")
    if not any(settings.vieneu_model_cache.glob("models--*VieNeu*")):
        pytest.skip(f"chưa có model VieNeu trong {settings.vieneu_model_cache}")
    tts = create_tts(settings)

    started = time.perf_counter()
    with anyio.fail_after(300):
        await tts.warm_up()
    warm_up_s = time.perf_counter() - started

    chunks: list[bytes] = []
    first_chunk_s = None
    started = time.perf_counter()
    with anyio.fail_after(120):
        async for chunk in tts.synthesize(SENTENCE):
            if first_chunk_s is None:
                first_chunk_s = time.perf_counter() - started
            chunks.append(chunk)
    total_s = time.perf_counter() - started

    assert tts.sample_rate == 16000
    assert chunks
    assert all(len(c) % 2 == 0 for c in chunks)
    audio_s = sum(len(c) for c in chunks) / 2 / tts.sample_rate
    assert audio_s > 0.5, audio_s
    print(
        f"\nvieneu warm_up={warm_up_s:.1f}s first_chunk={first_chunk_s:.2f}s total={total_s:.2f}s "
        f"audio={audio_s:.2f}s threads={settings.vieneu_cpu_threads}"
    )


async def test_gemini_reads_a_sentence():
    settings = Settings(tts_provider="gemini")
    if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value().strip():
        pytest.skip("chưa có GEMINI_API_KEY trong .env")
    tts = create_tts(settings)
    await tts.warm_up()

    chunks: list[bytes] = []
    first_chunk_s = None
    started = time.perf_counter()
    # A provider rate other than 16 kHz surfaces here as a `config_error` naming it (research R2).
    with anyio.fail_after(60):
        async for chunk in tts.synthesize(SENTENCE):
            if first_chunk_s is None:
                first_chunk_s = time.perf_counter() - started
            chunks.append(chunk)
    total_s = time.perf_counter() - started

    assert tts.sample_rate == 16000
    assert chunks
    assert all(len(c) % 2 == 0 for c in chunks)
    audio_s = sum(len(c) for c in chunks) / 2 / tts.sample_rate
    assert audio_s > 0.5, audio_s
    assert tts.usage.requests == 1
    print(
        f"\ngemini model={settings.gemini_tts_model} voice={settings.gemini_tts_voice} "
        f"first_chunk={first_chunk_s:.2f}s total={total_s:.2f}s audio={audio_s:.2f}s "
        f"chunks={len(chunks)} chars={tts.usage.chars}"
    )
