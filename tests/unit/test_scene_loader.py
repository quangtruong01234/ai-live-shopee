"""009 T010: reading a scene set never raises; every problem is a SceneIssue with the code the contract names."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from ai_live.scene.loader import load_scene_set
from fixtures.scene_builder import CUSTOMER, make_scene_dir, product_png

IDS = ["a", "b", "c"]


def _codes(scene) -> list[str]:
    return [i.code for i in scene.issues]


def test_full_set_loads_without_issue(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert scene.issues == ()
    assert set(scene.art) == set(IDS)
    assert scene.desk is not None and scene.desk.mode == "RGBA"
    assert not scene.blocked
    # Cropped to the opaque area.
    assert scene.art["a"].image.size == (120, 240)


def test_jpeg_product_is_no_alpha(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    (root / "products" / "b.png").unlink()
    Image.new("RGB", (40, 40), (1, 2, 3)).save(root / "products" / "b.jpg")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "no_alpha" in _codes(scene)
    assert "b" not in scene.art


def test_png_without_alpha_is_no_alpha(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    Image.new("RGB", (40, 40), (1, 2, 3)).save(root / "products" / "b.png")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    issue = next(i for i in scene.issues if i.code == "no_alpha")
    assert issue.level == "error" and issue.product_id == "b"


def test_broken_image(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    (root / "products" / "c.png").write_bytes(b"not a png")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "bad_image" in _codes(scene)
    assert "c" not in scene.art


def test_missing_image_only_warns(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    (root / "products" / "a.png").unlink()
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    issue = next(i for i in scene.issues if i.code == "missing_image")
    assert issue.level == "warning" and issue.product_id == "a"
    assert not scene.has_errors


def test_orphan_image_warns(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    product_png(root / "products" / "old-product.png")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "orphan_image" in _codes(scene)
    assert "old-product" not in scene.art


def test_missing_provenance_file(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    (root / "provenance.json").unlink()
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert _codes(scene).count("missing_provenance") == len(IDS)
    assert scene.has_errors


def test_missing_provenance_entry(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    data = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    del data["products"]["c"]
    (root / "provenance.json").write_text(json.dumps(data), encoding="utf-8")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert [i.product_id for i in scene.issues if i.code == "missing_provenance"] == ["c"]


def test_forbidden_edits(tmp_path: Path) -> None:
    root = make_scene_dir(
        tmp_path / "scene",
        IDS,
        records={
            "a": {"original": "originals/a.jpg", "edits": ["ai_generated"]},
            "b": {"original": "originals/b.jpg", "edits": ["recolor_label"]},
        },
    )
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "ai_product" in _codes(scene)
    assert "bad_edit" in _codes(scene)
    assert scene.has_errors


def test_missing_original(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    (root / "originals" / "a.jpg").unlink()
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert [i.product_id for i in scene.issues if i.code == "missing_original"] == ["a"]


def test_placeholder_warns_and_marks_art(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS, records={"a": {"original": None, "placeholder": True}})
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert [i.level for i in scene.issues if i.code == "placeholder"] == ["warning"]
    assert scene.art["a"].placeholder and not scene.art["b"].placeholder


def test_customer_mismatch_blocks(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS, customer_id="other_shop")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "customer_mismatch" in _codes(scene)
    assert scene.blocked


def test_unset_customer_id_does_not_block(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS, customer_id="other_shop")
    assert not load_scene_set(root, IDS, customer_id="").blocked


def test_missing_scene_json_uses_defaults(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS)
    (root / "scene.json").unlink()
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert "missing_scene_json" in _codes(scene)
    assert scene.layout.desk_top == 0.76
    assert set(scene.art) == set(IDS)


def test_missing_dir_does_not_raise(tmp_path: Path) -> None:
    scene = load_scene_set(tmp_path / "nowhere", IDS, customer_id=CUSTOMER)
    assert _codes(scene) == ["missing_dir"]
    assert scene.blocked and scene.art == {}


def test_bad_layout_values_fall_back(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS, scene={"layout": {"desk_top": 0.2, "max_slots": 3, "zoom": 2}})
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert scene.layout.desk_top == 0.76
    assert scene.layout.max_slots == 3
    assert "bad_scene_json" in _codes(scene) and "unknown_key" in _codes(scene)


def test_path_outside_scene_dir_is_refused(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS, scene={"desk": "../desk.png"})
    Image.new("RGB", (10, 10)).save(tmp_path / "desk.png")
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert scene.desk is None
    assert "bad_scene_json" in _codes(scene)


def test_missing_desk_warns(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", IDS, desk=False)
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    assert [i.level for i in scene.issues if i.code == "missing_desk"] == ["warning"]
    assert scene.desk is None
