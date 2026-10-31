"""T076: the `avatar_first_frame` milestone in `StaticRenderer` (research R10).

`avatar_first_frame` = when the server receives the host's `playback_started` ack for sentence 0 of a turn. The renderer
exposes it through `first_playback_at(utterance_id)`; ShowDirector reads it right after the first `speak()` returns.
An injected clock makes every assertion exact, so nothing here depends on the Windows timer resolution.
"""

from __future__ import annotations

import asyncio

import anyio
import pytest

from ai_live.avatar import static_renderer
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.core.protocols import RendererUnavailable
from fixtures.fake_host import FakeHostConnection

pytestmark = pytest.mark.anyio

SAMPLE_RATE = 16000


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


async def _audio(chunks: int = 2):
    for _ in range(chunks):
        yield b"\x00\x00" * 160


async def _wait_until(predicate, timeout_s: float = 2.0) -> None:
    # Polling on purpose: the renderer has no event to await for "speak has sent sentence_start".
    with anyio.fail_after(timeout_s):
        while not predicate():  # noqa: ASYNC110
            await anyio.sleep(0.01)


async def _ready_renderer(*, auto_ack: bool, clock: FakeClock) -> tuple[StaticRenderer, FakeHostConnection]:
    renderer = StaticRenderer(ack_timeout_s=1.0, clock=clock)
    conn = FakeHostConnection(renderer, auto_ack=auto_ack)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    return renderer, conn


def _ack(renderer: StaticRenderer, conn: FakeHostConnection, kind: str, utterance_id: str, seq: int) -> None:
    renderer.handle_message(conn, {"type": kind, "utterance_id": utterance_id, "seq": seq})


async def test_milestone_is_the_clock_at_ack_arrival_not_at_speak_return():
    clock = FakeClock(100.0)
    renderer, conn = await _ready_renderer(auto_ack=False, clock=clock)
    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn Lan.", _audio(), SAMPLE_RATE))
    try:
        await _wait_until(lambda: len(conn.json_messages("sentence_end")) == 1)
        clock.now = 101.5  # audio sent, browser not playing yet
        assert renderer.first_playback_at("u1") is None

        clock.now = 102.0
        _ack(renderer, conn, "playback_started", "u1", 0)
        assert renderer.first_playback_at("u1") == 102.0

        clock.now = 105.0  # sentence finishes playing later; speak returns at this time
        _ack(renderer, conn, "sentence_played", "u1", 0)
        with anyio.fail_after(2):
            await task
    finally:
        task.cancel()
    assert renderer.first_playback_at("u1") == 102.0


async def test_only_the_first_sentence_ack_sets_the_milestone_and_nothing_overwrites_it():
    clock = FakeClock(10.0)
    renderer, conn = await _ready_renderer(auto_ack=False, clock=clock)
    task = asyncio.create_task(renderer.speak("u1", "Câu một.", _audio(), SAMPLE_RATE))
    try:
        await _wait_until(lambda: renderer.is_speaking)
        # An ack for a later sentence (out of order or bogus) is not the first frame.
        _ack(renderer, conn, "playback_started", "u1", 1)
        _ack(renderer, conn, "sentence_played", "u1", 0)
        assert renderer.first_playback_at("u1") is None
        assert not task.done()

        clock.now = 11.0
        _ack(renderer, conn, "playback_started", "u1", 0)
        clock.now = 12.0
        _ack(renderer, conn, "playback_started", "u1", 0)  # duplicate ack keeps the first time
        assert renderer.first_playback_at("u1") == 11.0
        with anyio.fail_after(2):
            await task
    finally:
        task.cancel()

    clock.now = 20.0
    conn.auto_ack = True
    with anyio.fail_after(2):
        await renderer.speak("u1", "Câu hai.", _audio(), SAMPLE_RATE)
    assert renderer.first_playback_at("u1") == 11.0


async def test_ack_for_an_utterance_never_spoken_is_ignored():
    clock = FakeClock(50.0)
    renderer, conn = await _ready_renderer(auto_ack=False, clock=clock)
    _ack(renderer, conn, "playback_started", "ghost", 0)
    assert renderer.first_playback_at("ghost") is None


async def test_ack_from_a_replaced_or_detached_connection_is_ignored():
    clock = FakeClock(1.0)
    renderer, old = await _ready_renderer(auto_ack=False, clock=clock)
    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn.", _audio(), SAMPLE_RATE))
    await _wait_until(lambda: renderer.is_speaking)

    new = FakeHostConnection(renderer, auto_ack=False)
    await renderer.attach(new)  # the old page is closed with 4000; its in-flight speak fails
    with pytest.raises(RendererUnavailable):
        with anyio.fail_after(2):
            await task
    _ack(renderer, old, "playback_started", "u1", 0)
    assert renderer.first_playback_at("u1") is None

    renderer.handle_message(new, {"type": "ready"})
    renderer.detach(new)
    _ack(renderer, new, "playback_started", "u1", 0)
    assert renderer.first_playback_at("u1") is None


async def test_pruning_keeps_the_previous_turn_until_the_director_has_read_it(monkeypatch):
    monkeypatch.setattr(static_renderer, "_KEEP_UTTERANCES", 3)
    clock = FakeClock(0.0)
    renderer, _conn = await _ready_renderer(auto_ack=True, clock=clock)
    for i in range(6):
        clock.now = float(i)
        with anyio.fail_after(2):
            await renderer.speak(f"u{i}", "Dạ.", _audio(1), SAMPLE_RATE)
        # ShowDirector reads the milestone right after the first sentence returns.
        assert renderer.first_playback_at(f"u{i}") == float(i)
        if i:
            # Starting a new turn prunes, but never the turn that just finished.
            assert renderer.first_playback_at(f"u{i - 1}") == float(i - 1)

    # Memory stays bounded on a 15-hour live: the oldest turns are gone.
    assert renderer.first_playback_at("u0") is None
    assert renderer.first_playback_at("u5") == 5.0


async def test_late_ack_for_a_pruned_utterance_does_not_come_back(monkeypatch):
    monkeypatch.setattr(static_renderer, "_KEEP_UTTERANCES", 1)
    clock = FakeClock(0.0)
    renderer, conn = await _ready_renderer(auto_ack=True, clock=clock)
    for uid in ("a", "b", "c"):
        with anyio.fail_after(2):
            await renderer.speak(uid, "Dạ.", _audio(1), SAMPLE_RATE)
    assert renderer.first_playback_at("a") is None

    clock.now = 99.0
    _ack(renderer, conn, "playback_started", "a", 0)
    assert renderer.first_playback_at("a") is None
