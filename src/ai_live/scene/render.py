"""Drawing the scene (research R5): one RGBA layer for the desk, products and cards, one for the subtitle.

The layers are what the fork blends over each lip-synced frame, and what the app blends over the still image. They are
transparent wherever the face, the "AI" label or the watermark is (FR-019, FR-020): the fork checks the same boxes and
refuses a layer that touches them.
"""

from __future__ import annotations

import dataclasses
import io
import logging
from collections.abc import Iterable, Mapping

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from ai_live.products.models import Product
from ai_live.scene.fonts import SceneFonts
from ai_live.scene.layout import (
    CARD_PAD_PX,
    CONTACT_SHADOW_ALPHA,
    CONTACT_SHADOW_BLUR_PX,
    CONTACT_SHADOW_PX,
    HIGHLIGHT_ALPHA,
    HIGHLIGHT_BLUR_PX,
    HIGHLIGHT_COLOR,
    LINE_GAP_PX,
    PRICE_RANGE_SEP,
    REALISTIC_DIM,
    SHOWCASE_HIGHLIGHT_ALPHA,
    SOFT_SHADOW_ALPHA,
    SOFT_SHADOW_BLUR_PX,
    SOFT_SHADOW_HEIGHT,
    SOFT_SHADOW_WIDTH,
    card_height,
    card_text,
    line_height,
    riser_shape,
    riser_top_height,
    scaled,
    wrap_text,
)
from ai_live.scene.models import (
    Box,
    CardText,
    FrameGeometry,
    PriceTag,
    PromoBanner,
    SceneLayer,
    SceneLayout,
    SceneSet,
    Sticker,
)

CARD_FILL = (255, 255, 255, 235)
CARD_RADIUS_PX = 10
CARD_BORDER_PX = 3
NAME_COLOR = (34, 34, 34, 255)
SHADOW_ALPHA = 110
GLOW_ALPHA = 200
GLOW_BLUR_PX = 9
DIM_BRIGHTNESS = 0.85  # the others step back a little while one product is spoken about (FR-015)
SUBTITLE_FILL = (0, 0, 0, 150)
SUBTITLE_SIZE = 20
SUBTITLE_MIN_SIZE = 15
SUBTITLE_PAD_PX = 10
DEBUG_COLORS = {
    "face": (255, 0, 0, 255),
    "keep_out": (255, 200, 0, 255),
    "subtitle": (0, 200, 255, 255),
    "desk": (0, 200, 0, 255),
    "hands": (170, 0, 255, 255),
}
DEBUG_STEP_PX = 10
# 013 shadow (2026-11-23 review): the shadow follows the product's own foot line, so a box photographed at an angle
# touches the desk along its slanted bottom edge instead of hanging over a level ellipse. Most of each band lies behind
# the foot (the product covers it); only a short strip shows in front, since a wide strip there reads as floating.
FOOT_ALPHA = 128  # a column's foot is its lowest pixel at least this opaque (glass bottoms are see-through)
CONTACT_HALF_WIDTH = 0.55  # x the product width, from its middle: the contact runs just past both edges
CONTACT_BEHIND, CONTACT_FRONT = 0.5, 0.5  # x the contact height, above / below the foot line
SOFT_BEHIND, SOFT_FRONT = 0.5, 0.3  # x the soft height
SHADOW_END_POWER = 6  # band ends round off near the half width, flat across the middle
# A cut-out's see-through edge keeps some of the old background (white on a studio photo). Over the dark shadow that
# edge shows as a light line between product and desk, so it takes the colour of the solid pixels next to it.
EDGE_SOLID_ALPHA = 200
EDGE_REACH_PX = 4
# 013 FR-029 (ADR-082): a product photo is far crisper than the soft camera image of the host, so it looks pasted on.
# Blur and edge feather in px on an 832 px frame.
CAMERA_BLUR_PX = 0.7
CAMERA_FEATHER_PX = 0.8
DEBUG_DASH_PX = 5
# 013 showcase (ADR-079): a white round riser under the main product and a round price sticker on it.
RISER_TOP_COLOR = (250, 250, 248, 255)
RISER_SIDE_COLOR = (226, 226, 222, 255)
RISER_EDGE_COLOR = (205, 205, 200, 255)
RISER_SHADOW_ALPHA = 120
RISER_SHADOW_BLUR_PX = 5
RISER_SUPERSAMPLE = 4
logger = logging.getLogger("ai_live.scene")

STICKER_SIZE = 20
STICKER_MIN_SIZE = 11
STICKER_TEXT_WIDTH = 0.78  # x the diameter: a line wider than this touches the round edge
STICKER_RING_PX = 3
# 013 FR-031, FR-032 (ADR-095): price tags at the products' feet and the promotions strip of a "hot live" desk.
PRICE_TAG_MIN_SIZE = 10
PROMO_TITLE = "KHUYẾN MÃI"
PROMO_FILL = (255, 214, 64, 238)  # shop-sale yellow, nearly opaque so the room behind does not show through
PROMO_TEXT = (122, 16, 16, 255)
PROMO_SIZE = 14
PROMO_MIN_SIZE = 10
PROMO_PAD_PX = 6
PROMO_RADIUS_PX = 8


def encode_png(image: Image.Image) -> bytes:
    """Fast PNG: the layer is re-sent on every highlight change, a smaller file is not worth 100 ms."""
    out = io.BytesIO()
    image.save(out, "PNG", compress_level=1)
    return out.getvalue()


def cover_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale to cover `width`×`height` and crop the middle, as the host page's `object-fit: cover` does."""
    scale = max(width / image.width, height / image.height)
    size = (max(width, round(image.width * scale)), max(height, round(image.height * scale)))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    left, top = (size[0] - width) // 2, (size[1] - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(c * factor))) for c in color)  # type: ignore[return-value]


def _draw_desk(layer: Image.Image, scene: SceneSet, box: Box) -> None:
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    if height <= 0:
        return
    if scene.desk is not None:
        desk = scene.desk.convert("RGBA")
        scale = width / desk.width
        desk = desk.resize((width, max(height, round(desk.height * scale))), Image.Resampling.LANCZOS)
        layer.alpha_composite(desk.crop((0, 0, width, height)), (x1, y1))
        return
    # A plain desk: lighter where the light falls (the front edge), darker towards the viewer.
    draw = ImageDraw.Draw(layer)
    top, bottom = _shade(scene.desk_color, 1.12), _shade(scene.desk_color, 0.72)
    for row in range(height):
        t = row / max(1, height - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        draw.line([(x1, y1 + row), (x2 - 1, y1 + row)], fill=(*color, 255))
    draw.rectangle([x1, y1, x2 - 1, y1 + 2], fill=(*_shade(scene.desk_color, 1.45), 255))
    draw.line([(x1, y1 + 3), (x2 - 1, y1 + 3)], fill=(*_shade(scene.desk_color, 0.6), 255))


def _paste(layer: Image.Image, image: Image.Image, x: int, y: int) -> None:
    """`alpha_composite` that accepts a place partly outside the layer (a glow near the frame edge)."""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(image.width, layer.width - x), min(image.height, layer.height - y)
    if left < right and top < bottom:
        layer.alpha_composite(image.crop((left, top, right, bottom)), (x + left, y + top))


def _blurred(mask: Image.Image, radius: int, color: tuple[int, int, int], alpha: int) -> Image.Image:
    soft = mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: v * alpha // 255)
    out = Image.new("RGBA", mask.size, (*color, 0))
    out.putalpha(soft)
    return out


def _draw_product(
    layer: Image.Image,
    art: Image.Image,
    box: Box,
    *,
    highlighted: bool,
    dimmed: bool,
    accent: tuple[int, int, int],
    brightness: float = 1.0,
    geometry: FrameGeometry | None = None,
    shadow_box: Box | None = None,
    dim: float = DIM_BRIGHTNESS,
    light_alpha: int = HIGHLIGHT_ALPHA,
) -> None:
    """One product and its shadow. With `shadow_box` (013 realistic) the shadow is two layers clipped to that box,
    and the highlight is a warm light behind the product instead of the accent glow (research R3)."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return
    pic = art.resize((w, h), Image.Resampling.LANCZOS)
    if shadow_box is not None:
        pic = defringe(pic)
        if geometry is not None:
            k = geometry.height / 832
            pic = camera_soften(pic, CAMERA_BLUR_PX * k, CAMERA_FEATHER_PX * k)
    # 013 FR-006: the operator's brightness first, so a dimmed product steps back from the matched level.
    factor = brightness * (dim if dimmed else 1.0)
    if factor != 1.0:
        alpha = pic.getchannel("A")
        pic = ImageEnhance.Brightness(pic.convert("RGB")).enhance(factor).convert("RGBA")
        pic.putalpha(alpha)
    if shadow_box is not None and geometry is not None:
        if highlighted:
            _draw_warm_light(layer, geometry, box, pic, light_alpha)
        _draw_realistic_shadow(layer, geometry, box, shadow_box, pic.getchannel("A"))
    else:
        # Contact shadow: a product without one floats above the desk.
        pad = 12
        shadow_mask = Image.new("L", (w + 2 * pad, 2 * pad + 8), 0)
        ImageDraw.Draw(shadow_mask).ellipse([pad, pad, pad + w - 1, pad + 7], fill=255)
        _paste(layer, _blurred(shadow_mask, 5, (0, 0, 0), SHADOW_ALPHA), x1 - pad, y2 - pad - 4)
    if highlighted and shadow_box is None:
        glow_mask = Image.new("L", (w + 4 * GLOW_BLUR_PX, h + 4 * GLOW_BLUR_PX), 0)
        glow_mask.paste(pic.getchannel("A"), (2 * GLOW_BLUR_PX, 2 * GLOW_BLUR_PX))
        glow_mask = glow_mask.filter(ImageFilter.MaxFilter(5))
        glow = _blurred(glow_mask, GLOW_BLUR_PX, accent, GLOW_ALPHA)
        _paste(layer, glow, x1 - 2 * GLOW_BLUR_PX, y1 - 2 * GLOW_BLUR_PX)
    layer.alpha_composite(pic, (x1, y1))


def _draw_warm_light(
    layer: Image.Image, geometry: FrameGeometry, box: Box, pic: Image.Image, alpha: int = HIGHLIGHT_ALPHA
) -> None:
    """A soft warm light behind the spoken product (013 research R3), kept out of the hands zone.

    `layout.glow_box` is exactly the area this covers; the layout keeps it clear of the face and the labels, and the
    hands are cut out here because a light on the fingers would show where the overlay ends.
    """
    x1, y1, x2, y2 = box
    reach = 2 * scaled(geometry, HIGHLIGHT_BLUR_PX)
    mask = Image.new("L", (x2 - x1 + 2 * reach, y2 - y1 + 2 * reach), 0)
    mask.paste(pic.getchannel("A"), (reach, reach))
    mask = mask.filter(ImageFilter.MaxFilter(5))
    light = _blurred(mask, scaled(geometry, HIGHLIGHT_BLUR_PX), HIGHLIGHT_COLOR, alpha)
    if geometry.hands_zone is not None:
        hx1, hy1, hx2, hy2 = geometry.hands_zone
        ox, oy = x1 - reach, y1 - reach
        ImageDraw.Draw(light).rectangle([hx1 - ox, hy1 - oy, hx2 - ox - 1, hy2 - oy - 1], fill=(*HIGHLIGHT_COLOR, 0))
    _paste(layer, light, x1 - reach, y1 - reach)


def _premultiplied_blur(rgb: np.ndarray, alpha: np.ndarray, radius: float) -> tuple[np.ndarray, np.ndarray]:
    """Blurred colour x alpha and blurred alpha; their ratio blurs colour without the see-through pixels."""
    blur = ImageFilter.GaussianBlur(radius)
    pm = Image.fromarray(np.clip(rgb * alpha[..., None], 0, 255).astype(np.uint8), "RGB").filter(blur)
    a = Image.fromarray(np.clip(alpha * 255, 0, 255).astype(np.uint8), "L").filter(blur)
    return np.asarray(pm, np.float32), np.asarray(a, np.float32)[..., None] / 255


def camera_soften(pic: Image.Image, blur_px: float, feather_px: float) -> Image.Image:
    """`pic` blurred by `blur_px` and its alpha edge feathered by `feather_px`, to match the camera (013 FR-029).

    The colour blur is premultiplied by alpha, so the transparent black around a cut-out never darkens its edge. The
    feather only fades inward (the lower of the alpha and its blur): the outline never grows, so the foot stays on
    its contact shadow and nothing spills past the box the layout kept clear.
    """
    if blur_px <= 0 and feather_px <= 0:
        return pic
    rgba = np.asarray(pic.convert("RGBA"), np.float32)
    rgb, alpha = rgba[..., :3], rgba[..., 3] / 255
    out = rgb
    if blur_px > 0:
        floor = 1 / 255
        pm, a = _premultiplied_blur(rgb, alpha, blur_px)
        out = np.where(a > floor, pm / np.maximum(a, floor), rgb)
    alpha_img = pic.getchannel("A")
    if feather_px > 0:
        alpha_img = ImageChops.darker(alpha_img, alpha_img.filter(ImageFilter.GaussianBlur(feather_px)))
    result = Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGB")
    result.putalpha(alpha_img)
    return result


def defringe(pic: Image.Image) -> Image.Image:
    """`pic` with each see-through edge pixel recoloured from the solid pixels around it; alpha is unchanged."""
    rgba = np.asarray(pic.convert("RGBA"))
    alpha = rgba[..., 3]
    edge = (alpha > 0) & (alpha < EDGE_SOLID_ALPHA)
    known = alpha >= EDGE_SOLID_ALPHA
    if not edge.any() or not known.any():
        return pic
    color = np.where(known[..., None], rgba[..., :3], 0).astype(np.float32)
    weight = known.astype(np.float32)
    for _ in range(EDGE_REACH_PX):
        if not (edge & ~known).any():
            break
        cp = np.pad(color, ((1, 1), (1, 1), (0, 0)))
        wp = np.pad(weight, 1)
        sums = cp[:-2, 1:-1] + cp[2:, 1:-1] + cp[1:-1, :-2] + cp[1:-1, 2:]
        counts = wp[:-2, 1:-1] + wp[2:, 1:-1] + wp[1:-1, :-2] + wp[1:-1, 2:]
        grow = ~known & (counts > 0)
        color[grow] = sums[grow] / counts[grow][:, None]
        weight[grow] = 1.0
        known = known | grow
    out = rgba.copy()
    fix = edge & known
    out[..., :3][fix] = np.clip(color[fix], 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def foot_line(alpha: Image.Image) -> np.ndarray:
    """The lowest opaque row of each column of a product picture, -1 where a column has none."""
    solid = np.asarray(alpha) >= FOOT_ALPHA
    lowest = solid.shape[0] - 1 - np.argmax(solid[::-1], axis=0)
    return np.where(solid.any(axis=0), lowest, -1)


def _draw_realistic_shadow(
    layer: Image.Image, geometry: FrameGeometry, art_box: Box, shadow_box: Box, alpha: Image.Image
) -> None:
    """A wide faint shadow under a tight dark one along the product's foot line, clipped to `shadow_box` (research R3).

    The soft layer is the room light falling on the desk; the contact layer seats the product on it. Both stay inside
    `layout.shadow_ellipses`, which is what the layout keeps clear of the face, the labels and the hands.
    """
    x1, y1, x2, y2 = art_box
    sx1, sy1, sx2, sy2 = shadow_box
    w, h = x2 - x1, y2 - y1
    if sx2 <= sx1 or sy2 <= sy1 or w <= 0 or h <= 0:
        return
    foot = foot_line(alpha)
    solid = np.flatnonzero(foot >= 0)
    if solid.size == 0:
        return
    # Columns past the picture take the foot of its nearest solid column, so the soft layer spreads level beside it.
    cols = np.arange(sx1, sx2) - x1
    nearest = np.clip(cols, solid[0], solid[-1])
    inside = (cols >= 0) & (cols < w) & (foot[np.clip(cols, 0, w - 1)] >= 0)
    nearest = np.where(inside, cols, nearest)
    feet = foot[nearest] + y1
    rows = np.arange(sy1, sy2)[:, None]
    middle = (x1 + x2) / 2
    contact_h = scaled(geometry, CONTACT_SHADOW_PX)
    soft_h = max(contact_h, SOFT_SHADOW_HEIGHT * h)
    for half, height, behind, front, blur, strength in (
        (SOFT_SHADOW_WIDTH / 2, soft_h, SOFT_BEHIND, SOFT_FRONT, SOFT_SHADOW_BLUR_PX, SOFT_SHADOW_ALPHA),
        (CONTACT_HALF_WIDTH, contact_h, CONTACT_BEHIND, CONTACT_FRONT, CONTACT_SHADOW_BLUR_PX, CONTACT_SHADOW_ALPHA),
    ):
        t = np.abs(np.arange(sx1, sx2) + 0.5 - middle) / (half * w)
        reach = np.sqrt(np.clip(1 - t**SHADOW_END_POWER, 0, 1)) * height
        band = (rows >= feet - behind * reach) & (rows <= feet + front * reach) & (reach > 0)
        mask = Image.fromarray((band * 255).astype(np.uint8), "L")
        _paste(layer, _blurred(mask, scaled(geometry, blur), (0, 0, 0), strength), sx1, sy1)


def _draw_riser(layer: Image.Image, geometry: FrameGeometry, riser_box: Box) -> None:
    """A white round riser seen slightly from above: its shadow on the desk, the side, then the top (ADR-079)."""
    x1, y1, x2, y2 = riser_shape(riser_box, geometry)
    if x2 <= x1 or y2 <= y1:
        return
    eh = riser_top_height(x2 - x1)
    pad = riser_box[2] - x2
    ox, oy = riser_box[0], riser_box[1]
    mask = Image.new("L", (riser_box[2] - ox, riser_box[3] - oy), 0)
    ImageDraw.Draw(mask).ellipse([x1 - ox, y2 - eh - oy, x2 - ox - 1, y2 - oy - 1], fill=255)
    _paste(
        layer,
        _blurred(mask, max(1, min(pad // 2, scaled(geometry, RISER_SHADOW_BLUR_PX))), (0, 0, 0), RISER_SHADOW_ALPHA),
        ox,
        oy,
    )
    # PIL draws ellipses without anti-aliasing: at frame size the round edges show as stair steps that the page then
    # scales up. Drawn larger and scaled down, then softened like the product photos (ADR-082).
    k = RISER_SUPERSAMPLE
    bx1, by1, bx2, by2 = (x1 - ox) * k, (y1 - oy) * k, (x2 - ox) * k - 1, (y2 - oy) * k - 1
    ek = eh * k
    body = Image.new("RGBA", (mask.width * k, mask.height * k), (*RISER_SIDE_COLOR[:3], 0))
    draw = ImageDraw.Draw(body)
    draw.ellipse([bx1, by2 - ek + 1, bx2, by2], fill=RISER_SIDE_COLOR, outline=RISER_EDGE_COLOR, width=k)
    draw.rectangle([bx1, by1 + ek // 2, bx2, by2 - ek // 2], fill=RISER_SIDE_COLOR)
    draw.rectangle([bx1, by1 + ek // 2, bx1 + k - 1, by2 - ek // 2], fill=RISER_EDGE_COLOR)
    draw.rectangle([bx2 - k + 1, by1 + ek // 2, bx2, by2 - ek // 2], fill=RISER_EDGE_COLOR)
    draw.ellipse([bx1, by1, bx2, by1 + ek - 1], fill=RISER_TOP_COLOR, outline=RISER_EDGE_COLOR, width=k)
    body = body.resize(mask.size, Image.Resampling.BOX)
    body = body.filter(ImageFilter.GaussianBlur(CAMERA_BLUR_PX * geometry.height / 832))
    _paste(layer, body, ox, oy)


def sticker_lines(text: str) -> tuple[str, ...]:
    """The sticker's lines: a price range breaks after its dash, so each price stays whole."""
    low, sep, high = text.partition(PRICE_RANGE_SEP)
    return (f"{low}{sep.rstrip()}", high) if sep else (text,)


def _draw_sticker(
    layer: Image.Image, geometry: FrameGeometry, sticker: Sticker, fonts: SceneFonts, accent: tuple[int, int, int]
) -> None:
    """A round sticker in the accent colour with the catalog price in white, verbatim (FR-027)."""
    x1, y1, x2, y2 = sticker.box
    d = min(x2 - x1, y2 - y1)
    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        [x1, y1, x1 + d - 1, y1 + d - 1],
        fill=(*accent, 255),
        outline=(255, 255, 255, 255),
        width=scaled(geometry, STICKER_RING_PX),
    )
    lines = sticker_lines(sticker.text)
    room = STICKER_TEXT_WIDTH * d
    size = scaled(geometry, STICKER_MIN_SIZE)
    for size in range(scaled(geometry, STICKER_SIZE), scaled(geometry, STICKER_MIN_SIZE) - 1, -1):
        if max(fonts.get(size).getlength(line) for line in lines) <= room:
            break
    font = fonts.get(size)
    total = len(lines) * line_height(size)
    y = y1 + (d - total) / 2
    for line in lines:
        draw.text((x1 + d / 2, y), line, font=font, fill=(255, 255, 255, 255), anchor="ma")
        y += line_height(size)


def _draw_price_tag(
    layer: Image.Image, geometry: FrameGeometry, tag: PriceTag, fonts: SceneFonts, accent: tuple[int, int, int]
) -> None:
    """A rounded tag in the accent colour with the catalog price in white, verbatim (FR-031)."""
    x1, y1, x2, y2 = tag.box
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        [x1, y1, x2 - 1, y2 - 1], radius=(y2 - y1) // 2, fill=(*accent, 255), outline=(255, 255, 255, 255), width=1
    )
    room = (x2 - x1) - 2 * scaled(geometry, 4)
    size = scaled(geometry, PRICE_TAG_MIN_SIZE)
    for size in range(y2 - y1 - scaled(geometry, 6), scaled(geometry, PRICE_TAG_MIN_SIZE) - 1, -1):
        if fonts.get(size).getlength(tag.text) <= room:
            break
    draw.text(((x1 + x2) / 2, (y1 + y2) / 2), tag.text, font=fonts.get(size), fill=(255, 255, 255, 255), anchor="mm")


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    """`text` broken between words to `width`; a word wider than `width` keeps its own line, never cut."""
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(f"{lines[-1]} {word}") <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def promo_banner_lines(banner: PromoBanner, geometry: FrameGeometry, fonts: SceneFonts) -> tuple[int, list[list[str]]]:
    """The font size and, per promotion that fits, its wrapped lines (FR-032).

    The text shrinks before anything is left out; then whole promotions are left out from the end, never part of one.
    """
    x1, y1, x2, y2 = banner.box
    pad = scaled(geometry, PROMO_PAD_PX)
    width = x2 - x1 - 2 * pad
    room = y2 - y1 - 2 * pad
    size = scaled(geometry, PROMO_MIN_SIZE)
    blocks: list[list[str]] = []
    for size in range(scaled(geometry, PROMO_SIZE), scaled(geometry, PROMO_MIN_SIZE) - 1, -1):
        font = fonts.get(size, bold=False)
        blocks = [_wrap(f"{name}: {promo}", font, width) for name, promo in banner.lines]
        title_h = line_height(size) + pad // 2
        if title_h + sum(len(b) for b in blocks) * line_height(size) <= room:
            return size, blocks
    title_h = line_height(size) + pad // 2
    kept: list[list[str]] = []
    used = title_h
    for block in blocks:
        if used + len(block) * line_height(size) > room:
            break
        kept.append(block)
        used += len(block) * line_height(size)
    return size, kept


def _draw_promo_banner(
    layer: Image.Image, geometry: FrameGeometry, banner: PromoBanner, fonts: SceneFonts, accent: tuple[int, int, int]
) -> None:
    """A yellow sale strip on the desk front: a "KHUYẾN MÃI" pill, then each promotion with its product (FR-032)."""
    size, blocks = promo_banner_lines(banner, geometry, fonts)
    if len(blocks) < len(banner.lines):
        logger.info("promo_banner_trimmed shown=%d of=%d", len(blocks), len(banner.lines))
    if not blocks:
        return
    x1, y1, x2, _ = banner.box
    pad = scaled(geometry, PROMO_PAD_PX)
    lh = line_height(size)
    title_h = lh + pad // 2
    height = 2 * pad + title_h + sum(len(b) for b in blocks) * lh
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle([x1, y1, x2 - 1, y1 + height - 1], radius=scaled(geometry, PROMO_RADIUS_PX), fill=PROMO_FILL)
    title_font = fonts.get(size)
    title_w = title_font.getlength(PROMO_TITLE) + 2 * pad
    draw.rounded_rectangle([x1 + pad, y1 + pad, x1 + pad + title_w, y1 + pad + lh], radius=lh // 2, fill=(*accent, 255))
    draw.text((x1 + 2 * pad, y1 + pad + lh / 2), PROMO_TITLE, font=title_font, fill=(255, 255, 255, 255), anchor="lm")
    y = y1 + pad + title_h
    font = fonts.get(size, bold=False)
    for block in blocks:
        for line in block:
            draw.text((x1 + pad, y), line, font=font, fill=PROMO_TEXT)
            y += lh


def _fit_card(text: CardText, box: Box, geometry: FrameGeometry) -> CardText:
    """Drop the promotion, then the name's second line, until the card fits its box."""
    room = box[3] - box[1]
    if card_height(text, geometry) > room and text.promotion_lines:
        text = CardText(text.name_lines, text.price_lines, (), text.name_size, text.price_size, text.promo_size)
    if card_height(text, geometry) > room and len(text.name_lines) > 1:
        first = text.name_lines[0]
        name = (first if first.endswith("…") else f"{first}…",)
        text = CardText(name, text.price_lines, (), text.name_size, text.price_size, text.promo_size)
    return text


def _draw_card(
    layer: Image.Image,
    text: CardText,
    box: Box,
    geometry: FrameGeometry,
    fonts: SceneFonts,
    *,
    highlighted: bool,
    accent: tuple[int, int, int],
) -> None:
    x1, y1, x2, _ = box
    height = card_height(text, geometry)
    draw = ImageDraw.Draw(layer)
    radius = scaled(geometry, CARD_RADIUS_PX)
    border = CARD_BORDER_PX if highlighted else 0
    draw.rounded_rectangle(
        [x1, y1, x2 - 1, y1 + height - 1],
        radius=radius,
        fill=CARD_FILL,
        outline=(*accent, 255) if highlighted else None,
        width=border,
    )
    pad, gap = scaled(geometry, CARD_PAD_PX), scaled(geometry, LINE_GAP_PX)
    cx = (x1 + x2) / 2
    y = y1 + pad
    for line in text.name_lines:
        draw.text((cx, y), line, font=fonts.get(text.name_size), fill=NAME_COLOR, anchor="ma")
        y += line_height(text.name_size)
    y += gap
    for line in text.price_lines:
        draw.text((cx, y), line, font=fonts.get(text.price_size), fill=(*accent, 255), anchor="ma")
        y += line_height(text.price_size)
    if text.promotion_lines:
        y += 2 * gap
        promo_h = len(text.promotion_lines) * line_height(text.promo_size) + 2 * gap
        draw.rounded_rectangle([x1 + pad, y, x2 - 1 - pad, y + promo_h - 1], radius=radius // 2, fill=(*accent, 255))
        y += gap
        for line in text.promotion_lines:
            font = fonts.get(text.promo_size, bold=False)
            draw.text((cx, y), line, font=font, fill=(255, 255, 255, 255), anchor="ma")
            y += line_height(text.promo_size)


def punch(layer: Image.Image, geometry: FrameGeometry, origin: tuple[int, int] = (0, 0)) -> None:
    """Make the face zone, the "AI" label and the watermark fully transparent (FR-019, FR-020)."""
    ox, oy = origin
    for x1, y1, x2, y2 in [geometry.face_zone, *geometry.keep_out_boxes()]:
        box = (max(0, x1 - ox), max(0, y1 - oy), min(layer.width, x2 - ox), min(layer.height, y2 - oy))
        if box[0] < box[2] and box[1] < box[3]:
            layer.paste((0, 0, 0, 0), box)


def _cropped(name: str, layer: Image.Image) -> SceneLayer:
    bbox = layer.getchannel("A").getbbox()
    if bbox is None:
        return SceneLayer(name, 0, 0, None)  # type: ignore[arg-type]
    image = layer.crop(bbox)
    return SceneLayer(name, bbox[0], bbox[1], image, encode_png(image))  # type: ignore[arg-type]


def card_texts(
    scene: SceneSet,
    layout: SceneLayout,
    products: Mapping[str, Product],
    geometry: FrameGeometry,
    fonts: SceneFonts,
) -> dict[str, CardText]:
    """What each drawn card says, fitted to its box: verbatim from the file (FR-011), logged by the controller."""
    texts: dict[str, CardText] = {}
    for slot in layout.slots:
        product = products.get(slot.product_id)
        if slot.card_box is None or product is None:
            continue
        text = card_text(
            product,
            slot.card_box[2] - slot.card_box[0],
            fonts,
            geometry,
            highlighted=slot.highlighted,
            show_promotion=scene.layout.show_promotion,
        )
        texts[slot.product_id] = _fit_card(text, slot.card_box, geometry)
    return texts


def render_base(
    scene: SceneSet,
    layout: SceneLayout,
    products: Mapping[str, Product],
    geometry: FrameGeometry,
    fonts: SceneFonts,
    *,
    desk_in_image: bool = False,
) -> SceneLayer:
    """The desk, every placed product and its card, cropped to what was drawn.

    `desk_in_image` (011): the character's picture already shows a desk, so drawing another would cover it.
    """
    layer = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    if not layout.drawable:
        return SceneLayer("base", 0, 0, None)
    if not desk_in_image:
        _draw_desk(layer, scene, layout.desk_box)
    realistic = layout.mode in ("realistic", "showcase")
    if layout.mode == "showcase":
        # The showcase may cover the hands (FR-025), so the warm light must not cut them out.
        geometry = dataclasses.replace(geometry, hands_zone=None)
    any_highlight = any(s.highlighted for s in layout.slots)
    texts = card_texts(scene, layout, products, geometry, fonts)
    if layout.draw_order:
        # Far products first, so a nearer one always covers the one behind it (013 research R1).
        rank = {pid: i for i, pid in enumerate(layout.draw_order)}
        ordered = sorted(layout.slots, key=lambda s: rank.get(s.product_id, len(rank)))
    else:
        # The highlighted product is drawn last so its glow lies over its neighbours, never under them.
        ordered = sorted(layout.slots, key=lambda s: s.highlighted)
    for slot in ordered:
        art = scene.art.get(slot.product_id)
        if layout.riser_box is not None and slot.station == "showcase_middle":
            # Just before the main product: the riser covers the products behind it, the product stands on it.
            _draw_riser(layer, geometry, layout.riser_box)
        if art is not None and slot.art_box is not None:
            _draw_product(
                layer,
                art.desk_image,
                slot.art_box,
                highlighted=slot.highlighted,
                dimmed=any_highlight and not slot.highlighted,
                accent=scene.accent_color,
                brightness=scene.layout.brightness,
                geometry=geometry,
                shadow_box=slot.shadow_box,
                dim=REALISTIC_DIM if realistic else DIM_BRIGHTNESS,
                light_alpha=SHOWCASE_HIGHLIGHT_ALPHA if layout.mode == "showcase" else HIGHLIGHT_ALPHA,
            )
    for slot in layout.slots:
        text = texts.get(slot.product_id)
        if text is None or slot.card_box is None:
            continue
        _draw_card(layer, text, slot.card_box, geometry, fonts, highlighted=slot.highlighted, accent=scene.accent_color)
    if layout.sticker is not None:
        _draw_sticker(layer, geometry, layout.sticker, fonts, scene.accent_color)
    for tag in layout.price_tags:
        _draw_price_tag(layer, geometry, tag, fonts, scene.accent_color)
    if layout.promo_banner is not None:
        _draw_promo_banner(layer, geometry, layout.promo_banner, fonts, scene.accent_color)
    punch(layer, geometry)
    return _cropped("base", layer)


def render_subtitle(text: str, layout: SceneLayout, geometry: FrameGeometry, fonts: SceneFonts) -> SceneLayer:
    """The sentence being spoken, at most two lines, in a dark box over the host's chest (FR-018)."""
    x1, y1, x2, _ = layout.subtitle_box
    pad = scaled(geometry, SUBTITLE_PAD_PX)
    clean = " ".join(text.split())
    # A smaller font before a cut: the end of a sentence is often the price or the condition.
    for size in range(scaled(geometry, SUBTITLE_SIZE), scaled(geometry, SUBTITLE_MIN_SIZE) - 1, -1):
        font = fonts.get(size)
        lines, complete = wrap_text(clean, font, x2 - x1 - 2 * pad, 2)
        if complete:
            break
    if not text.strip() or not lines:
        return SceneLayer("subtitle", 0, 0, None)
    widest = max(font.getlength(line) for line in lines)
    box_w = min(x2 - x1, round(widest) + 2 * pad)
    box_h = len(lines) * line_height(size) + 2 * pad - scaled(geometry, LINE_GAP_PX)
    bx = (x1 + x2 - box_w) // 2
    layer = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle([bx, y1, bx + box_w - 1, y1 + box_h - 1], radius=pad, fill=SUBTITLE_FILL)
    y = y1 + pad
    for line in lines:
        draw.text(((x1 + x2) / 2, y), line, font=font, fill=(255, 255, 255, 255), anchor="ma")
        y += line_height(size)
    punch(layer, geometry)
    return _cropped("subtitle", layer)


def compose_still(face: Image.Image, layers: Iterable[SceneLayer | None]) -> Image.Image:
    """The still image as viewers see it: the host, then each layer at its place (no "AI" label: the page draws it)."""
    out = face.convert("RGBA")
    for layer in layers:
        if layer is not None and layer.image is not None:
            out.alpha_composite(layer.image, (layer.x, layer.y))
    return out.convert("RGB")


def draw_debug_zones(image: Image.Image, geometry: FrameGeometry, layout: SceneLayout | None = None) -> Image.Image:
    """Dashed outlines of the keep-out zones for `preview --debug-zones` and `preview.png?debug=1`.

    Never sent to the fork or the page. 013 adds the desk edge (green, across the frame) and the character's hands
    zone (purple), so the operator can measure `desk_top` and `hands_zone` against the picture (research R2).
    """
    out = image.convert("RGBA")
    draw = ImageDraw.Draw(out)
    zones: list[tuple[Box, tuple[int, int, int, int]]] = [(geometry.face_zone, DEBUG_COLORS["face"])]
    zones += [(box, DEBUG_COLORS["keep_out"]) for box in geometry.keep_out_boxes()]
    if layout is not None:
        zones.append((layout.subtitle_box, DEBUG_COLORS["subtitle"]))
    if geometry.hands_zone is not None:
        zones.append((geometry.hands_zone, DEBUG_COLORS["hands"]))
    for (x1, y1, x2, y2), color in zones:
        x2, y2 = min(x2, out.width) - 1, min(y2, out.height) - 1
        x1, y1 = max(0, x1), max(0, y1)
        for x in range(x1, x2, DEBUG_STEP_PX):
            draw.line([(x, y1), (min(x + DEBUG_DASH_PX, x2), y1)], fill=color, width=2)
            draw.line([(x, y2), (min(x + DEBUG_DASH_PX, x2), y2)], fill=color, width=2)
        for y in range(y1, y2, DEBUG_STEP_PX):
            draw.line([(x1, y), (x1, min(y + DEBUG_DASH_PX, y2))], fill=color, width=2)
            draw.line([(x2, y), (x2, min(y + DEBUG_DASH_PX, y2))], fill=color, width=2)
    if layout is not None:
        desk_y = min(layout.desk_box[1], out.height - 1)
        for x in range(0, out.width, DEBUG_STEP_PX):
            end = min(x + DEBUG_DASH_PX, out.width - 1)
            draw.line([(x, desk_y), (end, desk_y)], fill=DEBUG_COLORS["desk"], width=2)
    return out.convert("RGB")
