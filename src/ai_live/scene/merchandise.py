"""013 showcase merchandising for a "hot live" desk (ADR-095): stock groups of one product's picture.

A shop live shows stock, not one lone unit: bottles stand as a two-row cluster, cans stand as a small pyramid, a pack
has a second one behind it. The group is built once at load time from the product's own cut-out, so the layout and
the renderer keep handling one picture per product. Only the units' brightness changes (FR-006: colour, text and
shape stay).
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from typing import Literal

from PIL import Image, ImageEnhance

from ai_live.scene.limits import ART_MAX_SIDE
from ai_live.scene.models import LayoutParams, ProductArt

StockKind = Literal["row", "pyramid", "pair", "single"]

# Width / height of one unit. A bottle is narrow; a can is squat but still taller than wide; a pack is nearly square;
# a flat box is wider than tall and stays one unit.
STOCK_ROW_MAX_ASPECT = 0.45
STOCK_PYRAMID_MAX_ASPECT = 0.65
STOCK_PAIR_MAX_ASPECT = 1.2
# Units further back on the desk are a little darker.
STOCK_BACK_SHADE = 0.86
# Bottles as a two-row cluster (013 FR-035, ADR-098): a front row standing side by side and a back row further back,
# staggered by half a bottle so each back bottle shows between two front ones. The back row stands higher by what it
# loses to distance, so its tops line up with the front row's: the group stays one unit tall and the layout's
# real-size rule (ADR-082) still sizes one bottle. Was one bottle with two peeking behind it (ADR-095).
STOCK_ROW_FRONT = 2
STOCK_ROW_BACK = 3
STOCK_ROW_BACK_SCALE = 0.85
STOCK_ROW_SPACING = 1.0  # x unit width between two bottles' centres in a row: touching
# Pyramid: two cans side by side with this gap (x unit width), one more on top in the middle.
STOCK_PYRAMID_GAP = 0.04
STOCK_TOP_SHADE = 0.95
# Pair: a pack has a second one just behind it, this much smaller, standing this much higher (x unit height) and
# showing this share of its width on the right. A pyramid of packs would be two packs tall, and the layout sizes a
# picture by its height: each pack would show at half its real size.
STOCK_BACK_SCALE = 0.94
STOCK_BACK_LIFT = 0.03
STOCK_PAIR_SHOWN = 0.25


def stock_kind(size: tuple[int, int]) -> StockKind:
    """How a picture of `size` is stocked: by its shape, so a six-pack or a box stays one unit."""
    w, h = size
    aspect = w / h if h else 0.0
    if 0 < aspect <= STOCK_ROW_MAX_ASPECT:
        return "row"
    if aspect <= STOCK_PYRAMID_MAX_ASPECT:
        return "pyramid"
    if aspect <= STOCK_PAIR_MAX_ASPECT:
        return "pair"
    return "single"


def stocked(params: LayoutParams) -> bool:
    """Stock groups are a showcase option (`layout.stock`)."""
    return params.mode == "showcase" and params.stock


def _row_centres(w: int) -> tuple[list[float], list[float]]:
    """Centres (px from the group's left edge) of the front and the back bottles of a `w` px wide unit."""
    step = w * STOCK_ROW_SPACING
    # Half a bottle's stagger: with one row longer, the shorter one sits in its gaps; with equal rows, shifted right.
    shift = (STOCK_ROW_FRONT - STOCK_ROW_BACK) / 2 if STOCK_ROW_FRONT != STOCK_ROW_BACK else 0.5
    front = [i * step for i in range(STOCK_ROW_FRONT)]
    back = [(j + shift) * step for j in range(STOCK_ROW_BACK)]
    bw = w * STOCK_ROW_BACK_SCALE
    left = min([c - w / 2 for c in front] + [c - bw / 2 for c in back])
    return [c - left for c in front], [c - left for c in back]


def _row_size(w: int, h: int) -> tuple[int, int]:
    front, back = _row_centres(w)
    bw = w * STOCK_ROW_BACK_SCALE
    return math.ceil(max([c + w / 2 for c in front] + [c + bw / 2 for c in back])), h


def _pair_size(w: int, h: int) -> tuple[int, int]:
    return w + round(w * STOCK_BACK_SCALE * STOCK_PAIR_SHOWN), h


def _pyramid_size(w: int, h: int) -> tuple[int, int]:
    gap = round(w * STOCK_PYRAMID_GAP)
    return 2 * w + gap, 2 * h


def stock_size(size: tuple[int, int], params: LayoutParams) -> tuple[int, int]:
    """The size `stock_group` gives a picture of `size`, without drawing it (for upload checks)."""
    if not stocked(params):
        return size
    kind = stock_kind(size)
    if kind == "row":
        return _row_size(*size)
    if kind == "pyramid":
        return _pyramid_size(*size)
    if kind == "pair":
        return _pair_size(*size)
    return size


def _shaded(unit: Image.Image, factor: float) -> Image.Image:
    alpha = unit.getchannel("A")
    out = ImageEnhance.Brightness(unit.convert("RGB")).enhance(factor).convert("RGBA")
    out.putalpha(alpha)
    return out


def stock_group(unit: Image.Image) -> Image.Image:
    """`unit` (RGBA, cropped to its alpha) as a stock group, or `unit` itself when its shape is not stocked.

    The group is exactly as tall as the stack it shows, so the layout's real-size rule (ADR-082) still sizes one unit:
    a row and a pair are one unit tall, a pyramid two cans tall.
    """
    w, h = unit.size
    kind = stock_kind(unit.size)
    if kind == "row":
        width, _ = _row_size(w, h)
        bw, bh = round(w * STOCK_ROW_BACK_SCALE), round(h * STOCK_ROW_BACK_SCALE)
        back = _shaded(unit.resize((bw, bh), Image.Resampling.LANCZOS), STOCK_BACK_SHADE)
        out = Image.new("RGBA", (width, h), (0, 0, 0, 0))
        front_c, back_c = _row_centres(w)
        for c in back_c:
            out.alpha_composite(back, (min(width - bw, max(0, round(c - bw / 2))), 0))
        for c in front_c:
            out.alpha_composite(unit, (min(width - w, max(0, round(c - w / 2))), 0))
        return out
    if kind == "pyramid":
        width, height = _pyramid_size(w, h)
        out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        out.alpha_composite(_shaded(unit, STOCK_TOP_SHADE), ((width - w) // 2, 0))
        out.alpha_composite(unit, (0, h))
        out.alpha_composite(unit, (width - w, h))
        return out
    if kind == "pair":
        width, _ = _pair_size(w, h)
        bw, bh = round(w * STOCK_BACK_SCALE), round(h * STOCK_BACK_SCALE)
        back = _shaded(unit.resize((bw, bh), Image.Resampling.LANCZOS), STOCK_BACK_SHADE)
        out = Image.new("RGBA", (width, h), (0, 0, 0, 0))
        out.alpha_composite(back, (width - bw, h - round(h * STOCK_BACK_LIFT) - bh))
        out.alpha_composite(unit, (0, 0))
        return out
    return unit


def with_stock(art: Mapping[str, ProductArt], params: LayoutParams) -> dict[str, ProductArt]:
    """`art` with each product's stock group set when `params` stocks, else cleared (FR-030).

    Only a cut-out stacks: a picture that still has its background, or a placeholder, stays one unit.
    """
    out: dict[str, ProductArt] = {}
    for pid, item in art.items():
        group: Image.Image | None = None
        if stocked(params) and not item.opaque and not item.placeholder:
            built = stock_group(item.image)
            if built is not item.image:
                group = built
                if max(group.size) > ART_MAX_SIDE:
                    scale = ART_MAX_SIDE / max(group.size)
                    group = group.resize(
                        (max(1, round(group.width * scale)), max(1, round(group.height * scale))),
                        Image.Resampling.LANCZOS,
                    )
        out[pid] = item if item.stock is group else dataclasses.replace(item, stock=group)
    return out
