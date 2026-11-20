"""What the AI host just said, for the control page's "AI vừa nói" list (012 US4, FR-020, FR-021, data-model §7).

A bus subscriber keeps the scripted sentences in a ring buffer, so a reloaded control page gets the recent ones back in
`/api/state` instead of an empty list. Memory only: the session log stays the record.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

from ai_live.app.context import now_iso
from ai_live.core.events import Event, EventBus, EventType, Subscription

SPOKEN_MAX = 100
# A show starts over from these states; `paused` -> `running` is the same show going on.
_NEW_SHOW_FROM = {None, "idle", "ended"}


class _Catalog(Protocol):
    @property
    def products(self) -> Any: ...


class SpokenLog:
    def __init__(
        self,
        bus: EventBus,
        catalog: Callable[[], _Catalog | None],
        *,
        maxlen: int = SPOKEN_MAX,
        clock: Callable[[], str] = now_iso,
    ) -> None:
        self._bus = bus
        self._catalog = catalog
        self._clock = clock
        self._entries: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._show_state: str | None = None
        self._sub: Subscription | None = None
        self._task: asyncio.Task[None] | None = None

    def entries(self) -> list[dict[str, Any]]:
        """Newest first, as the page lists them."""
        return [dict(e) for e in reversed(self._entries)]

    def on_event(self, event: Event) -> None:
        if event.type is EventType.SHOW_STATE:
            state = event.payload.get("state")
            if state == "running" and self._show_state in _NEW_SHOW_FROM:
                self._entries.clear()
            self._show_state = state
        elif event.type is EventType.SENTENCE and event.payload.get("segment_id"):
            # Comment replies have no segment; blocked sentences never get a `sentence` event at all.
            payload = event.payload
            # Every scripted sentence is its own utterance: a repeated id is the same line, keep one row.
            if any(e["utterance_id"] == payload.get("utterance_id") for e in self._entries):
                return
            product_id = payload.get("product_id")
            self._entries.append(
                {
                    "ts": self._clock(),
                    "utterance_id": payload.get("utterance_id"),
                    "segment_id": payload["segment_id"],
                    "text": payload.get("text", ""),
                    "product_id": product_id,
                    # Looked up now: a later content change must not rename what was already said.
                    "product_name": self._name(product_id),
                    "topic": payload.get("topic"),
                }
            )

    def _name(self, product_id: str | None) -> str | None:
        catalog = self._catalog() if product_id else None
        if catalog is None:
            return None
        return next((p.name for p in catalog.products if p.id == product_id), None)

    def start(self) -> None:
        # Subscribed at call time, so nothing published before the read loop runs is lost.
        self._sub = self._bus.subscribe()
        self._task = asyncio.create_task(self._read(self._sub), name="spoken_log")

    async def _read(self, sub: Subscription) -> None:
        async for event in sub:
            self.on_event(event)

    async def stop(self) -> None:
        if self._sub is not None:
            self._sub.close()
            self._sub = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
