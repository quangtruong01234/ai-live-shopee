"""`static` AvatarRenderer: a still image plus audio played on the `/host` page over WebSocket (research R10; FR-014).

Only the browser knows when sound really starts playing, so the renderer waits for the host page's `playback_started` /
`sentence_played` acks instead of guessing durations. The `avatar_first_frame` milestone is the moment the server
receives the `playback_started` ack of a turn's first sentence; ShowDirector reads it through `first_playback_at`.

It also owns the single `/host` connection in both avatar modes (ADR-016), so it is the `HostLink` that the 005
`LiveTalkingRenderer` uses to send subtitle / mode messages and to learn the page's WebRTC `sessionid`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from ai_live.core.events import Event, EventBus, EventType
from ai_live.core.logging import log_event
from ai_live.core.protocols import RendererUnavailable

logger = logging.getLogger("ai_live.avatar")

CLOSE_REPLACED = 4000
# Keep state for the most recent turns only: the live runs 15 hours a day, so these dicts must not keep growing.
_KEEP_UTTERANCES = 64


class HostConnection(Protocol):
    """The part of a WebSocket the renderer uses; Starlette's `WebSocket` already satisfies it."""

    async def send_json(self, data: Any) -> None: ...
    async def send_bytes(self, data: bytes) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class HostLink(Protocol):
    """What the lip-sync renderer needs from the `/host` channel (005 contracts/adapters.md §5)."""

    @property
    def lipsync_session(self) -> str | None:
        """WebRTC `sessionid` the host page got from the fork's `/offer`; None until reported or if `/offer` failed."""
        ...

    @property
    def host_ready(self) -> bool:
        """Host page attached and "ready"; without it a lip-sync failure is the page's, not the character's."""
        ...

    async def send_to_host(self, message: dict[str, Any]) -> bool:
        """Send a JSON message to the attached host page; False when none is attached."""
        ...

    def on_session_change(self, callback: Callable[[str | None], None]) -> None: ...


class StaticRenderer:
    def __init__(
        self,
        ack_timeout_s: float = 3.0,
        *,
        bus: EventBus | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ack_timeout_s = ack_timeout_s
        self._bus = bus
        self._clock = clock
        self._conn: HostConnection | None = None
        self._ready = False
        self._next_seq: dict[str, int] = {}
        self._first_playback: dict[str, float] = {}
        # Pending acks, keyed by (ack kind, utterance_id, seq).
        self._waiters: dict[tuple[str, str, int], asyncio.Future[None]] = {}
        self._speaking: str | None = None
        self._interrupted = False
        self._lipsync_session: str | None = None
        self._session_callbacks: list[Callable[[str | None], None]] = []

    # ---------- AvatarRenderer ----------

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        if self._conn is not None:
            conn = self._conn
            self.detach(conn)
            await conn.close(1001)

    @property
    def is_speaking(self) -> bool:
        return self._speaking is not None

    @property
    def host_ready(self) -> bool:
        return self._conn is not None and self._ready

    def first_playback_at(self, utterance_id: str) -> float | None:
        return self._first_playback.get(utterance_id)

    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None:
        if not self.host_ready:
            raise RendererUnavailable('Chưa mở màn hình host hoặc chưa bấm "Bắt đầu"')
        conn = self._conn
        assert conn is not None
        seq = self._next_seq.get(utterance_id, 0)
        self._next_seq[utterance_id] = seq + 1
        if seq == 0:
            self._prune()
        loop = asyncio.get_running_loop()
        started = self._waiters[("playback_started", utterance_id, seq)] = loop.create_future()
        played = self._waiters[("sentence_played", utterance_id, seq)] = loop.create_future()
        self._speaking = utterance_id
        self._interrupted = False
        try:
            await conn.send_json(
                {
                    "type": "sentence_start",
                    "utterance_id": utterance_id,
                    "seq": seq,
                    "text": text,
                    "sample_rate": sample_rate,
                }
            )
            audio_bytes = 0
            async for chunk in audio:
                if self._interrupted:
                    return
                self._check_conn(conn)
                await conn.send_bytes(chunk)
                audio_bytes += len(chunk)
            if self._interrupted:
                return
            await conn.send_json({"type": "sentence_end", "utterance_id": utterance_id, "seq": seq})
            # The timeout applies per ack: a long sentence is still valid; only a host silent past ACK_TIMEOUT fails.
            await asyncio.wait_for(started, self.ack_timeout_s)
            duration_s = audio_bytes / 2 / sample_rate
            await asyncio.wait_for(played, duration_s + self.ack_timeout_s)
        finally:
            self._waiters.pop(("playback_started", utterance_id, seq), None)
            self._waiters.pop(("sentence_played", utterance_id, seq), None)
            for fut in (started, played):
                if not fut.done():
                    fut.cancel()
                elif not fut.cancelled():
                    # Mark the error as retrieved so an ack nobody waits for no longer logs
                    # "exception was never retrieved".
                    fut.exception()
            self._speaking = None

    async def interrupt(self) -> None:
        utterance_id = self._speaking
        # A repeated skip before `speak` has unwound must not send a second `stop`.
        if utterance_id is None or self._interrupted:
            return
        self._interrupted = True
        if self._conn is not None:
            await self._conn.send_json({"type": "stop", "utterance_id": utterance_id})
        for (_, uid, _seq), fut in list(self._waiters.items()):
            if uid == utterance_id and not fut.done():
                fut.set_result(None)

    # ---------- HostLink ----------

    @property
    def lipsync_session(self) -> str | None:
        return self._lipsync_session

    async def send_to_host(self, message: dict[str, Any]) -> bool:
        conn = self._conn
        if conn is None:
            return False
        await conn.send_json(message)
        return True

    def on_session_change(self, callback: Callable[[str | None], None]) -> None:
        self._session_callbacks.append(callback)

    # ---------- /ws/host channel ----------

    async def attach(self, conn: HostConnection) -> None:
        """A new host connection replaces the old one: only one screen plays, so two places never speak (api.md §4)."""
        old = self._conn
        if old is not None:
            self._drop_connection()
        self._conn = conn
        log_event(logger, "host_attached")
        if old is not None:
            await old.close(CLOSE_REPLACED)

    def detach(self, conn: HostConnection) -> None:
        if conn is self._conn:
            self._drop_connection()
            log_event(logger, "host_detached")

    def handle_message(self, conn: HostConnection, message: dict[str, Any]) -> None:
        if conn is not self._conn:
            return
        kind = message.get("type")
        if kind == "ready":
            if not self._ready:
                self._ready = True
                self._publish_connection(True)
            # A static-mode page sends no `lipsync_session`; that must not clear one reported earlier.
            if "lipsync_session" in message:
                self._set_lipsync_session(message["lipsync_session"])
            return
        if kind == "lipsync_session":
            self._set_lipsync_session(message.get("session"))
            return
        if kind not in ("playback_started", "sentence_played"):
            return
        utterance_id = message.get("utterance_id")
        seq = message.get("seq")
        if not isinstance(utterance_id, str) or not isinstance(seq, int):
            return
        # Only a turn this renderer actually sent counts: a bogus or late ack must not create a milestone, nor bring
        # back one already pruned (which would also let the dict grow between turns).
        if kind == "playback_started" and seq == 0 and utterance_id in self._next_seq:
            self._first_playback.setdefault(utterance_id, self._clock())
        fut = self._waiters.get((kind, utterance_id, seq))
        if fut is not None and not fut.done():
            fut.set_result(None)

    # ---------- Internals ----------

    def _check_conn(self, conn: HostConnection) -> None:
        if conn is not self._conn or not self._ready:
            raise RendererUnavailable("Màn hình host đã ngắt kết nối")

    def _prune(self) -> None:
        for d in (self._next_seq, self._first_playback):
            while len(d) > _KEEP_UTTERANCES:
                del d[next(iter(d))]

    def _set_lipsync_session(self, session: Any) -> None:
        # The fork's id is an opaque string (an upstream UUID); anything else from a buggy page is ignored.
        if session is not None and (not isinstance(session, str) or not session):
            return
        if session == self._lipsync_session:
            return
        self._lipsync_session = session
        for callback in list(self._session_callbacks):
            try:
                callback(session)
            except Exception:
                # One broken listener must not stop the host channel or the other listeners.
                logger.exception("lipsync session callback failed")

    def _drop_connection(self) -> None:
        was_ready = self._ready
        self._conn = None
        self._ready = False
        # The WebRTC session belonged to that page; a new page reports its own.
        self._set_lipsync_session(None)
        for fut in self._waiters.values():
            if not fut.done():
                fut.set_exception(RendererUnavailable("Màn hình host đã ngắt kết nối"))
        if was_ready:
            self._publish_connection(False)

    def _publish_connection(self, connected: bool) -> None:
        if self._bus is not None:
            self._bus.publish(Event(EventType.HOST_CONNECTION, {"connected": connected}))
