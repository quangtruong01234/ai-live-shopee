"""`SwitchingRenderer`: what `AVATAR_MODE=livetalking` runs, routing each turn to lip-sync or the still image (005).

The host page always attaches here and the channel is `StaticRenderer`'s, so the subtitles, the `sessionid` the page
reports and the still-image fallback all share one socket. A turn keeps the renderer picked at its first sentence; a
mode change applies from the next turn, so a viewer never sees one turn switch picture halfway (data-model §4).

`AVATAR_FALLBACK_AFTER` render-error turns in a row switch to the still image (FR-022, research R9); only the operator
switches back (`enable_lipsync`), because a fork that just failed twice is likely to fail again.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_live.avatar.static_renderer import HostConnection, StaticRenderer
from ai_live.core.events import EventBus, avatar_mode_event
from ai_live.core.logging import log_event
from ai_live.core.models import AvatarMode, AvatarModeState, RenderTurnStats

logger = logging.getLogger(__name__)

_KEEP_UTTERANCES = 64
FALLBACK_REASON = "render_errors"
# Error kind the director gives a `RendererUnavailable` (host page closed); it never counts toward the fallback.
HOST_UNAVAILABLE = "host_unavailable"


class LipsyncRenderer(Protocol):
    """What `SwitchingRenderer` needs from `LiveTalkingRenderer` (a fake in unit tests)."""

    ack_timeout_s: float

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None: ...
    async def interrupt(self) -> None: ...
    @property
    def is_speaking(self) -> bool: ...
    def first_playback_at(self, utterance_id: str) -> float | None: ...
    def render_stats(self, utterance_id: str) -> RenderTurnStats | None: ...


class SwitchingRenderer:
    def __init__(
        self,
        lipsync: LipsyncRenderer,
        static: StaticRenderer,
        *,
        fallback_after: int = 2,
        configured: AvatarMode = "livetalking",
        bus: EventBus | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.lipsync = lipsync
        self.static = static
        self.fallback_after = fallback_after
        self._bus = bus
        self._clock = clock
        self._state = AvatarModeState(configured=configured, active=configured)
        self._turn_renderer: dict[str, Any] = {}
        self._mode_message: asyncio.Task[bool] | None = None

    @property
    def mode(self) -> AvatarModeState:
        return self._state

    def _active_renderer(self) -> Any:
        return self.lipsync if self._state.active == "livetalking" else self.static

    def _activate(self, mode: AvatarMode, reason: str | None) -> None:
        if mode == self._state.active:
            return
        self._state.active = mode
        self._state.reason = reason
        self._state.changed_at = self._clock()
        if self._bus is not None:
            self._bus.publish(avatar_mode_event(self._state))
        # Called from sync code (`record_render_outcome`): the host page is told in a task, and `speak` waits for it
        # before a new turn so the page switches picture before that turn's first sentence arrives.
        message = {"type": "mode", "mode": mode, "reason": reason}
        self._mode_message = asyncio.get_running_loop().create_task(self.send_to_host(message))

    # ---------- RenderOutcomeSink + operator switch (data-model §4, FR-022) ----------

    def record_render_outcome(self, utterance_id: str, ok: bool, *, error_kind: str | None = None) -> None:
        state = self._state
        # Configured `static` has nothing to fall back to; after a fallback there is no lower mode either.
        if state.configured != "livetalking" or state.active != "livetalking":
            return
        # A closed host page is not the character failing: counting it would drop to the still image (data-model §4).
        if not ok and error_kind == HOST_UNAVAILABLE:
            return
        if ok:
            state.consecutive_errors = 0
            state.last_utterance_id = utterance_id
            return
        if state.last_utterance_id == utterance_id and state.consecutive_errors > 0:
            return
        state.consecutive_errors += 1
        state.last_utterance_id = utterance_id
        if state.consecutive_errors >= self.fallback_after:
            log_event(
                logger,
                "avatar_fallback",
                logging.WARNING,
                utterance_id=utterance_id,
                consecutive_errors=state.consecutive_errors,
                last_error_kind=error_kind,
            )
            self._activate("static", FALLBACK_REASON)

    async def enable_lipsync(self) -> AvatarModeState:
        """`POST /api/avatar/lipsync`: back to the lip-synced character from the next turn."""
        if self._state.configured != "livetalking":
            raise ValueError("avatar mode is configured as static")
        self._state.consecutive_errors = 0
        self._state.last_utterance_id = None
        if self._state.active != "livetalking":
            self._activate("livetalking", None)
            log_event(logger, "avatar_lipsync_enabled", by="operator")
            await self._flush_mode_message()
        return self._state

    async def _flush_mode_message(self) -> None:
        task, self._mode_message = self._mode_message, None
        if task is None:
            return
        # A page that missed the message (socket closing) reads `active` from `/api/host-config` when it reloads.
        with contextlib.suppress(Exception):
            await asyncio.shield(task)

    # ---------- AvatarRenderer ----------

    @property
    def ack_timeout_s(self) -> float:
        return self._active_renderer().ack_timeout_s

    async def start(self) -> None:
        await self.static.start()
        await self.lipsync.start()
        if self._bus is not None:
            self._bus.publish(avatar_mode_event(self._state))

    async def stop(self) -> None:
        await self.lipsync.stop()
        await self.static.stop()

    @property
    def is_speaking(self) -> bool:
        return self.lipsync.is_speaking or self.static.is_speaking

    def first_playback_at(self, utterance_id: str) -> float | None:
        renderer = self._turn_renderer.get(utterance_id)
        return renderer.first_playback_at(utterance_id) if renderer is not None else None

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None:
        # The still image measures no frame rate: a turn it served reports none (FR-020).
        renderer = self._turn_renderer.get(utterance_id)
        stats = getattr(renderer, "render_stats", None)
        return stats(utterance_id) if stats is not None else None

    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None:
        renderer = self._turn_renderer.get(utterance_id)
        if renderer is None:
            await self._flush_mode_message()
            renderer = self._turn_renderer[utterance_id] = self._active_renderer()
            while len(self._turn_renderer) > _KEEP_UTTERANCES:
                del self._turn_renderer[next(iter(self._turn_renderer))]
        await renderer.speak(utterance_id, text, audio, sample_rate)

    async def interrupt(self) -> None:
        await self.lipsync.interrupt()
        await self.static.interrupt()

    # ---------- Host page channel (owned by the still-image renderer) ----------

    @property
    def host_ready(self) -> bool:
        return self.static.host_ready

    @property
    def lipsync_session(self) -> str | None:
        return self.static.lipsync_session

    async def send_to_host(self, message: dict[str, Any]) -> bool:
        return await self.static.send_to_host(message)

    def on_session_change(self, callback: Callable[[str | None], None]) -> None:
        self.static.on_session_change(callback)

    async def attach(self, conn: HostConnection) -> None:
        await self.static.attach(conn)

    def detach(self, conn: HostConnection) -> None:
        self.static.detach(conn)

    def handle_message(self, conn: HostConnection, message: dict[str, Any]) -> None:
        self.static.handle_message(conn, message)
