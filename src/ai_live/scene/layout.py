"""Where everything goes in the frame (research R4). Pure: the same inputs always give the same boxes.

The frame from top to bottom: the host's face (never covered, FR-005/FR-006), a band where subtitles may go, the
products standing on the desk, and the name/price cards on the front of the desk. Every product of the file gets a
place (FR-007): the primary one in the middle and bigger, the secondary ones in file order around it, the one being
spoken about bigger still (FR-015).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import ImageFont

from ai_live.brain.prompt import format_price
from ai_live.products.models import Product
from ai_live.scene.fonts import SceneFonts
from ai_live.scene.models import (
    WATERMARK_BOX,
    Box,
    CardText,
    FrameGeometry,
    KeepOut,
    LayoutParams,
    SceneIssue,
    SceneLayout,
    Slot,
    intersects,
)

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

# The "AI" label as the fork draws it (vendor/livetalking/ailive_ext/label.py): used until the fork reports the real
# box in `hello.scene`, and in still-image mode so the scene does not move when a session falls back to it.
LABEL_MARGIN_PX = 12
LABEL_TEXT_RATIO = 0.036
LABEL_PAD_RATIO = 0.45
LABEL_CHAR_RATIO = 0.75  # generous: Hershey simplex averages ~0.53 of the text height per character


def estimate_label_box(width: int, height: int, text: str, position: str) -> Box:
    text_h = max(10.0, height * LABEL_TEXT_RATIO)
    pad = max(4, round(text_h * LABEL_PAD_RATIO))
    box_w = round(len(text) * text_h * LABEL_CHAR_RATIO) + 2 * pad
    box_h = round(text_h) + 2 * pad + 1
    x1 = LABEL_MARGIN_PX if position.endswith("left") else width - LABEL_MARGIN_PX - box_w
    y1 = LABEL_MARGIN_PX if position.startswith("top") else height - LABEL_MARGIN_PX - box_h
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
) -> SceneLayout:
    """Boxes for the desk, each product and its card. `art_sizes` is (w, h) of each product's picture."""
    W, H = geometry.width, geometry.height
    issues: list[SceneIssue] = []
    face_limit = geometry.face_zone[3]
    bottom = H - BOTTOM_MARGIN_PX
    shift = _bottom_shift(geometry, bottom)
    desk_y = round(params.desk_top * H) - shift
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
            if w > room:
                w, h = room, room * ah / aw
            if h < MIN_ART_HEIGHT * H:
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
