"""Where everything goes in the frame (research R4). Pure: the same inputs always give the same boxes.

The frame from top to bottom: the host's face (never covered, FR-005/FR-006), a band where subtitles may go, the
products standing on the desk, and the name/price cards on the front of the desk. Every product of the file gets a
place (FR-007): the primary one in the middle and bigger, the secondary ones in file order around it, the one being
spoken about bigger still (FR-015).
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from PIL import ImageFont

from ai_live.brain.prompt import format_price
from ai_live.products.models import Product
from ai_live.scene.fonts import SceneFonts
from ai_live.scene.limits import ART_MAX_SIDE
from ai_live.scene.models import (
    WATERMARK_BOX,
    Box,
    CardText,
    FrameGeometry,
    KeepOut,
    LayoutParams,
    PriceTag,
    ProductArt,
    PromoBanner,
    SceneIssue,
    SceneLayout,
    Slot,
    Sticker,
    grow,
    intersects,
)
from ai_live.scene.shopee_overlay import frame_boxes

SIDE_MARGIN_PX = 12
SLOT_GAP_PX = 8
ART_PAD_PX = 4  # free space on each side of a product inside its slot
BOTTOM_MARGIN_PX = 10
# Heights as a share of the frame height. The products stand a little below the desk's top edge so the desk reads as
# a surface seen from slightly above, not a shelf.
BASELINE_BELOW_DESK = 0.07
SECONDARY_HEIGHT = 0.18
PRIMARY_HEIGHT = 0.205
MIN_ART_HEIGHT = 0.06  # below this a product is a smudge: show its card only
CARD_GAP_PX = 6
WEIGHT_SECONDARY = 1.0
WEIGHT_PRIMARY = 1.25
WEIGHT_HIGHLIGHT = 1.5
SUBTITLE_TOP = 0.40
SUBTITLE_HEIGHT = 0.085
SUBTITLE_SIDE_PX = 24
TOO_WIDE_MESSAGE = (
    "Ảnh {pid} quá rộng so với ô trên bàn, bị thu nhỏ quá mức nên chỉ hiện thẻ; dùng ảnh gần vuông hoặc dọc hơn"
)

ArtFit = Literal["shown", "highlight_only", "card_only"]

# Card text, in px on an 832 px frame (scaled with the frame height).
CARD_PAD_PX = 7
NAME_SIZE = 15
# A name shrinks this far before it is cut with "…": a whole name at 13 px reads better than half of one at 15.
NAME_MIN_SIZE = 13
PRICE_SIZE = 19
PRICE_MIN_SIZE = 12
PROMO_SIZE = 13
PROMO_MIN_SIZE = 11
LINE_GAP_PX = 3
MAX_LINES = 2
ELLIPSIS = "…"
PRICE_RANGE_SEP = " – "

# The AI label as the fork draws it (vendor/livetalking/ailive_ext/label.py): used until the fork reports the real
# box in `hello.scene`, and in still-image mode so the scene does not move when a session falls back to it.
LABEL_MARGIN_PX = 12
LABEL_FONT_RATIO = 0.031  # font size / frame height
LABEL_HEIGHT_RATIO = 1.8  # sprite height / font size: letters, outline and drop shadow (ADR-076)
LABEL_CHAR_RATIO = 0.8  # generous: Segoe UI Black plus outline averages ~0.68 of the font size per character
# `shopee-top` (ADR-085): below the Shopee app's title band, within the free centre band between its side buttons.
LABEL_SHOPEE_TOP_Y_RATIO = 0.125
LABEL_SHOPEE_TOP_WIDTH_RATIO = 0.26
# The fork fills that room down to the host's head line with a condensed face (ADR-089), so a wrapped label's box is
# estimated as the whole room rather than from a guessed glyph width.
LABEL_SHOPEE_TOP_BOTTOM_RATIO = 0.195
# Height added by each extra line, relative to the estimated font size; generous like LABEL_CHAR_RATIO, because the
# estimate shrinks the font more than the fork's real glyph widths need.
LABEL_LINE_RATIO = 1.8


def _two_lines(text: str) -> tuple[str, str] | None:
    """Split at the space nearest the middle, as the fork does; None for a single word."""
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return None
    cut = min(spaces, key=lambda i: abs(i - len(text) / 2))
    return text[:cut].strip(), text[cut + 1 :].strip()


def label_lines(width: int, height: int, text: str, position: str) -> tuple[tuple[str, ...], float]:
    """The label's lines and estimated font size: `shopee-top` wraps into two lines before shrinking (ADR-085)."""
    font_px = max(10.0, height * LABEL_FONT_RATIO)
    if position != "shopee-top":
        return (text,), font_px
    room = min(width - 2 * LABEL_MARGIN_PX, round(width * LABEL_SHOPEE_TOP_WIDTH_RATIO))
    if len(text) * font_px * LABEL_CHAR_RATIO <= room:
        return (text,), font_px
    lines = _two_lines(text) or (text,)
    longest = max(len(line) for line in lines)
    return lines, min(font_px, room / (longest * LABEL_CHAR_RATIO))


def estimate_label_box(width: int, height: int, text: str, position: str) -> Box:
    lines, font_px = label_lines(width, height, text, position)
    room = width - 2 * LABEL_MARGIN_PX
    if position == "shopee-top":
        room = min(room, round(width * LABEL_SHOPEE_TOP_WIDTH_RATIO))
    # The fork shrinks a label that would not fit its room (ADR-065), so the box never leaves the frame.
    longest = max(len(line) for line in lines)
    box_w = min(round(longest * font_px * LABEL_CHAR_RATIO), room)
    box_h = round(font_px * (LABEL_HEIGHT_RATIO + LABEL_LINE_RATIO * (len(lines) - 1)))
    if position == "shopee-top" and len(lines) > 1:
        box_w = room
        box_h = round(height * LABEL_SHOPEE_TOP_BOTTOM_RATIO) - round(height * LABEL_SHOPEE_TOP_Y_RATIO)
    if position.endswith("left"):
        x1 = LABEL_MARGIN_PX
    elif position.endswith("right"):
        x1 = width - LABEL_MARGIN_PX - box_w
    else:
        x1 = (width - box_w) // 2
    if position == "shopee-top":
        y1 = round(height * LABEL_SHOPEE_TOP_Y_RATIO)
    elif position.startswith("top"):
        y1 = LABEL_MARGIN_PX
    else:
        y1 = height - LABEL_MARGIN_PX - box_h
    return x1, y1, x1 + box_w, y1 + box_h


def estimate_geometry(
    label_text: str, label_position: str, *, width: int = 480, height: int = 832, face_bottom: int | None = None
) -> FrameGeometry:
    """The frame as the app guesses it before (or without) the fork's `hello.scene`."""
    keep_out = (
        KeepOut("ai_label", estimate_label_box(width, height, label_text, label_position)),
        KeepOut("watermark", WATERMARK_BOX),
    )
    bottom = face_bottom if face_bottom is not None else round(height * 0.45)
    return FrameGeometry(width, height, bottom, keep_out, "estimate")


def slot_order(products: Sequence[Product], max_slots: int) -> tuple[list[str], list[str]]:
    """(ids left to right, ids without a place). The primary one is in the middle; the others keep file order."""
    primary = next((p for p in products if p.is_primary), None)
    others = [p.id for p in products if p is not primary]
    room = max_slots - (1 if primary is not None else 0)
    placed, overflow = others[: max(0, room)], others[max(0, room) :]
    if primary is None:
        return placed, overflow
    k = len(placed) // 2
    return placed[:k] + [primary.id] + placed[k:], overflow


def scaled(geometry: FrameGeometry, px: float) -> int:
    return max(1, round(px * geometry.height / 832))


def wrap_text(text: str, font: ImageFont.FreeTypeFont, width: int, max_lines: int) -> tuple[tuple[str, ...], bool]:
    """Word-wrap into at most `max_lines`; True when everything fit. A cut line ends with "…".

    A word is never split when it holds a digit: "SPF 5…" or "50.0…" would show a number that is not in the file.
    """
    words = text.split()
    lines: list[str] = []
    i = 0
    while i < len(words) and len(lines) < max_lines:
        line = words[i]
        if font.getlength(line) > width:
            if any(c.isdigit() for c in line):
                break
            while line and font.getlength(line + ELLIPSIS) > width:
                line = line[:-1]
            lines.append(line + ELLIPSIS)
            return tuple(lines), False
        i += 1
        while i < len(words) and font.getlength(f"{line} {words[i]}") <= width:
            line = f"{line} {words[i]}"
            i += 1
        lines.append(line)
    if i >= len(words):
        return tuple(lines), True
    # Cut: end the last line with "…", dropping whole words until it fits.
    last_words = lines.pop().split() if lines else []
    while last_words and font.getlength(" ".join(last_words) + ELLIPSIS) > width:
        last_words.pop()
    lines.append((" ".join(last_words) + ELLIPSIS) if last_words else ELLIPSIS)
    return tuple(lines), False


def price_text(product: Product) -> str:
    low, high = product.price_range
    return format_price(low) if low == high else f"{format_price(low)}{PRICE_RANGE_SEP}{format_price(high)}"


def card_text(
    product: Product,
    width: int,
    fonts: SceneFonts,
    geometry: FrameGeometry,
    *,
    highlighted: bool = False,
    show_promotion: bool = True,
) -> CardText:
    """What the card says, verbatim from the file (FR-011, FR-012, FR-014), fitted to `width` px."""
    inner = max(10, width - 2 * scaled(geometry, CARD_PAD_PX))
    name_size = scaled(geometry, NAME_SIZE)
    for size in range(name_size, scaled(geometry, NAME_MIN_SIZE) - 1, -1):
        name_lines, complete = wrap_text(product.name, fonts.get(size), inner, MAX_LINES)
        if complete:
            name_size = size
            break
    else:
        name_lines, _ = wrap_text(product.name, fonts.get(name_size), inner, MAX_LINES)

    price = price_text(product)
    price_lines: tuple[str, ...] = (price,)
    price_size = scaled(geometry, PRICE_SIZE)
    while price_size > scaled(geometry, PRICE_MIN_SIZE) and fonts.get(price_size).getlength(price) > inner:
        price_size -= 1
    if fonts.get(price_size).getlength(price) > inner and PRICE_RANGE_SEP in price:
        low, high = price.split(PRICE_RANGE_SEP)
        price_lines = (low + PRICE_RANGE_SEP.rstrip(), high)

    promotion_lines: tuple[str, ...] = ()
    promo_size = scaled(geometry, PROMO_SIZE)
    if highlighted and show_promotion and product.promotions:
        first = product.promotions[0]
        # The pill is inset by the card padding and keeps half of it inside on each side.
        pill_inner = max(10, inner - scaled(geometry, CARD_PAD_PX))
        for size in range(promo_size, scaled(geometry, PROMO_MIN_SIZE) - 1, -1):
            lines, complete = wrap_text(first, fonts.get(size, bold=False), pill_inner, MAX_LINES)
            # A half promotion ("Giảm 30.000đ cho…") misleads about its condition: show it whole or not at all.
            if complete:
                promotion_lines, promo_size = lines, size
                break
    return CardText(name_lines, price_lines, promotion_lines, name_size, price_size, promo_size)


def line_height(size: int) -> int:
    """Room for one line: Vietnamese stacks diacritics above capitals, so lines need ~25% more than the font size."""
    return round(size * 1.25)


def card_height(text: CardText, geometry: FrameGeometry) -> int:
    pad, gap = scaled(geometry, CARD_PAD_PX), scaled(geometry, LINE_GAP_PX)
    height = 2 * pad + len(text.name_lines) * line_height(text.name_size) + gap
    height += len(text.price_lines) * line_height(text.price_size)
    if text.promotion_lines:
        # Two gaps above the pill so it never touches the price's descenders, two inside it around the text.
        height += 2 * gap + len(text.promotion_lines) * line_height(text.promo_size) + 2 * gap
    return height


def _bottom_shift(geometry: FrameGeometry, bottom: int) -> int:
    """How far up the desk area moves so the cards end above a label in a bottom corner."""
    limit = bottom
    for box in geometry.keep_out_boxes():
        if box[1] > geometry.height // 2:
            limit = min(limit, box[1] - 4)
    return bottom - limit


def compute_layout(
    products: Sequence[Product],
    art_sizes: Mapping[str, tuple[int, int]],
    geometry: FrameGeometry,
    params: LayoutParams,
    highlight: str | None = None,
    *,
    desk_top: float | None = None,
) -> SceneLayout:
    """Boxes for the desk, each product and its card. `art_sizes` is (w, h) of each product's picture.

    `desk_top` is the character's own desk line (011: a picture with the desk in it); it replaces
    `params.desk_top`, and the face keep-out still applies to it.
    """
    W, H = geometry.width, geometry.height
    issues: list[SceneIssue] = []
    face_limit = geometry.face_zone[3]
    bottom = H - BOTTOM_MARGIN_PX
    shift = _bottom_shift(geometry, bottom)
    desk_y = round((params.desk_top if desk_top is None else desk_top) * H) - shift
    desk_box: Box = (0, desk_y, W, H)
    subtitle_top = max(round(SUBTITLE_TOP * H), face_limit + 4)
    subtitle_box: Box = (
        SUBTITLE_SIDE_PX,
        subtitle_top,
        W - SUBTITLE_SIDE_PX,
        subtitle_top + round(SUBTITLE_HEIGHT * H),
    )
    if desk_y <= face_limit:
        # The desk would cover the chin: draw nothing rather than hide the face (FR-006).
        issues.append(
            SceneIssue(
                "error",
                "layout_keep_out",
                f"Mặt bàn ({desk_y}px) chạm vùng mặt ({face_limit}px): không vẽ cảnh; hạ layout.desk_top",
            )
        )
        return SceneLayout((), (), desk_box, subtitle_box, tuple(issues))

    order, overflow = slot_order(products, params.max_slots)
    if overflow:
        issues.append(
            SceneIssue.of("overflow", f"Quá {params.max_slots} sản phẩm, không có chỗ trên bàn: {', '.join(overflow)}")
        )
    by_id = {p.id: p for p in products}
    if highlight not in order:
        highlight = None
    weights = [
        WEIGHT_HIGHLIGHT if pid == highlight else WEIGHT_PRIMARY if by_id[pid].is_primary else WEIGHT_SECONDARY
        for pid in order
    ]
    span = W - 2 * SIDE_MARGIN_PX - SLOT_GAP_PX * max(0, len(order) - 1)
    baseline = desk_y + round(BASELINE_BELOW_DESK * H)
    card_top = baseline + CARD_GAP_PX
    card_bottom = bottom - shift
    max_art_h = baseline - face_limit - 4
    slots: list[Slot] = []
    x = float(SIDE_MARGIN_PX)
    total = sum(weights) or 1.0
    for pid, weight in zip(order, weights, strict=True):
        width = span * weight / total
        x1, x2 = round(x), round(x + width)
        x += width + SLOT_GAP_PX
        product = by_id[pid]
        art_box: Box | None = None
        size = art_sizes.get(pid)
        if size is not None:
            target = (PRIMARY_HEIGHT if product.is_primary else SECONDARY_HEIGHT) * H
            if pid == highlight:
                target *= params.highlight_scale
            target = min(target, max_art_h)
            aw, ah = size
            h = target
            w = h * aw / ah
            room = (x2 - x1) - 2 * ART_PAD_PX
            narrowed = w > room
            if narrowed:
                w, h = room, room * ah / aw
            if h < MIN_ART_HEIGHT * H:
                # Name the real cause (FR-004a): a picture too flat for its slot needs another picture, while a
                # face zone reaching the desk needs the layout changed.
                if narrowed and target >= MIN_ART_HEIGHT * H:
                    issues.append(SceneIssue.of("art_too_wide", f"{TOO_WIDE_MESSAGE.format(pid=pid)} ({aw}×{ah})", pid))
                else:
                    issues.append(
                        SceneIssue.of("layout_keep_out", f"Không đủ chỗ cho ảnh {pid} dưới vùng mặt: chỉ hiện thẻ", pid)
                    )
            else:
                cx = (x1 + x2) / 2
                art_box = (round(cx - w / 2), round(baseline - h), round(cx + w / 2), baseline)
        card_box: Box = (x1, card_top, x2, card_bottom)
        for box in [art_box, card_box]:
            if box is not None and any(intersects(box, k) for k in geometry.keep_out_boxes()):
                issues.append(SceneIssue.of("layout_keep_out", f"Ô của {pid} chạm vùng nhãn/watermark", pid))
        slots.append(Slot(pid, (x1 + x2) // 2, x2 - x1, art_box, card_box, pid == highlight, product.is_primary))
    return SceneLayout(tuple(slots), tuple(overflow), desk_box, subtitle_box, tuple(issues))


def art_fit(
    products: Sequence[Product],
    product_id: str,
    size: tuple[int, int],
    geometry: FrameGeometry,
    params: LayoutParams,
    *,
    desk_top: float | None = None,
) -> ArtFit:
    """Whether a picture of `size` for `product_id` will show on the desk, judged by its shape only (FR-004a).

    Slot widths depend on the product list and the highlight, never on the other pictures, so only this one is laid
    out. "highlight_only": the slot is wide enough only while the AI talks about the product. A face zone reaching
    the desk is a frame problem, not this picture's, and is reported by `compute_layout` as `layout_keep_out`.
    """

    def too_wide(highlight: str | None) -> bool:
        layout = compute_scene_layout(products, {product_id: size}, geometry, params, highlight, desk_top=desk_top)
        return any(i.code == "art_too_wide" and i.product_id == product_id for i in layout.issues)

    if not too_wide(None):
        return "shown"
    return "card_only" if too_wide(product_id) else "highlight_only"


# ---------- 013: products standing on the desk like real ones (research R1, R2, R3) ----------


@dataclass(frozen=True)
class DeskStation:
    """A fixed place on the desk (data-model §4). `x_frac` runs left to right across the side's free range."""

    name: str
    side: Literal["left", "right"]
    x_frac: float
    depth: float  # foot at desk_y + depth × (H − desk_y); smaller = further back
    height_frac: float  # target height as a share of H


# Research R1. The main product stands in front on the right; each next one is smaller and further back (FR-004).
# Heights revised 2026-11-23 against the live Ultralight frame (head about 0.20 H): the 2026-11-22 values drew
# bottles about a third of a head tall, far smaller than real ones on a desk in front of the host.
DESK_STATIONS: tuple[DeskStation, ...] = (
    DeskStation("P", "right", 0.2, 0.64, 0.25),
    DeskStation("S1", "left", 1.0, 0.56, 0.21),
    DeskStation("S2", "left", 0.0, 0.40, 0.19),
    DeskStation("S3", "right", 1.0, 0.32, 0.17),
    DeskStation("S4", "left", 0.45, 0.24, 0.15),
)
HANDS_GAP_PX = 8
DEFAULT_HANDS_X = (0.30, 0.70)
DEFAULT_HANDS_ABOVE_DESK = 0.10
# Shadow under each product (research R3), in px on an 832 px frame: render.py draws exactly these boxes.
CONTACT_SHADOW_WIDTH = 0.9
CONTACT_SHADOW_PX = 6
CONTACT_SHADOW_BLUR_PX = 3
CONTACT_SHADOW_ALPHA = 140
SOFT_SHADOW_WIDTH = 1.25
SOFT_SHADOW_HEIGHT = 0.10
SOFT_SHADOW_BLUR_PX = 8
SOFT_SHADOW_ALPHA = 70
SHADOW_BLUR_REACH = 2  # a Gaussian blur fades out within about two radii; the box keeps that much
SHRINK_STEP = 0.98
OVERLAP_STEP = 0.9
MAX_HIDDEN = 0.5  # the front product may hide at most half of the one behind (research R1)
MAX_OVERLAP_ROUNDS = 40
# A crowded side shrinks by these factors, in turn, until it stands without crowding. The smallest is about the
# 2026-11-22 station heights, which fit five products even on a narrow desk.
CROWD_SCALES = (1.0, 0.9, 0.8, 0.7, 0.6)
MIRROR_GAIN = 1.15  # the main product moves to the left only when it is drawn at least this much bigger there
HANDS_MISSING_MESSAGE = (
    "Nhân vật chưa khai scene.hands_zone: dùng vùng tay mặc định giữa khung; đo bằng preview --debug-zones rồi ghi vào"
    " character.json"
)
ART_BACKGROUND_MESSAGE = "Ảnh của {name} còn nền, sẽ trông như dán lên; hãy bỏ nền hoặc tải ảnh nền trong suốt"
MATTING_MISSING_MESSAGE = "Chưa cài model tách nền: ảnh nền phức tạp sẽ không bỏ nền được"
# The highlight on the realistic desk (research R3): a soft warm light behind the product, not the 009 accent glow.
HIGHLIGHT_COLOR = (255, 240, 210)
HIGHLIGHT_BLUR_PX = 12
# A warm light barely shows on a light wooden desk (2026-11-23 review: 120 and 170 were invisible there), so the
# spoken product stands out mostly by its lift and by the others stepping back; 0.85 is the 009 level, still readable.
HIGHLIGHT_ALPHA = 230
# In `showcase` the products stand in front of the host's dark shirt, so 230 drew a milky halo round the spoken
# product (2026-11-25 live check, ADR-093); 60 still lifts it, the shirt keeps its colour.
SHOWCASE_HIGHLIGHT_ALPHA = 60
REALISTIC_DIM = 0.85
HIGHLIGHT_STEP = 0.005
CARD_MIN_WIDTH_PX = 96
CARD_NO_ROOM_MESSAGE = "Không đủ chỗ cho thẻ của {name}; thẻ bị ẩn"


def art_background_issues(
    products: Sequence[Product], art: Mapping[str, ProductArt], params: LayoutParams
) -> list[SceneIssue]:
    """`art_has_background` for each product whose live picture still has its background (FR-018, research R10).

    Only the desk layouts care: a rectangle of background on a shelf row is how 009 always looked. A placeholder
    already fails the readiness check on its own.
    """
    if params.mode == "rows":
        return []
    return [
        SceneIssue.of("art_has_background", ART_BACKGROUND_MESSAGE.format(name=p.name), p.id)
        for p in products
        if (a := art.get(p.id)) is not None and a.opaque and not a.placeholder
    ]


def default_hands_zone(desk_top: float) -> tuple[float, float, float, float]:
    """Where the hands are assumed to be when the character does not say (research R2): the middle of the frame."""
    return DEFAULT_HANDS_X[0], max(0.0, desk_top - DEFAULT_HANDS_ABOVE_DESK), DEFAULT_HANDS_X[1], 1.0


def station_order(products: Sequence[Product], max_slots: int) -> tuple[list[str], list[str]]:
    """(ids by station, ids without one): the main product first, then the others in file order (research R1)."""
    primary = [p.id for p in products if p.is_primary][:1]
    ids = primary + [p.id for p in products if p.id not in primary]
    room = max(0, min(max_slots, len(DESK_STATIONS)))
    return ids[:room], ids[room:]


def shadow_ellipses(geometry: FrameGeometry, art: Box) -> tuple[Box, Box]:
    """(contact, soft) shadow ellipses before blur, both centred on the middle of the product's foot."""
    x1, _, x2, y2 = art
    w, h, cx = x2 - x1, art[3] - art[1], (x1 + x2) / 2
    contact_h = scaled(geometry, CONTACT_SHADOW_PX)
    soft_h = max(contact_h, SOFT_SHADOW_HEIGHT * h)

    def ellipse(width: float, height: float) -> Box:
        return (
            math.floor(cx - width / 2),
            math.floor(y2 - height / 2),
            math.ceil(cx + width / 2),
            math.ceil(y2 + height / 2),
        )

    return ellipse(CONTACT_SHADOW_WIDTH * w, contact_h), ellipse(SOFT_SHADOW_WIDTH * w, soft_h)


def shadow_box(geometry: FrameGeometry, art: Box) -> Box:
    """The area both shadow layers may darken, blur included (render.py draws them clipped to it)."""
    contact, soft = shadow_ellipses(geometry, art)
    c = grow(contact, SHADOW_BLUR_REACH * scaled(geometry, CONTACT_SHADOW_BLUR_PX))
    s = grow(soft, SHADOW_BLUR_REACH * scaled(geometry, SOFT_SHADOW_BLUR_PX))
    return min(c[0], s[0]), min(c[1], s[1]), max(c[2], s[2]), max(c[3], s[3])


def shadow_overhang(geometry: FrameGeometry, width: int) -> int:
    """How far `shadow_box` reaches past either side of a product `width` px wide."""
    art: Box = (0, 0, width, width)
    box = shadow_box(geometry, art)
    return max(-box[0], box[2] - width)


def glow_box(geometry: FrameGeometry, art: Box) -> Box:
    """The area the warm highlight may light around `art`, blur included (render.py draws it clipped to this)."""
    return grow(art, SHADOW_BLUR_REACH * scaled(geometry, HIGHLIGHT_BLUR_PX))


def _card_reserve(
    geometry: FrameGeometry, product: Product, *, highlighted: bool, show_promotion: bool
) -> tuple[int, int]:
    """(smallest, full) card height in px: one name line and the price, or everything the card may say.

    The fonts are not known here, so this takes the largest sizes; `render.card_texts` fits the text into the box.
    """
    pad, gap = scaled(geometry, CARD_PAD_PX), scaled(geometry, LINE_GAP_PX)
    low, high = product.price_range
    price_lines = 1 if low == high else 2
    name_line = line_height(scaled(geometry, NAME_SIZE))
    smallest = 2 * pad + name_line + gap + price_lines * line_height(scaled(geometry, PRICE_SIZE))
    full = smallest + name_line
    if highlighted and show_promotion and product.promotions:
        full += 4 * gap + MAX_LINES * line_height(scaled(geometry, PROMO_SIZE))
    return smallest, full


@dataclass(frozen=True)
class _Placed:
    art_box: Box
    shadow_box: Box
    height: float

    @property
    def area(self) -> int:
        return _area(self.art_box)


def _height_for_area(area: float, aspect: float) -> float:
    """The tallest whole height whose box, rounded as `_place` rounds it, stays strictly below `area`."""
    if math.isinf(area):
        return area
    h = math.floor(math.sqrt(area / aspect))
    while h > 0 and h * round(h * aspect) >= area:
        h -= 1
    return h


def _place(
    station: DeskStation,
    aspect: float,
    geometry: FrameGeometry,
    side_range: tuple[int, int],
    bottom: int,
    max_h: float,
    blockers: Sequence[Box],
    hands: Box,
) -> _Placed | Literal["too_wide", "no_room"]:
    """The biggest box up to `max_h` at `station` that keeps its shape and touches nothing it must not.

    The shadow reaches further than the product, so on the side facing the hands the range is cut by that overhang
    first; `x_frac` then spreads the products across what is left. Any product may be lit later without moving, so
    its light must already stay clear of the face and the labels here.
    """
    H = geometry.height
    lit_blockers = [geometry.face_zone, *geometry.keep_out_boxes()]
    lo, hi = side_range
    face_limit = geometry.face_zone[3]
    room = hi - lo
    width_limit = room / aspect
    h = min(max_h, width_limit, bottom - face_limit)
    while h >= MIN_ART_HEIGHT * H:
        h_px = round(h)
        w_px = round(h_px * aspect)
        overhang = shadow_overhang(geometry, w_px)
        if station.side == "left":
            a, b = lo, min(hi, hands[0] - overhang)
        else:
            a, b = max(lo, hands[2] + overhang), hi
        if b - a < w_px:
            h *= SHRINK_STEP
            continue
        cx = a + w_px / 2 + station.x_frac * (b - a - w_px)
        x1 = round(cx - w_px / 2)
        art: Box = (x1, bottom - h_px, x1 + w_px, bottom)
        shadow = shadow_box(geometry, art)
        if not any(intersects(box, zone) for box in (art, shadow) for zone in blockers) and not any(
            intersects(glow_box(geometry, art), zone) for zone in lit_blockers
        ):
            return _Placed(art, shadow, h)
        h *= SHRINK_STEP
    # A picture too flat for its side needs another picture; anything else is the frame's or the desk's fault.
    too_wide = width_limit < MIN_ART_HEIGHT * H <= min(max_h, bottom - face_limit)
    return "too_wide" if too_wide else "no_room"


@dataclass(frozen=True)
class _Settled:
    """One try of the realistic placement at a set-wide scale."""

    placed: dict[str, _Placed]
    failed: dict[str, str]
    dropped: set[str]
    squeezed: bool  # the overlap rule had to shrink some pair
    crowded: frozenset[str]  # the sides that were squeezed or lost a product

    @property
    def clean(self) -> bool:
        return not self.squeezed and not self.dropped and all(v == "too_wide" for v in self.failed.values())

    @property
    def lost(self) -> int:
        return len(self.dropped) + sum(v != "too_wide" for v in self.failed.values())

    @property
    def rank(self) -> tuple[int, bool, int]:
        """Fewest products lost, then no squeeze, then the most drawn area."""
        return (-self.lost, not self.squeezed, sum(p.area for p in self.placed.values()))


def _size_cap(pid: str, aspect: float, order: Sequence[str], placed: Mapping[str, _Placed]) -> float:
    """The tallest height `pid` may have so it is smaller than every product in front of it (FR-004).

    Smaller means not both taller and bigger in area. By height alone a flat box in front would squash every
    bottle behind it below its own height; by area alone a thin bottle in front would squash a square jar behind it
    to a smudge. A product behind may be taller but thinner, or wider but lower.
    """
    cap = math.inf
    for other in order[: order.index(pid)]:
        if other in placed:
            box = placed[other].art_box
            cap = min(cap, max(box[3] - box[1] - 1, _height_for_area(placed[other].area, aspect)))
    return cap


def _settle(
    order: Sequence[str],
    stations: Mapping[str, DeskStation],
    art_sizes: Mapping[str, tuple[int, int]],
    geometry: FrameGeometry,
    ranges: Mapping[str, tuple[int, int]],
    bottoms: Mapping[str, int],
    blockers: Sequence[Box],
    scales: Mapping[str, float],
) -> _Settled:
    """Place every product at its side's scale × its station height, then apply the overlap rule until it holds."""
    H = geometry.height
    hands = geometry.hands_zone
    assert hands is not None
    # Each product's extra shrink from the overlap rule; a product in `dropped` found no room behind another.
    extra = dict.fromkeys(order, 1.0)
    dropped: set[str] = set()
    placed: dict[str, _Placed] = {}
    failed: dict[str, str] = {}
    crowded: set[str] = set()
    for _ in range(MAX_OVERLAP_ROUNDS):
        placed, failed = {}, {}
        for pid in order:
            size = art_sizes.get(pid)
            if size is None or pid in dropped:
                continue
            station = stations[pid]
            aw, ah = size
            target = station.height_frac * H * scales[station.side]
            max_h = min(target * extra[pid], _size_cap(pid, aw / ah, order, placed))
            result = _place(station, aw / ah, geometry, ranges[station.side], bottoms[pid], max_h, blockers, hands)
            if isinstance(result, str):
                failed[pid] = result
                continue
            placed[pid] = result
        clash = _worst_overlap(placed, bottoms)
        if clash is None:
            lost = dropped | {p for p, why in failed.items() if why != "too_wide"}
            sides = frozenset(crowded | {stations[p].side for p in lost})
            return _Settled(placed, failed, dropped, bool(crowded), sides)
        crowded.update(stations[p].side for p in clash)
        front, back = clash
        # Shrink from the sizes actually drawn (a width-limited product is already below its target).
        smaller = {p: placed[p].height * OVERLAP_STEP for p in clash}
        if any(h < MIN_ART_HEIGHT * H for h in smaller.values()):
            dropped.add(back)
            extra[front] = extra[back] = 1.0
        else:
            for p, h in smaller.items():
                extra[p] = h / (stations[p].height_frac * H * scales[stations[p].side])
    raise RuntimeError("realistic layout did not settle")  # pragma: no cover - the loop settles well before this


def _mirrored(station: DeskStation) -> DeskStation:
    """The same station on the other side of the hands, at the same distance from them."""
    side: Literal["left", "right"] = "left" if station.side == "right" else "right"
    return dataclasses.replace(station, side=side, x_frac=1.0 - station.x_frac)


def _main_area(settled: _Settled, main: str) -> float:
    placed = settled.placed.get(main)
    return placed.area if placed is not None else 0


def _arrange(
    order: Sequence[str],
    stations: Mapping[str, DeskStation],
    art_sizes: Mapping[str, tuple[int, int]],
    geometry: FrameGeometry,
    ranges: Mapping[str, tuple[int, int]],
    bottoms: Mapping[str, int],
    blockers: Sequence[Box],
) -> _Settled:
    """Biggest first. A crowded side would otherwise squeeze pairs one by one until one is dropped, so that side
    shrinks evenly instead, step by step, while a side with room keeps its full size."""
    scales = dict.fromkeys(ranges, CROWD_SCALES[0])
    best: _Settled | None = None
    while True:
        settled = _settle(order, stations, art_sizes, geometry, ranges, bottoms, blockers, scales)
        if best is None or settled.rank > best.rank:
            best = settled
        steppable = [side for side in settled.crowded if scales[side] > CROWD_SCALES[-1]]
        if settled.clean or not steppable:
            return best
        for side in steppable:
            scales[side] = CROWD_SCALES[CROWD_SCALES.index(scales[side]) + 1]


def compute_realistic_layout(
    products: Sequence[Product],
    art_sizes: Mapping[str, tuple[int, int]],
    geometry: FrameGeometry,
    params: LayoutParams,
    highlight: str | None = None,
    *,
    desk_top: float | None = None,
) -> SceneLayout:
    """Products on both sides of the hands, the main one in front on the right (research R1), with cards (R4).

    Same inputs and result type as `compute_layout`. `geometry.hands_zone` is the character's; without one the
    default middle zone is used and a `hands_zone_missing` warning says so (research R2). The highlighted product
    grows by up to `highlight_scale` from the middle of its foot; the others keep the places they have without it.
    """
    W, H = geometry.width, geometry.height
    issues: list[SceneIssue] = []
    face_limit = geometry.face_zone[3]
    top = params.desk_top if desk_top is None else desk_top
    desk_y = round(top * H)
    desk_box: Box = (0, desk_y, W, H)
    subtitle_top = max(round(SUBTITLE_TOP * H), face_limit + 4)
    subtitle_box: Box = (
        SUBTITLE_SIDE_PX,
        subtitle_top,
        W - SUBTITLE_SIDE_PX,
        subtitle_top + round(SUBTITLE_HEIGHT * H),
    )
    if desk_y <= face_limit:
        issues.append(
            SceneIssue(
                "error",
                "layout_keep_out",
                f"Mặt bàn ({desk_y}px) chạm vùng mặt ({face_limit}px): không vẽ cảnh; hạ desk_top",
            )
        )
        return SceneLayout((), (), desk_box, subtitle_box, tuple(issues), mode="realistic")
    if geometry.hands_zone is None:
        geometry = geometry.with_hands_zone(default_hands_zone(top))
        issues.append(SceneIssue.of("hands_zone_missing", HANDS_MISSING_MESSAGE))
    hands = geometry.hands_zone
    assert hands is not None
    ranges = {
        "left": (SIDE_MARGIN_PX, hands[0] - HANDS_GAP_PX),
        "right": (hands[2] + HANDS_GAP_PX, W - SIDE_MARGIN_PX),
    }
    blockers = [geometry.face_zone, *geometry.keep_out_boxes(), hands]

    order, overflow = station_order(products, params.max_slots)
    if overflow:
        limit = min(params.max_slots, len(DESK_STATIONS))
        issues.append(SceneIssue.of("overflow", f"Quá {limit} sản phẩm, không có chỗ trên bàn: {', '.join(overflow)}"))
    by_id = {p.id: p for p in products}
    if highlight not in order:
        highlight = None
    band = H - desk_y
    bottoms = {pid: min(H, round(desk_y + st.depth * band)) for pid, st in zip(order, DESK_STATIONS, strict=False)}

    # The main product stands on the right unless the left lets it be drawn clearly bigger: a flat box on a narrow
    # side is held to that side's width, and every product behind it then stays smaller still (2026-11-23 review).
    # The choice is made before the highlight, so lighting a product never moves the others.
    stations = dict(zip(order, DESK_STATIONS, strict=False))
    best = _arrange(order, stations, art_sizes, geometry, ranges, bottoms, blockers)
    if order:
        mirrored = {pid: _mirrored(st) for pid, st in stations.items()}
        other = _arrange(order, mirrored, art_sizes, geometry, ranges, bottoms, blockers)
        main = order[0]
        if (-other.lost, _main_area(other, main)) > (-best.lost, _main_area(best, main) * MIRROR_GAIN):
            stations, best = mirrored, other
    placed, failed, dropped = best.placed, best.failed, best.dropped

    if highlight in placed:
        # FR-004 still holds while lit: never as big as the products it is compared with.
        aw, ah = art_sizes[highlight]
        ahead = _size_cap(highlight, aw / ah, order, placed)
        cap = H if math.isinf(ahead) else round(ahead)
        placed[highlight] = _lifted(placed[highlight], art_sizes[highlight], geometry, params, blockers, cap)
    cards = _realistic_cards(
        order, placed, by_id, stations, highlight, geometry, params, ranges, [*blockers, subtitle_box], subtitle_box
    )

    slots: list[Slot] = []
    for pid in order:
        station = stations[pid]
        p = placed.get(pid)
        card = cards.get(pid)
        if card == "no_room":
            issues.append(SceneIssue.of("card_no_room", CARD_NO_ROOM_MESSAGE.format(name=by_id[pid].name), pid))
        if pid in dropped:
            issues.append(SceneIssue.of("no_room", f"Ảnh {pid} bị món phía trước che quá nửa: không đặt", pid))
        elif pid in failed:
            if failed[pid] == "too_wide":
                aw, ah = art_sizes[pid]
                issues.append(SceneIssue.of("art_too_wide", f"{TOO_WIDE_MESSAGE.format(pid=pid)} ({aw}×{ah})", pid))
            else:
                issues.append(SceneIssue.of("no_room", f"Không còn chỗ cho ảnh {pid} ở bên {station.side}", pid))
        if p is not None:
            x_center, width = (p.art_box[0] + p.art_box[2]) // 2, p.art_box[2] - p.art_box[0]
        else:
            lo, hi = ranges[station.side]
            x_center, width = round(lo + station.x_frac * (hi - lo)), 0
        slots.append(
            Slot(
                pid,
                x_center,
                width,
                p.art_box if p else None,
                card if isinstance(card, tuple) else None,
                pid == highlight,
                by_id[pid].is_primary,
                station=station.name,
                shadow_box=p.shadow_box if p else None,
            )
        )
    # Far (foot higher up) first, so the nearer product always covers the one behind; the highlight keeps its place.
    draw_order = tuple(sorted(order, key=lambda pid: (bottoms[pid], order.index(pid))))
    return SceneLayout(
        tuple(slots), tuple(overflow), desk_box, subtitle_box, tuple(issues), mode="realistic", draw_order=draw_order
    )


def _lifted(
    p: _Placed,
    size: tuple[int, int],
    geometry: FrameGeometry,
    params: LayoutParams,
    blockers: Sequence[Box],
    max_h: int,
) -> _Placed:
    """The highlighted product grown from the middle of its foot, as much as `highlight_scale` allows (research R3).

    The box, its shadow and its light must stay clear of every zone; when even a small step does not fit, it stays
    as it was (the light alone still shows which product is spoken about).
    """
    x1, y1, x2, y2 = p.art_box
    aw, ah = size
    h0, cx = y2 - y1, (x1 + x2) / 2
    lit_blockers = [geometry.face_zone, *geometry.keep_out_boxes()]
    scale = params.highlight_scale
    while scale > 1.0 + 1e-9:
        h = min(round(h0 * scale), max_h)
        if h <= h0:
            return p
        w = round(h * aw / ah)
        left = round(cx - w / 2)
        art: Box = (left, y2 - h, left + w, y2)
        shadow = shadow_box(geometry, art)
        fits = 0 <= art[0] and art[2] <= geometry.width and art[1] >= 0
        if (
            fits
            and not any(intersects(box, zone) for box in (art, shadow) for zone in blockers)
            and not any(intersects(glow_box(geometry, art), zone) for zone in lit_blockers)
        ):
            return _Placed(art, shadow, float(h))
        scale -= HIGHLIGHT_STEP
    return p


def _realistic_cards(
    order: Sequence[str],
    placed: Mapping[str, _Placed],
    by_id: Mapping[str, Product],
    stations: Mapping[str, DeskStation],
    highlight: str | None,
    geometry: FrameGeometry,
    params: LayoutParams,
    ranges: Mapping[str, tuple[int, int]],
    blockers: Sequence[Box],
    subtitle_box: Box,
) -> dict[str, Box | Literal["no_room"]]:
    """Card boxes by product id (research R4); "no_room" for a card that must be hidden and reported."""
    if params.cards == "none":
        return {}
    arts = [p.art_box for p in placed.values()]
    gap = scaled(geometry, CARD_GAP_PX)
    floor = geometry.height - BOTTOM_MARGIN_PX
    cards: dict[str, Box | Literal["no_room"]] = {}

    def clear(card: Box, taken: Sequence[Box]) -> bool:
        return not any(intersects(card, zone) for zone in (*blockers, *arts, *taken))

    if params.cards == "all":
        taken: list[Box] = []
        for pid in order:
            p = placed.get(pid)
            if p is None:
                continue
            smallest, full = _card_reserve(
                geometry, by_id[pid], highlighted=pid == highlight, show_promotion=params.show_promotion
            )
            lo, hi = ranges[stations[pid].side]
            x1, head, x2, foot = p.art_box
            width = max(x2 - x1, scaled(geometry, CARD_MIN_WIDTH_PX))
            left = min(max(round((x1 + x2 - width) / 2), lo), hi - width)
            top = foot + gap
            card: Box = (left, top, left + width, min(top + full, floor))
            if width <= hi - lo and card[3] - card[1] >= smallest and clear(card, taken):
                cards[pid] = card
                taken.append(card)
            else:
                cards[pid] = "no_room"
        return cards

    # "one": only the product being spoken about.
    if highlight is None or highlight not in placed:
        return cards
    smallest, full = _card_reserve(geometry, by_id[highlight], highlighted=True, show_promotion=params.show_promotion)
    side = stations[highlight].side
    lo, hi = ranges[side]
    same_side = [placed[pid].art_box for pid in placed if stations[pid].side == side]
    # Above the products on its side, just under the subtitle band.
    bottom = min(box[1] for box in same_side) - gap
    above: Box = (lo, max(subtitle_box[3] + gap, bottom - full), hi, bottom)
    if above[3] - above[1] >= smallest and clear(above, ()):
        cards[highlight] = above
        return cards
    # Else at the bottom of its side, under every product there.
    top = max([floor - full, *(box[3] + gap for box in same_side)])
    below: Box = (lo, top, hi, floor)
    if below[3] - below[1] >= smallest and clear(below, ()):
        cards[highlight] = below
    else:
        cards[highlight] = "no_room"
    return cards


def _worst_overlap(placed: Mapping[str, _Placed], bottoms: Mapping[str, int]) -> tuple[str, str] | None:
    """(front, back) of the pair where the front product hides the largest share (> half) of the one behind."""
    worst: tuple[float, str, str] | None = None
    for a, b in itertools.combinations(placed, 2):
        front, back = (a, b) if bottoms[a] >= bottoms[b] else (b, a)
        fb, bb = placed[front].art_box, placed[back].art_box
        cover = _area((max(fb[0], bb[0]), max(fb[1], bb[1]), min(fb[2], bb[2]), min(fb[3], bb[3])))
        share = cover / max(1, _area(bb))
        if share > MAX_HIDDEN and (worst is None or share > worst[0]):
            worst = (share, front, back)
    return None if worst is None else (worst[1], worst[2])


def _area(box: Box) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


# ---------- 013 showcase: the main product big in front of the host (FR-025 to FR-028, ADR-079) ----------

SHOWCASE_MAX_SLOTS = 4
# x H: near real size. A 25 cm six-pack in front of a 23 cm head looks about 1.2x its size (ADR-082, was 0.38).
SHOWCASE_MAIN_HEIGHT = 0.28
# x W: a wider gift case leaves the bottle clusters beside it no room and shows the case well above its real size
# (ADR-096, ADR-097, ADR-098: was 0.42).
SHOWCASE_MAIN_MAX_WIDTH = 0.38
# Foot at desk_y + depth x band. A little back from the desk's front edge: the low main product in front, the taller
# stock behind it on both sides, one stepped group by the host's hands (ADR-097, was 0.8).
SHOWCASE_MAIN_DEPTH = 0.7
# The products behind, in order: (side, target height x H, depth). Right, left, then right again further back.
# Back products shrink with the main one (ADR-082), or they outgrow it.
SHOWCASE_BACK = (("right", 0.22, 0.35), ("left", 0.20, 0.35), ("right", 0.18, 0.20))
SHOWCASE_X_STEP_PX = 2
# FR-025 (ADR-081): no product hides another, so the main one gives room beside it before the others shrink.
SHOWCASE_GAP_PX = 8  # between two products (px on an 832 px frame)
SHOWCASE_MAIN_MIN_HEIGHT = 0.22  # x H: the main product shrinks no lower than this to make room
SHOWCASE_MAIN_STEP = 0.95
SHOWCASE_BACK_KEEP = 0.85  # the others keep this share of their target height while the main one shrinks
SHOWCASE_BACK_MIN_SCALE = 0.3  # then the others shrink together, down to this share of their target height
# 014 ADR-087: the depth band shrinks no lower than this share of the real desk band, so products stay on the desk.
SHOWCASE_MIN_BAND = 0.3
RISER_WIDTH = 1.1  # x the main product's width
RISER_SIDE_HEIGHT = 0.035  # x H: the riser's visible side
RISER_TOP_RATIO = 0.18  # the top ellipse's height / the riser's width: a slight look from above
RISER_SHADOW_PX = 10  # the riser's own shadow reaches this far past its shape (px on an 832 px frame)
STICKER_PX = 72  # diameter on an 832 px frame; 96 covered the bottle necks (ADR-082)
STICKER_NO_PRICE_MESSAGE = "Món chính {name} không có giá trong file dữ liệu; không vẽ sticker giá"
STICKER_NO_ROOM_MESSAGE = "Không có chỗ cho sticker giá của {name} ngoài vùng cấm; không vẽ sticker"
# 013 FR-031, FR-032 (ADR-095): a price tag at each product's foot and the promotions strip on the desk front.
PRICE_TAG_HEIGHT_PX = 24
PRICE_TAG_SIZE = 15  # font px; the renderer shrinks it to the tag when needed
PRICE_TAG_MIN_SIZE = 11  # a narrow product's tag may shrink to this, still readable on a phone
PRICE_TAG_PAD_PX = 7
PRICE_TAG_GAP_PX = 3  # between the product's foot and its tag
PRICE_TAG_CHAR_WIDTH = 0.62  # x the font size: a bold digit's width, to size the tag before any font is loaded
PRICE_TAG_NO_ROOM_MESSAGE = "Không có chỗ cho tem giá của {name} mà không che món khác; không vẽ tem"
PROMO_BANNER_GAP_PX = 6
PROMO_BANNER_MIN_HEIGHT_PX = 44  # the title row and one promotion at the smallest size
PROMO_BANNER_MAX_HEIGHT_PX = 150
PROMO_BANNER_RESERVE_PX = 76  # kept free below the cluster: the title row and three promotions at the smallest size
PROMO_BANNER_NO_ROOM_MESSAGE = "Không còn chỗ trên mặt bàn cho băng khuyến mãi; không vẽ băng"
# FR-028: below this many source pixels per drawn pixel a product looks soft once the frame is scaled up for OBS
# (1280 / 832 is about 1.5).
LOW_RES_FACTOR = 1.5
LOW_RES_MESSAGE = "Ảnh của {name} nhỏ ({src} px) so với cỡ vẽ ({drawn} px), sẽ mờ trên hình; hãy tải ảnh to hơn"


def riser_shape(riser_box: Box, geometry: FrameGeometry) -> Box:
    """The riser itself inside `SceneLayout.riser_box`, which also holds its shadow."""
    return grow(riser_box, -scaled(geometry, RISER_SHADOW_PX))


def riser_top_height(width: int) -> int:
    """Height of the riser's top ellipse for a riser `width` px wide."""
    return max(2, round(RISER_TOP_RATIO * width))


def _riser_for(cx: float, width: int, base: int, geometry: FrameGeometry) -> tuple[Box, int]:
    """(riser box with its shadow, the y the product stands on) for a riser under a product `width` px wide.

    `base` is where the riser's front edge meets the desk; the riser is lifted when its shadow would leave the frame.
    """
    rw = round(RISER_WIDTH * width)
    eh = riser_top_height(rw)
    side = round(RISER_SIDE_HEIGHT * geometry.height)
    pad = scaled(geometry, RISER_SHADOW_PX)
    base = min(base, geometry.height - (eh - eh // 2) - pad)
    left = round(cx - rw / 2)
    shape: Box = (left, base - side - eh // 2, left + rw, base + eh - eh // 2)
    return grow(shape, pad), base - side


def _clear(geometry: FrameGeometry, boxes: Sequence[Box], blockers: Sequence[Box]) -> bool:
    """Every box inside the frame sideways and at the top, and touching no blocker."""
    inside = all(b[0] >= 0 and b[2] <= geometry.width and b[1] >= 0 for b in boxes)
    return inside and not any(intersects(b, z) for b in boxes for z in blockers)


def _touches(box: Box, others: Sequence[Box], gap: int = 0) -> bool:
    """`box` comes nearer than `gap` px to any of `others`."""
    near = grow(box, gap)
    return any(intersects(near, o) for o in others)


def _lit_reserve(box: Box, scale: float) -> Box:
    """The room `box` takes once grown by `scale` from the middle of its foot, as `_lifted` grows it."""
    x1, y1, x2, y2 = box
    half, h = (x2 - x1) * scale / 2, (y2 - y1) * scale
    cx = (x1 + x2) / 2
    return (math.floor(cx - half), math.floor(y2 - h), math.ceil(cx + half), y2)


def _showcase_main(
    aspect: float, geometry: FrameGeometry, foot: int, blockers: Sequence[Box], *, riser: bool, max_h: float
) -> tuple[_Placed, Box | None] | Literal["too_wide", "no_room"]:
    """The main product in the middle, at most `max_h` tall, on its riser when asked."""
    W, H = geometry.width, geometry.height
    cx = W / 2
    width_limit = SHOWCASE_MAIN_MAX_WIDTH * W / aspect
    if width_limit < MIN_ART_HEIGHT * H:
        return "too_wide"
    h = min(max_h, width_limit)
    while h >= MIN_ART_HEIGHT * H:
        h_px = round(h)
        w_px = round(h_px * aspect)
        riser_box, stand = _riser_for(cx, w_px, foot, geometry) if riser else (None, foot)
        x1 = round(cx - w_px / 2)
        art: Box = (x1, stand - h_px, x1 + w_px, stand)
        shadow = shadow_box(geometry, art)
        boxes = [art, shadow, glow_box(geometry, art), *([riser_box] if riser_box else [])]
        if _clear(geometry, boxes, blockers):
            return _Placed(art, shadow, h), riser_box
        h *= SHRINK_STEP
    return "no_room"


def _showcase_back(
    aspect: float,
    side: str,
    target: float,
    min_h: float,
    foot: int,
    preferred: float,
    taken: Sequence[Box],
    geometry: FrameGeometry,
    blockers: Sequence[Box],
) -> _Placed | Literal["too_wide", "no_room"]:
    """A product behind: the free place nearest `preferred` (its inner edge), shrinking down to `min_h` when needed.

    Free means `SHOWCASE_GAP_PX` away from everything in `taken` (FR-025: no product hides another).
    """
    W, H = geometry.width, geometry.height
    if (W - 2 * SIDE_MARGIN_PX) / aspect < MIN_ART_HEIGHT * H:
        return "too_wide"
    gap = scaled(geometry, SHOWCASE_GAP_PX)
    h = target
    while h >= min_h:
        h_px = round(h)
        w_px = round(h_px * aspect)
        start = round(preferred) if side == "right" else round(preferred) - w_px
        # Nearest to the preferred place first; on a tie the outer one.
        candidates = sorted(
            range(SIDE_MARGIN_PX, W - SIDE_MARGIN_PX - w_px + 1, SHOWCASE_X_STEP_PX),
            key=lambda x: (abs(x - start), -x if side == "right" else x),
        )
        for x1 in candidates:
            art: Box = (x1, foot - h_px, x1 + w_px, foot)
            if _touches(art, taken, gap):
                continue
            shadow = shadow_box(geometry, art)
            if _clear(geometry, [art, shadow, glow_box(geometry, art)], blockers):
                return _Placed(art, shadow, h)
        h *= SHRINK_STEP
    return "no_room"


@dataclass
class _ShowcaseTry:
    placed: dict[str, _Placed]
    bottoms: dict[str, int]
    failed: dict[str, str]
    riser_box: Box | None


def _place_showcase(
    order: Sequence[str],
    art_sizes: Mapping[str, tuple[int, int]],
    geometry: FrameGeometry,
    params: LayoutParams,
    blockers: Sequence[Box],
    desk_y: int,
    main_h: float,
    back_scale: float,
) -> _ShowcaseTry:
    """One try: the main product at most `main_h` tall, the others `back_scale` x their target height.

    A product behind may still shrink to `SHOWCASE_BACK_KEEP` x that height to find a free place.
    """
    W, H = geometry.width, geometry.height
    band = _showcase_band(geometry, desk_y, params)
    out = _ShowcaseTry({}, {}, {}, None)
    sides: dict[str, str] = {}
    # What a product behind keeps clear of: the others at their lit size and the riser.
    taken: list[Box] = []
    for i, pid in enumerate(order):
        size = art_sizes.get(pid)
        if i == 0:
            side, foot = "middle", min(H, round(desk_y + SHOWCASE_MAIN_DEPTH * band))
        else:
            side, height, depth = SHOWCASE_BACK[i - 1]
            foot = min(H, round(desk_y + depth * band))
        out.bottoms[pid], sides[pid] = foot, side
        if size is None:
            continue
        aspect = size[0] / size[1]
        if i == 0:
            main = _showcase_main(aspect, geometry, foot, blockers, riser=params.riser, max_h=main_h)
            if isinstance(main, str):
                out.failed[pid] = main
                continue
            out.placed[pid], out.riser_box = main
            out.bottoms[pid] = main[0].art_box[3]
            if out.riser_box is not None:
                taken.append(riser_shape(out.riser_box, geometry))
        else:
            target = min(back_scale * height * H, _size_cap(pid, aspect, order, out.placed))
            # Its inner edge starts at the middle of the outermost product already on its side (or of the main one),
            # so each next product steps outwards to the nearest free place.
            same = [out.placed[q].art_box for q in out.placed if sides[q] in (side, "middle")]
            centres = [(b[0] + b[2]) / 2 for b in same] or [W / 2]
            preferred = max(centres) if side == "right" else min(centres)
            min_h = max(SHOWCASE_BACK_KEEP * target, MIN_ART_HEIGHT * H)
            result = _showcase_back(aspect, side, target, min_h, foot, preferred, taken, geometry, blockers)
            if isinstance(result, str):
                out.failed[pid] = result
                continue
            out.placed[pid] = result
        taken.append(_lit_reserve(out.placed[pid].art_box, params.highlight_scale))
    return out


def _showcase_band(geometry: FrameGeometry, desk_y: int, params: LayoutParams) -> float:
    """The desk band (px below the desk edge) that product depths are measured in.

    With `avoid_app_overlay` the band shrinks until the main product, on its riser when there is one, stands just above
    the highest Shopee app zone that starts below the desk edge (comments, chat bar). Every product uses the same band,
    so the main one still stands in front of the others (014 FR-019, ADR-087).
    """
    W, H = geometry.width, geometry.height
    band = float(H - desk_y)
    if band <= 0:
        return band
    floors: list[int] = []
    if params.avoid_app_overlay:
        tops = [box[1] for _, box in frame_boxes(W, H) if box[1] > desk_y]
        if tops:
            floors.append(min(tops) - scaled(geometry, SHOWCASE_GAP_PX))
    if params.promo_banner:
        # 013 FR-032 (ADR-095): the main product's foot, then its price tag, leave room for the promotions strip.
        tag = scaled(geometry, PRICE_TAG_GAP_PX + PRICE_TAG_HEIGHT_PX) if params.price_tags else 0
        reserve = scaled(geometry, BOTTOM_MARGIN_PX + PROMO_BANNER_RESERVE_PX + PROMO_BANNER_GAP_PX) + tag
        floors.append(H - reserve)
    if not floors:
        return band
    floor = min(floors)
    # The riser's side lifts the product above the riser's base.
    lift = round(RISER_SIDE_HEIGHT * H) if params.riser else 0
    fitting = (floor + lift - desk_y) / SHOWCASE_MAIN_DEPTH
    return max(min(band, fitting), SHOWCASE_MIN_BAND * band)


def _sticker_box(art: Box, geometry: FrameGeometry, blockers: Sequence[Box]) -> Box | None:
    """The sticker over a top corner of the main product: right first, then left, then just inside each corner.

    `blockers` holds the other products too: the sticker covers only the main one (FR-025, ADR-081).
    """
    d = scaled(geometry, STICKER_PX)
    x1, y1, x2, _ = art
    tries: list[Box] = [
        (round(x2 - 0.7 * d), round(y1 - 0.3 * d), round(x2 + 0.3 * d), round(y1 + 0.7 * d)),
        (round(x1 - 0.3 * d), round(y1 - 0.3 * d), round(x1 + 0.7 * d), round(y1 + 0.7 * d)),
        (x2 - d, y1, x2, y1 + d),
        (x1, y1, x1 + d, y1 + d),
    ]
    for box in tries:
        if _clear(geometry, [box], blockers) and box[3] <= geometry.height:
            return box
    return None


def _price_tags(
    order: Sequence[str],
    placed: Mapping[str, _Placed],
    by_id: Mapping[str, Product],
    geometry: FrameGeometry,
    blockers: Sequence[Box],
    skip: str | None,
) -> tuple[list[PriceTag], list[SceneIssue]]:
    """A tag with the catalog price, verbatim, just below each placed product's foot (FR-031).

    When the desk below is taken the tag hangs just above the product, or one row lower, or as a last resort on
    the product's own lower part; a tag never covers another product, another tag or a blocker. `skip` is the
    product that already shows its price on the sticker.
    """
    W, H = geometry.width, geometry.height
    h = scaled(geometry, PRICE_TAG_HEIGHT_PX)
    pad = scaled(geometry, PRICE_TAG_PAD_PX)
    gap = scaled(geometry, PRICE_TAG_GAP_PX)
    tags: list[PriceTag] = []
    issues: list[SceneIssue] = []
    for pid in order:
        p = placed.get(pid)
        if p is None or pid == skip:
            continue
        product = by_id[pid]
        if product.price_range[1] <= 0:
            continue  # no price in the data: nothing to show, and nothing may be guessed (Điều VII)
        text = price_text(product)
        x1, head, x2, foot = p.art_box
        others = [placed[q].art_box for q in placed if q != pid]
        taken = [*blockers, *others, *(t.box for t in tags)]
        # A narrow product beside a neighbour gets a smaller tag rather than one a row away from its foot.
        widths = sorted(
            {
                min(math.ceil(len(text) * PRICE_TAG_CHAR_WIDTH * scaled(geometry, s)) + 2 * pad, W - 2 * SIDE_MARGIN_PX)
                for s in range(PRICE_TAG_SIZE, PRICE_TAG_MIN_SIZE - 1, -1)
            },
            reverse=True,
        )
        found: Box | None = None
        # Below the foot; else hung just above the product, as a shelf price is; else a row lower when a neighbour's
        # tag holds the first one; over the product's own foot (hiding a little of it) only as the last resort.
        for top in (foot + gap, head - gap - h, foot + 2 * gap + h, foot - h - gap):
            for width in widths:
                centred = round((x1 + x2 - width) / 2)
                # Centred first, then slid towards either side while the tag still overlaps the product's own width.
                lefts = [centred + d for k in range(5) for d in ((0,) if k == 0 else (-k * width // 4, k * width // 4))]
                lefts = [
                    x for x in lefts if SIDE_MARGIN_PX <= x <= W - SIDE_MARGIN_PX - width and x < x2 and x + width > x1
                ]
                for left in lefts:
                    box: Box = (left, top, left + width, top + h)
                    if box[1] >= 0 and box[3] <= H and _clear(geometry, [box], taken):
                        found = box
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if found is None:
            issues.append(SceneIssue.of("price_tag_no_room", PRICE_TAG_NO_ROOM_MESSAGE.format(name=product.name), pid))
        else:
            tags.append(PriceTag(found, text, pid))
    return tags, issues


def _promo_banner(
    order: Sequence[str],
    placed: Mapping[str, _Placed],
    by_id: Mapping[str, Product],
    geometry: FrameGeometry,
    blockers: Sequence[Box],
    *,
    tags: Sequence[PriceTag],
) -> PromoBanner | SceneIssue | None:
    """The promotions strip below the products on the desk front, or None when no placed product has one (FR-032).

    Every line is one promotion of the data file with its product's name, whole: the renderer shrinks the text or
    leaves out whole lines, never part of one. The strip's top follows the products' feet, not their lit size, so it
    keeps still while the host talks about one product after another.
    """
    lines = tuple((by_id[pid].name, promo) for pid in order if pid in placed for promo in by_id[pid].promotions)
    if not lines:
        return None
    W, H = geometry.width, geometry.height
    lowest = max([placed[pid].art_box[3] for pid in placed] + [t.box[3] for t in tags])
    top = lowest + scaled(geometry, PROMO_BANNER_GAP_PX)
    bottom = min(H - scaled(geometry, BOTTOM_MARGIN_PX), top + scaled(geometry, PROMO_BANNER_MAX_HEIGHT_PX))
    for zone in blockers:
        if zone[1] > top and zone[0] < W - SIDE_MARGIN_PX and zone[2] > SIDE_MARGIN_PX:
            bottom = min(bottom, zone[1] - 1)
    box: Box = (SIDE_MARGIN_PX, top, W - SIDE_MARGIN_PX, bottom)
    if bottom - top < scaled(geometry, PROMO_BANNER_MIN_HEIGHT_PX) or not _clear(geometry, [box], blockers):
        return SceneIssue.of("promo_banner_no_room", PROMO_BANNER_NO_ROOM_MESSAGE)
    return PromoBanner(box, lines)


def _showcase_cards(
    order: Sequence[str],
    placed: Mapping[str, _Placed],
    by_id: Mapping[str, Product],
    highlight: str | None,
    geometry: FrameGeometry,
    params: LayoutParams,
    blockers: Sequence[Box],
) -> dict[str, Box | Literal["no_room"]]:
    """A card just above each product that wants one (`one`: the spoken product only); "no_room" when it does not fit.

    The cluster fills the desk, so there is seldom room; that is why `none` is the default here.
    """
    if params.cards == "none":
        return {}
    wanted = list(order) if params.cards == "all" else [highlight] if highlight in placed else []
    arts = [p.art_box for p in placed.values()]
    gap = scaled(geometry, CARD_GAP_PX)
    W = geometry.width
    cards: dict[str, Box | Literal["no_room"]] = {}
    taken: list[Box] = []
    for pid in wanted:
        p = placed.get(pid) if pid is not None else None
        if pid is None or p is None:
            continue
        smallest, full = _card_reserve(
            geometry, by_id[pid], highlighted=pid == highlight, show_promotion=params.show_promotion
        )
        x1, top, x2, _ = p.art_box
        width = min(max(x2 - x1, scaled(geometry, CARD_MIN_WIDTH_PX)), W - 2 * SIDE_MARGIN_PX)
        left = min(max(round((x1 + x2 - width) / 2), SIDE_MARGIN_PX), W - SIDE_MARGIN_PX - width)
        found: Box | None = None
        for height in (full, smallest):
            card: Box = (left, top - gap - height, left + width, top - gap)
            if card[1] >= 0 and not any(intersects(card, z) for z in (*blockers, *arts, *taken)):
                found = card
                break
        cards[pid] = "no_room" if found is None else found
        if found is not None:
            taken.append(found)
    return cards


def compute_showcase_layout(
    products: Sequence[Product],
    art_sizes: Mapping[str, tuple[int, int]],
    geometry: FrameGeometry,
    params: LayoutParams,
    highlight: str | None = None,
    *,
    desk_top: float | None = None,
) -> SceneLayout:
    """The main product big in the middle in front of the host, up to three smaller ones behind it (FR-025).

    Same inputs and result type as `compute_layout`. The cluster may cover the hands and the chest, so the hands zone
    is not a blocker here; the face zone, the labels and the frame edges are, for every box that paints anything
    (product, shadow, highlight light, riser, sticker). The highlighted product grows as in `realistic`.
    """
    W, H = geometry.width, geometry.height
    issues: list[SceneIssue] = []
    face_limit = geometry.face_zone[3]
    top = params.desk_top if desk_top is None else desk_top
    desk_y = round(top * H)
    desk_box: Box = (0, desk_y, W, H)
    subtitle_top = max(round(SUBTITLE_TOP * H), face_limit + 4)
    subtitle_box: Box = (
        SUBTITLE_SIDE_PX,
        subtitle_top,
        W - SUBTITLE_SIDE_PX,
        subtitle_top + round(SUBTITLE_HEIGHT * H),
    )
    if desk_y <= face_limit:
        issues.append(
            SceneIssue(
                "error",
                "layout_keep_out",
                f"Mặt bàn ({desk_y}px) chạm vùng mặt ({face_limit}px): không vẽ cảnh; hạ desk_top",
            )
        )
        return SceneLayout((), (), desk_box, subtitle_box, tuple(issues), mode="showcase")
    # Hands are no blocker here, so the geometry carries none: the warm light must not cut them out either.
    geometry = dataclasses.replace(geometry, hands_zone=None)
    blockers = [geometry.face_zone, *geometry.keep_out_boxes()]

    limit = min(params.max_slots, SHOWCASE_MAX_SLOTS)
    order, overflow = station_order(products, limit)
    if overflow:
        issues.append(SceneIssue.of("overflow", f"Quá {limit} sản phẩm, không có chỗ trên bàn: {', '.join(overflow)}"))
    by_id = {p.id: p for p in products}
    if highlight not in order:
        highlight = None
    if params.promo_banner and not any(by_id[pid].promotions for pid in order):
        params = dataclasses.replace(params, promo_banner=False)  # nothing to list: keep the desk's full depth

    # The main product shrinks until every other one stands beside it at nearly its target size; when even the
    # smallest main product leaves too little room, the others shrink together as well.
    main_h, back_scale = SHOWCASE_MAIN_HEIGHT * H, 1.0
    while True:
        attempt = _place_showcase(order, art_sizes, geometry, params, blockers, desk_y, main_h, back_scale)
        crowded = any(attempt.failed.get(pid) == "no_room" for pid in order[1:])
        if not crowded or order[0] not in attempt.placed:
            break
        if main_h * SHOWCASE_MAIN_STEP >= SHOWCASE_MAIN_MIN_HEIGHT * H:
            main_h *= SHOWCASE_MAIN_STEP
        elif back_scale * SHOWCASE_MAIN_STEP >= SHOWCASE_BACK_MIN_SCALE:
            back_scale *= SHOWCASE_MAIN_STEP
        else:
            break
    placed, bottoms, failed, riser_box = attempt.placed, attempt.bottoms, attempt.failed, attempt.riser_box

    if highlight in placed:
        # FR-004 still holds while lit, and so does FR-025: growing stops before it touches another product.
        aw, ah = art_sizes[highlight]
        ahead = _size_cap(highlight, aw / ah, order, placed)
        cap = H if math.isinf(ahead) else round(ahead)
        others = [placed[q].art_box for q in placed if q != highlight]
        scale = params.highlight_scale
        while scale > 1.0 + 1e-9:
            lit_params = dataclasses.replace(params, highlight_scale=scale)
            lit = _lifted(placed[highlight], art_sizes[highlight], geometry, lit_params, blockers, cap)
            # Pushed out beside the main one, a product behind may sit near the frame edge: its light must stay in.
            inside = _clear(geometry, [lit.art_box, lit.shadow_box, glow_box(geometry, lit.art_box)], blockers)
            if inside and not _touches(lit.art_box, others):
                placed[highlight] = lit
                break
            scale -= HIGHLIGHT_STEP

    sticker: Sticker | None = None
    if params.sticker and order and order[0] in placed:
        main_id = order[0]
        product = by_id[main_id]
        if product.price_range[1] <= 0:
            issues.append(
                SceneIssue.of("sticker_no_price", STICKER_NO_PRICE_MESSAGE.format(name=product.name), main_id)
            )
        else:
            others = [placed[q].art_box for q in placed if q != main_id]
            box = _sticker_box(placed[main_id].art_box, geometry, [*blockers, *others])
            if box is None:
                issues.append(
                    SceneIssue.of("sticker_no_room", STICKER_NO_ROOM_MESSAGE.format(name=product.name), main_id)
                )
            else:
                sticker = Sticker(box, price_text(product), main_id)

    price_tags: list[PriceTag] = []
    if params.price_tags:
        skip = sticker.product_id if sticker else None
        extra_blockers = [*blockers, *([sticker.box] if sticker else [])]
        price_tags, tag_issues = _price_tags(order, placed, by_id, geometry, extra_blockers, skip)
        issues.extend(tag_issues)
    banner: PromoBanner | None = None
    if params.promo_banner and placed:
        found = _promo_banner(order, placed, by_id, geometry, blockers, tags=price_tags)
        if isinstance(found, SceneIssue):
            issues.append(found)
        else:
            banner = found

    extra = [
        *([sticker.box] if sticker else []),
        *([riser_box] if riser_box else []),
        *(t.box for t in price_tags),
        *([banner.box] if banner else []),
    ]
    cards = _showcase_cards(order, placed, by_id, highlight, geometry, params, [*blockers, subtitle_box, *extra])

    slots: list[Slot] = []
    for pid in order:
        p = placed.get(pid)
        card = cards.get(pid)
        if card == "no_room":
            issues.append(SceneIssue.of("card_no_room", CARD_NO_ROOM_MESSAGE.format(name=by_id[pid].name), pid))
        if failed.get(pid) == "too_wide":
            aw, ah = art_sizes[pid]
            issues.append(SceneIssue.of("art_too_wide", f"{TOO_WIDE_MESSAGE.format(pid=pid)} ({aw}×{ah})", pid))
        elif pid in failed:
            issues.append(SceneIssue.of("no_room", f"Không còn chỗ cho ảnh {pid} trên bàn trưng bày", pid))
        if p is not None:
            x_center, width = (p.art_box[0] + p.art_box[2]) // 2, p.art_box[2] - p.art_box[0]
        else:
            x_center, width = W // 2, 0
        # A product behind may end up on either side of the main one: name its station after where it stands.
        if pid == order[0]:
            side = "middle"
        elif p is None:
            side = SHOWCASE_BACK[order.index(pid) - 1][0]
        else:
            side = "right" if x_center >= W / 2 else "left"
        slots.append(
            Slot(
                pid,
                x_center,
                width,
                p.art_box if p else None,
                card if isinstance(card, tuple) else None,
                pid == highlight,
                by_id[pid].is_primary,
                station=f"showcase_{side}",
                shadow_box=p.shadow_box if p else None,
            )
        )
    # Far first; on the same depth the earlier product is the nearer one, so it is painted later.
    draw_order = tuple(sorted(order, key=lambda pid: (bottoms[pid], -order.index(pid))))
    return SceneLayout(
        tuple(slots),
        tuple(overflow),
        desk_box,
        subtitle_box,
        tuple(issues),
        mode="showcase",
        draw_order=draw_order,
        riser_box=riser_box,
        sticker=sticker,
        price_tags=tuple(price_tags),
        promo_banner=banner,
    )


def low_resolution_issues(
    layout: SceneLayout, products: Sequence[Product], art_sizes: Mapping[str, tuple[int, int]], params: LayoutParams
) -> list[SceneIssue]:
    """`art_low_resolution` for each drawn product whose picture is too small for its lit size (FR-028).

    A product that is not lit now is judged at its size grown by `highlight_scale`, so the warning does not come and
    go with each sentence. A picture already at `ART_MAX_SIDE` is not flagged: a bigger upload would be shrunk to it.
    """
    by_id = {p.id: p for p in products}
    out: list[SceneIssue] = []
    for slot in layout.slots:
        size = art_sizes.get(slot.product_id)
        if slot.art_box is None or size is None or max(size) >= ART_MAX_SIDE:
            continue
        height = slot.art_box[3] - slot.art_box[1]
        drawn = height if slot.highlighted else round(height * params.highlight_scale)
        if size[1] < LOW_RES_FACTOR * drawn:
            product = by_id.get(slot.product_id)
            name = product.name if product else slot.product_id
            message = LOW_RES_MESSAGE.format(name=name, src=size[1], drawn=drawn)
            out.append(SceneIssue.of("art_low_resolution", message, slot.product_id))
    return out


def compute_scene_layout(
    products: Sequence[Product],
    art_sizes: Mapping[str, tuple[int, int]],
    geometry: FrameGeometry,
    params: LayoutParams,
    highlight: str | None = None,
    *,
    desk_top: float | None = None,
) -> SceneLayout:
    """The layout `params.mode` asks for (009 rows, 013 realistic desk or showcase), with the FR-028 warnings."""
    compute = {"realistic": compute_realistic_layout, "showcase": compute_showcase_layout}.get(
        params.mode, compute_layout
    )
    layout = compute(products, art_sizes, geometry, params, highlight, desk_top=desk_top)
    low = low_resolution_issues(layout, products, art_sizes, params)
    return dataclasses.replace(layout, issues=(*layout.issues, *low)) if low else layout
