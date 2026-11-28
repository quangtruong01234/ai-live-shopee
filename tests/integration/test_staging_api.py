"""012 US2: "Chuẩn bị bộ mới" over HTTP (specs/012-product-image-upload/contracts/api.md §2, FR-013–FR-015a)."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import ai_live.scene.uploads as uploads_module
from ai_live.app.main import create_app
from fixtures.content_builder import build_docx, product_blocks, valid_docx
from fixtures.scene_builder import CUSTOMER, image_bytes, make_scene_dir, matting_bytes

# Live products (`valid_docx()`), with a kit image each.
LIVE_IDS = ["kem-chong-nang-x", "sua-rua-mat-y", "toner-z"]
# The staged file: two new products without any image, and one kept from the live set (its kit image is reused).
NEW_MAIN, KEPT, NEW_SIDE = "son-moi-a", "sua-rua-mat-y", "phan-b"
STAGED_IDS = [NEW_MAIN, KEPT, NEW_SIDE]


def staged_docx() -> bytes:
    return build_docx(
        [
            *product_blocks("Son môi A", "chính", price="199.000đ"),
            *product_blocks("Sữa rửa mặt Y", "phụ", price="159.000đ", forbidden=()),
            *product_blocks("Phấn B", "phụ", price="99.000đ"),
        ]
    )


@pytest.fixture
def scene_settings(app_settings, tmp_path: Path):
    root = make_scene_dir(tmp_path / "scenes" / "demo", LIVE_IDS)
    return app_settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})


@pytest.fixture
def client(scene_settings):
    with TestClient(create_app(scene_settings)) as c:
        yield c


def wait_drawn(client: TestClient) -> dict:
    client.get("/host")
    return client.get("/api/scene").json()


def stage(client: TestClient, data: bytes | None = None, name: str = "bộ mới.docx"):
    return client.post(
        "/api/content/staging",
        content=staged_docx() if data is None else data,
        headers={"Content-Type": "application/octet-stream", "X-Filename": quote(name)},
    )


def put_content(client: TestClient, data: bytes, name: str = "nội dung.docx"):
    return client.put(
        "/api/content",
        content=data,
        headers={"Content-Type": "application/octet-stream", "X-Filename": quote(name)},
    )


def upload(client: TestClient, pid: str, color=(20, 160, 220)) -> str:
    r = client.post(
        f"/api/scene/uploads?product_id={pid}",
        content=image_bytes("png", size=(300, 500), color=color),  # type: ignore[arg-type]
        headers={"Content-Type": "application/octet-stream", "X-Filename": quote("ảnh.png")},
    )
    assert r.status_code == 201, r.text
    return r.json()["version_id"]


def assign(client: TestClient, staged_id: str, pid: str, vid: str | None, *, confirmed: Any = True):
    body = {"staged_id": staged_id, "version_id": vid, "rights_confirmed": confirmed}
    return client.post(f"/api/content/staging/images/{pid}", json=body)


def apply_set(client: TestClient, staged_id: str, *, confirm: Any = None):
    return client.post("/api/content/staging/apply", json={"staged_id": staged_id, "confirm_missing": confirm})


def by_id(view: dict) -> dict[str, dict]:
    return {p["product_id"]: p for p in view["products"]}


def scene_sources(client: TestClient) -> dict[str, tuple[str, str | None]]:
    return {i["product_id"]: (i["source"], i["version_id"]) for i in client.get("/api/scene").json()["images"]}


def record_layers(client: TestClient) -> list[tuple[str, Any]]:
    got: list[tuple[str, Any]] = []
    client.app.state.ctx.renderer.set_scene_layer = lambda name, layer: got.append((name, layer))
    return got


def record_draws(client: TestClient) -> list[tuple[str, dict[str, str | None]]]:
    """Every draw of the live scene: the catalog version it showed and the image source of each product."""
    controller = client.app.state.ctx.scene
    seen: list[tuple[str, dict[str, str | None]]] = []
    real = controller._draw

    def recording(snap: Any) -> list[str]:
        art = {p.id: (snap.scene.art[p.id].source if p.id in snap.scene.art else None) for p in snap.catalog.products}
        seen.append((snap.catalog.version, art))
        return real(snap)

    controller._draw = recording
    return seen


# ---------- T031: create, view, assign, cancel ----------


def test_create_lists_the_new_set_and_leaves_live_alone(client: TestClient, json_log_lines) -> None:
    before = wait_drawn(client)
    live_version = client.app.state.ctx.store.catalog.version
    layers = record_layers(client)
    started = time.perf_counter()
    r = stage(client)
    assert time.perf_counter() - started < 2
    assert r.status_code == 200, r.text
    view = r.json()
    assert len(view["staged_id"]) == 6
    assert view["source_name"] == "bộ mới.docx"
    assert view["live_catalog_version"] == live_version and view["live_changed"] is False
    assert [p["product_id"] for p in view["products"]] == STAGED_IDS
    assert [p["is_primary"] for p in view["products"]] == [True, False, False]
    products = by_id(view)
    assert products[NEW_MAIN]["name"] == "Son môi A"
    assert products[NEW_MAIN]["image"] == "missing" and products[NEW_MAIN]["thumb_url"] is None
    assert products[KEPT]["image"] == "reused_kit"
    assert products[KEPT]["thumb_url"] == f"/api/scene/images/{KEPT}/kit.png"
    assert view["missing"] == [NEW_MAIN, NEW_SIDE]
    # FR-013: nothing on live moved.
    assert client.app.state.ctx.store.catalog.version == live_version
    assert client.get("/api/scene").json()["version"] == before["version"]
    assert layers == []
    state = client.get("/api/state").json()["staging"]
    assert state == {"staged_id": view["staged_id"], "source_name": "bộ mới.docx", "missing": 2}
    created = [ln for ln in json_log_lines if ln["event"] == "scene_staging_created"]
    assert len(created) == 1 and created[0]["products"] == 3


@pytest.mark.parametrize("data", [b"khong phai docx", b""])
def test_a_broken_file_gets_the_same_answer_as_put_content(client: TestClient, data: bytes) -> None:
    staged, live = stage(client, data), put_content(client, data)
    assert staged.status_code == live.status_code != 200
    assert staged.json()["error"] == live.json()["error"]
    assert client.get("/api/state").json()["staging"] is None


def test_a_second_file_replaces_the_staged_set(client: TestClient) -> None:
    first = stage(client).json()["staged_id"]
    second = stage(client, valid_docx(), name="khác.docx").json()
    assert second["staged_id"] != first
    assert client.get("/api/content/staging").json()["staged_id"] == second["staged_id"]
    vid = upload(client, "toner-z")
    r = assign(client, first, "toner-z", vid)
    assert (r.status_code, r.json()["error"]) == (409, "staging_changed")


def test_get_and_cancel(client: TestClient) -> None:
    r = client.get("/api/content/staging")
    assert (r.status_code, r.json()["error"]) == (404, "no_staging")
    r = client.delete("/api/content/staging")
    assert (r.status_code, r.json()["error"]) == (404, "no_staging")
    staged_id = stage(client).json()["staged_id"]
    vid = upload(client, NEW_MAIN)
    assert assign(client, staged_id, NEW_MAIN, vid).status_code == 200
    with client.websocket_connect("/ws/control") as control:
        assert client.delete("/api/content/staging").status_code == 204
        event = _scene_event(control, "staging")
    assert event == {"type": "scene", "kind": "staging", "action": "cancelled", "staged_id": staged_id}
    assert client.get("/api/content/staging").status_code == 404
    assert client.get("/api/state").json()["staging"] is None
    # FR-015a: what was uploaded stays in the manifest for later.
    entry = client.app.state.ctx.images.entry(NEW_MAIN)
    assert vid in entry["versions"] and entry["active"] == "kit"


def test_images_for_staged_products_upload_then_assign(client: TestClient) -> None:
    wait_drawn(client)
    staged_id = stage(client).json()["staged_id"]
    # A product that exists only in the staged set takes uploads (contracts/api.md §1).
    vid = upload(client, NEW_MAIN)
    r = assign(client, staged_id, NEW_MAIN, vid, confirmed=False)
    assert (r.status_code, r.json()["error"]) == (422, "rights_not_confirmed")
    r = assign(client, staged_id, NEW_MAIN, "0123456789ab")
    assert (r.status_code, r.json()["error"]) == (404, "unknown_version")
    r = assign(client, staged_id, "khong-co", vid)
    assert (r.status_code, r.json()["error"]) == (404, "unknown_product")
    r = assign(client, "ffffff", NEW_MAIN, vid)
    assert (r.status_code, r.json()["error"]) == (409, "staging_changed")
    with client.websocket_connect("/ws/control") as control:
        r = assign(client, staged_id, NEW_MAIN, vid)
        event = _scene_event(control, "staging")
    assert r.status_code == 200, r.text
    assert event["action"] == "updated"
    product = by_id(r.json())[NEW_MAIN]
    assert (product["image"], product["version_id"]) == ("staged", vid)
    assert product["rights_confirmed_at"] and product["has_alpha"] is True
    assert r.json()["missing"] == [NEW_SIDE]
    assert client.get("/api/state").json()["staging"]["missing"] == 1
    # Only the staged set knows: the manifest still has no active upload for it.
    assert client.app.state.ctx.images.entry(NEW_MAIN)["active"] == "kit"
    # Taking it back needs no rights box.
    r = assign(client, staged_id, NEW_MAIN, None, confirmed=False)
    assert by_id(r.json())[NEW_MAIN]["image"] == "missing"


def test_an_image_already_in_the_manifest_is_reused(client: TestClient) -> None:
    vid = upload(client, KEPT)
    r = client.post(f"/api/scene/images/{KEPT}/apply", json={"version_id": vid, "rights_confirmed": True})
    assert r.status_code == 200
    product = by_id(stage(client).json())[KEPT]
    assert (product["image"], product["version_id"]) == ("reused_upload", vid)
    assert product["thumb_url"] == f"/api/scene/images/{KEPT}/versions/{vid}.png"


def test_preview_draws_the_staged_set(client: TestClient) -> None:
    wait_drawn(client)
    r = client.get("/api/scene/preview.png?target=staging")
    assert (r.status_code, r.json()["error"]) == (404, "no_staging")
    staged_id = stage(client).json()["staged_id"]
    live = client.get("/api/scene/preview.png").content
    empty = client.get("/api/scene/preview.png?target=staging")
    assert empty.status_code == 200 and empty.headers["content-type"] == "image/png"
    assert assign(client, staged_id, NEW_MAIN, upload(client, NEW_MAIN, color=(250, 20, 20))).status_code == 200
    full = client.get("/api/scene/preview.png?target=staging").content
    assert Image.open(io.BytesIO(full)).size == Image.open(io.BytesIO(live)).size
    assert len({live, empty.content, full}) == 3
    r = client.get(f"/api/scene/preview.png?target=staging&product_id={NEW_MAIN}")
    assert r.status_code == 200
    r = client.get("/api/scene/preview.png?target=staging&product_id=khong-co")
    assert r.status_code == 404


def test_a_live_change_while_staging_is_flagged(client: TestClient) -> None:
    stage(client)
    assert put_content(client, staged_docx()).status_code == 200
    assert client.get("/api/content/staging").json()["live_changed"] is True


# ---------- T032: apply ----------


def test_apply_asks_again_when_products_lack_an_image(client: TestClient) -> None:
    before = wait_drawn(client)
    live_version = client.app.state.ctx.store.catalog.version
    staged_id = stage(client).json()["staged_id"]
    for confirm in (None, False, "true"):
        r = apply_set(client, staged_id, confirm=confirm)
        assert (r.status_code, r.json()["error"]) == (409, "missing_images")
    body = r.json()
    assert "Son môi A" in body["message"] and "Phấn B" in body["message"]
    assert body["details"] == [
        {"product_id": NEW_MAIN, "name": "Son môi A"},
        {"product_id": NEW_SIDE, "name": "Phấn B"},
    ]
    assert client.app.state.ctx.store.catalog.version == live_version
    assert client.get("/api/scene").json()["version"] == before["version"]
    assert client.get("/api/content/staging").status_code == 200


def test_apply_puts_catalog_and_images_live_together(client: TestClient, json_log_lines) -> None:
    before = wait_drawn(client)
    ctx = client.app.state.ctx
    live_version = ctx.store.catalog.version
    staged = stage(client).json()
    staged_id = staged["staged_id"]
    vid = upload(client, NEW_MAIN)
    assert assign(client, staged_id, NEW_MAIN, vid).status_code == 200
    replaced: list[str] = []
    real_replaced = ctx.director.on_catalog_replaced
    ctx.director.on_catalog_replaced = lambda catalog: (replaced.append(catalog.version), real_replaced(catalog))
    draws = record_draws(client)
    with client.websocket_connect("/ws/control") as control:
        r = apply_set(client, staged_id, confirm=True)
        event = _scene_event(control, "staging")
    assert r.status_code == 200, r.text
    body = r.json()
    new_version = ctx.store.catalog.version
    assert body["version"] == new_version != live_version
    assert [p["id"] for p in body["products"]] == STAGED_IDS
    assert (body["images_written"], body["missing_images"]) == (1, 1)
    assert body["scene_version"] > before["version"]
    assert 0 <= body["to_frame_ms"] < 2000
    assert replaced == [new_version]
    # Research R7: no frame ever showed the new cards with the old pictures.
    new_draws = [art for version, art in draws if version == new_version]
    assert new_draws and all(art[NEW_MAIN] == "upload" for art in new_draws)
    assert scene_sources(client)[NEW_MAIN] == ("upload", vid)
    assert ctx.images.entry(NEW_MAIN)["active"] == vid
    assert ctx.staging is None and client.get("/api/state").json()["staging"] is None
    assert event == {"type": "scene", "kind": "staging", "action": "applied", "staged_id": staged_id}
    applied = [ln for ln in json_log_lines if ln["event"] == "scene_staging_applied"]
    assert len(applied) == 1
    assert applied[0]["result"] == "ok" and applied[0]["images_written"] == 1 and applied[0]["missing_images"] == 1


def test_apply_with_every_image_needs_no_confirmation(client: TestClient) -> None:
    wait_drawn(client)
    staged_id = stage(client).json()["staged_id"]
    for pid in (NEW_MAIN, NEW_SIDE):
        assert assign(client, staged_id, pid, upload(client, pid)).status_code == 200
    r = apply_set(client, staged_id)
    assert r.status_code == 200, r.text
    assert (r.json()["images_written"], r.json()["missing_images"]) == (2, 0)


def test_manifest_write_failure_changes_nothing(client: TestClient, monkeypatch, json_log_lines) -> None:
    before = wait_drawn(client)
    ctx = client.app.state.ctx
    live_version = ctx.store.catalog.version
    staged_id = stage(client).json()["staged_id"]
    assert assign(client, staged_id, NEW_MAIN, upload(client, NEW_MAIN)).status_code == 200
    real = uploads_module._write_atomic

    def failing(path: Path, data: bytes) -> None:
        if path.name == "images.json":
            raise OSError("đĩa đầy")
        real(path, data)

    monkeypatch.setattr(uploads_module, "_write_atomic", failing)
    r = apply_set(client, staged_id, confirm=True)
    assert (r.status_code, r.json()["error"]) == (500, "save_failed")
    assert ctx.store.catalog.version == live_version
    assert ctx.images.entry(NEW_MAIN)["active"] == "kit"
    assert ctx.staging is not None and ctx.staging.staged_id == staged_id
    wait_drawn(client)
    assert client.get("/api/scene").json()["version"] >= before["version"]
    failed = [ln for ln in json_log_lines if ln["event"] == "scene_staging_applied"]
    assert [ln["result"] for ln in failed] == ["save_failed"]


def test_install_failure_puts_the_manifest_back(client: TestClient) -> None:
    wait_drawn(client)
    ctx = client.app.state.ctx
    live_version = ctx.store.catalog.version
    staged_id = stage(client).json()["staged_id"]
    assert assign(client, staged_id, NEW_MAIN, upload(client, NEW_MAIN)).status_code == 200

    def broken(catalog: Any) -> None:
        raise RuntimeError("hỏng")

    ctx.store.install = broken
    r = apply_set(client, staged_id, confirm=True)
    assert (r.status_code, r.json()["error"]) == (500, "save_failed")
    assert ctx.images.entry(NEW_MAIN)["active"] == "kit"
    assert ctx.store.catalog.version == live_version
    assert NEW_MAIN not in {i["product_id"] for i in client.get("/api/scene").json()["images"]}


def test_applied_images_survive_a_restart(scene_settings) -> None:
    with TestClient(create_app(scene_settings)) as c:
        staged_id = stage(c).json()["staged_id"]
        vid = upload(c, NEW_MAIN)
        assert assign(c, staged_id, NEW_MAIN, vid).status_code == 200
        assert apply_set(c, staged_id, confirm=True).status_code == 200
    with TestClient(create_app(scene_settings)) as c:
        assert c.app.state.ctx.images.entry(NEW_MAIN)["active"] == vid
        # A later file with the same product brings its picture back (FR-014).
        assert by_id(stage(c).json())[NEW_MAIN]["image"] == "reused_upload"


def _scene_event(control: Any, kind: str) -> dict:
    for _ in range(50):
        data = control.receive_json()
        if data.get("type") == "scene" and data.get("kind") == kind:
            return {k: v for k, v in data.items() if k != "ts"}
    raise AssertionError(f"no scene {kind} event")


# ---------- T071 (FR-004a): the shape warning follows the set the picture goes to ----------

HALF_FLAT = (440, 200)  # fits a secondary slot among 3 products, not among 4 (unless highlighted)


def four_product_docx() -> bytes:
    return build_docx(
        [
            *product_blocks("Son môi A", "chính", price="199.000đ"),
            *product_blocks("Sữa rửa mặt Y", "phụ", price="159.000đ", forbidden=()),
            *product_blocks("Phấn B", "phụ", price="99.000đ"),
            *product_blocks("Sản phẩm C", "phụ", price="89.000đ"),
        ]
    )


def upload_shape(client: TestClient, pid: str, size, target: str | None = None) -> dict:
    query = f"product_id={pid}" + (f"&target={target}" if target else "")
    r = client.post(
        f"/api/scene/uploads?{query}",
        content=image_bytes("png", size=size),
        headers={"Content-Type": "application/octet-stream", "X-Filename": quote("ảnh.png")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_the_shape_warning_follows_the_target_set(client: TestClient) -> None:
    wait_drawn(client)
    assert stage(client, four_product_docx()).status_code in (200, 201)
    # Live has 3 products: the slot is wide enough. The staged set has 4: narrower slots.
    assert upload_shape(client, KEPT, HALF_FLAT)["warnings"] == []
    staged = upload_shape(client, KEPT, HALF_FLAT, "staging")
    assert staged["warnings"] == ["too_wide"]
    assert "chỉ hiện lúc AI đang nói về món này" in staged["warning_messages"]["too_wide"]


def test_a_staged_only_product_is_judged_on_the_staged_set(client: TestClient) -> None:
    wait_drawn(client)
    assert stage(client, four_product_docx()).status_code in (200, 201)
    # Not in the live set: `target=live` falls back to the staged set.
    assert upload_shape(client, NEW_SIDE, HALF_FLAT)["warnings"] == ["too_wide"]


# ---------- 013 T035 (FR-017): a background-removed version goes into the staged set like any upload ----------


def test_a_cutout_version_can_be_assigned_to_the_staged_set(client: TestClient) -> None:
    wait_drawn(client)
    staged_id = stage(client).json()["staged_id"]
    r = client.post(
        f"/api/scene/uploads?product_id={NEW_MAIN}",
        content=matting_bytes("white_bg"),
        headers={"Content-Type": "application/octet-stream", "X-Filename": quote("son.png")},
    )
    assert r.status_code == 201, r.text
    cut = r.json()["cutout"]["version_id"]
    r = assign(client, staged_id, NEW_MAIN, cut)
    assert r.status_code == 200, r.text
    product = by_id(r.json())[NEW_MAIN]
    assert (product["image"], product["version_id"], product["has_alpha"]) == ("staged", cut, True)
    r = apply_set(client, staged_id, confirm=True)
    assert r.status_code == 200, r.text
    assert scene_sources(client)[NEW_MAIN] == ("upload", cut)
