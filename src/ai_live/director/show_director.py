"""Basic ShowDirector: answers one comment at a time (research R14; FR-006, FR-013, FR-018, FR-019, FR-020).

Each turn runs two tasks joined by a sentence queue of at most 2: a producer (LLM -> guard -> TTS) and a player
(renderer). The next sentence is produced while the previous one plays, so there is no silence between sentences.

Latency (US3): the four milestones are logged as JSON with the `utterance_id` the moment they are known, the finished
turn goes to the `LatencyTracker` and the session files, and a `latency` summary follows every `turn_finished`.

Session control (US4, research R14): pause stops new turns but lets the current one finish; skip cancels the current
turn's tasks and tells the renderer to stop. Every step has a timeout, and `inject_fault` (dev only, `FaultInjector` in
`director/faults.py`) makes the next turns fail at a chosen step, so one failure ends only that turn and the live
goes on (FR-020).

Scripted show (004 US1): `start_show()` builds a `ScriptRunner` that speaks the product script while no comment is
waiting. Both paths share `_floor`, held by a comment turn for its whole answer and by the script player for one
sentence, so a reply only ever lands between two scripted sentences (research R8). Both share the guard and the
`FaultInjector`.

Comments during a show (004 US6, FR-028 to FR-030): `run()` still takes a comment the moment it arrives, so the reply's
LLM and TTS run while the script finishes its sentence; only the reply's player waits for `_floor`. The script player
asks `_CommentGate` after every sentence and waits while a turn runs or a comment waits, keeping its voiced audio.
A reply is logged with the show's `show_id` and its sentences join the show's `SpokenHistory` (`source="reply"`), but
it is not a segment and does not move the rotation. Once the show is closing or ended no comment is answered: each one
taken from the queue is dropped as `show_ended`, even while paused, so none waits for a resume that cannot answer it.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ai_live.brain.guard import OutputGuard, refusal_sentence, word_form
from ai_live.brain.prompt import addressee
from ai_live.brain.sanitize import clean_spoken
from ai_live.core.config import Settings
from ai_live.core.events import Event, EventBus, EventType, comment_dropped_event
from ai_live.core.logging import log_event
from ai_live.core.models import (
    CommentStatus,
    DropReason,
    ErrorStep,
    Milestone,
    QueuedComment,
    RenderTurnStats,
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
    CommentQueue,
    ProductStore,
    RendererUnavailable,
    ReplyEngine,
    TTSEngine,
)
from ai_live.director.faults import ENTRY_FAULT_MODES, FAULT_MODES, FAULT_STEPS, FaultInjector, InjectedFault
from ai_live.director.latency import LatencyTracker
from ai_live.director.render_report import collect_render_stats_when_settled, report_render_outcome
from ai_live.director.script_runner import ScriptRunner, next_tts_chunk, tts_error_text
from ai_live.director.segment_planner import NoSlotAvailable, PlannedSlot, SegmentPlanner, TopicUnavailable
from ai_live.director.session_log import SessionLog, comment_record, error_record, utterance_record
from ai_live.director.show_stats import ShowStats
from ai_live.products.models import ProductCatalog
from ai_live.security.redact import redact_text

if TYPE_CHECKING:
    from ai_live.brain.chain_engine import TurnRecord

logger = logging.getLogger("ai_live.director")

SENTENCE_QUEUE_MAX = 2
RECENT_MAX = 50
INTERLEAVE_POLL_S = 0.05
# A show in one of these states owns the host: a second start reuses it and `debug/speak` is refused.
_ACTIVE_SHOW_STATES = (ShowState.RUNNING, ShowState.PAUSED, ShowState.CLOSING)
# A show in one of these states answers no comment: each one taken from the queue is dropped `show_ended` (FR-030).
_CLOSED_SHOW_STATES = (ShowState.CLOSING, ShowState.ENDED)

# Re-exported: `app/routes.py` and older imports read the fault names from here.
__all__ = [
    "ENTRY_FAULT_MODES",
    "FAULT_MODES",
    "FAULT_STEPS",
    "DirectorBusy",
    "HostUnavailable",
    "InjectedFault",
    "NoContent",
    "ShowDirector",
    "ShowNotRunning",
    "TopicUnavailable",
]

_END = object()


class DirectorBusy(RuntimeError):
    """A turn or a show is speaking; `speak_text` does not cut in."""


class HostUnavailable(RuntimeError):
    """`start_show`: no host page is connected, or it is connected but has not pressed Bắt đầu (`ready`)."""


class NoContent(RuntimeError):
    """`start_show`: no valid product content is loaded."""


class ShowNotRunning(RuntimeError):
    """`choose_next`: no show is running or paused (idle, closing or ended)."""


class _StepError(Exception):
    """A failed pipeline step. `kind` is the `type` written to `errors.jsonl` (e.g. `provider_blocked`, `timeout`)."""

    def __init__(self, step: ErrorStep, message: str, kind: str) -> None:
        super().__init__(message)
        self.step = step
        self.kind = kind


class ShowDirector:
    def __init__(
        self,
        *,
        queue: CommentQueue,
        store: ProductStore,
        engine: ReplyEngine,
        tts: TTSEngine,
        renderer: AvatarRenderer,
        bus: EventBus | None = None,
        llm_timeout_s: float = 8.0,
        tts_timeout_s: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        latency: LatencyTracker | None = None,
        session_log: SessionLog | None = None,
        llm_model: str | None = None,
        faults: FaultInjector | None = None,
        guard: OutputGuard | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.queue = queue
        self.store = store
        self.engine = engine
        self.tts = tts
        self.renderer = renderer
        self.bus = bus or EventBus()
        self.llm_timeout_s = llm_timeout_s
        self.tts_timeout_s = tts_timeout_s
        self._clock = clock
        self.latency = latency if latency is not None else LatencyTracker()
        self.session_log = session_log
        self.llm_model = llm_model
        # The app passes the guard with the platform phrases loaded at startup (analyze A4); the show uses it too.
        self._guard = guard if guard is not None else OutputGuard()
        self.settings = settings
        # One turn speaks at a time, including `speak_text` from the debug page.
        self._lock = asyncio.Lock()
        # Who holds the host right now: a comment turn (whole answer) or the script player (one sentence).
        self._floor = asyncio.Lock()
        self.show: ShowSession | None = None
        self._runner: ScriptRunner | None = None
        self._show_task: asyncio.Task[None] | None = None
        self.current: Utterance | None = None
        self.recent: deque[Utterance] = deque(maxlen=RECENT_MAX)
        # `_paused` is the operator's session state. `_running` / `_intake_held` say whether `run()` takes comments;
        # two events because `run()` waits for either (to take one, or to stop waiting). Kept apart from `_paused`:
        # a closing or ended show takes comments even while paused, to drop them (`_sync_intake`).
        self._running = asyncio.Event()
        self._running.set()
        self._intake_held = asyncio.Event()
        self._paused = asyncio.Event()
        # A comment is out of the queue but its turn has not taken `_lock` yet; the script gate counts it as waiting.
        self._taking = False
        self._take_task: asyncio.Future[QueuedComment] | None = None  # `run()` waiting in `queue.get()`
        self._turn_tasks: tuple[asyncio.Task[None], ...] = ()
        self._skipped_id: str | None = None
        # Shared with the scripted show so one queued fault hits whichever path reaches the step first (004 FR-024).
        self.faults = faults if faults is not None else FaultInjector()
        # comment.id -> utterance_id of the reply being produced: a chain's turn record only knows the comment.
        self._reply_utterances: dict[str, str] = {}
        # label -> model of the chain entries, in chain order, for the summary's `llm_chain` (008 data-model §7);
        # None when the engine is not the chain, which makes that section null.
        self._llm_entries: dict[str, str] | None = None
        add_turn_observer = getattr(engine, "add_turn_observer", None)
        if add_turn_observer is not None:
            self._llm_entries = {entry.label: entry.model for entry in getattr(engine, "entries", ())}
            add_turn_observer(self._on_llm_turn)

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    @property
    def show_active(self) -> bool:
        return self.show is not None and self.show.state in _ACTIVE_SHOW_STATES

    @property
    def history(self) -> SpokenHistory | None:
        """What the current or last show said, replies included (FR-030); None before the first start."""
        return self._runner.history if self._runner is not None else None

    @property
    def _show_closed(self) -> bool:
        return self.show is not None and self.show.state in _CLOSED_SHOW_STATES

    @property
    def state(self) -> str:
        return "paused" if self._paused.is_set() else "running"

    async def run(self) -> None:
        """Main loop: wait for a comment, answer it, repeat. While paused it takes nothing; the queue keeps filling.

        Before a show and while one runs, each comment is answered as in 001 (during a show the reply lands between
        two scripted sentences). Once the show is closing or ended, each comment taken is dropped `show_ended` (FR-030).
        """
        while True:
            await self._running.wait()
            queued = await self._next_comment()
            if queued is None:
                continue
            try:
                if self._show_closed:
                    self._drop_show_ended(queued)
                    continue
                await self.run_turn(queued)
            except Exception:
                # An unexpected error in one turn must not kill the whole live; log it and take the next comment.
                logger.exception("turn_crashed")
            finally:
                self._taking = False

    async def _take(self) -> QueuedComment:
        queued = await self.queue.get()
        # Set with no await after the pop, so the script gate never sees an empty queue and no turn in between.
        self._taking = True
        return queued

    async def _next_comment(self) -> QueuedComment | None:
        """Wait for a comment, but give up as soon as comments are held by a pause (None)."""
        get = self._take_task = asyncio.ensure_future(self._take())
        held = asyncio.ensure_future(self._intake_held.wait())
        try:
            await asyncio.wait({get, held}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            self._take_task = None
            held.cancel()
            if not get.done():
                get.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await get
        if get.cancelled():
            return None
        queued = get.result()
        if self._intake_held.is_set():
            # Paused in the same instant the comment arrived: put it back for after resume. `received_at` is kept,
            # so it still goes stale on time; only its order among equal priorities changes.
            await self.queue.put(queued.comment, queued.priority)
            self._taking = False
            return None
        return queued

    def _sync_intake(self) -> None:
        """Take comments while running, and also while paused once the show is closing or ended (to drop them)."""
        if self._paused.is_set() and not self._show_closed:
            self._running.clear()
            self._intake_held.set()
            take = self._take_task
            if take is not None and not take.done():
                # Cancelled now, not when `run()` next wakes: a comment that arrives before then must stay queued
                # (and may go stale), not be popped and answered as if the pause came after it.
                take.cancel()
        else:
            self._intake_held.clear()
            self._running.set()

    def _drop_show_ended(self, queued: QueuedComment) -> None:
        """A comment taken while the show is closing or ended is not answered (FR-030, contracts/api.md)."""
        show_id = self.show.show_id if self.show is not None else None
        queued.status = CommentStatus.DROPPED
        queued.drop_reason = DropReason.SHOW_ENDED
        log_event(
            logger, "comment_dropped", comment_id=queued.comment.id, reason=DropReason.SHOW_ENDED.value, show_id=show_id
        )
        # `SessionLog.record_drops` writes the `comments.jsonl` line from this event, like every other drop.
        self.bus.publish(comment_dropped_event(queued.comment, DropReason.SHOW_ENDED, show_id=show_id))

    # ---------- Session control (US4) ----------

    @property
    def show_state(self) -> str | None:
        """State of the current or last show; None before the first start."""
        return self.show.state.value if self.show is not None else None

    def pause(self, t_mono: float | None = None) -> str:
        """No new turn starts; the current one finishes. A running show stops after its current sentence (FR-015).

        Idempotent: a repeat publishes and logs nothing.
        """
        changed = False
        if not self._paused.is_set():
            self._paused.set()
            self._sync_intake()
            self.bus.publish(Event(EventType.SESSION_STATE, {"state": self.state}))
            changed = True
        if self._runner is not None and self._runner.pause():
            self._publish_show_state(reason="operator")
            changed = True
        if changed:
            self._log_applied("pause", t_mono, **self._show_fields())
        return self.state

    def resume(self, t_mono: float | None = None) -> str:
        """Comments are taken again; a paused show voices its next sentence again (research R7)."""
        changed = False
        if self._paused.is_set():
            self._paused.clear()
            self._sync_intake()
            self.bus.publish(Event(EventType.SESSION_STATE, {"state": self.state}))
            changed = True
        if self._runner is not None and self._runner.resume():
            self._publish_show_state(reason="operator")
            changed = True
        if changed:
            self._log_applied("resume", t_mono, **self._show_fields())
        return self.state

    def end_show(self, t_mono: float | None = None) -> tuple[str | None, str]:
        """Start the closing of a running or paused show (FR-017): `(show_id, show_state)`.

        Idempotent: with no show it returns `(None, "idle")`; a closing or ended show is left as it is.
        """
        show, runner = self.show, self._runner
        if show is None or runner is None:
            return None, ShowState.IDLE.value
        if runner.close():
            # A paused show that closes still takes its queued comments, only to drop them `show_ended`.
            self._sync_intake()
            self._publish_show_state(reason="operator")
            self._log_applied("show_end", t_mono, show_id=show.show_id)
        return show.show_id, show.state.value

    def choose_next(self, product_id: str | None, topic: Topic | None, t_mono: float | None = None) -> PlannedSlot:
        """Pick the next segment for the running or paused show (FR-018, `POST /api/show/next`).

        The prepared segment N+1 is discarded and rebuilt from the chosen slot; what is speaking now
        finishes first. Raises `ShowNotRunning` outside running/paused (a closing show only says goodbye)
        and `TopicUnavailable` when the product/topic has no data.
        """
        show, runner = self.show, self._runner
        if show is None or runner is None or show.state not in (ShowState.RUNNING, ShowState.PAUSED):
            raise ShowNotRunning("no running show")
        slot = runner.choose(product_id, topic)
        self._log_applied("show_next", t_mono, show_id=show.show_id, product_id=slot.product_id, topic=slot.topic.value)
        return slot

    async def skip(self, t_mono: float | None = None) -> str | None:
        """Cut what is speaking short; returns its `utterance_id`, or None when nothing is speaking."""
        return (await self.skip_current(t_mono))[0]

    async def skip_current(self, t_mono: float | None = None) -> tuple[str | None, str | None]:
        """Skip the comment turn speaking now, else the scripted segment: `(utterance_id, segment_id)` (FR-016).

        `segment_id` is None for a comment turn. While the show is closing, a skip ends it at once.
        """
        if self.current is not None and self._turn_tasks:
            return await self._skip_turn(t_mono), None
        runner = self._runner
        if runner is None or not self.show_active:
            return None, None
        utterance_id, segment_id = await runner.skip()
        if utterance_id is not None or segment_id is not None:
            self._log_applied("skip", t_mono, utterance_id=utterance_id, segment_id=segment_id, **self._show_fields())
        return utterance_id, segment_id

    async def _skip_turn(self, t_mono: float | None) -> str | None:
        utt = self.current
        if utt is None or not self._turn_tasks:
            return None
        if self._skipped_id == utt.utterance_id:
            return utt.utterance_id
        self._skipped_id = utt.utterance_id
        # Cancel before interrupting: `interrupt()` releases the renderer's ack waits, and a still-running player
        # would then send the next sentence. The renderer still knows what is speaking, because the cancellation
        # has not been delivered yet (no await in between).
        for task in self._turn_tasks:
            task.cancel()
        await self.renderer.interrupt()
        self._log_applied("skip", t_mono, utterance_id=utt.utterance_id)
        return utt.utterance_id

    # ---------- Scripted show (004 US1) ----------

    async def start_show(self, t_mono: float | None = None) -> tuple[ShowSession, bool]:
        """Start the show, or return the one already running: `(show, already_running)` (contracts/api.md §2).

        Raises `HostUnavailable` when the host page is not ready and `NoContent` when no product is loaded.
        """
        requested = self._clock() if t_mono is None else t_mono
        if self.show is not None and self.show_active:
            return self.show, True
        if not getattr(self.renderer, "host_ready", False):
            raise HostUnavailable("host not ready")
        catalog = self.store.catalog
        if catalog is None or not catalog.products:
            raise NoContent("no products")
        settings = self.settings if self.settings is not None else Settings(_env_file=None)
        try:
            planner = SegmentPlanner(catalog, settings.script_primary_share)
            planner.peek_slot()
        except (NoSlotAvailable, StopIteration) as exc:
            raise NoContent("no slot") from exc
        if self.session_log is None:
            raise RuntimeError("start_show needs a session log")
        show = ShowSession(
            show_id=uuid.uuid4().hex,
            session_id=self.session_log.session_id,
            start_requested_at=requested,
            catalog_version=catalog.version,
            state=ShowState.RUNNING,
            started_at=datetime.now(UTC),
        )
        runner = ScriptRunner(
            show=show,
            planner=planner,
            engine=self.engine,
            guard=self._guard,
            tts=self.tts,
            renderer=self.renderer,
            store=self.store,
            floor=self._floor,
            interleave=_CommentGate(self),
            faults=self.faults,
            stats=ShowStats(show.show_id, show.session_id, catalog, llm_entries=self._llm_entries),
            log=self.session_log,
            bus=self.bus,
            settings=settings,
            clock=self._clock,
        )
        self.show, self._runner = show, runner
        self._sync_intake()
        self._show_task = asyncio.create_task(self._run_show(runner), name="script_runner")
        self._publish_show_state()
        self._log_applied("show_start", t_mono, show_id=show.show_id)
        return show, False

    def show_snapshot(self) -> dict[str, Any] | None:
        """`ShowSnapshot` of the current or last show; None before the first start."""
        return self._runner.snapshot() if self._runner is not None else None

    def on_catalog_replaced(self, catalog: ProductCatalog) -> None:
        """New content was installed: the running show follows it (FR-022)."""
        if self._runner is not None and self.show_active:
            self._runner.on_catalog_replaced(catalog)

    async def close(self) -> None:
        """App shutdown: stop the show; the runner writes its summary before this returns."""
        task, self._show_task = self._show_task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _run_show(self, runner: ScriptRunner) -> None:
        try:
            await runner.run()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("show_crashed")
        finally:
            show = runner.show
            show.state = ShowState.ENDED
            show.ended_at = datetime.now(UTC)
            self._sync_intake()
            self._publish_show_state(reason=runner.ended_by)

    def _publish_show_state(self, reason: str | None = None) -> None:
        show = self.show
        if show is None:
            return
        fields: dict[str, object] = {"show_id": show.show_id, "state": show.state.value, "mode": show.mode.value}
        self.bus.publish(Event(EventType.SHOW_STATE, dict(fields)))
        if reason is not None:
            fields["reason"] = reason
        log_event(logger, "show_state", **fields)

    def inject_fault(self, step: str, mode: str, count: int = 1, entry: str | None = None) -> None:
        """Make the next `count` turns that reach `step` fail there (dev only, `POST /api/debug/fault`).

        With `entry` (008 FR-016), the next `count` tries of that chain entry fail instead, whichever turn makes them.
        """
        self.faults.inject(step, mode, count, entry=entry)

    def _show_fields(self) -> dict[str, object]:
        """`show_id` for control logs while a show exists, so they join with the show's own events."""
        return {"show_id": self.show.show_id} if self.show is not None else {}

    def _log_applied(self, command: str, t_mono: float | None, **fields: object) -> None:
        latency_ms = 0.0 if t_mono is None else max(0.0, (self._clock() - t_mono) * 1000)
        log_event(logger, "control_applied", command=command, latency_ms=round(latency_ms, 1), **fields)

    def _on_llm_turn(self, record: TurnRecord) -> None:
        """Engine turn observer (008 FR-005, FR-018).

        Every turn, segment or comment reply, feeds the current show's `llm_chain` counts. Comment replies also get one
        `llm_turn` log line tied to the utterance the viewer hears: this is called in the reply stream's `finally`, i.e.
        while `_turn` still maps the comment to its utterance. Scripted segments are logged by `ScriptRunner`, which
        owns their `segment_id`. A record that lands after the show ended goes to that show's stats, whose summary is
        already written, so it changes nothing.
        """
        if self._runner is not None:
            self._runner.stats.record_llm_turn(record)
        if record.kind != "reply":
            return
        log_event(
            logger,
            "llm_turn",
            utterance_id=self._reply_utterances.get(record.turn_key),
            comment_id=record.turn_key,
            label=record.label,
            model=record.model,
            provider=record.provider,
            attempts=len(record.attempts),
            outcome=record.outcome,
        )

    async def run_turn(self, queued: QueuedComment) -> Utterance:
        async with self._lock:
            return await self._turn(queued)

    async def speak_text(self, text: str) -> str:
        """Speak `text` through TTS + renderer only, skipping the LLM and the queue (Article IV, `/api/debug/speak`).

        Renderer errors (`RendererUnavailable`, `TimeoutError`) propagate so the API can return the right status.
        """
        if self._lock.locked() or self.show_active:
            raise DirectorBusy("Đang có lượt nói")
        async with self._lock:
            utterance_id = uuid.uuid4().hex
            chunks = await self._collect_tts(text)
            await self.renderer.speak(utterance_id, text, _iterate(chunks), self.tts.sample_rate)
            return utterance_id

    async def speak_audio(self, pcm: bytes, sample_rate: int, text: str) -> str:
        """Play ready-made PCM16 mono through the renderer alone, skipping LLM and TTS (005 FR-011, debug speak-audio).

        Same busy rule and error propagation as `speak_text`; `text` is the subtitle (the file name).
        """
        if self._lock.locked() or self.show_active:
            raise DirectorBusy("Đang có lượt nói")
        async with self._lock:
            utterance_id = f"dbg-audio-{uuid.uuid4().hex[:8]}"
            # 100 ms chunks, like a TTS stream, so the renderer starts sending before the whole file is queued.
            step = max(2, sample_rate // 10 * 2)
            chunks = [pcm[i : i + step] for i in range(0, len(pcm), step)]
            await self.renderer.speak(utterance_id, text, _iterate(chunks), sample_rate)
            return utterance_id

    # ---------- One turn ----------

    async def _turn(self, queued: QueuedComment) -> Utterance:
        comment = queued.comment
        # Snapshot the catalog at the start: replacing content mid-turn must not mix two versions in one answer.
        catalog = self.store.catalog
        utt = Utterance(utterance_id=uuid.uuid4().hex, comment_id=comment.id, catalog_version=catalog.version)
        if self.show is not None and self.show_active:
            utt.show_id = self.show.show_id  # a reply inside a show joins the show's files (contracts/events.md)
        utt.mark(Milestone.COMMENT_RECEIVED, comment.received_at)
        started = self._clock()
        utt.mark(Milestone.TURN_STARTED, started)
        self.current = utt
        queued.status = CommentStatus.ANSWERING
        log_event(
            logger,
            "turn_started",
            utterance_id=utt.utterance_id,
            comment_id=comment.id,
            priority=queued.priority.name,
            queue_wait_s=round(started - comment.received_at, 3),
        )
        log_event(
            logger, "comment_received", comment_id=comment.id, utterance_id=utt.utterance_id, t_mono=comment.received_at
        )
        self.bus.publish(
            Event(
                EventType.TURN_STARTED,
                {
                    "utterance_id": utt.utterance_id,
                    "comment_id": comment.id,
                    "author": comment.author,
                    "text": comment.text,
                },
            )
        )

        sentences: asyncio.Queue[object] = asyncio.Queue(maxsize=SENTENCE_QUEUE_MAX)
        self._reply_utterances[comment.id] = utt.utterance_id
        produce = asyncio.create_task(self._produce(utt, queued, catalog, sentences))
        play = asyncio.create_task(self._play(utt, sentences))
        self._turn_tasks = (produce, play)
        try:
            done, _ = await asyncio.wait({produce, play}, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                task.result()
            await play
            utt.outcome = TurnOutcome.COMPLETED
            queued.status = CommentStatus.ANSWERED
        except asyncio.CancelledError:
            # Only a skip of this very turn is an outcome; cancelling `run()` itself (shutdown) must propagate.
            current = asyncio.current_task()
            if self._skipped_id != utt.utterance_id or (current is not None and current.cancelling()):
                raise
            utt.outcome = TurnOutcome.SKIPPED
            queued.status = CommentStatus.SKIPPED
            log_event(logger, "turn_skipped", utterance_id=utt.utterance_id)
        except _StepError as exc:
            utt.outcome = TurnOutcome.ERROR
            utt.error_step = exc.step
            utt.error_kind = exc.kind
            utt.error_message = str(exc)
            queued.status = CommentStatus.ERROR
            log_event(
                logger,
                "turn_error",
                logging.WARNING,
                utterance_id=utt.utterance_id,
                step=exc.step.value,
                type=exc.kind,
                message=str(exc),
            )
            if self.session_log is not None:
                self.session_log.write_error(error_record(exc.step.value, exc.kind, str(exc), utt.utterance_id))
        finally:
            for task in (produce, play):
                if not task.done():
                    task.cancel()
            for task in (produce, play):
                with contextlib.suppress(asyncio.CancelledError, _StepError):
                    await task
            # The producer closed the reply stream, so the engine's turn record has already been sent.
            self._reply_utterances.pop(comment.id, None)
            self._turn_tasks = ()
            self.current = None
            self.recent.append(utt)
            self._finish(utt, queued)
        return utt

    async def _produce(
        self, utt: Utterance, queued: QueuedComment, catalog: ProductCatalog, out: asyncio.Queue[object]
    ) -> None:
        who = addressee(queued.comment.author)
        replies = self.faults.stream("llm", lambda: self.engine.reply(queued.comment, catalog))
        budget = _LlmBudget(self.llm_timeout_s)
        try:
            while True:
                sentence = await self._next_sentence(replies, budget)
                if sentence is None:
                    break
                self._mark(utt, Milestone.LLM_FIRST_SENTENCE, self._clock())
                # Same cleaning as the script (ADR-031): markdown and emoji are never read aloud nor guarded raw.
                sentence = clean_spoken(sentence)
                if not sentence:
                    continue
                try:
                    result = self._guard.check(sentence, catalog)
                except Exception as exc:
                    raise _StepError(ErrorStep.GUARD, f"Guard lỗi: {exc}", type(exc).__name__) from exc
                if result.ok:
                    await self._enqueue(utt, sentence, out)
                    continue
                # Stop producing once blocked: later sentences may build on the blocked one (FR-010, FR-011).
                utt.guard_reason = result.reason
                log_event(
                    logger,
                    "guard_blocked",
                    utterance_id=utt.utterance_id,
                    reason=result.reason.value if result.reason else None,
                    sentence_hash=hashlib.sha256(sentence.encode()).hexdigest()[:12],
                )
                self.bus.publish(
                    Event(
                        EventType.GUARD_BLOCKED,
                        {"utterance_id": utt.utterance_id, "reason": result.reason.value if result.reason else None},
                    )
                )
                await self._enqueue(utt, refusal_sentence(who), out)
                break
        finally:
            aclose = getattr(replies, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()
        await out.put(_END)

    async def _next_sentence(self, replies: AsyncIterator[str], budget: _LlmBudget) -> str | None:
        # LLM_TIMEOUT_S covers the first sentence and the whole stream (research R14), but only time spent waiting on
        # the LLM: time blocked on the play queue is playback, not an LLM fault.
        first = budget.spent == 0.0
        started = self._clock()
        try:
            return await asyncio.wait_for(anext(replies), budget.remaining)
        except StopAsyncIteration:
            return None
        except TimeoutError as exc:
            what = "không trả câu đầu" if first else "chưa trả hết câu trả lời"
            raise _StepError(ErrorStep.LLM, f"LLM quá {self.llm_timeout_s} s {what}", "timeout") from exc
        except Exception as exc:
            kind = str(getattr(exc, "kind", type(exc).__name__))
            raise _StepError(ErrorStep.LLM, f"{kind}: {exc}", kind) from exc
        finally:
            budget.spent += self._clock() - started

    async def _enqueue(self, utt: Utterance, sentence: str, out: asyncio.Queue[object]) -> None:
        """Run TTS for a sentence; hand it to the player once the first chunk exists, so the host never waits."""
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        stream = self.faults.stream("tts", lambda: self.tts.synthesize(sentence))
        try:
            first = await next_tts_chunk(stream, self.tts_timeout_s)
            self._mark(utt, Milestone.TTS_FIRST_CHUNK, self._clock())
            if first is not None:
                chunks.put_nowait(first)
            # Waiting for a free slot in the play queue is playback, not TTS: no timeout here (ADR-049).
            await out.put((sentence, chunks))
            while (chunk := await next_tts_chunk(stream, self.tts_timeout_s)) is not None:
                chunks.put_nowait(chunk)
        except TimeoutError as exc:
            raise _StepError(ErrorStep.TTS, f"TTS quá {self.tts_timeout_s} s", "timeout") from exc
        except Exception as exc:
            kind = str(getattr(exc, "kind", type(exc).__name__))
            raise _StepError(ErrorStep.TTS, tts_error_text(exc), kind) from exc
        finally:
            chunks.put_nowait(None)
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()

    async def _play(self, utt: Utterance, sentences: asyncio.Queue[object]) -> None:
        # The whole answer holds the floor, so the script never speaks in the middle of a reply (research R8).
        async with self._floor:
            await self._play_all(utt, sentences)

    async def _play_all(self, utt: Utterance, sentences: asyncio.Queue[object]) -> None:
        seq = 0
        while True:
            item = await sentences.get()
            if item is _END:
                if seq > 0:
                    report_render_outcome(self.renderer, utt.utterance_id, True)
                return
            text, chunks = item  # type: ignore[misc]
            utt.sentences.append(text)
            self.bus.publish(Event(EventType.SENTENCE, {"utterance_id": utt.utterance_id, "seq": seq, "text": text}))
            try:
                await self.faults.check_render(getattr(self.renderer, "ack_timeout_s", 3.0))
                await self.renderer.speak(utt.utterance_id, text, _drain(chunks), self.tts.sample_rate)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                kind = _render_error_kind(exc)
                report_render_outcome(self.renderer, utt.utterance_id, False, kind)
                raise _StepError(ErrorStep.RENDER, f"Renderer lỗi: {type(exc).__name__}: {exc}", kind) from exc
            if seq == 0:
                self._mark_first_frame(utt)
            seq += 1

    def _mark(self, utt: Utterance, milestone: Milestone, at: float) -> None:
        """Record a milestone once and log it right away, so a stuck turn still shows how far it got."""
        if milestone in utt.marks:
            return
        utt.mark(milestone, at)
        log_event(logger, milestone.value, utterance_id=utt.utterance_id, t_mono=at)

    def _attach_render(self, utterance_id: str, render: RenderTurnStats | None) -> None:
        # The turn's figures came after `turn_finished` (LIVETALKING_LEAD_S): refresh the latency panel with them.
        if self.latency.attach_render(utterance_id, render):
            self.bus.publish(Event(EventType.LATENCY, self.latency.summary().to_json()))

    def _mark_first_frame(self, utt: Utterance) -> None:
        # Only the AvatarRenderer protocol is used, so any renderer that reports first playback works unchanged.
        first = self.renderer.first_playback_at(utt.utterance_id)
        if first is not None:
            self._mark(utt, Milestone.AVATAR_FIRST_FRAME, first)

    def _finish(self, utt: Utterance, queued: QueuedComment) -> None:
        # The first sentence may have started playing and then failed (e.g. host gone before `sentence_played`).
        self._mark_first_frame(utt)
        total_s = None
        if Milestone.AVATAR_FIRST_FRAME in utt.marks:
            total_s = round(utt.marks[Milestone.AVATAR_FIRST_FRAME] - utt.marks[Milestone.COMMENT_RECEIVED], 3)
        payload = {
            "utterance_id": utt.utterance_id,
            "outcome": utt.outcome.value,
            "error_step": utt.error_step.value if utt.error_step else None,
            "total_s": total_s,
        }
        if utt.outcome is TurnOutcome.ERROR:
            # Added only on errors (003 contracts/events.md §2), so other turns keep the 001 payload.
            payload["error_kind"] = utt.error_kind
            # Provider errors can echo a key, as for `show_error`.
            payload["error_message"] = redact_text(utt.error_message) if utt.error_message else None
        log_event(logger, "turn_finished", **payload)
        uid = utt.utterance_id
        render = collect_render_stats_when_settled(self.renderer, uid, on_late=lambda s: self._attach_render(uid, s))
        self.latency.record(utt, render=render)
        if self.session_log is not None:
            self.session_log.write_utterance(utterance_record(utt, self.llm_model))
            if queued.status in _FINAL_COMMENT_STATUSES:
                self.session_log.write_comment(
                    comment_record(queued, queued.status, utt.utterance_id, show_id=utt.show_id)
                )
        self._add_to_show(utt, queued, total_s)
        self.bus.publish(Event(EventType.TURN_FINISHED, payload))
        self.bus.publish(Event(EventType.LATENCY, self.latency.summary().to_json()))

    def _add_to_show(self, utt: Utterance, queued: QueuedComment, total_s: float | None) -> None:
        """A reply inside a show: its sentences join the show's history (FR-030) and its latency the summary (SC-011).

        Not a segment: the planner and the segment counts never see it (FR-029). The lines carry the product of the
        segment the reply landed in, so that product's next segment gets them in `recent_lines` and avoids repeating.
        """
        runner = self._runner
        if runner is None or utt.show_id is None or runner.show.show_id != utt.show_id:
            return
        current = runner.show.current_segment
        product_id = current.product_id if current is not None else None
        for text in utt.sentences:
            runner.history.add(SpokenLine(text, word_form(text), product_id, "reply", queued.comment.text))
        if utt.outcome is TurnOutcome.COMPLETED and total_s is not None:
            runner.stats.record_reply_latency(total_s)

    async def _collect_tts(self, text: str) -> list[bytes]:
        # Same per-chunk timeout as a turn (ADR-049); `TimeoutError` propagates to the debug API.
        stream = self.tts.synthesize(text)
        chunks: list[bytes] = []
        try:
            while (chunk := await next_tts_chunk(stream, self.tts_timeout_s)) is not None:
                chunks.append(chunk)
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()
        return chunks


_FINAL_COMMENT_STATUSES = (CommentStatus.ANSWERED, CommentStatus.SKIPPED, CommentStatus.ERROR)


class _CommentGate:
    """`InterleaveGate` for the script player: a comment turn is speaking, or one is waiting and will be taken."""

    def __init__(self, director: ShowDirector) -> None:
        self._director = director

    def pending(self) -> bool:
        director = self._director
        if director.busy or director._taking:
            return True
        # While comments are paused nothing takes the queue, so a waiting comment must not hold the script.
        return director.state == "running" and director.queue.size() > 0

    async def wait_clear(self) -> None:
        # Polled: the queue protocol has no "became empty" event.
        while self.pending():  # noqa: ASYNC110
            await asyncio.sleep(INTERLEAVE_POLL_S)


class _LlmBudget:
    """LLM wait time left in one turn."""

    def __init__(self, limit_s: float) -> None:
        self.limit_s = limit_s
        self.spent = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.limit_s - self.spent)


def _render_error_kind(exc: Exception) -> str:
    if isinstance(exc, InjectedFault):
        return exc.kind
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, RendererUnavailable):
        return "host_unavailable"
    # `RendererError` names its own failure (`vram_oom`, `lipsync_unavailable`, ...), as in `ScriptRunner._error_kind`.
    return str(getattr(exc, "kind", type(exc).__name__))


async def _drain(chunks: asyncio.Queue[bytes | None]) -> AsyncIterator[bytes]:
    while (chunk := await chunks.get()) is not None:
        yield chunk


async def _iterate(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk
