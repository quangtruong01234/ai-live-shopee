"""In-process EventBus pushing events to the control page (contracts/events.md §3).

Each subscriber has its own bounded queue; when full, that subscriber alone loses its oldest event,
so a slow control page never slows the pipeline.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ai_live.core.models import Comment, DropReason


class EventType(StrEnum):
    STATE = "state"
    COMMENT_ACCEPTED = "comment_accepted"
    COMMENT_DROPPED = "comment_dropped"
    QUEUE_CHANGED = "queue_changed"
    TURN_STARTED = "turn_started"
    SENTENCE = "sentence"
    GUARD_BLOCKED = "guard_blocked"
    TURN_FINISHED = "turn_finished"
    SESSION_STATE = "session_state"
    CONTENT_REPLACED = "content_replaced"
    HOST_CONNECTION = "host_connection"
    LATENCY = "latency"


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"type": self.type.value, **self.payload}


class Subscription:
    """One subscriber. Read with `async for`; `close()` unsubscribes.

    After `close()` the loop still yields the events left in the queue, then ends.
    """

    def __init__(self, bus: EventBus, max_queue: int) -> None:
        self._bus = bus
        self._events: deque[Event] = deque(maxlen=max_queue)
        self._wakeup = asyncio.Event()
        self._closed = False
        self.dropped = 0

    def _push(self, event: Event) -> None:
        if len(self._events) == self._events.maxlen:
            self.dropped += 1
        self._events.append(event)
        self._wakeup.set()

    def drain(self) -> list[Event]:
        """Take every pending event right now, without waiting."""
        events = list(self._events)
        self._events.clear()
        return events

    def close(self) -> None:
        self._closed = True
        self._bus._unsubscribe(self)
        self._wakeup.set()

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> Event:
        while not self._events:
            if self._closed:
                raise StopAsyncIteration
            self._wakeup.clear()
            await self._wakeup.wait()
        return self._events.popleft()

    async def __aenter__(self) -> Subscription:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.close()


class EventBus:
    def __init__(self, max_queue: int = 1000) -> None:
        self._max_queue = max_queue
        self._subscribers: list[Subscription] = []

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> Subscription:
        """Registers at call time, not at the first iteration.

        So no event published between subscribing and starting to read is missed.
        """
        sub = Subscription(self, self._max_queue)
        self._subscribers.append(sub)
        return sub

    def publish(self, event: Event) -> None:
        """No await: the pipeline moves on right away, however slowly subscribers read."""
        for sub in self._subscribers:
            sub._push(event)

    def _unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subscribers:
            self._subscribers.remove(sub)


def comment_dropped_event(comment: Comment, reason: DropReason) -> Event:
    """`comment_dropped` for the control page; filter, queue_full and stale drops all share this shape."""
    return Event(
        EventType.COMMENT_DROPPED,
        {"comment_id": comment.id, "author": comment.author, "text": comment.text, "reason": reason.value},
    )
