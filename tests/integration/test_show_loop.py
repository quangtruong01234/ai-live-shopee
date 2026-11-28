"""ADR-088: the `loop` show repeats one fixed passage with invites to ask for advice, and is the default source.

No engine call while nobody comments; every line still goes through the guard, TTS and the realtime renderer.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_live.app.main import create_app
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.director import loop_script
from ai_live.director.script_runner import CLOSING_FALLBACK_SENTENCE
from fixtures.content_builder import build_docx, product_blocks

PLATFORM_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"
CLAIM_PHRASES = PLATFORM_PHRASES.with_name("claim_phrases.txt")


def _loop_docx() -> bytes:
    blocks = product_blocks(
        "Nước ngọt A",
        "chính",
        price="95.000đ",
        specs=("Dung tích: 355 ml", "Thành phần: nước, đường"),
        promotions=("Mua 2 lốc giảm 10.000đ",),
        intro="Chào cả nhà, đây là nước ngọt A.\nNước ngọt A đang ở ngay trước mặt em nè.",
        description="Nước ngọt A có ga, vị nguyên bản.",
    )
    blocks += product_blocks(
        "Nước ngọt B",
        "phụ",
        price="12.000đ",
        specs=("Dung tích: 500 ml",),
        promotions=(),
        forbidden=(),
        intro="Còn đây là nước ngọt B.",
        description="Nước ngọt B đựng trong chai nhựa.",
    )
    return build_docx(blocks)


@pytest.fixture
def loop_settings(app_settings, tmp_path):
    content = tmp_path / "loop.docx"
    content.write_bytes(_loop_docx())
    return app_settings.model_copy(
        update={
            "product_data_path": content,
            "platform_phrases_path": PLATFORM_PHRASES,
            "claim_phrases_path": CLAIM_PHRASES,
            "show_content": "loop",
        }
    )


@pytest.fixture
def engine():
    return FakeReplyEngine()


@pytest.fixture
def client(loop_settings, engine):
    with TestClient(create_app(loop_settings, reply_engine=engine)) as c:
        yield c


def _receive_json(ws) -> dict:
    while True:
        message = ws.receive()
        if message.get("text") is not None:
            return json.loads(message["text"])


def _play_one(ws) -> str:
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


def test_start_without_a_body_uses_show_content_and_repeats_the_passage(client, engine, loop_settings):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)

        r = client.post("/api/show/start")
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "loop"

        texts = [_play_one(host) for _ in range(30)]
        snapshot = client.get("/api/show").json()
        assert client.post("/api/show/end").json()["state"] == "closing"
        closing: list[str] = []
        while not closing or closing[-1] != CLOSING_FALLBACK_SENTENCE:
            closing.append(_play_one(host))
            assert len(closing) < 12, closing
        _wait_show_state(client, "ended")

    assert engine.narrate_requests == []
    assert snapshot["content_source"] == "loop"
    assert snapshot["mode"] == "normal"
    assert texts[0] == loop_script.OPENING_LINES[0]
    assert loop_script.OPENING_LINES[1] in texts[:3]
    # The main product comes back with its price each time, in turn-by-turn wording (FR-031, 2026-11-28).
    main_prices = [t for t in texts if "Nước ngọt A" in t and "95.000đ" in t]
    assert len(main_prices) >= 2 and len(set(main_prices)) >= 2
    assert "Nước ngọt B giá 12.000đ nha anh chị." in texts
    # Each visit reads the next intro paragraph, so both paragraphs are said.
    assert "Chào cả nhà, đây là nước ngọt A." in texts
    assert "Nước ngọt A đang ở ngay trước mặt em nè." in texts
    # Every product block ends with an invite to ask for advice, and the invites rotate.
    invites = [t for t in texts if t in loop_script.invite_lines(client.app.state.ctx.store.catalog)]
    assert len(set(invites)) >= 2
    sources = {row["source"] for row in _jsonl(loop_settings, "script_sentences.jsonl") if row["status"] == "spoken"}
    assert sources == {"loop"}


def test_an_explicit_script_body_still_starts_the_llm_show(client, engine):
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        _wait_host_ready(client)
        r = client.post("/api/show/start", json={"content": "script"})
        assert r.json()["content"] == "script"
        _play_one(host)
        client.post("/api/show/end")
    assert engine.narrate_requests
