"""The backdrop plate behind the host (014 contracts/adapters.md §2, research R10, R11, R15; FR-006, FR-007, FR-009).

`anh_shop` (ADR-100) is the scene's confirmed shop photo, cover-cropped to the frame, softened and light-matched.
The rest of this docstring is about `ke_hang`.

One flat RGB plate of the fork frame size: a shop aisle seen from its middle (ADR-086). Two side shelves run inward
toward a vanishing point at the host's eye level and meet a smaller, darker back shelf; every tier is stocked edge to
edge with units of the shop's own cut-out products, under a warm LED strip on each board. No text, price or logo is
drawn. The plate is then softened and matched to the light of the room the host was filmed in with a tone curve, so
it keeps its contrast and colour instead of washing out to a pale wall. Pure CPU work: callers run it in a thread
(`asyncio.to_thread`).
"""

from __future__ import annotations

import io
import math
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import cycle, islice
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from ai_live.scene.models import BackgroundConfig, Box
from ai_live.scene.shop_photo import AI_MIN_SOFTNESS_PX, ShopPhoto

# Warm, bright shop colours (R10). None of them is green-dominant: a green pixel on the plate is a stray picture.
CEILING = (240, 236, 228)
CEILING_LIGHT = (255, 250, 238)
PANEL = (206, 198, 186)  # shelf back panels: light for a bright shop, dark enough for the goods to stand out
BOARD = (244, 240, 232)  # white metal shelving
POST = (176, 170, 162)
LED = (255, 222, 168)
FLOOR = (168, 150, 126)

TIERS = 6
# The aisle (ADR-086): lines through the vanishing point at the host's eye level. A side shelf's outer edge is the
# frame edge; its tiers shrink to BACK_SCALE where it meets the back shelf, which is that much narrower and shorter.
VANISH_Y = 0.32  # frame-height fraction
OUTER_TOP = -0.02  # frame-height fraction: the side shelves rise past the top of the frame
BACK_SCALE = 0.55
BACK_SHADE = 0.72  # light at the back shelf relative to the front of the side shelves
BOARD_PX = 7  # board thickness at the frame edge, on an 832 px frame
POST_PX = 8  # upright width at the frame edge, on an 832 px frame
SIDE_POSTS = (0.8,)  # depth scales of the inner uprights on each side shelf
# A shelf product is far smaller than a 013 desk product (~20-30% of the frame height): the shelf is behind the host.
ITEM_TIER_FILL = 0.62  # item height / tier height
ITEM_MAX_ASPECT = 1.2  # item width / height at most, so one wide pack cannot fill a tier alone
ITEM_GAP = 0.08  # gap between units, relative to the item height
SIDE_SQUEEZE = 0.78  # units on a side shelf face the aisle: seen at an angle, they look narrower
ITEM_HAZE = 0.06  # a little of the panel colour over the far goods
LED_GLOW = 0.35  # frame-height fraction of a tier lit by the strip above, at the frame edge (x tier height)
SHELF_SHADOW = 0.85  # contact shadow under each unit
WHITE_BALANCE_CAP = 12.0  # R11: the realism skill's light-colour limit
TONE_STEPS = 40  # bisection steps for the tone curve that lands the mean luma on the target
# Plaster and metal grain: a real shelf is never flat. The seed is fixed so the same set always gives the same plate
# (the plate sent after a fork restart must be byte-identical).
TEXTURE_SIGMA = 1.5
TEXTURE_SEED = 14

STYLE_REASONS = {"goc": "style_goc", "bang_shop": "style_not_available"}


@dataclass(frozen=True)
class LightStats:
    """The `light` block of the character's background manifest (data-model §3): the old room the host was lit for."""

    person_luma: float
    person_rb: float
    room_luma: float
    room_rb: float

    @classmethod
    def from_manifest(cls, block: Mapping[str, Any] | None) -> LightStats | None:
        """The stats, or None when the block is missing or any value is not a number."""
        if not isinstance(block, Mapping):
            return None
        values: dict[str, float] = {}
        for name in ("person_luma", "person_rb", "room_luma", "room_rb"):
            value = block.get(name)
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
                return None
            values[name] = float(value)
        return cls(**values)


@dataclass(frozen=True)
class BackdropResult:
    """The drawn plate (PNG bytes, RGB, frame size) and the products on its shelves, or the reason nothing was drawn."""

    png: bytes | None
    items: tuple[str, ...]
    reason: str | None


def render_backdrop(
    config: BackgroundConfig,
    art: Mapping[str, Image.Image],
    size: tuple[int, int],
    desk_top_px: int,
    light: LightStats | None,
    photo: ShopPhoto | None = None,
) -> BackdropResult:
    """Draw the plate for `config.style` from the loaded products' active images (`art`: product id -> RGBA cut-out)
    or, for `anh_shop`, from the scene's shop photo."""
    if config.style in STYLE_REASONS:
        return BackdropResult(None, (), STYLE_REASONS[config.style])
    if config.style == "anh_shop":
        return _shop_photo_plate(config, photo, size, desk_top_px, light)
    if not art:
        return BackdropResult(None, (), "no_product_art")
    width, height = size
    desk_top = max(1, min(int(desk_top_px), height))
    # The rotation of products the shelves repeat: a one-product shop repeats that product (R10 edge case), and a set
    # never shows anything outside `art`. Many units of the same products fill the shelves (FR-007, FR-018).
    items = tuple(islice(cycle(art), max(1, config.max_items)))

    aisle = shelf_geometry(width, height, desk_top)
    plate = _room(aisle)
    _stock_shelves(plate, aisle, art, items)
    _posts(plate, aisle)
    plate *= _depth_shade(aisle)[None, :, None]
    grain = np.random.default_rng(TEXTURE_SEED).normal(0.0, TEXTURE_SIGMA, (desk_top, width, 1)).astype(np.float32)
    plate[:desk_top] += grain
    image = Image.fromarray(np.clip(np.rint(plate), 0, 255).astype(np.uint8), "RGB")
    if config.softness_px > 0:
        image = image.filter(ImageFilter.GaussianBlur(radius=config.softness_px))
    rgb = _match_light(np.asarray(image).astype(np.float32), desk_top, config.brightness, light)

    buffer = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buffer, format="PNG", optimize=False)
    return BackdropResult(buffer.getvalue(), items, None)


def _shop_photo_plate(
    config: BackgroundConfig, photo: ShopPhoto | None, size: tuple[int, int], desk_top_px: int, light: LightStats | None
) -> BackdropResult:
    """FR-009: cover the frame without stretching; FR-009a: an AI-made picture is never sharper than the minimum, except
    for `as_is` (ADR-102), where the cover-cropped photo goes out untouched."""
    if photo is None:
        return BackdropResult(None, (), "no_shop_photo")
    if photo.image is None:
        return BackdropResult(None, (), photo.reason or "no_shop_photo")
    width, height = size
    desk_top = max(1, min(int(desk_top_px), height))
    scale = max(width / photo.image.width, height / photo.image.height)
    scaled = (max(width, round(photo.image.width * scale)), max(height, round(photo.image.height * scale)))
    left, top = (scaled[0] - width) // 2, (scaled[1] - height) // 2
    image = photo.image.convert("RGB").resize(scaled, Image.Resampling.LANCZOS)
    image = image.crop((left, top, left + width, top + height))
    if config.as_is:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=False)
        return BackdropResult(buffer.getvalue(), (), None)
    softness = config.softness_px
    if photo.source == "ai_generated":
        softness = max(softness, AI_MIN_SOFTNESS_PX)
    if softness > 0:
        image = image.filter(ImageFilter.GaussianBlur(radius=softness))
    rgb = _match_light(np.asarray(image).astype(np.float32), desk_top, config.brightness, light)
    buffer = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buffer, format="PNG", optimize=False)
    return BackdropResult(buffer.getvalue(), (), None)


# ---------- the aisle (ADR-086) ----------


@dataclass(frozen=True)
class Aisle:
    """The shelf lines in frame pixels: each board line at the frame edge and where it meets the back shelf."""

    width: int
    height: int
    vanish: tuple[float, float]
    outer_lines: tuple[float, ...]  # TIERS + 1 board lines at the frame edge, top to bottom
    inner_lines: tuple[float, ...]  # the same lines across the back shelf
    back: Box  # the back shelf, from its top board line to its bottom one

    def scale(self) -> np.ndarray:
        """Depth scale of each column: 1 at the frame edges, BACK_SCALE across the back shelf."""
        vx = self.vanish[0]
        x = np.arange(self.width, dtype=np.float32) + 0.5
        return np.clip(np.abs(x - vx) / vx, BACK_SCALE, 1.0)

    def lines(self) -> np.ndarray:
        """(TIERS + 1, width): the y of each board line in every column."""
        vy = self.vanish[1]
        outer = np.asarray(self.outer_lines, np.float32)[:, None]
        return vy + (outer - vy) * self.scale()[None, :]


def shelf_geometry(width: int, height: int, desk_top: int) -> Aisle:
    """The aisle for a frame: the lowest board on the desk edge at the frame edge, the vanishing point at eye level."""
    vx, vy = width / 2, VANISH_Y * height
    outer = tuple(float(y) for y in np.linspace(OUTER_TOP * height, desk_top, TIERS + 1))
    inner = tuple(vy + (y - vy) * BACK_SCALE for y in outer)
    bx1 = round(vx * (1.0 - BACK_SCALE))
    return Aisle(width, height, (vx, vy), outer, inner, (bx1, round(inner[0]), width - bx1, round(inner[-1])))


def _unit(height: int) -> float:
    """Pixel sizes are tuned on an 832 px frame and scale with the frame height."""
    return height / 832


def _room(aisle: Aisle) -> np.ndarray:
    """Ceiling, floor, the shelves' back panels lit by the strip above, boards with an LED strip on the front edge."""
    width, height = aisle.width, aisle.height
    unit = _unit(height)
    lines, scale = aisle.lines(), aisle.scale()
    rows = np.arange(height, dtype=np.float32)[:, None]
    board = BOARD_PX * unit * scale
    led_px = np.maximum(1.0, 2.0 * unit * scale)
    plate = np.empty((height, width, 3), np.float32)
    plate[:] = CEILING
    # A ceiling light down the middle of the aisle, between the tops of the side shelves.
    middle = np.abs(np.arange(width) + 0.5 - width / 2) < 0.2 * width
    plate[(rows > 0.3 * lines[0]) & (rows < 0.65 * lines[0]) & middle[None, :]] = CEILING_LIGHT
    plate[rows >= lines[-1]] = FLOOR
    plate[(rows >= lines[0] - board) & (rows < lines[0])] = BOARD  # the top cap
    led = np.asarray(LED, np.float32)
    for k in range(TIERS):
        top, bottom = lines[k], lines[k + 1] - board
        tier = (rows >= top) & (rows < bottom)
        plate[tier] = PANEL
        # Warm LED glow from the strip under the board above, fading down the tier.
        reach = np.maximum(LED_GLOW * (lines[k + 1] - lines[k]), 1.0)
        glow = np.clip(1.0 - (rows - top) / reach, 0.0, 1.0) * tier
        plate += (led - plate) * (0.35 * glow)[..., None]
        plate[(rows >= bottom) & (rows < lines[k + 1])] = BOARD
        plate[(rows >= lines[k + 1] - led_px) & (rows < lines[k + 1])] = LED
    return plate


def _stock_shelves(plate: np.ndarray, aisle: Aisle, art: Mapping[str, Image.Image], items: tuple[str, ...]) -> None:
    """Fill every tier edge to edge with units of `items` in turn: left side, back shelf, right side, top to bottom."""
    width, height = aisle.width, aisle.height
    unit = _unit(height)
    lines, scale = aisle.lines(), aisle.scale()
    board = BOARD_PX * unit * scale
    bx1, _, bx2, _ = aisle.back
    tallest = max(4, math.ceil(ITEM_TIER_FILL * (aisle.outer_lines[1] - aisle.outer_lines[0])))
    # Shrink each picture once to the largest size a unit can have; every unit is resized from that.
    small = {pid: _fit(art[pid], tallest, round(ITEM_MAX_ASPECT * tallest)) for pid in dict.fromkeys(items)}
    cache: dict[tuple[str, int, bool], np.ndarray] = {}

    def cutout(product_id: str, s: float, tier_h: float, side: bool) -> np.ndarray:
        item_h = max(4, round(ITEM_TIER_FILL * tier_h * s))
        key = (product_id, item_h, side)
        if key not in cache:
            fitted = _fit(small[product_id], item_h, max(4, round(ITEM_MAX_ASPECT * item_h)))
            if side:
                squeezed = (max(2, round(fitted.width * SIDE_SQUEEZE)), fitted.height)
                fitted = fitted.resize(squeezed, Image.Resampling.LANCZOS)
            cache[key] = np.asarray(fitted).astype(np.float32)
        return cache[key]

    units = cycle(items)
    for k in range(TIERS):
        tier_h = aisle.outer_lines[k + 1] - aisle.outer_lines[k]
        foot = lines[k + 1] - board  # where a unit stands in each column

        def stand(rgba: np.ndarray, left: int, foot: np.ndarray = foot) -> None:
            centre = min(width - 1, max(0, left + rgba.shape[1] // 2))
            _place(plate, rgba, left, round(foot[centre]), float(scale[centre]), unit)

        # Back shelf first, left to right, all at one depth: the side shelves stand in front of its ends.
        x = bx1 + ITEM_GAP * ITEM_TIER_FILL * tier_h * BACK_SCALE
        while True:
            rgba = cutout(next(units), BACK_SCALE, tier_h, False)
            if x + rgba.shape[1] > bx2:
                break
            stand(rgba, round(x))
            x += rgba.shape[1] + ITEM_GAP * rgba.shape[0]
        # Side shelves from the frame edge inward; the last unit may run past the corner, over the back shelf's end,
        # so no strip of bare panel is left where the two meet.
        x = 0.0
        while x < bx1:
            rgba = cutout(next(units), float(scale[min(width - 1, int(x))]), tier_h, True)
            stand(rgba, round(x))
            x += rgba.shape[1] + ITEM_GAP * rgba.shape[0]
        x = float(width)
        while x > bx2:
            rgba = cutout(next(units), float(scale[max(0, min(width - 1, int(x) - 1))]), tier_h, True)
            stand(rgba, round(x) - rgba.shape[1])
            x -= rgba.shape[1] + ITEM_GAP * rgba.shape[0]


def _place(plate: np.ndarray, rgba: np.ndarray, left: int, bottom: int, s: float, unit: float) -> None:
    """Stand one unit on a board (its foot at `bottom`), with a little haze and a contact shadow."""
    height, width = plate.shape[:2]
    h, w = rgba.shape[:2]
    top = bottom - h
    x1, y1, x2, y2 = max(0, left), max(0, top), min(width, left + w), min(height, bottom)
    if x1 >= x2 or y1 >= y2:
        return
    part = rgba[y1 - top : y2 - top, x1 - left : x2 - left]
    alpha = part[..., 3:4] / 255.0
    rgb = part[..., :3] * (1.0 - ITEM_HAZE) + np.asarray(PANEL, np.float32) * ITEM_HAZE
    region = plate[y1:y2, x1:x2]
    region[:] = region * (1.0 - alpha) + rgb * alpha
    shadow = max(1, round(2 * unit * s))
    plate[y2 : min(height, y2 + shadow), x1:x2] *= SHELF_SHADOW


def _posts(plate: np.ndarray, aisle: Aisle) -> None:
    """Uprights at the front of each side shelf section and at the corners where the side shelves meet the back."""
    width, height = aisle.width, aisle.height
    lines = aisle.lines()
    vx = aisle.vanish[0]
    for s in (*SIDE_POSTS, BACK_SCALE):
        half = max(1, round(POST_PX * _unit(height) * s / 2))
        for centre in (round(vx * (1.0 - s)), width - round(vx * (1.0 - s))):
            column = min(width - 1, max(0, centre))
            top, bottom = max(0, round(lines[0][column])), min(height, round(lines[-1][column]))
            plate[top:bottom, max(0, centre - half) : min(width, centre + half)] = POST


def _depth_shade(aisle: Aisle) -> np.ndarray:
    """Light falls off down the aisle: full at the frame edges, BACK_SHADE across the back shelf."""
    depth = (aisle.scale() - BACK_SCALE) / (1.0 - BACK_SCALE)
    return BACK_SHADE + (1.0 - BACK_SHADE) * depth


def _fit(image: Image.Image, max_h: int, max_w: int) -> Image.Image:
    rgba = image.convert("RGBA")
    scale = min(max_h / rgba.height, max_w / rgba.width)
    size = (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale)))
    return rgba.resize(size, Image.Resampling.LANCZOS)


# ---------- light match (R11) ----------


def _luma(rgb: np.ndarray) -> float:
    return float((0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).mean())


def _tone(rgb: np.ndarray, desk_top: int, target: float) -> np.ndarray:
    """A gamma curve that lands the mean luma above the desk on `target` (FR-018).

    Black and white stay where they are, so a bright room lifts the midtones without clipping the plate into a pale
    wash, as the old linear gain did; the order of all tones, and so the contrast between goods and shelves, is kept.
    """
    norm = np.clip(rgb / 255.0, 0.0, 1.0)
    sample = norm[:desk_top:2, ::2]
    goal = min(254.0, max(1.0, target)) / 255.0
    low, high = 0.1, 10.0  # the mean falls as the gamma grows
    for _ in range(TONE_STEPS):
        gamma = math.sqrt(low * high)
        if _luma(sample**gamma) > goal:
            low = gamma
        else:
            high = gamma
    return 255.0 * norm ** math.sqrt(low * high)


def _match_light(rgb: np.ndarray, desk_top: int, brightness: float, light: LightStats | None) -> np.ndarray:
    """Mean luma above the desk to the old room's × brightness; R−B toward the old room's, at most ±12."""
    target = (light.room_luma if light is not None else _luma(rgb[:desk_top])) * brightness
    rgb = _tone(rgb, desk_top, target)
    if light is not None:
        current_rb = float(rgb[:desk_top, :, 0].mean() - rgb[:desk_top, :, 2].mean())
        shift = max(-WHITE_BALANCE_CAP, min(WHITE_BALANCE_CAP, light.room_rb - current_rb))
        # Red up and blue down by half the shift each; green moves to keep the luma where it was.
        rgb = rgb + np.asarray([shift / 2, -(0.299 - 0.114) * (shift / 2) / 0.587, -shift / 2], np.float32)
        rgb = np.clip(rgb, 0.0, 255.0)
    return np.rint(rgb).astype(np.uint8)
