"""TTS giả cho test và chạy laptop không mạng (research R11).

Phát một âm nhỏ thay vì im lặng để người vận hành nghe được lúc nào host đang nói; thời lượng tỉ lệ số âm tiết để
nhịp phụ đề và độ trễ gần với TTS thật.
"""

from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator

SECONDS_PER_SYLLABLE = 0.25
CHUNK_SECONDS = 0.1
TONE_HZ = 400
AMPLITUDE = 1036  # khoảng −30 dBFS


class FakeTTSError(RuntimeError):
    """Lỗi giả lập để test nhánh lỗi bước `tts`."""


class FakeTTS:
    def __init__(self, sample_rate: int = 16000, delay_ms: int = 0, *, fail: bool = False) -> None:
        self.sample_rate = sample_rate
        self.delay_ms = delay_ms
        self.fail = fail
        samples_per_chunk = int(sample_rate * CHUNK_SECONDS)
        # 400 Hz chia hết cho 10 chu kỳ/100 ms nên mọi chunk giống nhau: tính một lần, dùng lại.
        self._chunk = struct.pack(
            f"<{samples_per_chunk}h",
            *(round(AMPLITUDE * math.sin(2 * math.pi * TONE_HZ * n / sample_rate)) for n in range(samples_per_chunk)),
        )

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
            # Nhường event loop giữa các chunk như TTS thật đang stream.
            await asyncio.sleep(0)
