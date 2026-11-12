"""Scripted show runner: three tiers, write -> voice -> play (004 US1; FR-002 to FR-008, FR-011, FR-022, research R7).

- `_write` asks `narrate()` for one segment at a time and stays exactly one segment ahead: once the text of N+1 is
  out, it waits until N+1 starts playing before it asks for N+2. Each sentence is cleaned (`clean_spoken`), checked
  by the guard and put on the text queue; dropped and blocked sentences never reach TTS.
- `_voice` runs TTS in order and keeps at most `SENTENCE_QUEUE_MAX` voiced sentences waiting, like 001. A TTS error
  drops only that sentence (unlike 001, where it ends the whole turn).
- `_play` holds the shared `_floor` for each sentence (research R8), calls `renderer.speak()` and records the gap.
  Before the first sentence of a segment it checks the segment's `catalog_version`; a stale segment is discarded and
  the writer generates the next one from the new catalog.

Every scripted sentence is its own utterance (`seq = 0`), and logs the four milestones with `utterance_id`,
`segment_id` and `show_id` (Article VIII). No `turn_started`/`turn_finished` is published, so the 001 latency table
keeps meaning comment turns only. File writes go through `SessionLog`'s worker thread.

Operator control (US2, research R7, R13):
- `pause()` lets the sentence speaking now finish (no `interrupt`), drops audio that is voiced but not yet playing
  (`paused_discard`) and puts its text back at the head of the text queue, so `resume()` voices it again. The writer
  keeps generating the segment it is on.
- `skip()` cancels the sentence speaking, tells the renderer to stop and marks its segment `skipped`; the voiced rest of
  that segment is dropped by the player and the next segment speaks at once. While closing it ends the show.
- `close()` drops the text and voice queues, lets the sentence speaking finish, then says a `closing` segment of at
  most two sentences (`CLOSING_FALLBACK_SENTENCE` when the LLM gives nothing) and ends: `run()` returns.
- `choose()` (US5, FR-018) holds the operator's slot in the planner and discards the segment already generated but not
  yet speaking, so the writer generates the chosen slot right after the segment speaking now, which is never cut. The
  discarded rotation slot comes right after the chosen one: a manual segment does not use up the rotation (R6).

Comments (US6, FR-028, FR-029, research R8): after every sentence the player asks the `InterleaveGate` and, while a
comment turn runs or waits, waits in `wait_clear()` without holding `_floor`, so the reply speaks next. The sentence
it holds and the one voiced behind it are kept, so the interrupted segment goes on with its next sentence and no
scripted sentence is cut. The voicer also starts no new synthesis while the gate is pending, so the reply's sentences
never queue behind scripted ones at a one-sentence-at-a-time TTS engine. The gap that spans a reply is `comment`, kept
out of SC-002 like `paused`. Replies never reach the planner: the rotation is unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from ai_live.brain.guard import OutputGuard, word_form
from ai_live.brain.sanitize import clean_spoken
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.core.config import Settings
from ai_live.core.events import Event, EventBus, EventType, show_error_event
from ai_live.core.logging import log_event
from ai_live.core.models import (
    FINAL_SEGMENT_STATUSES,
    GapKind,
    GuardResult,
    Milestone,
    ScriptSentence,
    Segment,
    SegmentOrigin,
    SegmentRequest,
    SegmentStatus,
    SentenceGap,
    SentenceStatus,
    ShowMode,
    ShowSession,
    ShowState,
    SpokenHistory,
    SpokenLine,
    Topic,
    TurnOutcome,
    Utterance,
)
from ai_live.core.protocols import (
    AvatarRenderer,
    ProductStore,
    RendererUnavailable,
    RenderStatsSource,
    ReplyEngine,
    TTSEngine,
    TTSEngineError,
)
from ai_live.director.faults import FaultInjector, InjectedFault
from ai_live.director.render_report import collect_render_stats_when_settled, report_render_outcome
from ai_live.director.segment_planner import NoSlotAvailable, PlannedSlot, SegmentPlanner
from ai_live.director.session_log import (
    SessionLog,
    error_record,
    script_sentence_record,
    segment_record,
    utterance_record,
)
from ai_live.director.show_stats import ShowStats
from ai_live.products.models import ProductCatalog

logger = logging.getLogger("ai_live.director.script")

SENTENCE_QUEUE_MAX = 2
# A cleaned sentence with fewer letters than this is noise (an emoji line, "ok"), not speech (research R9).
MIN_LETTERS = 4
# How many blocked sentences and errors the control page lists (FR-019).
SNAPSHOT_RECENT = 10
# Pause after a segment whose LLM call failed with nothing to say, so a provider outage is not hammered.
LLM_RETRY_DELAY_S = 1.0
NO_SLOT_RETRY_S = 1.0
HOST_POLL_S = 0.1
# How often a held voicer checks whether the comment turn is over; the gate has no "became clear" event.
VOICE_HOLD_POLL_S = 0.05
DEFAULT_ACK_TIMEOUT_S = 3.0

_OPENING = PlannedSlot(None, Topic.OPENING, SegmentOrigin.ROTATION)
_CLOSING = PlannedSlot(None, Topic.CLOSING, SegmentOrigin.ROTATION)
# Accepted sentences of a discarded segment never play; any other unplayed one was cut short by shutdown.
DISCARDED_DROP_REASON = "segment_discarded"
# Audio dropped by a pause; the text is voiced again on resume, so no `script_sentences.jsonl` line is written.
PAUSED_DROP_REASON = "paused_discard"
# Said when the closing segment has nothing usable (LLM error, all blocked). No digit, so the guard never blocks it on
# an amount; it still goes through the guard like every scripted sentence (research R13).
CLOSING_FALLBACK_SENTENCE = "Cảm ơn cả nhà đã ở lại xem live cùng em, hẹn gặp lại cả nhà ở buổi sau nha."
CLOSING_MIN_SENTENCES = 1
CLOSING_MAX_SENTENCES = 2


class InterleaveGate(Protocol):
    """Comment traffic seen by the script player (contracts/adapters.md §6; one implementation, in ShowDirector)."""

    def pending(self) -> bool: ...

    async def wait_clear(self) -> None: ...


@dataclass
class _Line:
    """Writer -> voicer: one accepted sentence."""

    segment: Segment
    sentence: ScriptSentence
    handed: bool = False  # its audio reached the player, which now owns the voice slot


@dataclass
class _Voiced:
    """Voicer -> player: a sentence whose first audio chunk exists; the rest keeps arriving in `chunks`."""

    segment: Segment
    sentence: ScriptSentence
    chunks: asyncio.Queue[bytes | None]
    # The semaphore this sentence holds a slot of; `close()` swaps in a fresh one for the closing segment.
    slots: asyncio.Semaphore | None = None
    feeder: asyncio.Task[None] | None = None
    discarded: bool = False  # dropped by a pause: the player must not speak it


@dataclass
class _SegmentEnd:
    """The writer has no more sentences for this segment."""

    segment: Segment


@dataclass
class _GapMark:
    """A sentence was lost here (LLM, TTS or render): the next gap is `fault` or `error`, not plain script (R12)."""

    kind: GapKind


_TextItem = _Line | _SegmentEnd | _GapMark


class _LineQueue:
    """Writer -> voicer text queue. Unlike `asyncio.Queue`, a pause can put lines back at the head, in order."""

    def __init__(self) -> None:
        self._items: deque[_TextItem] = deque()
        self._ready = asyncio.Event()

    def put_nowait(self, item: _TextItem) -> None:
        self._items.append(item)
        self._ready.set()

    def push_front(self, items: Iterable[_TextItem]) -> None:
        self._items.extendleft(reversed(list(items)))
        if self._items:
            self._ready.set()

    def drain(self) -> list[_TextItem]:
        items = list(self._items)
        self._items.clear()
        return items

    async def get(self) -> _TextItem:
        while not self._items:
            self._ready.clear()
            await self._ready.wait()
        return self._items.popleft()


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


def _hash(text: str | None) -> str | None:
    return hashlib.sha256(text.encode()).hexdigest()[:12] if text else None


def _error_kind(exc: BaseException) -> str:
    if isinstance(exc, InjectedFault):
        return exc.kind
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, RendererUnavailable):
        return "host_unavailable"
    return str(getattr(exc, "kind", type(exc).__name__))


def _fallback_sentences(*texts: str) -> list[str]:
    """The sentences of `texts`, in order, split like LLM output (research R10)."""
    sentences: list[str] = []
    for text in texts:
        splitter = SentenceSplitter()
        sentences += splitter.feed(text or "")
        sentences += splitter.flush()
    return sentences


def _source(segment: Segment) -> Literal["script", "fallback"]:
    return "fallback" if segment.origin is SegmentOrigin.FALLBACK else "script"


async def _drain(chunks: asyncio.Queue[bytes | None]) -> AsyncIterator[bytes]:
    while (chunk := await chunks.get()) is not None:
        yield chunk


async def next_tts_chunk(stream: AsyncIterator[bytes], timeout_s: float) -> bytes | None:
    """The next chunk of a TTS stream, or None at its end.

    `TTS_TIMEOUT_S` bounds each wait, not the whole sentence (ADR-049): a slow CPU engine may need longer than the
    timeout for a long sentence, while a stalled one is still caught within `timeout_s`.
    """
    async with asyncio.timeout(timeout_s):
        return await anext(stream, None)


def tts_error_text(exc: BaseException) -> str:
    """Operator text for a failed TTS call; a `TTSEngineError` already carries its own (003 contracts/events.md §2)."""
    if isinstance(exc, TTSEngineError):
        return exc.message
    return f"TTS lỗi: {exc}"


async def _aclose(stream: object) -> None:
    aclose = getattr(stream, "aclose", None)
    if aclose is not None:
        with contextlib.suppress(Exception):
            await aclose()


class ScriptRunner:
    def __init__(
        self,
        *,
        show: ShowSession,
        planner: SegmentPlanner,
        engine: ReplyEngine,
        guard: OutputGuard,
        tts: TTSEngine,
        renderer: AvatarRenderer,
        store: ProductStore,
        floor: asyncio.Lock,
        interleave: InterleaveGate,
        faults: FaultInjector,
        stats: ShowStats,
        log: SessionLog,
        bus: EventBus,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
        history: SpokenHistory | None = None,
        wall_clock: Callable[[], datetime] = _now,
    ) -> None:
        self.show = show
        self.planner = planner
        self.engine = engine
        self.guard = guard
        self.tts = tts
        self.renderer = renderer
        self.store = store
        self.stats = stats
        self.log = log
        self.bus = bus
        self.settings = settings
        self.history = history if history is not None else SpokenHistory()
        self._floor = floor
        self._interleave = interleave
        self._faults = faults
        self._clock = clock
        # Wall time of the records (`started_at`, `finished_at`, summary windows); a test can run it fast.
        self._wall = wall_clock
        # Wait after a failed segment in normal mode, so a provider outage is not hammered.
        self.llm_retry_delay_s = LLM_RETRY_DELAY_S
        self._lines = _LineQueue()
        self._voiced: asyncio.Queue[_Voiced | _SegmentEnd | _GapMark] = asyncio.Queue()
        # Counts voiced sentences only, so a segment-end marker never takes a voice slot.
        self._voice_slots = asyncio.Semaphore(SENTENCE_QUEUE_MAX)
        self._next_index = 0
        # Segments not yet in a final status, by id; each has an event set once it starts playing or is final.
        self._open: dict[str, Segment] = {}
        self._settled: dict[str, asyncio.Event] = {}
        self._written: set[str] = set()  # utterance ids that already have a script_sentences.jsonl line
        self._blocked_at: dict[str, str] = {}
        self._last_played: tuple[str, str, float] | None = None  # (utterance_id, segment_id, played_at)
        self._last_text: str | None = None
        self._current_sentence: ScriptSentence | None = None
        self._first_spoken = False
        self._waiting_host = False
        self._tasks: tuple[asyncio.Task[Any], ...] = ()
        # Operator control (US2). Set while the show may voice and play; cleared by `pause()`.
        self._unpaused = asyncio.Event()
        self._unpaused.set()
        self._voice_line: _Line | None = None  # the line the voicer is on, and its job
        self._voice_job: asyncio.Task[None] | None = None
        self._play_item: _Voiced | None = None  # taken by the player, maybe still waiting for the floor
        self._in_speech: _Voiced | None = None  # handed to the renderer; a pause lets it finish once it is heard
        self._speak_task: asyncio.Task[None] | None = None
        self._pause_stop: asyncio.Task[None] | None = None  # keeps the pause's `interrupt()` alive until it ran
        self._paused_gap = False  # the next gap includes a pause
        self._comment_gap = False  # the next gap includes a comment turn (US6)
        self._gap_mark: GapKind | None = None  # a sentence was lost since the last one spoken (`fault` or `error`)
        # Layer 2 of the repeat filter also covers accepted lines not yet spoken (the writer runs a segment ahead):
        # word_form -> utterance_id of the queued line that holds it.
        self._inflight_forms: dict[str, str] = {}
        self._fallback_cursor: dict[str, int] = {}  # next fallback sentence per product (R10)
        self._close_requested = asyncio.Event()
        self._draining = False  # closing: nothing queued before the end may start playing
        self._closing_segment: Segment | None = None
        self._closing_done = asyncio.Event()
        self.ended_by: Literal["operator", "shutdown"] = "shutdown"
        # Operator choice (US5): the rotation slot a choice discarded, said right after the chosen one (research R6).
        self._deferred: PlannedSlot | None = None
        self._last_slot: PlannedSlot | None = None

    # ---------- lifecycle ----------

    async def run(self) -> None:
        """Opening, then rotation, until cancelled or closed. The summary is written in `finally` either way."""
        if self.show.started_at is None:
            self.show.started_at = self._wall()
        self.stats.mark_started(self.show.started_at)
        self._tasks = (
            asyncio.create_task(self._write(), name="script_write"),
            asyncio.create_task(self._voice(), name="script_voice"),
            asyncio.create_task(self._play(), name="script_play"),
        )
        close_wait = asyncio.create_task(self._close_requested.wait(), name="script_close_wait")
        try:
            done, _ = await asyncio.wait({*self._tasks, close_wait}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not close_wait:
                    task.result()  # a tier only returns once a close drains it; a crash is raised here
            if self._close_requested.is_set():
                await self._run_closing()
                self.ended_by = "operator"
        finally:
            close_wait.cancel()
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = ()
            self._drop_queued_audio()
            self._close_open_segments()
            self.show.state = ShowState.ENDED
            self.stats.mark_ended(self._wall(), self.ended_by)
            await self.log.write_show_summary(self.stats.summary())

    # ---------- operator control (US2) ----------

    def pause(self) -> bool:
        """Stop after the sentence speaking now (FR-015). Returns False when the show was not running.

        Audio already voiced is dropped and its text goes back to the head of the text queue, so `resume()` voices it
        again: a long pause never plays stale audio (research R7). The sentence already heard finishes without
        `interrupt()`; one handed to the renderer but not heard yet is stopped and kept like the queued ones.
        """
        if self.show.state is not ShowState.RUNNING:
            return False
        self.show.state = ShowState.PAUSED
        self._unpaused.clear()
        self._paused_gap = True
        kept: list[_TextItem] = []
        speaking, task = self._in_speech, self._speak_task
        if (
            speaking is not None
            and task is not None
            and not task.done()
            and self.renderer.first_playback_at(speaking.sentence.utterance_id) is None
        ):
            # Handed to the renderer but not heard yet: the lip-sync fork starts a sentence ~1 s after its audio
            # arrives, so it would begin after the pause (005 T062). Not started means not "speaking now": it waits for
            # resume like the queued ones. Discarded now, so it cannot count as played; stopped in one task step
            # (see `_stop_unheard`).
            kept.append(self._unvoice(speaking))
            self._pause_stop = asyncio.create_task(self._stop_unheard(task), name="script_pause_stop")
        taken = self._play_item
        if taken is not None and taken is not self._in_speech:
            kept.append(self._unvoice(taken))  # its slot was released when the player took it
        while not self._voiced.empty():
            queued = self._voiced.get_nowait()
            if isinstance(queued, _Voiced):
                if queued.slots is not None:
                    queued.slots.release()
                kept.append(self._unvoice(queued))
            else:
                kept.append(queued)
        job, line = self._voice_job, self._voice_line
        if job is not None and not job.done():
            job.cancel()
            if line is not None and not line.handed:
                kept.append(_Line(line.segment, line.sentence))
        self._lines.push_front(kept)
        log_event(logger, "show_paused", show_id=self.show.show_id, requeued=len(kept))
        return True

    def resume(self) -> bool:
        """Back to running; the kept text is voiced again (US2 #2). Returns False when the show was not paused."""
        if self.show.state is not ShowState.PAUSED:
            return False
        self.show.state = ShowState.RUNNING
        self._unpaused.set()
        log_event(logger, "show_resumed", show_id=self.show.show_id)
        return True

    async def skip(self) -> tuple[str | None, str | None]:
        """Cut the scripted sentence speaking now and drop the rest of its segment (FR-016).

        Returns `(utterance_id, segment_id)` of what was cut; `(None, None)` when there was nothing to skip. While
        closing it stops the show at once.
        """
        closing = self.show.state is ShowState.CLOSING
        speaking = self._in_speech
        segment = speaking.segment if speaking is not None else self.show.current_segment
        if segment is None and closing:
            segment = self._closing_segment
        task = self._speak_task
        cut = speaking is not None and task is not None and not task.done()
        utterance_id: str | None = None
        if cut:
            assert speaking is not None and task is not None
            utterance_id = speaking.sentence.utterance_id
            # Cancel before interrupting, with no await in between: the renderer still knows what is speaking, and a
            # released ack wait cannot let this sentence count as played.
            task.cancel()
            self._last_played = (utterance_id, speaking.segment.segment_id, self._clock())
        if segment is not None and segment.segment_id in self._open:
            self._finalize(segment, SegmentStatus.SKIPPED)
        if closing:
            if self._closing_segment is not None and self._closing_segment.segment_id in self._open:
                self._finalize(self._closing_segment, SegmentStatus.SKIPPED)
            self._closing_done.set()
        if cut:
            await self.renderer.interrupt()
        if segment is None and utterance_id is None:
            return None, None
        log_event(
            logger,
            "segment_skipped",
            show_id=self.show.show_id,
            segment_id=segment.segment_id if segment is not None else None,
            utterance_id=utterance_id,
        )
        return utterance_id, segment.segment_id if segment is not None else None

    def close(self) -> bool:
        """Start the end of the show (FR-017): `run()` finishes the sentence, says the closing and returns.

        Returns False when the show is not running or paused (already closing or ended).
        """
        if self.show.state not in (ShowState.RUNNING, ShowState.PAUSED):
            return False
        self.show.state = ShowState.CLOSING
        self._draining = True
        self._close_requested.set()
        log_event(logger, "show_closing", show_id=self.show.show_id)
        return True

    def choose(self, product_id: str | None, topic: Topic | None) -> PlannedSlot:
        """The operator's slot for the next segment (FR-018); raises `TopicUnavailable` for a combination without data.

        The segment speaking now finishes (US5 #1). A segment already generated (or being generated) but not yet
        speaking is discarded, which wakes the writer, and the chosen slot is generated in its place. The opening is
        never discarded: a choice made before it speaks applies after it. `ShowDirector` refuses it unless the show
        is running or paused.
        """
        slot = self.planner.choose(product_id, topic)
        for segment in sorted(self._open.values(), key=lambda s: s.index):
            if segment is self.show.current_segment or not segment.topic.has_product:
                continue
            if segment.status not in (SegmentStatus.PREPARING, SegmentStatus.READY):
                continue
            if segment.origin is SegmentOrigin.ROTATION and self._deferred is None:
                self._deferred = PlannedSlot(segment.product_id, segment.topic, SegmentOrigin.ROTATION)
            self._discard(segment)
        log_event(
            logger,
            "next_segment_chosen",
            show_id=self.show.show_id,
            product_id=slot.product_id,
            topic=slot.topic.value,
        )
        # No segment exists yet, so no `segment_id`; `planned` matches `next.status` of the snapshot.
        self.bus.publish(
            Event(
                EventType.SEGMENT_NEXT,
                {
                    "product_id": slot.product_id,
                    "topic": slot.topic.value,
                    "origin": slot.origin.value,
                    "status": "planned",
                },
            )
        )
        return slot

    def _unvoice(self, item: _Voiced) -> _Line:
        """Drop a voiced sentence's audio; return its text for the head of the text queue."""
        item.discarded = True
        if item.feeder is not None:
            item.feeder.cancel()
        # Voiced again later: the milestone must time the new audio, not the dropped one.
        item.sentence.marks.pop(Milestone.TTS_FIRST_CHUNK, None)
        log_event(
            logger,
            "sentence_dropped",
            show_id=self.show.show_id,
            segment_id=item.segment.segment_id,
            utterance_id=item.sentence.utterance_id,
            reason=PAUSED_DROP_REASON,
        )
        return _Line(item.segment, item.sentence)

    async def _stop_unheard(self, task: asyncio.Task[None]) -> None:
        """Cut the sentence a pause took back before it was heard.

        Cancel and stop with no await in between, as `skip()` does: once the cancelled `speak` unwinds, the renderer
        no longer knows the sentence and would not send `stop` for it.
        """
        task.cancel()
        try:
            await self.renderer.interrupt()
        except Exception as exc:  # nobody awaits this task; the next sentence surfaces a dead renderer
            log_event(logger, "pause_stop_failed", logging.WARNING, show_id=self.show.show_id, error=str(exc))

    def _drop_queued_audio(self) -> None:
        """Stop the TTS streams of voiced sentences that will never play."""
        while not self._voiced.empty():
            queued = self._voiced.get_nowait()
            if isinstance(queued, _Voiced) and queued.feeder is not None:
                queued.feeder.cancel()

    async def _run_closing(self) -> None:
        """Finish the sentence speaking, drop everything queued, then speak the closing segment."""
        old = self._tasks
        speaking = self._in_speech is not None
        for task in old:
            if task.get_name() != "script_play" or not speaking:
                task.cancel()
        # The player returns by itself after the sentence speaking now (it sees `_draining`).
        await asyncio.wait(old)
        for task in old:
            if not task.cancelled() and task.exception() is not None:
                logger.warning("script_tier_failed_before_closing", exc_info=task.exception())
        self._drop_queued_audio()
        self._lines.drain()
        # Like shutdown: a segment that has spoken is done, one not yet heard is discarded.
        self._close_open_segments()
        if self._closing_done.is_set():
            return  # skipped while the last sentence was finishing
        self._lines = _LineQueue()
        self._voiced = asyncio.Queue()
        self._voice_slots = asyncio.Semaphore(SENTENCE_QUEUE_MAX)
        self._draining = False
        self._unpaused.set()
        prepare = asyncio.create_task(self._prepare(_CLOSING, closing=True), name="script_closing")
        self._tasks = (
            prepare,
            asyncio.create_task(self._voice(), name="script_voice"),
            asyncio.create_task(self._play(), name="script_play"),
        )
        done_wait = asyncio.create_task(self._closing_done.wait(), name="script_closing_wait")
        pending: set[asyncio.Task[Any]] = {done_wait, *self._tasks}
        try:
            while not self._closing_done.is_set():
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task is not done_wait:
                        task.result()
        finally:
            done_wait.cancel()

    def on_catalog_replaced(self, catalog: ProductCatalog) -> None:
        """New content: the rotation follows it at once, and the prepared (not yet playing) segment is discarded.

        The segment already speaking finishes (contracts/api.md §3), unless its product was removed from the file:
        the player then drops the rest of it before the next sentence (research R7, "Sản phẩm bị bỏ").
        """
        self.planner.replace_catalog(catalog)
        self.stats.set_catalog(catalog)
        for segment in list(self._open.values()):
            if segment.status in (SegmentStatus.PREPARING, SegmentStatus.READY) and (
                segment.catalog_version != catalog.version
            ):
                self._discard(segment)

    # ---------- tier 1: write ----------

    async def _write(self) -> None:
        slot = _OPENING
        while True:
            settled = await self._prepare(slot)
            await settled.wait()
            slot = await self._next_slot()

    async def _next_slot(self) -> PlannedSlot:
        while True:
            catalog = self.store.catalog
            if self.planner.catalog.version != catalog.version:
                # Content replaced without `on_catalog_replaced` (e.g. a direct store install): follow it anyway.
                self.planner.replace_catalog(catalog)
                self.stats.set_catalog(catalog)
            slot = self._pick_slot()
            if slot is not None:
                self._last_slot = slot
                return slot
            await asyncio.sleep(NO_SLOT_RETRY_S)

    def _pick_slot(self) -> PlannedSlot | None:
        """The operator's slot first, then the rotation slot it pushed back, then the rotation (research R6)."""
        override = self.planner.take_override()
        if override is not None:
            return override
        deferred, self._deferred = self._deferred, None
        if (
            deferred is not None
            and deferred.product_id is not None
            and deferred.topic in self.planner.available_topics(deferred.product_id)
            and not self._repeats_last(deferred)
        ):
            return deferred
        try:
            return self.planner.next_slot()
        except NoSlotAvailable:
            return None

    def _repeats_last(self, slot: PlannedSlot) -> bool:
        """The operator chose the very slot that was discarded: saying it twice in a row is a repeat (R6)."""
        last = self._last_slot
        return last is not None and (last.product_id, last.topic) == (slot.product_id, slot.topic)

    async def _prepare(self, slot: PlannedSlot, *, closing: bool = False) -> asyncio.Event:
        """Generate one segment's text into the text queue; returns the event set when it plays or is final.

        `closing`: the end-of-show segment, 1 to 2 sentences, with `CLOSING_FALLBACK_SENTENCE` when nothing usable came.
        In fallback mode this call is the retry of R10 (shorter timeout); when it fails too, a fallback segment follows.
        """
        catalog = self.store.catalog
        segment, settled, requested = self._open_segment(slot.product_id, slot.topic, slot.origin, catalog)
        if closing:
            self._closing_segment = segment
            accepted, llm_failed, injected = await self._generate(
                segment, catalog, requested, min_sentences=CLOSING_MIN_SENTENCES, max_sentences=CLOSING_MAX_SENTENCES
            )
        else:
            retrying = self.show.mode is ShowMode.FALLBACK
            timeout_s = self.settings.script_retry_timeout_s if retrying else self.settings.script_llm_timeout_s
            accepted, llm_failed, injected = await self._generate(segment, catalog, requested, timeout_s=timeout_s)
            self._update_mode(segment, llm_failed)
        if llm_failed:
            # The lost text leaves a hole in the script: the next gap is labelled by its cause (research R12).
            self._lines.put_nowait(_GapMark(GapKind.FAULT if injected else GapKind.ERROR))
        if segment.status in FINAL_SEGMENT_STATUSES:
            return settled
        if closing and not accepted:
            # The show still ends politely; the fixed sentence is voiced and rendered live like any other.
            log_event(logger, "closing_fallback", show_id=self.show.show_id, segment_id=segment.segment_id)
            if self._take(segment, catalog, CLOSING_FALLBACK_SENTENCE, requested, over_max=False, dedup=False):
                accepted = 1
        if accepted:
            self._lines.put_nowait(_SegmentEnd(segment))
            return settled
        blocked = any(s.status is SentenceStatus.BLOCKED for s in segment.sentences)
        self._finalize(segment, SegmentStatus.BLOCKED if blocked and not llm_failed else SegmentStatus.FAILED)
        if llm_failed and not closing:
            if self.show.mode is ShowMode.FALLBACK:
                return await self._prepare_fallback(slot.product_id)
            await asyncio.sleep(self.llm_retry_delay_s)
        return settled

    def _open_segment(
        self, product_id: str | None, topic: Topic, origin: SegmentOrigin, catalog: ProductCatalog
    ) -> tuple[Segment, asyncio.Event, float]:
        """A new segment in `preparing`, logged as requested. Returns it, its settled event and the request time."""
        segment = Segment(
            segment_id=uuid.uuid4().hex,
            show_id=self.show.show_id,
            index=self._next_index,
            product_id=product_id,
            topic=topic,
            origin=origin,
            mode=self.show.mode,
            catalog_version=catalog.version,
            requested_at=self._wall(),
        )
        self._next_index += 1
        settled = asyncio.Event()
        self._open[segment.segment_id] = segment
        self._settled[segment.segment_id] = settled
        self.show.next_segment = segment
        requested = self._clock()
        log_event(
            logger,
            "segment_requested",
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            product_id=segment.product_id,
            topic=segment.topic.value,
            origin=segment.origin.value,
            mode=segment.mode.value,
            t_mono=requested,
        )
        return segment, settled, requested

    async def _prepare_fallback(self, product_id: str | None) -> asyncio.Event:
        """R10 fallback segment: the next sentences of the product's own `intro` then `description`, verbatim.

        They still go through cleaning, the guard, TTS and the realtime renderer. Each product has its own cursor,
        which wraps around. The opening slot has no product, so the main product stands in.
        """
        catalog = self.store.catalog
        product = next((p for p in catalog.products if p.id == product_id), None)
        if product is None and catalog.products:
            product = catalog.primary
        if product is None:
            await asyncio.sleep(self.llm_retry_delay_s)
            settled = asyncio.Event()
            settled.set()
            return settled
        segment, settled, requested = self._open_segment(product.id, Topic.INTRO, SegmentOrigin.FALLBACK, catalog)
        pool = _fallback_sentences(product.intro, product.description)
        count = min(self.settings.script_segment_min_sentences, len(pool))
        first = self._fallback_cursor.get(product.id, 0)
        accepted = 0
        for i in range(count):
            # Fallback text may be read again later (SC-005), so it skips the repeat filter.
            if self._take(segment, catalog, pool[(first + i) % len(pool)], requested, over_max=False, dedup=False):
                accepted += 1
        if pool:
            self._fallback_cursor[product.id] = (first + count) % len(pool)
        if accepted:
            self._lines.put_nowait(_SegmentEnd(segment))
            return settled
        blocked = any(s.status is SentenceStatus.BLOCKED for s in segment.sentences)
        self._finalize(segment, SegmentStatus.BLOCKED if blocked else SegmentStatus.FAILED)
        await asyncio.sleep(self.llm_retry_delay_s)
        return settled

    def _update_mode(self, segment: Segment, llm_failed: bool) -> None:
        """R10: enter fallback after `SCRIPT_FALLBACK_AFTER` service errors in a row; a successful retry leaves it."""
        show = self.show
        if not llm_failed and show.mode is ShowMode.FALLBACK:
            segment.mode = ShowMode.NORMAL
            self._set_mode(ShowMode.NORMAL, "retry_succeeded")
        elif (
            llm_failed
            and show.mode is ShowMode.NORMAL
            and show.consecutive_llm_failures >= self.settings.script_fallback_after
        ):
            self._set_mode(ShowMode.FALLBACK, "fallback_after_failures")

    def _set_mode(self, mode: ShowMode, reason: str) -> None:
        show = self.show
        old, show.mode = show.mode, mode
        self.stats.record_mode_change(mode, self._wall())
        log_event(
            logger,
            "mode_changed",
            logging.WARNING if mode is ShowMode.FALLBACK else logging.INFO,
            show_id=show.show_id,
            consecutive_failures=show.consecutive_llm_failures,
            **{"from": old.value, "to": mode.value},
        )
        log_event(logger, "show_state", show_id=show.show_id, state=show.state.value, mode=mode.value, reason=reason)
        self.bus.publish(
            Event(EventType.SHOW_STATE, {"show_id": show.show_id, "state": show.state.value, "mode": mode.value})
        )

    async def _generate(
        self,
        segment: Segment,
        catalog: ProductCatalog,
        requested: float,
        *,
        min_sentences: int | None = None,
        max_sentences: int | None = None,
        timeout_s: float | None = None,
    ) -> tuple[int, bool, bool]:
        """Returns (accepted sentences, whether the LLM step failed, whether that failure was an injected fault).

        `timeout_s` bounds the whole segment, not each sentence (default `SCRIPT_LLM_TIMEOUT_S`).
        """
        settings = self.settings
        request = SegmentRequest(
            segment_id=segment.segment_id,
            topic=segment.topic,
            product_id=segment.product_id,
            min_sentences=min_sentences if min_sentences is not None else settings.script_segment_min_sentences,
            max_sentences=max_sentences if max_sentences is not None else settings.script_segment_max_sentences,
            previous_sentence=self._last_text,
            recent_lines=self.history.recent_for(segment.product_id, settings.script_history_sentences),
        )
        if timeout_s is None:
            timeout_s = settings.script_llm_timeout_s
        deadline = requested + timeout_s
        injected = self._faults.pending("llm") > 0
        stream = self._faults.stream("llm", lambda: self.engine.narrate(request, catalog))
        raw_count = accepted = 0
        llm_failed = False
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(anext(stream), max(0.0, deadline - self._clock()))
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    llm_failed = True
                    message = f"LLM quá {timeout_s} s chưa sinh xong phân đoạn"
                    self._segment_error(segment, "llm", "timeout", message)
                    break
                except Exception as exc:
                    llm_failed = True
                    kind = _error_kind(exc)
                    self._segment_error(segment, "llm", kind, f"{kind}: {exc}")
                    break
                if segment.status in FINAL_SEGMENT_STATUSES:
                    break  # discarded while generating: stop paying for text nobody will hear
                raw_count += 1
                if self._take(segment, catalog, raw, requested, over_max=raw_count > request.max_sentences):
                    accepted += 1
                if raw_count > request.max_sentences:
                    break
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()
        if llm_failed:
            self.show.consecutive_llm_failures += 1
        else:
            self.show.consecutive_llm_failures = 0
        return accepted, llm_failed, llm_failed and injected

    def _take(
        self,
        segment: Segment,
        catalog: ProductCatalog,
        raw: str,
        requested: float,
        *,
        over_max: bool,
        dedup: bool = True,
    ) -> bool:
        """Clean, check and queue one sentence out of the LLM. Returns True when it goes on to TTS.

        `dedup`: layer 2 of the repeat filter (research R11) drops a sentence whose `word_form` was already said, or is
        already queued to be said. Fixed and fallback text skips it.
        """
        at = self._clock()
        text = clean_spoken(raw)
        sentence = ScriptSentence(
            utterance_id=uuid.uuid4().hex,
            segment_id=segment.segment_id,
            seq=len(segment.sentences),
            raw_text=raw,
            text=text,
            word_form=word_form(text),
        )
        sentence.marks[Milestone.SEGMENT_REQUESTED] = requested
        sentence.marks[Milestone.LLM_FIRST_SENTENCE] = at
        segment.sentences.append(sentence)
        if over_max:
            self._drop(segment, sentence, "sentence_count_exceeded")
            return False
        if _letters(text) < MIN_LETTERS:
            self._drop(segment, sentence, "empty_after_clean")
            return False
        try:
            result = self.guard.check(text, catalog)
        except Exception as exc:
            # Fail closed: a sentence the guard could not check is never spoken.
            self._segment_error(segment, "guard", type(exc).__name__, f"Guard lỗi: {exc}", sentence.utterance_id)
            result = GuardResult(ok=False)
        if not result.ok:
            self._block(segment, sentence, result)
            return False
        if dedup:
            form = sentence.word_form
            if form in self.history.seen_word_forms or form in self._inflight_forms:
                self._drop(segment, sentence, "duplicate")
                return False
            self._inflight_forms[form] = sentence.utterance_id
        self._log_milestone(segment, sentence, Milestone.LLM_FIRST_SENTENCE, at)
        if segment.status is SegmentStatus.PREPARING:
            segment.status = SegmentStatus.READY
            segment.ready_at = self._wall()
            log_event(
                logger,
                "segment_ready",
                show_id=self.show.show_id,
                segment_id=segment.segment_id,
                first_sentence_s=round(at - requested, 3),
            )
            self._publish_next(segment, segment.status.value)
        self._lines.put_nowait(_Line(segment, sentence))
        return True

    def _drop(self, segment: Segment, sentence: ScriptSentence, reason: str) -> None:
        sentence.status = SentenceStatus.DROPPED
        sentence.drop_reason = reason
        log_event(
            logger,
            "sentence_dropped",
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            utterance_id=sentence.utterance_id,
            reason=reason,
        )
        self._write_sentence(segment, sentence)

    def _block(self, segment: Segment, sentence: ScriptSentence, result: GuardResult) -> None:
        sentence.status = SentenceStatus.BLOCKED
        sentence.guard_reason = result.reason
        sentence.guard_detail = result.detail
        reason = result.reason.value if result.reason else None
        self.show.recent_blocked.append(sentence)
        self._blocked_at[sentence.utterance_id] = _iso(self._wall()) or ""
        # The sentence itself stays out of INFO logs (hash only); it goes to the localhost control page and the
        # session file (contracts/api.md §4).
        log_event(
            logger,
            "guard_blocked",
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            utterance_id=sentence.utterance_id,
            reason=reason,
            sentence_hash=_hash(sentence.text),
            detail_hash=_hash(result.detail),
        )
        self.bus.publish(
            Event(
                EventType.GUARD_BLOCKED,
                {
                    "utterance_id": sentence.utterance_id,
                    "segment_id": segment.segment_id,
                    "reason": reason,
                    "reason_label": result.reason.label if result.reason else None,
                    "text": sentence.text,
                },
            )
        )
        self._write_sentence(segment, sentence)

    # ---------- tier 2: voice ----------

    async def _voice(self) -> None:
        """Voice lines in order, one at a time. Each line is its own job, so `pause()` can cancel just that line."""
        while True:
            await self._unpaused.wait()
            item = await self._lines.get()
            if not self._unpaused.is_set():
                self._lines.push_front([item])
                continue
            if isinstance(item, _SegmentEnd | _GapMark):
                self._voiced.put_nowait(item)
                continue
            if item.segment.status in FINAL_SEGMENT_STATUSES:
                continue
            job = asyncio.create_task(self._voice_one(item), name="script_voice_one")
            self._voice_line, self._voice_job = item, job
            try:
                await asyncio.wait({job})
            finally:
                self._voice_line = self._voice_job = None
                if not job.done():
                    job.cancel()
            if not job.cancelled() and (exc := job.exception()) is not None:
                raise exc

    async def _voice_one(self, item: _Line) -> None:
        slots = self._voice_slots
        await slots.acquire()
        try:
            await self._yield_to_comments()
            if item.segment.status not in FINAL_SEGMENT_STATUSES:
                await self._synthesize(item, slots)
        finally:
            if not item.handed:
                slots.release()

    async def _yield_to_comments(self) -> None:
        """Start no scripted synthesis while a comment turn runs or waits (SC-011).

        A CPU engine voices one sentence at a time (VieNeu holds its lock per sentence, FIFO), so a scripted sentence
        started here would slot in before the reply's next sentence and push that wait past `TTS_TIMEOUT_S`. The player
        usually holds a voiced sentence for right after the reply, so holding the voicer adds no gap. Closing never
        waits: the closing segment must be voiced.
        """
        while self.show.state is not ShowState.CLOSING and self._interleave.pending():  # noqa: ASYNC110
            await asyncio.sleep(VOICE_HOLD_POLL_S)

    async def _synthesize(self, item: _Line, slots: asyncio.Semaphore) -> None:
        """TTS one sentence; hand it to the player once the first chunk exists, then wait for the rest of its audio."""
        segment, sentence = item.segment, item.sentence
        timeout_s = self.settings.tts_timeout_s
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        injected = self._faults.pending("tts") > 0
        stream = self._faults.stream("tts", lambda: self.tts.synthesize(sentence.text))
        try:
            try:
                first = await next_tts_chunk(stream, timeout_s)
            except Exception as exc:
                kind = _error_kind(exc)
                message = f"TTS quá {timeout_s} s" if kind == "timeout" else tts_error_text(exc)
                self._segment_error(segment, "tts", kind, message, sentence.utterance_id)
                # Only this sentence is lost; the next one is voiced right away (FR-020, US3 #4).
                sentence.status = SentenceStatus.TTS_ERROR
                self._write_sentence(segment, sentence)
                self._voiced.put_nowait(_GapMark(GapKind.FAULT if injected else GapKind.ERROR))
                return
            self._log_milestone(segment, sentence, Milestone.TTS_FIRST_CHUNK, self._clock())
            if first is not None:
                chunks.put_nowait(first)
            feeder = asyncio.create_task(self._feed(segment, sentence, stream, chunks), name="script_tts_feed")
            item.handed = True
            self._voiced.put_nowait(_Voiced(segment, sentence, chunks, slots, feeder))
        finally:
            if not item.handed:
                await _aclose(stream)
        # `wait`, not `await feeder`: cancelling this job (a pause) must not cut audio the player is speaking.
        await asyncio.wait({feeder})

    async def _feed(
        self,
        segment: Segment,
        sentence: ScriptSentence,
        stream: AsyncIterator[bytes],
        chunks: asyncio.Queue[bytes | None],
    ) -> None:
        """Stream the rest of a sentence's audio; cancelled when that audio is dropped."""
        timeout_s = self.settings.tts_timeout_s
        try:
            while (chunk := await next_tts_chunk(stream, timeout_s)) is not None:
                chunks.put_nowait(chunk)
        except Exception as exc:
            kind = _error_kind(exc)
            message = f"TTS quá {timeout_s} s" if kind == "timeout" else tts_error_text(exc)
            self._segment_error(segment, "tts", kind, message, sentence.utterance_id)
        finally:
            chunks.put_nowait(None)
            await _aclose(stream)

    # ---------- tier 3: play ----------

    async def _play(self) -> None:
        while True:
            await self._unpaused.wait()
            item = await self._voiced.get()
            if isinstance(item, _SegmentEnd):
                self._end_segment(item.segment)
                continue
            if isinstance(item, _GapMark):
                self._note_gap(item.kind)
                continue
            if item.slots is not None:
                item.slots.release()
            if not self._unpaused.is_set():
                self._lines.push_front([self._unvoice(item)])
                continue
            self._play_item = item
            try:
                await self._play_one(item)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One broken sentence must not end the show.
                logger.exception("script_play_crashed")
            finally:
                self._play_item = None
                if item.feeder is not None:
                    item.feeder.cancel()  # no-op once fully spoken; stops TTS for audio that will not play
            if self._draining:
                return  # closing: the sentence that was speaking is done, the closing segment comes next

    def _skip_item(self, item: _Voiced) -> bool:
        """Dropped by a pause, part of a final segment, or queued before a close: do not speak it."""
        return item.discarded or self._draining or item.segment.status in FINAL_SEGMENT_STATUSES

    async def _play_one(self, item: _Voiced) -> None:
        segment, sentence = item.segment, item.sentence
        if not self._still_valid(segment):
            self._discard(segment)
        if self._skip_item(item):
            return
        if self.show.state is not ShowState.CLOSING and self._interleave.pending():
            # A comment turn is running or waiting: it speaks between two scripted sentences (research R8). The
            # voiced audio stays with this item and the voicer, so nothing is synthesized twice.
            self._comment_gap = True
            await self._interleave.wait_clear()
        await self._wait_host()
        injected = False
        try:
            if self._floor.locked():
                # Only a comment turn holds the floor besides this player (a reply started after the gate check,
                # or one already speaking when the show began closing): the gap spans that reply.
                self._comment_gap = True
            async with self._floor:
                # Re-checked under the floor: a pause, skip or close may have come while this sentence waited.
                if self._skip_item(item):
                    return
                paused_gap, self._paused_gap = self._paused_gap, False
                if segment.status is not SegmentStatus.SPEAKING:
                    self._start_segment(segment)
                self._current_sentence = sentence
                self.bus.publish(
                    Event(
                        EventType.SENTENCE,
                        {
                            "utterance_id": sentence.utterance_id,
                            "seq": 0,
                            "text": sentence.text,
                            "segment_id": segment.segment_id,
                        },
                    )
                )
                self._in_speech = item
                injected = self._faults.pending("render") > 0
                try:
                    await self._faults.check_render(getattr(self.renderer, "ack_timeout_s", DEFAULT_ACK_TIMEOUT_S))
                    spoken = await self._speak(item)
                finally:
                    self._in_speech = None
        except Exception as exc:
            kind = _error_kind(exc)
            report_render_outcome(self.renderer, sentence.utterance_id, False, kind)
            # A pending render fault was consumed by `check_render`, so any failure here is the injected one.
            self._note_gap(GapKind.FAULT if injected else GapKind.ERROR)
            sentence.status = SentenceStatus.RENDER_ERROR
            self._mark_first_frame(segment, sentence)
            self._segment_error(
                segment, "render", kind, f"Renderer lỗi: {type(exc).__name__}: {exc}", sentence.utterance_id
            )
            self._write_sentence(segment, sentence)
            return
        if not spoken:
            return  # cut while speaking: `skip()` already wrote its line
        # Each scripted sentence is its own turn for the fallback counter (contracts/adapters.md §2).
        report_render_outcome(self.renderer, sentence.utterance_id, True)
        if segment.status in FINAL_SEGMENT_STATUSES:
            return  # skipped right after it finished: `skip()` already wrote its line
        played_at = self._clock()
        sentence.played_at = played_at
        sentence.status = SentenceStatus.SPOKEN
        first = self._mark_first_frame(segment, sentence)
        self._record_gap(segment, sentence, first, paused=paused_gap)
        self._last_played = (sentence.utterance_id, segment.segment_id, played_at)
        self._last_text = sentence.text
        if first is not None and not self._first_spoken:
            self._first_spoken = True
            self.stats.record_first_sentence(first - self.show.start_requested_at)
        log_event(
            logger,
            "sentence_played",
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            utterance_id=sentence.utterance_id,
            t_mono=played_at,
        )
        # No `TurnLatency` for scripted sentences (004 R2): the figures go to the log only.
        collect_render_stats_when_settled(self.renderer, sentence.utterance_id)
        self.history.add(SpokenLine(sentence.text, sentence.word_form, segment.product_id, _source(segment)))
        self._write_sentence(segment, sentence)
        utt = Utterance(
            utterance_id=sentence.utterance_id,
            comment_id=None,
            catalog_version=segment.catalog_version,
            sentences=[sentence.text],
            marks=dict(sentence.marks),
            outcome=TurnOutcome.COMPLETED,
            segment_id=segment.segment_id,
            show_id=self.show.show_id,
        )
        self.log.write_utterance(utterance_record(utt, None))

    async def _speak(self, item: _Voiced) -> bool:
        """Render one sentence as its own task, so `skip()` can cancel it. Returns False when it was cut."""
        if item.segment.status in FINAL_SEGMENT_STATUSES:
            return False  # skipped while the render check ran
        sentence = item.sentence
        task = asyncio.create_task(
            self.renderer.speak(sentence.utterance_id, sentence.text, _drain(item.chunks), self.tts.sample_rate),
            name="script_speak",
        )
        self._speak_task = task
        try:
            await asyncio.wait({task})
        finally:
            self._speak_task = None
            if not task.done():
                task.cancel()
        if task.cancelled() or item.discarded:
            return False  # a discarded one was taken back by a pause and is spoken again on resume
        task.result()
        return True

    def _still_valid(self, segment: Segment) -> bool:
        """A segment about a removed product stops; one not yet started must also match the loaded catalog."""
        if segment.status in FINAL_SEGMENT_STATUSES:
            return True
        catalog = self.store.catalog
        if segment.product_id is not None and all(p.id != segment.product_id for p in catalog.products):
            return False
        return segment.status is SegmentStatus.SPEAKING or segment.catalog_version == catalog.version

    async def _wait_host(self) -> None:
        """Hold the show while the host page is gone, instead of failing (and paying for) every next segment."""
        if getattr(self.renderer, "host_ready", True):
            return
        if not self._waiting_host:
            self._waiting_host = True
            log_event(logger, "show_waiting_host", logging.WARNING, show_id=self.show.show_id)
        # Polled: `host_ready` is a plain property of the renderer protocol, there is no event to wait on.
        while not getattr(self.renderer, "host_ready", True):  # noqa: ASYNC110
            await asyncio.sleep(HOST_POLL_S)
        self._waiting_host = False

    def _mark_first_frame(self, segment: Segment, sentence: ScriptSentence) -> float | None:
        first = self.renderer.first_playback_at(sentence.utterance_id)
        if first is not None:
            self._log_milestone(segment, sentence, Milestone.AVATAR_FIRST_FRAME, first)
        return first

    def _note_gap(self, kind: GapKind) -> None:
        """A sentence was lost before the next one spoken; a real error outranks an injected fault (research R12)."""
        if self._gap_mark is not GapKind.ERROR:
            self._gap_mark = kind

    def _record_gap(
        self, segment: Segment, sentence: ScriptSentence, first: float | None, *, paused: bool = False
    ) -> None:
        mark, self._gap_mark = self._gap_mark, None
        comment, self._comment_gap = self._comment_gap, False
        last = self._last_played
        if last is None or first is None:
            return
        last_id, last_segment, last_played_at = last
        # With LIVETALKING_LEAD_S `speak` returned up to `lead_s` before the sentence finished playing: the
        # renderer's own `sentence_played` time is the silence the viewer heard (005 R15).
        played = self.renderer.render_stats(last_id) if isinstance(self.renderer, RenderStatsSource) else None
        if played is not None and played.last_played_at is not None and played.last_played_at <= first:
            last_played_at = played.last_played_at
        if paused:
            kind = GapKind.PAUSED  # the operator's pause, not the pipeline, made this silence (research R12)
        elif comment:
            kind = GapKind.COMMENT  # a reply spoke in between; its time is the reply's, not a script gap (R12)
        elif mark is not None:
            kind = mark  # `fault` stays out of SC-002; `error` counts against it
        else:
            kind = GapKind.SCRIPT if last_segment == segment.segment_id else GapKind.SEGMENT_BOUNDARY
        gap = SentenceGap(last_id, sentence.utterance_id, round(max(0.0, first - last_played_at), 3), kind)
        self.stats.record_gap(gap)
        log_event(
            logger,
            "sentence_gap",
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            from_utterance_id=gap.from_utterance_id,
            to_utterance_id=gap.to_utterance_id,
            seconds=gap.seconds,
            kind=gap.kind.value,
        )

    # ---------- segments ----------

    def _start_segment(self, segment: Segment) -> None:
        segment.status = SegmentStatus.SPEAKING
        segment.started_at = self._wall()
        self.show.current_segment = segment
        if self.show.next_segment is segment:
            self.show.next_segment = None
        counts = segment_record(segment)["sentences"]
        log_event(
            logger,
            "segment_started",
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            product_id=segment.product_id,
            topic=segment.topic.value,
            status=segment.status.value,
            spoken=counts[SentenceStatus.SPOKEN.value],
            blocked=counts[SentenceStatus.BLOCKED.value],
            dropped=counts[SentenceStatus.DROPPED.value],
        )
        self.bus.publish(
            Event(
                EventType.SEGMENT_STARTED,
                {
                    "segment_id": segment.segment_id,
                    "product_id": segment.product_id,
                    "product_name": self._product_name(segment.product_id),
                    "topic": segment.topic.value,
                    "topic_label": segment.topic.label,
                    "origin": segment.origin.value,
                    "mode": segment.mode.value,
                },
            )
        )
        settled = self._settled.get(segment.segment_id)
        if settled is not None:
            settled.set()

    def _end_segment(self, segment: Segment) -> None:
        if segment.status in FINAL_SEGMENT_STATUSES:
            return
        spoken = any(s.status is SentenceStatus.SPOKEN and s.played_at is not None for s in segment.sentences)
        self._finalize(segment, SegmentStatus.DONE if spoken else SegmentStatus.FAILED)

    def _discard(self, segment: Segment) -> None:
        if segment.segment_id not in self._open:
            return
        self._finalize(segment, SegmentStatus.DISCARDED)
        self._publish_next(segment, SegmentStatus.DISCARDED.value)

    def _finalize(self, segment: Segment, status: SegmentStatus, *, shutdown: bool = False) -> None:
        """Final status: write the `segments.jsonl` line, update stats and wake the writer. Runs once per segment."""
        if self._open.pop(segment.segment_id, None) is None:
            return
        segment.status = status
        segment.finished_at = self._wall()
        for sentence in segment.sentences:
            if sentence.utterance_id in self._written:
                continue
            # Accepted but never played: dropped with a discarded segment, or cut short when the show stopped.
            if status is SegmentStatus.DISCARDED and not shutdown:
                sentence.status = SentenceStatus.DROPPED
                sentence.drop_reason = DISCARDED_DROP_REASON
            else:
                sentence.status = SentenceStatus.INTERRUPTED
            self._write_sentence(segment, sentence, force=True)
        record = segment_record(segment)
        self.log.write_segment(record)
        self.stats.record_segment(segment)
        counts = record["sentences"]
        log_event(
            logger,
            "segment_finished",
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            status=status.value,
            spoken=counts[SentenceStatus.SPOKEN.value],
            blocked=counts[SentenceStatus.BLOCKED.value],
            dropped=counts[SentenceStatus.DROPPED.value],
        )
        self.bus.publish(Event(EventType.SEGMENT_FINISHED, {"segment_id": segment.segment_id, "status": status.value}))
        self.bus.publish(Event(EventType.SHOW_STATS, self.stats.snapshot_stats()))
        if self.show.current_segment is segment:
            self.show.current_segment = None
            self._current_sentence = None
        if self.show.next_segment is segment:
            self.show.next_segment = None
        for sentence in segment.sentences:
            self._written.discard(sentence.utterance_id)
        settled = self._settled.pop(segment.segment_id, None)
        if settled is not None:
            settled.set()
        if segment is self._closing_segment:
            self._closing_done.set()

    def _close_open_segments(self) -> None:
        """Shutdown: a segment that has spoken counts as done; anything not yet heard is discarded."""
        for segment in sorted(self._open.values(), key=lambda s: s.index):
            spoken = any(s.status is SentenceStatus.SPOKEN and s.played_at is not None for s in segment.sentences)
            if segment.status is SegmentStatus.SPEAKING and spoken:
                self._finalize(segment, SegmentStatus.DONE, shutdown=True)
            else:
                self._finalize(segment, SegmentStatus.DISCARDED, shutdown=True)

    # ---------- records ----------

    def _write_sentence(self, segment: Segment, sentence: ScriptSentence, *, force: bool = False) -> None:
        """One `script_sentences.jsonl` line per sentence; nothing more once its segment is final."""
        if sentence.utterance_id in self._written or (not force and segment.segment_id not in self._open):
            return
        self._written.add(sentence.utterance_id)
        if self._inflight_forms.get(sentence.word_form) == sentence.utterance_id:
            # Final now: spoken lines live on in `history`; a line that never played may be said later.
            del self._inflight_forms[sentence.word_form]
        source = _source(segment)
        self.log.write_script_sentence(script_sentence_record(sentence, source))
        self.stats.record_sentence(sentence, source)

    def _log_milestone(self, segment: Segment, sentence: ScriptSentence, milestone: Milestone, at: float) -> None:
        sentence.marks.setdefault(milestone, at)
        log_event(
            logger,
            milestone.value,
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            utterance_id=sentence.utterance_id,
            t_mono=sentence.marks[milestone],
        )

    def _segment_error(
        self, segment: Segment, step: str, kind: str, message: str, utterance_id: str | None = None
    ) -> None:
        if segment.error_step is None:
            segment.error_step, segment.error_kind, segment.error_message = step, kind, message
        log_event(
            logger,
            "script_error",
            logging.WARNING,
            show_id=self.show.show_id,
            segment_id=segment.segment_id,
            utterance_id=utterance_id,
            step=step,
            type=kind,
            message=message,
        )
        self.log.write_error(
            error_record(step, kind, message, utterance_id, segment_id=segment.segment_id, show_id=self.show.show_id)
        )
        event = show_error_event(step=step, kind=kind, message=message, segment_id=segment.segment_id)
        self.show.recent_errors.append({**event.payload, "at": _iso(self._wall())})
        self.bus.publish(event)

    def _publish_next(self, segment: Segment, status: str) -> None:
        self.bus.publish(
            Event(
                EventType.SEGMENT_NEXT,
                {
                    "segment_id": segment.segment_id,
                    "product_id": segment.product_id,
                    "topic": segment.topic.value,
                    "origin": segment.origin.value,
                    "status": status,
                },
            )
        )

    def _product_name(self, product_id: str | None) -> str | None:
        if product_id is None:
            return None
        return next((p.name for p in self.store.catalog.products if p.id == product_id), None)

    # ---------- snapshot ----------

    def snapshot(self) -> dict[str, Any]:
        """`ShowSnapshot` of `GET /api/show` (contracts/api.md §4). Holds no config or secrets."""
        show = self.show
        return {
            "show_id": show.show_id,
            "state": show.state.value,
            "mode": show.mode.value,
            "started_at": _iso(show.started_at),
            "current": self._current_json(),
            "next": self._next_json(),
            "recent_blocked": [
                {
                    "segment_id": s.segment_id,
                    "text": s.text,
                    "reason": s.guard_reason.value if s.guard_reason else None,
                    "reason_label": s.guard_reason.label if s.guard_reason else None,
                    "at": self._blocked_at.get(s.utterance_id),
                }
                for s in list(show.recent_blocked)[-SNAPSHOT_RECENT:]
            ],
            "recent_errors": [dict(e) for e in list(show.recent_errors)[-SNAPSHOT_RECENT:]],
            "available_topics": {pid: [t.value for t in topics] for pid, topics in self.planner.availability().items()},
            "stats": self.stats.snapshot_stats(),
        }

    def _current_json(self) -> dict[str, Any] | None:
        segment = self.show.current_segment
        if segment is None:
            return None
        sentence = self._current_sentence
        return {
            "segment_id": segment.segment_id,
            "product_id": segment.product_id,
            "product_name": self._product_name(segment.product_id),
            "topic": segment.topic.value,
            "topic_label": segment.topic.label,
            "origin": segment.origin.value,
            "sentence": sentence.text if sentence is not None else None,
            "seq": sentence.seq if sentence is not None else None,
        }

    def _next_json(self) -> dict[str, Any] | None:
        segment = self.show.next_segment
        if segment is not None:
            return {
                "product_id": segment.product_id,
                "product_name": self._product_name(segment.product_id),
                "topic": segment.topic.value,
                "topic_label": segment.topic.label,
                "origin": segment.origin.value,
                "status": segment.status.value,
            }
        slot = self.planner.override
        if slot is None:
            try:
                slot = self.planner.peek_slot()
            except NoSlotAvailable:
                return None
        return {
            "product_id": slot.product_id,
            "product_name": self._product_name(slot.product_id),
            "topic": slot.topic.value,
            "topic_label": slot.topic.label,
            "origin": slot.origin.value,
            "status": "planned",
        }
