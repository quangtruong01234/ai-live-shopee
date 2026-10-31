"""T114: `TTSEngine` contract (contracts/adapters.md "Hành vi bắt buộc", `TTSEngine.synthesize`).

PCM16 little-endian mono: every chunk is whole 16-bit samples, so its length is even.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import anyio
import pytest

pytestmark = pytest.mark.anyio

TEXTS = ["Dạ.", "Dạ chào bạn Lan nha.", "Kem chống nắng X loại 50 ml giá 250.000đ, loại 100 ml giá 420.000đ ạ."]


def test_sample_rate_is_positive_int(tts_harness):
    tts = tts_harness.make()
    assert isinstance(tts.sample_rate, int)
    assert tts.sample_rate > 0


@pytest.mark.parametrize("text", TEXTS, ids=["one-word", "short", "long"])
async def test_synthesize_streams_even_length_pcm16_chunks(tts_harness, text):
    tts = tts_harness.make()
    stream = tts.synthesize(text)
    assert isinstance(stream, AsyncIterator)
    with anyio.fail_after(5):
        chunks = [c async for c in stream]
    assert chunks, "at least one chunk"
    assert all(isinstance(c, bytes) for c in chunks)
    assert all(len(c) % 2 == 0 for c in chunks), [len(c) for c in chunks]
    assert sum(len(c) for c in chunks) > 0


async def test_failure_raises_exception(tts_harness):
    tts = tts_harness.make_failing()
    # The director catches any exception and logs `error_step=tts`; ending silently would play nothing unnoticed.
    # fail_after sits outside, so a hang surfaces as TimeoutError instead of counting as "raised".
    with anyio.fail_after(5):
        with pytest.raises(Exception):  # noqa: B017 - the contract only requires that something is raised
            async for _ in tts.synthesize("Dạ chào bạn Lan nha."):
                pass
