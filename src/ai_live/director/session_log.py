"""Session files under `data/sessions/<session_id>/` (001 contracts/events.md §2; 004 contracts/events.md §2;
005 contracts/events.md §3-§4; 003 contracts/events.md §3).

Every write runs on one dedicated worker thread: file I/O never blocks the event loop, and a single worker keeps
lines in the order they were submitted. Each record passes through `redact` before it is serialised.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from ai_live.core.events import Event, EventType, Subscription
from ai_live.core.logging import log_event
from ai_live.core.models import (
    REQUIRED_MILESTONES,
    REQUIRED_SCRIPT_MILESTONES,
    AvatarModeState,
    CommentStatus,
    LipsyncHealth,
    Milestone,
    QueuedComment,
    RenderTurnStats,
    ScriptSentence,
    Segment,
    SentenceGap,
    SentenceStatus,
    ShowSummary,
    Utterance,
)
from ai_live.director.show_stats import COUNTED_GAP_KINDS
from ai_live.security.redact import redact

logger = logging.getLogger("ai_live.session_log")

COMMENTS_FILE = "comments.jsonl"
UTTERANCES_FILE = "utterances.jsonl"
ERRORS_FILE = "errors.jsonl"
SUMMARY_FILE = "latency_summary.json"
# 003: characters sent to the voice source in this session, to watch the free quota (FR-015).
TTS_USAGE_FILE = "tts_usage.json"
SEGMENTS_FILE = "segments.jsonl"
SCRIPT_SENTENCES_FILE = "script_sentences.jsonl"
SHOW_SUMMARY_FILE = "show_summary_{show_id}.json"
# 005: one line per avatar mode change and per fork health report, to plot VRAM / fps over a 30-minute run (SC-006).
AVATAR_FILE = "avatar.jsonl"
# 007: run conditions, every gap the runner measured, watchdog alerts and readiness checks, so the rehearsal report
# still has its data when the app crashed before `show_summary` (research R4).
SESSION_INFO_FILE = "session.json"
GAPS_FILE = "gaps.jsonl"
ALERTS_FILE = "alerts.jsonl"
READINESS_FILE = "readiness.jsonl"

# `type` values of a `render` step line in errors.jsonl; fault injection adds `injected_*` on top.
RENDER_ERROR_KINDS = frozenset(
    {
        "timeout",
        "host_unavailable",
        "lipsync_unavailable",
        "vram_oom",
        "inference_failed",
        "bad_audio",
        "renderer_restarted",
    }
)

_MARK_ORDER = (
    Milestone.COMMENT_RECEIVED,
    Milestone.SEGMENT_REQUESTED,
    Milestone.TURN_STARTED,
    *REQUIRED_MILESTONES[1:],
)
# Sentence counts of a `segments.jsonl` line (004 contracts/events.md §2).
_SEGMENT_SENTENCE_COUNTS = (
    SentenceStatus.SPOKEN,
    SentenceStatus.BLOCKED,
    SentenceStatus.DROPPED,
    SentenceStatus.TTS_ERROR,
)


def iso_now() -> str:
    return _iso(time.time())


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def mono_to_iso(mono: float) -> str:
    """Wall-clock ISO time of a `time.monotonic()` value (comments carry monotonic `received_at`)."""
    return _iso(time.time() - (time.monotonic() - mono))


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _with_show(record: dict[str, Any], show_id: str | None) -> dict[str, Any]:
    # Added only inside a show, so a 001 line keeps exactly its old shape.
    if show_id is not None:
        record["show_id"] = show_id
    return record


def comment_record(
    queued: QueuedComment,
    status: CommentStatus | str,
    utterance_id: str | None = None,
    *,
    show_id: str | None = None,
) -> dict[str, Any]:
    comment = queued.comment
    record = {
        "comment_id": comment.id,
        "received_at": mono_to_iso(comment.received_at),
        "author": comment.author,
        "text": comment.text,
        "truncated": bool(comment.meta.get("truncated", False)),
        "status": str(status),
        "drop_reason": queued.drop_reason.value if queued.drop_reason else None,
        "priority": queued.priority.name,
        "utterance_id": utterance_id,
    }
    return _with_show(record, show_id)


def dropped_record(payload: dict[str, Any]) -> dict[str, Any]:
    """`comments.jsonl` line built from a `comment_dropped` event.

    The event has no receive time, `truncated` flag or priority, so those are the drop time, null and null.
    """
    record = {
        "comment_id": payload.get("comment_id"),
        "received_at": iso_now(),
        "author": payload.get("author"),
        "text": payload.get("text"),
        "truncated": None,
        "status": CommentStatus.DROPPED.value,
        "drop_reason": payload.get("reason"),
        "priority": None,
        "utterance_id": None,
    }
    return _with_show(record, payload.get("show_id"))


def _relative_marks(
    marks: dict[Milestone, float], origin: float | None, order: tuple[Milestone, ...]
) -> dict[str, float]:
    if origin is None:
        return {}
    return {m.value: round(marks[m] - origin, 3) for m in order if m in marks}


def utterance_record(utt: Utterance, llm_model: str | None, *, render: RenderTurnStats | None = None) -> dict[str, Any]:
    """`marks` are seconds relative to the start of the clock, to keep the file readable.

    The clock starts at `comment_received` for a reply and at `segment_requested` for a scripted sentence.
    `segment_id`, `show_id` and the 005 render fields are added only when set, so a 001 line keeps exactly its
    old shape.
    """
    origin = utt.marks.get(Milestone.COMMENT_RECEIVED)
    if origin is None:
        origin = utt.marks.get(Milestone.SEGMENT_REQUESTED)
    marks = _relative_marks(utt.marks, origin, _MARK_ORDER)
    record: dict[str, Any] = {
        "utterance_id": utt.utterance_id,
        "comment_id": utt.comment_id,
        "catalog_version": utt.catalog_version,
        "llm_model": llm_model,
        "sentences": list(utt.sentences),
        "outcome": utt.outcome.value,
        "error_step": utt.error_step.value if utt.error_step else None,
        "guard_reason": utt.guard_reason.value if utt.guard_reason else None,
        "marks": marks,
        "total_s": marks.get(Milestone.AVATAR_FIRST_FRAME.value),
        "queue_wait_s": marks.get(Milestone.TURN_STARTED.value),
    }
    if utt.segment_id is not None:
        record["segment_id"] = utt.segment_id
    if render is not None:
        record["render_fps"] = render.render_fps
        record["infer_fps"] = render.infer_fps
        record["clips_used"] = list(render.clips_used)
        record["scene_ms"] = render.scene_ms
        record["mouth_method"] = render.mouth_method
    return _with_show(record, utt.show_id)


def avatar_mode_record(state: AvatarModeState | dict[str, Any]) -> dict[str, Any]:
    """`avatar.jsonl` line for a mode change (fallback to the still image, lip-sync re-enabled, startup)."""
    data = state.to_json() if isinstance(state, AvatarModeState) else dict(state)
    data.pop("type", None)
    return {"ts": iso_now(), "kind": "mode", **data}


def render_record(stats: RenderTurnStats, show_id: str | None) -> dict[str, Any]:
    """`avatar.jsonl` line with one turn's or one scripted sentence's render figures (005 contracts/events.md §4).

    `utterances.jsonl` of a scripted sentence is written before its figures arrive (LIVETALKING_LEAD_S), so the
    rehearsal report reads fps and mouth method from these lines instead.
    """
    return {
        "ts": iso_now(),
        "kind": "render",
        "utterance_id": stats.utterance_id,
        "show_id": show_id,
        "frames": stats.frames,
        "render_fps": stats.render_fps,
        "infer_fps": stats.infer_fps,
        "clips_used": list(stats.clips_used),
        "scene_ms": stats.scene_ms,
        "mouth_method": stats.mouth_method,
    }


def lipsync_health_record(health: LipsyncHealth | dict[str, Any], *, vram_peak_mb: int | None = None) -> dict[str, Any]:
    """`avatar.jsonl` line for a fork health report; `vram_peak_mb` is added when the fork sent it."""
    data = health.to_json() if isinstance(health, LipsyncHealth) else dict(health)
    data.pop("type", None)
    record = {"ts": iso_now(), "kind": "health", **data}
    if vram_peak_mb is not None:
        record["vram_peak_mb"] = vram_peak_mb
    return record


def error_record(
    step: str,
    error_type: str,
    message: str,
    utterance_id: str | None = None,
    *,
    segment_id: str | None = None,
    show_id: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {"ts": iso_now()}
    if utterance_id is not None:
        record["utterance_id"] = utterance_id
    if segment_id is not None:
        record["segment_id"] = segment_id
    if show_id is not None:
        record["show_id"] = show_id
    record.update({"step": step, "type": error_type, "message": message})
    return record


def segment_record(segment: Segment) -> dict[str, Any]:
    """`segments.jsonl` line, written once the segment reaches a final status."""
    counts = {status.value: 0 for status in _SEGMENT_SENTENCE_COUNTS}
    for sentence in segment.sentences:
        if sentence.status.value in counts:
            counts[sentence.status.value] += 1
    return {
        "segment_id": segment.segment_id,
        "show_id": segment.show_id,
        "index": segment.index,
        "product_id": segment.product_id,
        "topic": segment.topic.value,
        "origin": segment.origin.value,
        "mode": segment.mode.value,
        "catalog_version": segment.catalog_version,
        "status": segment.status.value,
        "requested_at": _dt_iso(segment.requested_at),
        "ready_at": _dt_iso(segment.ready_at),
        "started_at": _dt_iso(segment.started_at),
        "finished_at": _dt_iso(segment.finished_at),
        "sentences": counts,
        "error_step": segment.error_step,
        "error_kind": segment.error_kind,
    }


def gap_record(show_id: str, gap: SentenceGap, at: datetime) -> dict[str, Any]:
    """`gaps.jsonl` line (007 contracts/files.md §2); `at` is when the later sentence started playing."""
    return {
        "show_id": show_id,
        "kind": gap.kind.value,
        "counted": gap.kind in COUNTED_GAP_KINDS,
        "seconds": gap.seconds,
        "from_id": gap.from_utterance_id,
        "to_id": gap.to_utterance_id,
        "at": _dt_iso(at),
    }


def script_sentence_record(sentence: ScriptSentence, source: str) -> dict[str, Any]:
    """`script_sentences.jsonl` line. `marks` and `played_at` are seconds relative to `segment_requested`."""
    origin = sentence.marks.get(Milestone.SEGMENT_REQUESTED)
    played_at = None
    if origin is not None and sentence.played_at is not None:
        played_at = round(sentence.played_at - origin, 3)
    return {
        "utterance_id": sentence.utterance_id,
        "segment_id": sentence.segment_id,
        "seq": sentence.seq,
        "source": source,
        "text": sentence.text,
        "raw_text": sentence.raw_text,
        "status": sentence.status.value,
        "guard_reason": sentence.guard_reason.value if sentence.guard_reason else None,
        "guard_detail": sentence.guard_detail,
        "drop_reason": sentence.drop_reason,
        "marks": _relative_marks(sentence.marks, origin, REQUIRED_SCRIPT_MILESTONES),
        "played_at": played_at,
    }


class SessionLog:
    """Append-only JSONL files of one live session. Create with `await SessionLog.open(...)`."""

    def __init__(self, directory: Path, session_id: str) -> None:
        self.directory = directory
        self.session_id = session_id
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="session-log")
        self._files: dict[str, TextIO] = {}
        self._closed = False

    @classmethod
    async def open(cls, base_dir: Path, session_id: str) -> SessionLog:
        directory = Path(base_dir) / session_id
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        return cls(directory, session_id)

    # ---------- Writes (return at once; the worker thread does the I/O) ----------

    def write_comment(self, record: dict[str, Any]) -> None:
        self._submit(COMMENTS_FILE, record)

    def write_utterance(self, record: dict[str, Any]) -> None:
        self._submit(UTTERANCES_FILE, record)

    def write_error(self, record: dict[str, Any]) -> None:
        self._submit(ERRORS_FILE, record)

    def write_segment(self, record: dict[str, Any]) -> None:
        self._submit(SEGMENTS_FILE, record)

    def write_script_sentence(self, record: dict[str, Any]) -> None:
        self._submit(SCRIPT_SENTENCES_FILE, record)

    def write_avatar(self, record: dict[str, Any]) -> None:
        self._submit(AVATAR_FILE, record)

    def write_gap(self, record: dict[str, Any]) -> None:
        self._submit(GAPS_FILE, record)

    def write_alert(self, record: dict[str, Any]) -> None:
        self._submit(ALERTS_FILE, record)

    def write_readiness(self, record: dict[str, Any]) -> None:
        self._submit(READINESS_FILE, record)

    def write_session_info(self, info: dict[str, Any]) -> None:
        """Write `session.json` (run conditions at session start); returns at once like the JSONL writes."""
        if self._closed:
            return
        self._executor.submit(self._write_json, SESSION_INFO_FILE, info)

    async def write_show_summary(self, summary: ShowSummary | dict[str, Any]) -> None:
        """Write `show_summary_<show_id>.json` and wait until it is on disk (show end or app shutdown)."""
        if self._closed:
            return
        data = summary.to_json() if isinstance(summary, ShowSummary) else summary
        name = SHOW_SUMMARY_FILE.format(show_id=data["show_id"])
        await asyncio.get_running_loop().run_in_executor(self._executor, self._write_json, name, data)

    async def write_summary(self, data: dict[str, Any]) -> None:
        """Write `latency_summary.json` once (at shutdown) and wait until it is on disk."""
        if self._closed:
            return
        await asyncio.get_running_loop().run_in_executor(self._executor, self._write_json, SUMMARY_FILE, data)

    async def write_tts_usage(self, usage: dict[str, Any]) -> None:
        """Write `tts_usage.json` once (at shutdown, next to `latency_summary.json`) and wait until it is on disk."""
        if self._closed:
            return
        await asyncio.get_running_loop().run_in_executor(self._executor, self._write_json, TTS_USAGE_FILE, usage)

    async def record_drops(self, sub: Subscription) -> None:
        """Write a `comments.jsonl` line for every `comment_dropped` event.

        Drops happen in the intake (filters) and in the queue (full, stale); listening on the bus covers all of
        them without those stages knowing about session files. Pass a subscription taken at startup so no early
        drop is missed.
        """
        try:
            async for event in sub:
                if event.type is EventType.COMMENT_DROPPED:
                    self.write_comment(dropped_record(event.payload))
        finally:
            sub.close()

    async def record_avatar(self, sub: Subscription) -> None:
        """Write an `avatar.jsonl` line for every `avatar_mode` and `lipsync_health` event.

        Like `record_drops`: the renderers publish on the bus and never hold the session log, which changes per
        session while they live for the whole app.
        """
        try:
            async for event in sub:
                record = _avatar_record(event)
                if record is not None:
                    self.write_avatar(record)
        finally:
            sub.close()

    async def flush(self) -> None:
        """Wait until every write submitted so far is on disk."""
        if not self._closed:
            await asyncio.get_running_loop().run_in_executor(self._executor, lambda: None)

    async def close(self) -> None:
        if self._closed:
            return
        await self.flush()
        self._closed = True
        await asyncio.get_running_loop().run_in_executor(self._executor, self._close_files)
        await asyncio.to_thread(self._executor.shutdown, wait=True)

    # ---------- Worker thread ----------

    def _submit(self, name: str, record: dict[str, Any]) -> None:
        if self._closed:
            return
        self._executor.submit(self._append, name, record)

    def _append(self, name: str, record: dict[str, Any]) -> None:
        try:
            line = json.dumps(redact(record), ensure_ascii=False, default=str)
            handle = self._files.get(name)
            if handle is None:
                handle = self._files[name] = (self.directory / name).open("a", encoding="utf-8")
            handle.write(line + "\n")
            handle.flush()
        except Exception as exc:
            # A full disk must not stop the live; the log line says which file lost data.
            log_event(logger, "session_log_write_failed", logging.ERROR, file=name, error=type(exc).__name__)

    def _write_json(self, name: str, data: dict[str, Any]) -> None:
        try:
            text = json.dumps(redact(data), ensure_ascii=False, indent=2, default=str)
            (self.directory / name).write_text(text + "\n", encoding="utf-8")
        except Exception as exc:
            log_event(logger, "session_log_write_failed", logging.ERROR, file=name, error=type(exc).__name__)

    def _close_files(self) -> None:
        for handle in self._files.values():
            with contextlib.suppress(OSError):
                handle.close()
        self._files.clear()


def _avatar_record(event: Event) -> dict[str, Any] | None:
    if event.type is EventType.AVATAR_MODE:
        return avatar_mode_record(event.payload)
    if event.type is EventType.LIPSYNC_HEALTH:
        return lipsync_health_record(event.payload)
    return None
