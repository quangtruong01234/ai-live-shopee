"""Self-check of the fake fork (T014) against contracts/fork-protocol.md §1–§3, so US1 tests can trust it."""

from __future__ import annotations

import json
import urllib.request

import anyio
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from fixtures.fake_fork import CLOSE_UNKNOWN_SESSION, FakeFork

pytestmark = pytest.mark.anyio

PCM_100MS = b"\x01\x00" * 1600


def _ws_url(fork: FakeFork, session: str = "sess-1") -> str:
    return f"ws://127.0.0.1:{fork.port}/ailive/ws?sessionid={session}"


async def _recv(ws) -> dict:
    with anyio.fail_after(2):
        return json.loads(await ws.recv())


async def _until(ws, kind: str) -> dict:
    while True:
        message = await _recv(ws)
        if message["type"] == kind:
            return message


async def _send_sentence(ws, uid: str, seq: int, sample_rate: int = 16000) -> None:
    await ws.send(
        json.dumps(
            {"type": "sentence_start", "utterance_id": uid, "seq": seq, "text": "Dạ.", "sample_rate": sample_rate}
        )
    )
    await ws.send(PCM_100MS)
    await ws.send(json.dumps({"type": "sentence_end", "utterance_id": uid, "seq": seq}))


async def test_health_endpoint():
    async with FakeFork() as fork:
        body = await anyio.to_thread.run_sync(
            lambda: json.loads(urllib.request.urlopen(f"{fork.url}/ailive/health", timeout=2).read())
        )
    assert body["ok"] is True
    assert body["boot_id"] == fork.boot_id
    assert body["sessions"] == ["sess-1"]


async def test_hello_then_acks_and_stats_in_order():
    async with FakeFork() as fork, connect(_ws_url(fork)) as ws:
        hello = await _recv(ws)
        assert hello["type"] == "hello"
        assert hello["boot_id"] == fork.boot_id
        assert hello["sessionid"] == "sess-1"
        await _send_sentence(ws, "u1", 0)
        kinds = [(await _recv(ws))["type"] for _ in range(3)]
        assert kinds == ["playback_started", "sentence_played", "stats"]
        assert fork.sentences[0].duration_s == pytest.approx(0.1)


async def test_clip_kept_within_turn_and_changed_at_new_turn():
    async with FakeFork() as fork, connect(_ws_url(fork)) as ws:
        await _recv(ws)
        clips = []
        for uid, seq in (("u1", 0), ("u1", 1), ("u2", 0)):
            await _send_sentence(ws, uid, seq)
            stats = await _until(ws, "stats")
            assert stats["frames"] == 2  # 0.1 s at 25 fps, rounded
            clips.append(stats["clip_id"])
    assert clips[0] == clips[1]
    assert clips[2] != clips[1]


async def test_wrong_session_closes_4404():
    async with FakeFork() as fork, connect(_ws_url(fork, session="other")) as ws:
        with pytest.raises(ConnectionClosed) as exc:
            await _recv(ws)
    assert exc.value.rcvd.code == CLOSE_UNKNOWN_SESSION


async def test_ping_pong_error_and_bad_audio():
    async with FakeFork() as fork, connect(_ws_url(fork)) as ws:
        await _recv(ws)
        await ws.send(json.dumps({"type": "ping"}))
        assert (await _recv(ws))["type"] == "pong"
        fork.fail_next("vram_oom", "CUDA out of memory")
        await _send_sentence(ws, "u1", 0)
        error = await _recv(ws)
        assert (error["type"], error["kind"], error["utterance_id"]) == ("error", "vram_oom", "u1")
        await _send_sentence(ws, "u2", 0, sample_rate=24000)
        assert (await _recv(ws))["kind"] == "bad_audio"


async def test_no_ack_and_ack_delay():
    async with FakeFork() as fork, connect(_ws_url(fork)) as ws:
        await _recv(ws)
        fork.ack = False
        await _send_sentence(ws, "u1", 0)
        with pytest.raises(TimeoutError):
            with anyio.fail_after(0.3):
                await ws.recv()
        fork.ack = True
        fork.ack_delay_s = 0.2
        start = anyio.current_time()
        await _send_sentence(ws, "u2", 0)
        assert (await _recv(ws))["type"] == "playback_started"
        assert anyio.current_time() - start >= 0.19


async def test_stop_cuts_sentence_without_played():
    async with FakeFork() as fork, connect(_ws_url(fork)) as ws:
        await _recv(ws)
        fork.time_scale = 50.0  # 0.1 s of audio plays for 5 s
        await _send_sentence(ws, "u1", 0)
        assert (await _recv(ws))["type"] == "playback_started"
        await ws.send(json.dumps({"type": "stop", "utterance_id": "u1"}))
        with pytest.raises(TimeoutError):
            with anyio.fail_after(0.3):
                await ws.recv()
        assert fork.stopped == ["u1"]


async def test_restart_changes_boot_id_on_reconnect():
    async with FakeFork(health_interval_s=0.05) as fork:
        async with connect(_ws_url(fork)) as ws:
            first = (await _recv(ws))["boot_id"]
            assert (await _recv(ws))["type"] == "health"
            await fork.restart()
            with pytest.raises(ConnectionClosed):
                while True:
                    await _recv(ws)
        async with connect(_ws_url(fork)) as ws:
            second = (await _recv(ws))["boot_id"]
    assert first != second
    assert fork.connections == 2
