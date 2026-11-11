"""Streaming sample-rate conversion to the PCM16 every adapter returns (003 research R5).

VieNeu sends 48 kHz and Gemini 24 kHz; both go to `TTS_SAMPLE_RATE` (16 kHz).
Imported only by the adapters that need it, so `TTS_PROVIDER=fake` never loads `numpy`.
"""

from __future__ import annotations

from math import gcd

import numpy as np

# 31 taps per input sample keep the per-chunk cost tiny on CPU and still cut most of what would alias above 8 kHz.
FILTER_TAPS = 31
# Rates such as 44.1 kHz need 160x upsampling; nothing we use sends them, so refuse rather than run a huge filter.
MAX_UPSAMPLE = 4


class Resampler:
    """Rational resampler: insert zeros, low-pass, keep every `down`-th sample.

    Filter state and phase carry across chunks, so chunk edges do not click and the output does not depend on chunking.
    """

    def __init__(self, source_rate: int, target_rate: int) -> None:
        common = gcd(source_rate, target_rate)
        self.up = target_rate // common
        self.down = source_rate // common
        if self.up > MAX_UPSAMPLE:
            raise ValueError(f"cannot resample {source_rate} Hz to {target_rate} Hz")
        if self.up == self.down == 1:
            taps = np.ones(1)
        else:
            size = FILTER_TAPS * self.up | 1  # odd, so the filter delay is a whole number of samples
            offsets = np.arange(size) - (size - 1) / 2
            cutoff = 0.9 * 0.5 / max(self.up, self.down)  # per upsampled sample, just under the lower Nyquist
            taps = 2 * cutoff * np.sinc(2 * cutoff * offsets) * np.hamming(size)
            # Gain `up` makes up for the inserted zeros.
            taps *= self.up / taps.sum()
        self._taps = taps.astype(np.float32)
        self._history = np.zeros(len(taps) - 1, dtype=np.float32)
        self._phase = 0

    def __call__(self, chunk: np.ndarray) -> bytes:
        """Float samples in [-1, 1] (clipped) at the source rate → PCM16 little-endian at the target rate."""
        samples = np.clip(np.asarray(chunk, dtype=np.float32).reshape(-1), -1.0, 1.0)
        if self.up > 1:
            stuffed = np.zeros(len(samples) * self.up, dtype=np.float32)
            stuffed[:: self.up] = samples
        else:
            stuffed = samples
        padded = np.concatenate((self._history, stuffed))
        filtered = np.convolve(padded, self._taps, mode="valid")  # one output per upsampled sample
        if len(self._history):
            self._history = padded[-len(self._history) :]
        picked = filtered[self._phase :: self.down]
        self._phase = (self._phase - len(stuffed)) % self.down
        return np.round(np.clip(picked, -1.0, 1.0) * 32767).astype("<i2").tobytes()
