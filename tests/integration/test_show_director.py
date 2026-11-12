"""ShowDirector across turns: T082 content replaced mid-turn (US5; FR-022), T089 session control and fault
tolerance (US4; FR-017, FR-020, SC-005, SC-007) and 004 T069 comments interleaved with a running show (US6;
FR-028 to FR-030, SC-011), 008 T020: comment replies and the show on the model chain (FR-002, FR-005), and 005 T050:
comment replies on the lip-synced character over the fake fork (US2; FR-015 to FR-017, FR-022).

Runs the real `run()` loop with FakeReplyEngine, FakeTTS and StaticRenderer (or 005's `SwitchingRenderer`) over a fake
host page.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.guard import OutputGuard, refusal_sentence
from ai_live.brain.prompt import addressee
from ai_live.brain.sanitize import clean_spoken
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.classifier import PriorityClassifier
from ai_live.comments.filters import CommentFilter
from ai_live.comments.intake import CommentIntake
from ai_live.comments.mock_source import MockSource
from ai_live.core.events import EventBus, EventType
from ai_live.core.models import (
    REQUIRED_MILESTONES,
    Comment,
    CommentStatus,
    DropReason,
    ErrorStep,
    GuardReason,
    Priority,
    Topic,
    TurnOutcome,
    Utterance,
)
from ai_live.director import script_runner as script_runner_module
from ai_live.director.segment_planner import SegmentPlanner
from ai_live.director.session_log import SessionLog
from ai_live.director.show_director import ShowDirector
from ai_live.products.docx_loader import load_catalog
from ai_live.products.store import DocxProductStore
from ai_live.tts.fake_tts import FakeTTS
from fixtures.content_builder import build_docx, product_blocks, valid_docx
from fixtures.fake_fork import FakeFork
from fixtures.fake_host import FakeHostConnection
from fixtures.fake_openai import ChatReply, Disconnect, FakeOpenAI, Role, Text, http_error, stream_reply

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
        make_renderer: Callable[[EventBus], object] | None = None,
        ready_message: dict | None = None,
    ) -> None:
        self.bus = EventBus()
        self.queue = InMemoryCommentQueue(max_age_s=max_age_s, bus=self.bus)
        self.store = DocxProductStore(load_catalog(valid_docx(), "valid.docx", MAX_BYTES), MAX_BYTES, self.bus)
        if make_renderer is not None:
            self.renderer = make_renderer(self.bus)
        else:
            self.renderer = StaticRenderer(ack_timeout_s=ack_timeout_s, bus=self.bus)
        self.host = FakeHostConnection(self.renderer, auto_ack=auto_ack, ack_delay_s=ack_delay_s)
        self.host_ready = host_ready
        self.ready_message = ready_message or {"type": "ready"}
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
            self.renderer.handle_message(self.host, self.ready_message)
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


class PacedTTS(FakeTTS):
    """Sleeps `gaps[i]` before chunk i (the last gap repeats), like a CPU engine that streams slowly."""

    def __init__(self, *gaps: float) -> None:
        super().__init__(sample_rate=16000)
        self.gaps = gaps

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        i = 0
        async for chunk in super().synthesize(text):
            await asyncio.sleep(self.gaps[min(i, len(self.gaps) - 1)])
            i += 1
            yield chunk


async def test_tts_timeout_is_per_chunk_so_a_slow_steady_sentence_is_not_cut():
    # ADR-049: each chunk arrives within TTS_TIMEOUT_S, though the whole sentence takes several times longer.
    rig = Rig(FakeReplyEngine(), tts=PacedTTS(0.03), tts_timeout_s=0.2)
    async with rig:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1, timeout_s=10)
    assert rig.finished[0].outcome is TurnOutcome.COMPLETED


async def test_tts_stall_between_chunks_is_a_timeout():
    rig = Rig(tts=PacedTTS(0.0, 0.0, 1.0), tts_timeout_s=0.2)
    async with rig:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1)
    utt = rig.finished[0]
    assert utt.outcome is TurnOutcome.ERROR and utt.error_step is ErrorStep.TTS


async def test_tts_timeout_does_not_count_waiting_for_the_play_queue():
    # Slow playback blocks the producer on the sentence queue (max 2); that wait is playback, not a TTS fault.
    rig = Rig(SlowStreamEngine(count=5, gap_s=0.0), ack_delay_s=0.3, tts_timeout_s=0.15)
    async with rig:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1, timeout_s=10)
    assert rig.finished[0].outcome is TurnOutcome.COMPLETED
    assert len(rig.finished[0].sentences) == 5


async def test_speak_text_timeout_is_per_chunk():
    rig = Rig(tts=PacedTTS(0.03), tts_timeout_s=0.2)
    async with rig:
        assert await rig.director.speak_text("Dạ câu này đọc chậm mà đều nên không bị cắt giữa chừng nha cả nhà.")


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


# --- T069: comments interleaved with a running show (004 US6; FR-028, FR-029, FR-030, SC-011) ---

SHOW_SESSION_ID = "20261102-090000"
# Markdown and emoji on purpose: the reply path cleans them before the guard (ADR-031, analyze A2).
RAW_REPLY = "**Dạ** em chào bạn {author} nha 😊. Bạn {author} hỏi thêm em nha 👍."
MARKUP = ("**", "😊", "👍")


def _raw_reply(comment, catalog) -> str:
    return RAW_REPLY.format(author=comment.author)


def _cleaned_reply(author: str) -> list[str]:
    splitter = SentenceSplitter()
    raw = [*splitter.feed(RAW_REPLY.format(author=author)), *splitter.flush()]
    return [clean_spoken(s) for s in raw]


def _has_markup(text: str) -> bool:
    return any(mark in text for mark in MARKUP)


class RecordingEngine(FakeReplyEngine):
    """Records when each `reply()` starts streaming and what the host was doing at that moment."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.reply_calls: list[dict] = []
        self.probe: Callable[[], dict] = dict

    async def reply(self, comment, catalog) -> AsyncIterator[str]:
        self.reply_calls.append({"comment_id": comment.id, "at": time.monotonic(), **self.probe()})
        async for sentence in super().reply(comment, catalog):
            yield sentence


class CountingTTS(FakeTTS):
    """Records every synthesis, so a sentence voiced twice (audio not kept) shows up."""

    def __init__(self) -> None:
        super().__init__(sample_rate=16000)
        self.calls: list[tuple[str, float]] = []

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.calls.append((text, time.monotonic()))
        async for chunk in super().synthesize(text):
            yield chunk


class RecordingGuard(OutputGuard):
    def __init__(self) -> None:
        super().__init__()
        self.checked: list[str] = []

    def check(self, sentence, catalog):
        self.checked.append(sentence)
        return super().check(sentence, catalog)


class ShowRig:
    """The app's wiring for a show: intake (filter, priority, queue), the director loop, a running show, drops log."""

    def __init__(
        self,
        tmp_path,
        settings,
        *,
        ack_delay_s: float = 0.15,
        max_age_s: float = 30.0,
        answer=_raw_reply,
        engine=None,
        llm_model: str = "fake",
    ) -> None:
        self.tmp_path = tmp_path
        self.settings = settings.model_copy(
            update={"script_segment_min_sentences": 3, "script_segment_max_sentences": 3, "tts_timeout_s": 1.0}
        )
        self.bus = EventBus()
        self.events = self.bus.subscribe()
        self._drops = self.bus.subscribe()
        self.queue = InMemoryCommentQueue(max_age_s=max_age_s, bus=self.bus)
        self.store = DocxProductStore(load_catalog(valid_docx(), "valid.docx", MAX_BYTES), MAX_BYTES, self.bus)
        self.renderer = StaticRenderer(ack_timeout_s=1.0, bus=self.bus)
        self.host = FakeHostConnection(self.renderer, ack_delay_s=ack_delay_s)
        # `engine`: any ReplyEngine (e.g. the 008 chain); by default the recording fake, which also probes the host.
        self.engine = engine if engine is not None else RecordingEngine(answer)
        if isinstance(self.engine, RecordingEngine):
            self.engine.probe = self._probe
        self.llm_model = llm_model
        self.tts = CountingTTS()
        self.guard = RecordingGuard()
        self.intake = CommentIntake(
            source=MockSource(self.settings.comment_max_chars),
            comment_filter=CommentFilter.from_settings(self.settings),
            classifier=PriorityClassifier.from_settings(self.settings),
            queue=self.queue,
            bus=self.bus,
        )
        self.log: SessionLog | None = None
        self.director: ShowDirector | None = None
        self.show = None
        self._tasks: list[asyncio.Task] = []

    @property
    def folder(self):
        return self.tmp_path / "sessions" / SHOW_SESSION_ID

    async def __aenter__(self) -> ShowRig:
        self.log = await SessionLog.open(self.tmp_path / "sessions", SHOW_SESSION_ID)
        self.director = ShowDirector(
            queue=self.queue,
            store=self.store,
            engine=self.engine,
            tts=self.tts,
            renderer=self.renderer,
            bus=self.bus,
            llm_timeout_s=2.0,
            tts_timeout_s=1.0,
            session_log=self.log,
            llm_model=self.llm_model,
            guard=self.guard,
            settings=self.settings,
        )
        await self.renderer.attach(self.host)
        self.renderer.handle_message(self.host, {"type": "ready"})
        self._tasks = [
            asyncio.create_task(self.director.run()),
            asyncio.create_task(self.queue.run_sweeper(0.05)),
            asyncio.create_task(self.log.record_drops(self._drops)),
        ]
        self.show, _ = await self.director.start_show()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.director.close()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self.log.close()
        aclose = getattr(self.engine, "aclose", None)
        if aclose is not None:
            await aclose()

    def _probe(self) -> dict:
        starts = self.host.json_messages("sentence_start")
        return {"speaking": self.renderer.is_speaking, "last_start": starts[-1]["utterance_id"] if starts else None}

    async def submit(self, author: str, text: str):
        return await self.intake.submit(author, text)

    def starts(self) -> list[dict]:
        return self.host.json_messages("sentence_start")

    def reply_ids(self) -> set[str]:
        ids = {u.utterance_id for u in self.director.recent}
        if self.director.current is not None:
            ids.add(self.director.current.utterance_id)
        return ids

    def product_start(self) -> dict | None:
        """The first `sentence_start` of a product segment (the fake narrates `... của <product>.`)."""
        return next((m for m in self.starts() if " của " in m["text"]), None)

    def script_after_replies(self, count: int) -> bool:
        """`count` reply turns finished and the script then spoke a whole sentence (its gap is logged by then)."""
        if len(self.director.recent) < count or self.director.current is not None:
            return False
        replies = self.reply_ids()
        starts = self.starts()
        heard = [i for i, m in enumerate(starts) if m["utterance_id"] in replies]
        if not heard:
            return False
        after = [m["utterance_id"] for m in starts[heard[-1] + 1 :] if m["utterance_id"] not in replies]
        if not after:
            return False
        status = {ln["utterance_id"]: ln["status"] for ln in self.jsonl("script_sentences.jsonl")}
        return status.get(after[0]) == "spoken"

    def jsonl(self, name: str) -> list[dict]:
        path = self.folder / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]

    def segment_of(self) -> dict[str, str]:
        return {ln["utterance_id"]: ln["segment_id"] for ln in self.jsonl("script_sentences.jsonl")}


def _start_index(starts: list[dict], utterance_id: str) -> int:
    return next(i for i, m in enumerate(starts) if m["utterance_id"] == utterance_id)


def _rotation(rig: ShowRig, count: int) -> list[tuple[str | None, Topic]]:
    planner = SegmentPlanner(rig.store.catalog, rig.settings.script_primary_share)
    return [(slot.product_id, slot.topic) for slot in (planner.next_slot() for _ in range(count))]


def _not_spoken_in_full(rig: ShowRig, starts: list[dict]) -> list[str]:
    """Scripted sentences heard during the test whose status is not `spoken` (e.g. `interrupted`).

    The last one heard is left out: the rig's shutdown may cut it, and that is not the comment's doing.
    """
    status = {ln["utterance_id"]: ln["status"] for ln in rig.jsonl("script_sentences.jsonl")}
    heard = [m["utterance_id"] for m in starts if m["utterance_id"] in status][:-1]
    return [uid for uid in heard if status[uid] != "spoken"]


def _gap_kinds(lines: list[dict], to_utterance_id: str) -> list[str]:
    return [ln["kind"] for ln in lines if ln["event"] == "sentence_gap" and ln["to_utterance_id"] == to_utterance_id]


async def test_comment_lands_after_current_sentence_then_script_resumes(tmp_path, settings, json_log_lines):
    rig = ShowRig(tmp_path, settings)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        interrupted = rig.product_start()
        submitted_at = time.monotonic()
        result = await rig.submit("Lan", "chào shop nha")
        assert result.status is CommentStatus.WAITING
        await wait_until(lambda: rig.script_after_replies(1), 5.0)
        await asyncio.sleep(0.05)
        history = rig.director.history
        starts = rig.starts()

    reply = rig.director.recent[0]
    expected = _cleaned_reply("Lan")
    assert reply.comment_id == result.comment.id and reply.outcome is TurnOutcome.COMPLETED
    assert reply.show_id == rig.show.show_id
    # Cleaned before the guard, and the cleaned text is what is read, shown and logged (ADR-031, analyze A2).
    assert reply.sentences == expected
    assert not any(_has_markup(s) for s in reply.sentences)
    assert not any(_has_markup(s) for s in rig.guard.checked)
    assert [m["text"] for m in starts if m["utterance_id"] == reply.utterance_id] == expected

    # US6 #1, FR-028: the reply's LLM started at once, while the scripted sentence was still speaking...
    call = rig.engine.reply_calls[0]
    assert call["comment_id"] == result.comment.id
    assert call["speaking"] and call["last_start"] == interrupted["utterance_id"]
    # ...but the reply was heard only after that sentence ended; nothing was cut.
    sent = rig.host.sent
    end_of_interrupted = next(
        i
        for i, m in enumerate(sent)
        if isinstance(m, dict) and m.get("type") == "sentence_end" and m["utterance_id"] == interrupted["utterance_id"]
    )
    assert end_of_interrupted < sent.index(starts[_start_index(starts, reply.utterance_id)])
    assert rig.host.json_messages("stop") == []

    # US6 #2, FR-029: right after the reply comes the next sentence of the interrupted segment.
    segment_of = rig.segment_of()
    after = [m["utterance_id"] for m in starts[_start_index(starts, interrupted["utterance_id"]) + 1 :]]
    assert after[: len(expected)] == [reply.utterance_id] * len(expected)
    resumed = after[len(expected)]
    assert segment_of[resumed] == segment_of[interrupted["utterance_id"]]
    assert _not_spoken_in_full(rig, starts) == []

    # Voiced script audio is kept through the reply: the resumed sentence was voiced before the comment came, once.
    resumed_text = next(m["text"] for m in starts if m["utterance_id"] == resumed)
    voiced = [at for text, at in rig.tts.calls if text == resumed_text]
    assert len(voiced) == 1 and voiced[0] < submitted_at
    script_texts = [m["text"] for m in starts if m["utterance_id"] in segment_of]
    assert all(sum(1 for text, _ in rig.tts.calls if text == t) == 1 for t in script_texts)

    # The gap into the resumed sentence is a `comment` gap (research R12), kept out of SC-002; no other one is.
    assert _gap_kinds(json_log_lines, resumed) == ["comment"]
    comment_gaps = [ln for ln in json_log_lines if ln["event"] == "sentence_gap" and ln["kind"] == "comment"]
    assert [g["to_utterance_id"] for g in comment_gaps] == [resumed]

    # FR-030: the reply is in the show's history with the original comment; FR-029: rotation untouched.
    replies = [ln for ln in history.lines if ln.source == "reply"]
    assert [ln.text for ln in replies] == expected
    assert all(ln.comment_text == "chào shop nha" for ln in replies)
    assert all(ln.word_form in history.seen_word_forms for ln in replies)
    product_requests = [
        (r.product_id, r.topic) for r in rig.engine.narrate_requests if r.topic not in (Topic.OPENING, Topic.CLOSING)
    ]
    assert product_requests == _rotation(rig, len(product_requests))

    # US6 #4: the reply has the 001 milestones and joins the show in both files.
    lines = [ln for ln in rig.jsonl("utterances.jsonl") if ln["comment_id"] == result.comment.id]
    assert len(lines) == 1
    line = lines[0]
    assert line["show_id"] == rig.show.show_id
    assert line["sentences"] == expected
    assert all(m.value in line["marks"] for m in REQUIRED_MILESTONES)
    assert line["total_s"] is not None and line["total_s"] < 5.0
    comments = [ln for ln in rig.jsonl("comments.jsonl") if ln["comment_id"] == result.comment.id]
    assert [(c["status"], c["show_id"]) for c in comments] == [("answered", rig.show.show_id)]
    summary = json.loads((rig.folder / f"show_summary_{rig.show.show_id}.json").read_text("utf-8"))
    assert summary["comments"]["answered"] == 1


async def test_several_comments_answered_in_priority_order_before_script(tmp_path, settings, json_log_lines):
    rig = ShowRig(tmp_path, settings)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        interrupted = rig.product_start()
        low = await rig.submit("Mai", "chào shop nha")
        medium = await rig.submit("Hoa", "chất liệu ra sao shop")
        high = await rig.submit("Lan", "giá bao nhiêu vậy shop")
        assert (low.priority, medium.priority, high.priority) == (Priority.LOW, Priority.MEDIUM, Priority.HIGH)
        await wait_until(lambda: rig.script_after_replies(3), 8.0)
        starts = rig.starts()

    answered = list(rig.director.recent)
    assert [u.comment_id for u in answered] == [high.comment.id, medium.comment.id, low.comment.id]
    assert all(u.outcome is TurnOutcome.COMPLETED for u in answered)
    # No scripted sentence between the replies; then the script comes back with the interrupted segment.
    reply_ids = {u.utterance_id for u in answered}
    after = [m["utterance_id"] for m in starts[_start_index(starts, interrupted["utterance_id"]) + 1 :]]
    first_script = next(i for i, uid in enumerate(after) if uid not in reply_ids)
    assert set(after[:first_script]) == reply_ids
    segment_of = rig.segment_of()
    assert segment_of[after[first_script]] == segment_of[interrupted["utterance_id"]]
    assert rig.host.json_messages("stop") == []
    assert _gap_kinds(json_log_lines, after[first_script]) == ["comment"]


async def test_filtered_comment_does_not_interrupt_script(tmp_path, settings, json_log_lines):
    rig = ShowRig(tmp_path, settings)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        before = len(rig.starts())
        result = await rig.submit("Lan", "xem thêm ở https://example.com nha")
        await wait_until(lambda: len(rig.starts()) >= before + 3, 5.0)
        events = rig.events.drain()

    assert result.status is CommentStatus.DROPPED and result.drop_reason is DropReason.LINK
    dropped = [e.payload for e in events if e.type is EventType.COMMENT_DROPPED]
    assert [(d["comment_id"], d["reason"]) for d in dropped] == [(result.comment.id, "link")]
    assert rig.engine.reply_calls == []
    assert not any(e.type is EventType.TURN_STARTED for e in events)
    assert list(rig.director.recent) == []
    assert not any(ln["event"] == "sentence_gap" and ln["kind"] == "comment" for ln in json_log_lines)
    lines = [ln for ln in rig.jsonl("comments.jsonl") if ln["comment_id"] == result.comment.id]
    assert [(ln["status"], ln["drop_reason"]) for ln in lines] == [("dropped", "link")]


async def test_comment_sent_while_paused_is_answered_after_resume_unless_stale(tmp_path, settings):
    rig = ShowRig(tmp_path, settings, ack_delay_s=0.05, max_age_s=0.6)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        rig.director.pause()
        await wait_until(lambda: not rig.renderer.is_speaking, 2.0)
        fresh = await rig.submit("Lan", "chào shop nha")
        await asyncio.sleep(0.3)
        assert rig.engine.reply_calls == []
        assert rig.queue.size() == 1
        heard_before = len(rig.starts())
        resumed_at = time.monotonic()
        rig.director.resume()
        await wait_until(lambda: rig.script_after_replies(1), 5.0)
        # The reply is the first thing heard after resume: the waiting comment holds the script (research R8).
        reply = rig.director.recent[0]
        assert rig.starts()[heard_before]["utterance_id"] == reply.utterance_id
        assert reply.comment_id == fresh.comment.id and reply.outcome is TurnOutcome.COMPLETED
        assert rig.engine.reply_calls[0]["at"] >= resumed_at

        rig.director.pause()
        stale = await rig.submit("Mai", "shop ơi chào em")
        await wait_until(lambda: rig.queue.size() == 0, 3.0)
        rig.director.resume()
        await asyncio.sleep(0.3)
        events = rig.events.drain()

    assert [c["comment_id"] for c in rig.engine.reply_calls] == [fresh.comment.id]
    dropped = [e.payload for e in events if e.type is EventType.COMMENT_DROPPED]
    assert [(d["comment_id"], d["reason"]) for d in dropped] == [(stale.comment.id, "stale")]


async def test_comments_during_closing_or_after_end_are_dropped_show_ended(tmp_path, settings):
    rig = ShowRig(tmp_path, settings, ack_delay_s=0.05)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        show_id, state = rig.director.end_show()
        assert state == "closing"
        closing = await rig.submit("Lan", "chào shop nha")
        await wait_until(lambda: rig.director.show_state == "ended", 5.0)
        ended = await rig.submit("Mai", "giá bao nhiêu vậy shop")
        await wait_until(lambda: rig.queue.size() == 0, 3.0)
        await asyncio.sleep(0.1)
        events = rig.events.drain()

    assert rig.engine.reply_calls == []
    assert list(rig.director.recent) == []
    dropped = [e.payload for e in events if e.type is EventType.COMMENT_DROPPED]
    assert [(d["comment_id"], d["reason"], d.get("show_id")) for d in dropped] == [
        (closing.comment.id, "show_ended", show_id),
        (ended.comment.id, "show_ended", show_id),
    ]
    lines = [ln for ln in rig.jsonl("comments.jsonl") if ln["status"] == "dropped"]
    assert [(ln["comment_id"], ln["drop_reason"], ln["show_id"]) for ln in lines] == [
        (closing.comment.id, "show_ended", show_id),
        (ended.comment.id, "show_ended", show_id),
    ]


async def test_end_while_paused_drops_queued_comment_show_ended(tmp_path, settings):
    rig = ShowRig(tmp_path, settings, ack_delay_s=0.05)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        rig.director.pause()
        queued = await rig.submit("Lan", "chào shop nha")
        show_id, _ = rig.director.end_show()
        await wait_until(lambda: rig.director.show_state == "ended", 5.0)
        await wait_until(lambda: rig.queue.size() == 0, 3.0)
        await asyncio.sleep(0.05)
        events = rig.events.drain()

    assert rig.engine.reply_calls == []
    dropped = [e.payload for e in events if e.type is EventType.COMMENT_DROPPED]
    assert [(d["comment_id"], d["reason"], d.get("show_id")) for d in dropped] == [
        (queued.comment.id, "show_ended", show_id)
    ]


async def test_reply_already_running_at_end_finishes_before_goodbye(tmp_path, settings):
    rig = ShowRig(tmp_path, settings)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        result = await rig.submit("Lan", "chào shop nha")
        await wait_until(lambda: rig.engine.reply_calls != [], 3.0)
        rig.director.end_show()
        await wait_until(lambda: rig.director.show_state == "ended", 5.0)
        starts = rig.starts()

    reply = rig.director.recent[0]
    assert reply.comment_id == result.comment.id and reply.outcome is TurnOutcome.COMPLETED
    assert reply.sentences == _cleaned_reply("Lan")
    closing_ids = {ln["segment_id"] for ln in rig.jsonl("segments.jsonl") if ln["topic"] == "closing"}
    segment_of = rig.segment_of()
    closing_starts = [i for i, m in enumerate(starts) if segment_of.get(m["utterance_id"]) in closing_ids]
    assert closing_starts
    last_reply = max(i for i, m in enumerate(starts) if m["utterance_id"] == reply.utterance_id)
    assert last_reply < closing_starts[0]
    assert rig.host.json_messages("stop") == []


async def test_skip_during_reply_goes_to_next_comment_then_back_to_script(tmp_path, settings):
    rig = ShowRig(tmp_path, settings, ack_delay_s=0.15)
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        interrupted = rig.product_start()
        first = await rig.submit("Lan", "chào shop nha")
        second = await rig.submit("Mai", "shop ơi chào em")

        def reply_speaking(comment_id: str) -> bool:
            current = rig.director.current
            return (
                current is not None
                and current.comment_id == comment_id
                and any(m["utterance_id"] == current.utterance_id for m in rig.starts())
            )

        await wait_until(lambda: reply_speaking(first.comment.id), 3.0)
        skipped_first = await rig.director.skip_current()
        await wait_until(lambda: reply_speaking(second.comment.id), 3.0)
        skipped_second = await rig.director.skip_current()
        await wait_until(lambda: rig.script_after_replies(2), 5.0)
        starts = rig.starts()

    one, two = rig.director.recent
    assert (one.comment_id, one.outcome) == (first.comment.id, TurnOutcome.SKIPPED)
    assert (two.comment_id, two.outcome) == (second.comment.id, TurnOutcome.SKIPPED)
    assert skipped_first == (one.utterance_id, None) and skipped_second == (two.utterance_id, None)
    assert [m["utterance_id"] for m in rig.host.json_messages("stop")] == [one.utterance_id, two.utterance_id]
    # Back to the script: the next sentence of the interrupted segment, and no scripted sentence was cut.
    segment_of = rig.segment_of()
    script_ids = [m["utterance_id"] for m in starts if m["utterance_id"] in segment_of]
    resumed = script_ids[script_ids.index(interrupted["utterance_id"]) + 1]
    assert segment_of[resumed] == segment_of[interrupted["utterance_id"]]
    assert _not_spoken_in_full(rig, starts) == []
    comments = {ln["comment_id"]: ln for ln in rig.jsonl("comments.jsonl")}
    assert (comments[first.comment.id]["status"], comments[first.comment.id]["show_id"]) == (
        "skipped",
        rig.show.show_id,
    )


async def test_ten_comments_at_different_moments_all_answered(tmp_path, settings):
    # SC-011 shape: mid-segment, at segment boundaries, back to back; every one answered and the script comes back.
    rig = ShowRig(tmp_path, settings, ack_delay_s=0.03, answer="Dạ em cảm ơn bạn nha.")
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        ids = []
        for i in range(10):
            result = await rig.submit(f"Khách {i}", f"chào shop lần thứ {i} nha")
            assert result.status is CommentStatus.WAITING
            ids.append(result.comment.id)
            await asyncio.sleep(0.04 * (i % 4))
        await wait_until(lambda: rig.script_after_replies(10), 10.0)
        starts = rig.starts()

    answered = list(rig.director.recent)
    assert sorted(u.comment_id for u in answered) == sorted(ids)
    assert all(u.outcome is TurnOutcome.COMPLETED for u in answered)
    assert all(u.show_id == rig.show.show_id for u in answered)
    assert rig.host.json_messages("stop") == []
    assert _not_spoken_in_full(rig, starts) == []
    totals = [ln["total_s"] for ln in rig.jsonl("utterances.jsonl") if ln["comment_id"] in ids]
    assert len(totals) == 10 and all(t is not None and t < 5.0 for t in totals)


# --- 008 US1: the show and comment replies on the model chain (T020; FR-002, FR-005, US1 #2-#4) ---

SEALION_ROUTE = "cloudflare/gemma-sea-lion-v4-27b"
PRICE_LIE = "Kem chống nắng X giá chỉ 99.000đ thôi ạ."


class SplitProvider:
    """Two fake providers behind one transport: script turns go to `script`, comment replies to `reply`.

    Both use the same entry and model, so they are told apart by `max_tokens` in the request body (`LLM_MAX_TOKENS`
    for `reply()`, `SCRIPT_MAX_TOKENS` for `narrate()`, contracts/adapters.md §2-§3). Each script turn gets new lines,
    so the repeat filter never drops a sentence of the chain.
    """

    def __init__(self, settings, *reply_texts: str) -> None:
        assert settings.llm_max_tokens != settings.script_max_tokens
        self.reply_max_tokens = settings.llm_max_tokens
        entry = settings.llm_chain[0]
        self.base_url, self.model = entry.base_url, entry.model
        self.script = FakeOpenAI()
        self.reply = FakeOpenAI()
        self.script_lines = [
            (
                f"Câu {n} về sản phẩm của shop nha.",
                f"Câu {n} kể thêm chi tiết nha.",
                f"Câu {n} mời cả nhà nghe tiếp nha.",
            )
            for n in range(1, 60)
        ]
        self.script.chat(
            self.base_url,
            self.model,
            *[stream_reply(*(f"{line} " for line in lines), routed_via=SEALION_ROUTE) for lines in self.script_lines],
        )
        self.reply.chat(self.base_url, self.model, stream_reply(*reply_texts, routed_via=SEALION_ROUTE))
        self.transport = httpx.MockTransport(self._handle)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        target = self.reply if body.get("max_tokens") == self.reply_max_tokens else self.script
        return await target.transport.handle_async_request(request)

    @property
    def script_texts(self) -> set[str]:
        return {line for lines in self.script_lines for line in lines}


def _chain_rig(tmp_path, settings, with_chain, make_chain_engine, *reply_texts: str) -> tuple[ShowRig, SplitProvider]:
    chain_settings = with_chain(settings)
    provider = SplitProvider(chain_settings, *reply_texts)
    engine = make_chain_engine(chain_settings, provider.transport)
    return ShowRig(tmp_path, chain_settings, engine=engine, llm_model="chain"), provider


async def test_chain_reply_logs_llm_turn_with_model_and_provider(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    rig, provider = _chain_rig(
        tmp_path, settings, with_chain, make_chain_engine, "Dạ em chào bạn Lan nha. ", "Bạn Lan hỏi thêm em nha."
    )
    async with rig:
        await wait_until(lambda: bool(rig.starts()), 5.0)
        result = await rig.submit("Lan", "chào shop nha")
        await wait_until(lambda: rig.script_after_replies(1), 5.0)

    reply = rig.director.recent[0]
    assert reply.comment_id == result.comment.id and reply.outcome is TurnOutcome.COMPLETED
    assert reply.sentences == ["Dạ em chào bạn Lan nha.", "Bạn Lan hỏi thêm em nha."]
    assert len(provider.reply.chat_requests()) == 1 and provider.reply.unscripted == []
    # FR-005, US1 #3: one `llm_turn` per reply, from the director, tied to the utterance the viewer heard.
    turns = [ln for ln in json_log_lines if ln["event"] == "llm_turn"]
    assert len(turns) == 1
    turn = turns[0]
    assert turn["logger"] == "ai_live.director"
    assert (turn["utterance_id"], turn["comment_id"]) == (reply.utterance_id, result.comment.id)
    first = rig.settings.llm_chain[0]
    assert (turn["label"], turn["model"], turn["provider"]) == (first.label, first.model, SEALION_ROUTE)
    assert (turn["attempts"], turn["outcome"]) == (1, "ok")
    # No key in any log line.
    keys = (rig.settings.freellmapi_key.get_secret_value(), rig.settings.groq_api_key.get_secret_value())
    assert not any(key in json.dumps(ln, ensure_ascii=False) for ln in json_log_lines for key in keys)


async def test_chain_reply_with_an_invented_price_is_blocked_by_the_guard(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    rig, _ = _chain_rig(
        tmp_path, settings, with_chain, make_chain_engine, "Dạ chào bạn Lan nha. ", f"{PRICE_LIE} ", "Bạn Lan chọn nha."
    )
    async with rig:
        await wait_until(lambda: bool(rig.starts()), 5.0)
        result = await rig.submit("Lan", "giá bao nhiêu vậy shop")
        await wait_until(lambda: rig.script_after_replies(1), 5.0)
        starts = rig.starts()

    # US1 #4, FR-002: the same guard as with Gemini; the invented price is never read, the refusal is read instead.
    reply = rig.director.recent[0]
    assert reply.comment_id == result.comment.id
    assert PRICE_LIE in rig.guard.checked
    assert reply.guard_reason is GuardReason.UNKNOWN_AMOUNT
    assert reply.sentences == ["Dạ chào bạn Lan nha.", refusal_sentence(addressee("Lan"))]
    assert not any("99.000" in m["text"] for m in starts)
    blocked = [ln for ln in json_log_lines if ln["event"] == "guard_blocked"]
    assert [(ln["utterance_id"], ln["reason"]) for ln in blocked] == [(reply.utterance_id, "unknown_amount")]


async def test_after_a_chain_reply_the_next_segment_runs_on_the_chain_on_the_next_topic(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    rig, provider = _chain_rig(
        tmp_path, settings, with_chain, make_chain_engine, "Dạ em chào bạn Lan nha. ", "Bạn Lan hỏi thêm em nha."
    )

    def requested() -> list[dict]:
        return [ln for ln in json_log_lines if ln["event"] == "segment_requested"]

    def spoken_in(segment_id: str) -> list[dict]:
        lines = rig.jsonl("script_sentences.jsonl")
        return [ln for ln in lines if ln["segment_id"] == segment_id and ln["status"] == "spoken"]

    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        await rig.submit("Lan", "chào shop nha")
        await wait_until(lambda: rig.script_after_replies(1), 5.0)
        before = len(requested())
        # US1 #2: a segment asked for after the reply is written by the chain and spoken.
        await wait_until(lambda: len(requested()) > before and bool(spoken_in(requested()[before]["segment_id"])), 8.0)
        after = requested()[before]
        spoken = spoken_in(after["segment_id"])
        all_requested = requested()

    assert (after["mode"], after["origin"]) == ("normal", "rotation")
    assert all(ln["source"] == "script" for ln in spoken)
    assert {ln["text"] for ln in spoken} <= provider.script_texts
    assert provider.script.unscripted == [] and provider.reply.unscripted == []
    assert len(provider.reply.chat_requests()) == 1
    # The reply did not move the rotation: product segments follow the planner's order, before and after the reply.
    product = [(ln["product_id"], ln["topic"]) for ln in all_requested if ln["topic"] not in ("opening", "closing")]
    assert product == [(pid, topic.value) for pid, topic in _rotation(rig, len(product))]


# --- 008 US2: the show when entries of the chain fail (T029; FR-012, FR-014, SC-005, SC-006, events.md §3) ---

SEALION, QWEN = 0, 1


def _chain_lines(name: str, segments: int = 40) -> list[tuple[str, ...]]:
    """Three new sentences per segment, tagged with the entry name, so a spoken line tells which entry wrote it."""
    return [
        (
            f"{name} đoạn {n} kể về sản phẩm nha.",
            f"{name} đoạn {n} nói thêm chi tiết nha.",
            f"{name} đoạn {n} mời cả nhà nghe tiếp nha.",
        )
        for n in range(1, segments + 1)
    ]


def _segment_stream(lines: tuple[str, ...], routed_via: str | None = None, *, cut_after: int | None = None):
    """A narrate answer; `cut_after` drops the connection after that many sentences (a mid-segment failure)."""
    if cut_after is None:
        return stream_reply(*(f"{line} " for line in lines), routed_via=routed_via)
    events = [Role(), *(Text(f"{line} ") for line in lines[:cut_after]), Disconnect()]
    return ChatReply(events=events, routed_via=routed_via)


def _chain_show(tmp_path, settings, with_chain, make_chain_engine, fake: FakeOpenAI, **update) -> ShowRig:
    chain_settings = with_chain(settings).model_copy(update=update)
    engine = make_chain_engine(chain_settings, fake.transport)
    return ShowRig(tmp_path, chain_settings, engine=engine, llm_model="chain")


def _spoken_by_segment(rig: ShowRig) -> list[tuple[str, list[str]]]:
    """(segment_id, spoken texts) in the order the segments were heard."""
    texts: dict[str, list[str]] = {}
    for row in rig.jsonl("script_sentences.jsonl"):
        if row["status"] == "spoken":
            texts.setdefault(row["segment_id"], []).append(row["text"])
    return list(texts.items())


def _all_texts(lines: list[tuple[str, ...]]) -> set[str]:
    return {line for segment in lines for line in segment}


def _llm_errors(rig: ShowRig) -> list[dict]:
    return [e for e in rig.jsonl("errors.jsonl") if e["step"] == "llm"]


@pytest.mark.parametrize("engine_kind", ["chain", "gemini"])
async def test_a_chain_with_every_entry_failing_enters_fallback_like_gemini(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines, monkeypatch, engine_kind
):
    monkeypatch.setattr(script_runner_module, "LLM_RETRY_DELAY_S", 0.05)
    fallback_after = 2
    fake = FakeOpenAI()
    sealion, qwen = with_chain(settings).llm_chain[SEALION], with_chain(settings).llm_chain[QWEN]
    if engine_kind == "chain":
        fake.chat(sealion.base_url, sealion.model, http_error(429, code="rate_limited", routed_via=SEALION_ROUTE))
        fake.chat(qwen.base_url, qwen.model, http_error(429, type="rate_limit_exceeded"))
        rig = _chain_show(tmp_path, settings, with_chain, make_chain_engine, fake, script_fallback_after=fallback_after)
    else:
        # The Gemini path as 004 knows it: every narrate() is refused for a rate limit.
        gemini = FakeReplyEngine()
        gemini.fail_next("rate_limited", 100)
        rig = ShowRig(tmp_path, settings.model_copy(update={"script_fallback_after": fallback_after}), engine=gemini)

    def in_fallback() -> bool:
        return any(ln["event"] == "mode_changed" and ln.get("to") == "fallback" for ln in json_log_lines)

    async with rig:
        await wait_until(in_fallback, 8.0)
        mode = rig.director.show_snapshot()["mode"]
        lines = list(json_log_lines)

    # SC-006: exactly SCRIPT_FALLBACK_AFTER failed turns in a row, then fallback, whatever the engine behind it.
    index = next(i for i, ln in enumerate(lines) if ln["event"] == "mode_changed" and ln.get("to") == "fallback")
    errors = [ln for ln in lines[:index] if ln["event"] == "script_error" and ln["step"] == "llm"]
    assert mode == "fallback"
    assert lines[index]["consecutive_failures"] == fallback_after
    assert [e["type"] for e in errors] == ["rate_limited"] * fallback_after
    if engine_kind == "chain":
        # Turn 1 asked each entry once; the next turn found both resting and asked nobody (FR-012).
        assert len(fake.chat_requests(sealion.base_url)) == 1
        assert len(fake.chat_requests(qwen.base_url)) == 1
        assert fake.unscripted == []
        exhausted = [ln for ln in lines[:index] if ln["event"] == "llm_chain_exhausted"]
        assert [ln["kind"] for ln in exhausted] == ["rate_limited"] * fallback_after


async def test_entry_one_failing_mid_segment_ends_that_segment_and_entry_two_speaks_the_next(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    sealion, qwen = with_chain(settings).llm_chain[SEALION], with_chain(settings).llm_chain[QWEN]
    sealion_lines, qwen_lines = _chain_lines("Sư tử"), _chain_lines("Qwen")
    sealion_texts, qwen_texts = _all_texts(sealion_lines), _all_texts(qwen_lines)
    fake = FakeOpenAI()
    fake.chat(
        sealion.base_url,
        sealion.model,
        _segment_stream(sealion_lines[0], SEALION_ROUTE),
        _segment_stream(sealion_lines[1], SEALION_ROUTE, cut_after=2),
    )
    fake.chat(qwen.base_url, qwen.model, *[_segment_stream(lines) for lines in qwen_lines])
    rig = _chain_show(tmp_path, settings, with_chain, make_chain_engine, fake)

    def qwen_segment_heard() -> bool:
        return any(len(texts) == 3 and set(texts) <= qwen_texts for _, texts in _spoken_by_segment(rig))

    async with rig:
        await wait_until(qwen_segment_heard, 8.0)
        lines = list(json_log_lines)

    segments = _spoken_by_segment(rig)
    assert len(segments) >= 3
    (_, opening), (cut_id, cut), (_, after) = segments[:3]
    assert opening == list(sealion_lines[0])
    # US2 #3: the cut segment stops at the last sentence entry 1 sent; nothing of entry 2 is added to it.
    assert cut == list(sealion_lines[1][:2])
    # The next segment is entry 2's, whole.
    assert after == list(qwen_lines[0])
    # SC-005: no segment mixes sentences of the two entries.
    for _, texts in segments:
        assert set(texts) <= sealion_texts or set(texts) <= qwen_texts
    # One LLM error for the cut segment; entry 1 rests, so it is not asked again.
    assert [(e["segment_id"], e["type"]) for e in _llm_errors(rig)] == [(cut_id, "api_error")]
    assert len(fake.chat_requests(sealion.base_url)) == 2
    assert fake.unscripted == []
    rests = [ln for ln in lines if ln["event"] == "llm_entry_rest"]
    assert [(ln["label"], ln["reason"]) for ln in rests] == [(sealion.label, "interrupted")]


async def test_a_sentence_blocked_by_the_guard_does_not_switch_entry(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    sealion, qwen = with_chain(settings).llm_chain[SEALION], with_chain(settings).llm_chain[QWEN]
    lines = _chain_lines("Sư tử")
    # Segment 2 carries an invented price in the middle: the guard blocks that sentence, the entry is still healthy.
    lines[1] = (lines[1][0], PRICE_LIE, lines[1][2])
    fake = FakeOpenAI()
    fake.chat(sealion.base_url, sealion.model, *[_segment_stream(segment, SEALION_ROUTE) for segment in lines])
    fake.chat(qwen.base_url, qwen.model, _segment_stream(_chain_lines("Qwen")[0]))
    rig = _chain_show(tmp_path, settings, with_chain, make_chain_engine, fake)

    async with rig:
        await wait_until(lambda: len(_spoken_by_segment(rig)) >= 3, 8.0)
        rows = rig.jsonl("script_sentences.jsonl")
        log = list(json_log_lines)

    # FR-014, US2 #7: blocked and never read, and the chain stays on entry 1.
    assert [r["raw_text"] for r in rows if r["status"] == "blocked"] == [PRICE_LIE]
    assert not any("99.000" in m["text"] for m in rig.starts())
    assert fake.chat_requests(qwen.base_url) == []
    assert len(fake.chat_requests(sealion.base_url)) >= 3
    assert not any(ln["event"] in ("llm_switch", "llm_entry_rest", "llm_chain_exhausted") for ln in log)
    assert _llm_errors(rig) == []
    # The segment after the blocked one is entry 1's too.
    assert set(_spoken_by_segment(rig)[2][1]) <= _all_texts(lines)


async def test_chain_exhausted_writes_its_kind_and_every_entry_reason_to_errors_jsonl(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines, monkeypatch
):
    monkeypatch.setattr(script_runner_module, "LLM_RETRY_DELAY_S", 0.05)
    sealion, qwen = with_chain(settings).llm_chain[SEALION], with_chain(settings).llm_chain[QWEN]
    fake = FakeOpenAI()
    fake.chat(sealion.base_url, sealion.model, http_error(429, code="rate_limited", routed_via=SEALION_ROUTE))
    fake.chat(qwen.base_url, qwen.model, http_error(503, message="upstream overloaded"))
    rig = _chain_show(tmp_path, settings, with_chain, make_chain_engine, fake)

    async with rig:
        await wait_until(lambda: len(_llm_errors(rig)) >= 2, 8.0)
        raw = (rig.folder / "errors.jsonl").read_text("utf-8")
        log = list(json_log_lines)

    errors = _llm_errors(rig)
    # contracts/events.md §3, research R7: the reasons differ (rate limit + overload), so the kind is `api_error`.
    assert {e["type"] for e in errors} == {"api_error"}
    # Each message names every entry and why it is out, on the turn that asked them and on later turns that found
    # them resting.
    for error in errors:
        message = error["message"]
        assert sealion.label in message and "rate_limited" in message
        assert qwen.label in message and "overloaded" in message
    keys = (rig.settings.freellmapi_key.get_secret_value(), rig.settings.groq_api_key.get_secret_value())
    assert not any(key in raw for key in keys)
    assert not any(key in json.dumps(ln, ensure_ascii=False) for ln in log for key in keys)


async def test_a_comment_reply_on_an_exhausted_chain_writes_its_kind_and_a_redacted_message(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    # T036: the comment path writes the chain's `kind` and message to errors.jsonl like the script path does.
    chain_settings = with_chain(settings)
    sealion, qwen = chain_settings.llm_chain[SEALION], chain_settings.llm_chain[QWEN]
    keys = (chain_settings.freellmapi_key.get_secret_value(), chain_settings.groq_api_key.get_secret_value())
    fake = FakeOpenAI()
    fake.chat(sealion.base_url, sealion.model, http_error(429, code="rate_limited", routed_via=SEALION_ROUTE))
    # A provider that echoes the key it received: the key must not reach any file or log line (research R12).
    fake.chat(qwen.base_url, qwen.model, http_error(503, message=f"upstream overloaded for key {keys[1]}"))
    engine = make_chain_engine(chain_settings, fake.transport)
    log = await SessionLog.open(tmp_path / "sessions", "20261104-100000")
    rig = Rig(engine, session_log=log, llm_timeout_s=4.0)
    async with rig:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1, 5.0)
    await log.close()
    await engine.aclose()

    utt = rig.finished[0]
    assert (utt.outcome, utt.error_step) == (TurnOutcome.ERROR, ErrorStep.LLM)
    raw = (tmp_path / "sessions" / "20261104-100000" / "errors.jsonl").read_text("utf-8")
    errors = [json.loads(line) for line in raw.splitlines()]
    # contracts/events.md §3, research R7: mixed reasons, so `api_error`; the message names each entry and its reason.
    assert [(e["step"], e["type"], e["utterance_id"]) for e in errors] == [("llm", "api_error", utt.utterance_id)]
    message = errors[0]["message"]
    assert sealion.label in message and "rate_limited" in message
    assert qwen.label in message and "overloaded" in message
    assert len(fake.chat_requests(sealion.base_url)) == len(fake.chat_requests(qwen.base_url)) == 1
    assert not any(key in raw for key in keys)
    assert not any(key in json.dumps(ln, ensure_ascii=False) for ln in json_log_lines for key in keys)
    turn_errors = [ln for ln in json_log_lines if ln["event"] == "turn_error"]
    assert [(ln["step"], ln["type"]) for ln in turn_errors] == [("llm", "api_error")]


# --- 008 US3: the show summary on the model chain (T042; FR-018, data-model §7, contracts/events.md §3) ---


def _show_summary(rig: ShowRig) -> dict:
    return json.loads((rig.folder / f"show_summary_{rig.show.show_id}.json").read_text("utf-8"))


async def test_show_summary_llm_chain_is_null_when_the_engine_is_not_the_chain(tmp_path, settings):
    rig = ShowRig(tmp_path, settings)
    async with rig:
        await wait_until(lambda: bool(rig.starts()), 5.0)

    summary = _show_summary(rig)
    assert "llm_chain" in summary and summary["llm_chain"] is None


async def test_show_summary_counts_segments_and_replies_of_the_chain_per_entry(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    rig, _ = _chain_rig(
        tmp_path, settings, with_chain, make_chain_engine, "Dạ em chào bạn Lan nha. ", "Bạn Lan hỏi thêm em nha."
    )
    async with rig:
        await wait_until(lambda: rig.product_start() is not None, 5.0)
        await rig.submit("Lan", "chào shop nha")
        await wait_until(lambda: rig.script_after_replies(1), 5.0)

    sealion, qwen = rig.settings.llm_chain
    section = _show_summary(rig)["llm_chain"]
    assert list(section["entries"]) == [sealion.label, qwen.label]
    first = section["entries"][sealion.label]
    assert first["model"] == sealion.model
    # The comment reply is counted with the segments of the same show (FR-018); the `llm_turn` log stays as in US1.
    assert first["replies"] == 1
    finished = [
        ln
        for ln in json_log_lines
        if ln["event"] == "llm_attempt" and ln["outcome"] == "ok" and ln.get("segment_id") is not None
    ]
    # Opening + at least one product segment; a segment still being written when the show closed is not counted.
    assert 2 <= first["segments"] <= len(finished)
    assert first["failures"] == {}
    assert section["entries"][qwen.label] == {"model": qwen.model, "segments": 0, "replies": 0, "failures": {}}
    assert (section["switches"], section["exhausted"]) == ({}, 0)
    assert len([ln for ln in json_log_lines if ln["event"] == "llm_turn"]) == 1


async def test_show_summary_counts_failures_and_switches_by_reason(
    tmp_path, settings, with_chain, make_chain_engine, json_log_lines
):
    sealion, qwen = with_chain(settings).llm_chain[SEALION], with_chain(settings).llm_chain[QWEN]
    fake = FakeOpenAI()
    fake.chat(sealion.base_url, sealion.model, http_error(429, code="rate_limited", routed_via=SEALION_ROUTE))
    fake.chat(qwen.base_url, qwen.model, *[_segment_stream(lines) for lines in _chain_lines("Qwen")])
    rig = _chain_show(tmp_path, settings, with_chain, make_chain_engine, fake)

    async with rig:
        await wait_until(lambda: len(_spoken_by_segment(rig)) >= 3, 8.0)

    section = _show_summary(rig)["llm_chain"]
    # Entry 1 failed once, then rested (skipped tries are not failures); entry 2 wrote every segment.
    assert section["entries"][sealion.label]["failures"] == {"rate_limited": 1}
    assert section["entries"][sealion.label]["segments"] == 0
    assert section["entries"][qwen.label]["segments"] >= 3
    assert section["entries"][qwen.label]["failures"] == {}
    assert section["switches"] == {"rate_limited": 1}
    assert section["exhausted"] == 0
    switches = [ln for ln in json_log_lines if ln["event"] == "llm_switch"]
    assert len(switches) == 1


# --- 005 T050: comment replies on the lip-synced character over the fake fork (US2; FR-015 to FR-017, FR-022) ---
# `AVATAR_MODE=static` keeps the 004 behaviour (US2 #7, FR-014): the factory returns a bare StaticRenderer, which is
# exactly what `Rig` and `ShowRig` above run on, so those tests cover it. The show itself on the fork (US2 #1) is in
# test_script_runner.py, next to the other ScriptRunner tests.

LIPSYNC_READY = {"type": "ready", "lipsync_session": "sess-1"}


@pytest.fixture
async def fork() -> AsyncIterator[FakeFork]:
    async with FakeFork() as f:
        yield f


class LipsyncRig(Rig):
    """`Rig` with the app's lip-sync wiring: `SwitchingRenderer` over `LiveTalkingRenderer` (fake fork) and the still
    image, the host page reporting its WebRTC session in `ready` (contracts/api.md §4)."""

    def __init__(self, fork: FakeFork, engine=None, *, lead_s: float = 0.0, **kwargs) -> None:
        self.fork = fork

        def make(bus: EventBus) -> SwitchingRenderer:
            static = StaticRenderer(ack_timeout_s=1.0, bus=bus)
            lipsync = LiveTalkingRenderer(
                fork.url,
                static,
                first_frame_timeout_s=1.0,
                ack_timeout_s=1.0,
                reconnect_max_s=0.2,
                lead_s=lead_s,
                bus=bus,
            )
            return SwitchingRenderer(lipsync, static, fallback_after=2, bus=bus)

        super().__init__(engine, make_renderer=make, ready_message=LIPSYNC_READY, **kwargs)

    async def __aenter__(self) -> LipsyncRig:
        await self.renderer.start()
        await super().__aenter__()
        await wait_until(lambda: self.renderer.lipsync.ready)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await super().__aexit__(*exc)
        await self.renderer.stop()

    async def reopen_host(self) -> None:
        """A new host page: attach, `ready` with a session, and wait until the fork link is back."""
        self.host = FakeHostConnection(self.renderer)
        await self.renderer.attach(self.host)
        self.renderer.handle_message(self.host, LIPSYNC_READY)
        await wait_until(lambda: self.renderer.lipsync.ready)

    def subtitles_for(self, utterance_id: str) -> list[str]:
        return [m["text"] for m in self.host.json_messages("subtitle") if m["utterance_id"] == utterance_id]

    def fork_texts_for(self, utterance_id: str) -> list[str]:
        return [s.text for s in self.fork.sentences if s.utterance_id == utterance_id]


def _errors_jsonl(tmp_path, session_id: str) -> list[tuple[str, str, str]]:
    path = tmp_path / "sessions" / session_id / "errors.jsonl"
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []
    return [(e["step"], e["type"], e["utterance_id"]) for e in rows]


async def test_lipsync_comment_reply_is_spoken_by_the_fork_with_subtitles(fork, json_log_lines):
    rig = LipsyncRig(fork, FakeReplyEngine(THREE_SENTENCES))
    async with rig:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1)

    utt = rig.finished[0]
    uid = utt.utterance_id
    assert utt.outcome is TurnOutcome.COMPLETED
    # US2 #2: the character speaks every sentence; the host page shows subtitles only, it plays no audio itself.
    assert rig.fork_texts_for(uid) == utt.sentences == ["Dạ câu một nha.", "Dạ câu hai nha.", "Dạ câu ba nha."]
    assert rig.host.json_messages("sentence_start") == []
    assert rig.host.audio_bytes() == 0
    assert rig.subtitles_for(uid) == utt.sentences
    order = [(m["type"], m["seq"]) for m in rig.host.json_messages() if m["type"] in ("subtitle", "subtitle_clear")]
    assert order == [(kind, seq) for seq in range(3) for kind in ("subtitle", "subtitle_clear")]
    assert set(REQUIRED_MILESTONES) <= set(utt.marks)

    # FR-020: the fork's figures reach the turn's latency record and the `render_stats` log line.
    turn = rig.director.latency.turns[-1]
    assert turn.utterance_id == uid
    assert turn.clips_used == ["talk_01"]
    assert turn.infer_fps == pytest.approx(30.0)
    stats = [ln for ln in json_log_lines if ln["event"] == "render_stats"]
    assert len(stats) == 1
    assert stats[0]["utterance_id"] == uid and stats[0]["clips_used"] == ["talk_01"]
    assert stats[0]["frames"] > 0 and stats[0]["infer_fps"] == pytest.approx(30.0)
    assert rig.renderer.mode.active == "livetalking" and rig.renderer.mode.consecutive_errors == 0


async def test_lipsync_lead_turn_gets_its_figures_after_the_last_sentence_played(fork, json_log_lines):
    # 005 R15: with LIVETALKING_LEAD_S the turn finishes while its last sentence still plays; the figures follow.
    fork.time_scale = 1.0
    fork.stats_delay_s = 0.1
    rig = LipsyncRig(fork, FakeReplyEngine(THREE_SENTENCES), lead_s=0.5)
    async with rig:
        await rig.put("giá bao nhiêu?", "c1")
        await wait_until(lambda: len(rig.finished) >= 1)
        uid = rig.finished[0].utterance_id
        assert rig.director.latency.turns[-1].clips_used is None
        await wait_until(lambda: rig.director.latency.turns[-1].clips_used is not None, 5.0)

    turn = rig.director.latency.turns[-1]
    assert turn.utterance_id == uid and turn.clips_used == ["talk_01"] and turn.render_fps is not None
    [stats] = [ln for ln in json_log_lines if ln["event"] == "render_stats"]
    assert stats["utterance_id"] == uid
    assert stats["frames"] == sum(round(s.duration_s * fork.fps) for s in fork.sentences if s.utterance_id == uid)


async def test_lipsync_skip_stops_the_fork_within_one_second(fork):
    fork.time_scale = 1.0  # real-time playback, so the skip lands mid-sentence
    rig = LipsyncRig(fork, FakeReplyEngine(THREE_SENTENCES))
    async with rig:
        await rig.put("hỏi một", "c1")
        await wait_until(lambda: rig.host.json_messages("subtitle"))
        uid = rig.director.current.utterance_id

        t0 = time.monotonic()
        assert await rig.director.skip(t0) == uid
        await wait_until(lambda: len(rig.finished) >= 1, 1.0)
        assert time.monotonic() - t0 <= 1.0  # SC-004
        await wait_until(lambda: fork.stopped == [uid], 1.0)

        fork.time_scale = 0.0
        await rig.put("hỏi hai", "c2")
        await wait_until(lambda: len(rig.finished) >= 2)

    first, second = rig.finished
    assert first.outcome is TurnOutcome.SKIPPED
    assert {"type": "stop", "utterance_id": uid} in rig.host.json_messages("stop")
    assert rig.fork_texts_for(uid) == ["Dạ câu một nha."]
    # A skip is not a render error: the next turn is still the character's.
    assert second.outcome is TurnOutcome.COMPLETED
    assert rig.fork_texts_for(second.utterance_id) == second.sentences
    assert rig.renderer.mode.active == "livetalking" and rig.renderer.mode.consecutive_errors == 0


async def test_lipsync_render_error_is_logged_with_its_kind_and_the_next_turn_plays(fork, tmp_path):
    log = await SessionLog.open(tmp_path / "sessions", "20261111-100000")
    rig = LipsyncRig(fork, FakeReplyEngine(THREE_SENTENCES), session_log=log)
    async with rig:
        fork.fail_next("vram_oom", "Hết bộ nhớ đồ họa")
        await rig.put("hỏi một", "c1")
        await wait_until(lambda: len(rig.finished) >= 1)
        await rig.put("hỏi hai", "c2")
        await wait_until(lambda: len(rig.finished) >= 2)
    await log.close()

    first, second = rig.finished
    assert first.outcome is TurnOutcome.ERROR
    assert first.error_step is ErrorStep.RENDER and first.error_kind == "vram_oom"
    assert _errors_jsonl(tmp_path, "20261111-100000") == [("render", "vram_oom", first.utterance_id)]
    # US2 #4, SC-005: one bad turn, and the show goes on with the character.
    assert second.outcome is TurnOutcome.COMPLETED
    assert rig.fork_texts_for(second.utterance_id) == second.sentences
    assert rig.renderer.mode.active == "livetalking" and rig.renderer.mode.consecutive_errors == 0


async def test_two_render_error_turns_switch_to_the_still_image_until_the_operator_enables_lipsync(
    fork, json_log_lines
):
    rig = LipsyncRig(fork, FakeReplyEngine("Dạ em trả lời nha."))
    async with rig, rig.bus.subscribe() as sub:
        for i, cid in enumerate(("c1", "c2"), start=1):
            fork.fail_next("inference_failed")
            await rig.put("hỏi lỗi", cid)
            await wait_until(lambda i=i: len(rig.finished) >= i)
        assert rig.renderer.mode.active == "static" and rig.renderer.mode.reason == "render_errors"
        on_fork = len(fork.sentences)

        # US2 #5: the third turn plays on the still image, and the page was told before its first sentence.
        await rig.put("hỏi ba", "c3")
        await wait_until(lambda: len(rig.finished) >= 3)
        third = rig.finished[2]
        assert third.outcome is TurnOutcome.COMPLETED
        assert rig.texts_for(third.utterance_id) == ["Dạ em trả lời nha."]
        assert len(fork.sentences) == on_fork
        sent = rig.host.json_messages()
        to_static = {"type": "mode", "mode": "static", "reason": "render_errors"}
        first_start = next(m for m in sent if m["type"] == "sentence_start")
        assert sent.index(to_static) < sent.index(first_start)

        # US2 #6: the operator turns the character back on; the next turn is the fork's again.
        await rig.renderer.enable_lipsync()
        await rig.put("hỏi bốn", "c4")
        await wait_until(lambda: len(rig.finished) >= 4)
        fourth = rig.finished[3]
        events = sub.drain()

    assert [u.outcome for u in rig.finished[:2]] == [TurnOutcome.ERROR, TurnOutcome.ERROR]
    assert all(u.error_kind == "inference_failed" for u in rig.finished[:2])
    assert fourth.outcome is TurnOutcome.COMPLETED
    assert rig.fork_texts_for(fourth.utterance_id) == ["Dạ em trả lời nha."]
    assert rig.texts_for(fourth.utterance_id) == []
    assert rig.host.json_messages("mode") == [to_static, {"type": "mode", "mode": "livetalking", "reason": None}]
    assert [e.payload["active"] for e in events if e.type == EventType.AVATAR_MODE] == ["static", "livetalking"]
    fallback = [ln for ln in json_log_lines if ln["event"] == "avatar_fallback"]
    assert len(fallback) == 1
    assert fallback[0]["utterance_id"] == rig.finished[1].utterance_id
    assert fallback[0]["consecutive_errors"] == 2 and fallback[0]["last_error_kind"] == "inference_failed"
    # The still image measures no frame rate (FR-020): only the fork's turn logs `render_stats`.
    stats = [ln["utterance_id"] for ln in json_log_lines if ln["event"] == "render_stats"]
    assert stats == [fourth.utterance_id]


async def test_host_page_closed_mid_turn_is_host_unavailable_and_the_next_turn_plays_after_reopen(fork, tmp_path):
    fork.time_scale = 1.0
    log = await SessionLog.open(tmp_path / "sessions", "20261111-110000")
    rig = LipsyncRig(fork, FakeReplyEngine(THREE_SENTENCES), session_log=log)
    async with rig:
        await rig.put("hỏi một", "c1")
        await wait_until(lambda: rig.host.json_messages("subtitle"))
        rig.renderer.detach(rig.host)
        await wait_until(lambda: len(rig.finished) >= 1)
        # Still closed: the next turn fails the same way, without a fork error.
        await rig.put("hỏi hai", "c2")
        await wait_until(lambda: len(rig.finished) >= 2)

        fork.time_scale = 0.0
        await rig.reopen_host()
        await rig.put("hỏi ba", "c3")
        await wait_until(lambda: len(rig.finished) >= 3)
    await log.close()

    first, second, third = rig.finished
    # Edge case "đóng màn hình host giữa lúc nói" (analyze A5): the 001 error, not a lip-sync one (research R10).
    for utt in (first, second):
        assert utt.outcome is TurnOutcome.ERROR
        assert utt.error_step is ErrorStep.RENDER and utt.error_kind == "host_unavailable"
    assert _errors_jsonl(tmp_path, "20261111-110000") == [
        ("render", "host_unavailable", first.utterance_id),
        ("render", "host_unavailable", second.utterance_id),
    ]
    assert third.outcome is TurnOutcome.COMPLETED
    assert rig.fork_texts_for(third.utterance_id) == third.sentences
    # A closed page is not a broken character: no fallback to the still image (data-model §4).
    assert rig.renderer.mode.active == "livetalking" and rig.renderer.mode.consecutive_errors == 0
