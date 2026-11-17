"""Drawing the scene (research R5): one RGBA layer for the desk, products and cards, one for the subtitle.

The layers are what the fork blends over each lip-synced frame, and what the app blends over the still image. They are
transparent wherever the face, the "AI" label or the watermark is (FR-019, FR-020): the fork checks the same boxes and
refuses a layer that touches them.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Mapping

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from ai_live.products.models import Product
from ai_live.scene.fonts import SceneFonts
from ai_live.scene.layout import (
    CARD_PAD_PX,
    LINE_GAP_PX,
    card_height,
    card_text,
    line_height,
    scaled,
    wrap_text,
)
from ai_live.scene.models import Box, CardText, FrameGeometry, SceneLayer, SceneLayout, SceneSet

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
DEBUG_COLORS = {"face": (255, 0, 0, 255), "keep_out": (255, 200, 0, 255), "subtitle": (0, 200, 255, 255)}


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
) -> None:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return
    pic = art.resize((w, h), Image.Resampling.LANCZOS)
    if dimmed:
        alpha = pic.getchannel("A")
        pic = ImageEnhance.Brightness(pic.convert("RGB")).enhance(DIM_BRIGHTNESS).convert("RGBA")
        pic.putalpha(alpha)
    # Contact shadow: a product without one floats above the desk.
    pad = 12
    shadow_mask = Image.new("L", (w + 2 * pad, 2 * pad + 8), 0)
    ImageDraw.Draw(shadow_mask).ellipse([pad, pad, pad + w - 1, pad + 7], fill=255)
    _paste(layer, _blurred(shadow_mask, 5, (0, 0, 0), SHADOW_ALPHA), x1 - pad, y2 - pad - 4)
    if highlighted:
        glow_mask = Image.new("L", (w + 4 * GLOW_BLUR_PX, h + 4 * GLOW_BLUR_PX), 0)
        glow_mask.paste(pic.getchannel("A"), (2 * GLOW_BLUR_PX, 2 * GLOW_BLUR_PX))
        glow_mask = glow_mask.filter(ImageFilter.MaxFilter(5))
        glow = _blurred(glow_mask, GLOW_BLUR_PX, accent, GLOW_ALPHA)
        _paste(layer, glow, x1 - 2 * GLOW_BLUR_PX, y1 - 2 * GLOW_BLUR_PX)
    layer.alpha_composite(pic, (x1, y1))


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


def render_base(
    scene: SceneSet,
    layout: SceneLayout,
    products: Mapping[str, Product],
    geometry: FrameGeometry,
    fonts: SceneFonts,
) -> SceneLayer:
    """The desk, every placed product and its card, cropped to what was drawn."""
    layer = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    if not layout.drawable:
        return SceneLayer("base", 0, 0, None)
    _draw_desk(layer, scene, layout.desk_box)
    any_highlight = any(s.highlighted for s in layout.slots)
    # The highlighted product is drawn last so its glow lies over its neighbours, never under them.
    for slot in sorted(layout.slots, key=lambda s: s.highlighted):
        art = scene.art.get(slot.product_id)
        if art is not None and slot.art_box is not None:
            _draw_product(
                layer,
                art.image,
                slot.art_box,
                highlighted=slot.highlighted,
                dimmed=any_highlight and not slot.highlighted,
                accent=scene.accent_color,
            )
    for slot in layout.slots:
        product = products[slot.product_id]
        text = card_text(
            product,
            slot.card_box[2] - slot.card_box[0],
            fonts,
            geometry,
            highlighted=slot.highlighted,
            show_promotion=scene.layout.show_promotion,
        )
        text = _fit_card(text, slot.card_box, geometry)
        _draw_card(layer, text, slot.card_box, geometry, fonts, highlighted=slot.highlighted, accent=scene.accent_color)
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
    """Dashed outlines of the keep-out zones for `preview --debug-zones` (never sent to the fork or the page)."""
    out = image.convert("RGBA")
    draw = ImageDraw.Draw(out)
    zones: list[tuple[Box, tuple[int, int, int, int]]] = [(geometry.face_zone, DEBUG_COLORS["face"])]
    zones += [(box, DEBUG_COLORS["keep_out"]) for box in geometry.keep_out_boxes()]
    if layout is not None:
        zones.append((layout.subtitle_box, DEBUG_COLORS["subtitle"]))
    for (x1, y1, x2, y2), color in zones:
        x2, y2 = min(x2, out.width) - 1, min(y2, out.height) - 1
        x1, y1 = max(0, x1), max(0, y1)
        for x in range(x1, x2, 10):
            draw.line([(x, y1), (min(x + 5, x2), y1)], fill=color, width=2)
            draw.line([(x, y2), (min(x + 5, x2), y2)], fill=color, width=2)
        for y in range(y1, y2, 10):
            draw.line([(x1, y), (x1, min(y + 5, y2))], fill=color, width=2)
            draw.line([(x2, y), (x2, min(y + 5, y2))], fill=color, width=2)
    return out.convert("RGB")
