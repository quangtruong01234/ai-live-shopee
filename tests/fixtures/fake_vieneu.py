"""Stand-in for a loaded `vieneu.Vieneu` model (003 T020, T021): no 581 MB download, no ONNX.

Only the surface `VieneuTTS` uses: `sample_rate`, `list_preset_voices()`, `get_preset_voice()`, the reference-clip
encoder `engine._encode_ref_wav()` and the synchronous `infer_stream()` generator yielding float32 arrays at 48 kHz,
like v3 Turbo.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence
from typing import Any

import numpy as np

MODEL_RATE = 48000
VOICES = ("Thục Đoan", "Mỹ Duyên", "Hải Đăng")
# Shape of the real MOSS codes: (frames, codebooks).
REF_CODES = np.arange(30 * 16, dtype=np.int64).reshape(30, 16)


class FakeEngine:
    """`model.engine`: records every reference clip it encodes."""

    def __init__(self) -> None:
        self.encoded: list[tuple[np.ndarray, int]] = []

    def _encode_ref_wav(self, wav: np.ndarray, sr: int) -> np.ndarray:
        self.encoded.append((np.asarray(wav), sr))
        return REF_CODES


class FakeVieneuModel:
    def __init__(
        self,
        *,
        chunks: int = 3,
        chunk_samples: int = 4800,
        values: Sequence[float] | None = None,
        delay_s: float = 0.0,
        fail_after_calls: int | None = None,
        hold_last: threading.Event | None = None,
        sample_rate: int = MODEL_RATE,
        engine: Any = None,
    ) -> None:
        self.sample_rate = sample_rate
        # Pass `engine=object()` to model a vieneu release without the private encoder.
        self.engine = engine if engine is not None else FakeEngine()
        self.chunks = chunks
        self.chunk_samples = chunk_samples
        self.values = list(values) if values is not None else [0.25] * chunks
        self.delay_s = delay_s
        self.fail_after_calls = fail_after_calls
        self.hold_last = hold_last
        self.calls: list[tuple[str, Any]] = []
        self.produced = 0
        self.finished_streams = 0
        self.active = 0
        self.max_active = 0
        self._count_lock = threading.Lock()

    def list_preset_voices(self) -> list[tuple[str, str]]:
        return [(f"⭐ {name}", name) for name in VOICES]

    def get_preset_voice(self, voice_name: str | None = None) -> dict[str, Any]:
        index = VOICES.index(voice_name or VOICES[0])
        return {"description": "giả", "speaker_emb": [float(index), 0.5, -0.5]}

    def infer_stream(self, text: str, voice: Any = None, **kwargs: Any) -> Iterator[np.ndarray]:
        self.calls.append((text, voice))
        with self._count_lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.fail_after_calls is not None and len(self.calls) > self.fail_after_calls:
                raise RuntimeError("onnx hỏng")
            for index in range(self.chunks):
                if self.hold_last is not None and index == self.chunks - 1:
                    self.hold_last.wait(5)
                if self.delay_s:
                    time.sleep(self.delay_s)
                self.produced += 1
                yield np.full(self.chunk_samples, self.values[index % len(self.values)], dtype=np.float32)
        finally:
            with self._count_lock:
                self.active -= 1
            self.finished_streams += 1
