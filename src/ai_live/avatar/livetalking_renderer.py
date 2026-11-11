"""`livetalking` AvatarRenderer: feeds sentences to the LiveTalking fork, which lip-syncs them into WebRTC video (005).

The host page plays the fork's WebRTC stream itself; this side only talks to the fork's `/ailive/ws` (fork-protocol.md
§2–§3): it sends the PCM of each sentence and waits for the fork's `playback_started` / `sentence_played`, the same two
acks `StaticRenderer` gets from the browser. Subtitles still go to the host page, through the `HostLink`, timed to those
acks so the text appears when the mouth starts moving.

The socket is opened only once the host page reports a WebRTC `sessionid`, because the fork's session is tied to that
peer connection; a new `sessionid` (page reloaded, `/offer` redone) moves the socket to the new session.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from ai_live.avatar.static_renderer import HostLink
from ai_live.core.events import EventBus, lipsync_health_event
from ai_live.core.logging import log_event
from ai_live.core.models import LipsyncHealth, RenderTurnStats
from ai_live.core.protocols import RendererError, RendererUnavailable

logger = logging.getLogger("ai_live.avatar")

ForkConnector = Callable[..., Any]  # `websockets.asyncio.client.connect` or a test double; awaiting it opens the socket

_KEEP_UTTERANCES = 64
_FIRST_RETRY_S = 0.5
_OPEN_TIMEOUT_S = 5.0
# The fork sends `stats` right behind `sentence_played`; wait this long so callers reading the turn's figures when
# `speak` returns see the last sentence. Missing stats only cost figures, never the turn.
_STATS_GRACE_S = 0.5
_CONNECT_ERRORS = (OSError, TimeoutError, InvalidHandshake, InvalidURI, ConnectionClosed)
_UNAVAILABLE = "Chưa nối được phần nhép miệng (LiveTalking)"
_LOST = "Mất kết nối tới phần nhép miệng (LiveTalking)"
_HOST_NOT_READY = 'Chưa mở màn hình host hoặc chưa bấm "Bắt đầu"'
_HOST_LOST = "Màn hình host đã ngắt kết nối"


@dataclass
class _Turn:
    """Per-turn figures summed from the fork's per-sentence `stats` (FR-013, FR-020)."""

    first_frame_at: float | None = None
    last_played_at: float | None = None
    frames: int = 0
    infer_fps: list[float] = field(default_factory=list)
    clips_used: list[str] = field(default_factory=list)


class LiveTalkingRenderer:
    def __init__(
        self,
        base_url: str,
        host: HostLink,
        *,
        first_frame_timeout_s: float = 10.0,
        ack_timeout_s: float = 3.0,
        reconnect_max_s: float = 10.0,
        lead_s: float = 0.0,
        connect: ForkConnector = ws_connect,
        bus: EventBus | None = None,
        clock: Callable[[], float] = time.monotonic,
        expected_fork_commit: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.first_frame_timeout_s = first_frame_timeout_s
        self.ack_timeout_s = ack_timeout_s
        self.reconnect_max_s = reconnect_max_s
        self.lead_s = lead_s
        self._host = host
        self._connect = connect
        self._bus = bus
        self._clock = clock
        # The commit `prepare` ran with; a different running fork is only a warning (data-model §2).
        self._expected_fork_commit = expected_fork_commit
        self._ws: ClientConnection | None = None
        self._ready = False
        self._boot_id: str | None = None
        self._health = LipsyncHealth()
        self._session_changed = asyncio.Event()
        self._registered = False
        self._task: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[Any]] = set()
        self._next_seq: dict[str, int] = {}
        self._turns: dict[str, _Turn] = {}
        # Pending acks, keyed by (ack kind, utterance_id, seq).
        self._waiters: dict[tuple[str, str, int], asyncio.Future[None]] = {}
        # Unfinished sentences per turn; with `lead_s` a sentence keeps playing after `speak` returned.
        self._active: dict[str, int] = {}
        self._interrupted = False

    # ---------- Extra state ----------

    @property
    def ready(self) -> bool:
        return self._ready and self._ws is not None

    @property
    def health(self) -> LipsyncHealth:
        return self._health

    # ---------- AvatarRenderer ----------

    async def start(self) -> None:
        if not self._registered:
            self._host.on_session_change(self._on_session_change)
            self._registered = True
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="livetalking-link")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for bg in list(self._background):
            bg.cancel()
        await asyncio.gather(*self._background, return_exceptions=True)
        ws, self._ws = self._ws, None
        if ws is not None:
            await ws.close()
        self._fail_waiters(RendererError("lipsync_unavailable", _LOST))
        self._ready = False

    @property
    def is_speaking(self) -> bool:
        return bool(self._active)

    def first_playback_at(self, utterance_id: str) -> float | None:
        turn = self._turns.get(utterance_id)
        return turn.first_frame_at if turn else None

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None:
        turn = self._turns.get(utterance_id)
        if turn is None:
            return None
        render_fps = None
        if turn.first_frame_at is not None and turn.last_played_at is not None and turn.frames:
            elapsed = turn.last_played_at - turn.first_frame_at
            render_fps = turn.frames / elapsed if elapsed > 0 else None
        return RenderTurnStats(
            utterance_id=utterance_id,
            mode="livetalking",
            clips_used=list(turn.clips_used),
            frames=turn.frames,
            render_fps=render_fps,
            infer_fps=sum(turn.infer_fps) / len(turn.infer_fps) if turn.infer_fps else None,
            first_frame_at=turn.first_frame_at,
        )

    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None:
        # A closed host page drops the WebRTC session and with it the fork link: report the page, as 001 does,
        # so the fallback counter does not blame a healthy character (contracts/adapters.md §5, research R10).
        if not self._host.host_ready:
            raise RendererUnavailable(_HOST_NOT_READY)
        ws = self._ws
        if not self._ready or ws is None:
            raise RendererError("lipsync_unavailable", _UNAVAILABLE)
        seq = self._next_seq.get(utterance_id, 0)
        self._next_seq[utterance_id] = seq + 1
        if seq == 0:
            self._turns[utterance_id] = _Turn()
            self._prune()
        loop = asyncio.get_running_loop()
        started = self._waiters[("playback_started", utterance_id, seq)] = loop.create_future()
        played = self._waiters[("sentence_played", utterance_id, seq)] = loop.create_future()
        counted = self._waiters[("stats", utterance_id, seq)] = loop.create_future()
        self._active[utterance_id] = self._active.get(utterance_id, 0) + 1
        self._interrupted = False
        ids = {"utterance_id": utterance_id, "seq": seq}
        handed_off = False
        try:
            await ws.send(json.dumps({"type": "sentence_start", **ids, "text": text, "sample_rate": sample_rate}))
            audio_bytes = 0
            async for chunk in audio:
                if self._interrupted:
                    return
                await ws.send(chunk)
                audio_bytes += len(chunk)
            if self._interrupted:
                return
            await ws.send(json.dumps({"type": "sentence_end", **ids}))
            await self._wait(started, self.first_frame_timeout_s, "Phần nhép miệng không phát câu này kịp")
            if self._interrupted:
                return
            await self._host.send_to_host({"type": "subtitle", **ids, "text": text})
            duration_s = audio_bytes / 2 / sample_rate
            if self.lead_s > 0:
                # R15: hand back early so the next sentence's TTS overlaps the end of this one; the fork queues it.
                try:
                    await asyncio.wait_for(asyncio.shield(played), max(0.0, duration_s - self.lead_s))
                except TimeoutError:
                    handed_off = True
                    self._spawn(self._finish(utterance_id, seq, played, started, counted, duration_s))
                    return
            else:
                await self._wait(played, duration_s + self.ack_timeout_s, "Phần nhép miệng không báo phát xong câu")
            if not self._interrupted:
                await self._host.send_to_host({"type": "subtitle_clear", **ids})
                await asyncio.wait({counted}, timeout=_STATS_GRACE_S)  # never raises: stats are figures only
        except (ConnectionClosed, RendererError) as exc:
            if not self._host.host_ready:
                raise RendererUnavailable(_HOST_LOST) from exc
            if isinstance(exc, ConnectionClosed):
                raise RendererError("lipsync_unavailable", _LOST) from exc
            raise
        finally:
            if not handed_off:
                self._release(utterance_id, seq, started, played, counted)

    async def interrupt(self) -> None:
        # A repeated skip before `speak` has unwound must not send a second `stop`.
        if not self._active or self._interrupted:
            return
        self._interrupted = True
        for utterance_id in list(self._active):
            ws = self._ws
            if ws is not None:
                with contextlib.suppress(ConnectionClosed):
                    await ws.send(json.dumps({"type": "stop", "utterance_id": utterance_id}))
            await self._host.send_to_host({"type": "stop", "utterance_id": utterance_id})
            for (_, uid, _seq), fut in list(self._waiters.items()):
                if uid == utterance_id and not fut.done():
                    fut.set_result(None)

    # ---------- Speaking internals ----------

    async def _wait(self, fut: asyncio.Future[None], timeout_s: float, message: str) -> None:
        try:
            await asyncio.wait_for(fut, timeout_s)
        except TimeoutError as exc:
            raise RendererError("timeout", message) from exc

    async def _finish(
        self,
        utterance_id: str,
        seq: int,
        played: asyncio.Future[None],
        started: asyncio.Future[None],
        counted: asyncio.Future[None],
        duration_s: float,
    ) -> None:
        """Rest of a sentence `speak` handed back early: wait until it is played, then clear its subtitle."""
        try:
            await asyncio.wait_for(played, duration_s + self.ack_timeout_s)
            if not self._interrupted:
                await self._host.send_to_host({"type": "subtitle_clear", "utterance_id": utterance_id, "seq": seq})
        except (TimeoutError, RendererError) as exc:
            # Nobody awaits this sentence any more; the next one surfaces a dead fork through its own acks.
            log_event(
                logger,
                "lipsync_sentence_unfinished",
                logging.WARNING,
                utterance_id=utterance_id,
                seq=seq,
                error=str(exc),
            )
        finally:
            self._release(utterance_id, seq, started, played, counted)

    def _release(self, utterance_id: str, seq: int, *futures: asyncio.Future[None]) -> None:
        self._waiters.pop(("playback_started", utterance_id, seq), None)
        self._waiters.pop(("sentence_played", utterance_id, seq), None)
        self._waiters.pop(("stats", utterance_id, seq), None)
        for fut in futures:
            if not fut.done():
                fut.cancel()
            elif not fut.cancelled():
                # Mark the error as retrieved so a failed ack nobody waits for does not log "never retrieved".
                fut.exception()
        left = self._active.get(utterance_id, 0) - 1
        if left > 0:
            self._active[utterance_id] = left
        else:
            self._active.pop(utterance_id, None)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def _prune(self) -> None:
        for d in (self._next_seq, self._turns):
            while len(d) > _KEEP_UTTERANCES:
                del d[next(iter(d))]

    def _fail_waiters(self, error: RendererError, utterance_id: str | None = None) -> None:
        for (_, uid, _seq), fut in list(self._waiters.items()):
            if (utterance_id is None or uid == utterance_id) and not fut.done():
                fut.set_exception(error)

    # ---------- Fork link ----------

    def _ws_uri(self, session: str) -> str:
        base = self.base_url
        if base.startswith("https://"):
            base = "wss://" + base.removeprefix("https://")
        elif base.startswith("http://"):
            base = "ws://" + base.removeprefix("http://")
        return f"{base}/ailive/ws?sessionid={quote(session, safe='')}"

    def _on_session_change(self, session: str | None) -> None:
        self._session_changed.set()
        ws = self._ws
        if ws is not None:
            # The fork session belongs to the old peer connection; drop it so `_run` dials the new one.
            with contextlib.suppress(RuntimeError):
                self._spawn(ws.close())

    async def _run(self) -> None:
        retry_s = min(_FIRST_RETRY_S, self.reconnect_max_s)
        while True:
            session = self._host.lipsync_session
            self._session_changed.clear()
            if session is None:
                await self._session_changed.wait()
                continue
            try:
                ws = await self._connect(self._ws_uri(session), open_timeout=_OPEN_TIMEOUT_S)
            except _CONNECT_ERRORS as exc:
                log_event(logger, "lipsync_connect_failed", logging.WARNING, session_id=session, error=str(exc))
            else:
                retry_s = min(_FIRST_RETRY_S, self.reconnect_max_s)
                await self._serve(ws, session)
            if self._session_changed.is_set():
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._session_changed.wait(), retry_s)
            retry_s = min(retry_s * 2, self.reconnect_max_s)

    async def _serve(self, ws: ClientConnection, session: str) -> None:
        self._ws = ws
        reason = "closed"
        try:
            async for raw in ws:
                if isinstance(raw, str):
                    self._on_message(raw, session)
        except ConnectionClosed as exc:
            reason = f"closed {exc.rcvd.code if exc.rcvd else ''}".strip()
        finally:
            if self._ws is ws:
                self._ws = None
            was_ready, self._ready = self._ready, False
            self._fail_waiters(RendererError("lipsync_unavailable", _LOST))
            self._health = replace(self._health, connected=False, updated_at=datetime.now(UTC))
            if was_ready:
                log_event(logger, "lipsync_disconnected", logging.WARNING, reason=reason)
            self._publish_health()

    def _on_message(self, raw: str, session: str) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        kind = message.get("type")
        if kind == "hello":
            self._on_hello(message, session)
        elif kind in ("playback_started", "sentence_played"):
            self._on_ack(kind, message)
        elif kind == "stats":
            self._on_stats(message)
        elif kind == "health":
            self._health = replace(
                self._health,
                vram_used_mb=message.get("vram_used_mb"),
                infer_fps=message.get("infer_fps"),
                updated_at=datetime.now(UTC),
            )
            self._publish_health()
        elif kind == "error":
            self._on_error(message)

    def _on_hello(self, message: dict[str, Any], session: str) -> None:
        boot_id = message.get("boot_id")
        fork_commit = message.get("fork_commit")
        if self._boot_id is not None and boot_id != self._boot_id:
            log_event(logger, "renderer_restarted", logging.WARNING, old_boot_id=self._boot_id, new_boot_id=boot_id)
            self._fail_waiters(RendererError("renderer_restarted", "Phần nhép miệng vừa khởi động lại"))
        self._boot_id = boot_id
        if self._expected_fork_commit and fork_commit and fork_commit != self._expected_fork_commit:
            log_event(
                logger,
                "avatar_prepared_with_other_fork",
                logging.WARNING,
                prepared_commit=self._expected_fork_commit,
                running_commit=fork_commit,
            )
        self._ready = True
        self._health = replace(
            self._health,
            connected=True,
            boot_id=boot_id,
            fork_commit=fork_commit,
            session_id=message.get("sessionid", session),
            updated_at=datetime.now(UTC),
        )
        log_event(
            logger, "lipsync_connected", boot_id=boot_id, fork_commit=fork_commit, session_id=self._health.session_id
        )
        self._publish_health()

    def _on_ack(self, kind: str, message: dict[str, Any]) -> None:
        utterance_id, seq = message.get("utterance_id"), message.get("seq")
        if not isinstance(utterance_id, str) or not isinstance(seq, int):
            return
        turn = self._turns.get(utterance_id)
        # Only a turn this renderer sent counts: a late ack must not create a milestone for a pruned turn.
        if turn is not None:
            now = self._clock()
            if kind == "playback_started" and seq == 0 and turn.first_frame_at is None:
                turn.first_frame_at = now
            elif kind == "sentence_played":
                turn.last_played_at = now
        fut = self._waiters.get((kind, utterance_id, seq))
        if fut is not None and not fut.done():
            fut.set_result(None)

    def _on_stats(self, message: dict[str, Any]) -> None:
        utterance_id, seq = message.get("utterance_id"), message.get("seq")
        turn = self._turns.get(utterance_id)  # type: ignore[arg-type]
        if turn is None:
            return
        fut = self._waiters.get(("stats", utterance_id, seq))  # type: ignore[arg-type]
        if fut is not None and not fut.done():
            fut.set_result(None)
        frames = message.get("frames")
        if isinstance(frames, int):
            turn.frames += frames
        infer_fps = message.get("infer_fps")
        if isinstance(infer_fps, int | float):
            turn.infer_fps.append(float(infer_fps))
        clip_id = message.get("clip_id")
        if isinstance(clip_id, str) and clip_id not in turn.clips_used:
            turn.clips_used.append(clip_id)

    def _on_error(self, message: dict[str, Any]) -> None:
        kind = str(message.get("kind") or "inference_failed")
        text = str(message.get("message") or kind)
        utterance_id = message.get("utterance_id")
        self._health = replace(self._health, last_error=kind, updated_at=datetime.now(UTC))
        if kind == "vram_oom":
            log_event(
                logger,
                "lipsync_vram_oom",
                logging.ERROR,
                utterance_id=utterance_id,
                vram_peak_mb=message.get("vram_peak_mb"),
            )
        else:
            log_event(logger, "lipsync_error", logging.WARNING, kind=kind, utterance_id=utterance_id)
        self._fail_waiters(RendererError(kind, text), utterance_id if isinstance(utterance_id, str) else None)
        self._publish_health()

    def _publish_health(self) -> None:
        if self._bus is not None:
            self._bus.publish(lipsync_health_event(self._health))
