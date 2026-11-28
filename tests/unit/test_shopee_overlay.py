"""014 T069: where the Shopee app covers the live frame on a portrait phone (FR-019, SC-008, ADR-085)."""

from __future__ import annotations

import numpy as np
import pytest

from ai_live.scene.layout import estimate_label_box
from ai_live.scene.models import intersects
from ai_live.scene.shopee_overlay import PHONE_ASPECT, ZONES, box_share, frame_boxes, zone_mask

W, H = 480, 832


def test_zone_table_names_every_app_overlay():
    names = {zone.name for zone in ZONES}
    assert {"header", "badges_left", "pinned_product", "rewards_right", "comments", "chat_bar"} <= names
    for zone in ZONES:
        assert 0 <= zone.x1 < zone.x2 <= 1 and 0 <= zone.y1 < zone.y2 <= 1, zone


def test_aspect_fill_crops_the_frame_sides_on_a_narrower_phone():
    boxes = dict(frame_boxes(W, H))
    crop = (W - PHONE_ASPECT * H) / 2  # ~53 px cut on each side of a 480x832 frame
    assert boxes["header"][0] == 0 and boxes["header"][2] == W  # clamped to the frame
    assert boxes["header"][3] == pytest.approx(0.115 * H, abs=1)
    x1 = boxes["badges_left"][0]
    assert x1 == pytest.approx(crop + 0.03 * PHONE_ASPECT * H, abs=1)
    assert boxes["chat_bar"][3] <= H


def test_a_wider_phone_crops_top_and_bottom_instead():
    boxes = dict(frame_boxes(W, H, phone_aspect=0.7))
    crop_y = (H - W / 0.7) / 2
    assert boxes["header"][1] == 0 and boxes["header"][3] == pytest.approx(crop_y + 0.115 * W / 0.7, abs=1)
    assert boxes["badges_left"][0] == pytest.approx(0.03 * W, abs=1)


@pytest.mark.parametrize("size", [(480, 832), (1080, 1920), (360, 640)])
def test_shopee_top_label_is_clear_of_every_app_overlay(size):
    # SC-008: on Shopee the label must not sit under the app's title, chips or reward widgets (ADR-085, ADR-090).
    width, height = size
    label = estimate_label_box(width, height, "AI-GENERATED CONTENT", "shopee-top")
    for name, box in frame_boxes(width, height):
        assert not intersects(label, box), (name, label, box)
    assert box_share(label, width, height) == 0.0


def test_the_meet_default_top_center_label_would_sit_under_the_app_title():
    label = estimate_label_box(W, H, "AI-GENERATED CONTENT", "top-center")
    assert box_share(label, W, H) > 0.5


def test_zone_mask_matches_the_boxes():
    mask = zone_mask(W, H)
    assert mask.shape == (H, W) and mask.dtype == bool
    for _, (x1, y1, x2, y2) in frame_boxes(W, H):
        assert mask[y1:y2, x1:x2].all()
    assert not mask[H // 2, W // 2]  # the host's chest is clear
    assert np.isclose(box_share((0, 0, W, 10), W, H), 1.0)
