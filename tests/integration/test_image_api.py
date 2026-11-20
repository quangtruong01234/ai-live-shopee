"""012 US1: product images over HTTP (specs/012-product-image-upload/contracts/api.md §1, §4–§7)."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import ai_live.scene.uploads as uploads_module
from ai_live.app.main import create_app
from fixtures.scene_builder import CUSTOMER, image_bytes, make_scene_dir, write_manifest

# Slugs of the products in `valid_docx()`, in file order (primary first).
IDS = ["kem-chong-nang-x", "sua-rua-mat-y", "toner-z"]
PID = "toner-z"
PLATFORM_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"
CLAIM_PHRASES = PLATFORM_PHRASES.with_name("claim_phrases.txt")
CHANGED_FIELDS = {
    "action",
    "product_id",
    "version_id",
    "from_state",
    "to_state",
    "result",
    "to_frame_ms",
    "scene_version",
}


@pytest.fixture
def scene_settings(app_settings, tmp_path: Path):
    root = make_scene_dir(tmp_path / "scenes" / "demo", IDS)
    return app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})


@pytest.fixture
def client(scene_settings):
    with TestClient(create_app(scene_settings)) as c:
        yield c


@pytest.fixture
def off_client(app_settings, tmp_path: Path):
    """Scene off, but the folder exists: the page can still list and prepare images (edge case)."""
    root = make_scene_dir(tmp_path / "scenes" / "demo", IDS)
    settings = app_settings.model_copy(update={"scene_enabled": False, "scene_dir": root, "customer_id": CUSTOMER})
    with TestClient(create_app(settings)) as c:
        yield c


def wait_drawn(client: TestClient) -> dict:
    client.get("/host")
    return client.get("/api/scene").json()


def upload(client: TestClient, kind: str = "png", *, pid: str = PID, name: str = "ảnh mới.png", **kw: Any):
    return client.post(
        f"/api/scene/uploads?product_id={pid}",
        content=image_bytes(kind, **kw),  # type: ignore[arg-type]
        headers={"Content-Type": "application/octet-stream", "X-Filename": quote(name)},
    )


def apply(client: TestClient, vid: str, *, pid: str = PID, confirmed: Any = True):
    return client.post(f"/api/scene/images/{pid}/apply", json={"version_id": vid, "rights_confirmed": confirmed})


def images(client: TestClient) -> dict:
    r = client.get("/api/scene/images")
    assert r.status_code == 200, r.text
    return r.json()


def item(body: dict, pid: str = PID) -> dict:
    return next(p for p in body["products"] if p["product_id"] == pid)


def scene_image(client: TestClient, pid: str = PID) -> dict:
    return next(i for i in client.get("/api/scene").json()["images"] if i["product_id"] == pid)


def record_layers(client: TestClient) -> list[tuple[str, Any]]:
    """Stand in for the fork: collect every layer the scene hands to the renderer."""
    got: list[tuple[str, Any]] = []
    client.app.state.ctx.renderer.set_scene_layer = lambda name, layer: got.append((name, layer))
    return got


def uploads_dir(client: TestClient) -> Path:
    return client.app.state.ctx.settings.scene_dir / "uploads"


def files_under(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*") if p.is_file()) if path.exists() else []


# ---------- T014: list and upload ----------


def test_images_list_follows_the_live_catalog(client: TestClient) -> None:
    wait_drawn(client)
    body = images(client)
    assert body["scene_enabled"] is True
    assert body["scene_usable"] is True
    assert body["catalog_version"] == client.app.state.ctx.store.catalog.version
    assert [p["product_id"] for p in body["products"]] == IDS
    assert [p["is_primary"] for p in body["products"]] == [True, False, False]
    first = body["products"][0]
    assert first["name"]
    assert first["state"] == "kit"
    assert first["version_id"] is None
    assert first["thumb_url"] == f"/api/scene/images/{IDS[0]}/kit.png"
    assert first["can_revert"] is False
    assert first["issues"] == []
    assert first["versions"] == []
    assert body["uploads_bytes"] == 0


def test_images_list_works_with_the_scene_off(off_client: TestClient) -> None:
    body = images(off_client)
    assert body["scene_enabled"] is False
    assert [p["product_id"] for p in body["products"]] == IDS
    assert item(body)["state"] == "kit"


def test_product_without_any_image_is_none(app_settings, tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scenes" / "demo", IDS[:2])
    settings = app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})
    with TestClient(create_app(settings)) as c:
        wait_drawn(c)
        status = item(images(c))
        assert status["state"] == "none"
        assert status["thumb_url"] is None


def test_upload_stores_a_version_without_changing_live(client: TestClient, json_log_lines) -> None:
    before = wait_drawn(client)
    layers = record_layers(client)
    r = upload(client, "png", size=(300, 500))
    assert r.status_code == 201, r.text
    body = r.json()
    vid = body["version_id"]
    assert body["product_id"] == PID
    assert body["reused"] is False
    assert body["has_alpha"] is True
    assert body["warnings"] == []
    assert (body["width"], body["height"]) == (300, 500)
    assert body["thumb_url"] == f"/api/scene/images/{PID}/versions/{vid}.png"
    # Saved, not shown: the live scene and the renderer's layers stay as they were.
    assert client.get("/api/scene").json()["version"] == before["version"]
    assert layers == []
    assert scene_image(client)["source"] == "kit"
    status = item(images(client))
    assert status["state"] == "kit"
    assert [v["version_id"] for v in status["versions"]] == [vid]
    assert status["versions"][0]["source_name"] == "ảnh mới.png"
    assert images(client)["uploads_bytes"] > 0
    logged = [ln for ln in json_log_lines if ln["event"] == "scene_image_uploaded"]
    assert len(logged) == 1
    assert {"product_id", "version_id", "reused", "has_alpha", "width", "height", "bytes", "ms"} <= set(logged[0])
    assert "ảnh mới.png" not in json.dumps(json_log_lines, ensure_ascii=False)


def test_same_picture_twice_is_reused(client: TestClient) -> None:
    first = upload(client).json()
    again = upload(client, name="lần hai.png")
    assert again.status_code == 201
    assert again.json()["reused"] is True
    assert again.json()["version_id"] == first["version_id"]
    assert len(item(images(client))["versions"]) == 1


def test_jpeg_upload_warns_about_its_background(client: TestClient) -> None:
    body = upload(client, "jpeg", name="anh.jpg").json()
    assert body["has_alpha"] is False
    assert body["warnings"] == ["has_background"]


@pytest.mark.parametrize(
    ("kind", "status", "code", "message"),
    [
        ("too_large", 413, "too_large", "Ảnh quá lớn (tối đa 10 MB)"),
        ("png_truncated", 400, "bad_image", "Không đọc được file ảnh (hỏng hoặc không phải ảnh)"),
        ("text", 400, "bad_image", "Không đọc được file ảnh (hỏng hoặc không phải ảnh)"),
        ("gif_animated", 415, "bad_format", "Chỉ nhận ảnh PNG, WebP hoặc JPEG"),
        ("png_too_wide", 400, "too_big", "Ảnh quá to: cạnh dài 4100 điểm ảnh (tối đa 4000)"),
        ("webp_animated", 400, "animated", "Không nhận ảnh động"),
        ("png_transparent", 400, "empty", "Ảnh gần như trong suốt hoàn toàn, trên live sẽ không thấy gì"),
    ],
)
def test_bad_files_get_the_contract_error_and_write_nothing(
    client: TestClient, json_log_lines, kind: str, status: int, code: str, message: str
) -> None:
    r = upload(client, kind)
    assert r.status_code == status
    assert r.json()["error"] == code
    assert r.json()["message"] == message
    assert files_under(uploads_dir(client)) == []
    rejected = [ln for ln in json_log_lines if ln["event"] == "scene_image_rejected"]
    assert [ln["code"] for ln in rejected] == [code]


def test_unknown_product_is_404(client: TestClient) -> None:
    r = upload(client, pid="serum-khong-co")
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_product"
    assert r.json()["message"] == "Không có sản phẩm serum-khong-co trong file đang nạp hay bộ chuẩn bị"
    assert files_under(uploads_dir(client)) == []


@pytest.mark.parametrize("pid", ["Kem", "kem_chong", "-kem"])
def test_bad_product_id_is_400(client: TestClient, pid: str) -> None:
    r = upload(client, pid=pid)
    assert r.status_code == 400
    assert r.json()["error"] == "bad_id"


def test_other_customers_manifest_is_409(app_settings, tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scenes" / "demo", IDS)
    write_manifest(root, {"schema_version": 1, "customer_id": "shop_khac", "products": {}})
    settings = app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})
    with TestClient(create_app(settings)) as c:
        r = upload(c)
        assert r.status_code == 409
        assert r.json()["error"] == "customer_mismatch"
        assert r.json()["message"] == "Bộ cảnh không thuộc khách của phiên này"


def test_other_customers_scene_set_is_409(app_settings, tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scenes" / "other", IDS, customer_id="shop_khac")
    settings = app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})
    with TestClient(create_app(settings)) as c:
        wait_drawn(c)
        r = upload(c)
        assert r.status_code == 409
        assert r.json()["error"] == "customer_mismatch"
        assert files_under(root / "uploads") == []


def test_version_png_is_immutable(client: TestClient) -> None:
    vid = upload(client).json()["version_id"]
    r = client.get(f"/api/scene/images/{PID}/versions/{vid}.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "max-age=31536000, immutable"
    assert client.get(f"/api/scene/images/{PID}/versions/0123456789ab.png").status_code == 404
    assert client.get(f"/api/scene/images/{PID}/versions/NOTAVERSION.png").json()["error"] == "bad_id"


def test_kit_png_is_the_cropped_scene_art(client: TestClient) -> None:
    r = client.get(f"/api/scene/images/{PID}/kit.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-cache"
    assert max(Image.open(io.BytesIO(r.content)).size) <= 640
    assert client.get("/api/scene/images/serum-khong-co/kit.png").status_code == 404


# ---------- T015: preview and apply ----------


def test_preview_draws_the_candidate_without_touching_live(client: TestClient) -> None:
    before = wait_drawn(client)
    live = client.get("/api/scene/still.png").content
    vid = upload(client, "png", size=(300, 500), color=(20, 160, 220)).json()["version_id"]
    r = client.get(f"/api/scene/preview.png?target=live&product_id={PID}&version_id={vid}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"
    assert Image.open(io.BytesIO(r.content)).size == (480, 832)
    assert r.content != live
    assert client.get("/api/scene").json()["version"] == before["version"]
    assert client.get("/api/scene/still.png").content == live


def test_preview_errors(client: TestClient, off_client: TestClient, app_settings, tmp_path: Path) -> None:
    wait_drawn(client)
    r = client.get(f"/api/scene/preview.png?product_id={PID}&version_id=0123456789ab")
    assert (r.status_code, r.json()["error"]) == (404, "unknown_version")
    r = client.get("/api/scene/preview.png?product_id=serum-khong-co")
    assert (r.status_code, r.json()["error"]) == (404, "unknown_product")
    r = client.get("/api/scene/preview.png?target=staging")
    assert (r.status_code, r.json()["error"]) == (404, "no_staging")
    r = off_client.get(f"/api/scene/preview.png?product_id={PID}")
    assert (r.status_code, r.json()["error"]) == (409, "scene_disabled")
    root = make_scene_dir(tmp_path / "scenes" / "other", IDS, customer_id="shop_khac")
    settings = app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})
    with TestClient(create_app(settings)) as c:
        wait_drawn(c)
        r = c.get(f"/api/scene/preview.png?product_id={PID}")
        assert (r.status_code, r.json()["error"]) == (409, "scene_unusable")


@pytest.mark.parametrize("confirmed", [False, None, "true", 1])
def test_apply_without_rights_confirmation_changes_nothing(client: TestClient, confirmed: Any) -> None:
    before = wait_drawn(client)
    vid = upload(client).json()["version_id"]
    layers = record_layers(client)
    r = apply(client, vid, confirmed=confirmed)
    assert r.status_code == 422
    assert r.json()["error"] == "rights_not_confirmed"
    assert r.json()["message"] == "Chưa đánh dấu xác nhận quyền dùng ảnh"
    assert item(images(client))["state"] == "kit"
    assert client.app.state.ctx.images.active(PID) == "kit"
    assert client.get("/api/scene").json()["version"] == before["version"]
    assert layers == []


def test_apply_unknown_product_or_version(client: TestClient) -> None:
    wait_drawn(client)
    r = apply(client, "0123456789ab", pid="serum-khong-co")
    assert (r.status_code, r.json()["error"]) == (404, "unknown_product")
    r = apply(client, "0123456789ab")
    assert (r.status_code, r.json()["error"]) == (404, "unknown_version")
    r = apply(client, "NOT-A-VID")
    assert (r.status_code, r.json()["error"]) == (400, "bad_id")


def test_apply_puts_the_new_image_on_live(client: TestClient, json_log_lines) -> None:
    before = wait_drawn(client)
    still_before = client.get("/api/scene/still.png").content
    vid = upload(client, "png", size=(300, 500), color=(20, 160, 220)).json()["version_id"]
    layers = record_layers(client)
    with client.websocket_connect("/ws/control") as control:
        r = apply(client, vid)
        assert r.status_code == 200, r.text
        event = None
        for _ in range(50):
            data = control.receive_json()
            if data.get("type") == "scene" and data.get("kind") == "image_changed":
                event = {k: v for k, v in data.items() if k != "ts"}  # every bus event carries ts
                break
    body = r.json()
    assert body["product_id"] == PID
    assert body["active"] == vid
    assert body["applied_at"] and body["rights_confirmed_at"]
    assert body["scene_enabled"] is True
    assert body["scene_version"] > before["version"]
    assert 0 <= body["to_frame_ms"] < 2000
    # The fork got a new base layer (FR-009).
    assert [name for name, _ in layers] == ["base"]
    assert event == {
        "type": "scene",
        "kind": "image_changed",
        "product_id": PID,
        "action": "apply",
        "active": vid,
        "scene_version": body["scene_version"],
    }
    assert scene_image(client) == {"product_id": PID, "source": "upload", "version_id": vid}
    status = item(images(client))
    assert status["state"] == "upload"
    assert status["version_id"] == vid
    assert status["thumb_url"] == f"/api/scene/images/{PID}/versions/{vid}.png"
    assert status["can_revert"] is True
    assert status["rights_confirmed_at"] == body["rights_confirmed_at"]
    # Static avatar mode: the still behind the host follows the new image (edge case).
    assert client.get("/api/scene/still.png").content != still_before
    changed = [ln for ln in json_log_lines if ln["event"] == "scene_image_changed"]
    assert len(changed) == 1
    assert CHANGED_FIELDS <= set(changed[0])
    assert changed[0]["action"] == "apply"
    assert (changed[0]["from_state"], changed[0]["to_state"], changed[0]["result"]) == ("kit", vid, "ok")


def test_apply_with_the_scene_off_records_but_does_not_draw(off_client: TestClient) -> None:
    vid = upload(off_client).json()["version_id"]
    r = apply(off_client, vid)
    assert r.status_code == 200
    assert r.json()["to_frame_ms"] is None
    assert r.json()["scene_version"] is None
    assert r.json()["scene_enabled"] is False
    assert item(images(off_client))["state"] == "upload"


def test_two_applies_close_together_end_in_agreement(client: TestClient) -> None:
    wait_drawn(client)
    a = upload(client, "png", size=(300, 500)).json()["version_id"]
    b = upload(client, "png", size=(320, 480), color=(20, 160, 220)).json()["version_id"]
    assert a != b
    app = client.app

    async def both() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            body = {"rights_confirmed": True}
            return await asyncio.gather(
                ac.post(f"/api/scene/images/{PID}/apply", json={**body, "version_id": a}),
                ac.post(f"/api/scene/images/{PID}/apply", json={**body, "version_id": b}),
            )

    responses = client.portal.call(both)
    assert [r.status_code for r in responses] == [200, 200]
    entry = client.app.state.ctx.images.entry(PID)
    # Both landed one after the other; whichever went second is what the ledger and live both show.
    assert entry["history"][-1] in {a, b}
    assert entry["active"] == ({a, b} - {entry["history"][-1]}).pop()
    assert scene_image(client)["version_id"] == entry["active"]


def test_highlighted_product_stays_highlighted_with_its_new_image(client: TestClient) -> None:
    wait_drawn(client)
    scene = client.app.state.ctx.scene
    client.portal.call(lambda: scene._set_highlight(PID))
    vid = upload(client).json()["version_id"]
    assert apply(client, vid).status_code == 200
    body = client.get("/api/scene").json()
    assert body["highlight"] == PID
    assert scene_image(client)["version_id"] == vid


def test_ledger_write_failure_keeps_the_old_image(client: TestClient, monkeypatch, json_log_lines) -> None:
    before = wait_drawn(client)
    vid = upload(client).json()["version_id"]
    real = uploads_module._write_atomic

    def failing(path: Path, data: bytes) -> None:
        if path.name == "images.json":
            raise OSError("đĩa đầy")
        real(path, data)

    monkeypatch.setattr(uploads_module, "_write_atomic", failing)
    r = apply(client, vid)
    assert r.status_code == 500
    assert r.json()["error"] == "save_failed"
    assert r.json()["message"].startswith("Không lưu được ảnh: ")
    assert scene_image(client)["source"] == "kit"
    assert client.get("/api/scene").json()["version"] == before["version"]
    failed = [ln for ln in json_log_lines if ln["event"] == "scene_image_changed"]
    assert [ln["result"] for ln in failed] == ["save_failed"]


def test_applied_image_survives_a_restart(scene_settings) -> None:
    with TestClient(create_app(scene_settings)) as c:
        vid = upload(c).json()["version_id"]
        assert apply(c, vid).status_code == 200
    with TestClient(create_app(scene_settings)) as c:
        wait_drawn(c)
        assert scene_image(c) == {"product_id": PID, "source": "upload", "version_id": vid}
        assert item(images(c))["state"] == "upload"


# ---------- T015: a running show is not interrupted (FR-010) ----------


def _receive_json(ws) -> dict:
    while True:
        message = ws.receive()
        if message.get("text") is not None:
            return json.loads(message["text"])


def _play_one(ws) -> dict:
    """Play one sentence like the host page does; returns its `sentence_start`."""
    while (start := _receive_json(ws))["type"] != "sentence_start":
        pass
    ws.send_json({"type": "playback_started", "utterance_id": start["utterance_id"], "seq": start["seq"]})
    while _receive_json(ws)["type"] != "sentence_end":
        pass
    ws.send_json({"type": "sentence_played", "utterance_id": start["utterance_id"], "seq": start["seq"]})
    return start


def test_apply_during_a_show_keeps_it_running(scene_settings) -> None:
    settings = scene_settings.model_copy(
        update={
            "platform_phrases_path": PLATFORM_PHRASES,
            "claim_phrases_path": CLAIM_PHRASES,
            "script_segment_min_sentences": 2,
            "script_segment_max_sentences": 3,
        }
    )
    with TestClient(create_app(settings)) as c, c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready"})
        for _ in range(500):
            if c.get("/health").json()["host_connected"]:
                break
        assert c.post("/api/show/start").status_code == 200
        first = _play_one(host)
        vid = upload(c).json()["version_id"]
        assert apply(c, vid).status_code == 200
        assert c.get("/api/show").json()["state"] == "running"
        after = _play_one(host)
        assert (after["utterance_id"], after["seq"]) != (first["utterance_id"], first["seq"])
        assert c.get("/api/show").json()["state"] == "running"


# ---------- T056: revert and remove (US3, contracts/api.md §1) ----------


def _change(client: TestClient, path: str, **kw: Any) -> tuple[Any, dict | None]:
    """POST one change while listening on /ws/control; returns the response and its image_changed event."""
    with client.websocket_connect("/ws/control") as control:
        r = client.post(f"/api/scene/images/{PID}/{path}", **kw)
        if r.status_code != 200:
            return r, None
        for _ in range(50):
            data = control.receive_json()
            if data.get("type") == "scene" and data.get("kind") == "image_changed":
                return r, {k: v for k, v in data.items() if k != "ts"}
    return r, None


def _check_step(r: Any, event: dict | None, action: str, active: Any) -> None:
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_id"] == PID
    assert body["active"] == active
    assert body["scene_enabled"] is True
    assert 0 <= body["to_frame_ms"] < 2000
    assert event == {
        "type": "scene",
        "kind": "image_changed",
        "product_id": PID,
        "action": action,
        "active": active,
        "scene_version": body["scene_version"],
    }


def test_revert_walks_back_to_the_kit_then_has_nothing_left(client: TestClient, json_log_lines) -> None:
    wait_drawn(client)
    a = upload(client, "png", size=(300, 500), color=(20, 160, 220)).json()["version_id"]
    b = upload(client, "webp", size=(320, 480)).json()["version_id"]
    assert apply(client, a).status_code == 200
    assert apply(client, b).status_code == 200
    layers = record_layers(client)

    r, event = _change(client, "revert")
    _check_step(r, event, "revert", a)
    assert scene_image(client) == {"product_id": PID, "source": "upload", "version_id": a}
    assert [name for name, _ in layers] == ["base"]

    r, event = _change(client, "revert")
    _check_step(r, event, "revert", "kit")
    assert scene_image(client)["source"] == "kit"
    status = item(images(client))
    assert status["state"] == "kit"
    assert status["can_revert"] is False

    r, _ = _change(client, "revert")
    assert (r.status_code, r.json()["error"]) == (409, "nothing_to_revert")
    assert client.app.state.ctx.images.active(PID) == "kit"

    reverts = [ln for ln in json_log_lines if ln["event"] == "scene_image_changed" and ln["action"] == "revert"]
    assert [(ln["from_state"], ln["to_state"], ln["result"]) for ln in reverts] == [
        (b, a, "ok"),
        (a, "kit", "ok"),
        ("kit", "kit", "nothing_to_revert"),
    ]
    assert all(CHANGED_FIELDS <= set(ln) for ln in reverts)


@pytest.mark.parametrize("body", [{"confirm": False}, {}, {"confirm": "true"}, {"confirm": 1}])
def test_remove_without_confirmation_changes_nothing(client: TestClient, body: dict) -> None:
    before = wait_drawn(client)
    layers = record_layers(client)
    r = client.post(f"/api/scene/images/{PID}/remove", json=body)
    assert r.status_code == 422
    assert r.json()["error"] == "remove_not_confirmed"
    assert r.json()["message"] == "Chưa xác nhận gỡ ảnh"
    assert client.app.state.ctx.images.active(PID) == "kit"
    assert client.get("/api/scene").json()["version"] == before["version"]
    assert layers == []


def test_remove_takes_the_image_off_but_keeps_the_card(client: TestClient, json_log_lines) -> None:
    wait_drawn(client)
    vid = upload(client).json()["version_id"]
    assert apply(client, vid).status_code == 200
    layers = record_layers(client)

    r, event = _change(client, "remove", json={"confirm": True})
    _check_step(r, event, "remove", None)
    scene = client.get("/api/scene").json()
    assert PID not in [i["product_id"] for i in scene["images"]]
    assert PID in scene["slots"]  # the name/price card is still on the desk
    assert [name for name, _ in layers] == ["base"]
    status = item(images(client))
    assert status["state"] == "removed"
    assert status["can_revert"] is True

    r, _ = _change(client, "remove", json={"confirm": True})
    assert (r.status_code, r.json()["error"]) == (409, "already_removed")

    # Removing is undoable: revert brings the image back.
    r, event = _change(client, "revert")
    _check_step(r, event, "revert", vid)
    assert scene_image(client) == {"product_id": PID, "source": "upload", "version_id": vid}

    removes = [ln for ln in json_log_lines if ln["event"] == "scene_image_changed" and ln["action"] == "remove"]
    assert [(ln["from_state"], ln["to_state"], ln["result"]) for ln in removes] == [
        (vid, None, "ok"),
        (None, None, "already_removed"),
    ]


def test_images_list_has_the_detail_fields(client: TestClient) -> None:
    wait_drawn(client)
    vid = upload(client).json()["version_id"]
    assert apply(client, vid).status_code == 200
    body = images(client)
    assert isinstance(body["uploads_bytes"], int) and body["uploads_bytes"] > 0
    status = item(body)
    for key in ("uploaded_at", "applied_at", "rights_confirmed_at", "has_alpha", "can_revert", "versions"):
        assert key in status, key
    assert status["uploaded_at"] and status["applied_at"] and status["rights_confirmed_at"]
    assert [v["version_id"] for v in status["versions"]] == [vid]


@pytest.mark.parametrize("path", ["revert", "remove"])
def test_revert_and_remove_of_an_unknown_product_is_404(client: TestClient, path: str) -> None:
    wait_drawn(client)
    r = client.post(f"/api/scene/images/serum-khong-co/{path}", json={"confirm": True})
    assert (r.status_code, r.json()["error"]) == (404, "unknown_product")
    r = client.post(f"/api/scene/images/Kem/{path}", json={"confirm": True})
    assert (r.status_code, r.json()["error"]) == (400, "bad_id")
