"""ShowDirector across turns: T082 content replaced mid-turn (US5; FR-022) and T089 session control and fault
tolerance (US4; FR-017, FR-020, SC-005, SC-007).

Runs the real `run()` loop with FakeReplyEngine, FakeTTS and StaticRenderer over a fake host page.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable

import pytest

from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.core.events import EventBus, EventType
from ai_live.core.models import Comment, ErrorStep, Priority, TurnOutcome, Utterance
from ai_live.director.session_log import SessionLog
from ai_live.director.show_director import ShowDirector
from ai_live.products.docx_loader import load_catalog
from ai_live.products.store import DocxProductStore
from ai_live.tts.fake_tts import FakeTTS
from fixtures.content_builder import build_docx, product_blocks, valid_docx
from fixtures.fake_host import FakeHostConnection

pytestmark = pytest.mark.anyio

MAX_BYTES = 5_000_000
THREE_SENTENCES = "Dạ câu một nha. Dạ câu hai nha. Dạ câu ba nha."


class Rig:
    """A director running its real loop, plus the queue sweeper, against a fake host page."""

    def __init__(
        self,
        engine=None,
        *,
        tts=None,
        host_ready: bool = True,
        auto_ack: bool = True,
        ack_delay_s: float = 0.0,
        ack_timeout_s: float = 1.0,
        llm_timeout_s: float = 1.0,
        tts_timeout_s: float = 1.0,
        max_age_s: float = 30.0,
        session_log: SessionLog | None = None,
    ) -> None:
        self.bus = EventBus()
        self.queue = InMemoryCommentQueue(max_age_s=max_age_s, bus=self.bus)
        self.store = DocxProductStore(load_catalog(valid_docx(), "valid.docx", MAX_BYTES), MAX_BYTES, self.bus)
        self.renderer = StaticRenderer(ack_timeout_s=ack_timeout_s, bus=self.bus)
        self.host = FakeHostConnection(self.renderer, auto_ack=auto_ack, ack_delay_s=ack_delay_s)
        self.host_ready = host_ready
        self.director = ShowDirector(
            queue=self.queue,
            store=self.store,
            engine=engine or FakeReplyEngine(),
            tts=tts or FakeTTS(sample_rate=16000),
            renderer=self.renderer,
            bus=self.bus,
            llm_timeout_s=llm_timeout_s,
            tts_timeout_s=tts_timeout_s,
            session_log=session_log,
            llm_model="fake",
        )
        self._tasks: list[asyncio.Task] = []

    async def __aenter__(self) -> Rig:
        await self.renderer.attach(self.host)
        if self.host_ready:
            self.renderer.handle_message(self.host, {"type": "ready"})
        self._tasks = [
            asyncio.create_task(self.director.run()),
            asyncio.create_task(self.queue.run_sweeper(0.05)),
        ]
        return self

    async def __aexit__(self, *exc: object) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def put(
        self, text: str, cid: str, priority: Priority = Priority.MEDIUM, *, author: str = "Lan", age_s: float = 0.0
    ) -> None:
        comment = Comment(id=cid, source="mock", author=author, text=text, received_at=time.monotonic() - age_s)
        await self.queue.put(comment, priority)

    @property
    def finished(self) -> list[Utterance]:
        return list(self.director.recent)

    def texts_for(self, utterance_id: str) -> list[str]:
        return [m["text"] for m in self.host.json_messages("sentence_start") if m["utterance_id"] == utterance_id]


async def wait_until(predicate: Callable[[], bool], timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


def _applied(lines: list[dict], command: str) -> list[dict]:
    return [ln for ln in lines if ln["event"] == "control_applied" and ln["command"] == command]


# --- T082: content replaced mid-turn (FR-022) ---


async def test_content_replaced_mid_turn_applies_from_next_turn():
    rig = Rig(FakeReplyEngine(first_delay_s=0.1))
    async with rig:
        old_version = rig.store.catalog.version
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: rig.director.current is not None)
        rig.store.replace(build_docx(product_blocks("Kem khác", price="300.000đ")), "new.docx")
        await rig.put("giá bao nhiêu vậy shop?", "c2")
        await wait_until(lambda: len(rig.finished) >= 2)

    first, second = rig.finished
    assert first.comment_id == "c1" and first.catalog_version == old_version
    assert "250.000đ" in " ".join(first.sentences)
    assert "300.000đ" not in " ".join(first.sentences)
    assert second.comment_id == "c2" and second.catalog_version == rig.store.catalog.version != old_version
    assert "300.000đ" in " ".join(second.sentences)


# --- T089: skip (US4 #1; SC-007) ---


async def test_skip_while_speaking_interrupts_and_takes_next_comment(json_log_lines):
    rig = Rig(FakeReplyEngine(THREE_SENTENCES), auto_ack=False)
    async with rig, rig.bus.subscribe() as sub:
        await rig.put("hỏi một", "c1")
        await wait_until(lambda: rig.renderer.is_speaking)
        utterance_id = rig.director.current.utterance_id
        rig.host.auto_ack = True  # from now on the host acks, so the next turn can finish

        t0 = time.monotonic()
        skipped = await rig.director.skip(t0)
        assert time.monotonic() - t0 < 1.0
        assert skipped == utterance_id

        await rig.put("hỏi hai", "c2")
        await wait_until(lambda: len(rig.finished) >= 2)
        events = sub.drain()

    first, second = rig.finished
    assert first.utterance_id == utterance_id and first.outcome is TurnOutcome.SKIPPED
    assert second.comment_id == "c2" and second.outcome is TurnOutcome.COMPLETED
    # renderer.interrupt() told the host to stop, and nothing more of the skipped turn was sent.
    assert rig.host.json_messages("stop") == [{"type": "stop", "utterance_id": utterance_id}]
    assert rig.texts_for(utterance_id) == ["Dạ câu một nha."]
    finished = [e.payload for e in events if e.type == EventType.TURN_FINISHED]
    assert finished[0]["utterance_id"] == utterance_id and finished[0]["outcome"] == "skipped"

    applied = _applied(json_log_lines, "skip")
    assert len(applied) == 1
    assert applied[0]["utterance_id"] == utterance_id
    assert 0 <= applied[0]["latency_ms"] <= 1000


async def test_skip_with_nothing_speaking_returns_none():
    rig = Rig()
    async with rig:
        assert await rig.director.skip(time.monotonic()) is None
    assert rig.host.json_messages("stop") == []
    assert rig.finished == []


# --- T089: pause and resume (US4 #2, #3; SC-007) ---


async def test_pause_finishes_current_turn_and_starts_no_new_one(json_log_lines):
    rig = Rig(FakeReplyEngine(THREE_SENTENCES), ack_delay_s=0.05, max_age_s=1.0)
    async with rig, rig.bus.subscribe() as sub:
        await rig.put("hỏi một", "c1")
        await wait_until(lambda: rig.renderer.is_speaking)
        assert rig.director.pause(time.monotonic()) == "paused"
        assert rig.director.state == "paused"

        await rig.put("hỏi hai", "c2")
        await rig.put("hỏi ba", "c3", age_s=0.9)  # goes stale while paused
        await wait_until(lambda: len(rig.finished) >= 1)
        await asyncio.sleep(0.3)
        events = sub.drain()
        waiting = [q.comment.id for q in rig.queue.snapshot()]

    assert len(rig.finished) == 1
    first = rig.finished[0]
    assert first.comment_id == "c1" and first.outcome is TurnOutcome.COMPLETED
    assert first.sentences == ["Dạ câu một nha.", "Dạ câu hai nha.", "Dạ câu ba nha."]
    # Comments still queue during a pause, and the stale sweep still runs.
    assert waiting == ["c2"]
    dropped = [e.payload for e in events if e.type == EventType.COMMENT_DROPPED]
    assert [(d["comment_id"], d["reason"]) for d in dropped] == [("c3", "stale")]
    assert [e.payload["state"] for e in events if e.type == EventType.SESSION_STATE] == ["paused"]
    assert [e.payload["comment_id"] for e in events if e.type == EventType.TURN_STARTED] == ["c1"]

    applied = _applied(json_log_lines, "pause")
    assert len(applied) == 1 and 0 <= applied[0]["latency_ms"] <= 1000
    after = json_log_lines[json_log_lines.index(applied[0]) :]
    assert not any(ln["event"] == "turn_started" for ln in after)


async def test_resume_answers_highest_priority_first(json_log_lines):
    rig = Rig(FakeReplyEngine("Dạ em trả lời nha."))
    async with rig, rig.bus.subscribe() as sub:
        # Paused while idle: the loop is blocked waiting for a comment and must not take the next one.
        rig.director.pause(time.monotonic())
        assert rig.director.pause(time.monotonic()) == "paused"  # idempotent
        await rig.put("chào shop", "c-low", Priority.LOW)
        await rig.put("giá bao nhiêu?", "c-high", Priority.HIGH)
        await asyncio.sleep(0.2)
        assert rig.finished == []
        assert rig.queue.size() == 2

        assert rig.director.resume(time.monotonic()) == "running"
        assert rig.director.resume(time.monotonic()) == "running"  # idempotent
        assert rig.director.state == "running"
        await wait_until(lambda: len(rig.finished) >= 2)
        events = sub.drain()

    assert [u.comment_id for u in rig.finished] == ["c-high", "c-low"]
    assert [e.payload["state"] for e in events if e.type == EventType.SESSION_STATE] == ["paused", "running"]
    for command in ("pause", "resume"):
        applied = _applied(json_log_lines, command)
        assert len(applied) == 1, command
        assert 0 <= applied[0]["latency_ms"] <= 1000


# --- T089: timeouts and host errors end only that turn (FR-020) ---


class SlowStreamEngine:
    """Each sentence arrives in time, but the whole stream takes longer than LLM_TIMEOUT_S."""

    def __init__(self, count: int = 8, gap_s: float = 0.06) -> None:
        self.count = count
        self.gap_s = gap_s

    async def reply(self, comment, catalog) -> AsyncIterator[str]:
        for i in range(self.count):
            await asyncio.sleep(self.gap_s)
            yield f"Dạ câu số {i + 1} nha."


@pytest.mark.parametrize(
    ("rig_kwargs", "step", "kind"),
    [
        pytest.param(
            {"engine": FakeReplyEngine(first_delay_s=1.0), "llm_timeout_s": 0.1}, "llm", "timeout", id="llm-first"
        ),
        pytest.param({"engine": SlowStreamEngine(), "llm_timeout_s": 0.2}, "llm", "timeout", id="llm-stream"),
        pytest.param(
            {"tts": FakeTTS(sample_rate=16000, delay_ms=500), "tts_timeout_s": 0.1}, "tts", "timeout", id="tts"
        ),
        pytest.param({"auto_ack": False, "ack_timeout_s": 0.1}, "render", "timeout", id="render-ack"),
        pytest.param({"host_ready": False}, "render", "host_unavailable", id="no-host"),
    ],
)
async def test_step_timeout_ends_turn_with_error_and_next_is_answered(tmp_path, rig_kwargs, step, kind):
    log = await SessionLog.open(tmp_path / "sessions", "20261031-100000")
    rig = Rig(session_log=log, **rig_kwargs)
    async with rig, rig.bus.subscribe() as sub:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1)
        events = sub.drain()
    await log.close()

    utt = rig.finished[0]
    assert utt.outcome is TurnOutcome.ERROR
    assert utt.error_step is ErrorStep(step)
    finished = [e.payload for e in events if e.type == EventType.TURN_FINISHED]
    assert finished[0]["outcome"] == "error" and finished[0]["error_step"] == step
    errors = [
        json.loads(line)
        for line in (tmp_path / "sessions" / "20261031-100000" / "errors.jsonl").read_text("utf-8").splitlines()
    ]
    assert [(e["step"], e["type"], e["utterance_id"]) for e in errors] == [(step, kind, utt.utterance_id)]


async def test_llm_stream_timeout_counts_llm_time_not_playback():
    # Slow playback blocks the producer on the sentence queue; that wait must not count against LLM_TIMEOUT_S.
    rig = Rig(SlowStreamEngine(count=4, gap_s=0.01), ack_delay_s=0.1, llm_timeout_s=0.2)
    async with rig:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1)
    assert rig.finished[0].outcome is TurnOutcome.COMPLETED
    assert len(rig.finished[0].sentences) == 4


# --- T089: injected faults (SC-005) ---


@pytest.mark.parametrize("step", ["llm", "tts", "render"])
@pytest.mark.parametrize("mode", ["error", "timeout"])
async def test_injected_fault_fails_next_turn_at_that_step(json_log_lines, step, mode):
    rig = Rig(llm_timeout_s=0.2, tts_timeout_s=0.2, ack_timeout_s=0.2)
    async with rig:
        rig.director.inject_fault(step, mode, 1)
        await rig.put("giá bao nhiêu?", "c1")
        await rig.put("giá bao nhiêu vậy shop?", "c2")
        await wait_until(lambda: len(rig.finished) >= 2)

    failed, ok = rig.finished
    assert failed.outcome is TurnOutcome.ERROR and failed.error_step is ErrorStep(step)
    assert ok.outcome is TurnOutcome.COMPLETED
    error_lines = [ln for ln in json_log_lines if ln["event"] == "turn_error"]
    assert [(ln["step"], ln["type"]) for ln in error_lines] == [
        (step, "timeout" if mode == "timeout" else "fault_injected")
    ]


async def test_three_faults_in_a_row_then_normal_comment_answered():
    rig = Rig(llm_timeout_s=0.2, tts_timeout_s=0.2)
    async with rig:
        rig.director.inject_fault("llm", "error", 1)
        rig.director.inject_fault("tts", "timeout", 1)
        rig.director.inject_fault("render", "error", 1)
        for i in range(4):
            await rig.put("giá bao nhiêu?", f"c{i}")
        await wait_until(lambda: len(rig.finished) >= 4)

    assert [(u.outcome, u.error_step) for u in rig.finished] == [
        (TurnOutcome.ERROR, ErrorStep.LLM),
        (TurnOutcome.ERROR, ErrorStep.TTS),
        (TurnOutcome.ERROR, ErrorStep.RENDER),
        (TurnOutcome.COMPLETED, None),
    ]
    assert "250.000đ" in " ".join(rig.finished[3].sentences)


async def test_fault_count_covers_that_many_turns():
    rig = Rig()
    async with rig:
        rig.director.inject_fault("llm", "error", 2)
        for i in range(3):
            await rig.put("giá bao nhiêu?", f"c{i}")
        await wait_until(lambda: len(rig.finished) >= 3)
    assert [u.outcome for u in rig.finished] == [TurnOutcome.ERROR, TurnOutcome.ERROR, TurnOutcome.COMPLETED]
