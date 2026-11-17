"""009 T007: renderers tell `PlaybackListener`s when a sentence is really heard (contracts/adapters.md §1, FR-016).

Started at the playback ack (not when the audio is sent), ended at `sentence_played`, stopped on interrupt. A listener
that raises is logged and never breaks the turn; a repeated ack does not fire twice.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
import pytest

from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from fixtures.fake_fork import FakeFork
from fixtures.fake_host import FakeHostConnection

pytestmark = pytest.mark.anyio

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def playback_started(self, utterance_id: str, seq: int, text: str) -> None:
        self.calls.append(("started", utterance_id, seq, text))

    def playback_ended(self, utterance_id: str, seq: int) -> None:
        self.calls.append(("ended", utterance_id, seq))

    def playback_stopped(self) -> None:
        self.calls.append(("stopped",))


class Broken:
    def playback_started(self, utterance_id: str, seq: int, text: str) -> None:
        raise RuntimeError("scene broke")

    def playback_ended(self, utterance_id: str, seq: int) -> None:
        raise RuntimeError("scene broke")

    def playback_stopped(self) -> None:
        raise RuntimeError("scene broke")


async def audio(chunks: int = 2) -> AsyncIterator[bytes]:
    for _ in range(chunks):
        yield b"\x00\x00" * 160


async def until(predicate: Callable[[], bool], timeout_s: float = 3.0) -> None:
    # Polling on purpose: the fakes expose plain lists, not events.
    with anyio.fail_after(timeout_s):
        while not predicate():  # noqa: ASYNC110
            await anyio.sleep(0.01)


async def static_renderer(*, auto_ack: bool = True) -> tuple[StaticRenderer, FakeHostConnection]:
    renderer = StaticRenderer(ack_timeout_s=2.0)
    conn = FakeHostConnection(renderer, auto_ack=auto_ack)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    return renderer, conn


# ---------- StaticRenderer ----------


async def test_static_reports_started_and_ended() -> None:
    renderer, _ = await static_renderer()
    rec = Recorder()
    renderer.add_playback_listener(rec)
    await renderer.speak("u1", "Câu một.", audio(), SAMPLE_RATE)
    await renderer.speak("u1", "Câu hai.", audio(), SAMPLE_RATE)
    assert rec.calls == [
        ("started", "u1", 0, "Câu một."),
        ("ended", "u1", 0),
        ("started", "u1", 1, "Câu hai."),
        ("ended", "u1", 1),
    ]


async def test_static_started_waits_for_the_ack() -> None:
    renderer, conn = await static_renderer(auto_ack=False)
    rec = Recorder()
    renderer.add_playback_listener(rec)
    task = asyncio.create_task(renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE))
    await until(lambda: bool(conn.json_messages("sentence_end")))
    assert rec.calls == []  # audio sent, nothing heard yet
    renderer.handle_message(conn, {"type": "playback_started", "utterance_id": "u1", "seq": 0})
    assert rec.calls == [("started", "u1", 0, "Dạ.")]
    # A repeated ack (a page that re-sends) must not move the scene again.
    renderer.handle_message(conn, {"type": "playback_started", "utterance_id": "u1", "seq": 0})
    renderer.handle_message(conn, {"type": "sentence_played", "utterance_id": "u1", "seq": 0})
    renderer.handle_message(conn, {"type": "sentence_played", "utterance_id": "u1", "seq": 0})
    await task
    assert rec.calls == [("started", "u1", 0, "Dạ."), ("ended", "u1", 0)]


async def test_static_ack_for_unknown_sentence_is_ignored() -> None:
    renderer, conn = await static_renderer()
    rec = Recorder()
    renderer.add_playback_listener(rec)
    renderer.handle_message(conn, {"type": "playback_started", "utterance_id": "ghost", "seq": 0})
    assert rec.calls == []


async def test_static_interrupt_reports_stopped() -> None:
    renderer, conn = await static_renderer(auto_ack=False)
    rec = Recorder()
    renderer.add_playback_listener(rec)
    task = asyncio.create_task(renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE))
    await until(lambda: bool(conn.json_messages("sentence_end")))
    await renderer.interrupt()
    await task
    assert rec.calls[-1] == ("stopped",)


async def test_broken_listener_does_not_break_the_turn(caplog: pytest.LogCaptureFixture) -> None:
    renderer, _ = await static_renderer()
    rec = Recorder()
    renderer.add_playback_listener(Broken())
    renderer.add_playback_listener(rec)
    with caplog.at_level(logging.ERROR, logger="ai_live.avatar"):
        await renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE)
    # The good listener after the broken one still hears everything.
    assert rec.calls == [("started", "u1", 0, "Dạ."), ("ended", "u1", 0)]
    assert any(r.getMessage() == "playback listener failed" for r in caplog.records)


async def test_same_listener_added_twice_hears_once() -> None:
    renderer, _ = await static_renderer()
    rec = Recorder()
    renderer.add_playback_listener(rec)
    renderer.add_playback_listener(rec)
    await renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE)
    assert [c[0] for c in rec.calls] == ["started", "ended"]


# ---------- LiveTalkingRenderer ----------


class HostLink:
    def __init__(self) -> None:
        self.lipsync_session: str | None = "sess-1"
        self.host_ready = True
        self.sent: list[dict[str, Any]] = []

    async def send_to_host(self, message: dict[str, Any]) -> bool:
        self.sent.append(message)
        return True

    def on_session_change(self, callback: Callable[[str | None], None]) -> None:
        pass


@pytest.fixture
async def fork() -> AsyncIterator[FakeFork]:
    async with FakeFork() as f:
        yield f


async def test_livetalking_reports_started_and_ended(fork: FakeFork) -> None:
    host = HostLink()
    renderer = LiveTalkingRenderer(fork.url, host)
    rec = Recorder()
    renderer.add_playback_listener(rec)
    await renderer.start()
    try:
        await until(lambda: renderer.ready)
        await renderer.speak("u1", "Chào cả nhà.", audio(), SAMPLE_RATE)
        assert rec.calls == [("started", "u1", 0, "Chào cả nhà."), ("ended", "u1", 0)]
        # Started goes with the subtitle, i.e. at the fork's `playback_started`.
        assert [m["type"] for m in host.sent] == ["subtitle", "subtitle_clear"]
    finally:
        await renderer.stop()


async def test_livetalking_broken_listener_does_not_break_the_turn(fork: FakeFork) -> None:
    renderer = LiveTalkingRenderer(fork.url, HostLink())
    renderer.add_playback_listener(Broken())
    await renderer.start()
    try:
        await until(lambda: renderer.ready)
        await renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE)
        assert not renderer.is_speaking
    finally:
        await renderer.stop()


async def test_livetalking_interrupt_reports_stopped(fork: FakeFork) -> None:
    fork.ack_delay_s = 5.0
    renderer = LiveTalkingRenderer(fork.url, HostLink())
    rec = Recorder()
    renderer.add_playback_listener(rec)
    await renderer.start()
    try:
        await until(lambda: renderer.ready)
        task = asyncio.create_task(renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE))
        await until(lambda: len(fork.sentences) == 1)
        await renderer.interrupt()
        await task
        assert rec.calls == [("stopped",)]
    finally:
        await renderer.stop()


# ---------- SwitchingRenderer ----------


async def test_switching_registers_on_both(fork: FakeFork) -> None:
    lipsync = LiveTalkingRenderer(fork.url, HostLink())
    static = StaticRenderer(ack_timeout_s=2.0)
    renderer = SwitchingRenderer(lipsync, static, configured="static")
    rec = Recorder()
    renderer.add_playback_listener(rec)
    await renderer.start()
    try:
        conn = FakeHostConnection(renderer, auto_ack=True)
        await renderer.attach(conn)
        renderer.handle_message(conn, {"type": "ready"})
        await renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE)
        assert rec.calls == [("started", "u1", 0, "Dạ."), ("ended", "u1", 0)]
        # The lip-sync renderer got the same listener, so a turn routed there reports too.
        assert rec in lipsync._playback._listeners
    finally:
        await renderer.stop()
