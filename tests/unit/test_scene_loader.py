"""009 T010: reading a scene set never raises; every problem is a SceneIssue with the code the contract names."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import LayoutParams
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
    assert scene.art["a"].image.size == (200, 400)


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


# ---------- 013 T007: layout.mode / cards / brightness (contracts/scene-set.md §1, data-model §1, FR-019) ----------


def _layout(tmp_path: Path, layout: dict) -> tuple:
    root = make_scene_dir(tmp_path / "scene", IDS, scene={"layout": layout})
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    return scene.layout, {i.code: i.level for i in scene.issues}


def test_layout_without_mode_is_exactly_009(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"desk_top": 0.8, "highlight_scale": 1.4})
    assert layout == LayoutParams(desk_top=0.8, highlight_scale=1.4)
    assert layout.mode == "rows" and layout.cards == "all" and layout.brightness == 1.0
    assert codes == {}


def test_unknown_mode_is_an_error_and_draws_rows(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "shelf"})
    assert layout.mode == "rows" and layout.cards == "all"
    assert codes["bad_layout"] == "error"


def test_realistic_defaults(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic"})
    assert layout.mode == "realistic"
    assert layout.cards == "none"
    assert layout.highlight_scale == pytest.approx(1.08)
    assert layout.brightness == 1.0
    assert layout.max_slots == 5
    assert codes == {}


@pytest.mark.parametrize("cards", ["none", "one", "all"])
def test_realistic_takes_every_cards_value(tmp_path: Path, cards: str) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic", "cards": cards})
    assert layout.cards == cards
    assert codes == {}


@pytest.mark.parametrize("cards", ["none", "one"])
def test_rows_always_has_cards(tmp_path: Path, cards: str) -> None:
    layout, codes = _layout(tmp_path, {"cards": cards})
    assert layout.cards == "all"
    assert codes == {"cards_ignored": "warning"}


def test_rows_with_cards_all_does_not_warn(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "rows", "cards": "all"})
    assert layout.cards == "all" and codes == {}


def test_unknown_cards_value_is_a_layout_error(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic", "cards": "some"})
    assert layout.cards == "none"
    assert codes["bad_layout"] == "error"


@pytest.mark.parametrize(("value", "used"), [(0.5, 0.85), (1.5, 1.10)])
def test_brightness_out_of_range_is_clamped(tmp_path: Path, value: float, used: float) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic", "brightness": value})
    assert layout.brightness == pytest.approx(used)
    assert codes == {"layout_clamped": "warning"}


def test_brightness_in_range_is_kept(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic", "brightness": 0.9})
    assert layout.brightness == pytest.approx(0.9) and codes == {}


def test_brightness_not_a_number_falls_back(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic", "brightness": "bright"})
    assert layout.brightness == 1.0
    assert codes["bad_scene_json"] == "error"


@pytest.mark.parametrize(
    ("mode", "value", "used"),
    [("realistic", 1.3, 1.10), ("realistic", 0.9, 1.00), ("rows", 2.0, 1.6), ("rows", 0.5, 1.0)],
)
def test_highlight_scale_is_clamped_to_the_mode_range(tmp_path: Path, mode: str, value: float, used: float) -> None:
    layout, codes = _layout(tmp_path, {"mode": mode, "highlight_scale": value})
    assert layout.highlight_scale == pytest.approx(used)
    assert codes == {"layout_clamped": "warning"}


def test_realistic_highlight_scale_in_range_is_kept(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic", "highlight_scale": 1.08})
    assert layout.highlight_scale == pytest.approx(1.08) and codes == {}


def test_realistic_max_slots_above_five_is_clamped(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"mode": "realistic", "max_slots": 7})
    assert layout.max_slots == 5
    assert codes == {"layout_clamped": "warning"}


def test_rows_max_slots_seven_is_kept(tmp_path: Path) -> None:
    layout, codes = _layout(tmp_path, {"max_slots": 7})
    assert layout.max_slots == 7 and codes == {}
