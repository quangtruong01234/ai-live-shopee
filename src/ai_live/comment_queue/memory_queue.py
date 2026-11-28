"""In-process priority comment queue (contracts/adapters.md `CommentQueue`, research R9).

One waiting comment per viewer (001 FR-028, ADR-077): a newer comment from the same viewer replaces the waiting one
unless it ranks lower, and the loser is dropped as `superseded`; without this a fast viewer fills every turn even under
the rate limit. Bounded: when full, the lowest-priority earliest comment makes room (`queue_full`). Comments older than
`max_age_s` are dropped (`stale`) both when `get()` reaches them and by the periodic `sweep()`, so the host never
answers a question the viewer asked long ago.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import time
from collections.abc import Callable

from ai_live.core.events import Event, EventBus, EventType, comment_dropped_event
from ai_live.core.logging import log_event
from ai_live.core.models import Comment, CommentStatus, DropReason, Priority, QueuedComment

logger = logging.getLogger("ai_live.queue")

_Entry = tuple[int, int, QueuedComment]


class InMemoryCommentQueue:
    def __init__(
        self,
        max_size: int = 50,
        max_age_s: float = 30,
        bus: EventBus | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._heap: list[_Entry] = []
        self._seq = itertools.count()
        self._not_empty = asyncio.Condition()
        self._max_size = max_size
        self._max_age_s = max_age_s
        self._bus = bus
        self._clock = clock

    async def put(self, comment: Comment, priority: Priority) -> QueuedComment:
        """Returns the queued item; its status is `dropped` when the queue was full and it ranked strictly lowest, or
        when the same viewer already has a higher-ranked or newer comment waiting (`superseded`)."""
        item = QueuedComment(comment=comment, priority=priority, seq=next(self._seq))
        key = comment.author_key
        waiting = next((e for e in self._heap if e[2].comment.author_key == key), None)
        if waiting is not None:
            old = waiting[2]
            # A comment put back after a pause is older than the one that arrived meanwhile, so age breaks the tie.
            newer_or_same = comment.received_at >= old.comment.received_at
            if int(priority) < int(old.priority) or (priority == old.priority and newer_or_same):
                self._heap.remove(waiting)
                heapq.heapify(self._heap)
                self._drop([old], DropReason.SUPERSEDED)
            else:
                self._drop([item], DropReason.SUPERSEDED)
                return item
        if len(self._heap) >= self._max_size:
            worst = max(entry[0] for entry in self._heap)
            if int(priority) > worst:
                self._drop([item], DropReason.QUEUE_FULL)
                return item
            victim = min((e for e in self._heap if e[0] == worst), key=lambda e: e[1])
            self._heap.remove(victim)
            heapq.heapify(self._heap)
            self._drop([victim[2]], DropReason.QUEUE_FULL)
        async with self._not_empty:
            heapq.heappush(self._heap, (int(priority), item.seq, item))
            self._not_empty.notify()
        self._publish_changed()
        return item

    async def get(self) -> QueuedComment:
        async with self._not_empty:
            while True:
                stale = self._remove_stale()
                if self._heap:
                    item = heapq.heappop(self._heap)[2]
                    self._publish_changed()
                    return item
                if stale:
                    self._publish_changed()
                await self._not_empty.wait()

    def size(self) -> int:
        return len(self._heap)

    def snapshot(self) -> list[QueuedComment]:
        """In exactly the order `get()` will return, without removing anything."""
        return [entry[2] for entry in sorted(self._heap)]

    def sweep(self) -> list[QueuedComment]:
        """Drop every stale comment now. Synchronous with no await, so it cannot interleave with `get()`."""
        stale = self._remove_stale()
        if stale:
            self._publish_changed()
        return stale

    async def run_sweeper(self, interval_s: float = 1.0) -> None:
        """Sweep forever; the control page sees stale comments leave even while the host is busy talking."""
        while True:
            await asyncio.sleep(interval_s)
            self.sweep()

    def remove_author(self, author_key: str, reason: DropReason = DropReason.BLOCKED) -> list[QueuedComment]:
        """Drop every waiting comment of one viewer (001 FR-029: the operator blocked them)."""
        gone = [e for e in self._heap if e[2].comment.author_key == author_key]
        if not gone:
            return []
        self._heap = [e for e in self._heap if e not in gone]
        heapq.heapify(self._heap)
        items = [e[2] for e in sorted(gone)]
        self._drop(items, reason)
        self._publish_changed()
        return items

    def _remove_stale(self) -> list[QueuedComment]:
        now = self._clock()
        stale = [e for e in self._heap if now - e[2].comment.received_at > self._max_age_s]
        if not stale:
            return []
        self._heap = [e for e in self._heap if e not in stale]
        heapq.heapify(self._heap)
        items = [e[2] for e in sorted(stale)]
        self._drop(items, DropReason.STALE)
        return items

    def _drop(self, items: list[QueuedComment], reason: DropReason) -> None:
        for item in items:
            item.status = CommentStatus.DROPPED
            item.drop_reason = reason
            log_event(logger, "comment_dropped", comment_id=item.comment.id, reason=reason.value)
            if self._bus is not None:
                self._bus.publish(comment_dropped_event(item.comment, reason))

    def _publish_changed(self) -> None:
        if self._bus is not None:
            self._bus.publish(Event(EventType.QUEUE_CHANGED, {"queue": [q.to_json() for q in self.snapshot()]}))
