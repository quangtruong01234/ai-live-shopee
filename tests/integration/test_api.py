"""App HTTP/WebSocket tests (contracts/api.md): T037 (US1 #5; FR-015, FR-021, SC-006), T062 (US2), T073 (US3)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_live.app.main import create_app
from ai_live.products.models import ContentLoadError

FAKE_KEY = "AIzaSyTEST-not-a-real-key-0123456789abcd"


@pytest.fixture
def client(app_settings):
    with TestClient(create_app(app_settings)) as c:
        yield c


def test_post_comment_returns_202_waiting(client):
    r = client.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu vậy shop?"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "waiting"
    assert body["priority"] == "HIGH"
    assert body["comment_id"]


def test_post_comment_bad_schema_is_422_json_error(client):
    r = client.post("/api/comments", json={"author": "Lan"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert body["message"]
    assert isinstance(body["details"], list)


def test_favicon_is_empty_not_404(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 204
    assert r.content == b""


def test_host_page_shows_label(client):
    html = client.get("/host").text
    assert 'id="ai-label"' in html
    assert ">AI<" in html


@pytest.mark.parametrize("query", ["?label=0", "?hide_label=1", "?ai_label=off", "?show_label=false"])
def test_host_page_has_no_param_to_hide_label(client, query):
    html = client.get("/host" + query).text
    assert 'id="ai-label"' in html
    assert ">AI<" in html


def test_host_label_text_and_position_from_settings(app_settings):
    s = app_settings.model_copy(update={"ai_label_text": "Trợ lý <AI>", "ai_label_position": "bottom-left"})
    with TestClient(create_app(s)) as c:
        html = c.get("/host").text
    assert "Trợ lý &lt;AI&gt;" in html
    assert "<AI>" not in html
    assert "label-bottom-left" in html


def test_blank_label_stops_startup(monkeypatch, content_path, tmp_path):
    monkeypatch.setenv("AI_LABEL_TEXT", "   ")
    monkeypatch.setenv("PRODUCT_DATA_PATH", str(content_path))
    monkeypatch.setenv("REPLY_ENGINE", "fake")
    monkeypatch.setenv("SESSION_DATA_DIR", str(tmp_path / "s"))
    with pytest.raises(ValidationError):
        with TestClient(create_app(env_file=None)):
            pass


def test_invalid_content_stops_startup(app_settings, tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a docx")
    s = app_settings.model_copy(update={"product_data_path": bad})
    with pytest.raises(ContentLoadError):
        with TestClient(create_app(s)):
            pass


def test_secret_not_exposed(app_settings):
    from pydantic import SecretStr

    s = app_settings.model_copy(update={"gemini_api_key": SecretStr(FAKE_KEY)})
    with TestClient(create_app(s)) as c:
        health = c.get("/health")
        state = c.get("/api/state")
        with c.websocket_connect("/ws/control") as ws:
            first = ws.receive_json()
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert FAKE_KEY not in health.text
    assert FAKE_KEY not in state.text
    assert first["type"] == "state" and "ts" in first
    assert FAKE_KEY not in json.dumps(first, ensure_ascii=False)


def test_state_shape(client):
    body = client.get("/api/state").json()
    assert set(body) >= {"session", "queue", "current_utterance", "catalog"}
    assert body["catalog"]["version"]
    assert [p["name"] for p in body["catalog"]["products"]] == ["Kem chống nắng X", "Sữa rửa mặt Y", "Toner Z"]
    health = client.get("/health").json()
    assert health["catalog_version"] == body["catalog"]["version"]


def test_control_ws_forwards_events(client):
    with client.websocket_connect("/ws/control") as ws:
        assert ws.receive_json()["type"] == "state"
        client.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu?"})
        msg = ws.receive_json()
        assert msg["type"] == "comment_accepted"
        assert msg["author"] == "Lan"
        assert "ts" in msg


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("có link không http://x.y", "link"),
        ("ghé shopkhac.vn nha", "link"),
        ("vcl giá gì kỳ vậy", "profanity"),
        ("😍😍😍", "empty"),
        ("   ", "empty"),
    ],
)
def test_post_filtered_comment_returns_202_dropped(client, text, reason):
    r = client.post("/api/comments", json={"author": "Lan", "text": text})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "dropped"
    assert body["drop_reason"] == reason
    assert body["comment_id"]
    assert "priority" not in body


def test_post_duplicate_comment_returns_202_dropped(client):
    first = client.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu?"}).json()
    second = client.post("/api/comments", json={"author": "Lan", "text": "Gia bao nhieu"}).json()
    assert first["status"] == "waiting"
    assert second["status"] == "dropped"
    assert second["drop_reason"] == "duplicate"


@pytest.mark.parametrize(
    ("text", "priority"),
    [("giá bao nhiêu vậy shop?", "HIGH"), ("chất liệu gì vậy?", "MEDIUM"), ("hello shop", "LOW")],
)
def test_post_valid_comment_returns_priority(client, text, priority):
    body = client.post("/api/comments", json={"author": "Huy", "text": text}).json()
    assert body["status"] == "waiting"
    assert body["priority"] == priority
    assert "drop_reason" not in body


def test_control_ws_gets_comment_dropped_with_reason(client):
    with client.websocket_connect("/ws/control") as ws:
        assert ws.receive_json()["type"] == "state"
        r = client.post("/api/comments", json={"author": "Lan", "text": "có link không http://x.y"})
        msg = ws.receive_json()
    assert msg["type"] == "comment_dropped"
    assert msg["comment_id"] == r.json()["comment_id"]
    assert msg["reason"] == "link"
    assert msg["author"] == "Lan"


# --- POST /api/debug/speak ---


def _host_play_one(ws, *, ack: bool = True) -> list[dict]:
    """Read messages up to `sentence_end`, acking like the real host page. Returns the JSON messages received."""
    got: list[dict] = []
    while True:
        message = ws.receive()
        if message.get("text") is None:
            continue
        data = json.loads(message["text"])
        got.append(data)
        if ack and data["type"] == "sentence_start":
            ws.send_json({"type": "playback_started", "utterance_id": data["utterance_id"], "seq": data["seq"]})
        if data["type"] == "sentence_end":
            if ack:
                ws.send_json({"type": "sentence_played", "utterance_id": data["utterance_id"], "seq": data["seq"]})
            return got


def test_debug_speak_200_after_playback(client):
    with client.websocket_connect("/ws/host") as host, ThreadPoolExecutor(1) as pool:
        host.send_json({"type": "ready"})
        future = pool.submit(client.post, "/api/debug/speak", json={"text": "Dạ chào cả nhà."})
        got = _host_play_one(host)
        r = future.result(timeout=5)
    assert r.status_code == 200
    assert r.json()["utterance_id"]
    assert got[0]["type"] == "sentence_start" and got[0]["text"] == "Dạ chào cả nhà."


def test_debug_speak_409_while_speaking(client):
    with client.websocket_connect("/ws/host") as host, ThreadPoolExecutor(1) as pool:
        host.send_json({"type": "ready"})
        future = pool.submit(client.post, "/api/debug/speak", json={"text": "Dạ chào cả nhà."})
        first = host.receive_json()
        assert first["type"] == "sentence_start"
        busy = client.post("/api/debug/speak", json={"text": "Câu thứ hai."})
        assert busy.status_code == 409
        assert busy.json()["error"] == "busy"
        host.send_json({"type": "playback_started", "utterance_id": first["utterance_id"], "seq": 0})
        _host_play_one(host)
        assert future.result(timeout=5).status_code == 200


@pytest.mark.parametrize("text", ["", "x" * 301])
def test_debug_speak_422_text_length(client, text):
    assert client.post("/api/debug/speak", json={"text": text}).status_code == 422


def test_debug_speak_503_without_host(client):
    r = client.post("/api/debug/speak", json={"text": "Dạ chào cả nhà."})
    assert r.status_code == 503
    assert r.json()["error"] == "host_unavailable"


def test_debug_speak_404_when_not_dev(app_settings):
    s = app_settings.model_copy(update={"app_env": "demo"})
    with TestClient(create_app(s)) as c:
        r = c.post("/api/debug/speak", json={"text": "Dạ chào cả nhà."})
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


# --- GET /api/latency (T073, US3 #2; data-model.md §4) ---

STEP_NAMES = {
    "received_to_first_sentence",
    "first_sentence_to_tts_first_chunk",
    "tts_first_chunk_to_first_frame",
    "queue_wait",
    "floor_wait",
    "total",
}


def _assert_latency_summary(body: dict, *, idle_only: bool) -> None:
    assert body["idle_only"] is idle_only
    assert body["min_samples"] == 20
    assert body["idle_threshold_s"] == pytest.approx(0.3)
    for key in ("completed", "errors", "skipped", "idle_completed"):
        assert isinstance(body[key], int)
    for group in ("steps", "idle_steps"):
        assert set(body[group]) == STEP_NAMES
        for stats in body[group].values():
            assert set(stats) == {"count", "median", "p95", "note"}


def test_latency_empty_session(client):
    r = client.get("/api/latency")
    assert r.status_code == 200
    body = r.json()
    _assert_latency_summary(body, idle_only=False)
    assert body["completed"] == body["errors"] == body["skipped"] == 0
    total = body["steps"]["total"]
    assert total == {"count": 0, "median": None, "p95": None, "note": "chưa đủ mẫu"}

    idle = client.get("/api/latency?idle_only=true")
    assert idle.status_code == 200
    _assert_latency_summary(idle.json(), idle_only=True)


def test_latency_after_one_answered_turn(app_settings):
    from ai_live.brain.fake_engine import FakeReplyEngine

    with TestClient(create_app(app_settings, reply_engine=FakeReplyEngine("Dạ chào bạn Lan nha."))) as c:
        with c.websocket_connect("/ws/host") as host:
            host.send_json({"type": "ready"})
            for _ in range(250):
                if c.get("/health").json()["host_connected"]:
                    break
            c.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu?"})
            _host_play_one(host)
            for _ in range(250):
                body = c.get("/api/latency").json()
                if body["completed"] == 1:
                    break
        idle = c.get("/api/latency", params={"idle_only": "true"}).json()

    _assert_latency_summary(body, idle_only=False)
    assert body["completed"] == 1 and body["errors"] == 0
    total = body["steps"]["total"]
    assert total["count"] == 1
    assert total["median"] is not None and total["median"] >= 0
    assert total["p95"] is None and total["note"] == "chưa đủ mẫu"
    _assert_latency_summary(idle, idle_only=True)
    assert idle["completed"] == 1
    # The turn may or may not count as idle (queue_wait < 0.3 s); both groups must agree in idle mode.
    assert idle["steps"] == idle["idle_steps"]


# --- PUT /api/content (T081, US5; FR-022, contracts/api.md §2) ---


def _put_content(client, data: bytes, filename: str = "demo.docx"):
    return client.put(
        "/api/content",
        content=data,
        headers={"Content-Type": "application/octet-stream", "X-Filename": filename},
    )


def test_put_content_valid_returns_new_version(client):
    from fixtures.content_builder import build_docx, product_blocks

    old = client.get("/api/state").json()["catalog"]["version"]
    r = _put_content(client, build_docx(product_blocks("Kem mới", price="300.000đ")))
    assert r.status_code == 200
    body = r.json()
    assert body["version"] and body["version"] != old
    assert body["products"] == [{"id": body["products"][0]["id"], "name": "Kem mới", "is_primary": True}]
    assert client.get("/health").json()["catalog_version"] == body["version"]


def test_put_content_invalid_lists_every_issue_and_keeps_catalog(client):
    from fixtures.content_builder import build_docx, product_blocks

    before = client.get("/api/state").json()["catalog"]
    r = _put_content(client, build_docx(product_blocks("Kem X", price="250k", forbidden=None)))
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "content_invalid"
    assert body["message"]
    codes = sorted(d["code"] for d in body["details"])
    assert codes == ["missing_section", "price_format"]
    assert any(d["section"] == "Khẳng định bị cấm" for d in body["details"])
    assert all(d["message"] for d in body["details"])
    assert client.get("/api/state").json()["catalog"] == before


def test_put_content_too_large_is_413(app_settings):
    from fixtures.content_builder import valid_docx

    # The startup file must still fit, so the limit sits just above it.
    s = app_settings.model_copy(update={"content_max_bytes": len(valid_docx()) + 10})
    with TestClient(create_app(s)) as c:
        before = c.get("/health").json()["catalog_version"]
        r = _put_content(c, valid_docx() + b"\0" * 200)
        assert r.status_code == 413
        assert r.json()["error"] == "content_too_large"
        assert c.get("/health").json()["catalog_version"] == before


@pytest.mark.parametrize("data", [b"not a docx at all", b"PK\x03\x04broken zip"])
def test_put_content_not_docx_is_415(client, data):
    before = client.get("/health").json()["catalog_version"]
    r = _put_content(client, data, "notes.txt")
    assert r.status_code == 415
    assert r.json()["error"] == "unsupported_media_type"
    assert client.get("/health").json()["catalog_version"] == before


def test_put_content_filename_is_never_a_write_path(client, tmp_path, monkeypatch):
    from fixtures.content_builder import valid_docx

    workdir = tmp_path / "work" / "sub"
    workdir.mkdir(parents=True)
    monkeypatch.chdir(workdir)
    r = _put_content(client, valid_docx(), "../evil.docx")
    assert r.status_code == 200
    assert list((tmp_path / "work").rglob("*")) == [workdir]


# --- POST /api/pause, /api/resume, /api/skip, /api/debug/fault (T090, US4; contracts/api.md §2, events.md §1) ---


def _control_logs(lines: list[dict], command: str) -> list[dict]:
    return [
        r for r in lines if r.get("event") in ("control_command", "control_applied") and r.get("command") == command
    ]


def test_pause_and_resume_are_idempotent_and_logged(client, json_log_lines):
    for _ in range(2):
        r = client.post("/api/pause")
        assert r.status_code == 200 and r.json() == {"state": "paused"}
    assert client.get("/api/state").json()["session"]["state"] == "paused"
    for _ in range(2):
        r = client.post("/api/resume")
        assert r.status_code == 200 and r.json() == {"state": "running"}
    assert client.get("/api/state").json()["session"]["state"] == "running"

    for command in ("pause", "resume"):
        logs = _control_logs(json_log_lines, command)
        # A repeat changes nothing, so it publishes no `session_state` and logs no `control_applied` (events.md §1).
        assert [r["event"] for r in logs] == ["control_command", "control_applied", "control_command"]
        assert all(isinstance(r["t_mono"], float) for r in logs if r["event"] == "control_command")
        assert all(r["latency_ms"] >= 0 for r in logs if r["event"] == "control_applied")


def test_control_ws_gets_session_state(client):
    with client.websocket_connect("/ws/control") as ws:
        assert ws.receive_json()["type"] == "state"
        client.post("/api/pause")
        # The comment's `queue_changed` is a sentinel: a missing `session_state` fails instead of blocking forever.
        client.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu?"})
        msg = ws.receive_json()
        while msg["type"] not in ("session_state", "queue_changed"):
            msg = ws.receive_json()
        assert (msg["type"], msg["state"]) == ("session_state", "paused")


def test_skip_with_nothing_speaking_returns_null(client, json_log_lines):
    r = client.post("/api/skip")
    assert r.status_code == 200
    assert r.json() == {"skipped_utterance_id": None}
    # Nothing to stop, so no `stop` is sent and no `control_applied` is logged (events.md §1).
    assert [r["event"] for r in _control_logs(json_log_lines, "skip")] == ["control_command"]


def test_skip_while_speaking_stops_host(app_settings):
    from ai_live.brain.fake_engine import FakeReplyEngine

    engine = FakeReplyEngine("Dạ câu thứ nhất nha. Dạ câu thứ hai nha.")
    with TestClient(create_app(app_settings, reply_engine=engine)) as c, c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        for _ in range(250):
            if c.get("/health").json()["host_connected"]:
                break
        c.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu?"})
        first = host.receive_json()
        assert first["type"] == "sentence_start"
        # No ack: the host is still "speaking" the first sentence when the operator skips.
        r = c.post("/api/skip")
        assert r.status_code == 200
        assert r.json() == {"skipped_utterance_id": first["utterance_id"]}
        # The next comment's `sentence_start` is a sentinel: a missing `stop` fails instead of blocking forever.
        c.post("/api/comments", json={"author": "Mai", "text": "còn hàng không shop?"})
        received = []
        while True:
            message = host.receive()
            if message.get("text") is None:
                continue
            data = json.loads(message["text"])
            received.append(data)
            if data["type"] == "sentence_start" and data["utterance_id"] != first["utterance_id"]:
                break
        stops = [m for m in received if m["type"] == "stop"]
        assert stops == [{"type": "stop", "utterance_id": first["utterance_id"]}]


def test_debug_fault_200_in_dev(client):
    r = client.post("/api/debug/fault", json={"step": "tts", "mode": "timeout", "count": 2})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"step": "brain", "mode": "error", "count": 1},
        {"step": "llm", "mode": "crash", "count": 1},
        {"step": "llm", "mode": "error", "count": 0},
    ],
)
def test_debug_fault_422_bad_body(client, body):
    assert client.post("/api/debug/fault", json=body).status_code == 422


def test_debug_fault_404_when_not_dev(app_settings):
    s = app_settings.model_copy(update={"app_env": "demo"})
    with TestClient(create_app(s)) as c:
        r = c.post("/api/debug/fault", json={"step": "llm", "mode": "error", "count": 1})
    assert r.status_code == 404


def test_session_json_records_run_conditions_without_secrets(app_settings):
    # 007 T013 (data-model §3, contracts/files.md §1): the rehearsal report reads the run conditions from here.
    from pydantic import SecretStr

    s = app_settings.model_copy(update={"gemini_api_key": SecretStr(FAKE_KEY), "customer_id": "shop_a"})
    with TestClient(create_app(s)) as c:
        session_id = c.get("/api/state").json()["session"]["session_id"]
        catalog_version = c.get("/api/state").json()["catalog"]["version"]
        path = s.session_data_dir / session_id / "session.json"
        text = path.read_text(encoding="utf-8")
    info = json.loads(text)
    assert info["session_id"] == session_id
    assert info["started_at"].endswith("Z")
    assert (info["app_env"], info["reply_engine"], info["tts_provider"], info["avatar_mode"]) == (
        s.app_env,
        s.reply_engine,
        s.tts_provider,
        s.avatar_mode,
    )
    assert info["scene_enabled"] is False
    assert (info["customer_id"], info["avatar_id"]) == ("shop_a", s.avatar_id)
    assert info["catalog_version"] == catalog_version
    assert info["power"] in ("ac", "battery", None)
    assert info["watchdog"] == {
        "enabled": s.watchdog_enabled,
        "silence_s": s.watchdog_silence_s,
        "frozen_s": s.watchdog_frozen_s,
        "autoskip_s": s.watchdog_autoskip_s,
    }
    assert FAKE_KEY not in text
