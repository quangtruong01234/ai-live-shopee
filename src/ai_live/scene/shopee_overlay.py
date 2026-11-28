"""Where the Shopee app covers the live picture on a portrait phone (spec 014 FR-019, SC-008, ADR-085).

The zones were measured as screen fractions on one 900x2000 (9:20) phone screenshot of a Shopee AI live taken
2026-11-25. The app is assumed to fill the screen and crop the video ("aspect fill"): a 480x832 frame on a 9:20
screen loses ~11% of its width on each side. TODO: check aspect fill against letterboxing on a test live on Shopee or
on a real phone, and re-measure if the app's layout changes.

Used by the realism tool to flag the AI label or desk products under the app's UI, and by the showcase layout when
`layout.avoid_app_overlay` is on: the product cluster then stands above the comments and chat bar (ADR-087).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ai_live.scene.models import Box

PHONE_ASPECT = 9 / 20  # screen width / height of the reference phone


@dataclass(frozen=True)
class OverlayZone:
    """One app overlay as fractions of the phone screen; x2/y2 exclusive."""

    name: str
    x1: float
    y1: float
    x2: float
    y2: float


ZONES: tuple[OverlayZone, ...] = (
    OverlayZone("header", 0.0, 0.0, 1.0, 0.115),  # live title, shop name, follow button, viewers, close
    OverlayZone("badges_left", 0.03, 0.13, 0.33, 0.19),  # "Streamer AI" and creator chips
    OverlayZone("pinned_product", 0.03, 0.21, 0.27, 0.37),  # the pinned product card
    OverlayZone("rewards_right", 0.69, 0.136, 0.96, 0.27),  # coins and reward widgets
    OverlayZone("comments", 0.0, 0.83, 0.73, 0.91),  # comment bubbles
    OverlayZone("chat_bar", 0.0, 0.93, 1.0, 0.985),  # chat input, cart, share, like
)


def _shown(width: int, height: int, phone_aspect: float) -> tuple[float, float, float, float]:
    """Offset and size of the frame part the phone shows (aspect fill: the app crops what does not fit)."""
    if width / height >= phone_aspect:
        shown_w, shown_h = phone_aspect * height, float(height)  # the sides are cut off
    else:
        shown_w, shown_h = float(width), width / phone_aspect  # the top and bottom are cut off
    return (width - shown_w) / 2, (height - shown_h) / 2, shown_w, shown_h


def shown_box(width: int, height: int, phone_aspect: float = PHONE_ASPECT) -> Box:
    """The part of the frame the phone shows at all; what lies outside it never reaches a viewer."""
    off_x, off_y, _, _ = _shown(width, height, phone_aspect)
    x1, y1 = round(off_x), round(off_y)
    return x1, y1, width - x1, height - y1


def frame_boxes(width: int, height: int, phone_aspect: float = PHONE_ASPECT) -> list[tuple[str, Box]]:
    """Each zone as a box in frame pixels, clamped to the frame."""
    off_x, off_y, shown_w, shown_h = _shown(width, height, phone_aspect)
    boxes: list[tuple[str, Box]] = []
    for zone in ZONES:
        x1 = max(0, min(width, round(off_x + zone.x1 * shown_w)))
        x2 = max(0, min(width, round(off_x + zone.x2 * shown_w)))
        y1 = max(0, min(height, round(off_y + zone.y1 * shown_h)))
        y2 = max(0, min(height, round(off_y + zone.y2 * shown_h)))
        # A zone that starts at the screen edge reaches the frame edge too, past the cropped strip.
        if zone.x1 == 0.0:
            x1 = 0
        if zone.x2 == 1.0:
            x2 = width
        if zone.y1 == 0.0:
            y1 = 0
        boxes.append((zone.name, (x1, y1, x2, y2)))
    return boxes


def zone_mask(width: int, height: int, phone_aspect: float = PHONE_ASPECT) -> np.ndarray:
    """(height, width) bool: True where any app overlay covers the frame."""
    mask = np.zeros((height, width), bool)
    for _, (x1, y1, x2, y2) in frame_boxes(width, height, phone_aspect):
        mask[y1:y2, x1:x2] = True
    return mask


def box_share(box: Box, width: int, height: int, phone_aspect: float = PHONE_ASPECT) -> float:
    """Share of `box` (clipped to the frame) that some app overlay covers, 0..1."""
    x1, y1 = max(0, box[0]), max(0, box[1])
    x2, y2 = min(width, box[2]), min(height, box[3])
    if x1 >= x2 or y1 >= y2:
        return 0.0
    return float(zone_mask(width, height, phone_aspect)[y1:y2, x1:x2].mean())
