"""006 T007, T008, T014, T022: `/obs`, `/ws/host?role=`, host-config and `/api/state` (contracts/api.md §1–§5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_live.app.main import create_app

PLATFORM_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"
CLAIM_PHRASES = PLATFORM_PHRASES.with_name("claim_phrases.txt")


@pytest.fixture
def obs_settings(app_settings):
    return app_settings.model_copy(
        update={
            "platform_phrases_path": PLATFORM_PHRASES,
            "claim_phrases_path": CLAIM_PHRASES,
            "script_segment_min_sentences": 2,
            "script_segment_max_sentences": 3,
            "output_mode": "obs",
        }
    )


@pytest.fixture
def client(obs_settings):
    with TestClient(create_app(obs_settings)) as c:
        yield c


def _wait(client: TestClient, predicate) -> dict:
    for _ in range(500):
        state = client.get("/api/state").json()
        if predicate(state):
            return state
    raise AssertionError("state never reached")


def _play_one(ws) -> list[dict]:
    """Read up to one `sentence_end`, acking like the real page; the JSON messages received."""
    got: list[dict] = []
    while True:
        message = ws.receive()
        if message.get("text") is None:
            continue
        data = json.loads(message["text"])
        got.append(data)
        if data["type"] == "sentence_start":
            ws.send_json({"type": "playback_started", "utterance_id": data["utterance_id"], "seq": data["seq"]})
        if data["type"] == "sentence_end":
            ws.send_json({"type": "sentence_played", "utterance_id": data["utterance_id"], "seq": data["seq"]})
            return got


def _close_code(ws) -> int:
    """Skip whatever was queued for a losing page; the close code it finally gets."""
    try:
        while True:
            message = ws.receive()
            if message["type"] == "websocket.close":
                return message["code"]
    except WebSocketDisconnect as exc:
        return exc.code


# ---------- T007: the page ----------


def test_obs_page_is_host_page_with_obs_class(client, obs_settings):
    r = client.get("/obs")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert '<body class="host obs">' in r.text
    assert "{{" not in r.text
    assert obs_settings.ai_label_text in r.text
    assert obs_settings.ai_label_position in r.text


@pytest.mark.parametrize("query", ["?ai_label=0", "?label=off", "?obs=0", "?role=host"])
def test_obs_page_ignores_query_string(client, query):
    # Article I: no URL can hide the label or change the page.
    assert client.get(f"/obs{query}").text == client.get("/obs").text


def test_host_page_unchanged(client):
    text = client.get("/host").text
    assert '<body class="host">' in text
    assert "host obs" not in text


def test_host_config_has_output_mode(client):
    assert client.get("/api/host-config").json()["output_mode"] == "obs"


def test_host_config_output_mode_defaults_to_meet(app_settings):
    with TestClient(create_app(app_settings)) as c:
        assert c.get("/api/host-config").json()["output_mode"] == "meet"


def test_no_route_serves_a_video_file(client):
    # 007 FR-021 still holds: the backup video is never reachable from the app.
    for path in ("/obs.mp4", "/obs/video", "/api/backup-video", "/static/backup.mp4"):
        r = client.get(path)
        assert r.status_code == 404 or not r.headers.get("content-type", "").startswith("video/")


# ---------- T008: `/ws/host?role=obs` plays, a later host is refused ----------


def test_obs_role_plays_the_show_and_a_host_tab_gets_4001(client):
    with client.websocket_connect("/ws/host?role=obs") as obs:
        obs.send_json({"type": "ready"})
        state = _wait(client, lambda s: s["session"]["host_connected"])
        assert state["session"]["host_role"] == "obs"
        assert client.post("/api/show/start").status_code == 200
        got = _play_one(obs)
        assert any(m["type"] == "sentence_start" for m in got)
        with client.websocket_connect("/ws/host?role=host") as host:
            assert _close_code(host) == 4001
        # OBS keeps the sound.
        got = _play_one(obs)
        assert any(m["type"] == "sentence_start" for m in got)
        assert client.get("/api/state").json()["session"]["host_role"] == "obs"


def test_missing_or_unknown_role_is_host(client):
    with client.websocket_connect("/ws/host?role=camera") as page:
        page.send_json({"type": "ready"})
        assert _wait(client, lambda s: s["session"]["host_connected"])["session"]["host_role"] == "host"


# ---------- T014: OBS takes over a running show ----------


def test_obs_takes_over_running_show_from_host(client):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait(client, lambda s: s["session"]["host_connected"])
        assert client.post("/api/show/start").status_code == 200
        _play_one(host)
        with client.websocket_connect("/ws/host?role=obs") as obs:
            obs.send_json({"type": "ready"})
            assert _close_code(host) == 4001
            _wait(client, lambda s: s["session"]["host_role"] == "obs" and s["session"]["host_connected"])
            # The show goes on through OBS without a restart.
            got = _play_one(obs)
            assert any(m["type"] == "sentence_start" for m in got)
            assert client.get("/api/show").json()["state"] == "running"
        # The OBS source closed: nobody plays, the yielded host does not come back on its own.
        state = _wait(client, lambda s: not s["session"]["host_connected"])
        assert state["session"]["host_role"] is None


def test_new_obs_source_reloads_current_scene_and_mode(client):
    with client.websocket_connect("/ws/host?role=obs") as first:
        first.send_json({"type": "ready"})
        _wait(client, lambda s: s["session"]["host_connected"])
    # A reloaded source gets the current picture and avatar mode from the page and host-config, not from the socket.
    config = client.get("/api/host-config").json()
    page = client.get("/obs").text
    assert config["active"] in ("static", "livetalking")
    assert ("/avatar-image" in page) or ("avatar-placeholder" in page) or ("/api/scene/still.png" in page)
    with client.websocket_connect("/ws/host?role=obs") as second:
        second.send_json({"type": "ready"})
        assert _wait(client, lambda s: s["session"]["host_connected"])["session"]["host_role"] == "obs"


# ---------- T022: `/api/state` and the control snapshot ----------


def test_state_has_output_mode_and_host_role(client):
    state = client.get("/api/state").json()
    assert state["session"]["output_mode"] == "obs"
    assert state["session"]["host_role"] is None
    with client.websocket_connect("/ws/control") as control:
        snapshot = control.receive_json()
        assert snapshot["type"] == "state"
        assert snapshot["session"]["output_mode"] == "obs"
        assert snapshot["session"]["host_role"] is None
        with client.websocket_connect("/ws/host?role=obs") as obs:
            obs.send_json({"type": "ready"})
            while True:
                event = control.receive_json()
                if event["type"] == "host_connection":
                    assert event == {**event, "connected": True, "role": "obs"}
                    break


# ---------- T032: a show played by the OBS source is measured like one played by /host (FR-013) ----------


def test_show_through_obs_logs_every_latency_milestone(client, json_log_lines):
    with client.websocket_connect("/ws/host?role=obs") as obs:
        obs.send_json({"type": "ready"})
        _wait(client, lambda s: s["session"]["host_connected"])
        assert client.post("/api/show/start").status_code == 200
        for _ in range(2):
            _play_one(obs)
    events = {ln["event"] for ln in json_log_lines}
    for milestone in ("segment_requested", "llm_first_sentence", "tts_first_chunk", "avatar_first_frame"):
        assert milestone in events, milestone
    first_frames = [ln for ln in json_log_lines if ln["event"] == "avatar_first_frame"]
    assert all(ln.get("utterance_id") for ln in first_frames)


@pytest.mark.parametrize("path", ["/static/host.js", "/static/style.css"])
def test_static_files_are_revalidated(client, path):
    # OBS's browser kept a cached host.js after an app update (006 T029, 2026-11-19): with only Last-Modified, a
    # browser may reuse a file for a long time without asking. `no-cache` makes it check the ETag on every load.
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"


def test_host_page_versions_its_assets(client):
    # A cache entry stored before `no-cache` existed is only bypassed by a new URL.
    page = client.get("/obs").text
    for name in ("host.js", "style.css"):
        mtime = int((Path(__file__).resolve().parents[2] / "src" / "ai_live" / "app" / "static" / name).stat().st_mtime)
        assert f"/static/{name}?v={mtime}" in page
