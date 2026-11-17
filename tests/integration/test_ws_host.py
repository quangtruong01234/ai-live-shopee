"""T035, T091: the `/ws/host` channel and `StaticRenderer` (FR-014, SC-007; contracts/api.md §4)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_live.app.main import create_app
from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from ai_live.core.events import EventBus, EventType
from ai_live.core.protocols import RendererUnavailable
from fixtures.fake_fork import FakeFork
from fixtures.fake_host import FakeHostConnection


async def _audio(*chunks: bytes):
    for c in chunks:
        yield c


# --- Through the real app (TestClient) ---


def test_new_host_connection_closes_old_with_4000(app_settings):
    with TestClient(create_app(app_settings)) as client:
        with client.websocket_connect("/ws/host") as first:
            first.send_json({"type": "ready"})
            with client.websocket_connect("/ws/host") as second:
                with pytest.raises(WebSocketDisconnect) as exc:
                    first.receive_json()
                assert exc.value.code == 4000
                second.send_json({"type": "ready"})
                assert client.get("/health").json()["host_connected"] is True


def test_host_connected_only_after_ready(app_settings):
    with TestClient(create_app(app_settings)) as client:
        assert client.get("/health").json()["host_connected"] is False
        with client.websocket_connect("/ws/host") as host:
            assert client.get("/health").json()["host_connected"] is False
            host.send_json({"type": "ready"})
            # The ack goes through the app event loop; a later HTTP call is enough for `ready` to have been handled.
            for _ in range(50):
                if client.get("/health").json()["host_connected"]:
                    break
            assert client.get("/health").json()["host_connected"] is True
        assert client.get("/health").json()["host_connected"] is False


# --- StaticRenderer behaviour with a fake host ---


@pytest.mark.anyio
async def test_speak_before_ready_raises_renderer_unavailable():
    renderer = StaticRenderer(ack_timeout_s=0.5)
    with pytest.raises(RendererUnavailable):
        await renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 10), 16000)

    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    # Connected but "Bắt đầu" not clicked yet: still counts as no host.
    with pytest.raises(RendererUnavailable):
        await renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 10), 16000)


@pytest.mark.anyio
async def test_speak_sends_start_pcm_end_and_returns_after_played():
    bus = EventBus()
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=bus)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    assert renderer.host_ready

    await renderer.speak("u1", "Dạ chào bạn Lan.", _audio(b"\x01\x00" * 800, b"\x02\x00" * 400), 16000)
    await renderer.speak("u1", "Kem giá 250.000đ nha.", _audio(b"\x03\x00" * 800), 16000)

    kinds = ["pcm" if isinstance(m, bytes) else m["type"] for m in conn.sent]
    assert kinds == ["sentence_start", "pcm", "pcm", "sentence_end", "sentence_start", "pcm", "sentence_end"]
    starts = conn.json_messages("sentence_start")
    assert starts[0] == {
        "type": "sentence_start",
        "utterance_id": "u1",
        "seq": 0,
        "text": "Dạ chào bạn Lan.",
        "sample_rate": 16000,
    }
    assert starts[1]["seq"] == 1 and starts[1]["text"] == "Kem giá 250.000đ nha."
    assert conn.json_messages("sentence_end")[1] == {"type": "sentence_end", "utterance_id": "u1", "seq": 1}
    assert renderer.first_playback_at("u1") is not None
    assert not renderer.is_speaking


@pytest.mark.anyio
async def test_speak_waits_for_sentence_played():
    renderer = StaticRenderer(ack_timeout_s=1.0)
    conn = FakeHostConnection(renderer, auto_ack=False)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})

    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 160), 16000))
    await asyncio.sleep(0.05)
    assert not task.done()
    assert renderer.is_speaking
    renderer.handle_message(conn, {"type": "playback_started", "utterance_id": "u1", "seq": 0})
    await asyncio.sleep(0.05)
    assert not task.done()
    renderer.handle_message(conn, {"type": "sentence_played", "utterance_id": "u1", "seq": 0})
    await asyncio.wait_for(task, 1.0)
    assert not renderer.is_speaking


@pytest.mark.anyio
async def test_speak_times_out_without_playback_started():
    renderer = StaticRenderer(ack_timeout_s=0.1)
    conn = FakeHostConnection(renderer, auto_ack=False)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    with pytest.raises(TimeoutError):
        await renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 160), 16000)
    assert not renderer.is_speaking


@pytest.mark.anyio
async def test_host_disconnect_during_speak_raises_renderer_unavailable():
    renderer = StaticRenderer(ack_timeout_s=1.0)
    conn = FakeHostConnection(renderer, auto_ack=False)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 160), 16000))
    await asyncio.sleep(0.05)
    renderer.detach(conn)
    with pytest.raises(RendererUnavailable):
        await asyncio.wait_for(task, 1.0)
    assert not renderer.host_ready


@pytest.mark.anyio
async def test_attach_new_connection_closes_old_with_4000():
    bus = EventBus()
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=bus)
    async with bus.subscribe() as sub:
        old = FakeHostConnection(renderer)
        await renderer.attach(old)
        renderer.handle_message(old, {"type": "ready"})
        new = FakeHostConnection(renderer)
        await renderer.attach(new)
        assert old.closed_code == 4000
        assert not renderer.host_ready
        # Messages from the old connection are ignored.
        renderer.handle_message(old, {"type": "ready"})
        assert not renderer.host_ready
        renderer.handle_message(new, {"type": "ready"})
        assert renderer.host_ready
        events = [e for e in sub.drain() if e.type == "host_connection"]
    assert [e.payload["connected"] for e in events] == [True, False, True]


@pytest.mark.anyio
async def test_interrupt_sends_stop_and_releases_speak():
    renderer = StaticRenderer(ack_timeout_s=1.0)
    conn = FakeHostConnection(renderer, auto_ack=False)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 160), 16000))
    await asyncio.sleep(0.05)
    await renderer.interrupt()
    await asyncio.wait_for(task, 1.0)
    assert conn.json_messages("stop") == [{"type": "stop", "utterance_id": "u1"}]
    assert not renderer.is_speaking


@pytest.mark.anyio
async def test_interrupt_is_fast_and_idempotent():
    """T091 (SC-007): `stop` reaches the host within 1 s, and a repeated skip sends no second `stop`."""
    renderer = StaticRenderer(ack_timeout_s=5.0)
    conn = FakeHostConnection(renderer, auto_ack=False)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 16000), 16000))
    await asyncio.sleep(0.05)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await renderer.interrupt()
    await renderer.interrupt()
    await asyncio.wait_for(task, 1.0)
    assert loop.time() - t0 < 1.0
    await renderer.interrupt()
    assert conn.json_messages("stop") == [{"type": "stop", "utterance_id": "u1"}]


@pytest.mark.anyio
async def test_interrupt_when_idle_sends_nothing():
    renderer = StaticRenderer(ack_timeout_s=1.0)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    await renderer.interrupt()
    assert conn.json_messages("stop") == []


# --- Feature 005: StaticRenderer as HostLink (contracts/adapters.md §5, api.md §4, T013) ---


@pytest.mark.anyio
async def test_ready_with_lipsync_session_sets_session_and_calls_back():
    renderer = StaticRenderer(ack_timeout_s=0.5)
    seen: list[str | None] = []
    renderer.on_session_change(seen.append)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    assert renderer.lipsync_session is None

    renderer.handle_message(conn, {"type": "ready", "lipsync_session": "s7"})
    assert renderer.host_ready
    assert renderer.lipsync_session == "s7"
    assert seen == ["s7"]


@pytest.mark.anyio
async def test_standalone_lipsync_session_message_updates_session():
    renderer = StaticRenderer(ack_timeout_s=0.5)
    seen: list[str | None] = []
    renderer.on_session_change(seen.append)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready", "lipsync_session": "s7"})

    # The host page redid /offer (after `mode` or a lost WebRTC link) and reports the new session.
    renderer.handle_message(conn, {"type": "lipsync_session", "session": "s9"})
    assert renderer.lipsync_session == "s9"
    # Same value again is not a change; null means the new /offer failed.
    renderer.handle_message(conn, {"type": "lipsync_session", "session": "s9"})
    renderer.handle_message(conn, {"type": "lipsync_session", "session": None})
    assert renderer.lipsync_session is None
    assert seen == ["s7", "s9", None]


@pytest.mark.anyio
async def test_lipsync_session_ignores_bad_values_and_other_connections():
    renderer = StaticRenderer(ack_timeout_s=0.5)
    conn = FakeHostConnection(renderer)
    stranger = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready", "lipsync_session": "s7"})

    renderer.handle_message(conn, {"type": "lipsync_session", "session": 8})
    renderer.handle_message(conn, {"type": "lipsync_session", "session": ""})
    renderer.handle_message(conn, {"type": "lipsync_session", "session": True})
    renderer.handle_message(stranger, {"type": "lipsync_session", "session": "s5"})
    assert renderer.lipsync_session == "s7"


@pytest.mark.anyio
async def test_ready_without_lipsync_session_behaves_as_before():
    bus = EventBus()
    sub = bus.subscribe()
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=bus)
    seen: list[str | None] = []
    renderer.on_session_change(seen.append)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)

    renderer.handle_message(conn, {"type": "ready"})
    assert renderer.host_ready
    assert renderer.lipsync_session is None
    assert seen == []
    assert [e.payload for e in sub.drain()] == [{"connected": True, "role": "host"}]

    await renderer.speak("u1", "Dạ chào bạn.", _audio(b"\x00\x00" * 160), 16000)
    assert [m["type"] for m in conn.json_messages()] == ["sentence_start", "sentence_end"]


@pytest.mark.anyio
async def test_send_to_host_forwards_message():
    renderer = StaticRenderer(ack_timeout_s=0.5)
    assert await renderer.send_to_host({"type": "mode", "mode": "static"}) is False

    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    assert await renderer.send_to_host({"type": "subtitle", "utterance_id": "u1", "text": "Dạ."}) is True
    assert conn.json_messages("subtitle") == [{"type": "subtitle", "utterance_id": "u1", "text": "Dạ."}]


@pytest.mark.anyio
async def test_detach_resets_lipsync_session():
    renderer = StaticRenderer(ack_timeout_s=0.5)
    seen: list[str | None] = []
    renderer.on_session_change(seen.append)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready", "lipsync_session": "s7"})

    renderer.detach(conn)
    assert renderer.lipsync_session is None
    assert seen == ["s7", None]
    assert await renderer.send_to_host({"type": "mode", "mode": "static"}) is False


# --- Feature 005 US2: `mode`, `subtitle`, `subtitle_clear` on the host channel (contracts/api.md §4, T053) ---


def _switching(fork: FakeFork) -> SwitchingRenderer:
    static = StaticRenderer(ack_timeout_s=1.0)
    lipsync = LiveTalkingRenderer(fork.url, static, first_frame_timeout_s=1.0, ack_timeout_s=1.0, reconnect_max_s=0.2)
    return SwitchingRenderer(lipsync, static, fallback_after=2)


async def _wait(predicate, timeout_s: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition not met in time"
        await asyncio.sleep(0.01)


async def _lipsync_host(renderer: SwitchingRenderer) -> FakeHostConnection:
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready", "lipsync_session": "sess-1"})
    await _wait(lambda: renderer.lipsync.ready)
    return conn


@pytest.mark.anyio
async def test_host_gets_mode_static_before_the_fallback_turn_and_livetalking_on_enable():
    async with FakeFork() as fork:
        renderer = _switching(fork)
        await renderer.start()
        try:
            conn = await _lipsync_host(renderer)
            renderer.record_render_outcome("u1", False, error_kind="lipsync_unavailable")
            assert conn.json_messages("mode") == []
            renderer.record_render_outcome("u2", False, error_kind="lipsync_unavailable")

            # The next turn is on the still image: the page switches picture before its first sentence arrives.
            await renderer.speak("u3", "Dạ chào bạn.", _audio(b"\x00\x00" * 160), 16000)
            types = [m["type"] for m in conn.json_messages()]
            assert types.index("mode") < types.index("sentence_start")
            assert conn.json_messages("mode") == [{"type": "mode", "mode": "static", "reason": "render_errors"}]
            assert conn.audio_bytes() > 0

            # The operator switches back: the page hears it before `enable_lipsync` returns.
            await renderer.enable_lipsync()
            assert conn.json_messages("mode")[-1] == {"type": "mode", "mode": "livetalking", "reason": None}
            # Already on lip-sync: a second press sends nothing new.
            await renderer.enable_lipsync()
            assert len(conn.json_messages("mode")) == 2
        finally:
            await renderer.stop()


@pytest.mark.anyio
async def test_lipsync_subtitle_and_clear_arrive_in_sentence_order():
    async with FakeFork() as fork:
        renderer = _switching(fork)
        await renderer.start()
        try:
            conn = await _lipsync_host(renderer)
            for text in ("Dạ chào bạn.", "Hôm nay mình giới thiệu áo."):
                await renderer.speak("u1", text, _audio(b"\x00\x00" * 1600), 16000)
            subs = [
                (m["type"], m["seq"], m.get("text"))
                for m in conn.json_messages()
                if m["type"] in ("subtitle", "subtitle_clear")
            ]
            assert subs == [
                ("subtitle", 0, "Dạ chào bạn."),
                ("subtitle_clear", 0, None),
                ("subtitle", 1, "Hôm nay mình giới thiệu áo."),
                ("subtitle_clear", 1, None),
            ]
            # On lip-sync the fork speaks: the page gets no `sentence_start` and no audio of its own.
            assert conn.json_messages("sentence_start") == [] and conn.audio_bytes() == 0
            assert {m["utterance_id"] for m in conn.json_messages("subtitle")} == {"u1"}
        finally:
            await renderer.stop()


# --- 007 T014: the host tab's `host_status` heartbeat (007 contracts/api.md §4, data-model §2) ---


@pytest.mark.anyio
async def test_host_status_from_current_tab_reaches_the_bus():
    bus = EventBus()
    sub = bus.subscribe()
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=bus, clock=lambda: 42.0)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    sub.drain()
    renderer.handle_message(
        conn,
        {
            "type": "host_status",
            "frames": 1834,
            "audio": "running",
            "video_muted": False,
            "video_paused": False,
            "visible": False,
        },
    )
    events = [e for e in sub.drain() if e.type is EventType.HOST_STATUS]
    assert [e.payload for e in events] == [
        {
            "frames": 1834,
            "audio": "running",
            "video_muted": False,
            "video_paused": False,
            "visible": False,
            "received_at": 42.0,
        }
    ]
    # The app never answers a heartbeat.
    assert not [m for m in conn.json_messages() if m.get("type") == "host_status"]


@pytest.mark.anyio
async def test_host_status_missing_or_wrong_fields_become_null():
    bus = EventBus()
    sub = bus.subscribe()
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=bus, clock=lambda: 1.0)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    renderer.handle_message(conn, {"type": "ready"})
    renderer.handle_message(
        conn, {"type": "host_status", "frames": "12", "audio": "loud", "video_muted": 1, "visible": True}
    )
    renderer.handle_message(conn, {"type": "host_status", "frames": True})
    payloads = [e.payload for e in sub.drain() if e.type is EventType.HOST_STATUS]
    assert payloads[0] == {
        "frames": None,
        "audio": None,
        "video_muted": None,
        "video_paused": None,
        "visible": True,
        "received_at": 1.0,
    }
    # A bool is an int in Python; a frame count must be a real number of frames.
    assert payloads[1]["frames"] is None


@pytest.mark.anyio
async def test_renderer_keeps_last_host_status_until_the_tab_goes():
    # The readiness check reads it without subscribing to the bus (007 data-model §1 `host`).
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=None, clock=lambda: 3.0)
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    assert renderer.host_status is None
    renderer.handle_message(conn, {"type": "host_status", "frames": None, "audio": "suspended"})
    renderer.handle_message(conn, {"type": "host_status", "frames": None, "audio": "running"})
    assert renderer.host_status is not None and renderer.host_status.audio == "running"
    renderer.detach(conn)
    assert renderer.host_status is None


@pytest.mark.anyio
async def test_host_status_from_replaced_tab_is_ignored():
    bus = EventBus()
    sub = bus.subscribe()
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=bus)
    old = FakeHostConnection(renderer)
    await renderer.attach(old)
    new = FakeHostConnection(renderer)
    await renderer.attach(new)
    renderer.handle_message(old, {"type": "host_status", "frames": 5, "audio": "running"})
    assert not [e for e in sub.drain() if e.type is EventType.HOST_STATUS]


def test_control_page_does_not_get_host_status(app_settings):
    with TestClient(create_app(app_settings)) as client:
        with client.websocket_connect("/ws/control") as control, client.websocket_connect("/ws/host") as host:
            assert control.receive_json()["type"] == "state"
            host.send_json({"type": "ready"})
            assert control.receive_json()["type"] == "host_connection"
            host.send_json({"type": "host_status", "frames": None, "audio": "running"})
            # Anything published after the heartbeat proves the heartbeat was skipped, not just late.
            client.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu?"})
            assert control.receive_json()["type"] == "comment_accepted"
