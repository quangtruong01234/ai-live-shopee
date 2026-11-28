"""014 T070: `realism_report.py` reports what the Shopee app's UI covers (FR-019, SC-008, ADR-085).

The skill script is not a package, so it is loaded with importlib.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ai_live.scene.layout import estimate_label_box
from ai_live.scene.shopee_overlay import frame_boxes, shown_box

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".claude" / "skills" / "live-scene-realism" / "scripts"
W, H = 480, 832
TEXT = "AI-GENERATED CONTENT"


@pytest.fixture(scope="module")
def rr():
    spec = importlib.util.spec_from_file_location("realism_report_overlay_test", SCRIPTS / "realism_report.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mask(box) -> np.ndarray:
    x1, y1, x2, y2 = box
    mask = np.zeros((H, W), bool)
    mask[y1:y2, x1:x2] = True
    return mask


def test_shown_box_is_the_part_of_the_frame_the_phone_shows():
    x1, y1, x2, y2 = shown_box(W, H)
    assert (y1, y2) == (0, H)
    assert x1 == round((W - 0.45 * H) / 2) and x2 == W - x1
    assert shown_box(1080, 1920)[0] == 108


def test_default_label_and_a_central_product_are_clear(rr):
    label = estimate_label_box(W, H, TEXT, "shopee-top")
    report = rr.overlay_report(label, {"main": _mask((200, 400, 280, 680))}, W, H)
    assert report["label"]["share"] == 0.0 and report["label"]["zones"] == []
    assert report["products"]["main"]["covered_share"] == 0.0
    assert report["products"]["main"]["cropped_share"] == 0.0
    assert report["flags"] == []


def test_a_label_under_the_app_title_is_flagged(rr):
    label = estimate_label_box(W, H, TEXT, "top-center")
    report = rr.overlay_report(label, {}, W, H)
    assert report["label"]["share"] > 0.5 and "header" in report["label"]["zones"]
    assert any("AI label" in flag and "header" in flag for flag in report["flags"])


def test_a_product_under_the_comments_is_flagged_with_its_share(rr):
    _, (cx1, cy1, cx2, cy2) = next(item for item in frame_boxes(W, H) if item[0] == "comments")
    # The lower half of the product sits under the comment bubbles.
    half = (cy2 - cy1) // 2
    box = (cx1 + 80, cy1 - (cy2 - cy1) + half, cx1 + 160, cy1 + half)
    report = rr.overlay_report(None, {"side": _mask(box)}, W, H)
    row = report["products"]["side"]
    assert row["zones"] == ["comments"]
    assert row["covered_share"] == pytest.approx(0.5, abs=0.03)
    assert any(flag.startswith("side:") and "comments" in flag for flag in report["flags"])


def test_a_small_overlap_is_reported_but_not_flagged(rr):
    _, (cx1, cy1, _, _) = next(item for item in frame_boxes(W, H) if item[0] == "comments")
    box = (cx1 + 80, cy1 - 95, cx1 + 160, cy1 + 5)  # 5 of 100 rows
    report = rr.overlay_report(None, {"side": _mask(box)}, W, H)
    assert 0 < report["products"]["side"]["covered_share"] <= rr.OVERLAY_PRODUCT_MAX
    assert report["flags"] == []


def test_a_product_past_the_phone_crop_is_flagged(rr):
    x1 = shown_box(W, H)[0]
    report = rr.overlay_report(None, {"edge": _mask((0, 400, x1 + x1, 600))}, W, H)
    assert report["products"]["edge"]["cropped_share"] == pytest.approx(0.5, abs=0.02)
    assert any(flag.startswith("edge:") and "crop" in flag for flag in report["flags"])


def test_draw_overlay_zones_marks_the_zones_and_the_crop(rr):
    image = Image.new("RGB", (W, H), (128, 128, 128))
    out = np.asarray(rr.draw_overlay_zones(image), np.int16)
    assert out.shape == (H, W, 3)
    assert (np.asarray(image) == 128).all()  # the input is left as it was
    _, (hx1, hy1, hx2, hy2) = frame_boxes(W, H)[0]
    assert (out[(hy1 + hy2) // 2, W // 2] != 128).any()  # inside the header zone
    assert (out[H // 2, 5] < 128).all()  # the cropped side strip is darkened
    assert (out[H // 2, W // 2] == 128).all()  # the free middle stays untouched
