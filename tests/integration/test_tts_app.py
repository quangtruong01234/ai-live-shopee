"""T010 (003): the app warms the TTS up at startup and writes `tts_usage.json` at shutdown (contracts/events.md §1, §3).

Startup logs come before any request, and `configure_logging` replaces the handlers of the `ai_live` root, so these
tests listen on the `ai_live.app` child logger, attached before the client starts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_live.app.main import create_app
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.core.events import EventType
from ai_live.core.models import ErrorStep, ShowState, Topic, TurnOutcome
from ai_live.core.protocols import TTSEngineError
from ai_live.director.session_log import SessionLog
from ai_live.tts.fake_tts import FakeTTS
from ai_live.tts.gemini_tts import GeminiTTS
from ai_live.tts.speech import SpeechTTS
from fixtures.fake_gemini_tts import FakeGeminiClient, FakeInteractions
from integration.test_pipeline_fake import Pipeline, _comment, _queued, _read_jsonl
from integration.test_script_runner import TTS_LINES, ScriptRig, _payloads, _row, _starts, wait_until

USAGE_FIELDS = {"provider", "requests", "chars", "quota_errors", "rejected_in_cooldown"}


class CountingTTS:
    """FakeTTS audio with a counted (or failing) warm-up."""

    def __init__(self, *, warm_up_error: TTSEngineError | None = None) -> None:
        self._inner = FakeTTS()
        self.sample_rate = self._inner.sample_rate
        self.warm_up_error = warm_up_error
        self.warm_ups = 0

    async def warm_up(self) -> None:
        self.warm_ups += 1
        if self.warm_up_error is not None:
            raise self.warm_up_error

    def synthesize(self, text: str) -> AsyncIterator[bytes]:
        return self._inner.synthesize(text)


def _wrap(engine: CountingTTS) -> SpeechTTS:
    return SpeechTTS(engine, provider="fake", normalize=lambda text: text, quota_cooldown_s=60)


@pytest.fixture
def app_logs() -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class _Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Keep(level=logging.DEBUG)
    app_logger = logging.getLogger("ai_live.app")
    old_level = app_logger.level
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    yield records
    app_logger.removeHandler(handler)
    app_logger.setLevel(old_level)


def _events(records: list[logging.LogRecord], name: str) -> list[logging.LogRecord]:
    return [r for r in records if r.getMessage() == name]


def test_warm_up_called_once_at_startup_and_logged(app_settings, app_logs):
    engine = CountingTTS()
    with TestClient(create_app(app_settings, tts=_wrap(engine))) as client:
        assert client.get("/health").status_code == 200
        assert engine.warm_ups == 1
    assert engine.warm_ups == 1
    [ready] = _events(app_logs, "tts_ready")
    assert ready.fields["provider"] == "fake"
    assert "voice" in ready.fields
    assert isinstance(ready.fields["warm_up_s"], float)
    assert not _events(app_logs, "tts_warm_up_failed")


def test_warm_up_failure_keeps_app_running(app_settings, app_logs):
    error = TTSEngineError("config_error", "Nguồn giọng chưa sẵn sàng: thiếu model")
    engine = CountingTTS(warm_up_error=error)
    with TestClient(create_app(app_settings, tts=_wrap(engine))) as client:
        assert client.get("/health").status_code == 200
    [failed] = _events(app_logs, "tts_warm_up_failed")
    assert failed.levelno >= logging.WARNING
    assert failed.fields == {"provider": "fake", "kind": "config_error", "message": error.message}
    assert not _events(app_logs, "tts_ready")


def test_usage_file_and_log_written_at_shutdown(app_settings, app_logs):
    with TestClient(create_app(app_settings)) as client:
        session_id = client.app.state.ctx.session_id
    path = app_settings.session_data_dir / session_id / "tts_usage.json"
    usage = json.loads(path.read_text(encoding="utf-8"))
    assert set(usage) == USAGE_FIELDS
    assert usage["provider"] == "fake"
    [logged] = _events(app_logs, "tts_usage")
    assert logged.fields == usage


def test_engine_without_usage_writes_no_usage_file(app_settings):
    # A test or tool may pass a bare engine; only the SpeechTTS wrapper counts usage.
    with TestClient(create_app(app_settings, tts=CountingTTS())) as client:
        session_id = client.app.state.ctx.session_id
    assert not (app_settings.session_data_dir / session_id / "tts_usage.json").exists()


# ---------- T039: the tts step fails, the session goes on (US3 #2, #3, FR-013, FR-014, SC-004) ----------

SESSION = "20261109-100000"
HANG = "hang"


class BreakingTTS:
    """FakeTTS audio that breaks on demand, after the first chunk of a sentence (mid-sentence, like a dropped stream).

    - `armed`: one entry per coming sentence, a `TTSEngineError` to raise or `HANG` to stall forever.
    - `by_marker`: sentences containing the key raise that error (scripted show segments).
    """

    def __init__(self) -> None:
        self._inner = FakeTTS(sample_rate=16000)
        self.sample_rate = 16000
        self.calls: list[str] = []
        self.armed: list[TTSEngineError | str] = []
        self.by_marker: dict[str, TTSEngineError] = {}

    async def warm_up(self) -> None:
        return None

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.calls.append(text)
        failure = self.armed.pop(0) if self.armed else None
        failure = failure or next((e for m, e in self.by_marker.items() if m in text), None)
        async for chunk in self._inner.synthesize(text):
            yield chunk
            if failure == HANG:
                await asyncio.Event().wait()
            if isinstance(failure, TTSEngineError):
                raise failure


def _finished(events: list) -> list[dict]:
    return [e.payload for e in events if e.type is EventType.TURN_FINISHED]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("api_error", "Gemini TTS lỗi HTTP 500: máy chủ lỗi"),
        ("model_error", "VieNeu lỗi khi đọc câu: hết bộ nhớ"),
    ],
)
async def test_tts_error_mid_sentence_fails_one_turn_and_the_next_comment_is_answered(tmp_path, kind, message):
    log = await SessionLog.open(tmp_path / "sessions", SESSION)
    engine = BreakingTTS()
    p = Pipeline(FakeReplyEngine(), tts=_wrap(engine), session_log=log)
    await p.connect()
    answered = 0
    failed_ids: list[str] = []
    async with p.bus.subscribe() as sub:
        for i in range(10):
            engine.armed.append(TTSEngineError(kind, message))
            failed = await p.director.run_turn(_queued(_comment("giá?", cid=f"bad{i}"), seq=2 * i))
            assert (failed.outcome, failed.error_step) == (TurnOutcome.ERROR, ErrorStep.TTS)
            failed_ids.append(failed.utterance_id)
            [finished] = [f for f in _finished(sub.drain()) if f["utterance_id"] == failed.utterance_id]
            # The control page prints "Lỗi ở bước tts: <message>" from this payload (003 contracts/events.md §2).
            assert (finished["error_step"], finished["error_kind"]) == ("tts", kind)
            assert finished["error_message"] == message
            ok = await p.director.run_turn(_queued(_comment("giá bao nhiêu vậy shop?", cid=f"ok{i}"), seq=2 * i + 1))
            answered += ok.outcome is TurnOutcome.COMPLETED
    await log.close()
    assert answered == 10  # SC-004: 10/10

    errors = _read_jsonl(tmp_path / "sessions" / SESSION / "errors.jsonl")
    assert [e["utterance_id"] for e in errors] == failed_ids
    assert {(e["step"], e["type"], e["message"]) for e in errors} == {("tts", kind, message)}


def test_control_page_prints_the_turn_error_message():
    js = (Path(__file__).resolve().parents[2] / "src" / "ai_live" / "app" / "static" / "control.js").read_text("utf-8")
    assert "msg.error_message" in js


@pytest.mark.anyio
async def test_tts_too_slow_is_a_timeout_and_the_next_comment_is_answered():
    engine = BreakingTTS()
    engine.armed.append(HANG)
    p = Pipeline(FakeReplyEngine(), tts=_wrap(engine), tts_timeout_s=0.2)
    await p.connect()
    async with p.bus.subscribe() as sub:
        slow = await p.director.run_turn(_queued(_comment("giá?", cid="c1")))
        [finished] = [f for f in _finished(sub.drain()) if f["utterance_id"] == slow.utterance_id]
    assert (slow.outcome, slow.error_step) == (TurnOutcome.ERROR, ErrorStep.TTS)
    assert (finished["error_kind"], finished["error_message"]) == ("timeout", "TTS quá 0.2 s")
    ok = await p.director.run_turn(_queued(_comment("giá bao nhiêu vậy shop?", cid="c2"), seq=1))
    assert ok.outcome is TurnOutcome.COMPLETED


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.anyio
async def test_quota_exhausted_rejects_during_cooldown_then_tries_the_engine_again():
    engine = BreakingTTS()
    engine.armed.append(TTSEngineError("quota_exhausted", "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí)."))
    clock = _Clock()
    tts = SpeechTTS(engine, provider="gemini", normalize=lambda text: text, quota_cooldown_s=60, clock=clock)
    p = Pipeline(FakeReplyEngine(), tts=tts)
    await p.connect()
    async with p.bus.subscribe() as sub:
        first = await p.director.run_turn(_queued(_comment("giá?", cid="c1")))
        calls = len(engine.calls)
        clock.now += 15
        rejected = await p.director.run_turn(_queued(_comment("giá bao nhiêu vậy shop?", cid="c2"), seq=1))
        finished = {f["utterance_id"]: f for f in _finished(sub.drain())}
    assert (first.outcome, first.error_step) == (TurnOutcome.ERROR, ErrorStep.TTS)
    assert finished[first.utterance_id]["error_kind"] == "quota_exhausted"
    assert finished[first.utterance_id]["error_message"] == (
        "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí). Thử lại sau 60 giây."
    )
    # During the cooldown the turn is turned away at once: the engine is not called and the session does not hang.
    assert (rejected.outcome, rejected.error_step) == (TurnOutcome.ERROR, ErrorStep.TTS)
    assert finished[rejected.utterance_id]["error_message"] == (
        "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí). Thử lại sau 45 giây."
    )
    assert len(engine.calls) == calls

    clock.now += 45
    again = await p.director.run_turn(_queued(_comment("giá bao nhiêu vậy shop?", cid="c3"), seq=2))
    assert again.outcome is TurnOutcome.COMPLETED
    assert len(engine.calls) > calls


@pytest.mark.anyio
async def test_tts_error_in_a_script_segment_drops_one_sentence_and_the_show_goes_on(tmp_path, settings):
    engine = BreakingTTS()
    message = "Gemini TTS lỗi HTTP 500: máy chủ lỗi"
    engine.by_marker["lỗi giọng nói"] = TTSEngineError("api_error", message)
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(script={(None, Topic.OPENING): TTS_LINES}), tts=_wrap(engine))
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 4)
        assert rig.show.state is ShowState.RUNNING
        await rig.stop()

        # The error comes after the first chunk, so the broken sentence had started (004 keeps its row `spoken`,
        # the part that played); the error is still recorded and the next sentence is spoken in full.
        assert rig.started_texts()[:3] == TTS_LINES
        lost = _row(rig, TTS_LINES[1])
        assert _row(rig, TTS_LINES[2])["status"] == "spoken"
        errors = [e for e in rig.jsonl("errors.jsonl") if e.get("utterance_id") == lost["utterance_id"]]
        assert [(e["step"], e["type"], e["message"]) for e in errors] == [("tts", "api_error", message)]
        shown = _payloads(rig.bus_events(), EventType.SHOW_ERROR)
        assert [(p["step"], p["kind"], p["message"]) for p in shown] == [("tts", "api_error", message)]
        segments = rig.jsonl("segments.jsonl")
        opening = next(s for s in segments if s["topic"] == "opening")
        assert opening["status"] == "done"
        # The show went on: the next segment started speaking (stop() then discards it mid-way).
        assert rig.started_texts()[3] not in TTS_LINES
        assert any(s["index"] > opening["index"] and s["started_at"] for s in segments)


@pytest.mark.anyio
async def test_skip_mid_sentence_closes_the_provider_stream():
    interactions = FakeInteractions(hang_after=2)
    gemini = GeminiTTS(client=FakeGeminiClient(interactions), model="gemini-3.8-flash-tts", voice="Leda")
    p = Pipeline(FakeReplyEngine(), tts=_wrap(gemini), tts_timeout_s=5.0)
    await p.connect()
    turn = asyncio.create_task(p.director.run_turn(_queued(_comment("giá?"))))
    await wait_until(lambda: bool(interactions.streams) and bool(p.spoken()))
    assert not interactions.streams[0].closed
    await p.director.skip()
    utt = await asyncio.wait_for(turn, 5)
    assert utt.outcome is TurnOutcome.SKIPPED
    assert interactions.streams[0].closed
