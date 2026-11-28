"""009 T011, T028: where products and cards go; nothing ever reaches the face, the "AI" label or the watermark."""

from __future__ import annotations

import pytest

from ai_live.core.config import AI_LABEL_DEFAULT_POSITION, AI_LABEL_POSITIONS
from ai_live.scene.fonts import SceneFontError, SceneFonts, load_fonts
from ai_live.scene.layout import (
    ELLIPSIS,
    MAX_LINES,
    art_fit,
    card_text,
    compute_layout,
    estimate_geometry,
    estimate_label_box,
    label_lines,
    price_text,
    slot_order,
)
from ai_live.scene.models import FrameGeometry, LayoutParams, intersects
from fixtures.scene_builder import catalog, demo_catalog, product

POSITIONS = AI_LABEL_POSITIONS
ART = (120, 240)


@pytest.fixture(scope="module")
def fonts() -> SceneFonts:
    try:
        return load_fonts(None)
    except SceneFontError:
        pytest.skip("no font with Vietnamese diacritics on this machine")


def _sizes(products) -> dict[str, tuple[int, int]]:
    return {p.id: ART for p in products}


def _boxes(layout):
    for slot in layout.slots:
        if slot.art_box is not None:
            yield slot.product_id, slot.art_box
        yield slot.product_id, slot.card_box


def test_primary_in_the_middle_and_secondary_keep_file_order() -> None:
    products = [product("s1"), product("s2"), product("p", primary=True), product("s3"), product("s4")]
    order, overflow = slot_order(products, 5)
    assert order == ["s1", "s2", "p", "s3", "s4"]
    assert overflow == []
    products = [product("p", primary=True), product("s1"), product("s2")]
    assert slot_order(products, 5) == (["s1", "p", "s2"], [])


def test_overflow_beyond_max_slots() -> None:
    products = [product("p", primary=True), *[product(f"s{i}") for i in range(6)]]
    layout = compute_layout(products, _sizes(products), estimate_geometry("AI", "top-right"), LayoutParams())
    assert len(layout.slots) == 5
    assert layout.overflow == ("s4", "s5")
    assert [i.level for i in layout.issues if i.code == "overflow"] == ["warning"]
    assert layout.slot("p") is not None and layout.slot("p").primary


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("highlight", [None, "sua-rua-mat", "kem-chong-nang", "toner"])
def test_every_box_stays_out_of_keep_out_zones(position: str, highlight: str | None) -> None:
    geometry = estimate_geometry("AI", position)
    products = demo_catalog().products
    layout = compute_layout(products, _sizes(products), geometry, LayoutParams(), highlight)
    assert layout.drawable and not layout.issues
    face_limit = geometry.face_zone[3]
    for pid, box in _boxes(layout):
        assert box[1] >= face_limit, (pid, box)
        assert 0 <= box[0] and box[2] <= geometry.width and box[3] <= geometry.height, (pid, box)
        for keep in geometry.keep_out_boxes():
            assert not intersects(box, keep), (pid, box, keep)


@pytest.mark.parametrize("scale", [1.0, 1.3, 1.6])
def test_highlighted_product_scaled_stays_below_face(scale: float) -> None:
    # The real fork frame puts the chin lower than the estimate.
    geometry = estimate_geometry("AI", "top-right", face_bottom=420)
    products = demo_catalog().products
    layout = compute_layout(products, _sizes(products), geometry, LayoutParams(highlight_scale=scale), "kem-chong-nang")
    slot = layout.slot("kem-chong-nang")
    assert slot is not None and slot.highlighted and slot.art_box is not None
    assert slot.art_box[1] >= geometry.face_zone[3]


def test_highlight_makes_the_product_bigger() -> None:
    geometry = estimate_geometry("AI", "top-right")
    products = demo_catalog().products
    plain = compute_layout(products, _sizes(products), geometry, LayoutParams())
    lit = compute_layout(products, _sizes(products), geometry, LayoutParams(), "toner")
    height = lambda layout: layout.slot("toner").art_box[3] - layout.slot("toner").art_box[1]  # noqa: E731
    assert height(lit) > height(plain)
    assert lit.slot("toner").width > plain.slot("toner").width


def test_unknown_highlight_is_ignored() -> None:
    products = demo_catalog().products
    layout = compute_layout(products, _sizes(products), estimate_geometry("AI", "top-right"), LayoutParams(), "gone")
    assert not any(s.highlighted for s in layout.slots)


def test_low_desk_against_face_is_not_drawable() -> None:
    geometry = estimate_geometry("AI", "top-right", face_bottom=700)
    products = demo_catalog().products
    layout = compute_layout(products, _sizes(products), geometry, LayoutParams())
    assert not layout.drawable
    assert layout.slots == ()
    assert [i.level for i in layout.issues if i.code == "layout_keep_out"] == ["error"]


def test_no_room_for_art_shows_card_only() -> None:
    # A very flat picture in a narrow slot would be a smudge a few pixels high.
    geometry = estimate_geometry("AI", "top-right")
    products = demo_catalog().products
    layout = compute_layout(products, {p.id: (600, 40) for p in products}, geometry, LayoutParams())
    assert layout.drawable
    assert all(s.art_box is None for s in layout.slots)
    # The slot is too narrow, not the face too low: its own warning since 012 T071 (FR-004a).
    assert {(i.level, i.code) for i in layout.issues} == {("warning", "art_too_wide")}


def test_product_without_picture_has_card_only() -> None:
    products = demo_catalog().products
    sizes = {"kem-chong-nang": ART}
    layout = compute_layout(products, sizes, estimate_geometry("AI", "top-right"), LayoutParams())
    assert layout.slot("toner").art_box is None
    assert layout.slot("kem-chong-nang").art_box is not None


def test_price_text_single_and_range() -> None:
    assert price_text(product("x", price=159_000)) == "159.000đ"
    assert price_text(product("y", variants=(("50 ml", 250_000), ("100 ml", 420_000)))) == "250.000đ – 420.000đ"


def test_long_name_is_cut_to_two_lines_with_ellipsis(fonts: SceneFonts) -> None:
    name = "Kem chống nắng dưỡng ẩm nâng tông kiềm dầu siêu mỏng nhẹ dành cho mọi loại da nhạy cảm"
    text = card_text(product("x", name=name), 120, fonts, FrameGeometry())
    assert len(text.name_lines) == MAX_LINES
    assert text.name_lines[-1].endswith(ELLIPSIS)
    # Every word shown is the file's own, in order.
    shown = " ".join(text.name_lines).removesuffix(ELLIPSIS).split()
    assert shown == name.split()[: len(shown)]


def test_short_name_is_whole(fonts: SceneFonts) -> None:
    text = card_text(product("x", name="Toner Z"), 140, fonts, FrameGeometry())
    assert text.name_lines == ("Toner Z",)


def test_number_is_never_split(fonts: SceneFonts) -> None:
    text = card_text(product("x", name="SPF 50000000000000000000000000"), 60, fonts, FrameGeometry())
    for line in text.name_lines:
        assert "5" not in line or "50000000000000000000000000" in line


def test_price_range_wraps_on_narrow_card(fonts: SceneFonts) -> None:
    p = product("y", variants=(("50 ml", 250_000), ("100 ml", 1_420_000)))
    text = card_text(p, 70, fonts, FrameGeometry())
    assert text.price_lines == ("250.000đ –", "1.420.000đ")


def test_promotion_only_on_the_highlighted_card(fonts: SceneFonts) -> None:
    p = demo_catalog().products[1]
    lit = card_text(p, 200, fonts, FrameGeometry(), highlighted=True)
    plain = card_text(p, 200, fonts, FrameGeometry(), highlighted=False)
    off = card_text(p, 200, fonts, FrameGeometry(), highlighted=True, show_promotion=False)
    assert " ".join(lit.promotion_lines) == p.promotions[0]
    assert plain.promotion_lines == () and off.promotion_lines == ()


def test_promotion_too_long_is_left_out_not_cut(fonts: SceneFonts) -> None:
    long = "Giảm 30.000đ cho đơn từ 500.000đ áp dụng cho khách hàng mới đăng ký thành viên trong tuần lễ vàng"
    text = card_text(product("x", promotions=(long,)), 90, fonts, FrameGeometry(), highlighted=True)
    assert text.promotion_lines == ()


def test_single_product_catalog() -> None:
    products = catalog(product("only", primary=True)).products
    layout = compute_layout(products, _sizes(products), estimate_geometry("AI", "top-right"), LayoutParams())
    assert [s.product_id for s in layout.slots] == ["only"]


@pytest.mark.parametrize("position", ["top-left", "top-right", "bottom-left", "bottom-right"])
@pytest.mark.parametrize("text", ["AI-GENERATED CONTENT", "THIS LIVE HOST IS AN AI-GENERATED AVATAR AND VOICE"])
def test_a_long_label_estimate_stays_inside_the_frame(text, position):
    # The fork shrinks a label wider than the frame (ADR-065); the estimate must not reach past the edges either.
    x1, y1, x2, y2 = estimate_label_box(480, 832, text, position)
    assert 12 <= x1 < x2 <= 480 - 12
    assert 0 <= y1 < y2 <= 832


# ---------- 011 T016: the desk is part of the character image ----------


def test_character_desk_top_replaces_the_scene_json_one() -> None:
    geometry = estimate_geometry("AI", "top-right")
    products = demo_catalog().products
    from_json = compute_layout(products, _sizes(products), geometry, LayoutParams(desk_top=0.76))
    layout = compute_layout(products, _sizes(products), geometry, LayoutParams(desk_top=0.76), desk_top=0.84)
    same = compute_layout(products, _sizes(products), geometry, LayoutParams(desk_top=0.84))
    assert layout.drawable and not layout.issues
    assert layout.desk_box == same.desk_box and layout.desk_box[1] > from_json.desk_box[1]
    desk_y = layout.desk_box[1]
    # Products stand on that edge and their cards sit on the desk below it.
    for slot in layout.slots:
        if slot.art_box is not None:
            assert slot.art_box[3] >= desk_y, slot
        assert slot.card_box[1] >= desk_y, slot


def test_character_desk_top_touching_the_face_still_blocks() -> None:
    geometry = estimate_geometry("AI", "top-right")
    products = demo_catalog().products
    touching = (geometry.face_zone[3] - 10) / geometry.height
    layout = compute_layout(products, _sizes(products), geometry, LayoutParams(desk_top=0.76), desk_top=touching)
    assert not layout.drawable
    assert [i.code for i in layout.issues] == ["layout_keep_out"]


# 012 T071 (FR-004a): a picture too wide for its slot is dropped with its own reason, and `art_fit` says so up front.
WIDE = (1600, 300)  # 5.3:1, too flat even for the bigger highlighted slot
FLAT = (600, 200)  # 3:1, fits only the highlighted slot


def test_a_too_wide_picture_says_so_instead_of_blaming_the_face() -> None:
    geometry = estimate_geometry("AI", "top-right")
    products = demo_catalog().products
    sizes = {**_sizes(products), "toner": WIDE}
    layout = compute_layout(products, sizes, geometry, LayoutParams())
    assert layout.slot("toner").art_box is None
    toner = [i for i in layout.issues if i.product_id == "toner"]
    assert [(i.level, i.code) for i in toner] == [("warning", "art_too_wide")]
    assert "rộng" in toner[0].message and "vùng mặt" not in toner[0].message
    assert all(i.code != "layout_keep_out" for i in layout.issues)


@pytest.mark.parametrize(("size", "fit"), [(ART, "shown"), (FLAT, "highlight_only"), (WIDE, "card_only")])
def test_art_fit_tells_when_a_picture_will_show(size, fit) -> None:
    geometry = estimate_geometry("AI", "top-right")
    products = demo_catalog().products
    assert art_fit(products, "toner", size, geometry, LayoutParams()) == fit


def test_art_fit_of_a_product_without_a_slot_is_shown() -> None:
    products = [product("p", primary=True), *[product(f"s{i}") for i in range(6)]]
    geometry = estimate_geometry("AI", "top-right")
    assert art_fit(products, "s5", WIDE, geometry, LayoutParams()) == "shown"


# ---------- 013 T010: the hands zone of the frame (data-model §3, research R2) ----------

_HANDS = (0.27, 0.74, 0.73, 1.0)


def test_hands_zone_fractions_become_pixels() -> None:
    plain = FrameGeometry(width=832, height=832)
    assert plain.hands_zone is None
    geometry = plain.with_hands_zone(_HANDS)
    assert geometry.hands_zone == (round(0.27 * 832), round(0.74 * 832), round(0.73 * 832), 832)
    wide = FrameGeometry(width=1080, height=1920).with_hands_zone(_HANDS)
    assert wide.hands_zone == (round(0.27 * 1080), round(0.74 * 1920), round(0.73 * 1080), 1920)
    assert geometry.with_hands_zone(None).hands_zone is None


def test_hands_zone_change_means_a_new_frame() -> None:
    plain = FrameGeometry()
    assert not plain.with_hands_zone(_HANDS).same_frame(plain)
    assert not plain.with_hands_zone(_HANDS).same_frame(plain.with_hands_zone((0.2, 0.7, 0.8, 1.0)))
    assert plain.with_hands_zone(_HANDS).same_frame(plain.with_hands_zone(_HANDS))


def test_hands_zone_is_not_a_keep_out_and_is_not_punched() -> None:
    from PIL import Image

    from ai_live.scene.render import punch

    geometry = FrameGeometry(width=400, height=400, face_bottom=100).with_hands_zone(_HANDS)
    assert geometry.hands_zone is not None
    assert geometry.hands_zone not in geometry.keep_out_boxes()
    assert geometry.keep_out_boxes() == FrameGeometry(width=400, height=400, face_bottom=100).keep_out_boxes()
    layer = Image.new("RGBA", (400, 400), (200, 100, 50, 255))
    punch(layer, geometry)
    x1, y1, x2, y2 = geometry.hands_zone
    assert layer.getpixel(((x1 + x2) // 2, (y1 + y2) // 2))[3] == 255
    assert layer.getpixel((x1, y2 - 1))[3] == 255


# ---------- 014 T068: `shopee-top`, the label below the Shopee app's title band (ADR-085) ----------

# Boxes the fork's `label_box` gives for the default label with Bahnschrift Bold Condensed (ADR-089, measured
# 2026-11-25; Segoe UI Black gave (177, 104, 302, 150) on 480x832 before).
FORK_SHOPEE_TOP = {
    (480, 832): (183, 104, 297, 158),
    (1080, 1920): (407, 240, 673, 369),
    (360, 640): (135, 80, 224, 122),
}


def test_default_is_one_line_top_center_and_shopee_top_stays_selectable():
    # ADR-090: the Meet demo uses one large line; `shopee-top` is for Shopee via OBS.
    assert "shopee-top" in AI_LABEL_POSITIONS
    assert AI_LABEL_DEFAULT_POSITION == "top-center"
    lines, _ = label_lines(480, 832, "AI-GENERATED CONTENT", AI_LABEL_DEFAULT_POSITION)
    assert lines == ("AI-GENERATED CONTENT",)


@pytest.mark.parametrize("size", list(FORK_SHOPEE_TOP))
def test_shopee_top_estimate_covers_what_the_fork_draws(size):
    width, height = size
    x1, y1, x2, y2 = estimate_label_box(width, height, "AI-GENERATED CONTENT", "shopee-top")
    fx1, fy1, fx2, fy2 = FORK_SHOPEE_TOP[size]
    assert x1 <= fx1 and y1 <= fy1 and x2 >= fx2 and y2 >= fy2
    assert y1 == round(height * 0.125)
    assert x2 - x1 <= round(width * 0.26) and abs((x1 + x2) - width) <= 1
    assert y2 - fy2 <= 0.01 * height  # generous, not a different place
    assert y2 <= round(height * 0.195)  # above the host's head (~19.6% of the frame height)


def test_shopee_top_keeps_a_short_label_on_one_line():
    lines, px = label_lines(480, 832, "AI", "shopee-top")
    assert lines == ("AI",) and px == pytest.approx(832 * 0.031)
    lines, _ = label_lines(480, 832, "AI-GENERATED CONTENT", "shopee-top")
    assert lines == ("AI-GENERATED", "CONTENT")
    lines, _ = label_lines(480, 832, "AI-GENERATED CONTENT", "top-center")
    assert lines == ("AI-GENERATED CONTENT",)
