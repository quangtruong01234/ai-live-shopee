"""T044 (003): the shared streaming resampler (research R5): VieNeu 48 → 16 kHz, Gemini 24 → 16 kHz."""

from __future__ import annotations

import numpy as np
import pytest

from ai_live.tts.resample import Resampler


def _tone(freq: float, rate: int, seconds: float = 0.5, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _pcm(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32767


def _level(samples: np.ndarray) -> float:
    # Skip the filter's start-up so only the steady state is measured.
    return float(np.sqrt(np.mean(samples[200:] ** 2)))


@pytest.mark.parametrize(("source", "n_in", "n_out"), [(24000, 2400, 1600), (48000, 4800, 1600), (16000, 1600, 1600)])
def test_output_has_the_target_number_of_samples(source, n_in, n_out):
    out = Resampler(source, 16000)(np.zeros(n_in, dtype=np.float32))
    assert len(out) == n_out * 2


@pytest.mark.parametrize("source", [24000, 48000])
def test_speech_band_tone_keeps_its_level(source):
    out = _pcm(Resampler(source, 16000)(_tone(1000, source)))
    assert _level(out) == pytest.approx(0.5 / np.sqrt(2), rel=0.05)


@pytest.mark.parametrize("source", [24000, 48000])
def test_tone_above_the_new_nyquist_is_cut(source):
    # 10 kHz cannot exist at 16 kHz; without the low-pass it would fold back to an audible 6 kHz.
    out = _pcm(Resampler(source, 16000)(_tone(10000, source)))
    assert _level(out) < 0.05


@pytest.mark.parametrize("source", [24000, 48000])
def test_chunked_input_matches_one_call(source):
    signal = _tone(700, source) + _tone(3000, source, amplitude=0.2)
    whole = Resampler(source, 16000)(signal)
    resampler = Resampler(source, 16000)
    # Odd, uneven chunk sizes so chunk edges fall on every phase of the 2:3 and 1:3 patterns.
    sizes = [1, 7, 333, 2, 1000, 5]
    parts, start = [], 0
    while start < len(signal):
        size = sizes[len(parts) % len(sizes)]
        parts.append(resampler(signal[start : start + size]))
        start += size
    assert b"".join(parts) == whole


def test_same_rate_only_converts_to_int16():
    signal = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    assert Resampler(16000, 16000)(signal) == np.round(signal * 32767).astype("<i2").tobytes()


def test_values_are_clipped():
    out = np.frombuffer(Resampler(16000, 16000)(np.array([2.0, -3.0], dtype=np.float32)), dtype="<i2")
    assert out.tolist() == [32767, -32767]


@pytest.mark.parametrize("source", [44100, 22050, 11025])
def test_ratio_needing_large_upsampling_is_rejected(source):
    with pytest.raises(ValueError, match=str(source)):
        Resampler(source, 16000)
