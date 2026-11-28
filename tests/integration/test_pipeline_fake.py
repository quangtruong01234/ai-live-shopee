"""T036 fake pipeline (US1; FR-013, FR-020), T061 queue ordering (US2) and T072 latency/session logs (US3).

FakeReplyEngine -> sentence splitter -> guard -> FakeTTS -> StaticRenderer with a fake host.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_live.app.main import create_app
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.author_limits import AuthorLimiter
from ai_live.comments.classifier import PriorityClassifier
from ai_live.comments.filters import CommentFilter
from ai_live.comments.greetings import GreetingReplier, GreetingRules
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
    Milestone,
    Priority,
    QueuedComment,
    TurnOutcome,
)
from ai_live.core.protocols import ReplyEngineError
from ai_live.director.session_log import SessionLog
from ai_live.director.show_director import ShowDirector
from ai_live.products.docx_loader import load_catalog
from ai_live.products.store import DocxProductStore
from ai_live.tts.fake_tts import FakeTTS
from fixtures.content_builder import valid_docx
from fixtures.fake_host import FakeHostConnection

pytestmark = pytest.mark.anyio

REFUSAL_LAN = "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha."
RULES = Path(__file__).resolve().parents[2] / "data" / "rules" / "priority_keywords.json"


def _comment(text: str, author: str = "Lan", cid: str = "c1") -> Comment:
    return Comment(id=cid, source="mock", author=author, text=text, received_at=time.monotonic())


def _queued(comment: Comment, seq: int = 0) -> QueuedComment:
    return QueuedComment(comment=comment, priority=Priority.MEDIUM, seq=seq, status=CommentStatus.WAITING)


class Pipeline:
    def __init__(
        self, engine, *, tts=None, host_ready=True, llm_timeout_s=2.0, tts_timeout_s=2.0, session_log=None
    ) -> None:
        self.bus = EventBus()
        self.queue = InMemoryCommentQueue()
        self.store = DocxProductStore(load_catalog(valid_docx(), "valid.docx", 5_000_000), 5_000_000, self.bus)
        self.renderer = StaticRenderer(ack_timeout_s=1.0, bus=self.bus)
        self.host = FakeHostConnection(self.renderer)
        self.host_ready = host_ready
        self.director = ShowDirector(
            queue=self.queue,
            store=self.store,
            engine=engine,
            tts=tts or FakeTTS(sample_rate=16000),
            renderer=self.renderer,
            bus=self.bus,
            llm_timeout_s=llm_timeout_s,
            tts_timeout_s=tts_timeout_s,
            session_log=session_log,
            llm_model="fake",
        )

    async def connect(self) -> None:
        await self.renderer.attach(self.host)
        if self.host_ready:
            self.renderer.handle_message(self.host, {"type": "ready"})

    def spoken(self) -> list[str]:
        return [m["text"] for m in self.host.json_messages("sentence_start")]


class FlakyEngine:
    """Fails on the first turn, answers normally afterwards."""

    def __init__(self) -> None:
        self.calls = 0
        self.ok = FakeReplyEngine()

    async def reply(self, comment, catalog):
        self.calls += 1
        if self.calls == 1:
            raise ReplyEngineError("api_error", "lỗi giả")
        async for s in self.ok.reply(comment, catalog):
            yield s


async def test_us1_1_price_answer_with_subtitles_per_sentence():
    p = Pipeline(FakeReplyEngine())
    await p.connect()
    async with p.bus.subscribe() as sub:
        utt = await p.director.run_turn(_queued(_comment("giá bao nhiêu vậy shop?")))
        events = sub.drain()

    assert utt.outcome is TurnOutcome.COMPLETED
    text = " ".join(utt.sentences)
    assert "bạn Lan" in text
    assert "250.000đ" in text and "420.000đ" in text
    assert p.spoken() == utt.sentences

    # Each sentence: sentence_start (with subtitle) -> its PCM -> sentence_end, never interleaved with another.
    kinds = ["pcm" if isinstance(m, bytes) else m["type"] for m in p.host.sent]
    i = 0
    for seq in range(len(utt.sentences)):
        assert kinds[i] == "sentence_start" and p.host.sent[i]["seq"] == seq
        i += 1
        assert kinds[i] == "pcm"
        while kinds[i] == "pcm":
            i += 1
        assert kinds[i] == "sentence_end" and p.host.sent[i]["seq"] == seq
        i += 1
    assert i == len(kinds)

    types = [e.type for e in events]
    assert types[0] == EventType.TURN_STARTED
    # `latency` follows every `turn_finished` (contracts/events.md §3).
    assert types[-2:] == [EventType.TURN_FINISHED, EventType.LATENCY]
    sentence_events = [e.payload for e in events if e.type == EventType.SENTENCE]
    assert [s["text"] for s in sentence_events] == utt.sentences
    assert [s["seq"] for s in sentence_events] == list(range(len(utt.sentences)))
    finished = events[-2].payload
    assert finished["outcome"] == "completed"
    assert finished["total_s"] is not None

    assert set(REQUIRED_MILESTONES) <= set(utt.marks)


async def test_us1_3_forbidden_claim_replaced_by_refusal():
    p = Pipeline(FakeReplyEngine("Dạ kem này chữa khỏi mụn luôn nha bạn Lan. Bạn mua ngay nha."))
    await p.connect()
    async with p.bus.subscribe() as sub:
        utt = await p.director.run_turn(_queued(_comment("kem có trị mụn không?")))
        events = sub.drain()

    assert p.spoken() == [REFUSAL_LAN]
    assert utt.outcome is TurnOutcome.COMPLETED
    assert utt.guard_reason is GuardReason.FORBIDDEN_CLAIM
    assert utt.sentences == [REFUSAL_LAN]
    blocked = [e.payload for e in events if e.type == EventType.GUARD_BLOCKED]
    assert blocked == [{"utterance_id": utt.utterance_id, "reason": "forbidden_claim"}]


async def test_us1_4_unknown_amount_after_good_sentence():
    p = Pipeline(FakeReplyEngine("Dạ chào bạn Lan nha. Giá chỉ còn 99k thôi bạn. Mua liền nha."))
    await p.connect()
    utt = await p.director.run_turn(_queued(_comment("giảm còn 99k được không shop?")))

    assert p.spoken() == ["Dạ chào bạn Lan nha.", REFUSAL_LAN]
    assert utt.outcome is TurnOutcome.COMPLETED
    assert utt.guard_reason is GuardReason.UNKNOWN_AMOUNT
    assert "99k" not in " ".join(p.spoken())


async def test_engine_error_marks_turn_error_and_next_comment_answered():
    p = Pipeline(FlakyEngine())
    await p.connect()
    runner = asyncio.create_task(p.director.run())
    try:
        await p.queue.put(_comment("giá bao nhiêu?", cid="c1"), Priority.MEDIUM)
        # Another viewer: a second comment from Lan would replace the first while it waits (001 FR-028).
        await p.queue.put(_comment("giá bao nhiêu vậy shop?", author="Mai", cid="c2"), Priority.MEDIUM)
        for _ in range(200):
            if len(p.director.recent) >= 2:
                break
            await asyncio.sleep(0.01)
    finally:
        runner.cancel()
    first, second = list(p.director.recent)[:2]
    assert first.comment_id == "c1"
    assert first.outcome is TurnOutcome.ERROR
    assert first.error_step is ErrorStep.LLM
    assert second.comment_id == "c2"
    assert second.outcome is TurnOutcome.COMPLETED
    assert "250.000đ" in " ".join(second.sentences)


async def test_llm_timeout_is_llm_error():
    p = Pipeline(FakeReplyEngine(first_delay_s=1.0), llm_timeout_s=0.1)
    await p.connect()
    utt = await p.director.run_turn(_queued(_comment("giá?")))
    assert utt.outcome is TurnOutcome.ERROR
    assert utt.error_step is ErrorStep.LLM
    assert p.spoken() == []


async def test_tts_failure_is_tts_error():
    p = Pipeline(FakeReplyEngine(), tts=FakeTTS(sample_rate=16000, fail=True))
    await p.connect()
    utt = await p.director.run_turn(_queued(_comment("giá?")))
    assert utt.outcome is TurnOutcome.ERROR
    assert utt.error_step is ErrorStep.TTS


async def test_no_host_is_render_error():
    p = Pipeline(FakeReplyEngine(), host_ready=False)
    await p.connect()
    utt = await p.director.run_turn(_queued(_comment("giá?")))
    assert utt.outcome is TurnOutcome.ERROR
    assert utt.error_step is ErrorStep.RENDER


async def test_turn_uses_catalog_snapshot_taken_at_start():
    p = Pipeline(FakeReplyEngine(first_delay_s=0.05))
    await p.connect()
    turn = asyncio.create_task(p.director.run_turn(_queued(_comment("giá?"))))
    await asyncio.sleep(0.01)
    old_version = p.store.catalog.version
    from fixtures.content_builder import build_docx, product_blocks

    p.store.replace(build_docx(product_blocks("Kem khác", price="300.000đ")), "new.docx")
    utt = await turn
    assert utt.catalog_version == old_version
    assert "250.000đ" in " ".join(utt.sentences)


async def test_no_comment_no_turn():
    p = Pipeline(FakeReplyEngine())
    await p.connect()
    async with p.bus.subscribe() as sub:
        runner = asyncio.create_task(p.director.run())
        await asyncio.sleep(0.1)
        runner.cancel()
        events = sub.drain()
    assert p.host.sent == []
    assert not any(e.type == EventType.TURN_STARTED for e in events)
    assert len(p.director.recent) == 0


class RecordingEngine:
    """Records the comments that reach the engine, then answers like FakeReplyEngine."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self.ok = FakeReplyEngine()

    async def reply(self, comment, catalog):
        self.seen.append(comment.text)
        async for s in self.ok.reply(comment, catalog):
            yield s


async def test_us2_queue_order_and_dropped_never_reach_engine():
    engine = RecordingEngine()
    p = Pipeline(engine)
    await p.connect()
    intake = CommentIntake(
        source=MockSource(),
        comment_filter=CommentFilter(banned_words=["vcl"]),
        classifier=PriorityClassifier.from_file(RULES),
        queue=p.queue,
        bus=p.bus,
    )
    # Everything is queued before the director starts, like a paused session.
    results = [
        await intake.submit("Huy", "chào shop"),
        await intake.submit("Mai", "xem ở đây http://spam.vn"),
        await intake.submit("Tú", "chất liệu gì vậy?"),
        await intake.submit("Lan", "giá bao nhiêu?"),
        await intake.submit("Bo", "vcl"),
        await intake.submit("Lan", "giá bao nhiêu?"),
        await intake.submit("Na", "😍😍"),
    ]
    assert [r.drop_reason for r in results] == [
        None,
        DropReason.LINK,
        None,
        None,
        DropReason.PROFANITY,
        DropReason.DUPLICATE,
        DropReason.EMPTY,
    ]
    assert [r.priority for r in results if r.drop_reason is None] == [Priority.LOW, Priority.MEDIUM, Priority.HIGH]

    runner = asyncio.create_task(p.director.run())
    try:
        for _ in range(300):
            if len(p.director.recent) >= 3:
                break
            await asyncio.sleep(0.01)
    finally:
        runner.cancel()
    assert engine.seen == ["giá bao nhiêu?", "chất liệu gì vậy?", "chào shop"]


# ---------- T072: latency milestones and session files (US3; FR-018, FR-019, FR-021, SC-004) ----------

FAKE_KEY = "AIzaSyTEST-not-a-real-key-0123456789abcd"
MILESTONE_ORDER = (
    Milestone.COMMENT_RECEIVED,
    Milestone.TURN_STARTED,
    Milestone.LLM_FIRST_SENTENCE,
    Milestone.TTS_FIRST_CHUNK,
    Milestone.AVATAR_FIRST_FRAME,
)
TURN_LOG_EVENTS = {
    "turn_started",
    "comment_received",
    "llm_first_sentence",
    "tts_first_chunk",
    "avatar_first_frame",
    "turn_finished",
    "turn_error",
    "guard_blocked",
}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def test_us3_1_completed_turns_have_all_milestones_in_order():
    p = Pipeline(FakeReplyEngine())
    await p.connect()
    async with p.bus.subscribe() as sub:
        utts = [await p.director.run_turn(_queued(_comment("giá bao nhiêu?", cid=f"c{i}"), seq=i)) for i in range(3)]
        events = sub.drain()

    for utt in utts:
        assert utt.outcome is TurnOutcome.COMPLETED
        assert set(MILESTONE_ORDER) <= set(utt.marks)
        times = [utt.marks[m] for m in MILESTONE_ORDER]
        assert times == sorted(times), utt.marks
    assert len({u.utterance_id for u in utts}) == 3

    # A `latency` summary follows every `turn_finished` (contracts/events.md §3).
    types = [e.type for e in events]
    finished_at = [i for i, t in enumerate(types) if t == EventType.TURN_FINISHED]
    assert len(finished_at) == 3
    for i in finished_at:
        assert types[i + 1] == EventType.LATENCY
    last = [e.payload for e in events if e.type == EventType.LATENCY][-1]
    assert last["completed"] == 3
    assert last["steps"]["total"]["count"] == 3
    assert p.director.latency.summary().completed == 3


async def test_us3_turn_log_lines_carry_utterance_id(json_log_lines):
    p = Pipeline(FakeReplyEngine("Dạ chào bạn Lan nha. Giá chỉ còn 99k thôi bạn."))
    await p.connect()
    json_log_lines.clear()
    ok = await p.director.run_turn(_queued(_comment("giảm còn 99k được không?")))
    p.director.engine = FlakyEngine()
    failed = await p.director.run_turn(_queued(_comment("giá?", cid="c2")))

    assert ok.outcome is TurnOutcome.COMPLETED and failed.outcome is TurnOutcome.ERROR
    assert json_log_lines
    for line in json_log_lines:
        assert line.get("utterance_id") in (ok.utterance_id, failed.utterance_id), line
    ok_events = {line["event"] for line in json_log_lines if line["utterance_id"] == ok.utterance_id}
    assert {"comment_received", "llm_first_sentence", "tts_first_chunk", "avatar_first_frame"} <= ok_events
    assert {"turn_started", "turn_finished", "guard_blocked"} <= ok_events
    for line in json_log_lines:
        if line["event"] in ("llm_first_sentence", "tts_first_chunk", "avatar_first_frame"):
            assert isinstance(line["t_mono"], float)
    finished = [
        ln for ln in json_log_lines if ln["event"] == "turn_finished" and ln["utterance_id"] == failed.utterance_id
    ]
    assert finished[0]["outcome"] == "error"
    assert finished[0]["error_step"] == "llm"
    assert {line["event"] for line in json_log_lines} <= TURN_LOG_EVENTS


async def test_us3_3_error_turn_marked_and_not_in_summary():
    p = Pipeline(FakeReplyEngine(), tts=FakeTTS(sample_rate=16000, fail=True))
    await p.connect()
    utt = await p.director.run_turn(_queued(_comment("giá?")))
    assert utt.outcome is TurnOutcome.ERROR
    assert utt.error_step is ErrorStep.TTS
    summary = p.director.latency.summary()
    assert summary.errors == 1
    assert summary.completed == 0
    assert summary.steps["total"].count == 0


async def test_us3_session_files_written_by_director(tmp_path):
    log = await SessionLog.open(tmp_path / "sessions", "20261030-100000")
    p = Pipeline(FlakyEngine(), session_log=log)
    await p.connect()
    failed = await p.director.run_turn(_queued(_comment("giá?", cid="c1")))
    ok = await p.director.run_turn(_queued(_comment("giá bao nhiêu vậy shop?", cid="c2"), seq=1))
    await log.close()

    folder = tmp_path / "sessions" / "20261030-100000"
    utterances = _read_jsonl(folder / "utterances.jsonl")
    assert [u["utterance_id"] for u in utterances] == [failed.utterance_id, ok.utterance_id]
    assert utterances[0]["outcome"] == "error" and utterances[0]["error_step"] == "llm"
    done = utterances[1]
    assert done["outcome"] == "completed"
    assert done["comment_id"] == "c2"
    assert done["catalog_version"] == ok.catalog_version
    assert done["llm_model"] == "fake"
    assert done["sentences"] == ok.sentences
    assert done["marks"]["comment_received"] == 0.0
    assert set(done["marks"]) == {m.value for m in MILESTONE_ORDER}
    assert done["total_s"] == done["marks"]["avatar_first_frame"]
    assert done["queue_wait_s"] == done["marks"]["turn_started"]

    comments = _read_jsonl(folder / "comments.jsonl")
    assert [(c["comment_id"], c["status"]) for c in comments] == [("c1", "error"), ("c2", "answered")]
    assert comments[1]["utterance_id"] == ok.utterance_id
    assert comments[1]["author"] == "Lan" and comments[1]["priority"] == "MEDIUM"
    assert comments[1]["received_at"].endswith("Z")

    errors = _read_jsonl(folder / "errors.jsonl")
    assert len(errors) == 1
    assert errors[0]["utterance_id"] == failed.utterance_id
    assert errors[0]["step"] == "llm"
    assert errors[0]["type"] == "api_error"
    assert errors[0]["message"] and errors[0]["ts"]


class BlockedThenAnswer:
    """First turn: the provider blocks the prompt (message carries a key-like string). Then one short sentence."""

    def __init__(self) -> None:
        self.calls = 0

    async def reply(self, comment, catalog):
        self.calls += 1
        if self.calls == 1:
            raise ReplyEngineError("provider_blocked", f"Gemini chặn prompt: SAFETY {FAKE_KEY}")
        yield "Dạ chào bạn Lan nha."


def _ack_one_sentence(host) -> None:
    while True:
        message = host.receive()
        if message.get("text") is None:
            continue
        data = json.loads(message["text"])
        if data["type"] == "sentence_start":
            host.send_json({"type": "playback_started", "utterance_id": data["utterance_id"], "seq": data["seq"]})
        if data["type"] == "sentence_end":
            host.send_json({"type": "sentence_played", "utterance_id": data["utterance_id"], "seq": data["seq"]})
            return


def _wait_until(predicate, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def test_us3_session_files_and_latency_summary_on_shutdown(app_settings):
    settings = app_settings.model_copy(update={"gemini_api_key": SecretStr(FAKE_KEY)})
    with TestClient(create_app(settings, reply_engine=BlockedThenAnswer())) as client:
        with client.websocket_connect("/ws/host") as host:
            host.send_json({"type": "ready"})
            _wait_until(lambda: client.get("/health").json()["host_connected"])
            dropped = client.post("/api/comments", json={"author": "Mai", "text": "xem ở đây http://spam.vn"}).json()
            first = client.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu?"}).json()
            _wait_until(lambda: client.get("/api/latency").json()["errors"] == 1)
            second = client.post("/api/comments", json={"author": "Lan", "text": "chất liệu gì vậy?"}).json()
            _ack_one_sentence(host)
            _wait_until(lambda: client.get("/api/latency").json()["completed"] == 1)

    folders = [d for d in settings.session_data_dir.iterdir() if d.is_dir()]
    assert len(folders) == 1
    folder = folders[0]
    assert {f.name for f in folder.iterdir()} >= {
        "comments.jsonl",
        "utterances.jsonl",
        "errors.jsonl",
        "latency_summary.json",
    }

    comments = {c["comment_id"]: c for c in _read_jsonl(folder / "comments.jsonl")}
    assert comments[dropped["comment_id"]]["status"] == "dropped"
    assert comments[dropped["comment_id"]]["drop_reason"] == "link"
    assert comments[first["comment_id"]]["status"] == "error"
    assert comments[second["comment_id"]]["status"] == "answered"

    utterances = _read_jsonl(folder / "utterances.jsonl")
    assert [u["outcome"] for u in utterances] == ["error", "completed"]
    assert utterances[0]["error_step"] == "llm"

    errors = _read_jsonl(folder / "errors.jsonl")
    assert [(e["step"], e["type"]) for e in errors] == [("llm", "provider_blocked")]
    assert errors[0]["utterance_id"] == utterances[0]["utterance_id"]

    summary = json.loads((folder / "latency_summary.json").read_text(encoding="utf-8"))
    assert summary["session_id"] == folder.name
    assert summary["all"]["idle_only"] is False
    assert summary["idle_only"]["idle_only"] is True
    for mode in ("all", "idle_only"):
        assert summary[mode]["errors"] == 1
        assert summary[mode]["completed"] == 1
        assert set(summary[mode]["steps"]) >= {"total", "queue_wait"}
    assert summary["all"]["steps"]["total"]["count"] == 1

    for path in folder.iterdir():
        text = path.read_text(encoding="utf-8")
        assert FAKE_KEY not in text, path.name
        assert "AIza" not in text, path.name


# ---------- ADR-077: greetings answered from templates, per-viewer spam limit (001 FR-026..FR-028) ----------

GREETINGS = Path(__file__).resolve().parents[2] / "data" / "rules" / "greetings.json"


def _intake_077(p: Pipeline, clock=None) -> CommentIntake:
    limiter = AuthorLimiter(3, 30, 120, clock=clock) if clock is not None else AuthorLimiter(3, 30, 120)
    return CommentIntake(
        source=MockSource(),
        comment_filter=CommentFilter(banned_words=[]),
        classifier=PriorityClassifier.from_file(RULES),
        queue=p.queue,
        bus=p.bus,
        limiter=limiter,
        greetings=GreetingRules.from_file(GREETINGS),
    )


async def test_077_greeting_is_answered_from_template_without_the_llm():
    engine = RecordingEngine()
    p = Pipeline(engine)
    p.director.greeter = GreetingReplier.from_file(GREETINGS)
    await p.connect()
    intake = _intake_077(p)
    first = await intake.submit("Huy", "hi shop")
    again = await intake.submit("Huy", "hello")
    assert first.drop_reason is None and first.comment.meta["kind"] == "greeting"
    assert again.drop_reason is DropReason.GREETED

    queued = await p.queue.get()
    utt = await p.director.run_turn(queued)
    assert utt.outcome is TurnOutcome.COMPLETED
    assert engine.seen == []
    assert "bạn Huy" in utt.sentences[0]
    assert p.spoken() == utt.sentences


async def test_077_spammer_is_muted_and_keeps_one_waiting_comment():
    p = Pipeline(RecordingEngine())
    intake = _intake_077(p)
    results = [await intake.submit("Tú", f"đẹp quá {i}") for i in range(6)]
    assert [r.drop_reason for r in results[3:]] == [DropReason.SPAM] * 3
    # Only the newest accepted comment of Tú waits; a quiet viewer is unaffected.
    other = await intake.submit("Lan", "giá bao nhiêu?")
    assert other.drop_reason is None
    assert [(q.comment.author, q.comment.text) for q in p.queue.snapshot()] == [
        ("Lan", "giá bao nhiêu?"),
        ("Tú", "đẹp quá 2"),
    ]
    assert results[0].drop_reason is None  # accepted at intake, superseded later in the queue


# ---------- ADR-078: the operator blocks a viewer (001 FR-029) ----------


async def test_078_blocked_viewer_is_dropped_and_waiting_comment_removed():
    p = Pipeline(RecordingEngine())
    intake = _intake_077(p)
    await intake.submit("Tú", "giá bao nhiêu?")
    async with p.bus.subscribe() as sub:
        removed = intake.block("tu", 5, author="Tú")
        events = sub.drain()
    assert removed == 1 and p.queue.snapshot() == []
    changed = [e for e in events if e.type is EventType.VIEWERS_CHANGED]
    assert changed[-1].payload["viewers"][0]["kind"] == "manual"

    blocked = await intake.submit("Tú", "còn hàng không?")
    assert blocked.drop_reason is DropReason.BLOCKED
    # A block does not count toward the rate limit: after unblocking, Tú gets a fresh start.
    for i in range(5):
        await intake.submit("Tú", f"x {i}")
    intake.unblock("tu")
    assert intake.viewers() == []
    assert (await intake.submit("Tú", "giá sao shop?")).drop_reason is None
    assert (await intake.submit("Lan", "hi")).drop_reason is None


async def test_078_auto_mute_is_published_for_the_control_page():
    p = Pipeline(RecordingEngine())
    intake = _intake_077(p)
    async with p.bus.subscribe() as sub:
        for i in range(4):
            await intake.submit("Tú", f"đẹp quá {i}")
        events = sub.drain()
    changed = [e for e in events if e.type is EventType.VIEWERS_CHANGED]
    assert len(changed) == 1
    [viewer] = changed[0].payload["viewers"]
    assert (viewer["author_key"], viewer["author"], viewer["kind"]) == ("tu", "Tú", "auto")
    assert 119 < viewer["remaining_s"] <= 120
