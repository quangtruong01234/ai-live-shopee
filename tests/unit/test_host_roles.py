"""006 T003, T013: who holds the playing `/ws/host` connection, `obs` > `host` (data-model §2, contracts/api.md §2)."""

from __future__ import annotations

import asyncio

import pytest

from ai_live.avatar.static_renderer import CLOSE_REPLACED, CLOSE_YIELDED, StaticRenderer
from ai_live.core.events import EventBus, EventType
from ai_live.core.protocols import RendererUnavailable
from fixtures.fake_host import FakeHostConnection


def _renderer() -> tuple[StaticRenderer, list[dict]]:
    bus = EventBus()
    renderer = StaticRenderer(ack_timeout_s=0.5, bus=bus)
    events: list[dict] = []
    original = bus.publish

    def record(event):
        if event.type is EventType.HOST_CONNECTION:
            events.append(dict(event.payload))
        original(event)

    bus.publish = record  # type: ignore[method-assign]
    return renderer, events


async def _attach_ready(renderer: StaticRenderer, role: str, **kwargs) -> FakeHostConnection:
    conn = FakeHostConnection(renderer, **kwargs)
    assert await renderer.attach(conn, role) is True
    renderer.handle_message(conn, {"type": "ready"})
    return conn


async def _audio(*chunks: bytes):
    for c in chunks:
        yield c


# ---------- Transition table (data-model §2) ----------


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["obs", "host"])
async def test_first_connection_plays(role):
    renderer, events = _renderer()
    conn = await _attach_ready(renderer, role)
    assert renderer.host_role == role
    assert renderer.host_ready is True
    assert conn.closed_code is None
    assert events == [{"connected": True, "role": role}]


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["obs", "host"])
async def test_same_role_newest_wins_with_4000(role):
    renderer, _ = _renderer()
    old = await _attach_ready(renderer, role)
    new = await _attach_ready(renderer, role)
    assert old.closed_code == CLOSE_REPLACED
    assert new.closed_code is None
    assert renderer.host_role == role


@pytest.mark.anyio
async def test_obs_takes_over_host_with_4001():
    renderer, events = _renderer()
    host = await _attach_ready(renderer, "host")
    obs = await _attach_ready(renderer, "obs")
    assert host.closed_code == CLOSE_YIELDED
    assert host.closed_reason == "obs_active"
    assert obs.closed_code is None
    assert renderer.host_role == "obs"
    assert events == [
        {"connected": True, "role": "host"},
        {"connected": False, "role": None},
        {"connected": True, "role": "obs"},
    ]


@pytest.mark.anyio
async def test_host_is_refused_while_obs_plays():
    renderer, events = _renderer()
    obs = await _attach_ready(renderer, "obs")
    host = FakeHostConnection(renderer)
    assert await renderer.attach(host, "host") is False
    assert host.closed_code == CLOSE_YIELDED
    assert host.closed_reason == "obs_active"
    assert obs.closed_code is None
    assert renderer.host_role == "obs"
    # A refused connection is ignored: its messages change nothing and publish nothing.
    renderer.handle_message(host, {"type": "ready"})
    renderer.handle_message(host, {"type": "playback_started", "utterance_id": "u1", "seq": 0})
    renderer.detach(host)
    assert renderer.host_role == "obs"
    assert renderer.host_ready is True
    assert events == [{"connected": True, "role": "obs"}]


@pytest.mark.anyio
async def test_role_none_when_playing_connection_closes():
    renderer, events = _renderer()
    obs = await _attach_ready(renderer, "obs")
    renderer.detach(obs)
    assert renderer.host_role is None
    assert renderer.host_ready is False
    assert events[-1] == {"connected": False, "role": None}


@pytest.mark.anyio
async def test_role_set_before_ready_but_not_published():
    renderer, events = _renderer()
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn, "obs")
    assert renderer.host_role == "obs"
    assert renderer.host_ready is False
    assert events == []


@pytest.mark.anyio
async def test_yielded_host_does_not_come_back_when_obs_closes():
    renderer, _ = _renderer()
    host = await _attach_ready(renderer, "host")
    obs = await _attach_ready(renderer, "obs")
    renderer.detach(obs)
    # The yielded page was closed; it only plays again if the operator reloads it (a new connection).
    renderer.handle_message(host, {"type": "ready"})
    assert renderer.host_role is None
    assert renderer.host_ready is False


@pytest.mark.anyio
async def test_unknown_role_counts_as_host():
    renderer, _ = _renderer()
    await _attach_ready(renderer, "obs")
    other = FakeHostConnection(renderer)
    assert await renderer.attach(other, "camera") is False
    assert other.closed_code == CLOSE_YIELDED


@pytest.mark.anyio
async def test_default_role_is_host():
    renderer, _ = _renderer()
    conn = FakeHostConnection(renderer)
    await renderer.attach(conn)
    assert renderer.host_role == "host"


# ---------- T013: a full sequence and a takeover mid-sentence ----------


@pytest.mark.anyio
async def test_sequence_host_obs_host_new_obs_close():
    renderer, _ = _renderer()
    host1 = await _attach_ready(renderer, "host")
    obs1 = await _attach_ready(renderer, "obs")
    assert (host1.closed_code, renderer.host_role) == (CLOSE_YIELDED, "obs")
    host2 = FakeHostConnection(renderer)
    assert await renderer.attach(host2, "host") is False
    assert (host2.closed_code, renderer.host_role) == (CLOSE_YIELDED, "obs")
    obs2 = await _attach_ready(renderer, "obs")
    assert (obs1.closed_code, obs2.closed_code, renderer.host_role) == (CLOSE_REPLACED, None, "obs")
    renderer.detach(obs2)
    assert renderer.host_role is None


@pytest.mark.anyio
async def test_takeover_mid_sentence_fails_cleanly_then_next_sentence_plays_on_obs():
    renderer, _ = _renderer()
    # The host page never acks, so the sentence is still waiting when OBS takes over.
    host = await _attach_ready(renderer, "host", auto_ack=False)
    speaking = asyncio.create_task(renderer.speak("u1", "Câu một.", _audio(b"\x00" * 3200), 16000))
    for _ in range(20):
        if host.json_messages("sentence_start"):
            break
        await asyncio.sleep(0.01)
    obs = await _attach_ready(renderer, "obs")
    with pytest.raises(RendererUnavailable):
        await asyncio.wait_for(speaking, 1)
    assert renderer.is_speaking is False
    await asyncio.wait_for(renderer.speak("u2", "Câu hai.", _audio(b"\x00" * 3200), 16000), 1)
    assert [m["utterance_id"] for m in obs.json_messages("sentence_start")] == ["u2"]
    assert host.json_messages("sentence_start")[-1]["utterance_id"] == "u1"
