"""Session files under `data/sessions/<session_id>/` (contracts/events.md §2; FR-019, FR-021).

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

from ai_live.core.events import EventType, Subscription
from ai_live.core.logging import log_event
from ai_live.core.models import REQUIRED_MILESTONES, CommentStatus, Milestone, QueuedComment, Utterance
from ai_live.security.redact import redact

logger = logging.getLogger("ai_live.session_log")

COMMENTS_FILE = "comments.jsonl"
UTTERANCES_FILE = "utterances.jsonl"
ERRORS_FILE = "errors.jsonl"
SUMMARY_FILE = "latency_summary.json"

_MARK_ORDER = (Milestone.COMMENT_RECEIVED, Milestone.TURN_STARTED, *REQUIRED_MILESTONES[1:])


def iso_now() -> str:
    return _iso(time.time())


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def mono_to_iso(mono: float) -> str:
    """Wall-clock ISO time of a `time.monotonic()` value (comments carry monotonic `received_at`)."""
    return _iso(time.time() - (time.monotonic() - mono))


def comment_record(
    queued: QueuedComment, status: CommentStatus | str, utterance_id: str | None = None
) -> dict[str, Any]:
    comment = queued.comment
    return {
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


def dropped_record(payload: dict[str, Any]) -> dict[str, Any]:
    """`comments.jsonl` line built from a `comment_dropped` event.

    The event has no receive time, `truncated` flag or priority, so those are the drop time, null and null.
    """
    return {
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


def utterance_record(utt: Utterance, llm_model: str | None) -> dict[str, Any]:
    """`marks` are seconds relative to `comment_received`, as the contract asks, to keep the file readable."""
    origin = utt.marks.get(Milestone.COMMENT_RECEIVED)
    marks: dict[str, float] = {}
    if origin is not None:
        marks = {m.value: round(utt.marks[m] - origin, 3) for m in _MARK_ORDER if m in utt.marks}
    return {
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


def error_record(step: str, error_type: str, message: str, utterance_id: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"ts": iso_now()}
    if utterance_id is not None:
        record["utterance_id"] = utterance_id
    record.update({"step": step, "type": error_type, "message": message})
    return record


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

    async def write_summary(self, data: dict[str, Any]) -> None:
        """Write `latency_summary.json` once (at shutdown) and wait until it is on disk."""
        if self._closed:
            return
        await asyncio.get_running_loop().run_in_executor(self._executor, self._write_json, SUMMARY_FILE, data)

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
