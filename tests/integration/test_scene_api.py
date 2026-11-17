"""009 T014: the scene over HTTP and `/ws/host` (contracts/api.md §1–§6)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai_live.app.main import create_app
from fixtures.content_builder import sparse_docx
from fixtures.scene_builder import CUSTOMER, make_scene_dir

# Slugs of the products in `valid_docx()` (primary first in the file).
IDS = ["kem-chong-nang-x", "sua-rua-mat-y", "toner-z"]


@pytest.fixture
def scene_settings(app_settings, tmp_path: Path):
    root = make_scene_dir(tmp_path / "scenes" / "demo", IDS)
    return app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})


@pytest.fixture
def client(scene_settings):
    with TestClient(create_app(scene_settings)) as c:
        yield c


@pytest.fixture
def plain_client(app_settings):
    with TestClient(create_app(app_settings)) as c:
        yield c


def wait_drawn(client: TestClient) -> dict:
    # `/host` waits for the first draw; going through it makes every later read deterministic.
    client.get("/host")
    return client.get("/api/scene").json()


def test_status_when_enabled(client: TestClient) -> None:
    body = wait_drawn(client)
    assert body["enabled"] is True
    assert body["scene_id"] == "demo"
    assert body["version"] >= 1
    # One secondary each side of the primary, file order kept (FR-007).
    assert body["slots"] == ["sua-rua-mat-y", "kem-chong-nang-x", "toner-z"]
    assert body["highlight"] is None
    assert body["issues"] == []
    assert body["last_error"] is None
    assert (body["geometry"]["width"], body["geometry"]["height"]) == (480, 832)
    assert body["geometry"]["source"] == "estimate"
    assert isinstance(body["render_ms"], float)


def test_status_when_disabled(plain_client: TestClient) -> None:
    body = plain_client.get("/api/scene").json()
    assert body["enabled"] is False
    assert body["slots"] == [] and body["version"] is None


def test_still_is_a_frame_sized_png_never_cached(client: TestClient) -> None:
    wait_drawn(client)
    r = client.get("/api/scene/still.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"
    assert Image.open(io.BytesIO(r.content)).size == (480, 832)


def test_still_is_404_when_disabled(plain_client: TestClient) -> None:
    r = plain_client.get("/api/scene/still.png")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


def test_host_config_carries_scene(client: TestClient, plain_client: TestClient) -> None:
    version = wait_drawn(client)["version"]
    assert client.get("/api/host-config").json()["scene"] == {"enabled": True, "subtitles": False, "version": version}
    assert plain_client.get("/api/host-config").json()["scene"] == {
        "enabled": False,
        "subtitles": False,
        "version": None,
    }


def test_host_page_uses_the_still(client: TestClient, plain_client: TestClient) -> None:
    page = client.get("/host").text
    version = client.get("/api/scene").json()["version"]
    assert f"/api/scene/still.png?v={version}" in page
    # The AI label is still on the page, outside any scene picture (Article I).
    assert "ai-label" in page
    assert "/api/scene/still.png" not in plain_client.get("/host").text


def test_content_replace_redraws_and_tells_the_host(client: TestClient) -> None:
    before = wait_drawn(client)["version"]
    with client.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        r = client.put(
            "/api/content",
            content=sparse_docx(),
            headers={"Content-Type": "application/octet-stream", "X-Filename": "moi.docx"},
        )
        assert r.status_code == 200
        message = None
        for _ in range(20):
            data = json.loads(host.receive_text())
            if data["type"] == "scene":
                message = data
                break
        # Flat message, sent in every avatar mode (api.md §5).
        assert message is not None and set(message) == {"type", "version"}
        assert message["version"] > before
    body = client.get("/api/scene").json()
    assert body["version"] == message["version"]
    # FR-013: the product gone from the file is gone from the desk; its picture is only an orphan.
    assert body["slots"] == ["kem-chong-nang-x", "sua-rua-mat-y"]
    assert [i["code"] for i in body["issues"]] == ["orphan_image"]


def test_other_customers_scene_is_never_drawn(app_settings, tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scenes" / "other", IDS, customer_id="other_shop")
    settings = app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})
    with TestClient(create_app(settings)) as c:
        body = wait_drawn(c)
        assert "customer_mismatch" in [i["code"] for i in body["issues"]]
        assert body["slots"] == []
        # The show still starts and the page still opens (FR-003).
        assert c.get("/host").status_code == 200


def test_missing_scene_dir_does_not_stop_startup(app_settings, tmp_path: Path) -> None:
    settings = app_settings.model_copy(
        update={"scene_enabled": True, "scene_dir": tmp_path / "nowhere", "customer_id": CUSTOMER}
    )
    with TestClient(create_app(settings)) as c:
        assert c.get("/health").status_code == 200
        assert [i["code"] for i in wait_drawn(c)["issues"]] == ["missing_dir"]
