"""007 T019: `GET /api/readiness` (contracts/api.md §1) and the new `/health` fields, without GPU, network or keys."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_live.app.main import create_app
from ai_live.core.events import EventType
from ai_live.ops.readiness import ITEM_IDS, MANUAL_CHECKS
from fixtures.character_builder import CHARACTER_ID, CUSTOMER_ID, READY_PREPARE, make_character_dir
from fixtures.fake_fork import FakeFork


class CountingChain:
    """Stands in for ChainReplyEngine: the snapshot is free, anything else would be a model call (FR-004, SC-007)."""

    def __init__(self) -> None:
        self.snapshots = 0
        self.calls: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        self.snapshots += 1
        return {
            "entries": [
                {"label": "SEA-LION", "status": "ready", "reason": None},
                {"label": "Qwen", "status": "resting", "reason": "rate_limit"},
            ],
            "last_entry": None,
            "using_backup": False,
        }

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> None:
            self.calls.append(name)

        return call


@pytest.fixture
def fork() -> Iterator[FakeFork]:
    """The fake fork on its own loop thread: the TestClient app runs on another loop."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    fake = asyncio.run_coroutine_threadsafe(FakeFork().start(), loop).result(5)
    yield fake
    asyncio.run_coroutine_threadsafe(fake.stop(), loop).result(5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)


def by_id(body: dict) -> dict[str, dict]:
    return {item["id"]: item for item in body["items"]}


def readiness_lines(settings, session_id: str) -> list[dict]:
    path = Path(settings.session_data_dir) / session_id / "readiness.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_static_fake_app_is_not_ready_and_says_why(app_settings):
    """Quickstart §1: the try-out config fails on env, engine, voice, host and the missing backup video."""
    s = app_settings.model_copy(update={"backup_video_dir": app_settings.session_data_dir.parent / "no_video"})
    with TestClient(create_app(s)) as c:
        session_id = c.get("/api/state").json()["session"]["session_id"]
        show_before = c.get("/api/show").json()
        ctx = c.app.state.ctx
        sub = ctx.bus.subscribe()
        r = c.get("/api/readiness")
        show_after = c.get("/api/show").json()
        events = sub.drain()
        sub.close()
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"checked_at", "source", "ready", "duration_ms", "output_mode", "items", "manual"}
    assert body["source"] == "app"
    assert body["ready"] is False
    assert [item["id"] for item in body["items"]] == list(ITEM_IDS)
    assert body["manual"] == list(MANUAL_CHECKS)
    assert body["duration_ms"] <= 5000  # SC-001
    failed = {item["id"] for item in body["items"] if item["status"] == "fail"}
    assert {"app_env", "reply_engine", "tts_provider", "host", "backup_video"} <= failed
    items = by_id(body)
    assert items["fork"]["status"] == "ok"  # static: no fork to need
    assert items["llm_chain"]["status"] == "ok"
    assert items["ai_label"]["status"] == "ok"
    for item in body["items"]:
        assert set(item) == {"id", "label", "status", "message", "action"}
        assert (item["action"] is None) == (item["status"] == "ok")
    # Read-only: nothing spoken, the show untouched (FR-004).
    assert show_before == show_after
    assert not [e for e in events if e.type is EventType.SENTENCE]
    lines = readiness_lines(s, session_id)
    assert len(lines) == 1
    assert lines[0] == body


def test_each_call_appends_one_line(app_settings):
    with TestClient(create_app(app_settings)) as c:
        session_id = c.get("/api/state").json()["session"]["session_id"]
        c.get("/api/readiness")
        c.get("/api/readiness")
    assert len(readiness_lines(app_settings, session_id)) == 2


def test_chain_is_read_from_its_snapshot_never_called(app_settings):
    """SC-007: a readiness check must not spend one free-model request."""
    chain = CountingChain()
    with TestClient(create_app(app_settings)) as c:
        ctx = c.app.state.ctx
        saved_chain, saved_settings = ctx.chain, ctx.settings
        ctx.chain = chain
        ctx.settings = ctx.settings.model_copy(update={"reply_engine": "chain"})
        try:
            body = c.get("/api/readiness").json()
        finally:
            ctx.chain, ctx.settings = saved_chain, saved_settings
    assert chain.calls == []
    assert chain.snapshots == 1
    llm = by_id(body)["llm_chain"]
    assert llm["status"] == "warn"
    assert "Qwen" in llm["message"]


def test_host_ready_after_the_tab_starts(app_settings):
    with TestClient(create_app(app_settings)) as c, c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        host.send_json({"type": "host_status", "frames": None, "audio": "running", "visible": True})
        for _ in range(50):
            body = c.get("/api/readiness").json()
            if by_id(body)["host"]["status"] == "ok":
                break
    assert by_id(body)["host"]["status"] == "ok"


@pytest.fixture
def lipsync_settings(app_settings, tmp_path: Path, fork: FakeFork):
    avatar_dir = make_character_dir(tmp_path / "avatars", prepare=READY_PREPARE)
    return app_settings.model_copy(
        update={
            "avatar_mode": "livetalking",
            "customer_id": CUSTOMER_ID,
            "avatar_id": CHARACTER_ID,
            "avatar_dir": avatar_dir,
            "livetalking_url": fork.url,
        }
    )


def test_fork_recording_left_on_is_a_failure(lipsync_settings, fork: FakeFork):
    fork.record_enabled = True
    with TestClient(create_app(lipsync_settings)) as c:
        items = by_id(c.get("/api/readiness").json())
    assert items["recording"]["status"] == "fail"
    assert "AILIVE_RECORD_DIR" in items["recording"]["action"]
    # Up but no host-page session yet.
    assert items["fork"]["status"] == "warn"
    assert items["character"]["status"] == "ok"


def test_fork_not_recording_passes(lipsync_settings, fork: FakeFork):
    with TestClient(create_app(lipsync_settings)) as c:
        items = by_id(c.get("/api/readiness").json())
    assert items["recording"]["status"] == "ok"


def test_fork_down_is_a_failure(lipsync_settings, fork: FakeFork):
    s = lipsync_settings.model_copy(update={"livetalking_url": "http://127.0.0.1:9"})
    with TestClient(create_app(s)) as c:
        body = c.get("/api/readiness").json()
    items = by_id(body)
    assert items["fork"]["status"] == "fail"
    assert items["recording"]["status"] == "unknown"
    assert body["duration_ms"] <= 5000


def test_health_names_the_character_and_the_show(app_settings):
    s = app_settings.model_copy(update={"customer_id": "shop_a", "avatar_id": "host_a"})
    with TestClient(create_app(s)) as c:
        body = c.get("/health").json()
    assert body["customer_id"] == "shop_a"
    assert body["avatar_id"] == "host_a"
    assert body["show_active"] is False


def test_control_page_has_the_readiness_button_and_every_status_label(app_settings):
    """T025: the button reads `/api/readiness` and shows each status in words, not only by colour."""
    with TestClient(create_app(app_settings)) as c:
        html = c.get("/static/control.html").text
        js = c.get("/static/control.js").text
    start = html.index('id="readiness-panel"')
    panel = html[start : html.index("</section>", start)]
    assert 'id="readiness-btn"' in panel and "Kiểm tra trước demo" in panel
    assert "Việc tự xác nhận" in panel
    assert 'fetch("/api/readiness")' in js
    for status, label in {"ok": "Đạt", "warn": "Chú ý", "fail": "Lỗi", "unknown": "Chưa rõ"}.items():
        assert f'{status}: "{label}"' in js
    # Server text goes in through textContent only.
    assert ".innerHTML" not in js
