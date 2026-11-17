"""007 US2 T028/T029: the show watchdog inside the real app, with a fake host tab and scaled-down thresholds.

The thresholds are cut to fractions of a second so each scenario (spec US2 #1–#5) runs in a few seconds; the rules
themselves are unit-tested in `tests/unit/test_watchdog.py`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_live.app.main import create_app
from ai_live.core.events import EventType
from ai_live.core.logging import JsonFormatter
from fixtures.character_builder import CHARACTER_ID, CUSTOMER_ID, READY_PREPARE, make_character_dir
from fixtures.fake_fork import FakeFork
from fixtures.fake_host import FakeHostConnection

pytestmark = pytest.mark.anyio

FAST = {
    "watchdog_silence_s": 0.5,
    "watchdog_autoskip_s": 1.5,
    "watchdog_frozen_s": 0.5,
    "watchdog_audio_ack_s": 1.0,
    "watchdog_tick_s": 0.05,
}


class Run:
    """One app lifespan: the context, every ALERT payload on the bus, and the app's JSON log lines."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.alerts: list[dict] = []
        self.logs: list[dict] = []

    def opened(self, kind: str) -> list[dict]:
        return [a for a in self.alerts if a["kind"] == kind and a["state"] == "open"]

    def kinds(self) -> set[str]:
        return {a["kind"] for a in self.alerts}

    async def wait(self, predicate, timeout_s: float = 5.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while not predicate():
            assert loop.time() < deadline, f"condition not met in time; alerts={self.alerts}"
            await asyncio.sleep(0.02)

    def alert_lines(self) -> list[dict]:
        path = Path(self.ctx.session_log.directory) / "alerts.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@asynccontextmanager
async def running_app(settings) -> AsyncIterator[Run]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        run = Run(app.state.ctx)

        # Attached after startup: `configure_logging` replaces the ai_live handlers.
        class Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                run.logs.append(json.loads(self.format(record)))

        handler = Collect()
        handler.setFormatter(JsonFormatter("test-session"))
        root = logging.getLogger("ai_live")
        root.addHandler(handler)
        sub = run.ctx.bus.subscribe()

        async def collect() -> None:
            async for event in sub:
                if event.type is EventType.ALERT:
                    run.alerts.append(event.payload["alert"])

        task = asyncio.create_task(collect())
        try:
            yield run
        finally:
            task.cancel()
            root.removeHandler(handler)


async def connect_host(ctx: Any, **ready: Any) -> FakeHostConnection:
    host = FakeHostConnection(ctx.renderer, ack_delay_s=0.02)
    await ctx.renderer.attach(host)
    ctx.renderer.handle_message(host, {"type": "ready", **ready})
    return host


@pytest.fixture
def fast_settings(app_settings):
    return app_settings.model_copy(update=FAST)


async def test_stuck_sentence_is_skipped_once_then_the_show_speaks_again(fast_settings):
    """US2 #1: a sentence that never gets its voice opens `silence`, the watchdog skips it, the show goes on."""
    s = fast_settings.model_copy(update={"tts_timeout_s": 30})
    async with running_app(s) as run:
        ctx = run.ctx
        await connect_host(ctx)
        ctx.director.inject_fault("tts", "timeout", 1)
        session, _ = await ctx.director.start_show()

        await run.wait(lambda: run.opened("silence"))
        await run.wait(lambda: any(a.get("auto_action") == "skip" for a in run.opened("silence")))
        # Skipping the stuck sentence brings speech back well before the 30 s TTS timeout.
        await run.wait(lambda: any(a["kind"] == "silence" and a["state"] == "closed" for a in run.alerts), 4.0)

        silence = [a for a in run.alerts if a["kind"] == "silence"]
        assert {a["alert_id"] for a in silence} == {silence[0]["alert_id"]}
        assert silence[0]["level"] == "warning"
        assert all(a["show_id"] == session.show_id for a in silence)
        assert not [a for a in silence if a["level"] == "operator"]
        assert [line["event"] for line in run.logs if line.get("event") == "watchdog_auto_skip"] == [
            "watchdog_auto_skip"
        ]
        assert any(line.get("event") == "segment_skipped" for line in run.logs)
        ctx.director.end_show()
    events = [line["event"] for line in run.alert_lines() if line["alert"]["kind"] == "silence"]
    assert events == ["open", "auto_skip", "close"]


async def test_host_tab_closed_raises_the_root_alert_only(fast_settings):
    """US2 #3: closing the host tab opens `host_closed` (operator), never silence under it; reopening closes it."""
    async with running_app(fast_settings) as run:
        ctx = run.ctx
        host = await connect_host(ctx)
        await ctx.director.start_show()
        await asyncio.sleep(0.3)
        ctx.renderer.detach(host)

        await run.wait(lambda: run.opened("host_closed"))
        await asyncio.sleep(1.0)  # longer than silence_s: silence must stay covered
        assert run.opened("host_closed")[0]["level"] == "operator"
        assert "silence" not in run.kinds()
        assert [a.kind for a in ctx.watchdog.open_alerts] == ["host_closed"]

        await connect_host(ctx)
        await run.wait(lambda: any(a["kind"] == "host_closed" and a["state"] == "closed" for a in run.alerts))
        ctx.director.end_show()


async def test_a_normal_show_raises_nothing(fast_settings):
    """SC-004: no false alarm while the host speaks normally."""
    s = fast_settings.model_copy(update={"watchdog_silence_s": 1.0, "watchdog_autoskip_s": 3.0})
    async with running_app(s) as run:
        ctx = run.ctx
        await connect_host(ctx)
        await ctx.director.start_show()
        await asyncio.sleep(3.0)
        ctx.director.end_show()
        await asyncio.sleep(0.2)
    assert run.alerts == []
    assert run.alert_lines() == []


async def test_a_long_pause_raises_nothing(fast_settings):
    """US2 #4: the operator's pause is not silence, however long."""
    async with running_app(fast_settings) as run:
        ctx = run.ctx
        await connect_host(ctx)
        await ctx.director.start_show()
        await asyncio.sleep(0.2)
        ctx.director.pause()
        await asyncio.sleep(1.5)
        assert run.alerts == []
        ctx.director.resume()
        await asyncio.sleep(0.4)
        ctx.director.end_show()
    assert "silence" not in run.kinds()


async def test_watchdog_off_adds_no_service(fast_settings):
    async with running_app(fast_settings.model_copy(update={"watchdog_enabled": False})) as run:
        assert run.ctx.watchdog is None
        assert "show_watchdog" not in {t.get_name() for t in asyncio.all_tasks()}


def test_control_page_hears_the_alert_and_state_lists_it(fast_settings):
    """US2 #3 over the real sockets: `/ws/control` gets `alert`, `GET /api/state` lists what is open."""
    with TestClient(create_app(fast_settings)) as c:
        with c.websocket_connect("/ws/host") as host:
            host.send_json({"type": "ready"})
            assert c.post("/api/show/start").status_code == 200
        with c.websocket_connect("/ws/control") as control:
            for _ in range(200):
                msg = control.receive_json()
                if msg["type"] == "state" and any(a["kind"] == "host_closed" for a in msg.get("alerts", [])):
                    break
                if msg["type"] == "alert" and msg["alert"]["kind"] == "host_closed":
                    break
            else:
                pytest.fail("host_closed never reached the control page")
        alerts = c.get("/api/state").json()["alerts"]
        assert [a["kind"] for a in alerts] == ["host_closed"]
        assert alerts[0]["state"] == "open" and alerts[0]["action"]
        c.post("/api/show/end")


# --- T029: lip-sync only kinds ---


@pytest.fixture
def lipsync_fast(fast_settings, tmp_path: Path):
    avatar_dir = make_character_dir(tmp_path / "avatars", prepare=READY_PREPARE)
    return fast_settings.model_copy(
        update={
            "avatar_mode": "livetalking",
            "customer_id": CUSTOMER_ID,
            "avatar_id": CHARACTER_ID,
            "avatar_dir": avatar_dir,
        }
    )


def beat(ctx: Any, host: FakeHostConnection, frames: int | None) -> None:
    ctx.renderer.handle_message(
        host, {"type": "host_status", "frames": frames, "audio": "running", "video_muted": False, "visible": True}
    )


async def test_fork_lost_then_frozen_picture(lipsync_fast):
    """US2 #2 and #5 with lip-sync: a frozen picture opens `frozen`; losing the fork opens `fork_lost`, covering it."""
    async with FakeFork() as fork:
        s = lipsync_fast.model_copy(update={"livetalking_url": fork.url})
        async with running_app(s) as run:
            ctx = run.ctx
            host = await connect_host(ctx, lipsync_session="sess-1")
            await run.wait(lambda: ctx.renderer.lipsync.ready)
            await ctx.director.start_show()

            beat(ctx, host, 100)
            await asyncio.sleep(0.3)
            beat(ctx, host, 120)
            await asyncio.sleep(0.6)
            beat(ctx, host, 120)
            await run.wait(lambda: run.opened("frozen"))
            assert run.opened("frozen")[0]["level"] == "warning"
            beat(ctx, host, 150)
            await run.wait(lambda: any(a["kind"] == "frozen" and a["state"] == "closed" for a in run.alerts))

            await fork.stop()
            await run.wait(lambda: run.opened("fork_lost"))
            assert run.opened("fork_lost")[0]["level"] == "operator"
            ctx.director.end_show()


def test_control_page_has_the_alert_banner(fast_settings):
    with TestClient(create_app(fast_settings)) as c:
        html = c.get("/").text
        js = c.get("/static/control.js").text
    assert 'id="alert-banner"' in html
    # Alert text comes from the app but is rendered as text, never as markup.
    assert "renderAlerts" in js and "innerHTML" not in js.split("function renderAlerts")[1].split("function ")[0]


def test_host_page_stays_out_of_the_back_forward_cache(fast_settings):
    """T035: a host page cached on navigation kept its socket open; `host_closed` came only at the ping timeout."""
    with TestClient(create_app(fast_settings)) as c:
        resp = c.get("/host")
        js = c.get("/static/host.js").text
    assert resp.headers["cache-control"] == "no-store"
    assert 'addEventListener("pagehide"' in js


# --- 006 T021: OUTPUT_MODE=obs in the real app (contracts/api.md §8) ---


async def test_obs_mode_host_tab_is_output_lost_until_obs_connects_and_stale_source_alerts(fast_settings):
    s = fast_settings.model_copy(
        update={"output_mode": "obs", "watchdog_host_stale_s": 0.6, "watchdog_silence_s": 30, "watchdog_autoskip_s": 60}
    )
    async with running_app(s) as run:
        ctx = run.ctx
        await connect_host(ctx)  # a Chrome /host tab, role `host`
        await ctx.director.start_show()
        await run.wait(lambda: run.opened("host_closed"))
        assert run.opened("host_closed")[0]["message"] == "Nguồn OBS đã ngắt"

        obs = FakeHostConnection(ctx.renderer, ack_delay_s=0.02)
        await ctx.renderer.attach(obs, "obs")
        ctx.renderer.handle_message(obs, {"type": "ready"})
        await run.wait(lambda: any(a["kind"] == "host_closed" and a["state"] == "closed" for a in run.alerts))

        # The source stays connected but sends no heartbeat: output lost (stale), a heartbeat clears it.
        await run.wait(lambda: len(run.opened("host_closed")) == 2, 3.0)
        assert "nhịp" in run.opened("host_closed")[1]["message"]
        beat(ctx, obs, None)
        await run.wait(lambda: sum(a["kind"] == "host_closed" and a["state"] == "closed" for a in run.alerts) == 2)
        ctx.director.end_show()
