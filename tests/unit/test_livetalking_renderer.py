"""`LiveTalkingRenderer` against the fake fork: speaking path (005 T025) and errors / recovery (T048); adapters.md §3,
fork-protocol.md §1–§3."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import anyio
import pytest

from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.core.events import EventBus, EventType
from ai_live.core.protocols import RendererError, RendererUnavailable
from fixtures.fake_fork import FakeFork

pytestmark = pytest.mark.anyio

SAMPLE_RATE = 16000


def pcm(seconds: float) -> bytes:
    return b"\x01\x00" * round(seconds * SAMPLE_RATE)


async def audio(data: bytes, chunk: int = 3200) -> AsyncIterator[bytes]:
    for i in range(0, len(data), chunk):
        yield data[i : i + chunk]


class FakeHostLink:
    """The `/host` side as `LiveTalkingRenderer` sees it (contracts/adapters.md §5)."""

    def __init__(self, session: str | None = "sess-1") -> None:
        self.lipsync_session = session
        self.host_ready = True
        self.sent: list[dict[str, Any]] = []
        self._callbacks: list[Callable[[str | None], None]] = []

    async def send_to_host(self, message: dict[str, Any]) -> bool:
        self.sent.append(message)
        return True

    def on_session_change(self, callback: Callable[[str | None], None]) -> None:
        self._callbacks.append(callback)

    def set_session(self, session: str | None) -> None:
        self.lipsync_session = session
        for callback in self._callbacks:
            callback(session)

    def kinds(self) -> list[str]:
        return [m["type"] for m in self.sent]


MakeRenderer = Callable[..., Awaitable[tuple[LiveTalkingRenderer, FakeHostLink]]]


@pytest.fixture
async def fork() -> AsyncIterator[FakeFork]:
    async with FakeFork() as f:
        yield f


@pytest.fixture
async def make_renderer(fork: FakeFork) -> AsyncIterator[MakeRenderer]:
    made: list[LiveTalkingRenderer] = []

    async def factory(*, host: FakeHostLink | None = None, wait_ready: bool = True, **kwargs: Any):
        host = host or FakeHostLink()
        renderer = LiveTalkingRenderer(fork.url, host, **kwargs)
        made.append(renderer)
        await renderer.start()
        if wait_ready:
            await until(lambda: renderer.ready)
        return renderer, host

    yield factory
    for renderer in made:
        await renderer.stop()


async def until(predicate: Callable[[], bool], timeout_s: float = 3.0) -> None:
    # Polling on purpose: the fake fork exposes plain lists, not events.
    with anyio.fail_after(timeout_s):
        while not predicate():  # noqa: ASYNC110
            await anyio.sleep(0.01)


async def test_hello_makes_renderer_ready(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    bus = EventBus()
    sub = bus.subscribe()
    renderer, _ = await make_renderer(bus=bus)
    health = renderer.health
    assert health.connected is True
    assert (health.boot_id, health.fork_commit, health.session_id) == (fork.boot_id, "fakecommit0", "sess-1")
    events = [e for e in sub.drain() if e.type is EventType.LIPSYNC_HEALTH]
    assert events and events[-1].payload["connected"] is True


async def test_speak_before_ready_is_lipsync_unavailable(make_renderer: MakeRenderer) -> None:
    """No WebRTC session from the host page yet: the turn fails with a render error, not a hang."""
    renderer, _ = await make_renderer(host=FakeHostLink(session=None), wait_ready=False)
    with pytest.raises(RendererError) as info:
        await renderer.speak("u1", "Chào cả nhà.", audio(pcm(0.2)), SAMPLE_RATE)
    assert info.value.kind == "lipsync_unavailable"


async def test_speak_sends_sentence_to_fork(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    renderer, _ = await make_renderer()
    data = pcm(0.3)
    await renderer.speak("u1", "Chào cả nhà.", audio(data), SAMPLE_RATE)

    start = next(m for m in fork.received if m["type"] == "sentence_start")
    assert start == {
        "type": "sentence_start",
        "utterance_id": "u1",
        "seq": 0,
        "text": "Chào cả nhà.",
        "sample_rate": 16000,
    }
    assert any(m == {"type": "sentence_end", "utterance_id": "u1", "seq": 0} for m in fork.received)
    [sentence] = fork.sentences
    assert bytes(sentence.audio) == data


async def test_seq_counts_sentences_of_a_turn(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    renderer, _ = await make_renderer()
    for text in ("Câu một.", "Câu hai."):
        await renderer.speak("u1", text, audio(pcm(0.1)), SAMPLE_RATE)
    await renderer.speak("u2", "Lượt mới.", audio(pcm(0.1)), SAMPLE_RATE)
    assert [(s.utterance_id, s.seq) for s in fork.sentences] == [("u1", 0), ("u1", 1), ("u2", 0)]


async def test_subtitle_waits_for_playback_started(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """The subtitle shows when the mouth starts moving, not when the audio was sent."""
    fork.ack_delay_s = 0.3
    renderer, host = await make_renderer()
    async with anyio.create_task_group() as tg:
        tg.start_soon(renderer.speak, "u1", "Chào cả nhà.", audio(pcm(0.1)), SAMPLE_RATE)
        await until(lambda: len(fork.sentences) == 1)
        assert "subtitle" not in host.kinds()
    assert host.sent == [
        {"type": "subtitle", "utterance_id": "u1", "seq": 0, "text": "Chào cả nhà."},
        {"type": "subtitle_clear", "utterance_id": "u1", "seq": 0},
    ]


async def test_speak_returns_after_sentence_played(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.time_scale = 1.0
    renderer, _ = await make_renderer()
    t0 = time.monotonic()
    await renderer.speak("u1", "Dạ.", audio(pcm(0.4)), SAMPLE_RATE)
    assert time.monotonic() - t0 >= 0.35
    assert not renderer.is_speaking


async def test_first_playback_is_first_sentence_playback_started(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """FR-019: `avatar_first_frame` = when the fork reports the first lip-synced frame of the turn."""
    fork.ack_delay_s = 0.2
    renderer, _ = await make_renderer()
    t0 = time.monotonic()
    await renderer.speak("u1", "Câu một.", audio(pcm(0.1)), SAMPLE_RATE)
    first = renderer.first_playback_at("u1")
    assert first is not None and first - t0 >= 0.18
    await renderer.speak("u1", "Câu hai.", audio(pcm(0.1)), SAMPLE_RATE)
    assert renderer.first_playback_at("u1") == first
    stats = renderer.render_stats("u1")
    assert stats is not None and stats.first_frame_at == first
    assert renderer.first_playback_at("never") is None


async def test_render_stats_ready_when_speak_returns(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """The fork sends `stats` right after `sentence_played` (fork-protocol §2): a caller reading the turn's figures as
    soon as `speak` returns (speak-audio, the session log) must see that sentence counted."""
    fork.stats_delay_s = 0.05
    renderer, _ = await make_renderer()
    await renderer.speak("u1", "Dạ.", audio(pcm(0.4)), SAMPLE_RATE)
    stats = renderer.render_stats("u1")
    assert stats is not None and stats.frames == 10
    assert stats.clips_used == ["talk_01"]


async def test_missing_stats_does_not_fail_the_turn(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.stats_delay_s = 5.0
    renderer, _ = await make_renderer()
    t0 = time.monotonic()
    await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)
    assert time.monotonic() - t0 < 2.0
    stats = renderer.render_stats("u1")
    assert stats is not None and stats.frames == 0


async def test_no_playback_started_is_timeout(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.ack = False
    renderer, _ = await make_renderer(first_frame_timeout_s=0.3)
    t0 = time.monotonic()
    with pytest.raises(RendererError) as info:
        await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)
    assert info.value.kind == "timeout"
    assert time.monotonic() - t0 < 2.0


async def test_lead_returns_early_and_clears_subtitle_later(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """R15: with LIVETALKING_LEAD_S the next sentence is prepared while this one finishes playing."""
    fork.time_scale = 1.0
    renderer, host = await make_renderer(lead_s=0.6)
    t0 = time.monotonic()
    await renderer.speak("u1", "Dạ.", audio(pcm(1.0)), SAMPLE_RATE)
    elapsed = time.monotonic() - t0
    assert 0.3 <= elapsed < 0.8
    assert "subtitle_clear" not in host.kinds()
    await until(lambda: "subtitle_clear" in host.kinds())


async def test_render_stats_accumulate_over_turn(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """FR-020: frames, render fps, inference fps and talk clips per turn."""
    fork.time_scale = 1.0
    renderer, _ = await make_renderer()
    for text in ("Câu một.", "Câu hai."):
        await renderer.speak("u1", text, audio(pcm(0.4)), SAMPLE_RATE)
    await until(lambda: (renderer.render_stats("u1") or _no_stats()).frames == 20)
    stats = renderer.render_stats("u1")
    assert stats is not None
    assert stats.mode == "livetalking"
    assert stats.infer_fps == pytest.approx(30.0)
    assert stats.clips_used == ["talk_01"]
    assert stats.render_fps is not None and 15.0 <= stats.render_fps <= 27.0

    await renderer.speak("u2", "Lượt mới.", audio(pcm(0.2)), SAMPLE_RATE)
    await until(lambda: renderer.render_stats("u2") is not None and renderer.render_stats("u2").clips_used != [])
    assert renderer.render_stats("u2").clips_used == ["talk_02"]
    assert renderer.render_stats("never") is None


def _no_stats():
    class _Empty:
        frames = -1

    return _Empty()


async def test_fork_error_fails_turn_with_its_kind(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.fail_next("vram_oom", "CUDA out of memory")
    renderer, _ = await make_renderer()
    with pytest.raises(RendererError) as info:
        await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)
    assert info.value.kind == "vram_oom"
    assert renderer.health.last_error == "vram_oom"


async def test_disconnect_while_waiting_is_lipsync_unavailable(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.ack = False
    renderer, _ = await make_renderer()
    task = asyncio.create_task(renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE))
    await until(lambda: len(fork.sentences) == 1)
    await fork.disconnect()
    with pytest.raises(RendererError) as info:
        await task
    assert info.value.kind == "lipsync_unavailable"


async def test_speak_while_host_page_is_closed_is_host_unavailable(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """The page is gone, not the character: 001's `host_unavailable`, so the fallback counter ignores it (§5, R10)."""
    host = FakeHostLink()
    renderer, _ = await make_renderer(host=host)
    host.host_ready = False
    with pytest.raises(RendererUnavailable):
        await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)
    assert fork.sentences == []


async def test_host_page_closing_mid_sentence_is_host_unavailable(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.ack = False
    host = FakeHostLink()
    renderer, _ = await make_renderer(host=host)
    task = asyncio.create_task(renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE))
    await until(lambda: len(fork.sentences) == 1)
    # What `StaticRenderer.detach` does: the page is no longer ready and its WebRTC session is dropped.
    host.host_ready = False
    host.set_session(None)
    with pytest.raises(RendererUnavailable):
        await task


async def test_reconnects_after_fork_drop(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    renderer, _ = await make_renderer(reconnect_max_s=0.2)
    await fork.disconnect()
    await until(lambda: fork.connections == 2 and renderer.ready)
    await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)


async def test_follows_host_session_change(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """The host page re-offers WebRTC (new sessionid): the renderer reconnects to that session."""
    fork.sessions.add("sess-2")
    renderer, host = await make_renderer()
    host.set_session("sess-2")
    await until(lambda: renderer.health.session_id == "sess-2" and renderer.ready)


async def test_interrupt_stops_fork_and_host(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.time_scale = 1.0
    renderer, host = await make_renderer()
    t0 = time.monotonic()
    async with anyio.create_task_group() as tg:
        tg.start_soon(renderer.speak, "u1", "Dạ.", audio(pcm(3.0)), SAMPLE_RATE)
        await until(lambda: "subtitle" in host.kinds())
        await renderer.interrupt()
    assert time.monotonic() - t0 < 2.0
    assert fork.stopped == ["u1"]
    assert {"type": "stop", "utterance_id": "u1"} in host.sent
    assert not renderer.is_speaking


async def test_interrupt_when_idle_is_noop(make_renderer: MakeRenderer) -> None:
    renderer, _ = await make_renderer()
    await renderer.interrupt()
    await renderer.interrupt()


# ---------- Errors and recovery (T048; contracts/adapters.md §3, events.md §2, FR-016, FR-017, FR-021) ----------


def records(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, Any]]:
    return [getattr(r, "fields", {}) for r in caplog.records if r.getMessage() == event]


async def test_vram_oom_is_logged(
    fork: FakeFork, make_renderer: MakeRenderer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    fork.fail_next("vram_oom", "CUDA out of memory")
    renderer, _ = await make_renderer()
    with pytest.raises(RendererError):
        await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)
    [fields] = records(caplog, "lipsync_vram_oom")
    assert fields["utterance_id"] == "u1"


async def test_inference_error_kind_reaches_caller(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    fork.fail_next("inference_failed", "lỗi suy luận")
    renderer, _ = await make_renderer()
    with pytest.raises(RendererError) as info:
        await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)
    assert info.value.kind == "inference_failed"
    # Only that turn failed: the next one plays.
    await renderer.speak("u2", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)


async def test_drop_and_reconnect_are_logged(
    fork: FakeFork, make_renderer: MakeRenderer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    renderer, _ = await make_renderer(reconnect_max_s=0.2)
    assert len(records(caplog, "lipsync_connected")) == 1
    t0 = time.monotonic()
    await fork.disconnect()
    await until(lambda: len(records(caplog, "lipsync_connected")) == 2)
    assert time.monotonic() - t0 < 1.0  # first retry is capped by reconnect_max_s
    assert len(records(caplog, "lipsync_disconnected")) == 1
    assert records(caplog, "renderer_restarted") == []


async def test_speak_while_fork_is_gone_is_lipsync_unavailable(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    renderer, _ = await make_renderer(reconnect_max_s=0.2)
    await fork.stop()
    await until(lambda: not renderer.ready)
    assert renderer.health.connected is False
    with pytest.raises(RendererError) as info:
        await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)
    assert info.value.kind == "lipsync_unavailable"


async def test_fork_restart_is_logged_and_fails_waiting_turn(
    fork: FakeFork, make_renderer: MakeRenderer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    renderer, _ = await make_renderer(reconnect_max_s=0.2)
    old_boot = fork.boot_id
    await fork.restart()
    await until(lambda: renderer.ready and renderer.health.boot_id == fork.boot_id)
    [fields] = records(caplog, "renderer_restarted")
    assert fields == {"old_boot_id": old_boot, "new_boot_id": fork.boot_id}
    await renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE)


async def test_interrupt_ends_waiting_speak_at_once(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    """FR-016: a turn waiting for a fork that never acks ends as soon as the operator skips."""
    fork.ack = False
    renderer, _ = await make_renderer(first_frame_timeout_s=10.0)
    task = asyncio.create_task(renderer.speak("u1", "Dạ.", audio(pcm(0.1)), SAMPLE_RATE))
    await until(lambda: len(fork.sentences) == 1)
    t0 = time.monotonic()
    await renderer.interrupt()
    with anyio.fail_after(1.0):
        with contextlib.suppress(RendererError, asyncio.CancelledError):
            await task
    assert time.monotonic() - t0 < 1.0
    await until(lambda: fork.stopped == ["u1"])


async def test_health_message_publishes_lipsync_health(fork: FakeFork, make_renderer: MakeRenderer) -> None:
    bus = EventBus()
    sub = bus.subscribe()
    renderer, _ = await make_renderer(bus=bus)
    sub.drain()
    fork.vram_used_mb = 2656
    await fork.send_health()
    await until(lambda: renderer.health.vram_used_mb == 2656)
    events = [e.payload for e in sub.drain() if e.type is EventType.LIPSYNC_HEALTH]
    assert events and events[-1]["vram_used_mb"] == 2656
    assert events[-1]["infer_fps"] == pytest.approx(30.0)
