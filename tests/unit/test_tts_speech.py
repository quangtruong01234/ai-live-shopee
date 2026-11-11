"""T008 (003): `SpeechTTS` wrapper (contracts/adapters.md §2, data-model §4).

The wrapper normalizes text, counts usage and holds a cooldown after a quota error, so the engine underneath only ever
sees spoken text and is not hammered while the free quota is exhausted.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator

import anyio
import anyio.lowlevel
import pytest

from ai_live.core.protocols import TTSEngineError
from ai_live.tts.speech import SpeechTTS, TTSUsage

pytestmark = pytest.mark.anyio

CHUNK = b"\x01\x00" * 160


class ScriptedEngine:
    """Records what it was asked to say; `failures` are raised one per call before any chunk."""

    def __init__(self, *, chunks: int = 3, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.chunks = chunks
        self.calls: list[str] = []
        self.failures: list[TTSEngineError] = []
        self.warm_ups = 0
        self.closed = False
        self.produced = 0

    async def warm_up(self) -> None:
        self.warm_ups += 1

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.calls.append(text)
        if self.failures:
            raise self.failures.pop(0)
        try:
            for _ in range(self.chunks):
                self.produced += 1
                yield CHUNK
                await anyio.lowlevel.checkpoint()
        finally:
            self.closed = True


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _upper(text: str) -> str:
    return text.upper()


def _make(
    engine: ScriptedEngine, *, normalize=_upper, cooldown: float = 60, clock: FakeClock | None = None
) -> SpeechTTS:
    return SpeechTTS(
        engine, provider="gemini", normalize=normalize, quota_cooldown_s=cooldown, clock=clock or FakeClock()
    )


async def _collect(stream: AsyncIterator[bytes]) -> list[bytes]:
    with anyio.fail_after(5):
        return [c async for c in stream]


@pytest.fixture
def tts_logs() -> Iterator[list[logging.LogRecord]]:
    """Records of `ai_live.tts` with our own handler: `configure_logging` may have stopped propagation."""
    records: list[logging.LogRecord] = []

    class _Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Keep(level=logging.DEBUG)
    tts_logger = logging.getLogger("ai_live.tts")
    old_level = tts_logger.level
    tts_logger.addHandler(handler)
    tts_logger.setLevel(logging.DEBUG)
    yield records
    tts_logger.removeHandler(handler)
    tts_logger.setLevel(old_level)


def _events(records: list[logging.LogRecord], name: str) -> list[logging.LogRecord]:
    return [r for r in records if r.getMessage() == name]


async def test_engine_receives_normalized_text_and_chunks_pass_through():
    engine = ScriptedEngine(chunks=3)
    tts = _make(engine)
    chunks = await _collect(tts.synthesize("dạ chị"))
    assert engine.calls == ["DẠ CHỊ"]
    assert chunks == [CHUNK] * 3


async def test_usage_counts_requests_and_normalized_chars():
    engine = ScriptedEngine()
    tts = _make(engine, normalize=lambda t: t + " ạ")
    await _collect(tts.synthesize("Dạ"))
    await _collect(tts.synthesize("Chào chị"))
    assert tts.usage == TTSUsage(provider="gemini", requests=2, chars=len("Dạ ạ") + len("Chào chị ạ"))


async def test_failed_sentence_still_counts_as_request():
    engine = ScriptedEngine()
    engine.failures.append(TTSEngineError("api_error", "Gemini TTS lỗi HTTP 500: lỗi máy chủ"))
    tts = _make(engine)
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("abc"))
    assert (tts.usage.requests, tts.usage.chars) == (1, 3)


async def test_empty_after_normalization_yields_nothing_and_skips_engine():
    engine = ScriptedEngine()
    tts = _make(engine, normalize=lambda _t: "")
    assert await _collect(tts.synthesize("👉 https://x.vn")) == []
    assert engine.calls == []
    assert (tts.usage.requests, tts.usage.chars) == (0, 0)


async def test_quota_error_enters_cooldown_logs_and_reraises(tts_logs):
    engine = ScriptedEngine()
    engine.failures.append(TTSEngineError("quota_exhausted", "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí)."))
    tts = _make(engine, cooldown=60)
    with pytest.raises(TTSEngineError) as exc:
        await _collect(tts.synthesize("abc"))
    assert exc.value.kind == "quota_exhausted"
    assert exc.value.message == "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí). Thử lại sau 60 giây."
    assert tts.usage.quota_errors == 1
    [record] = _events(tts_logs, "tts_quota_exhausted")
    assert record.fields == {"provider": "gemini", "cooldown_s": 60}


async def test_cooldown_rejects_without_calling_engine():
    engine = ScriptedEngine()
    engine.failures.append(TTSEngineError("quota_exhausted", "Hết hạn mức"))
    clock = FakeClock()
    tts = _make(engine, cooldown=60, clock=clock)
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("abc"))
    clock.now += 15
    with pytest.raises(TTSEngineError) as exc:
        await _collect(tts.synthesize("xyz"))
    assert exc.value.kind == "quota_exhausted"
    assert "Thử lại sau 45 giây" in exc.value.message
    assert engine.calls == ["ABC"]
    assert tts.usage.rejected_in_cooldown == 1
    # A rejected sentence never reached the source, so it does not count toward the quota.
    assert (tts.usage.requests, tts.usage.chars) == (1, 3)


async def test_after_cooldown_engine_is_tried_exactly_once():
    engine = ScriptedEngine()
    engine.failures.append(TTSEngineError("quota_exhausted", "Hết hạn mức"))
    clock = FakeClock()
    tts = _make(engine, cooldown=60, clock=clock)
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("abc"))
    clock.now += 60
    assert await _collect(tts.synthesize("xyz")) == [CHUNK] * 3
    assert engine.calls == ["ABC", "XYZ"]
    assert await _collect(tts.synthesize("def")) == [CHUNK] * 3
    assert tts.usage.rejected_in_cooldown == 0


async def test_quota_error_again_after_cooldown_restarts_it():
    engine = ScriptedEngine()
    engine.failures += [TTSEngineError("quota_exhausted", "a"), TTSEngineError("quota_exhausted", "b")]
    clock = FakeClock()
    tts = _make(engine, cooldown=10, clock=clock)
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("a"))
    clock.now += 10
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("b"))
    clock.now += 5
    with pytest.raises(TTSEngineError) as exc:
        await _collect(tts.synthesize("c"))
    assert "Thử lại sau 5 giây" in exc.value.message
    assert (tts.usage.quota_errors, tts.usage.rejected_in_cooldown, len(engine.calls)) == (2, 1, 2)


@pytest.mark.parametrize("kind", ["rate_limited", "api_error", "config_error", "model_error"])
async def test_other_errors_pass_through_without_cooldown(kind):
    engine = ScriptedEngine()
    original = TTSEngineError(kind, "lỗi gốc")
    engine.failures.append(original)
    tts = _make(engine)
    with pytest.raises(TTSEngineError) as exc:
        await _collect(tts.synthesize("abc"))
    assert exc.value is original
    assert await _collect(tts.synthesize("xyz")) == [CHUNK] * 3
    assert (tts.usage.quota_errors, tts.usage.rejected_in_cooldown) == (0, 0)


async def test_non_tts_exception_passes_through():
    class Broken(ScriptedEngine):
        async def synthesize(self, text: str) -> AsyncIterator[bytes]:
            raise ValueError("hỏng")
            yield b""  # pragma: no cover - makes this an async generator

    tts = _make(Broken())
    with pytest.raises(ValueError, match="hỏng"):
        await _collect(tts.synthesize("abc"))


async def test_aclose_closes_engine_stream():
    # FR-014: skipping a sentence must stop the source from producing the rest.
    engine = ScriptedEngine(chunks=50)
    tts = _make(engine)
    stream = tts.synthesize("abc")
    with anyio.fail_after(5):
        assert await anext(stream) == CHUNK
        await stream.aclose()
    assert engine.closed
    assert engine.produced == 1


async def test_warm_up_and_sample_rate_forwarded():
    engine = ScriptedEngine(sample_rate=24000)
    tts = _make(engine)
    assert tts.sample_rate == 24000
    await tts.warm_up()
    assert engine.warm_ups == 1


async def test_usage_provider_and_zero_start():
    tts = _make(ScriptedEngine())
    assert tts.usage == TTSUsage(provider="gemini")
    assert (tts.usage.requests, tts.usage.chars, tts.usage.quota_errors, tts.usage.rejected_in_cooldown) == (0, 0, 0, 0)


async def test_normalized_text_not_logged_at_info(tts_logs):
    # contracts/events.md §1: spoken text may carry a viewer's name, so it stays at DEBUG at most.
    engine = ScriptedEngine()
    engine.failures.append(TTSEngineError("quota_exhausted", "Hết hạn mức"))
    tts = _make(engine)
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("chị lan"))
    with pytest.raises(TTSEngineError):
        await _collect(tts.synthesize("chị lan"))
    for record in tts_logs:
        if record.levelno >= logging.INFO:
            text = record.getMessage() + repr(getattr(record, "fields", {}))
            assert "CHỊ LAN" not in text and "chị lan" not in text
