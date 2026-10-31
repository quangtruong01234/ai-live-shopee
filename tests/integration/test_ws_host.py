"""T035, T091: the `/ws/host` channel and `StaticRenderer` (FR-014, SC-007; contracts/api.md §4)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_live.app.main import create_app
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.core.events import EventBus
from ai_live.core.protocols import RendererUnavailable
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
