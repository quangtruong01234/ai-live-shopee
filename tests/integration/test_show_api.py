"""T024 show API, start part (004 US1; FR-001, FR-013, FR-019, FR-027, contracts/api.md §2-§4, analyze A4), 008
T019: the app on the model chain (startup check, first segment from entry 1, engine closed on shutdown), and 008 T039:
the chain on `/api/state`, `/health` and `/ws/control` (US3).

The app is built through `create_app` and its real lifespan, so the guard used by the show is the one the app wires up
at startup (with `PLATFORM_PHRASES_PATH` loaded), not one built by the test.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ai_live.app.main import create_app
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.guard import GuardConfigError
from ai_live.core.models import ROTATION_TOPICS, Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.director import script_runner as script_runner_module
from ai_live.products.models import ProductCatalog
from fixtures.content_builder import SPARSE_PRODUCT_NAME, build_docx, product_blocks, sparse_docx
from fixtures.fake_openai import FakeOpenAI, ModelRow, models_error, models_list, stream_reply

FAKE_KEY = "AIzaSyTEST-not-a-real-key-0123456789abcd"
PLATFORM_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"

HOST_UNAVAILABLE_MESSAGE = "Màn hình host chưa sẵn sàng. Mở /host và bấm Bắt đầu."
NO_CONTENT_MESSAGE = "Chưa nạp file nội dung sản phẩm hợp lệ."
SNAPSHOT_KEYS = {
    "show_id",
    "state",
    "mode",
    "started_at",
    "current",
    "next",
    "recent_blocked",
    "recent_errors",
    "available_topics",
    "stats",
}


@pytest.fixture
def show_settings(app_settings):
    return app_settings.model_copy(
        update={
            "platform_phrases_path": PLATFORM_PHRASES,
            "script_segment_min_sentences": 2,
            "script_segment_max_sentences": 3,
        }
    )


@pytest.fixture
def client(show_settings):
    with TestClient(create_app(show_settings)) as c:
        yield c


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


def _sentence_start(got: list[dict]) -> dict:
    return next(m for m in got if m["type"] == "sentence_start")


def _wait_host_ready(client: TestClient) -> None:
    for _ in range(500):
        if client.get("/health").json()["host_connected"]:
            return
    raise AssertionError("host never became ready")


def _start(client: TestClient) -> dict:
    """Start the show and check it started, so a failed start never leaves the test waiting on the host socket."""
    r = client.post("/api/show/start")
    assert r.status_code == 200, r.text
    return r.json()


def _session_files(settings) -> list[Path]:
    return [p for p in Path(settings.session_data_dir).rglob("*") if p.is_file()]


def _jsonl(settings, name: str) -> list[dict]:
    lines: list[dict] = []
    for path in Path(settings.session_data_dir).rglob(name):
        lines += [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    return lines


# --- POST /api/show/start ---


def test_start_returns_show_id_and_a_second_start_reuses_the_show(client, json_log_lines):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)

        first = client.post("/api/show/start")
        assert first.status_code == 200
        body = first.json()
        assert body["show_id"]
        assert body["state"] == "running"
        assert body["already_running"] is False

        played = [_sentence_start(_host_play_one(host))]
        again = client.post("/api/show/start")
        assert again.status_code == 200
        assert again.json() == {"show_id": body["show_id"], "state": "running", "already_running": True}
        played += [_sentence_start(_host_play_one(host)) for _ in range(2)]

    # Still one stream: every sentence is its own utterance, and the opening was requested once.
    ids = [m["utterance_id"] for m in played]
    assert len(set(ids)) == len(ids)
    assert all(m["seq"] == 0 for m in played)
    openings = [ln for ln in json_log_lines if ln["event"] == "segment_requested" and ln.get("topic") == "opening"]
    assert len(openings) == 1
    commands = [ln for ln in json_log_lines if ln["event"] == "control_command" and ln.get("command") == "show_start"]
    assert len(commands) == 2


def test_start_without_host_is_409_host_unavailable(client):
    r = client.post("/api/show/start")

    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "host_unavailable"
    assert body["message"] == HOST_UNAVAILABLE_MESSAGE


def test_start_with_host_connected_but_not_ready_is_409(client):
    with client.websocket_connect("/ws/host"):
        r = client.post("/api/show/start")

    assert r.status_code == 409
    assert r.json()["error"] == "host_unavailable"


def test_start_without_content_is_409_no_content(client):
    """A valid file is required at startup, so an empty catalog is installed to stand in for "no content"."""
    empty = ProductCatalog(version="empty", source_name="empty.docx", loaded_at=datetime.now(UTC), products=())
    client.portal.call(client.app.state.ctx.store.install, empty)
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        r = client.post("/api/show/start")

    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "no_content"
    assert body["message"] == NO_CONTENT_MESSAGE


# --- GET /api/show, GET /api/state ---


def test_state_has_null_show_before_start(client):
    body = client.get("/api/state").json()

    assert "show" in body
    assert body["show"] is None


def test_show_snapshot_and_state_while_running(client):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        show_id = _start(client)["show_id"]
        _host_play_one(host)

        snapshot = client.get("/api/show")
        state = client.get("/api/state").json()
        _host_play_one(host)

    assert snapshot.status_code == 200
    body = snapshot.json()
    assert set(body) >= SNAPSHOT_KEYS
    assert body["show_id"] == show_id
    assert body["state"] == "running"
    assert body["mode"] == "normal"
    assert body["started_at"]
    assert body["current"]["topic"] in {"opening", *(t.value for t in ROTATION_TOPICS)}
    assert set(body["stats"]) == {"segments", "gap_p95_s", "gap_max_s", "primary_share"}
    assert isinstance(body["recent_blocked"], list)
    assert isinstance(body["recent_errors"], list)
    primary = next(p for p in state["catalog"]["products"] if p["is_primary"])
    assert body["available_topics"][primary["id"]] == [t.value for t in ROTATION_TOPICS]
    assert state["show"]["show_id"] == show_id
    assert set(state["show"]) >= SNAPSHOT_KEYS


# --- POST /api/debug/speak while a show runs ---


def test_debug_speak_is_409_busy_while_show_runs(client):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        _start(client)
        _host_play_one(host)

        r = client.post("/api/debug/speak", json={"text": "Dạ chào cả nhà."})
        _host_play_one(host)

    assert r.status_code == 409
    assert r.json()["error"] == "busy"


# --- FR-027: no secret in session files or logs ---


def test_fake_api_key_never_reaches_session_files_or_logs(show_settings, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    s = show_settings.model_copy(update={"gemini_api_key": SecretStr(FAKE_KEY)})
    with TestClient(create_app(s)) as c:
        with c.websocket_connect("/ws/host") as host:
            host.send_json({"type": "ready"})
            _wait_host_ready(c)
            _start(c)
            for _ in range(3):
                _host_play_one(host)
            snapshot = c.get("/api/show").text

    files = _session_files(s)
    assert any(p.name == "script_sentences.jsonl" for p in files)
    for path in files:
        assert FAKE_KEY not in path.read_text("utf-8"), path.name
    assert FAKE_KEY not in capsys.readouterr().out
    assert FAKE_KEY not in snapshot


# --- analyze A4: the app's guard loads PLATFORM_PHRASES_PATH ---


def test_app_guard_blocks_platform_phrase_from_the_script(show_settings):
    blocked = "Anh chị bấm vào giỏ hàng nha."
    engine = FakeReplyEngine(
        script={
            (None, Topic.OPENING): [blocked, "Chào cả nhà, em là host AI nha.", "Hôm nay em có nhiều sản phẩm nha."]
        }
    )
    with TestClient(create_app(show_settings, reply_engine=engine)) as c:
        with c.websocket_connect("/ws/host") as host:
            host.send_json({"type": "ready"})
            _wait_host_ready(c)
            _start(c)
            texts = [_sentence_start(_host_play_one(host))["text"] for _ in range(2)]
            snapshot = c.get("/api/show").json()

    assert blocked not in texts
    assert texts[0] == "Chào cả nhà, em là host AI nha."
    reasons = [b["reason"] for b in snapshot["recent_blocked"]]
    assert "platform_phrase" in reasons
    sentences = _jsonl(show_settings, "script_sentences.jsonl")
    row = next(s for s in sentences if s["raw_text"] == blocked)
    assert row["status"] == "blocked"
    assert row["guard_reason"] == "platform_phrase"


def test_missing_platform_phrases_file_stops_startup(show_settings, tmp_path):
    s = show_settings.model_copy(update={"platform_phrases_path": tmp_path / "missing.txt"})

    with pytest.raises(GuardConfigError):
        with TestClient(create_app(s)):
            pass


# --- T041: pause, resume, skip and end with a show (US2; FR-015 to FR-017, contracts/api.md §2-§3) ---

CLOSING_LINES = ["Dạ em cảm ơn cả nhà đã xem live hôm nay nha.", "Hẹn gặp lại cả nhà ở buổi live sau nha."]


def _receive_json(ws) -> dict:
    """Next JSON message from the host socket, skipping audio frames."""
    while True:
        message = ws.receive()
        if message.get("text") is not None:
            return json.loads(message["text"])


def _next_start(ws) -> dict:
    while (data := _receive_json(ws))["type"] != "sentence_start":
        pass
    return data


def _finish_sentence(ws, start: dict) -> None:
    """Play out a sentence whose `playback_started` was already acked."""
    while _receive_json(ws)["type"] != "sentence_end":
        pass
    ws.send_json({"type": "sentence_played", "utterance_id": start["utterance_id"], "seq": start["seq"]})


def _ack_started(ws, start: dict) -> None:
    ws.send_json({"type": "playback_started", "utterance_id": start["utterance_id"], "seq": start["seq"]})


def _show_state(client: TestClient) -> str:
    return client.get("/api/show").json()["state"]


def _wait_show_state(client: TestClient, state: str) -> None:
    for _ in range(500):
        if _show_state(client) == state:
            return
    raise AssertionError(f"show never reached {state}")


def test_pause_resume_and_skip_bodies_carry_the_show(client, json_log_lines):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        show_id = _start(client)["show_id"]

        start = _next_start(host)
        _ack_started(host, start)
        r = client.post("/api/pause")
        assert r.status_code == 200
        assert r.json() == {"state": "paused", "show_state": "paused"}
        _finish_sentence(host, start)
        assert _show_state(client) == "paused"

        r = client.post("/api/resume")
        assert r.json() == {"state": "running", "show_state": "running"}
        resumed = _next_start(host)
        dropped = [
            ln for ln in json_log_lines if ln["event"] == "sentence_dropped" and ln["reason"] == "paused_discard"
        ]
        assert resumed["utterance_id"] == dropped[0]["utterance_id"]

        _ack_started(host, resumed)
        r = client.post("/api/skip")
        assert r.status_code == 200
        body = r.json()
        assert body["skipped_utterance_id"] == resumed["utterance_id"]
        assert body["skipped_segment_id"]
        while (data := _receive_json(host))["type"] != "stop":
            pass
        assert data["utterance_id"] == resumed["utterance_id"]

    applied = [ln for ln in json_log_lines if ln["event"] == "control_applied" and ln.get("command") == "skip"]
    assert len(applied) == 1
    assert applied[0]["latency_ms"] >= 0
    assert applied[0]["utterance_id"] == resumed["utterance_id"]
    assert applied[0]["segment_id"] == body["skipped_segment_id"]
    assert applied[0]["show_id"] == show_id
    for command in ("pause", "resume"):
        assert [ln for ln in json_log_lines if ln["event"] == "control_applied" and ln.get("command") == command]


def test_show_end_is_idempotent_without_a_show(client, json_log_lines):
    for _ in range(2):
        r = client.post("/api/show/end")
        assert r.status_code == 200
        assert r.json() == {"show_id": None, "state": "idle"}
    assert client.get("/api/show").json() is None
    commands = [ln for ln in json_log_lines if ln["event"] == "control_command" and ln.get("command") == "show_end"]
    assert len(commands) == 2
    assert not [ln for ln in json_log_lines if ln["event"] == "control_applied" and ln.get("command") == "show_end"]


@pytest.fixture
def closing_client(show_settings):
    """App whose fake engine has a fixed closing. Request it before `json_log_lines` (startup resets log handlers)."""
    engine = FakeReplyEngine(script={(None, Topic.CLOSING): CLOSING_LINES})
    with TestClient(create_app(show_settings, reply_engine=engine)) as c:
        yield c


def _wait_summary(settings, show_id: str) -> list[Path]:
    """The summary is written by the session log's worker thread just after the show turns `ended`."""
    for _ in range(200):
        if found := [p for p in _session_files(settings) if p.name == f"show_summary_{show_id}.json"]:
            return found
        time.sleep(0.01)
    raise AssertionError(f"show_summary_{show_id}.json was never written")


def test_end_while_paused_still_says_the_closing_and_start_makes_a_new_show(
    closing_client, show_settings, json_log_lines
):
    c = closing_client
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        show_id = _start(c)["show_id"]

        start = _next_start(host)
        _ack_started(host, start)
        assert c.post("/api/pause").json()["show_state"] == "paused"
        _finish_sentence(host, start)

        r = c.post("/api/show/end")
        assert r.status_code == 200
        assert r.json() == {"show_id": show_id, "state": "closing"}
        closing = [_sentence_start(_host_play_one(host)) for _ in CLOSING_LINES]
        assert [m["text"] for m in closing] == CLOSING_LINES
        _wait_show_state(c, "ended")

        # FR-017: an ended show does not start again by itself.
        requested = len([ln for ln in json_log_lines if ln["event"] == "segment_requested"])
        assert c.post("/api/show/end").json() == {"show_id": show_id, "state": "ended"}
        assert _show_state(c) == "ended"
        assert len([ln for ln in json_log_lines if ln["event"] == "segment_requested"]) == requested
        assert c.get("/api/state").json()["show"]["state"] == "ended"

        again = _start(c)
        assert again["show_id"] != show_id
        assert again["already_running"] is False
        _host_play_one(host)

    summaries = _wait_summary(show_settings, show_id)
    assert len(summaries) == 1
    summary = json.loads(summaries[0].read_text("utf-8"))
    assert summary["show_id"] == show_id
    assert summary["ended_by"] == "operator"
    commands = [ln for ln in json_log_lines if ln["event"] == "control_command" and ln.get("command") == "show_end"]
    assert len(commands) == 2
    applied = [ln for ln in json_log_lines if ln["event"] == "control_applied" and ln.get("command") == "show_end"]
    assert len(applied) == 1
    assert applied[0]["show_id"] == show_id
    states = [ln for ln in json_log_lines if ln["event"] == "show_state" and ln.get("show_id") == show_id]
    assert [s["state"] for s in states][-1] == "ended"
    assert states[-1]["reason"] == "operator"


# --- T049: faults and content changes during a show (US3; FR-020, FR-022, FR-024, contracts/api.md §3) ---

INTRO_TEXT = "Chào cả nhà, hôm nay em giới thiệu kem chống nắng."
DESCRIPTION_TEXT = "Kem chống nắng dạng sữa, thấm nhanh."


def _put_content(client: TestClient, data: bytes, filename: str = "demo.docx"):
    return client.put(
        "/api/content",
        content=data,
        headers={"Content-Type": "application/octet-stream", "X-Filename": filename},
    )


def _without_toner() -> bytes:
    return build_docx(
        [
            *product_blocks(
                "Kem chống nắng X",
                "chính",
                price=None,
                variants=[("50 ml", "250.000đ"), ("100 ml", "420.000đ")],
                promotions=("Giảm 30.000đ cho đơn từ 500.000đ",),
            ),
            *product_blocks("Sữa rửa mặt Y", "phụ", price="159.000đ", forbidden=()),
        ]
    )


def _wait_jsonl(settings, name: str, predicate) -> list[dict]:
    """Session files are written by the log's worker thread; wait for the lines the test needs."""
    for _ in range(300):
        lines = _jsonl(settings, name)
        if predicate(lines):
            return lines
        time.sleep(0.01)
    raise AssertionError(f"{name} never had the expected lines")


def test_debug_fault_llm_fails_the_next_narrate(client, show_settings):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        _start(client)
        _host_play_one(host)

        r = client.post("/api/debug/fault", json={"step": "llm", "mode": "error", "count": 1})
        assert r.status_code == 200
        for _ in range(5):
            _host_play_one(host)
        snapshot = client.get("/api/show").json()

    assert snapshot["state"] == "running"
    assert [(e["step"], e["kind"]) for e in snapshot["recent_errors"]] == [("llm", "fault_injected")]
    lines = _wait_jsonl(show_settings, "errors.jsonl", lambda lines: bool(lines))
    # Closing the host socket at the end of the `with` may add a render error; only the LLM one matters here.
    errors = [e for e in lines if e["step"] == "llm"]
    assert [(e["step"], e["type"]) for e in errors] == [("llm", "fault_injected")]
    segments = _wait_jsonl(
        show_settings, "segments.jsonl", lambda lines: any(s["segment_id"] == errors[0]["segment_id"] for s in lines)
    )
    failed = next(s for s in segments if s["segment_id"] == errors[0]["segment_id"])
    assert (failed["status"], failed["error_step"], failed["error_kind"]) == ("failed", "llm", "fault_injected")


def test_put_content_while_the_show_runs_applies_from_the_next_segment(client, show_settings):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        _start(client)
        old_catalog = client.get("/api/state").json()["catalog"]
        toner = next(p["id"] for p in old_catalog["products"] if p["name"] == "Toner Z")

        first = _next_start(host)
        _ack_started(host, first)
        speaking = client.get("/api/show").json()["current"]
        assert speaking["topic"] == "opening"
        r = _put_content(client, _without_toner(), "moi.docx")
        assert r.status_code == 200, r.text
        new_version = r.json()["version"]
        assert new_version != old_catalog["version"]
        # The running show follows the new content at once (contracts/api.md §3).
        snapshot = client.get("/api/show").json()
        assert toner not in snapshot["available_topics"]
        assert snapshot["current"]["segment_id"] == speaking["segment_id"]

        _finish_sentence(host, first)
        later = [_sentence_start(_host_play_one(host)) for _ in range(5)]
        assert client.get("/api/show").json()["state"] == "running"

    texts = [m["text"] for m in later]
    assert "Toner Z" not in " ".join(texts)
    segments = _wait_jsonl(show_settings, "segments.jsonl", lambda lines: len(lines) >= 2)
    by_id = {s["segment_id"]: s for s in segments}
    opening = by_id[speaking["segment_id"]]
    # The segment speaking during the upload finishes on the old content.
    assert opening["status"] == "done"
    assert opening["catalog_version"] == old_catalog["version"]
    assert opening["sentences"]["spoken"] == 2
    sentences = _jsonl(show_settings, "script_sentences.jsonl")
    later_segments = {s["segment_id"] for s in sentences if s["utterance_id"] in {m["utterance_id"] for m in later}}
    later_segments.discard(speaking["segment_id"])
    assert later_segments
    for segment_id in later_segments:
        if segment_id in by_id:
            assert by_id[segment_id]["catalog_version"] == new_version
            assert by_id[segment_id]["product_id"] != toner
    stale = [s for s in segments if s["segment_id"] != speaking["segment_id"] and s["catalog_version"] != new_version]
    assert all(s["status"] == "discarded" for s in stale)


def test_bad_file_while_the_show_runs_keeps_the_old_content(client):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        _start(client)
        _host_play_one(host)
        before = client.get("/api/state").json()["catalog"]
        topics = client.get("/api/show").json()["available_topics"]

        r = _put_content(client, build_docx(product_blocks("Kem X", price="250k", forbidden=None)))
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "content_invalid"
        assert sorted(d["code"] for d in body["details"]) == ["missing_section", "price_format"]

        played = [_sentence_start(_host_play_one(host)) for _ in range(3)]
        snapshot = client.get("/api/show").json()

    assert client.get("/api/state").json()["catalog"] == before
    assert snapshot["state"] == "running"
    assert snapshot["available_topics"] == topics
    assert len({m["utterance_id"] for m in played}) == 3


@pytest.fixture
def fallback_client(show_settings):
    """App that enters fallback after one LLM failure. Request it before `json_log_lines`."""
    s = show_settings.model_copy(update={"script_fallback_after": 1})
    with TestClient(create_app(s)) as c:
        yield c


def test_snapshot_mode_turns_fallback_and_the_host_reads_product_text(fallback_client, json_log_lines):
    c = fallback_client
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        show_id = _start(c)["show_id"]
        _host_play_one(host)
        # Enough faults that every retry before a fallback segment fails too: the show stays in fallback.
        assert c.post("/api/debug/fault", json={"step": "llm", "mode": "error", "count": 50}).status_code == 200

        texts: list[str] = []
        for _ in range(12):
            texts.append(_sentence_start(_host_play_one(host))["text"])
            if texts[-1] == INTRO_TEXT:
                break
        snapshot = c.get("/api/show").json()
        texts.append(_sentence_start(_host_play_one(host))["text"])

    assert INTRO_TEXT in texts
    assert texts[-1] == DESCRIPTION_TEXT
    assert snapshot["mode"] == "fallback"
    assert snapshot["state"] == "running"
    states = [ln for ln in json_log_lines if ln["event"] == "show_state" and ln.get("show_id") == show_id]
    assert any(s.get("mode") == "fallback" and s.get("reason") == "fallback_after_failures" for s in states)
    changes = [ln for ln in json_log_lines if ln["event"] == "mode_changed"]
    assert changes[0]["from"] == "normal"
    assert changes[0]["to"] == "fallback"


# --- T063: POST /api/show/next (US5; FR-018, contracts/api.md §2) ---

SHOW_NOT_RUNNING_MESSAGE = "Show chưa chạy."
TOPIC_UNAVAILABLE_MESSAGE = "Sản phẩm này không có dữ liệu cho chủ đề đã chọn."


@pytest.fixture
def sparse_client(show_settings, tmp_path):
    """App whose secondary product has no specs, FAQ or promotions. Request it before `json_log_lines`."""
    path = tmp_path / "sparse.docx"
    path.write_bytes(sparse_docx())
    with TestClient(create_app(show_settings.model_copy(update={"product_data_path": path}))) as c:
        yield c


def _product_ids(client: TestClient) -> dict[str, str]:
    """Product name -> id, from the loaded catalog."""
    return {p["name"]: p["id"] for p in client.get("/api/state").json()["catalog"]["products"]}


def test_show_next_while_running_returns_the_operator_slot_and_logs_the_command(sparse_client, json_log_lines):
    c = sparse_client
    ids = _product_ids(c)
    primary = next(p["id"] for p in c.get("/api/state").json()["catalog"]["products"] if p["is_primary"])
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        show_id = _start(c)["show_id"]
        _ack_started(host, _next_start(host))

        r = c.post("/api/show/next", json={"product_id": ids[SPARSE_PRODUCT_NAME], "topic": "price"})
        assert r.status_code == 200, r.text
        assert r.json() == {"product_id": ids[SPARSE_PRODUCT_NAME], "topic": "price", "origin": "operator"}
        nxt = c.get("/api/show").json()["next"]
        assert (nxt["product_id"], nxt["topic"], nxt["origin"]) == (ids[SPARSE_PRODUCT_NAME], "price", "operator")

        # Topic only: the first product that has it, primary first (research R6).
        r = c.post("/api/show/next", json={"topic": "promotion"})
        assert r.status_code == 200, r.text
        assert r.json() == {"product_id": primary, "topic": "promotion", "origin": "operator"}

        # Product only: that product's next topic.
        r = c.post("/api/show/next", json={"product_id": ids[SPARSE_PRODUCT_NAME]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["product_id"] == ids[SPARSE_PRODUCT_NAME]
        assert body["origin"] == "operator"
        assert body["topic"] in c.get("/api/show").json()["available_topics"][ids[SPARSE_PRODUCT_NAME]]

    commands = [ln for ln in json_log_lines if ln["event"] == "control_command" and ln.get("command") == "show_next"]
    assert len(commands) == 3
    applied = [ln for ln in json_log_lines if ln["event"] == "control_applied" and ln.get("command") == "show_next"]
    assert len(applied) == 3
    assert all(a["show_id"] == show_id and a["latency_ms"] >= 0 for a in applied)
    assert (applied[0]["product_id"], applied[0]["topic"]) == (ids[SPARSE_PRODUCT_NAME], "price")


def test_show_next_while_paused_is_accepted(client):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        _start(client)
        _ack_started(host, _next_start(host))
        assert client.post("/api/pause").json()["show_state"] == "paused"

        r = client.post("/api/show/next", json={"topic": "faq"})

    assert r.status_code == 200, r.text
    assert r.json()["origin"] == "operator"


def test_show_next_without_a_show_is_409_show_not_running(client, json_log_lines):
    r = client.post("/api/show/next", json={"topic": "price"})

    assert r.status_code == 409
    assert r.json()["error"] == "show_not_running"
    assert r.json()["message"] == SHOW_NOT_RUNNING_MESSAGE
    assert [ln for ln in json_log_lines if ln["event"] == "control_command" and ln.get("command") == "show_next"]
    assert not [ln for ln in json_log_lines if ln["event"] == "control_applied" and ln.get("command") == "show_next"]


def test_show_next_while_closing_is_409_show_not_running(closing_client):
    c = closing_client
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        _start(c)
        _ack_started(host, _next_start(host))
        assert c.post("/api/show/end").json()["state"] == "closing"

        r = c.post("/api/show/next", json={"topic": "price"})

    assert r.status_code == 409
    assert r.json()["error"] == "show_not_running"


def test_show_next_combination_without_data_is_422_topic_unavailable(sparse_client):
    c = sparse_client
    sparse = _product_ids(c)[SPARSE_PRODUCT_NAME]
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        _start(c)
        _ack_started(host, _next_start(host))
        before = c.get("/api/show").json()["next"]

        refused = [
            c.post("/api/show/next", json={"product_id": sparse, "topic": "promotion"}),  # US5 #2
            c.post("/api/show/next", json={"product_id": "khong-co", "topic": "price"}),  # unknown product
            c.post("/api/show/next", json={"product_id": "khong-co"}),
            c.post("/api/show/next", json={"topic": "opening"}),  # not a choice: the show owns it
        ]
        after = c.get("/api/show").json()["next"]

    for r in refused:
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "topic_unavailable"
        assert r.json()["message"] == TOPIC_UNAVAILABLE_MESSAGE
    assert after is None or after.get("origin") != "operator"
    assert before is None or before.get("origin") != "operator"


@pytest.mark.parametrize("body", [{}, {"topic": "khong-co"}, {"product_id": None, "topic": None}, {"product_id": 5}])
def test_show_next_with_a_bad_body_is_422_validation_error(client, body):
    r = client.post("/api/show/next", json=body)

    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


def test_available_topics_lists_only_topics_with_data_and_each_is_choosable(sparse_client):
    c = sparse_client
    ids = _product_ids(c)
    sparse = ids[SPARSE_PRODUCT_NAME]
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        _start(c)
        _ack_started(host, _next_start(host))
        available = c.get("/api/show").json()["available_topics"]

        assert set(available) == set(ids.values())
        assert {"specs", "faq", "promotion"}.isdisjoint(available[sparse])
        assert "opening" not in available[sparse] and "closing" not in available[sparse]
        primary = next(pid for name, pid in ids.items() if name != SPARSE_PRODUCT_NAME)
        assert available[primary] == [t.value for t in ROTATION_TOPICS]
        # The picker never shows a combination the server would refuse, and refuses every one it hides.
        for topic in ROTATION_TOPICS:
            r = c.post("/api/show/next", json={"product_id": sparse, "topic": topic.value})
            expected = 200 if topic.value in available[sparse] else 422
            assert r.status_code == expected, (topic, r.text)


# --- 008 US1: the app on the model chain (T019; FR-006, FR-011, US1 #6) ---

SEALION_ROUTE = "cloudflare/gemma-sea-lion-v4-27b"


@pytest.fixture
def chain_settings(show_settings, with_chain):
    return with_chain(show_settings)


def _keys(settings) -> list[str]:
    return [settings.freellmapi_key.get_secret_value(), settings.groq_api_key.get_secret_value()]


def _chain_provider(settings) -> FakeOpenAI:
    """Both entries pass the startup check; only entry 1 is scripted to speak, with lines that never repeat."""
    first, second = settings.llm_chain
    fake = FakeOpenAI()
    fake.models(first.base_url, models_list(ModelRow(first.model, available=True)))
    fake.models(second.base_url, models_list(second.model))
    lines = [
        stream_reply(f"Dạ câu {n} chào cả nhà nha. ", f"Dạ câu {n} mời cả nhà ở lại nha.", routed_via=SEALION_ROUTE)
        for n in range(1, 40)
    ]
    fake.chat(first.base_url, first.model, *lines)
    return fake


def test_chain_preflight_failure_stops_startup_without_leaking_a_key(chain_settings, make_chain_engine, capsys):
    first, second = chain_settings.llm_chain
    fake = FakeOpenAI()
    fake.models(first.base_url, models_error(401))
    fake.models(second.base_url, models_list("another-model"))
    engine = make_chain_engine(chain_settings, fake.transport)
    served: list[int] = []

    with pytest.raises(ReplyEngineError) as info:
        with TestClient(create_app(chain_settings, reply_engine=engine)) as c:
            served.append(c.get("/health").status_code)

    # US1 #6, FR-011: the app never served a request, and the message names every bad entry (contracts/config.md §4).
    assert served == []
    assert info.value.kind == "config_error"
    message = str(info.value)
    assert "LLM_CHAIN mục 1 (sealion)" in message and "FREELLMAPI_KEY" in message and "401" in message
    assert "LLM_CHAIN mục 2 (qwen)" in message and second.model in message
    # One GET /models per (base_url, key_env), and no turn was ever started.
    assert len(fake.models_requests(first.base_url)) == 1
    assert len(fake.models_requests(second.base_url)) == 1
    assert fake.chat_requests() == []
    captured = capsys.readouterr()
    for key in _keys(chain_settings):
        assert key not in message
        assert key not in captured.out and key not in captured.err


@pytest.fixture
def chain_app(chain_settings, make_chain_engine):
    """A client of the app on the chain, with the fake provider and the engine kept for checks."""
    fake = _chain_provider(chain_settings)
    engine = make_chain_engine(chain_settings, fake.transport)
    with TestClient(create_app(chain_settings, reply_engine=engine)) as c:
        yield c, fake


def test_chain_preflight_passes_then_the_show_speaks_with_entry_one(chain_app, chain_settings, json_log_lines):
    c, fake = chain_app
    first, second = chain_settings.llm_chain
    # Checked before the first request, so it is done by the time the client is up (FR-011).
    assert len(fake.models_requests(first.base_url)) == 1
    assert len(fake.models_requests(second.base_url)) == 1
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        _start(c)
        start = _sentence_start(_host_play_one(host))

    # FR-006: the first segment was written by entry 1; entry 2 was never asked.
    assert start["text"] == "Dạ câu 1 chào cả nhà nha."
    assert fake.chat_requests(first.base_url, first.model)
    assert fake.chat_requests(second.base_url) == []
    assert fake.unscripted == []
    # The 004 milestones are still there for the sentence the chain wrote.
    requested = [ln for ln in json_log_lines if ln["event"] == "segment_requested" and ln.get("topic") == "opening"]
    assert len(requested) == 1
    firsts = [ln for ln in json_log_lines if ln["event"] == "llm_first_sentence"]
    mine = [ln for ln in firsts if ln["utterance_id"] == start["utterance_id"]]
    assert len(mine) == 1 and mine[0]["segment_id"] == requested[0]["segment_id"]


def test_chain_engine_is_closed_on_app_shutdown(chain_settings, make_chain_engine):
    fake = _chain_provider(chain_settings)
    engine = make_chain_engine(chain_settings, fake.transport)
    closed: list[bool] = []
    real_aclose = engine.aclose

    async def recording_aclose() -> None:
        closed.append(True)
        await real_aclose()

    engine.aclose = recording_aclose
    with TestClient(create_app(chain_settings, reply_engine=engine)) as c:
        assert c.get("/health").status_code == 200
        assert closed == []

    assert closed == [True]


# --- 008 US2: per-entry faults through POST /api/debug/fault (T030; FR-016, contracts/api.md §1) ---


def test_debug_fault_with_entry_queues_it_and_returns_pending(chain_app):
    c, _ = chain_app
    r = c.post("/api/debug/fault", json={"step": "llm", "mode": "rate_limited", "count": 3, "entry": "sealion"})
    assert r.status_code == 200, r.text
    assert r.json() == {"step": "llm", "mode": "rate_limited", "count": 3, "entry": "sealion", "pending": 3}
    # `pending` counts what is queued for that entry, so a second call adds up.
    r = c.post("/api/debug/fault", json={"step": "llm", "mode": "interrupted", "count": 2, "entry": "sealion"})
    assert r.status_code == 200, r.text
    assert r.json()["pending"] == 5
    # `timeout` works for both forms; the other entry has its own queue.
    r = c.post("/api/debug/fault", json={"step": "llm", "mode": "timeout", "entry": "qwen"})
    assert r.status_code == 200, r.text
    assert r.json() == {"step": "llm", "mode": "timeout", "count": 1, "entry": "qwen", "pending": 1}
    faults = c.app.state.ctx.director.faults
    assert (faults.pending_entry("sealion"), faults.pending_entry("qwen")) == (5, 1)
    # A per-entry fault is not a step fault: the next turn does not fail before the engine runs.
    assert faults.pending("llm") == 0


@pytest.mark.parametrize("mode", ["rate_limited", "overloaded", "timeout", "empty", "wrong_platform", "interrupted"])
def test_debug_fault_accepts_every_entry_mode(chain_app, mode):
    c, _ = chain_app
    r = c.post("/api/debug/fault", json={"step": "llm", "mode": mode, "entry": "qwen"})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == mode and r.json()["pending"] == 1


def test_debug_fault_step_form_is_unchanged_on_the_chain(chain_app):
    c, _ = chain_app
    r = c.post("/api/debug/fault", json={"step": "llm", "mode": "error", "count": 2})
    assert r.status_code == 200, r.text
    # The 004 response shape, without `entry` / `pending`.
    assert r.json() == {"step": "llm", "mode": "error", "count": 2}
    assert c.app.state.ctx.director.faults.pending("llm") == 2


@pytest.mark.parametrize(
    ("body", "error"),
    [
        # The entry is not in LLM_CHAIN.
        ({"step": "llm", "mode": "rate_limited", "entry": "gptoss"}, "unknown_entry"),
        # An entry-only mode without an entry.
        ({"step": "llm", "mode": "rate_limited"}, "validation_error"),
        ({"step": "llm", "mode": "interrupted", "count": 2}, "validation_error"),
        # An entry with a step-wide-only mode, or with a step other than llm.
        ({"step": "llm", "mode": "error", "entry": "sealion"}, "validation_error"),
        ({"step": "tts", "mode": "timeout", "entry": "sealion"}, "validation_error"),
        ({"step": "render", "mode": "timeout", "entry": "sealion"}, "validation_error"),
        # An entry-only mode never applies to tts / render.
        ({"step": "tts", "mode": "overloaded"}, "validation_error"),
        # Bad counts still fail, with an entry too.
        ({"step": "llm", "mode": "rate_limited", "count": 0, "entry": "sealion"}, "validation_error"),
    ],
)
def test_debug_fault_with_a_bad_entry_body_is_422(chain_app, body, error):
    c, _ = chain_app
    r = c.post("/api/debug/fault", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == error
    assert r.json()["message"]
    faults = c.app.state.ctx.director.faults
    # Nothing was queued anywhere.
    assert faults.pending_entry("sealion") == faults.pending_entry("gptoss") == 0
    assert faults.pending("llm") == faults.pending("tts") == faults.pending("render") == 0


def test_debug_fault_with_entry_is_422_when_the_engine_is_not_the_chain(client):
    r = client.post("/api/debug/fault", json={"step": "llm", "mode": "rate_limited", "entry": "sealion"})
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "chain_not_active"
    assert "REPLY_ENGINE" in r.json()["message"]
    # Even `timeout`, valid without an entry, is refused once it names an entry.
    r = client.post("/api/debug/fault", json={"step": "llm", "mode": "timeout", "entry": "sealion"})
    assert r.status_code == 422
    assert client.app.state.ctx.director.faults.pending("llm") == 0


def test_debug_fault_with_entry_is_404_outside_dev(chain_settings, make_chain_engine):
    settings = chain_settings.model_copy(update={"app_env": "demo"})
    fake = _chain_provider(settings)
    engine = make_chain_engine(settings, fake.transport)
    with TestClient(create_app(settings, reply_engine=engine)) as c:
        r = c.post("/api/debug/fault", json={"step": "llm", "mode": "rate_limited", "entry": "sealion"})
    assert r.status_code == 404


class _WiredChain:
    """The app builds its own chain engine through `create_reply_engine` (T035), over the fake provider's transport."""

    def __init__(self, monkeypatch, settings) -> None:
        from ai_live.app import main as main_module
        from ai_live.brain.chain_engine import ChainReplyEngine

        self.fake = _chain_provider(settings)
        self.hooks: list = []

        def create(settings, *, only=None, fault_hook=None):
            # Same call as the real factory, plus the fake transport (`from_settings` takes one for tests).
            self.hooks.append(fault_hook)
            transport = self.fake.transport
            return ChainReplyEngine.from_settings(settings, only=only, fault_hook=fault_hook, transport=transport)

        monkeypatch.setattr(main_module, "create_reply_engine", create)


@pytest.fixture
def wired_chain_client(monkeypatch, chain_settings):
    """A dev app whose chain engine comes from `main.py`'s own wiring. Request it before `json_log_lines`."""
    wired = _WiredChain(monkeypatch, chain_settings)
    with TestClient(create_app(chain_settings)) as c:
        yield c, wired


def test_main_passes_the_fault_injector_as_the_chain_hook_only_in_dev(monkeypatch, chain_settings):
    wired = _WiredChain(monkeypatch, chain_settings)
    with TestClient(create_app(chain_settings)) as c:
        director = c.app.state.ctx.director
        # FR-016, research R8: the hook is the director's own injector, so the route and the engine share one queue.
        (hook,) = wired.hooks
        assert hook is not None and hook.__self__ is director.faults
        assert hook.__func__ is type(director.faults).take_entry

    demo = chain_settings.model_copy(update={"app_env": "demo"})
    wired = _WiredChain(monkeypatch, demo)
    with TestClient(create_app(demo)) as c:
        assert c.get("/health").status_code == 200
    # Outside dev the engine gets no hook, so no queued fault could ever reach a real provider call.
    assert wired.hooks == [None]


def test_a_queued_entry_fault_makes_the_next_turn_switch_entry(wired_chain_client, chain_settings, json_log_lines):
    c, wired = wired_chain_client
    fake = wired.fake
    first, second = chain_settings.llm_chain
    fake.chat(
        second.base_url,
        second.model,
        *[
            stream_reply(f"Dạ Qwen đoạn {n} chào cả nhà nha. ", f"Dạ Qwen đoạn {n} mời cả nhà nha.")
            for n in range(1, 40)
        ],
    )
    with c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(c)
        r = c.post("/api/debug/fault", json={"step": "llm", "mode": "rate_limited", "entry": first.label})
        assert r.status_code == 200 and r.json()["pending"] == 1
        _start(c)
        start = _sentence_start(_host_play_one(host))
    pending_after = c.app.state.ctx.director.faults.pending_entry(first.label)

    # FR-016: the fault stood in for entry 1's answer; entry 1 was never called, entry 2 spoke the first segment.
    assert start["text"] == "Dạ Qwen đoạn 1 chào cả nhà nha."
    assert fake.chat_requests(first.base_url, first.model) == []
    assert fake.chat_requests(second.base_url, second.model)
    assert fake.unscripted == []
    assert pending_after == 0
    attempts = [ln for ln in json_log_lines if ln["event"] == "llm_attempt" and ln["label"] == first.label]
    assert attempts and (attempts[0]["outcome"], attempts[0]["reason"], attempts[0]["injected"]) == (
        "failed",
        "rate_limited",
        True,
    )
    switches = [
        (ln["from_label"], ln["to_label"], ln["reason"]) for ln in json_log_lines if ln["event"] == "llm_switch"
    ]
    assert switches[0] == (first.label, second.label, "rate_limited")
    # No key in any log line.
    assert not any(key in json.dumps(ln, ensure_ascii=False) for ln in json_log_lines for key in _keys(chain_settings))


# --- 008 US3: the chain on /api/state, /health and /ws/control (T039; FR-017, SC-007, contracts/api.md §1-§2) ---


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _control_until(ws, predicate) -> list[dict]:
    """Every control message up to and including the first one `predicate` accepts."""
    got: list[dict] = []
    while True:
        data = _receive_json(ws)
        got.append(data)
        if predicate(data):
            return got


def _chain_rows(settings, **by_label: dict) -> list[dict]:
    """`ChainSnapshot.entries` of `settings.llm_chain`, every entry ready unless `by_label` says otherwise."""
    rows = []
    for entry in settings.llm_chain:
        row = {
            "label": entry.label,
            "model": entry.model,
            "platform": entry.platform,
            "position": entry.position,
            "status": "ready",
            "reason": None,
            "retry_at": None,
        }
        rows.append({**row, **by_label.get(entry.label, {})})
    return rows


def test_state_and_health_without_the_chain_have_a_null_llm_chain_and_the_engine_name(client, show_settings):
    state = client.get("/api/state").json()
    assert "llm_chain" in state and state["llm_chain"] is None

    r = client.get("/health")
    assert r.status_code == 200
    health = r.json()
    assert health["reply_engine"] == show_settings.reply_engine == "fake"
    # `llm_ready` only exists on the chain (contracts/api.md §1).
    assert "llm_ready" not in health

    with client.websocket_connect("/ws/control") as control:
        first = _receive_json(control)
    assert first["type"] == "state"
    assert "llm_chain" in first and first["llm_chain"] is None


def test_state_and_health_on_the_chain_before_any_turn(chain_app, chain_settings):
    c, _ = chain_app
    expected = {"entries": _chain_rows(chain_settings), "last_entry": None, "using_backup": False}
    assert c.get("/api/state").json()["llm_chain"] == expected

    r = c.get("/health")
    assert r.status_code == 200
    assert (r.json()["reply_engine"], r.json()["llm_ready"]) == ("chain", True)

    # The `state` message on connect carries the same snapshot as GET /api/state (contracts/api.md §2).
    with c.websocket_connect("/ws/control") as control:
        first = _receive_json(control)
    assert first["type"] == "state"
    assert first["llm_chain"] == expected


def test_a_switch_reaches_the_control_page_as_llm_chain_within_2_s(wired_chain_client, chain_settings, json_log_lines):
    c, wired = wired_chain_client
    first, second = chain_settings.llm_chain
    wired.fake.chat(
        second.base_url,
        second.model,
        *[
            stream_reply(f"Dạ Qwen đoạn {n} chào cả nhà nha. ", f"Dạ Qwen đoạn {n} mời cả nhà nha.")
            for n in range(1, 40)
        ],
    )
    with c.websocket_connect("/ws/control") as control:
        state = _receive_json(control)
        assert state["type"] == "state"
        assert (state["llm_chain"]["last_entry"], state["llm_chain"]["using_backup"]) == (None, False)
        with c.websocket_connect("/ws/host") as host:
            host.send_json({"type": "ready"})
            _wait_host_ready(c)
            r = c.post("/api/debug/fault", json={"step": "llm", "mode": "rate_limited", "entry": first.label})
            assert r.status_code == 200
            _start(c)
            start = _sentence_start(_host_play_one(host))
            # A known later event bounds the read: the switch happened before the first sentence was written.
            assert c.post("/api/pause").status_code == 200
            got = _control_until(control, lambda m: m["type"] == "show_state" and m["state"] == "paused")
            state_after = c.get("/api/state").json()["llm_chain"]

    assert start["text"] == "Dạ Qwen đoạn 1 chào cả nhà nha."
    chain_messages = [m for m in got if m["type"] == "llm_chain"]
    backup = next(m for m in chain_messages if m["using_backup"])
    assert backup["last_entry"] == second.label
    resting = backup["entries"][0]
    assert (resting["label"], resting["status"], resting["reason"]) == (first.label, "resting", "rate_limited")
    assert resting["retry_at"] is not None
    assert backup["entries"][1] == _chain_rows(chain_settings)[1]
    # SC-007: on the page within 2 s of the switch the log recorded.
    switch = next(ln for ln in json_log_lines if ln["event"] == "llm_switch")
    assert (_ts(backup["ts"]) - _ts(switch["ts"])).total_seconds() <= 2.0
    # GET /api/state follows the same snapshot.
    assert (state_after["last_entry"], state_after["using_backup"]) == (second.label, True)
    assert state_after["entries"] == backup["entries"]


def test_with_every_entry_resting_the_show_still_starts_and_enters_fallback(monkeypatch, chain_settings):
    monkeypatch.setattr(script_runner_module, "LLM_RETRY_DELAY_S", 0.05)
    settings = chain_settings.model_copy(update={"script_fallback_after": 1})
    wired = _WiredChain(monkeypatch, settings)
    labels = [entry.label for entry in settings.llm_chain]
    with TestClient(create_app(settings)) as c:
        director = c.app.state.ctx.director
        # A comment reply finds every entry rate limited, so the whole chain rests before the show starts.
        for label in labels:
            r = c.post("/api/debug/fault", json={"step": "llm", "mode": "rate_limited", "entry": label})
            assert r.status_code == 200
        assert c.post("/api/comments", json={"author": "Lan", "text": "giá bao nhiêu vậy shop?"}).status_code == 202
        deadline = time.monotonic() + 5.0
        while any(director.faults.pending_entry(label) for label in labels) or director.busy:
            assert time.monotonic() < deadline, "the reply turn never tried every entry"
            time.sleep(0.01)

        before = c.get("/health")
        rows = c.get("/api/state").json()["llm_chain"]["entries"]
        with c.websocket_connect("/ws/host") as host:
            host.send_json({"type": "ready"})
            _wait_host_ready(c)
            _start(c)
            deadline = time.monotonic() + 8.0
            while c.get("/api/show").json()["mode"] != "fallback":
                assert time.monotonic() < deadline, "the show never entered fallback"
                time.sleep(0.02)
            during = c.get("/health")

    # Edge case of the spec: the operator sees it before starting, the start still works, and the show reads the
    # product text as in 004 (ADR-032); /health stays 200 so a monitor does not restart the app.
    assert before.status_code == 200
    assert (before.json()["reply_engine"], before.json()["llm_ready"]) == ("chain", False)
    assert all(row["status"] == "resting" for row in rows)
    assert during.status_code == 200 and during.json()["llm_ready"] is False
    # No provider was ever called: the faults stood in for the first tries, then every entry rested.
    for entry in settings.llm_chain:
        assert wired.fake.chat_requests(entry.base_url) == []


# --- 008 US3: the "Model LLM" area and the dev fault form of the control page (T046; FR-020, contracts/api.md §3) ---


def test_the_control_page_finds_the_fault_form_only_in_dev(show_settings):
    """control.js shows its fault form when GET on the POST-only debug route answers 405, and hides it on 404."""
    with TestClient(create_app(show_settings)) as c:
        assert c.get("/api/debug/fault").status_code == 405
    with TestClient(create_app(show_settings.model_copy(update={"app_env": "demo"}))) as c:
        assert c.get("/api/debug/fault").status_code == 404


def test_the_model_area_of_the_control_page_has_no_button_and_every_reason_label(client):
    html = client.get("/static/control.html").text
    start = html.index('id="llm-panel"')
    panel = html[start : html.index("</section>", start)]
    # FR-020: the operator watches the chain, never steers it from the page.
    assert "<button" not in panel and "hidden" in html[start - 40 : start + 40]
    js = client.get("/static/control.js").text
    for reason, label in {
        "rate_limited": "hết hạn mức",
        "overloaded": "quá tải / lỗi máy chủ",
        "empty": "trả về rỗng",
        "connection": "lỗi kết nối",
        "timeout": "quá giờ chờ câu đầu",
        "rejected": "bị từ chối (key/model)",
        "wrong_platform": "sai nền tảng",
        "blocked": "bị bộ lọc nội dung chặn",
        "interrupted": "đứt giữa chừng",
    }.items():
        assert f'{reason}: "{label}"' in js
    assert "Không có model nào sẵn sàng; show sẽ vào chế độ dự phòng" in html
    assert "Đang dùng model dự phòng" in html
