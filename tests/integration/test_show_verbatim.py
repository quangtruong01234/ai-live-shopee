"""007 US4 T043/T044: the `verbatim` show for the backup video (FR-020, research R6) and no backup-video route (FR-021).

A `verbatim` show reads the customer's own `intro` then `description` through cleaning, the guard, TTS and the realtime
renderer, exactly like the 004 fallback (R10), but never asks the engine and stays in `normal` mode.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from ai_live.app.main import create_app
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.director.script_runner import CLOSING_FALLBACK_SENTENCE
from fixtures.content_builder import build_docx, product_blocks

PLATFORM_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"
CLAIM_PHRASES = PLATFORM_PHRASES.with_name("claim_phrases.txt")

PRIMARY_INTRO = "Chào cả nhà, hôm nay em giới thiệu kem chống nắng X. Kem này dùng hằng ngày rất tiện."
PRIMARY_DESCRIPTION = "Kem dạng sữa nên thấm rất nhanh trên da."
SECONDARY = {
    "Sữa rửa mặt Y": ("Tiếp theo là sữa rửa mặt Y của shop.", "Sữa rửa mặt Y tạo bọt mịn khi rửa."),
    "Toner Z": ("Còn đây là toner Z của shop mình.", "Toner Z có dạng nước trong và mát."),
}


def _sentences(*texts: str) -> list[str]:
    pool: list[str] = []
    for text in texts:
        splitter = SentenceSplitter()
        pool += splitter.feed(text)
        pool += splitter.flush()
    return pool


def _verbatim_docx() -> bytes:
    blocks = product_blocks("Kem chống nắng X", "chính", intro=PRIMARY_INTRO, description=PRIMARY_DESCRIPTION)
    for name, (intro, description) in SECONDARY.items():
        blocks += product_blocks(name, "phụ", intro=intro, description=description, price="159.000đ", forbidden=())
    return build_docx(blocks)


@pytest.fixture
def verbatim_settings(app_settings, tmp_path):
    content = tmp_path / "verbatim.docx"
    content.write_bytes(_verbatim_docx())
    return app_settings.model_copy(
        update={
            "product_data_path": content,
            "platform_phrases_path": PLATFORM_PHRASES,
            "claim_phrases_path": CLAIM_PHRASES,
            "script_segment_min_sentences": 2,
            "script_segment_max_sentences": 3,
            "backup_video_dir": tmp_path / "backup",
        }
    )


@pytest.fixture
def engine():
    return FakeReplyEngine()


@pytest.fixture
def client(verbatim_settings, engine):
    with TestClient(create_app(verbatim_settings, reply_engine=engine)) as c:
        yield c


def _receive_json(ws) -> dict:
    while True:
        message = ws.receive()
        if message.get("text") is not None:
            return json.loads(message["text"])


def _play_one(ws) -> str:
    """Play one sentence like the host page does; returns its text."""
    while (start := _receive_json(ws))["type"] != "sentence_start":
        pass
    ws.send_json({"type": "playback_started", "utterance_id": start["utterance_id"], "seq": start["seq"]})
    while _receive_json(ws)["type"] != "sentence_end":
        pass
    ws.send_json({"type": "sentence_played", "utterance_id": start["utterance_id"], "seq": start["seq"]})
    return start["text"]


def _wait_host_ready(client: TestClient) -> None:
    for _ in range(500):
        if client.get("/health").json()["host_connected"]:
            return
    raise AssertionError("host never became ready")


def _wait_show_state(client: TestClient, state: str) -> None:
    for _ in range(500):
        if client.get("/api/show").json()["state"] == state:
            return
        time.sleep(0.01)
    raise AssertionError(f"show never reached {state}")


def _jsonl(settings, name: str) -> list[dict]:
    lines: list[dict] = []
    for path in Path(settings.session_data_dir).rglob(name):
        lines += [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    return lines


# --- T043: content `verbatim` (FR-020, research R6, contracts/api.md §2) ---


def test_verbatim_show_reads_the_product_text_and_never_asks_the_engine(
    client, engine, verbatim_settings, json_log_lines
):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)

        r = client.post("/api/show/start", json={"content": "verbatim"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "verbatim"
        assert body["already_running"] is False
        show_id = body["show_id"]

        texts = [_play_one(host) for _ in range(10)]
        snapshot = client.get("/api/show").json()

        # A second press keeps the running show and its content source, whatever the body says.
        again = client.post("/api/show/start", json={"content": "script"})
        assert again.status_code == 200
        assert again.json()["already_running"] is True
        assert again.json()["show_id"] == show_id
        assert again.json()["content"] == "verbatim"
        assert client.get("/api/show").json()["content_source"] == "verbatim"

        assert client.post("/api/show/end").json()["state"] == "closing"
        closing: list[str] = []
        while not closing or closing[-1] != CLOSING_FALLBACK_SENTENCE:
            closing.append(_play_one(host))
            assert len(closing) < 6, closing
        _wait_show_state(client, "ended")

    assert engine.narrate_requests == []
    primary = _sentences(PRIMARY_INTRO, PRIMARY_DESCRIPTION)
    secondary = [s for intro, description in SECONDARY.values() for s in _sentences(intro, description)]
    # The main product opens the show with its own intro, then its description follows.
    assert texts[:2] == primary[:2]
    assert primary[2] in texts
    assert set(texts) <= set(primary) | set(secondary)
    assert set(texts) & set(secondary), texts
    assert snapshot["content_source"] == "verbatim"
    assert snapshot["mode"] == "normal"
    assert snapshot["state"] == "running"
    assert not [ln for ln in json_log_lines if ln["event"] == "mode_changed"]
    assert not [a for a in _jsonl(verbatim_settings, "alerts.jsonl") if a["alert"]["kind"] == "fallback_mode"]
    starts = [ln for ln in json_log_lines if ln["event"] == "control_applied" and ln.get("command") == "show_start"]
    assert starts[0].get("content") == "verbatim"
    # The product text is logged as `verbatim`, not as fallback lines (004 contracts/events.md §2).
    sources = {
        row["source"] for row in _jsonl(verbatim_settings, "script_sentences.jsonl") if row["status"] == "spoken"
    }
    assert "fallback" not in sources
    assert "verbatim" in sources


def test_start_without_a_body_is_the_004_script_show(client, engine):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        r = client.post("/api/show/start")
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "script"
        _play_one(host)
        assert client.get("/api/show").json()["content_source"] == "script"
        client.post("/api/show/end")
    assert engine.narrate_requests


def test_start_with_script_content_is_the_004_show(client, engine):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        r = client.post("/api/show/start", json={"content": "script"})
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "script"
        _play_one(host)
        client.post("/api/show/end")
    assert engine.narrate_requests


@pytest.mark.parametrize(
    "body", [{"content": "video"}, {"content": ""}, {"content": None}, {"content": "verbatim", "x": 1}]
)
def test_start_with_another_content_is_422(client, body):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        r = client.post("/api/show/start", json=body)
    assert r.status_code == 422
    assert client.get("/api/show").json() is None


# --- T044: no way for the app to play the backup video (FR-021, constitution I) ---


def _all_routes(routes) -> list:
    """Every route of the app, inside included routers too (FastAPI keeps them behind a wrapper; no prefixes here)."""
    found = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        found += _all_routes(inner.routes) if inner is not None else [route]
    return found


def test_no_route_serves_a_video_or_reads_the_backup_folder(client, verbatim_settings):
    backup = Path(verbatim_settings.backup_video_dir)
    backup.mkdir(parents=True)
    marker = b"BACKUP-VIDEO-BYTES-must-never-be-served"
    (backup / "backup_20261113-1000_demo_customer_01.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + marker)

    checked = 0
    for route in _all_routes(client.app.routes):
        assert "video" not in getattr(route, "path", "").lower(), route
        directory = getattr(getattr(route, "app", None), "directory", None)
        if directory is not None:
            assert Path(directory).resolve() != backup.resolve(), route
        if not isinstance(route, APIRoute) or "GET" not in route.methods or "{" in route.path:
            continue
        r = client.get(route.path)
        assert not r.headers.get("content-type", "").startswith("video/"), route.path
        assert marker not in r.content, route.path
        checked += 1
    assert checked >= 5
    for name in ("backup_20261113-1000_demo_customer_01.mp4", "../backup/backup_20261113-1000_demo_customer_01.mp4"):
        r = client.get(f"/static/{name}")
        assert r.status_code == 404
        assert marker not in r.content
