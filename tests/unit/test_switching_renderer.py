"""`SwitchingRenderer` pass-through, per-turn routing (005 T026) and the fallback counter (T049;
contracts/adapters.md §4, data-model §4, FR-022)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
import pytest

from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from ai_live.core.events import EventBus, EventType
from ai_live.core.models import RenderTurnStats
from fixtures.fake_host import FakeHostConnection

pytestmark = pytest.mark.anyio

SAMPLE_RATE = 16000


async def audio(chunks: int = 2) -> AsyncIterator[bytes]:
    for _ in range(chunks):
        yield b"\x00\x00" * 160


class FakeLipsync:
    """Stands in for `LiveTalkingRenderer`: records calls, always plays at once."""

    ack_timeout_s = 7.0

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []
        self.interrupts = 0
        self.started = 0
        self.stopped = 0
        self.speaking = False
        self._first: dict[str, float] = {}

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None:
        async for _ in audio:
            pass
        self.spoken.append((utterance_id, text))
        self._first.setdefault(utterance_id, 123.0)

    async def interrupt(self) -> None:
        self.interrupts += 1

    @property
    def is_speaking(self) -> bool:
        return self.speaking

    def first_playback_at(self, utterance_id: str) -> float | None:
        return self._first.get(utterance_id)

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None:
        if utterance_id not in self._first:
            return None
        return RenderTurnStats(utterance_id=utterance_id, mode="livetalking", frames=50)


async def make(
    configured: str = "livetalking", *, bus: EventBus | None = None
) -> tuple[SwitchingRenderer, FakeLipsync, StaticRenderer, Any]:
    lipsync = FakeLipsync()
    static = StaticRenderer(ack_timeout_s=2.0)
    renderer = SwitchingRenderer(lipsync, static, configured=configured, bus=bus)
    await renderer.start()
    conn = FakeHostConnection(renderer, auto_ack=True)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready", "lipsync_session": "sess-1"})
    return renderer, lipsync, static, conn


async def test_host_channel_goes_to_static() -> None:
    renderer, lipsync, static, conn = await make()
    assert static.host_ready and renderer.host_ready
    assert static.lipsync_session == "sess-1"
    renderer.detach(conn)
    assert not static.host_ready and not renderer.host_ready
    assert static.lipsync_session is None


async def test_start_and_stop_reach_both() -> None:
    renderer, lipsync, _, _ = await make()
    assert lipsync.started == 1
    await renderer.stop()
    assert lipsync.stopped == 1


async def test_ack_timeout_follows_active_renderer() -> None:
    renderer, _, static, _ = await make()
    assert renderer.ack_timeout_s == FakeLipsync.ack_timeout_s
    renderer_static, _, static2, _ = await make("static")
    assert renderer_static.ack_timeout_s == static2.ack_timeout_s


async def test_livetalking_turn_uses_lipsync() -> None:
    renderer, lipsync, _, conn = await make()
    await renderer.speak("u1", "Câu một.", audio(), SAMPLE_RATE)
    await renderer.speak("u1", "Câu hai.", audio(), SAMPLE_RATE)
    assert lipsync.spoken == [("u1", "Câu một."), ("u1", "Câu hai.")]
    assert conn.json_messages("sentence_start") == []
    assert renderer.first_playback_at("u1") == 123.0
    stats = renderer.render_stats("u1")
    assert stats is not None and stats.mode == "livetalking"
    assert renderer.mode.configured == "livetalking" and renderer.mode.active == "livetalking"


async def test_turn_keeps_renderer_chosen_at_first_sentence() -> None:
    """A mode change applies from the next turn; the turn being spoken stays on its renderer (data-model §4)."""
    renderer, lipsync, _, conn = await make()
    await renderer.speak("u1", "Câu một.", audio(), SAMPLE_RATE)
    renderer._activate("static", "render_errors")
    await renderer.speak("u1", "Câu hai.", audio(), SAMPLE_RATE)
    assert [text for _, text in lipsync.spoken] == ["Câu một.", "Câu hai."]
    await renderer.speak("u2", "Lượt mới.", audio(), SAMPLE_RATE)
    assert [m["utterance_id"] for m in conn.json_messages("sentence_start")] == ["u2"]
    assert renderer.render_stats("u2") is None
    assert renderer.render_stats("u1") is not None


async def test_static_mode_routes_everything_to_static() -> None:
    renderer, lipsync, static, conn = await make("static")
    with anyio.fail_after(2):
        await renderer.speak("u1", "Câu một.", audio(), SAMPLE_RATE)
        await renderer.speak("u1", "Câu hai.", audio(), SAMPLE_RATE)
    assert lipsync.spoken == []
    assert [m["text"] for m in conn.json_messages("sentence_start")] == ["Câu một.", "Câu hai."]
    assert renderer.first_playback_at("u1") == static.first_playback_at("u1")
    assert renderer.mode.configured == "static" and renderer.mode.active == "static"


async def test_interrupt_reaches_both_and_is_speaking_covers_both() -> None:
    renderer, lipsync, _, _ = await make()
    assert not renderer.is_speaking
    lipsync.speaking = True
    assert renderer.is_speaking
    await renderer.interrupt()
    assert lipsync.interrupts == 1


# ---------- Fallback counter (T049, data-model §4, FR-022) ----------


async def until(predicate: Callable[[], bool], timeout_s: float = 2.0) -> None:
    with anyio.fail_after(timeout_s):
        while not predicate():  # noqa: ASYNC110
            await anyio.sleep(0.01)


def mode_events(sub: Any) -> list[dict[str, Any]]:
    return [e.payload for e in sub.drain() if e.type is EventType.AVATAR_MODE]


async def test_one_error_turn_does_not_switch() -> None:
    renderer, lipsync, _, conn = await make()
    renderer.record_render_outcome("u1", False, error_kind="timeout")
    assert renderer.mode.active == "livetalking"
    assert renderer.mode.consecutive_errors == 1
    await renderer.speak("u2", "Câu.", audio(), SAMPLE_RATE)
    assert lipsync.spoken == [("u2", "Câu.")]
    assert conn.json_messages("mode") == []


async def test_two_error_turns_switch_to_static_from_next_turn(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    bus = EventBus()
    sub = bus.subscribe()
    renderer, lipsync, _, conn = await make(bus=bus)
    assert mode_events(sub)[-1]["active"] == "livetalking"  # published once at start

    await renderer.speak("u1", "Câu.", audio(), SAMPLE_RATE)
    renderer.record_render_outcome("u1", False, error_kind="lipsync_unavailable")
    renderer.record_render_outcome("u2", False, error_kind="vram_oom")

    state = renderer.mode
    assert (state.active, state.reason, state.consecutive_errors) == ("static", "render_errors", 2)
    assert state.changed_at is not None
    [event] = mode_events(sub)
    assert event["active"] == "static" and event["reason"] == "render_errors"
    await until(lambda: conn.json_messages("mode") != [])
    assert conn.json_messages("mode") == [{"type": "mode", "mode": "static", "reason": "render_errors"}]
    [record] = [r for r in caplog.records if r.getMessage() == "avatar_fallback"]
    assert record.fields == {"utterance_id": "u2", "consecutive_errors": 2, "last_error_kind": "vram_oom"}

    # The turn already on lip-sync keeps it; the next turn goes to the still image.
    await renderer.speak("u1", "Câu hai.", audio(), SAMPLE_RATE)
    with anyio.fail_after(2):
        await renderer.speak("u3", "Lượt mới.", audio(), SAMPLE_RATE)
    assert [uid for uid, _ in lipsync.spoken] == ["u1", "u1"]
    assert [m["utterance_id"] for m in conn.json_messages("sentence_start")] == ["u3"]


async def test_many_sentences_of_one_turn_count_once() -> None:
    renderer, _, _, _ = await make()
    for _ in range(3):
        renderer.record_render_outcome("u1", False, error_kind="timeout")
    assert renderer.mode.consecutive_errors == 1
    assert renderer.mode.active == "livetalking"


async def test_ok_turn_resets_counter() -> None:
    renderer, _, _, _ = await make()
    renderer.record_render_outcome("u1", False, error_kind="timeout")
    renderer.record_render_outcome("u2", True)
    renderer.record_render_outcome("u3", False, error_kind="timeout")
    assert renderer.mode.consecutive_errors == 1
    assert renderer.mode.active == "livetalking"


async def test_host_unavailable_turns_do_not_count() -> None:
    """Closing the host page twice must not drop a healthy character to the still image (data-model §4)."""
    renderer, _, _, conn = await make()
    renderer.record_render_outcome("u1", False, error_kind="timeout")
    for uid in ("u2", "u3"):
        renderer.record_render_outcome(uid, False, error_kind="host_unavailable")
    assert renderer.mode.active == "livetalking"
    assert renderer.mode.consecutive_errors == 1
    assert conn.json_messages("mode") == []


async def test_static_errors_after_fallback_do_not_count() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    renderer, _, _, _ = await make(bus=bus)
    for uid in ("u1", "u2"):
        renderer.record_render_outcome(uid, False, error_kind="timeout")
    sub.drain()
    for uid in ("u3", "u4", "u5"):
        renderer.record_render_outcome(uid, False, error_kind="host_unavailable")
    assert renderer.mode.consecutive_errors == 2
    assert mode_events(sub) == []


async def test_enable_lipsync_returns_to_livetalking(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    bus = EventBus()
    sub = bus.subscribe()
    renderer, lipsync, _, conn = await make(bus=bus)
    for uid in ("u1", "u2"):
        renderer.record_render_outcome(uid, False, error_kind="timeout")
    sub.drain()

    state = await renderer.enable_lipsync()
    assert (state.active, state.reason, state.consecutive_errors) == ("livetalking", None, 0)
    assert mode_events(sub)[-1]["active"] == "livetalking"
    await until(lambda: len(conn.json_messages("mode")) == 2)
    assert conn.json_messages("mode")[-1] == {"type": "mode", "mode": "livetalking", "reason": None}
    [record] = [r for r in caplog.records if r.getMessage() == "avatar_lipsync_enabled"]
    assert record.fields == {"by": "operator"}

    await renderer.speak("u3", "Lại nhép miệng.", audio(), SAMPLE_RATE)
    assert lipsync.spoken == [("u3", "Lại nhép miệng.")]
    # Counting starts again from zero: one more error does not switch.
    renderer.record_render_outcome("u4", False, error_kind="timeout")
    assert renderer.mode.active == "livetalking"


async def test_enable_lipsync_when_already_livetalking_keeps_mode() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    renderer, _, _, conn = await make(bus=bus)
    renderer.record_render_outcome("u1", False, error_kind="timeout")
    sub.drain()
    state = await renderer.enable_lipsync()
    assert state.active == "livetalking" and state.consecutive_errors == 0
    assert conn.json_messages("mode") == []


async def test_enable_lipsync_in_static_configuration_is_value_error() -> None:
    renderer, _, _, _ = await make("static")
    with pytest.raises(ValueError):
        await renderer.enable_lipsync()


async def test_static_configuration_does_not_count() -> None:
    renderer, _, _, _ = await make("static")
    for uid in ("u1", "u2", "u3"):
        renderer.record_render_outcome(uid, False, error_kind="host_unavailable")
    assert renderer.mode.consecutive_errors == 0
    assert renderer.mode.active == "static" and renderer.mode.reason is None
