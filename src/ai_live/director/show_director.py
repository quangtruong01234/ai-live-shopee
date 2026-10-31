"""Basic ShowDirector: answers one comment at a time (research R14; FR-006, FR-013, FR-018, FR-019, FR-020).

Each turn runs two tasks joined by a sentence queue of at most 2: a producer (LLM -> guard -> TTS) and a player
(renderer). The next sentence is produced while the previous one plays, so there is no silence between sentences.

Latency (US3): the four milestones are logged as JSON with the `utterance_id` the moment they are known, the finished
turn goes to the `LatencyTracker` and the session files, and a `latency` summary follows every `turn_finished`.

Session control (US4, research R14): pause stops new turns but lets the current one finish; skip cancels the current
turn's tasks and tells the renderer to stop. Every step has a timeout, and `inject_fault` (dev only) makes the next
turns fail at a chosen step, so one failure ends only that turn and the live goes on (FR-020).
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

from ai_live.brain.guard import OutputGuard, refusal_sentence
from ai_live.brain.prompt import addressee
from ai_live.core.events import Event, EventBus, EventType
from ai_live.core.logging import log_event
from ai_live.core.models import (
    CommentStatus,
    ErrorStep,
    Milestone,
    QueuedComment,
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
from ai_live.director.latency import LatencyTracker
from ai_live.director.session_log import SessionLog, comment_record, error_record, utterance_record
from ai_live.products.models import ProductCatalog

logger = logging.getLogger("ai_live.director")

SENTENCE_QUEUE_MAX = 2
RECENT_MAX = 50
FAULT_STEPS = ("llm", "tts", "render")
FAULT_MODES = ("error", "timeout")

_END = object()


class DirectorBusy(RuntimeError):
    """A turn is speaking; `speak_text` does not cut in."""


class InjectedFault(Exception):
    """A failure made on purpose through `inject_fault`; `kind` becomes the `type` in `errors.jsonl`."""

    kind = "fault_injected"


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
        self._guard = OutputGuard()
        # One turn speaks at a time, including `speak_text` from the debug page.
        self._lock = asyncio.Lock()
        self.current: Utterance | None = None
        self.recent: deque[Utterance] = deque(maxlen=RECENT_MAX)
        # Two events because `run()` waits for either state: running (to take a comment) or paused (to stop waiting).
        self._running = asyncio.Event()
        self._running.set()
        self._paused = asyncio.Event()
        self._turn_tasks: tuple[asyncio.Task[None], ...] = ()
        self._skipped_id: str | None = None
        self._faults: dict[str, deque[str]] = {step: deque() for step in FAULT_STEPS}

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    @property
    def state(self) -> str:
        return "paused" if self._paused.is_set() else "running"

    async def run(self) -> None:
        """Main loop: wait for a comment, answer it, repeat. While paused it takes nothing; the queue keeps filling.

        With no comment it does nothing (no idle script yet; that is feature 004).
        """
        while True:
            await self._running.wait()
            queued = await self._next_comment()
            if queued is None:
                continue
            try:
                await self.run_turn(queued)
            except Exception:
                # An unexpected error in one turn must not kill the whole live; log it and take the next comment.
                logger.exception("turn_crashed")

    async def _next_comment(self) -> QueuedComment | None:
        """Wait for a comment, but give up as soon as the session is paused (None)."""
        get = asyncio.ensure_future(self.queue.get())
        paused = asyncio.ensure_future(self._paused.wait())
        try:
            await asyncio.wait({get, paused}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            paused.cancel()
            if not get.done():
                get.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await get
        if get.cancelled():
            return None
        queued = get.result()
        if self._paused.is_set():
            # Paused in the same instant the comment arrived: put it back for after resume. `received_at` is kept,
            # so it still goes stale on time; only its order among equal priorities changes.
            await self.queue.put(queued.comment, queued.priority)
            return None
        return queued

    # ---------- Session control (US4) ----------

    def pause(self, t_mono: float | None = None) -> str:
        """No new turn starts; the current one finishes. Idempotent: a repeat publishes and logs nothing."""
        if not self._paused.is_set():
            self._running.clear()
            self._paused.set()
            self._publish_state(t_mono, "pause")
        return self.state

    def resume(self, t_mono: float | None = None) -> str:
        if self._paused.is_set():
            self._paused.clear()
            self._running.set()
            self._publish_state(t_mono, "resume")
        return self.state

    async def skip(self, t_mono: float | None = None) -> str | None:
        """Cut the current turn short; returns its `utterance_id`, or None when nothing is speaking."""
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

    def inject_fault(self, step: str, mode: str, count: int = 1) -> None:
        """Make the next `count` turns that reach `step` fail there (dev only, `POST /api/debug/fault`)."""
        if step not in FAULT_STEPS or mode not in FAULT_MODES or count < 1:
            raise ValueError(f"Bad fault: step={step!r} mode={mode!r} count={count!r}")
        self._faults[step].extend([mode] * count)
        log_event(logger, "fault_injected", step=step, mode=mode, count=count)

    def _take_fault(self, step: str) -> str | None:
        pending = self._faults[step]
        return pending.popleft() if pending else None

    def _publish_state(self, t_mono: float | None, command: str) -> None:
        self.bus.publish(Event(EventType.SESSION_STATE, {"state": self.state}))
        self._log_applied(command, t_mono)

    def _log_applied(self, command: str, t_mono: float | None, **fields: object) -> None:
        latency_ms = 0.0 if t_mono is None else max(0.0, (self._clock() - t_mono) * 1000)
        log_event(logger, "control_applied", command=command, latency_ms=round(latency_ms, 1), **fields)

    async def run_turn(self, queued: QueuedComment) -> Utterance:
        async with self._lock:
            return await self._turn(queued)

    async def speak_text(self, text: str) -> str:
        """Speak `text` through TTS + renderer only, skipping the LLM and the queue (Article IV, `/api/debug/speak`).

        Renderer errors (`RendererUnavailable`, `TimeoutError`) propagate so the API can return the right status.
        """
        if self._lock.locked():
            raise DirectorBusy("Đang có lượt nói")
        async with self._lock:
            utterance_id = uuid.uuid4().hex
            chunks = await asyncio.wait_for(self._collect_tts(text), self.tts_timeout_s)
            await self.renderer.speak(utterance_id, text, _iterate(chunks), self.tts.sample_rate)
            return utterance_id

    # ---------- One turn ----------

    async def _turn(self, queued: QueuedComment) -> Utterance:
        comment = queued.comment
        # Snapshot the catalog at the start: replacing content mid-turn must not mix two versions in one answer.
        catalog = self.store.catalog
        utt = Utterance(utterance_id=uuid.uuid4().hex, comment_id=comment.id, catalog_version=catalog.version)
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
            self._turn_tasks = ()
            self.current = None
            self.recent.append(utt)
            self._finish(utt, queued)
        return utt

    async def _produce(
        self, utt: Utterance, queued: QueuedComment, catalog: ProductCatalog, out: asyncio.Queue[object]
    ) -> None:
        who = addressee(queued.comment.author)
        fault = self._take_fault("llm")
        replies = _faulty_stream(fault, "llm") if fault else self.engine.reply(queued.comment, catalog)
        budget = _LlmBudget(self.llm_timeout_s)
        try:
            while True:
                sentence = await self._next_sentence(replies, budget)
                if sentence is None:
                    break
                self._mark(utt, Milestone.LLM_FIRST_SENTENCE, self._clock())
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
        fault = self._take_fault("tts")
        stream = _faulty_stream(fault, "tts") if fault else self.tts.synthesize(sentence)
        try:
            async with asyncio.timeout(self.tts_timeout_s):
                first = await anext(stream, None)
                self._mark(utt, Milestone.TTS_FIRST_CHUNK, self._clock())
                if first is not None:
                    chunks.put_nowait(first)
                await out.put((sentence, chunks))
                async for chunk in stream:
                    chunks.put_nowait(chunk)
        except TimeoutError as exc:
            raise _StepError(ErrorStep.TTS, f"TTS quá {self.tts_timeout_s} s", "timeout") from exc
        except Exception as exc:
            kind = str(getattr(exc, "kind", type(exc).__name__))
            raise _StepError(ErrorStep.TTS, f"TTS lỗi: {exc}", kind) from exc
        finally:
            chunks.put_nowait(None)
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()

    async def _play(self, utt: Utterance, sentences: asyncio.Queue[object]) -> None:
        seq = 0
        while True:
            item = await sentences.get()
            if item is _END:
                return
            text, chunks = item  # type: ignore[misc]
            utt.sentences.append(text)
            self.bus.publish(Event(EventType.SENTENCE, {"utterance_id": utt.utterance_id, "seq": seq, "text": text}))
            try:
                fault = self._take_fault("render")
                if fault == "error":
                    raise InjectedFault("Lỗi giả lập ở bước render")
                if fault == "timeout":
                    # Nothing is sent, so the host never acks: wait out the renderer's ack timeout like a silent host.
                    await asyncio.sleep(getattr(self.renderer, "ack_timeout_s", 3.0))
                    raise TimeoutError("Giả lập host không phản hồi")
                await self.renderer.speak(utt.utterance_id, text, _drain(chunks), self.tts.sample_rate)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise _StepError(
                    ErrorStep.RENDER, f"Renderer lỗi: {type(exc).__name__}: {exc}", _render_error_kind(exc)
                ) from exc
            if seq == 0:
                self._mark_first_frame(utt)
            seq += 1

    def _mark(self, utt: Utterance, milestone: Milestone, at: float) -> None:
        """Record a milestone once and log it right away, so a stuck turn still shows how far it got."""
        if milestone in utt.marks:
            return
        utt.mark(milestone, at)
        log_event(logger, milestone.value, utterance_id=utt.utterance_id, t_mono=at)

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
        log_event(logger, "turn_finished", **payload)
        self.latency.record(utt)
        if self.session_log is not None:
            self.session_log.write_utterance(utterance_record(utt, self.llm_model))
            if queued.status in _FINAL_COMMENT_STATUSES:
                self.session_log.write_comment(comment_record(queued, queued.status, utt.utterance_id))
        self.bus.publish(Event(EventType.TURN_FINISHED, payload))
        self.bus.publish(Event(EventType.LATENCY, self.latency.summary().to_json()))

    async def _collect_tts(self, text: str) -> list[bytes]:
        return [chunk async for chunk in self.tts.synthesize(text)]


_FINAL_COMMENT_STATUSES = (CommentStatus.ANSWERED, CommentStatus.SKIPPED, CommentStatus.ERROR)


class _LlmBudget:
    """LLM wait time left in one turn."""

    def __init__(self, limit_s: float) -> None:
        self.limit_s = limit_s
        self.spent = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.limit_s - self.spent)


async def _faulty_stream(mode: str, step: str) -> AsyncIterator:
    """Stand-in for an LLM or TTS stream: fails at once (`error`) or never answers, so the step timeout fires."""
    if mode == "error":
        raise InjectedFault(f"Lỗi giả lập ở bước {step}")
    await asyncio.Event().wait()
    yield  # unreachable; makes this an async generator


def _render_error_kind(exc: Exception) -> str:
    if isinstance(exc, InjectedFault):
        return exc.kind
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, RendererUnavailable):
        return "host_unavailable"
    return type(exc).__name__


async def _drain(chunks: asyncio.Queue[bytes | None]) -> AsyncIterator[bytes]:
    while (chunk := await chunks.get()) is not None:
        yield chunk


async def _iterate(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk
