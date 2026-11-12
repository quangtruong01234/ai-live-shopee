"""Fake LiveTalking fork for tests (005 contracts/fork-protocol.md §1–§3, T014).

A real `websockets` server on 127.0.0.1 with a random port, so `LiveTalkingRenderer` is tested over the same transport
it uses against the real fork, without a GPU. It answers `/ailive/ws` and `GET /ailive/health` like the fork: `hello`
on connect, then `playback_started`, `sentence_played` and `stats` per sentence, timed to the audio length.

Test controls (plain attributes, change them at any time):
- `time_scale`: playback time = audio length x this (0 = instant, the default keeps tests fast).
- `ack_delay_s`: extra wait before `playback_started`.
- `ack`: False = take sentences but never ack them (first-frame timeout).
- `fail_next(kind, message)`: answer the next finished sentence with `error {kind}` instead of acks.
- `disconnect()`: drop the app connection; `restart()`: new `boot_id`, then drop (the app sees a fork restart).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from itertools import cycle
from typing import Any
from urllib.parse import parse_qs, urlsplit

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

SAMPLE_RATE = 16000
CLOSE_UNKNOWN_SESSION = 4404


@dataclass
class ReceivedSentence:
    utterance_id: str
    seq: int
    text: str
    sample_rate: int
    audio: bytearray = field(default_factory=bytearray)
    clip_id: str = ""

    @property
    def duration_s(self) -> float:
        return len(self.audio) / 2 / SAMPLE_RATE


class FakeFork:
    def __init__(
        self,
        *,
        session_id: str = "sess-1",
        fork_commit: str = "fakecommit0",
        fps: int = 25,
        batch_size: int = 16,
        lip_every_n: int = 1,
        ai_label: str = "AI",
        talk_clips: tuple[str, ...] = ("talk_01", "talk_02"),
        infer_fps: float = 30.0,
        vram_used_mb: int = 2100,
        health_interval_s: float = 5.0,
    ) -> None:
        self.sessions: set[str] = {session_id}
        self.boot_id = uuid.uuid4().hex
        self.fork_commit = fork_commit
        self.fps = fps
        self.batch_size = batch_size
        self.lip_every_n = lip_every_n
        self.ai_label = ai_label
        self.infer_fps = infer_fps
        self.vram_used_mb = vram_used_mb
        self.vram_peak_mb = vram_used_mb
        self.health_interval_s = health_interval_s
        # Test controls
        self.time_scale = 0.0
        self.ack_delay_s = 0.0
        self.stats_delay_s = 0.0  # gap between `sentence_played` and `stats`, as on a busy real fork
        self.ack = True
        self._fail: list[tuple[str, str]] = []
        # What the fork saw, for assertions
        self.received: list[dict[str, Any]] = []
        self.sentences: list[ReceivedSentence] = []
        self.stopped: list[str] = []
        self.connections = 0
        self._clips = cycle(talk_clips)
        self._turn_clip: dict[str, str] = {}
        self._server: Server | None = None
        self._conn: ServerConnection | None = None
        self.port = 0

    # ---------- Lifecycle ----------

    async def start(self) -> FakeFork:
        self._server = await serve(self._handle, "127.0.0.1", 0, process_request=self._process_request)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> FakeFork:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    @property
    def url(self) -> str:
        """Value for `LIVETALKING_URL`."""
        return f"http://127.0.0.1:{self.port}"

    @property
    def connected(self) -> bool:
        return self._conn is not None

    # ---------- Test controls ----------

    def fail_next(self, kind: str, message: str = "lỗi giả") -> None:
        self._fail.append((kind, message))

    async def disconnect(self, code: int = 1011) -> None:
        if self._conn is not None:
            await self._conn.close(code, "fake fork disconnect")

    async def restart(self) -> None:
        """Simulate a fork process restart: the next `hello` carries a new `boot_id`."""
        self.boot_id = uuid.uuid4().hex
        self._turn_clip.clear()
        await self.disconnect()

    async def send(self, message: dict[str, Any]) -> None:
        """Push any message (e.g. an unsolicited `error` or `health`) to the connected app."""
        if self._conn is not None:
            await self._conn.send(json.dumps(message))

    async def send_health(self) -> None:
        await self.send(
            {
                "type": "health",
                "vram_used_mb": self.vram_used_mb,
                "vram_peak_mb": self.vram_peak_mb,
                "infer_fps": self.infer_fps,
            }
        )

    def health_body(self) -> dict[str, Any]:
        return {
            "ok": True,
            "boot_id": self.boot_id,
            "fork_commit": self.fork_commit,
            "sessions": sorted(self.sessions),
            "vram_used_mb": self.vram_used_mb,
        }

    # ---------- Server ----------

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        path = urlsplit(request.path).path
        if path == "/ailive/health":
            body = json.dumps(self.health_body()).encode()
            return Response(HTTPStatus.OK, "OK", Headers([("Content-Type", "application/json")]), body)
        if path == "/ailive/ws":
            return None
        return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")

    async def _handle(self, ws: ServerConnection) -> None:
        query = parse_qs(urlsplit(ws.request.path).query)
        session = query.get("sessionid", [""])[0]
        if session not in self.sessions:
            await ws.close(CLOSE_UNKNOWN_SESSION, "unknown session")
            return
        self.connections += 1
        self._conn = ws
        playlist: asyncio.Queue[ReceivedSentence] = asyncio.Queue()
        player = asyncio.create_task(self._play(ws, playlist))
        health = asyncio.create_task(self._health_loop(ws))
        current: ReceivedSentence | None = None
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "boot_id": self.boot_id,
                        "fork_commit": self.fork_commit,
                        "sessionid": session,
                        "fps": self.fps,
                        "batch_size": self.batch_size,
                        "lip_every_n": self.lip_every_n,
                        "ai_label": self.ai_label,
                    }
                )
            )
            async for raw in ws:
                if isinstance(raw, bytes):
                    if current is not None:
                        current.audio += raw
                    continue
                message = json.loads(raw)
                self.received.append(message)
                kind = message.get("type")
                if kind == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                elif kind == "sentence_start":
                    current = self._start_sentence(message)
                    if current.sample_rate != SAMPLE_RATE:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "error",
                                    "kind": "bad_audio",
                                    "message": f"sample_rate {current.sample_rate} != {SAMPLE_RATE}",
                                    "utterance_id": current.utterance_id,
                                }
                            )
                        )
                        current = None
                elif kind == "sentence_end":
                    if current is not None and (current.utterance_id, current.seq) == (
                        message.get("utterance_id"),
                        message.get("seq"),
                    ):
                        self.sentences.append(current)
                        playlist.put_nowait(current)
                    current = None
                elif kind == "stop":
                    uid = message.get("utterance_id")
                    self.stopped.append(uid)
                    current = None
                    # Drop queued sentences of the stopped turn and cut the one playing (no `sentence_played`).
                    kept = [s for s in _drain(playlist) if s.utterance_id != uid]
                    for s in kept:
                        playlist.put_nowait(s)
                    player.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await player
                    player = asyncio.create_task(self._play(ws, playlist))
        except ConnectionClosed:
            pass
        finally:
            for task in (player, health):
                task.cancel()
            await asyncio.gather(player, health, return_exceptions=True)
            if self._conn is ws:
                self._conn = None

    def _start_sentence(self, message: dict[str, Any]) -> ReceivedSentence:
        uid = str(message.get("utterance_id"))
        seq = int(message.get("seq", 0))
        # Simplified: one talk clip per turn, picked at seq 0. The real fork also keeps it across turns inside its hold
        # and rotates per clip cycle (fork-protocol §4); app tests only need a clip_id that changes between turns.
        if seq == 0 or uid not in self._turn_clip:
            self._turn_clip[uid] = next(self._clips)
        return ReceivedSentence(
            utterance_id=uid,
            seq=seq,
            text=str(message.get("text", "")),
            sample_rate=int(message.get("sample_rate", 0)),
            clip_id=self._turn_clip[uid],
        )

    async def _play(self, ws: ServerConnection, playlist: asyncio.Queue[ReceivedSentence]) -> None:
        with contextlib.suppress(ConnectionClosed):
            while True:
                sentence = await playlist.get()
                ids = {"utterance_id": sentence.utterance_id, "seq": sentence.seq}
                if self._fail:
                    kind, message = self._fail.pop(0)
                    await ws.send(
                        json.dumps(
                            {"type": "error", "kind": kind, "message": message, "utterance_id": sentence.utterance_id}
                        )
                    )
                    continue
                if not self.ack:
                    continue
                if self.ack_delay_s:
                    await asyncio.sleep(self.ack_delay_s)
                await ws.send(json.dumps({"type": "playback_started", **ids}))
                await asyncio.sleep(sentence.duration_s * self.time_scale)
                await ws.send(json.dumps({"type": "sentence_played", **ids}))
                if self.stats_delay_s:
                    await asyncio.sleep(self.stats_delay_s)
                await ws.send(
                    json.dumps(
                        {
                            "type": "stats",
                            **ids,
                            "frames": round(sentence.duration_s * self.fps),
                            "infer_fps": self.infer_fps,
                            "render_fps": float(self.fps),
                            "clip_id": sentence.clip_id,
                        }
                    )
                )

    async def _health_loop(self, ws: ServerConnection) -> None:
        with contextlib.suppress(ConnectionClosed):
            while True:
                await asyncio.sleep(self.health_interval_s)
                await ws.send(
                    json.dumps(
                        {
                            "type": "health",
                            "vram_used_mb": self.vram_used_mb,
                            "vram_peak_mb": self.vram_peak_mb,
                            "infer_fps": self.infer_fps,
                        }
                    )
                )


def _drain(queue: asyncio.Queue[ReceivedSentence]) -> list[ReceivedSentence]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items
