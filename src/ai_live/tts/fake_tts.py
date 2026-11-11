"""Fake TTS for tests and offline laptop runs (001 research R11).

Plays a quiet tone instead of silence so the operator can hear when the host is speaking; the duration scales with
the syllable count so subtitle pacing and latency stay close to a real TTS.
"""

from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator

SECONDS_PER_SYLLABLE = 0.25
CHUNK_SECONDS = 0.1
TONE_HZ = 400
AMPLITUDE = 1036  # about -30 dBFS


class FakeTTSError(RuntimeError):
    """Simulated failure to test the error path of the `tts` step."""


class FakeTTS:
    def __init__(self, sample_rate: int = 16000, delay_ms: int = 0, *, fail: bool = False) -> None:
        self.sample_rate = sample_rate
        self.delay_ms = delay_ms
        self.fail = fail
        samples_per_chunk = int(sample_rate * CHUNK_SECONDS)
        # 400 Hz is exactly 40 cycles per 100 ms, so every chunk is identical: compute it once and reuse it.
        self._chunk = struct.pack(
            f"<{samples_per_chunk}h",
            *(round(AMPLITUDE * math.sin(2 * math.pi * TONE_HZ * n / sample_rate)) for n in range(samples_per_chunk)),
        )

    async def warm_up(self) -> None:
        return None

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        if self.fail:
            raise FakeTTSError("FakeTTS được cấu hình để lỗi")
        syllables = max(1, len(text.split()))
        remaining = int(syllables * SECONDS_PER_SYLLABLE * self.sample_rate) * 2
        while remaining > 0:
            chunk = self._chunk[:remaining]
            remaining -= len(chunk)
            yield chunk
            # Yield to the event loop between chunks, like a real streaming TTS.
            await asyncio.sleep(0)
