"""Loading rules for uploaded product images (specs/012-product-image-upload/contracts/scene-set.md §3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_live.scene.loader import load_scene_set
from ai_live.scene.uploads import validate_and_normalize
from fixtures.scene_builder import CUSTOMER, image_bytes, make_scene_dir, write_manifest

IDS = ["sua-rua-mat", "kem-chong-nang", "toner"]
CONFIRMED = "2026-11-20T09:00:00.000Z"


def _codes(scene: Any, pid: str | None = None) -> set[str]:
    return {i.code for i in scene.issues if pid is None or i.product_id == pid}


def _upload(root: Path, pid: str, kind: str = "png", size: tuple[int, int] = (300, 500)) -> str:
    image = validate_and_normalize(image_bytes(kind, size=size))  # type: ignore[arg-type]
    path = root / "uploads" / pid / f"{image.version_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image.png)
    return image.version_id


def _version(confirmed: str | None = CONFIRMED) -> dict[str, Any]:
    return {
        "uploaded_at": CONFIRMED,
        "source_name": "a.png",
        "width": 300,
        "height": 500,
        "has_alpha": True,
        "bytes": 1,
        "applied_at": CONFIRMED,
        "rights_confirmed_at": confirmed,
    }


def _manifest(products: dict[str, Any], *, customer: str = CUSTOMER) -> dict[str, Any]:
    return {"schema_version": 1, "customer_id": customer, "products": products}


def _entry(active: str | None, versions: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"active": active, "history": ["kit"], "updated_at": CONFIRMED, "versions": versions or {}}


def test_no_uploads_folder_behaves_like_009(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert set(scene.art) == set(IDS)
    assert all(a.source == "kit" and a.version_id is None for a in scene.art.values())
    assert not scene.has_errors


def test_kit_entry_keeps_the_009_image(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    write_manifest(root, _manifest({"toner": _entry("kit")}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert scene.art["toner"].source == "kit"
    assert scene.art["toner"].path == root / "products" / "toner.png"


def test_confirmed_upload_replaces_the_kit_image_without_provenance(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = _upload(root, "toner", size=(600, 1000))
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version()})}))
    # Drop provenance for this product entirely: uploads do not need it (ADR-071).
    prov_path = root / "provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    del prov["products"]["toner"]
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    art = scene.art["toner"]
    assert art.source == "upload"
    assert art.version_id == vid
    assert art.path == root / "uploads" / "toner" / f"{vid}.png"
    # Cropped and shrunk like 009 art: long side ≤ 640.
    assert max(art.image.size) == 640
    assert not _codes(scene, "toner")
    assert "orphan_image" not in _codes(scene)
    assert not scene.has_errors


def test_upload_for_product_without_kit_image(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", ["sua-rua-mat"])
    vid = _upload(root, "toner")
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version()})}))
    scene = load_scene_set(root, ["sua-rua-mat", "toner"], customer_id=CUSTOMER)
    assert scene.art["toner"].source == "upload"
    assert not _codes(scene, "toner")


def test_upload_without_rights_confirmation_is_not_drawn(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = _upload(root, "toner")
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version(confirmed=None)})}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "toner" not in scene.art
    issue = next(i for i in scene.issues if i.code == "missing_confirmation")
    assert issue.level == "error"
    assert issue.product_id == "toner"
    assert issue.message == "Ảnh tải lên của sản phẩm toner chưa có xác nhận quyền dùng: không hiện"


def test_missing_upload_file_is_an_error(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = "0123456789ab"
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version()})}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "toner" not in scene.art
    issue = next(i for i in scene.issues if i.code == "bad_uploads")
    assert issue.level == "error"
    assert issue.message == f"Ảnh tải lên {vid} của sản phẩm toner không đọc được"


def test_broken_upload_file_is_an_error(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = "0123456789ab"
    path = root / "uploads" / "toner" / f"{vid}.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(image_bytes("png_truncated"))
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version()})}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "toner" not in scene.art
    assert "bad_uploads" in _codes(scene, "toner")


def test_active_version_missing_from_versions_is_an_error(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = _upload(root, "toner")
    write_manifest(root, _manifest({"toner": _entry(vid, {})}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "toner" not in scene.art
    assert "bad_uploads" in _codes(scene, "toner")


def test_removed_image_shows_only_the_card(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    write_manifest(root, _manifest({"toner": _entry(None)}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "toner" not in scene.art
    issue = next(i for i in scene.issues if i.product_id == "toner")
    assert (issue.level, issue.code) == ("warning", "missing_image")
    assert "đã gỡ ảnh" in issue.message
    assert "orphan_image" not in _codes(scene)
    assert not scene.has_errors


def test_managed_products_skip_kit_provenance_checks(tmp_path: Path) -> None:
    """A placeholder or broken kit record of a product now using an upload must not raise kit issues for it."""
    root = make_scene_dir(
        tmp_path / "demo",
        IDS,
        records={"toner": {"original": "originals/missing.jpg", "edits": ["ai_generated"], "placeholder": False}},
    )
    vid = _upload(root, "toner")
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version()})}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert not _codes(scene, "toner")


def test_broken_manifest_is_ignored_with_an_error(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    write_manifest(root, "{không phải json")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert set(scene.art) == set(IDS)
    issue = next(i for i in scene.issues if i.code == "bad_uploads")
    assert issue.level == "error"
    assert issue.message.startswith("uploads/images.json hỏng: ")


def test_manifest_that_is_not_an_object_is_ignored(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    write_manifest(root, "[1, 2]")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert set(scene.art) == set(IDS)
    assert "bad_uploads" in _codes(scene)


def test_unknown_schema_version_ignores_the_manifest(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = _upload(root, "toner")
    write_manifest(root, {**_manifest({"toner": _entry(vid, {vid: _version()})}), "schema_version": 2})
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert scene.art["toner"].source == "kit"
    assert "bad_uploads" in _codes(scene)


def test_other_customers_manifest_blocks_the_scene(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    write_manifest(root, _manifest({}, customer="shop_khac"))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "customer_mismatch" in _codes(scene)
    assert scene.blocked


def test_uploads_of_products_outside_the_catalog_are_ignored(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = _upload(root, "serum-cu")
    write_manifest(root, _manifest({"serum-cu": _entry(vid, {vid: _version(confirmed=None)})}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "serum-cu" not in scene.art
    assert not _codes(scene, "serum-cu")
    assert not scene.has_errors


def test_bad_product_key_in_manifest_is_skipped(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    write_manifest(root, _manifest({"../escape": _entry(None)}))
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert set(scene.art) == set(IDS)
    assert "bad_uploads" in _codes(scene)


def _run_check(monkeypatch: Any, root: Path, ids: list[str]) -> int:
    """`python -m ai_live.scene check` on `root` with a catalog of `ids` (no content file needed)."""
    from ai_live.scene import __main__ as cli
    from fixtures.scene_builder import catalog, product

    monkeypatch.setenv("CUSTOMER_ID", CUSTOMER)
    monkeypatch.setattr(cli, "_catalog", lambda path, settings: catalog(*(product(pid) for pid in ids)))
    return cli.main(["check", str(root)])


def test_check_command_counts_uploaded_images(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = _upload(root, "toner")
    prov_path = root / "provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    del prov["products"]["toner"]
    prov_path.write_text(json.dumps(prov), encoding="utf-8")
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version()}), "sua-rua-mat": _entry(None)}))

    assert _run_check(monkeypatch, root, IDS) == 0
    out = capsys.readouterr().out
    assert "Ảnh tải lên: 1 đang dùng, 0 thiếu xác nhận, 1 đã gỡ" in out
    # The uploaded product does not need a provenance record (ADR-071).
    assert "toner" not in out


def test_check_command_fails_on_unconfirmed_upload(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    root = make_scene_dir(tmp_path / "demo", IDS)
    vid = _upload(root, "toner")
    write_manifest(root, _manifest({"toner": _entry(vid, {vid: _version(confirmed=None)})}))

    assert _run_check(monkeypatch, root, IDS) == 1
    out = capsys.readouterr().out
    assert "missing_confirmation" in out
    assert "Ảnh tải lên: 0 đang dùng, 1 thiếu xác nhận, 0 đã gỡ" in out
