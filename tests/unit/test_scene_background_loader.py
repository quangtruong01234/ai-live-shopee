"""014 T006: the optional `background` block of `scene.json` (014 data-model §1, FR-001, FR-006, FR-007; no GPU)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import BackgroundConfig
from fixtures.scene_builder import CUSTOMER, make_scene_dir

PIDS = ["sua-rua-mat"]


def _load(tmp_path: Path, background: Any = None, *, omit: bool = False):
    scene: dict[str, Any] = {} if omit else {"background": background}
    root = make_scene_dir(tmp_path / "scene", PIDS, scene=scene)
    scene_set = load_scene_set(root, PIDS, customer_id=CUSTOMER)
    return scene_set, {i.code: i.level for i in scene_set.issues}


def _events(caplog: pytest.LogCaptureFixture, name: str) -> list[dict[str, Any]]:
    return [getattr(r, "fields", {}) for r in caplog.records if r.getMessage() == name]


def test_missing_block_means_the_original_room(tmp_path: Path) -> None:
    scene_set, codes = _load(tmp_path, omit=True)
    assert scene_set.background == BackgroundConfig()
    assert scene_set.background.style == "goc"
    assert (scene_set.background.softness_px, scene_set.background.brightness, scene_set.background.max_items) == (
        1.5,  # ADR-086
        0.95,
        12,
    )
    assert codes == {}


def test_shelves_block_with_numbers_is_read(tmp_path: Path) -> None:
    scene_set, codes = _load(tmp_path, {"style": "ke_hang", "softness_px": 2.5, "brightness": 1.0, "max_items": 6})
    assert scene_set.background == BackgroundConfig(style="ke_hang", softness_px=2.5, brightness=1.0, max_items=6)
    assert codes == {}


@pytest.mark.parametrize("style", ["bang_shop", "anh_shop"])
def test_post_demo_styles_are_readable(tmp_path: Path, style: str) -> None:
    scene_set, codes = _load(tmp_path, {"style": style})
    assert scene_set.background.style == style
    assert codes == {}


@pytest.mark.parametrize("style", ["lam_mo", "blur", 3, None])
def test_unknown_style_is_a_scene_error_and_falls_back_to_the_room(tmp_path: Path, style: Any) -> None:
    scene_set, codes = _load(tmp_path, {"style": style})
    assert scene_set.background.style == "goc"
    assert codes["bad_scene_json"] == "error"


def test_block_that_is_not_an_object_is_a_scene_error(tmp_path: Path) -> None:
    scene_set, codes = _load(tmp_path, "ke_hang")
    assert scene_set.background == BackgroundConfig()
    assert codes["bad_scene_json"] == "error"


@pytest.mark.parametrize(
    ("field", "value", "used"),
    [
        ("softness_px", 12, 8.0),
        ("softness_px", -1, 0.0),
        ("brightness", 0.5, 0.8),
        ("brightness", 1.4, 1.1),
        ("max_items", 0, 1),
        ("max_items", 40, 24),
    ],
)
def test_out_of_range_numbers_are_clamped_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, field: str, value: float, used: float
) -> None:
    caplog.set_level(logging.INFO, logger="ai_live")
    scene_set, codes = _load(tmp_path, {"style": "ke_hang", field: value})
    assert getattr(scene_set.background, field) == pytest.approx(used)
    assert codes == {"background_clamped": "warning"}
    (fields,) = _events(caplog, "background_clamped")
    assert fields == {"field": field, "value": value, "clamped_to": used}


def test_max_items_stays_an_integer(tmp_path: Path) -> None:
    scene_set, _ = _load(tmp_path, {"style": "ke_hang", "max_items": 7.6})
    assert scene_set.background.max_items == 7
    assert isinstance(scene_set.background.max_items, int)


def test_softness_zero_is_allowed(tmp_path: Path) -> None:
    scene_set, codes = _load(tmp_path, {"style": "ke_hang", "softness_px": 0})
    assert scene_set.background.softness_px == 0.0
    assert codes == {}


def test_non_number_falls_back_to_the_default(tmp_path: Path) -> None:
    scene_set, codes = _load(tmp_path, {"style": "ke_hang", "brightness": "sáng"})
    assert scene_set.background.brightness == 0.95
    assert codes["bad_scene_json"] == "error"


def test_unknown_key_is_warned_and_ignored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ai_live")
    scene_set, codes = _load(tmp_path, {"style": "ke_hang", "blur_px": 9})
    assert scene_set.background == BackgroundConfig(style="ke_hang")
    assert codes == {"background_unknown_key": "warning"}
    (fields,) = _events(caplog, "background_unknown_key")
    assert fields == {"key": "blur_px"}


def test_background_is_not_an_unknown_scene_key(tmp_path: Path) -> None:
    _, codes = _load(tmp_path, {"style": "ke_hang"})
    assert "unknown_key" not in codes


def test_as_is_is_read_and_always_warned(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ai_live")
    scene_set, codes = _load(tmp_path, {"style": "anh_shop", "as_is": True})
    assert scene_set.background.as_is is True
    assert codes.get("background_as_is") == "warning"
    assert _events(caplog, "background_as_is") == [{"style": "anh_shop"}]


def test_as_is_that_is_not_a_bool_is_a_scene_error(tmp_path: Path) -> None:
    scene_set, codes = _load(tmp_path, {"style": "anh_shop", "as_is": "yes"})
    assert scene_set.background.as_is is False
    assert codes["bad_scene_json"] == "error"
