"""T023 ScriptRunner, normal run (004 US1; FR-002, FR-007, FR-008, FR-011, FR-022, research R7, R9, R12).

Runs the real three-stage runner with FakeReplyEngine, FakeTTS and StaticRenderer over a fake host page, then checks
the host messages, bus events, JSON log lines and session files (contracts/events.md).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.guard import OutputGuard
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.core.events import EventBus, EventType
from ai_live.core.models import (
    REQUIRED_SCRIPT_MILESTONES,
    RenderTurnStats,
    ShowMode,
    ShowSession,
    ShowState,
    Topic,
)
from ai_live.core.protocols import ReplyEngineError
from ai_live.director.faults import FaultInjector
from ai_live.director.script_runner import CLOSING_FALLBACK_SENTENCE, ScriptRunner
from ai_live.director.segment_planner import SegmentPlanner
from ai_live.director.session_log import SessionLog
from ai_live.director.show_stats import ShowStats
from ai_live.products.docx_loader import load_catalog
from ai_live.products.store import DocxProductStore
from ai_live.tts.fake_tts import FakeTTS, FakeTTSError
from fixtures.content_builder import build_docx, product_blocks, valid_docx
from fixtures.fake_fork import FakeFork
from fixtures.fake_host import FakeHostConnection

pytestmark = pytest.mark.anyio

MAX_BYTES = 5_000_000
SESSION_ID = "20261101-090000"
SHOW_ID = "show-test"


class NoComments:
    """Interleave gate of a show with no comment traffic (contracts/adapters.md §6)."""

    def pending(self) -> bool:
        return False

    async def wait_clear(self) -> None:
        return None


class ScriptRig:
    """A running ScriptRunner and everything it talks to."""

    def __init__(
        self,
        tmp_path: Path,
        settings,
        engine: FakeReplyEngine,
        *,
        ack_delay_s: float = 0.0,
        settings_update: dict | None = None,
        tts=None,
        host_factory: Callable[..., FakeHostConnection] = FakeHostConnection,
        ack_timeout_s: float = 1.0,
        wall_clock: Callable[[], datetime] | None = None,
        make_renderer: Callable[[EventBus, float], StaticRenderer | SwitchingRenderer] | None = None,
        ready_message: dict | None = None,
        interleave=None,
    ) -> None:
        self.tmp_path = tmp_path
        self.interleave = interleave if interleave is not None else NoComments()
        self.settings = settings.model_copy(
            update={
                "script_segment_min_sentences": 2,
                "script_segment_max_sentences": 3,
                "tts_timeout_s": 1.0,
                **(settings_update or {}),
            }
        )
        self.engine = engine
        self.bus = EventBus()
        self.events = self.bus.subscribe()
        self.store = DocxProductStore(load_catalog(valid_docx(), "valid.docx", MAX_BYTES), MAX_BYTES, self.bus)
        self.catalog = self.store.catalog
        if make_renderer is not None:
            self.renderer = make_renderer(self.bus, ack_timeout_s)
        else:
            self.renderer = StaticRenderer(ack_timeout_s=ack_timeout_s, bus=self.bus)
        self.ready_message = ready_message or {"type": "ready"}
        self.host = host_factory(self.renderer, ack_delay_s=ack_delay_s)
        self.planner = SegmentPlanner(self.catalog, self.settings.script_primary_share)
        self.show = ShowSession(
            show_id=SHOW_ID,
            session_id=SESSION_ID,
            start_requested_at=time.monotonic(),
            catalog_version=self.catalog.version,
            state=ShowState.RUNNING,
        )
        self.stats = ShowStats(SHOW_ID, SESSION_ID, self.catalog)
        self.faults = FaultInjector()
        self.tts = tts if tts is not None else FakeTTS(sample_rate=16000)
        self.wall_clock = wall_clock
        self.log: SessionLog | None = None
        self.runner: ScriptRunner | None = None
        self._task: asyncio.Task | None = None

    @property
    def folder(self) -> Path:
        return self.tmp_path / "sessions" / SESSION_ID

    async def __aenter__(self) -> ScriptRig:
        self.log = await SessionLog.open(self.tmp_path / "sessions", SESSION_ID)
        extra = {"wall_clock": self.wall_clock} if self.wall_clock is not None else {}
        self.runner = ScriptRunner(
            show=self.show,
            planner=self.planner,
            engine=self.engine,
            guard=OutputGuard(),
            tts=self.tts,
            renderer=self.renderer,
            store=self.store,
            floor=asyncio.Lock(),
            interleave=self.interleave,
            faults=self.faults,
            stats=self.stats,
            log=self.log,
            bus=self.bus,
            settings=self.settings,
            **extra,
        )
        # A failed segment waits before the next LLM call; tests keep that short.
        self.runner.llm_retry_delay_s = 0.05
        await self.renderer.attach(self.host)
        self.renderer.handle_message(self.host, self.ready_message)
        self._task = asyncio.create_task(self.runner.run())
        return self

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self.log is not None:
            await self.log.flush()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()
        if self.log is not None:
            await self.log.close()

    def started_texts(self) -> list[str]:
        return [m["text"] for m in self.host.json_messages("sentence_start")]

    def jsonl(self, name: str) -> list[dict]:
        path = self.folder / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]

    def bus_events(self) -> list:
        return self.events.drain()


async def wait_until(predicate: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


def _events(lines: list[dict], name: str) -> list[dict]:
    return [ln for ln in lines if ln.get("event") == name]


def _first_slot(rig: ScriptRig):
    """The first rotation slot after the opening, read before the runner consumes it."""
    return rig.planner.peek_slot()


# --- opening, one utterance per sentence, milestones, files ---


async def test_opening_first_and_each_sentence_is_its_own_utterance(tmp_path, settings, json_log_lines):
    engine = FakeReplyEngine()
    rig = ScriptRig(tmp_path, settings, engine)
    first_slot = _first_slot(rig)
    async with rig:
        await wait_until(lambda: len(rig.host.json_messages("sentence_start")) >= 6)
        await rig.stop()

        starts = rig.host.json_messages("sentence_start")
        assert all(m["seq"] == 0 for m in starts)  # FR-008: one sentence per utterance
        ids = [m["utterance_id"] for m in starts]
        assert len(set(ids)) == len(ids)

        # FR-002: the show opens with `opening`; then the planner's rotation.
        requests = engine.narrate_requests
        assert requests[0].topic is Topic.OPENING
        assert requests[0].product_id is None
        assert (requests[1].product_id, requests[1].topic) == (first_slot.product_id, first_slot.topic)
        assert all(r.min_sentences == 2 and r.max_sentences == 3 for r in requests)

        events = rig.bus_events()
        started = [e.payload for e in events if e.type is EventType.SEGMENT_STARTED]
        assert started[0]["topic"] == "opening"
        assert started[0].get("product_id") is None
        assert started[0]["topic_label"] == Topic.OPENING.label
        sentence_events = [e.payload for e in events if e.type is EventType.SENTENCE]
        assert sentence_events and all(p.get("segment_id") for p in sentence_events)
        # The 001 latency table keeps meaning comment turns only (contracts/events.md §3).
        assert not [e for e in events if e.type in (EventType.TURN_STARTED, EventType.TURN_FINISHED)]

        # FR-022: each spoken sentence logs the milestones with its ids.
        for name in ("llm_first_sentence", "tts_first_chunk", "avatar_first_frame"):
            lines = [ln for ln in _events(json_log_lines, name) if ln.get("utterance_id") in ids]
            assert {ln["utterance_id"] for ln in lines} >= set(ids[:4])
            assert all(ln.get("segment_id") and ln.get("show_id") == SHOW_ID for ln in lines)
            assert all("t_mono" in ln for ln in lines)
        requested = _events(json_log_lines, "segment_requested")
        assert requested[0]["topic"] == "opening"
        assert all(ln.get("show_id") == SHOW_ID and ln.get("segment_id") for ln in requested)

        sentences = rig.jsonl("script_sentences.jsonl")
        spoken = [s for s in sentences if s["status"] == "spoken"]
        assert {s["utterance_id"] for s in spoken} >= set(ids[:4])
        for s in spoken:
            assert set(s["marks"]) >= {m.value for m in REQUIRED_SCRIPT_MILESTONES}
            assert s["marks"]["segment_requested"] == 0.0  # stored relative to segment_requested
            assert s["played_at"] >= s["marks"]["avatar_first_frame"]
            assert s["source"] == "script"
        assert set(sentences[0]) >= {
            "utterance_id",
            "segment_id",
            "seq",
            "source",
            "text",
            "raw_text",
            "status",
            "guard_reason",
            "guard_detail",
            "drop_reason",
            "marks",
            "played_at",
        }

        segments = rig.jsonl("segments.jsonl")
        assert segments, "a finished segment writes a segments.jsonl line"
        assert segments[0]["topic"] == "opening"
        assert segments[0]["status"] == "done"
        assert segments[0]["show_id"] == SHOW_ID
        assert segments[0]["sentences"]["spoken"] == 2
        assert set(segments[0]) >= {
            "segment_id",
            "show_id",
            "index",
            "product_id",
            "topic",
            "origin",
            "mode",
            "catalog_version",
            "status",
            "requested_at",
            "started_at",
            "finished_at",
            "sentences",
            "error_step",
            "error_kind",
        }
        assert set(segments[0]["sentences"]) >= {"spoken", "blocked", "dropped", "tts_error"}

        # The summary is written in `finally`, even when the app cancels the runner.
        summary = json.loads((rig.folder / f"show_summary_{SHOW_ID}.json").read_text("utf-8"))
        assert summary["show_id"] == SHOW_ID
        assert summary["sentences"]["spoken"] >= 4


async def test_sentence_gaps_are_script_or_segment_boundary(tmp_path, settings, json_log_lines):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine())
    async with rig:
        await wait_until(lambda: len(rig.host.json_messages("sentence_start")) >= 7)
        await rig.stop()

    gaps = _events(json_log_lines, "sentence_gap")
    assert gaps
    assert {g["kind"] for g in gaps} == {"script", "segment_boundary"}
    for g in gaps:
        assert g["seconds"] >= 0
        assert g["from_utterance_id"] != g["to_utterance_id"]


async def test_next_segment_is_ready_before_the_current_one_finishes(tmp_path, settings, json_log_lines):
    """FR-007: the writer runs one segment ahead, so N+1 is ready while N still plays."""
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), ack_delay_s=0.05)
    async with rig:
        await wait_until(lambda: len(rig.host.json_messages("sentence_start")) >= 5)
        await rig.stop()

    requested = [ln["segment_id"] for ln in _events(json_log_lines, "segment_requested")]
    first, second = requested[0], requested[1]
    events = [(ln["event"], ln.get("segment_id")) for ln in json_log_lines]
    ready_second = events.index(("segment_ready", second))
    finished_first = events.index(("segment_finished", first))
    assert ready_second < finished_first


# --- guard, cleaning, sentence count ---


async def test_blocked_sentences_are_skipped_and_an_all_blocked_segment_is_blocked(tmp_path, settings):
    probe = ScriptRig(tmp_path / "probe", settings, FakeReplyEngine())
    slots = [probe.planner.next_slot() for _ in range(3)]
    one, two, three = slots
    blocked_one = "Kem này giá chỉ 999.000đ thôi nha."
    script = {
        (None, Topic.OPENING): ["Chào cả nhà, em là host AI của shop nha.", "Hôm nay em có nhiều sản phẩm hay lắm."],
        (one.product_id, one.topic): [blocked_one, "Sản phẩm này thấm nhanh lắm nha."],
        (two.product_id, two.topic): ["Giá chỉ 777.000đ thôi nha.", "Giảm ngay 88% hôm nay nha."],
        (three.product_id, three.topic): ["Dạ phần tiếp theo em kể nha.", "Cả nhà nghe em nói tiếp nha."],
    }
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(script=script))
    async with rig:
        await wait_until(lambda: "Cả nhà nghe em nói tiếp nha." in rig.started_texts())
        await rig.stop()

        texts = rig.started_texts()
        assert blocked_one not in texts
        assert "Sản phẩm này thấm nhanh lắm nha." in texts
        assert not any("777.000" in t or "88%" in t for t in texts)

        by_index = {s["index"]: s for s in rig.jsonl("segments.jsonl")}
        assert by_index[1]["sentences"]["blocked"] == 1
        assert by_index[1]["status"] == "done"
        assert by_index[2]["status"] == "blocked"
        assert by_index[2]["sentences"] == {"spoken": 0, "blocked": 2, "dropped": 0, "tts_error": 0}
        assert by_index[3]["status"] == "done"

        blocked = [s for s in rig.jsonl("script_sentences.jsonl") if s["status"] == "blocked"]
        assert len(blocked) == 3
        assert {s["guard_reason"] for s in blocked} <= {"unknown_amount", "unknown_percent"}
        assert all(s["text"] not in texts for s in blocked)

        events = rig.bus_events()
        guard_events = [e.payload for e in events if e.type is EventType.GUARD_BLOCKED]
        assert len(guard_events) == 3
        assert all(p.get("segment_id") for p in guard_events)


async def test_symbols_are_cleaned_and_a_too_short_sentence_is_dropped(tmp_path, settings):
    script = {
        (None, Topic.OPENING): ["**Chào cả nhà** nha 😍", "🔥🔥 ok", "Hôm nay em giới thiệu nhiều sản phẩm nha."],
    }
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(script=script))
    async with rig:
        await wait_until(lambda: len(rig.host.json_messages("sentence_start")) >= 3)
        await rig.stop()

        texts = rig.started_texts()
        assert "Chào cả nhà" in texts[0]
        assert not any("**" in t or "😍" in t or "🔥" in t for t in texts)
        assert texts[1] == "Hôm nay em giới thiệu nhiều sản phẩm nha."

        sentences = rig.jsonl("script_sentences.jsonl")
        dropped = [s for s in sentences if s["status"] == "dropped"]
        assert [s["drop_reason"] for s in dropped] == ["empty_after_clean"]
        assert dropped[0]["raw_text"] == "🔥🔥 ok"
        first = next(s for s in sentences if s["raw_text"] == "**Chào cả nhà** nha 😍")
        assert "**" not in first["text"]


async def test_sentences_over_max_are_dropped(tmp_path, settings):
    lines = [f"Dạ đây là câu mở màn số {word} nha." for word in ("một", "hai", "ba", "bốn", "năm")]
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(script={(None, Topic.OPENING): lines}))
    async with rig:
        await wait_until(lambda: any(s["topic"] == "opening" for s in rig.jsonl("segments.jsonl")), timeout_s=5.0)
        await rig.stop()

        texts = rig.started_texts()
        assert texts[:3] == lines[:3]
        assert lines[3] not in texts and lines[4] not in texts

        opening = next(s for s in rig.jsonl("segments.jsonl") if s["topic"] == "opening")
        assert opening["sentences"]["spoken"] == 3  # max_sentences
        exceeded = [s for s in rig.jsonl("script_sentences.jsonl") if s["drop_reason"] == "sentence_count_exceeded"]
        assert exceeded
        assert {s["segment_id"] for s in exceeded} == {opening["segment_id"]}


# --- content replaced mid-show ---


def _without_toner() -> bytes:
    return build_docx(
        [
            *product_blocks(
                "Kem chống nắng X",
                "chính",
                price=None,
                variants=[("50 ml", "250.000đ"), ("100 ml", "420.000đ")],
                promotions=("Giảm 30.000đ cho đơn từ 500.000đ",),
            ),
            *product_blocks("Sữa rửa mặt Y", "phụ", price="159.000đ", forbidden=()),
        ]
    )


async def test_catalog_replaced_discards_prepared_segment_and_removed_product_is_never_spoken(
    tmp_path, settings, json_log_lines
):
    opening = [
        "Chào cả nhà, em là host AI của shop nha.",
        "Hôm nay em có nhiều sản phẩm hay lắm.",
        "Cả nhà ở lại với em nha.",
    ]
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(script={(None, Topic.OPENING): opening}), ack_delay_s=0.15)
    toner = next(p for p in rig.catalog.products if p.name == "Toner Z")
    async with rig:
        requested = lambda: [ln["segment_id"] for ln in _events(json_log_lines, "segment_requested")]  # noqa: E731
        await wait_until(lambda: len(requested()) >= 2)
        prepared = requested()[1]
        await wait_until(
            lambda: any(ln.get("segment_id") == prepared for ln in _events(json_log_lines, "segment_ready"))
        )
        assert not any(ln.get("segment_id") == prepared for ln in _events(json_log_lines, "segment_started"))

        new_catalog = rig.store.replace(_without_toner(), "new.docx")
        rig.runner.on_catalog_replaced(new_catalog)
        replaced_at = len(rig.started_texts())

        await wait_until(lambda: len(_events(json_log_lines, "segment_started")) >= 6, timeout_s=10.0)
        await rig.stop()

        segments = {s["segment_id"]: s for s in rig.jsonl("segments.jsonl")}
        assert segments[prepared]["status"] == "discarded"
        assert segments[prepared]["sentences"]["spoken"] == 0

        later = [s for s in segments.values() if s["index"] > segments[prepared]["index"]]
        assert later
        assert all(s["catalog_version"] == new_catalog.version for s in later)
        assert toner.id not in {s["product_id"] for s in segments.values()}
        assert not any("Toner Z" in t for t in rig.started_texts()[replaced_at:])
        assert opening[2] in rig.started_texts()  # the segment already speaking finishes (api.md §3)


# --- T040: pause, resume, skip, end (US2; FR-015 to FR-017, research R7, R13) ---

CLOSING_LINES = [
    "Dạ em cảm ơn cả nhà đã xem live hôm nay nha.",
    "Hẹn gặp lại cả nhà ở buổi live sau nha.",
    "Câu chào kết thứ ba này không được nói nha.",
]


def _spy_interrupt(rig: ScriptRig) -> list[str | None]:
    """Count `renderer.interrupt()` calls, recording what was speaking at that moment."""
    calls: list[str | None] = []
    original = rig.renderer.interrupt

    async def spy() -> None:
        calls.append(rig.renderer._speaking)
        await original()

    rig.renderer.interrupt = spy  # type: ignore[method-assign]
    return calls


def _segment_of(lines: list[dict], utterance_id: str) -> str:
    return next(ln["segment_id"] for ln in _events(lines, "llm_first_sentence") if ln["utterance_id"] == utterance_id)


def _ended(rig: ScriptRig) -> bool:
    return rig._task is not None and rig._task.done()


def _starts(rig: ScriptRig) -> list[dict]:
    return rig.host.json_messages("sentence_start")


async def test_pause_finishes_the_sentence_drops_voiced_audio_and_resume_revoices_it(
    tmp_path, settings, json_log_lines
):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), ack_delay_s=0.2)
    async with rig:
        interrupts = _spy_interrupt(rig)
        await wait_until(lambda: len(_starts(rig)) >= 2)
        speaking = _starts(rig)[1]["utterance_id"]
        started = {m["utterance_id"] for m in _starts(rig)}
        # Something after the speaking sentence is already voiced, so the pause has audio to drop.
        await wait_until(
            lambda: any(ln["utterance_id"] not in started for ln in _events(json_log_lines, "tts_first_chunk"))
        )
        # Heard already: only a sentence that started playing finishes through a pause (004 FR-015).
        await wait_until(lambda: rig.renderer.first_playback_at(speaking) is not None)

        assert rig.runner.pause() is True
        assert rig.runner.pause() is False  # idempotent
        assert rig.show.state is ShowState.PAUSED

        # US2 #1: the sentence speaking now finishes, without a stop, and nothing new starts.
        await wait_until(lambda: any(m["utterance_id"] == speaking for m in rig.host.json_messages("sentence_end")))
        await asyncio.sleep(0.8)
        assert len(_starts(rig)) == 2
        assert interrupts == []
        assert rig.host.json_messages("stop") == []
        await wait_until(
            lambda: any(ln["utterance_id"] == speaking for ln in _events(json_log_lines, "sentence_played"))
        )

        # The voiced audio is dropped; the text is kept (research R7).
        dropped = [ln for ln in _events(json_log_lines, "sentence_dropped") if ln["reason"] == "paused_discard"]
        assert dropped
        first_dropped = dropped[0]["utterance_id"]
        voiced = [ln for ln in _events(json_log_lines, "tts_first_chunk") if ln["utterance_id"] == first_dropped]
        assert len(voiced) == 1

        played_at = next(
            ln["t_mono"] for ln in _events(json_log_lines, "sentence_played") if ln["utterance_id"] == speaking
        )
        paused_for = time.monotonic() - played_at

        # US2 #2: resume voices the next sentence again and plays it within 3 s.
        assert rig.runner.resume() is True
        assert rig.runner.resume() is False
        assert rig.show.state is ShowState.RUNNING
        resumed_at = time.monotonic()
        await wait_until(lambda: len(_starts(rig)) >= 3, timeout_s=3.0)
        assert time.monotonic() - resumed_at <= 3.0
        assert _starts(rig)[2]["utterance_id"] == first_dropped
        await wait_until(
            lambda: any(g["to_utterance_id"] == first_dropped for g in _events(json_log_lines, "sentence_gap"))
        )
        await rig.stop()

    voiced = [ln for ln in _events(json_log_lines, "tts_first_chunk") if ln["utterance_id"] == first_dropped]
    assert len(voiced) == 2
    gap = next(g for g in _events(json_log_lines, "sentence_gap") if g["to_utterance_id"] == first_dropped)
    assert gap["kind"] == "paused"
    # The silence includes the whole pause: from the last sentence played until resume, and more.
    assert paused_for >= 0.5
    assert gap["seconds"] >= round(paused_for, 3)
    # A paused sentence is spoken later, so its only script_sentences line says `spoken`.
    rows = [s for s in rig.jsonl("script_sentences.jsonl") if s["utterance_id"] == first_dropped]
    assert [r["status"] for r in rows] == ["spoken"]


async def test_segment_being_generated_at_pause_is_not_lost(tmp_path, settings):
    opening = [
        "Chào cả nhà, em là host AI của shop nha.",
        "Hôm nay em có nhiều sản phẩm hay lắm.",
        "Cả nhà ở lại với em nha.",
    ]
    engine = FakeReplyEngine(script={(None, Topic.OPENING): opening}, delay_s=0.4)
    rig = ScriptRig(tmp_path, settings, engine, ack_delay_s=0.1)
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 1)
        await wait_until(lambda: rig.renderer.first_playback_at(_starts(rig)[0]["utterance_id"]) is not None)
        assert rig.runner.pause() is True
        # The writer keeps going while paused; nothing more is spoken.
        await asyncio.sleep(1.2)
        assert rig.started_texts() == opening[:1]

        assert rig.runner.resume() is True
        await wait_until(lambda: len(_starts(rig)) >= 3, timeout_s=3.0)
        assert rig.started_texts()[:3] == opening
        await wait_until(lambda: any(s["topic"] == "opening" for s in rig.jsonl("segments.jsonl")))
        await rig.stop()

    segment = next(s for s in rig.jsonl("segments.jsonl") if s["topic"] == "opening")
    assert segment["status"] == "done"
    assert segment["sentences"]["spoken"] == 3


async def test_skip_interrupts_drops_the_rest_and_the_next_segment_speaks_at_once(tmp_path, settings, json_log_lines):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), ack_delay_s=0.5)
    async with rig:
        interrupts = _spy_interrupt(rig)
        # The third sentence is the first of the first rotation segment (the opening has two).
        await wait_until(lambda: len(_starts(rig)) >= 3)
        speaking = _starts(rig)[2]["utterance_id"]
        segment_id = _segment_of(json_log_lines, speaking)

        skipped_at = time.monotonic()
        result = await rig.runner.skip()

        assert result == (speaking, segment_id)
        assert interrupts == [speaking]
        assert [m["utterance_id"] for m in rig.host.json_messages("stop")] == [speaking]
        await wait_until(lambda: len(_starts(rig)) >= 4, timeout_s=1.0)
        assert time.monotonic() - skipped_at <= 1.0
        next_id = _starts(rig)[3]["utterance_id"]
        assert _segment_of(json_log_lines, next_id) != segment_id
        await rig.stop()

    segment = next(s for s in rig.jsonl("segments.jsonl") if s["segment_id"] == segment_id)
    assert segment["status"] == "skipped"
    rows = [s for s in rig.jsonl("script_sentences.jsonl") if s["segment_id"] == segment_id]
    assert len(rows) == 2
    assert all(s["status"] != "spoken" for s in rows)
    started_ids = {m["utterance_id"] for m in _starts(rig)}
    assert not ({s["utterance_id"] for s in rows} - {speaking}) & started_ids


async def test_close_finishes_the_sentence_then_says_at_most_two_closing_sentences(tmp_path, settings, json_log_lines):
    engine = FakeReplyEngine(script={(None, Topic.CLOSING): CLOSING_LINES})
    rig = ScriptRig(tmp_path, settings, engine, ack_delay_s=0.3)
    async with rig:
        interrupts = _spy_interrupt(rig)
        await wait_until(lambda: len(_starts(rig)) >= 3)
        speaking = _starts(rig)[2]["utterance_id"]
        speaking_segment = _segment_of(json_log_lines, speaking)
        await wait_until(lambda: len(_events(json_log_lines, "segment_requested")) >= 3)
        prepared = _events(json_log_lines, "segment_requested")[2]["segment_id"]
        assert prepared != speaking_segment
        before = len(_starts(rig))

        assert rig.runner.close() is True
        assert rig.runner.close() is False
        assert rig.show.state is ShowState.CLOSING

        # US2 #4: the run ends by itself once the closing segment is done.
        await wait_until(lambda: _ended(rig), timeout_s=5.0)
        rig._task.result()
        await rig.stop()

    assert interrupts == []
    assert rig.host.json_messages("stop") == []
    assert any(m["utterance_id"] == speaking for m in rig.host.json_messages("sentence_end"))
    assert rig.started_texts()[before:] == CLOSING_LINES[:2]

    closing_requests = [r for r in engine.narrate_requests if r.topic is Topic.CLOSING]
    assert len(closing_requests) == 1
    assert closing_requests[0].product_id is None
    assert (closing_requests[0].min_sentences, closing_requests[0].max_sentences) == (1, 2)

    segments = {s["segment_id"]: s for s in rig.jsonl("segments.jsonl")}
    closing = next(s for s in segments.values() if s["topic"] == "closing")
    assert closing["status"] == "done"
    assert closing["sentences"]["spoken"] == 2
    assert segments[prepared]["status"] == "discarded"
    assert segments[prepared]["sentences"]["spoken"] == 0
    exceeded = [s for s in rig.jsonl("script_sentences.jsonl") if s["drop_reason"] == "sentence_count_exceeded"]
    assert [s["raw_text"] for s in exceeded] == [CLOSING_LINES[2]]

    summary = json.loads((rig.folder / f"show_summary_{SHOW_ID}.json").read_text("utf-8"))
    assert summary["ended_by"] == "operator"
    assert rig.show.state is ShowState.ENDED


class _FailingClosingEngine(FakeReplyEngine):
    """Rotation works; the closing segment's LLM call fails."""

    async def narrate(self, request, catalog):
        if request.topic is Topic.CLOSING:
            self.narrate_requests.append(request)
            raise ReplyEngineError("api_error", "giả lập lỗi chào kết")
        async for line in super().narrate(request, catalog):
            yield line


async def test_closing_llm_failure_says_the_fallback_sentence_through_the_guard(tmp_path, settings):
    rig = ScriptRig(tmp_path, settings, _FailingClosingEngine(), ack_delay_s=0.05)
    async with rig:
        checked: list[str] = []
        original = rig.runner.guard.check

        def spy(text, catalog):
            checked.append(text)
            return original(text, catalog)

        rig.runner.guard.check = spy  # type: ignore[method-assign]
        await wait_until(lambda: len(_starts(rig)) >= 2)
        assert rig.runner.close() is True
        await wait_until(lambda: _ended(rig), timeout_s=5.0)
        rig._task.result()
        await rig.stop()

    assert not any(ch.isdigit() for ch in CLOSING_FALLBACK_SENTENCE)
    assert CLOSING_FALLBACK_SENTENCE in checked
    assert rig.started_texts()[-1] == CLOSING_FALLBACK_SENTENCE
    assert rig.started_texts().count(CLOSING_FALLBACK_SENTENCE) == 1
    closing = next(s for s in rig.jsonl("segments.jsonl") if s["topic"] == "closing")
    assert closing["status"] == "done"
    assert closing["error_step"] == "llm"


async def test_skip_while_closing_stops_at_once(tmp_path, settings):
    engine = FakeReplyEngine(script={(None, Topic.CLOSING): CLOSING_LINES[:2]})
    rig = ScriptRig(tmp_path, settings, engine, ack_delay_s=0.5)
    async with rig:
        interrupts = _spy_interrupt(rig)
        await wait_until(lambda: len(_starts(rig)) >= 1)
        assert rig.runner.close() is True
        await wait_until(lambda: CLOSING_LINES[0] in rig.started_texts(), timeout_s=5.0)
        speaking = next(m for m in _starts(rig) if m["text"] == CLOSING_LINES[0])

        uid, segment_id = await rig.runner.skip()

        assert uid == speaking["utterance_id"]
        assert interrupts == [uid]
        await wait_until(lambda: _ended(rig), timeout_s=1.0)
        rig._task.result()
        await asyncio.sleep(0.3)
        await rig.stop()

    assert CLOSING_LINES[1] not in rig.started_texts()
    closing = next(s for s in rig.jsonl("segments.jsonl") if s["topic"] == "closing")
    assert closing["segment_id"] == segment_id
    assert closing["status"] == "skipped"
    summary = json.loads((rig.folder / f"show_summary_{SHOW_ID}.json").read_text("utf-8"))
    assert summary["ended_by"] == "operator"


# --- T047: robustness (US3; FR-020, FR-021, FR-024, research R10, R12) ---

# Guard-blocked lines: amounts and percents that are not in the product data.
BLOCKED_LINES = ["Giá chỉ 777.000đ thôi nha.", "Giảm ngay 88% hôm nay nha."]


class _PlannedEngine(FakeReplyEngine):
    """`narrate()` call N follows `plan[N]`: "ok" (default lines), "error", "hang" or "block"; past the plan, "ok"."""

    def __init__(self, plan: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.plan = list(plan)
        self.calls = 0

    async def narrate(self, request, catalog):
        action = self.plan[self.calls] if self.calls < len(self.plan) else "ok"
        self.calls += 1
        if action == "ok":
            async for line in super().narrate(request, catalog):
                yield line
            return
        self.narrate_requests.append(request)
        if action == "error":
            raise ReplyEngineError("api_error", "giả lập lỗi narrate")
        if action == "hang":
            await asyncio.Event().wait()
        for line in BLOCKED_LINES:
            await asyncio.sleep(0)
            yield line


class _PickyTTS(FakeTTS):
    """Fails (`error`) or never answers (`hang`) on sentences containing `marker`; the others are voiced as usual."""

    def __init__(self, marker: str, mode: str) -> None:
        super().__init__(sample_rate=16000)
        self.marker = marker
        self.mode = mode

    async def synthesize(self, text: str):
        if self.marker in text:
            if self.mode == "error":
                raise FakeTTSError("giả lập lỗi TTS")
            await asyncio.Event().wait()
        async for chunk in super().synthesize(text):
            yield chunk


SILENT_MARK = "màn hình host không phản hồi"


class _SilentHost(FakeHostConnection):
    """Never acks a sentence whose text contains `SILENT_MARK`, like a host page frozen on it."""

    def __init__(self, renderer=None, **kwargs) -> None:
        super().__init__(renderer, **kwargs)
        self.silent: set[str] = set()

    async def send_json(self, data: dict) -> None:
        if data.get("type") == "sentence_start" and SILENT_MARK in data.get("text", ""):
            self.silent.add(data["utterance_id"])
        if data.get("utterance_id") in self.silent:
            self.sent.append(data)
            return
        await super().send_json(data)


def _payloads(events: list, kind: EventType) -> list[dict]:
    return [e.payload for e in events if e.type is kind]


def _gap_kind_to(lines: list[dict], utterance_id: str) -> str:
    return next(g["kind"] for g in _events(lines, "sentence_gap") if g["to_utterance_id"] == utterance_id)


def _row(rig: ScriptRig, raw_text: str) -> dict:
    return next(s for s in rig.jsonl("script_sentences.jsonl") if s["raw_text"] == raw_text)


@pytest.mark.parametrize(("action", "kind"), [("error", "api_error"), ("hang", "timeout")])
async def test_llm_error_or_timeout_fails_the_segment_and_the_show_goes_on(
    tmp_path, settings, json_log_lines, action, kind
):
    engine = _PlannedEngine(["ok", action])
    rig = ScriptRig(tmp_path, settings, engine, settings_update={"script_llm_timeout_s": 0.3})
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 6)
        assert rig.show.state is ShowState.RUNNING
        assert rig.show.mode is ShowMode.NORMAL
        await rig.stop()

        failed_id = engine.narrate_requests[1].segment_id
        segments = {s["segment_id"]: s for s in rig.jsonl("segments.jsonl")}
        failed = segments[failed_id]
        assert failed["status"] == "failed"
        assert (failed["error_step"], failed["error_kind"]) == ("llm", kind)
        assert failed["sentences"]["spoken"] == 0
        assert any(s["index"] > failed["index"] and s["status"] == "done" for s in segments.values())

        errors = [e for e in rig.jsonl("errors.jsonl") if e.get("segment_id") == failed_id]
        assert [(e["step"], e["type"]) for e in errors] == [("llm", kind)]
        assert errors[0]["show_id"] == SHOW_ID
        shown = [p for p in _payloads(rig.bus_events(), EventType.SHOW_ERROR) if p.get("segment_id") == failed_id]
        assert [(p["step"], p["kind"]) for p in shown] == [("llm", kind)]


TTS_LINES = [
    "Chào cả nhà, em là host AI của shop nha.",
    "Câu này em đọc bị lỗi giọng nói nha.",
    "Hôm nay em có nhiều sản phẩm hay lắm.",
]


@pytest.mark.parametrize(("mode", "kind"), [("error", "FakeTTSError"), ("hang", "timeout")])
async def test_tts_error_or_timeout_drops_one_sentence_and_the_next_one_speaks(
    tmp_path, settings, json_log_lines, mode, kind
):
    engine = FakeReplyEngine(script={(None, Topic.OPENING): TTS_LINES})
    rig = ScriptRig(
        tmp_path, settings, engine, settings_update={"tts_timeout_s": 0.2}, tts=_PickyTTS("lỗi giọng nói", mode)
    )
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 3)
        assert rig.show.state is ShowState.RUNNING
        await rig.stop()

        texts = rig.started_texts()
        assert texts[:2] == [TTS_LINES[0], TTS_LINES[2]]
        lost = _row(rig, TTS_LINES[1])
        assert lost["status"] == "tts_error"
        errors = [e for e in rig.jsonl("errors.jsonl") if e.get("utterance_id") == lost["utterance_id"]]
        assert [(e["step"], e["type"]) for e in errors] == [("tts", kind)]
        shown = _payloads(rig.bus_events(), EventType.SHOW_ERROR)
        assert [(p["step"], p["kind"]) for p in shown] == [("tts", kind)]
        opening = next(s for s in rig.jsonl("segments.jsonl") if s["topic"] == "opening")
        assert opening["status"] == "done"
        assert opening["sentences"]["tts_error"] == 1

    # R12: a real error between two spoken sentences labels the gap `error`.
    assert _gap_kind_to(json_log_lines, _row(rig, TTS_LINES[2])["utterance_id"]) == "error"


ACK_LINES = [
    "Chào cả nhà, em là host AI của shop nha.",
    f"Câu này {SILENT_MARK} nha.",
    "Hôm nay em có nhiều sản phẩm hay lắm.",
]


async def test_missing_playback_ack_is_a_render_error_and_the_next_sentence_speaks(tmp_path, settings, json_log_lines):
    engine = FakeReplyEngine(script={(None, Topic.OPENING): ACK_LINES})
    rig = ScriptRig(tmp_path, settings, engine, host_factory=_SilentHost, ack_timeout_s=0.2)
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 4)
        assert rig.show.state is ShowState.RUNNING
        await rig.stop()

        assert rig.started_texts()[:3] == ACK_LINES
        silent = _row(rig, ACK_LINES[1])
        assert silent["status"] == "render_error"
        errors = [e for e in rig.jsonl("errors.jsonl") if e.get("utterance_id") == silent["utterance_id"]]
        assert [(e["step"], e["type"]) for e in errors] == [("render", "timeout")]
        assert _row(rig, ACK_LINES[2])["status"] == "spoken"

    assert _gap_kind_to(json_log_lines, _row(rig, ACK_LINES[2])["utterance_id"]) == "error"


def _fallback_pool(product) -> list[str]:
    """R10: the product's `intro` then `description`, split into sentences."""
    pool: list[str] = []
    for text in (product.intro, product.description):
        splitter = SentenceSplitter()
        pool += splitter.feed(text)
        pool += splitter.flush()
    return pool


async def test_fallback_after_consecutive_failures_reads_product_text_and_a_retry_returns_to_normal(
    tmp_path, settings, json_log_lines
):
    # Calls: opening ok; two failures enter fallback; the retry before the second fallback segment fails on the short
    # retry timeout; the next retry succeeds.
    engine = _PlannedEngine(["ok", "error", "hang", "hang", "ok"])
    update = {"script_fallback_after": 2, "script_llm_timeout_s": 1.0, "script_retry_timeout_s": 0.2}
    rig = ScriptRig(tmp_path, settings, engine, settings_update=update)
    async with rig:
        checked: list[str] = []
        original = rig.runner.guard.check

        def spy(text, catalog):
            checked.append(text)
            return original(text, catalog)

        rig.runner.guard.check = spy  # type: ignore[method-assign]
        await wait_until(lambda: len(_events(json_log_lines, "mode_changed")) >= 2, timeout_s=8.0)

        def retry_ok_finished() -> bool:
            # Stop only once the successful retry has been spoken in full; stopping mid-segment discards it.
            if len(engine.narrate_requests) < 5:
                return False
            retry_id = engine.narrate_requests[4].segment_id
            return any(ln.get("segment_id") == retry_id for ln in _events(json_log_lines, "segment_finished"))

        await wait_until(retry_ok_finished, timeout_s=8.0)
        assert rig.show.state is ShowState.RUNNING
        assert rig.show.mode is ShowMode.NORMAL
        await rig.stop()

        changes = _events(json_log_lines, "mode_changed")
        assert [(c["from"], c["to"]) for c in changes] == [("normal", "fallback"), ("fallback", "normal")]
        assert changes[0]["consecutive_failures"] == 2
        assert all(c["show_id"] == SHOW_ID for c in changes)
        states = [ln for ln in _events(json_log_lines, "show_state") if ln.get("show_id") == SHOW_ID]
        assert [(s["mode"], s["reason"]) for s in states] == [
            ("fallback", "fallback_after_failures"),
            ("normal", "retry_succeeded"),
        ]
        published = _payloads(rig.bus_events(), EventType.SHOW_STATE)
        assert [p["mode"] for p in published] == ["fallback", "normal"]
        assert all(p["state"] == "running" and p["show_id"] == SHOW_ID for p in published)

        segments = rig.jsonl("segments.jsonl")
        by_id = {s["segment_id"]: s for s in segments}
        fallback = [s for s in segments if s["origin"] == "fallback"]
        assert len(fallback) == 2
        assert all(s["mode"] == "fallback" and s["status"] == "done" for s in fallback)
        retry_failed = by_id[engine.narrate_requests[3].segment_id]
        assert retry_failed["mode"] == "fallback"
        assert retry_failed["status"] == "failed"
        retry_ok = by_id[engine.narrate_requests[4].segment_id]
        assert retry_ok["origin"] == "rotation"
        assert retry_ok["mode"] == "normal"
        assert retry_ok["status"] == "done"
        # The retry used SCRIPT_RETRY_TIMEOUT_S, not the full LLM timeout.
        retry_error = next(e for e in rig.jsonl("errors.jsonl") if e.get("segment_id") == retry_failed["segment_id"])
        assert retry_error["type"] == "timeout"
        assert "0.2" in retry_error["message"]

        rows = rig.jsonl("script_sentences.jsonl")
        products = {p.id: p for p in rig.catalog.products}
        for seg in fallback:
            pool = _fallback_pool(products[seg["product_id"]])
            assert len(pool) == 2
            said = [r for r in rows if r["segment_id"] == seg["segment_id"]]
            assert [r["raw_text"] for r in said] == pool
            assert all(r["source"] == "fallback" and r["status"] == "spoken" for r in said)
            assert all(r["text"] in checked for r in said)  # through the guard
        fallback_forms = {r["text"] for r in rows if r["source"] == "fallback"}
        assert fallback_forms
        assert not any(r["source"] == "fallback" for r in rows if r["segment_id"] == retry_ok["segment_id"])
        spoken_fallback = sum(r["source"] == "fallback" and r["status"] == "spoken" for r in rows)

        summary = json.loads((rig.folder / f"show_summary_{SHOW_ID}.json").read_text("utf-8"))
        assert [m["mode"] for m in summary["mode_changes"]] == ["fallback", "normal"]
        assert summary["sentences"]["fallback_spoken"] == spoken_fallback


async def test_all_blocked_segments_are_not_service_errors(tmp_path, settings, json_log_lines):
    engine = _PlannedEngine(["ok", "block", "block", "block"])
    rig = ScriptRig(tmp_path, settings, engine, settings_update={"script_fallback_after": 2})
    async with rig:
        await wait_until(lambda: engine.calls >= 6 and len(_starts(rig)) >= 4)
        assert rig.show.mode is ShowMode.NORMAL
        assert rig.show.consecutive_llm_failures == 0
        await rig.stop()

        blocked_ids = {r.segment_id for r in engine.narrate_requests[1:4]}
        segments = [s for s in rig.jsonl("segments.jsonl") if s["segment_id"] in blocked_ids]
        assert len(segments) == 3
        assert all(s["status"] == "blocked" and s["error_step"] is None for s in segments)
        assert not [e for e in rig.jsonl("errors.jsonl") if e["step"] == "llm"]
    assert not _events(json_log_lines, "mode_changed")


class _SlowTTS(FakeTTS):
    """Every chunk takes `gap_s`; a sentence containing `stall_marker` hangs after its first chunk."""

    def __init__(self, gap_s: float, stall_marker: str | None = None) -> None:
        super().__init__(sample_rate=16000)
        self.gap_s = gap_s
        self.stall_marker = stall_marker

    async def synthesize(self, text: str):
        first = True
        async for chunk in super().synthesize(text):
            if not first and self.stall_marker and self.stall_marker in text:
                await asyncio.Event().wait()
            await asyncio.sleep(self.gap_s)
            first = False
            yield chunk


async def test_tts_timeout_is_per_chunk_so_slow_steady_sentences_are_spoken(tmp_path, settings):
    # ADR-049: each chunk comes within TTS_TIMEOUT_S though a sentence takes several times longer.
    engine = FakeReplyEngine(script={(None, Topic.OPENING): [TTS_LINES[0], TTS_LINES[2]]})
    rig = ScriptRig(tmp_path, settings, engine, settings_update={"tts_timeout_s": 0.2}, tts=_SlowTTS(0.03))
    async with rig:
        await wait_until(lambda: len(_ends(rig)) >= 2, timeout_s=10)
        await rig.stop()

        assert rig.started_texts()[:2] == [TTS_LINES[0], TTS_LINES[2]]
        assert not rig.jsonl("errors.jsonl")


async def test_tts_stall_after_the_first_chunk_is_a_timeout(tmp_path, settings):
    engine = FakeReplyEngine(script={(None, Topic.OPENING): TTS_LINES})
    tts = _SlowTTS(0.0, stall_marker="lỗi giọng nói")
    rig = ScriptRig(tmp_path, settings, engine, settings_update={"tts_timeout_s": 0.2}, tts=tts)
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 3)
        await rig.stop()

        lost = _row(rig, TTS_LINES[1])
        errors = [e for e in rig.jsonl("errors.jsonl") if e.get("utterance_id") == lost["utterance_id"]]
        assert [(e["step"], e["type"]) for e in errors] == [("tts", "timeout")]


class _Gate:
    """An interleave gate the test opens and shuts, standing in for a comment turn that runs or waits."""

    def __init__(self, busy: bool = False) -> None:
        self.busy = busy

    def pending(self) -> bool:
        return self.busy

    async def wait_clear(self) -> None:
        while self.busy:  # noqa: ASYNC110
            await asyncio.sleep(0.01)


class _RecordingTTS(FakeTTS):
    """Records each sentence when its synthesis starts."""

    def __init__(self) -> None:
        super().__init__(sample_rate=16000)
        self.started: list[str] = []

    async def synthesize(self, text: str):
        self.started.append(text)
        async for chunk in super().synthesize(text):
            yield chunk


async def test_no_scripted_synthesis_starts_while_a_comment_turn_is_pending(tmp_path, settings):
    # SC-011: a one-sentence-at-a-time engine (VieNeu) serves the reply's sentences, not the script queued between them.
    gate, tts = _Gate(busy=True), _RecordingTTS()
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), tts=tts, interleave=gate)
    async with rig:
        await wait_until(lambda: len(rig.engine.narrate_requests) > 0)
        await asyncio.sleep(0.3)
        assert tts.started == []

        gate.busy = False
        await wait_until(lambda: len(_starts(rig)) >= 2)
        gate.busy = True
        started = len(tts.started)
        await asyncio.sleep(0.3)
        assert len(tts.started) == started

        gate.busy = False
        await wait_until(lambda: len(_starts(rig)) >= 4)
        await rig.stop()

    assert not rig.jsonl("errors.jsonl")


async def test_closing_is_voiced_while_a_comment_turn_is_pending(tmp_path, settings):
    engine = FakeReplyEngine(script={(None, Topic.CLOSING): CLOSING_LINES})
    gate = _Gate()
    rig = ScriptRig(tmp_path, settings, engine, interleave=gate)
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 1)
        gate.busy = True
        assert rig.runner.close() is True
        await wait_until(lambda: _ended(rig), timeout_s=5.0)
        rig._task.result()
        await rig.stop()

    assert rig.started_texts()[-2:] == CLOSING_LINES[:2]


def _ends(rig: ScriptRig) -> list[dict]:
    return rig.host.json_messages("sentence_end")


@pytest.mark.parametrize("step", ["llm", "tts", "render"])
async def test_an_injected_fault_labels_the_gap_fault(tmp_path, settings, json_log_lines, step):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), settings_update={"tts_timeout_s": 0.3})
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 1)
        rig.faults.inject(step, "error")
        await wait_until(lambda: len(_starts(rig)) >= 7)
        assert rig.show.state is ShowState.RUNNING
        await rig.stop()

        errors = rig.jsonl("errors.jsonl")
        assert [(e["step"], e["type"]) for e in errors] == [(step, "fault_injected")]

    kinds = {g["kind"] for g in _events(json_log_lines, "sentence_gap")}
    assert "fault" in kinds
    assert "error" not in kinds


async def test_host_disconnect_is_a_render_error_and_the_show_keeps_running(tmp_path, settings):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), ack_delay_s=0.2)
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 2)
        rig.renderer.detach(rig.host)
        await wait_until(lambda: any(e["step"] == "render" for e in rig.show.recent_errors))
        await asyncio.sleep(0.1)
        assert rig.show.state is ShowState.RUNNING

        host = FakeHostConnection(rig.renderer)
        await rig.renderer.attach(host)
        rig.renderer.handle_message(host, {"type": "ready"})
        await wait_until(lambda: len(host.json_messages("sentence_start")) >= 2)
        assert rig.show.state is ShowState.RUNNING
        await rig.stop()

        errors = [e for e in rig.jsonl("errors.jsonl") if e["step"] == "render"]
        assert [e["type"] for e in errors] == ["host_unavailable"]
        rows = [r for r in rig.jsonl("script_sentences.jsonl") if r["status"] == "render_error"]
        assert [r["utterance_id"] for r in rows] == [errors[0]["utterance_id"]]


async def test_cancelled_run_writes_a_shutdown_summary(tmp_path, settings):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine())
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 2)
        await rig.stop()

        summary = json.loads((rig.folder / f"show_summary_{SHOW_ID}.json").read_text("utf-8"))
        assert summary["ended_by"] == "shutdown"
        assert rig.show.state is ShowState.ENDED


# --- T048: repeats and the long-run soak (US3; FR-006, SC-004, SC-005, research R6, R11) ---


async def test_a_sentence_already_said_is_dropped_as_duplicate(tmp_path, settings, json_log_lines):
    probe = ScriptRig(tmp_path / "probe", settings, FakeReplyEngine())
    one = probe.planner.next_slot()
    said = "Chào cả nhà, em là host AI của shop nha."
    again = "chào cả nhà em là host AI của shop nha!"  # same word_form, other case and punctuation
    script = {
        (None, Topic.OPENING): [said, "Hôm nay em có nhiều sản phẩm hay lắm."],
        (one.product_id, one.topic): [again, "Sản phẩm này thấm nhanh lắm nha."],
    }
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(script=script))
    async with rig:
        await wait_until(lambda: "Sản phẩm này thấm nhanh lắm nha." in rig.started_texts())
        await rig.stop()

        texts = rig.started_texts()
        assert texts.count(said) == 1
        assert again not in texts
        row = _row(rig, again)
        assert (row["status"], row["drop_reason"]) == ("dropped", "duplicate")
        summary = json.loads((rig.folder / f"show_summary_{SHOW_ID}.json").read_text("utf-8"))
        assert summary["duplicates"]["before_filter_rate"] > 0
        assert summary["duplicates"]["spoken_rate"] == 0

    dropped = [ln for ln in _events(json_log_lines, "sentence_dropped") if ln["reason"] == "duplicate"]
    assert [ln["utterance_id"] for ln in dropped] == [row["utterance_id"]]


# Tags made of consonants only: no digit (the guard reads any bare number >= 1000 as an unknown amount), and no
# vowel, so a tag can never spell a forbidden claim or platform phrase.
_TAG_LETTERS = "bdghlnqrtvx"
SOAK_CALLS = 219  # opening + 218 rotation segments; call 220 hangs, so the show stops at a known point
SOAK_SEGMENT_S = 30  # fake wall time per finished segment: 20 segments per 10-minute coverage window
REPEAT_EVERY = 5


def _tag(n: int) -> str:
    letters: list[str] = []
    while True:
        n, r = divmod(n, len(_TAG_LETTERS))
        letters.append(_TAG_LETTERS[r])
        if n == 0:
            return "".join(reversed(letters))


class _SoakEngine(FakeReplyEngine):
    """Unique, digit-free lines; every `REPEAT_EVERY`-th segment opens with a line said a few segments ago."""

    def __init__(self) -> None:
        super().__init__()
        self.said: list[str] = []
        self.n = 0

    async def narrate(self, request, catalog):
        self.narrate_requests.append(request)
        if len(self.narrate_requests) > SOAK_CALLS:
            await asyncio.Event().wait()
        name = next((p.name for p in catalog.products if p.id == request.product_id), "shop")
        lines = []
        for _ in range(request.min_sentences):
            self.n += 1
            lines.append(f"Dạ phần {request.topic.label.lower()} của {name}, ghi chú {_tag(self.n)} nha.")
        if len(self.narrate_requests) % REPEAT_EVERY == 0 and len(self.said) >= 6:
            lines[0] = self.said[-6]
        self.said += lines
        for line in lines:
            await asyncio.sleep(0)
            yield line


class _OneChunkTTS(FakeTTS):
    """A tiny clip per sentence, so hundreds of sentences stay fast and small in memory."""

    async def synthesize(self, text: str):
        await asyncio.sleep(0)
        yield b"\0" * 320


class _CountingStats(ShowStats):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.finished = 0

    def record_segment(self, segment) -> None:
        super().record_segment(segment)
        self.finished += 1


async def test_soak_of_200_segments_keeps_share_coverage_and_no_repeats(tmp_path, settings):
    base = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    rig = ScriptRig(
        tmp_path, settings, _SoakEngine(), settings_update={"script_llm_timeout_s": 60.0}, tts=_OneChunkTTS()
    )
    stats = _CountingStats(SHOW_ID, SESSION_ID, rig.catalog)
    rig.stats = stats
    # Wall time follows finished segments, so segment k starts at k * 30 s whatever the machine speed.
    rig.wall_clock = lambda: base + timedelta(seconds=SOAK_SEGMENT_S * stats.finished)
    async with rig:
        await wait_until(lambda: stats.finished >= SOAK_CALLS, timeout_s=60.0)
        await rig.stop()

        summary = json.loads((rig.folder / f"show_summary_{SHOW_ID}.json").read_text("utf-8"))

    assert summary["segments"]["total"] >= 200
    assert summary["segments"]["primary_share"] >= 0.5
    windows = summary["secondary_coverage"]
    assert len(windows) >= 10
    assert all(w["missing_products"] == [] for w in windows), windows
    duplicates = summary["duplicates"]
    assert duplicates["before_filter_rate"] > 0  # the engine did repeat; layer 2 caught it
    assert duplicates["spoken_rate"] <= 0.05
    assert duplicates["identical_segments"] == 0


# --- T062: operator choice of the next segment (US5; FR-018, research R6, R7) ---


async def test_choice_discards_the_prepared_segment_and_the_chosen_slot_follows_the_one_speaking(
    tmp_path, settings, json_log_lines
):
    opening = [
        "Chào cả nhà, em là host AI của shop nha.",
        "Hôm nay em có nhiều sản phẩm hay lắm.",
        "Cả nhà ở lại với em nha.",
    ]
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(script={(None, Topic.OPENING): opening}), ack_delay_s=0.15)
    toner = next(p for p in rig.catalog.products if p.name == "Toner Z")
    rotation_slot = _first_slot(rig)
    async with rig:
        requested = lambda: [ln["segment_id"] for ln in _events(json_log_lines, "segment_requested")]  # noqa: E731
        await wait_until(lambda: len(requested()) >= 2)
        opening_id, prepared = requested()[0], requested()[1]
        await wait_until(
            lambda: any(ln.get("segment_id") == prepared for ln in _events(json_log_lines, "segment_ready"))
        )
        assert not any(ln.get("segment_id") == prepared for ln in _events(json_log_lines, "segment_started"))
        rig.bus_events()

        chosen = rig.runner.choose(toner.id, Topic.PROMOTION)

        assert (chosen.product_id, chosen.topic, chosen.origin.value) == (toner.id, Topic.PROMOTION, "operator")
        await wait_until(lambda: len(_events(json_log_lines, "segment_started")) >= 3, timeout_s=10.0)
        await rig.stop()

        events = rig.bus_events()
        segments = {s["segment_id"]: s for s in rig.jsonl("segments.jsonl")}

    # N+1, already generated, is discarded and never heard.
    assert segments[prepared]["status"] == "discarded"
    assert segments[prepared]["sentences"]["spoken"] == 0
    nexts = [e.payload for e in events if e.type is EventType.SEGMENT_NEXT]
    assert any(n.get("segment_id") == prepared and n["status"] == "discarded" for n in nexts)
    assert any(n["origin"] == "operator" and (n["product_id"], n["topic"]) == (toner.id, "promotion") for n in nexts)

    # US5 #1: the segment right after the one speaking is the chosen slot, marked as the operator's.
    started = [e.payload for e in events if e.type is EventType.SEGMENT_STARTED]
    after_opening = [s for s in started if s["segment_id"] != opening_id]
    first = after_opening[0]
    assert (first["product_id"], first["topic"], first["origin"]) == (toner.id, "promotion", "operator")
    # The manual segment does not use up a rotation slot: the discarded rotation slot comes next (research R6).
    second = after_opening[1]
    assert (second["product_id"], second["topic"], second["origin"]) == (
        rotation_slot.product_id,
        rotation_slot.topic.value,
        "rotation",
    )

    # The segment speaking when the operator chose is not cut.
    assert segments[opening_id]["status"] == "done"
    assert segments[opening_id]["sentences"]["spoken"] == 3
    assert rig.started_texts()[:3] == opening
    assert rig.host.json_messages("stop") == []


# --- 005 T051: render outcome and figures from the script player (US2; FR-020, FR-022, contracts/adapters.md §2) ---


class _ReportingRenderer(StaticRenderer):
    """The still image plus the two optional hooks `SwitchingRenderer` has, recording what the player tells it."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.outcomes: list[tuple[str, bool, str | None]] = []

    def record_render_outcome(self, utterance_id: str, ok: bool, *, error_kind: str | None = None) -> None:
        self.outcomes.append((utterance_id, ok, error_kind))

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None:
        return RenderTurnStats(
            utterance_id, "livetalking", clips_used=["talk_01"], frames=25, render_fps=25.0, infer_fps=30.0
        )


def _reporting(bus: EventBus, ack_timeout_s: float) -> _ReportingRenderer:
    return _ReportingRenderer(ack_timeout_s=ack_timeout_s, bus=bus)


async def test_each_spoken_sentence_reports_ok_and_logs_render_stats_but_a_tts_error_reports_nothing(
    tmp_path, settings, json_log_lines
):
    engine = FakeReplyEngine(script={(None, Topic.OPENING): TTS_LINES})
    rig = ScriptRig(tmp_path, settings, engine, tts=_PickyTTS("lỗi giọng nói", "error"), make_renderer=_reporting)
    async with rig:
        await wait_until(lambda: len(rig.renderer.outcomes) >= 2)
        await rig.stop()

    spoken = [_row(rig, TTS_LINES[0])["utterance_id"], _row(rig, TTS_LINES[2])["utterance_id"]]
    lost = _row(rig, TTS_LINES[1])["utterance_id"]
    assert rig.renderer.outcomes[:2] == [(uid, True, None) for uid in spoken]
    assert all(uid != lost for uid, _, _ in rig.renderer.outcomes)
    # Scripted sentences have no `TurnLatency` (004 R2): the figures go to the log only, one line per spoken sentence.
    stats = _events(json_log_lines, "render_stats")
    assert [ln["utterance_id"] for ln in stats][:2] == spoken
    assert stats[0]["clips_used"] == ["talk_01"] and stats[0]["infer_fps"] == 30.0 and stats[0]["frames"] == 25
    assert lost not in {ln["utterance_id"] for ln in stats}


async def test_a_render_error_reports_its_kind_once_and_logs_no_render_stats(tmp_path, settings, json_log_lines):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), make_renderer=_reporting)
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 1)
        rig.faults.inject("render", "error")
        await wait_until(lambda: any(not ok for _, ok, _ in rig.renderer.outcomes))
        await wait_until(lambda: len(_starts(rig)) >= 3)
        await rig.stop()

    [error] = [e for e in rig.jsonl("errors.jsonl") if e["step"] == "render"]
    failed = [(uid, kind) for uid, ok, kind in rig.renderer.outcomes if not ok]
    assert failed == [(error["utterance_id"], "fault_injected")]
    assert error["utterance_id"] not in {ln["utterance_id"] for ln in _events(json_log_lines, "render_stats")}


async def test_a_sentence_cut_by_skip_reports_no_render_outcome(tmp_path, settings):
    rig = ScriptRig(tmp_path, settings, FakeReplyEngine(), ack_delay_s=0.5, make_renderer=_reporting)
    async with rig:
        await wait_until(lambda: len(_starts(rig)) >= 1)
        cut, _ = await rig.runner.skip()
        await wait_until(lambda: len(rig.renderer.outcomes) >= 1)
        await rig.stop()

    assert cut not in {uid for uid, _, _ in rig.renderer.outcomes}


# --- 005 US2 #1: the scripted show on the lip-synced character (FR-015, FR-016) ---

LIPSYNC_READY = {"type": "ready", "lipsync_session": "sess-1"}


@pytest.fixture
async def fork() -> AsyncIterator[FakeFork]:
    async with FakeFork() as f:
        yield f


class LipsyncScriptRig(ScriptRig):
    """`ScriptRig` with the app's lip-sync wiring: `SwitchingRenderer` over `LiveTalkingRenderer` (fake fork)."""

    def __init__(self, fork: FakeFork, tmp_path: Path, settings, engine: FakeReplyEngine, **kwargs) -> None:
        self.fork = fork

        def make(bus: EventBus, ack_timeout_s: float) -> SwitchingRenderer:
            static = StaticRenderer(ack_timeout_s=ack_timeout_s, bus=bus)
            lipsync = LiveTalkingRenderer(
                fork.url, static, first_frame_timeout_s=1.0, ack_timeout_s=ack_timeout_s, reconnect_max_s=0.2, bus=bus
            )
            return SwitchingRenderer(lipsync, static, fallback_after=2, bus=bus)

        super().__init__(tmp_path, settings, engine, make_renderer=make, ready_message=LIPSYNC_READY, **kwargs)

    async def __aenter__(self) -> LipsyncScriptRig:
        await self.renderer.start()
        await super().__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await super().__aexit__(*exc)
        await self.renderer.stop()

    def fork_uids(self) -> list[str]:
        return [s.utterance_id for s in self.fork.sentences]

    def cleared(self) -> set[str]:
        return {m["utterance_id"] for m in self.host.json_messages("subtitle_clear")}


async def test_lipsync_show_speaks_on_the_fork_with_subtitles_and_pause_resume_keeps_working(
    fork, tmp_path, settings, json_log_lines
):
    fork.time_scale = 0.2  # a pause must land while a sentence is still playing
    rig = LipsyncScriptRig(fork, tmp_path, settings, FakeReplyEngine())
    async with rig:
        await wait_until(lambda: len(rig.fork.sentences) >= 2)
        # The fork speaks; the host page shows the subtitle only and gets no audio of its own.
        assert _starts(rig) == [] and rig.host.audio_bytes() == 0
        first = rig.fork.sentences[0]
        await wait_until(lambda: first.utterance_id in rig.cleared())
        subtitles = [m["text"] for m in rig.host.json_messages("subtitle") if m["utterance_id"] == first.utterance_id]
        assert subtitles == [first.text]

        # US2 #1 (004): pause lets the sentence on the fork finish without a stop, and nothing new starts.
        speaking = rig.fork_uids()[-1]
        await wait_until(lambda: rig.renderer.first_playback_at(speaking) is not None)
        assert rig.runner.pause() is True
        await wait_until(lambda: speaking in rig.cleared())
        count = len(rig.fork.sentences)
        await asyncio.sleep(0.5)
        assert len(rig.fork.sentences) == count
        assert rig.fork.stopped == [] and rig.host.json_messages("stop") == []

        assert rig.runner.resume() is True
        await wait_until(lambda: len(rig.fork.sentences) > count, timeout_s=3.0)
        nxt = rig.fork_uids()[count]
        await wait_until(lambda: nxt in {ln["utterance_id"] for ln in _events(json_log_lines, "render_stats")})
        await rig.stop()

    assert rig.renderer.mode.active == "livetalking" and rig.renderer.mode.consecutive_errors == 0
    played = {ln["utterance_id"] for ln in _events(json_log_lines, "sentence_played")}
    stats = {ln["utterance_id"]: ln for ln in _events(json_log_lines, "render_stats")}
    assert {first.utterance_id, speaking, nxt} <= played & set(stats)
    assert stats[first.utterance_id]["clips_used"] == ["talk_01"] and stats[first.utterance_id]["frames"] > 0
    rows = {r["utterance_id"]: r["status"] for r in rig.jsonl("script_sentences.jsonl")}
    assert rows[first.utterance_id] == rows[speaking] == rows[nxt] == "spoken"


async def test_lipsync_pause_stops_a_sentence_sent_but_not_heard_and_resume_speaks_it_again(
    fork, tmp_path, settings, json_log_lines
):
    # 005 T062: the fork starts a sentence ~1 s after its audio arrives. One sent but not heard at the pause would
    # begin after it; it is stopped and spoken again on resume (004 FR-015).
    fork.time_scale = 0.2
    fork.ack_delay_s = 0.6
    rig = LipsyncScriptRig(fork, tmp_path, settings, FakeReplyEngine())
    async with rig:
        await wait_until(lambda: len(rig.fork.sentences) >= 2)
        waiting = rig.fork_uids()[-1]
        assert rig.renderer.first_playback_at(waiting) is None
        assert rig.runner.pause() is True

        await wait_until(lambda: rig.fork.stopped == [waiting])
        assert [m["utterance_id"] for m in rig.host.json_messages("stop")] == [waiting]
        count = len(rig.fork.sentences)
        await asyncio.sleep(1.0)
        assert len(rig.fork.sentences) == count
        assert waiting not in {m["utterance_id"] for m in rig.host.json_messages("subtitle")}
        dropped = [ln for ln in _events(json_log_lines, "sentence_dropped") if ln["reason"] == "paused_discard"]
        assert waiting in {ln["utterance_id"] for ln in dropped}

        assert rig.runner.resume() is True
        await wait_until(lambda: len(rig.fork.sentences) > count, timeout_s=3.0)
        again = rig.fork.sentences[count]
        # The same sentence, a new turn: seq 0, so the fork picks a talk clip again.
        assert (again.utterance_id, again.seq) == (waiting, 0)
        await wait_until(lambda: waiting in {ln["utterance_id"] for ln in _events(json_log_lines, "render_stats")})
        await rig.stop()

    assert rig.renderer.mode.active == "livetalking" and rig.renderer.mode.consecutive_errors == 0
    rows = [r["status"] for r in rig.jsonl("script_sentences.jsonl") if r["utterance_id"] == waiting]
    assert rows == ["spoken"]
