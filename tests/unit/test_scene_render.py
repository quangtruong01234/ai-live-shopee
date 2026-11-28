"""009 T012, T028: the drawn layers. Transparent where the face, the "AI" label and the watermark are; fast enough."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import pytest
from PIL import Image

from ai_live.scene.fonts import SceneFontError, SceneFonts, load_fonts
from ai_live.scene.layout import REALISTIC_DIM, card_text, compute_layout, estimate_geometry, glow_box, price_text
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import FrameGeometry, LayoutParams, SceneLayer, SceneSet
from ai_live.scene.render import compose_still, render_base, render_subtitle
from fixtures.scene_builder import CUSTOMER, demo_catalog, make_scene_dir
from fixtures.scene_builder import product as make_product

POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")
PRODUCTS = {p.id: p for p in demo_catalog().products}


@pytest.fixture(scope="module")
def fonts() -> SceneFonts:
    try:
        return load_fonts(None)
    except SceneFontError:
        pytest.skip("no font with Vietnamese diacritics on this machine")


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> SceneSet:
    root = make_scene_dir(tmp_path_factory.mktemp("scene") / "demo", list(PRODUCTS))
    loaded = load_scene_set(root, list(PRODUCTS), customer_id=CUSTOMER)
    assert loaded.issues == ()
    return loaded


def _render(scene: SceneSet, fonts: SceneFonts, geometry: FrameGeometry, highlight: str | None = None, params=None):
    params = params or scene.layout
    sizes = {pid: art.image.size for pid, art in scene.art.items()}
    layout = compute_layout(list(PRODUCTS.values()), sizes, geometry, params, highlight)
    return layout, render_base(scene, layout, PRODUCTS, geometry, fonts)


def _frame(layer: SceneLayer, geometry: FrameGeometry) -> Image.Image:
    """The layer placed on a transparent full frame."""
    frame = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    if layer.image is not None:
        frame.alpha_composite(layer.image, (layer.x, layer.y))
    return frame


def _clear(frame: Image.Image, box: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = box
    region = frame.crop((max(0, x1), max(0, y1), min(frame.width, x2), min(frame.height, y2)))
    return region.getchannel("A").getextrema()[1] == 0


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("highlight", [None, "kem-chong-nang", "toner"])
def test_base_is_rgba_and_clear_in_keep_out_zones(scene, fonts, position: str, highlight: str | None) -> None:
    geometry = estimate_geometry("AI", position)
    _, layer = _render(scene, fonts, geometry, highlight)
    assert layer.name == "base" and layer.image is not None and layer.image.mode == "RGBA"
    assert layer.png and layer.png.startswith(b"\x89PNG")
    frame = _frame(layer, geometry)
    assert _clear(frame, geometry.face_zone)
    for box in geometry.keep_out_boxes():
        assert _clear(frame, box), box
    # The desk is drawn edge to edge at the bottom.
    assert frame.getpixel((geometry.width // 2, geometry.height - 2))[3] == 255


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("desk_top", [0.55, 0.65, 0.76, 0.85, 0.92])
@pytest.mark.parametrize("scale", [1.0, 1.6])
@pytest.mark.parametrize("max_slots", [1, 3, 7])
def test_any_valid_scene_json_leaves_the_ai_label_clear(
    scene, fonts, position: str, desk_top: float, scale: float, max_slots: int
) -> None:
    # FR-020: whatever a valid scene.json says, the label box stays untouched (and the face too, FR-006).
    geometry = estimate_geometry("AI", position)
    params = LayoutParams(desk_top=desk_top, max_slots=max_slots, highlight_scale=scale)
    _, layer = _render(scene, fonts, geometry, "kem-chong-nang", params)
    frame = _frame(layer, geometry)
    for box in [geometry.face_zone, *geometry.keep_out_boxes()]:
        assert _clear(frame, box), box


def test_fork_geometry_is_respected(scene, fonts) -> None:
    geometry = estimate_geometry("Trợ lý AI", "bottom-left", face_bottom=430)
    _, layer = _render(scene, fonts, geometry, "toner")
    frame = _frame(layer, geometry)
    for box in [geometry.face_zone, *geometry.keep_out_boxes()]:
        assert _clear(frame, box), box


def test_vietnamese_diacritics_are_drawn(fonts) -> None:
    font = fonts.get(30)
    # A font without these glyphs draws the same box (or nothing) for each: the stacked marks make them taller.
    assert font.getbbox("Ự")[1] < font.getbbox("U")[1] or font.getbbox("Ự")[3] > font.getbbox("U")[3]
    assert font.getmask("Đ").getbbox() is not None
    assert font.getbbox("Ắ")[1] < font.getbbox("A")[1]


def test_render_is_fast(scene, fonts) -> None:
    geometry = estimate_geometry("AI", "top-right")
    _render(scene, fonts, geometry)  # warm the font cache, as the controller does at start
    started = time.perf_counter()
    _render(scene, fonts, geometry, "kem-chong-nang")
    assert (time.perf_counter() - started) * 1000 < 300


def test_still_is_the_frame_size(scene, fonts) -> None:
    geometry = estimate_geometry("AI", "top-right")
    layout, base = _render(scene, fonts, geometry)
    subtitle = render_subtitle("Dạ chị ơi, kem này thấm nhanh lắm ạ.", layout, geometry, fonts)
    face = Image.new("RGB", (geometry.width, geometry.height), (90, 90, 90))
    still = compose_still(face, [base, subtitle, None])
    assert still.size == (480, 832) and still.mode == "RGB"
    # The face stays untouched.
    assert still.getpixel((240, 100)) == (90, 90, 90)


def test_cards_show_no_number_outside_the_file(fonts) -> None:
    geometry = estimate_geometry("AI", "top-right")
    for product in PRODUCTS.values():
        for width, lit in [(90, False), (140, True), (220, True)]:
            text = card_text(product, width, fonts, geometry, highlighted=lit)
            allowed = " ".join([product.name, price_text(product), *product.promotions])
            shown = " ".join([*text.name_lines, *text.price_lines, *text.promotion_lines])
            for number in re.findall(r"\d[\d.]*", shown):
                assert number.rstrip(".") in allowed, (product.id, number, shown)


def test_others_are_dimmed_while_one_is_highlighted(scene, fonts) -> None:
    geometry = estimate_geometry("AI", "top-right")
    plain_layout, plain = _render(scene, fonts, geometry)
    lit_layout, lit = _render(scene, fonts, geometry, "kem-chong-nang")
    other = lit_layout.slot("toner").art_box
    point = ((other[0] + other[2]) // 2, (other[1] + other[3]) // 2)
    before = plain_layout.slot("toner").art_box
    point_before = ((before[0] + before[2]) // 2, (before[1] + before[3]) // 2)
    assert sum(_frame(lit, geometry).getpixel(point)[:3]) < sum(_frame(plain, geometry).getpixel(point_before)[:3])


def test_subtitle_layer_is_inside_its_box_and_clear_of_face(scene, fonts) -> None:
    geometry = estimate_geometry("AI", "top-right")
    layout, _ = _render(scene, fonts, geometry)
    long = "Dạ kem chống nắng Mây Sáng có hai dung tích là năm mươi mi li và một trăm mi li, " * 3
    layer = render_subtitle(long, layout, geometry, fonts)
    assert layer.image is not None
    x1, y1, x2, _ = layout.subtitle_box
    assert layer.x >= x1 and layer.x + layer.image.width <= x2 and layer.y >= y1
    assert _clear(_frame(layer, geometry), geometry.face_zone)


def test_empty_subtitle_clears(scene, fonts) -> None:
    geometry = estimate_geometry("AI", "top-right")
    layout, _ = _render(scene, fonts, geometry)
    assert render_subtitle("   ", layout, geometry, fonts).image is None


def test_undrawable_layout_gives_empty_base(scene, fonts) -> None:
    geometry = estimate_geometry("AI", "top-right", face_bottom=700)
    _, layer = _render(scene, fonts, geometry)
    assert layer.image is None


def test_scene_without_desk_or_art_still_draws_cards(tmp_path: Path, fonts) -> None:
    root = make_scene_dir(tmp_path / "bare", [], desk=False)
    bare = load_scene_set(root, list(PRODUCTS), customer_id=CUSTOMER)
    geometry = estimate_geometry("AI", "top-right")
    _, layer = _render(bare, fonts, geometry)
    assert layer.image is not None
    assert _clear(_frame(layer, geometry), geometry.face_zone)


# ---------- 011 T017: a desk drawn in the character image ----------


def _desk_strip(layout, geometry: FrameGeometry) -> tuple[int, int, int, int]:
    # The left margin of the desk area: only the desk layer ever draws there.
    x1, y1, _, y2 = layout.desk_box
    return x1, y1, x1 + 4, min(y2, geometry.height - 40)


def test_desk_in_image_draws_no_desk_but_keeps_cards_and_highlight(scene, fonts) -> None:
    geometry = estimate_geometry("AI", "top-right")
    sizes = {pid: art.image.size for pid, art in scene.art.items()}
    layout = compute_layout(list(PRODUCTS.values()), sizes, geometry, scene.layout, "toner")
    with_desk = _frame(render_base(scene, layout, PRODUCTS, geometry, fonts), geometry)
    assert not _clear(with_desk, _desk_strip(layout, geometry))
    layer = render_base(scene, layout, PRODUCTS, geometry, fonts, desk_in_image=True)
    frame = _frame(layer, geometry)
    assert _clear(frame, _desk_strip(layout, geometry))
    for slot in layout.slots:
        assert not _clear(frame, slot.card_box), slot.product_id
    highlighted = layout.slot("toner")
    assert highlighted is not None and highlighted.highlighted and highlighted.art_box is not None
    assert not _clear(frame, highlighted.art_box)
    assert _clear(frame, geometry.face_zone)


# ---------- 013 T018: a scene set without `mode` draws exactly as 009 (US1 #6, FR-001) ----------

# sha256 of the base layer's raw RGBA bytes, recorded with the 009 `render.py` before 013 touched it. Glyph pixels
# depend on the font file, so the check runs only with the font these were recorded with.
GOLDEN_FONT = "segoeuib.ttf"
GOLDEN_ROWS = {
    None: ((0, 519, 480, 313), "5359ac5bd81269e6dc3546b323e9fc5b3c59d2b21423ac94c95837ab5259d1fc"),
    "toner": ((0, 477, 480, 355), "872023a733ed0afb489f5a9670116d8cd1d31e1c824f343ab9dd4e9d383857a3"),
}


@pytest.fixture(scope="module")
def rows4(tmp_path_factory: pytest.TempPathFactory) -> tuple[SceneSet, dict]:
    products = dict(PRODUCTS)
    products["serum"] = make_product("serum", name="Serum Sáng Da", price=320_000)
    root = make_scene_dir(tmp_path_factory.mktemp("rows4") / "demo", list(products))
    return load_scene_set(root, list(products), customer_id=CUSTOMER), products


@pytest.mark.parametrize("highlight", [None, "toner"])
def test_rows_scene_without_mode_draws_byte_for_byte_as_009(rows4, fonts, highlight: str | None) -> None:
    if fonts.bold.name.lower() != GOLDEN_FONT:
        pytest.skip(f"golden hashes were recorded with {GOLDEN_FONT}, this machine uses {fonts.bold.name}")
    scene, products = rows4
    assert scene.layout.mode == "rows"
    geometry = estimate_geometry("AI", "top-right")
    sizes = {pid: art.image.size for pid, art in scene.art.items()}
    layout = compute_layout(list(products.values()), sizes, geometry, scene.layout, highlight)
    layer = render_base(scene, layout, products, geometry, fonts)
    (x, y, w, h), digest = GOLDEN_ROWS[highlight]
    assert layer.image is not None and (layer.x, layer.y, *layer.image.size) == (x, y, w, h)
    assert hashlib.sha256(layer.image.tobytes()).hexdigest() == digest


# ---------- 013 T018: realistic desk (FR-005, FR-006, FR-008, FR-009, US1 #5, #7) ----------

HANDS = (0.30, 0.77, 0.70, 1.0)
REALISTIC = {"mode": "realistic", "desk_top": 0.868, "max_slots": 5, "highlight_scale": 1.04, "cards": "none"}
TWO = {"kem-chong-nang": PRODUCTS["kem-chong-nang"], "toner": PRODUCTS["toner"]}


def _realistic_scene(root: Path, products: dict, **layout) -> SceneSet:
    scene_dir = make_scene_dir(root, list(products), scene={"layout": {**REALISTIC, **layout}})
    loaded = load_scene_set(scene_dir, list(products), customer_id=CUSTOMER)
    assert loaded.layout.mode == "realistic", loaded.issues
    return loaded


def _realistic(scene: SceneSet, products: dict, fonts: SceneFonts, *, desk_in_image: bool = True, highlight=None):
    from ai_live.scene.layout import compute_realistic_layout

    geometry = estimate_geometry("AI", "top-right").with_hands_zone(HANDS)
    sizes = {pid: art.image.size for pid, art in scene.art.items()}
    layout = compute_realistic_layout(list(products.values()), sizes, geometry, scene.layout, highlight)
    layer = render_base(scene, layout, products, geometry, fonts, desk_in_image=desk_in_image)
    return geometry, layout, _frame(layer, geometry)


def _dark_run(frame: Image.Image, x: int, y: int) -> tuple[int, int]:
    """First and last x of the run of shadow pixels on row `y` that contains `x`."""

    def dark(px: int) -> bool:
        p = frame.getpixel((px, y))
        return p[3] > 8 and max(p[:3]) < 60

    left = right = x
    while left > 0 and dark(left - 1):
        left -= 1
    while right < frame.width - 1 and dark(right + 1):
        right += 1
    return left, right


def _union(*boxes) -> tuple[int, int, int, int]:
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def test_realistic_draws_a_soft_shadow_under_each_product_as_wide_as_it(tmp_path: Path, fonts) -> None:
    scene = _realistic_scene(tmp_path / "s", TWO)
    _, layout, frame = _realistic(scene, TWO, fonts)
    widths = {}
    for slot in layout.slots:
        assert slot.art_box is not None and slot.shadow_box is not None, slot.product_id
        x1, _, x2, y2 = slot.art_box
        below = frame.getpixel(((x1 + x2) // 2, y2 + 1))
        assert below[3] > 0 and max(below[:3]) < 60, (slot.product_id, below)  # a dark, see-through shadow
        left, right = _dark_run(frame, (x1 + x2) // 2, y2 + 1)
        assert left >= slot.shadow_box[0] and right < slot.shadow_box[2], (slot.shadow_box, left, right)
        widths[slot.product_id] = (right - left, x2 - x1)
        # The soft layer is wider than the product (research R3: 1.25 w), not just a line under it.
        assert right - left >= 1.1 * (x2 - x1), (slot.product_id, right - left, x2 - x1)
    # The bigger product throws the wider shadow.
    big, small = sorted(widths.values(), key=lambda w: w[1], reverse=True)
    if big[1] > small[1]:
        assert big[0] > small[0]


def test_realistic_with_cards_none_draws_only_products_and_shadows(tmp_path: Path, fonts) -> None:
    products = {**PRODUCTS, "serum": make_product("serum", name="Serum Sáng Da", price=320_000)}
    scene = _realistic_scene(tmp_path / "s", products)
    geometry, layout, frame = _realistic(scene, products, fonts, highlight="toner")
    assert all(slot.card_box is None for slot in layout.slots)
    drawn = [b for s in layout.slots for b in (s.art_box, s.shadow_box) if b is not None]
    # US3: the spoken product's warm light reaches a little further (research R3).
    drawn += [glow_box(geometry, s.art_box) for s in layout.slots if s.highlighted and s.art_box is not None]
    bbox = frame.getchannel("A").getbbox()
    assert bbox is not None
    x1, y1, x2, y2 = _union(*drawn)
    assert bbox[0] >= max(0, x1) and bbox[1] >= y1 and bbox[2] <= x2 and bbox[3] <= min(frame.height, y2)


@pytest.mark.parametrize("factor", [0.9, 1.1])
def test_brightness_scales_rgb_evenly_and_keeps_alpha(tmp_path: Path, fonts, factor: float) -> None:
    import colorsys

    plain = _realistic(_realistic_scene(tmp_path / "a", TWO), TWO, fonts)
    lit = _realistic(_realistic_scene(tmp_path / "b", TWO, brightness=factor), TWO, fonts)
    for slot in plain[1].slots:
        x1, y1, x2, y2 = slot.art_box
        point = ((x1 + x2) // 2, (y1 + y2) // 2)
        before, after = plain[2].getpixel(point), lit[2].getpixel(point)
        assert after[3] == before[3] == 255
        for b, a in zip(before[:3], after[:3], strict=True):
            assert abs(a - b * factor) <= 1, (before, after)
        hue = [colorsys.rgb_to_hsv(*(c / 255 for c in px[:3]))[0] * 360 for px in (before, after)]
        assert abs(hue[0] - hue[1]) <= 1.0


def test_realistic_draws_the_009_desk_only_when_the_picture_has_none(tmp_path: Path, fonts) -> None:
    scene = _realistic_scene(tmp_path / "s", TWO)
    geometry, layout, with_desk = _realistic(scene, TWO, fonts, desk_in_image=False)
    # The middle of the desk, under the hands: no product or shadow ever goes there.
    _, desk_y, width, height = layout.desk_box
    strip = (width // 2 - 2, desk_y, width // 2 + 2, height)
    assert not _clear(with_desk, strip)
    _, _, without = _realistic(scene, TWO, fonts, desk_in_image=True)
    assert _clear(without, strip)
    assert _clear(without, geometry.face_zone)


def test_debug_zones_mark_the_desk_edge_green_and_the_hands_purple(tmp_path: Path, fonts) -> None:
    from ai_live.scene.render import draw_debug_zones

    scene = _realistic_scene(tmp_path / "s", TWO)
    geometry, layout, frame = _realistic(scene, TWO, fonts)
    still = compose_still(Image.new("RGB", (geometry.width, geometry.height), (128, 128, 128)), [])
    debug = draw_debug_zones(still, geometry, layout)
    desk_y = layout.desk_box[1]
    hx1, hy1, _, _ = geometry.hands_zone
    green, purple = debug.getpixel((2, desk_y)), debug.getpixel((hx1, hy1 + 2))
    assert green[1] > 150 and green[0] < 80 and green[2] < 80, green
    assert purple[0] > 120 and purple[2] > 200 and purple[1] < 80, purple
    # Only the debug picture: the plain still and the live layer have neither mark.
    assert still.getpixel((2, desk_y)) == (128, 128, 128)
    assert still.getpixel((hx1, hy1 + 2)) == (128, 128, 128)
    assert frame.getpixel((hx1, hy1 + 2))[3] == 0


# ---------- 013 T047: the warm highlight, the dimming and the card text (research R3, R4; FR-020, FR-022) ----------

WARM = (255, 240, 210)


def _warm(px: tuple[int, ...]) -> bool:
    return px[3] > 0 and all(abs(a - b) <= 3 for a, b in zip(px[:3], WARM, strict=True))


def _middle(box) -> tuple[int, int]:
    return (box[0] + box[2]) // 2, (box[1] + box[3]) // 2


@pytest.mark.parametrize("highlight", ["kem-chong-nang", "toner"])
def test_realistic_highlight_is_a_warm_light_clear_of_every_zone(tmp_path: Path, fonts, highlight: str) -> None:
    from ai_live.scene.layout import scaled

    scene = _realistic_scene(tmp_path / "s", TWO)
    geometry, _, plain = _realistic(scene, TWO, fonts)
    _, layout, lit = _realistic(scene, TWO, fonts, highlight=highlight)
    x1, y1, x2, _ = layout.slot(highlight).art_box
    # Just above the picture's own transparent margin: only the light is there.
    above = ((x1 + x2) // 2, y1 - scaled(geometry, 4))
    assert _warm(lit.getpixel(above)), lit.getpixel(above)
    assert plain.getpixel(above)[3] == 0
    for zone in [geometry.face_zone, *geometry.keep_out_boxes(), geometry.hands_zone]:
        assert _clear(lit, zone), zone  # the light stops at the hands too (research R1, FR-007)


def test_realistic_dims_the_others_and_never_the_spoken_one(tmp_path: Path, fonts) -> None:
    scene = _realistic_scene(tmp_path / "s", TWO)
    _, plain_layout, plain = _realistic(scene, TWO, fonts)
    _, layout, lit = _realistic(scene, TWO, fonts, highlight="toner")
    box = layout.slot("kem-chong-nang").art_box
    assert box == plain_layout.slot("kem-chong-nang").art_box
    before, after = plain.getpixel(_middle(box)), lit.getpixel(_middle(box))
    assert after[3] == before[3] == 255
    for b, a in zip(before[:3], after[:3], strict=True):
        assert abs(a - b * REALISTIC_DIM) <= 1, (before, after)  # steps back, still clear (US3 #4)
    spoken = lit.getpixel(_middle(layout.slot("toner").art_box))
    assert spoken == plain.getpixel(_middle(plain_layout.slot("toner").art_box))


THREE = {
    **TWO,
    "serum": make_product(
        "serum",
        name="Serum Sáng Da",
        variants=(("30 ml", 290_000), ("50 ml", 420_000)),
        promotions=("Tặng bông tẩy trang",),
    ),
}


@pytest.mark.parametrize(
    ("cards", "highlight"), [("one", "serum"), ("one", "kem-chong-nang"), ("all", "serum"), ("all", None)]
)
def test_realistic_card_text_is_verbatim_from_the_file(tmp_path: Path, fonts, cards: str, highlight) -> None:
    from ai_live.scene.render import card_texts

    # 0.78 as on the demo host frame: a higher desk leaves no room above the taller products of 2026-11-23.
    scene = _realistic_scene(tmp_path / "s", THREE, cards=cards, desk_top=0.78)
    geometry, layout, frame = _realistic(scene, THREE, fonts, highlight=highlight)
    texts = card_texts(scene, layout, THREE, geometry, fonts)
    assert set(texts) == {s.product_id for s in layout.slots if s.card_box is not None}
    assert texts, layout.issues
    if cards == "one":
        assert set(texts) == {highlight}
    for pid, text in texts.items():
        product = THREE[pid]
        name = " ".join(text.name_lines)
        assert name == product.name or (name.endswith("…") and product.name.startswith(name[:-1].rstrip())), name
        # One line, or a range split after its dash: either way the words read as the file has them.
        assert " ".join(text.price_lines) == price_text(product), text.price_lines
        if text.promotion_lines:
            assert " ".join(text.promotion_lines) == product.promotions[0]
            assert layout.slot(pid).highlighted
        assert not _clear(frame, layout.slot(pid).card_box), pid


def _slanted_box(w: int = 120, h: int = 80, rise: int = 16) -> Image.Image:
    """A red box seen at an angle: its foot runs from `rise` px up on the left down to the bottom row on the right."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x in range(w):
        foot = h - 1 - round(rise * (w - 1 - x) / (w - 1))
        for y in range(foot + 1):
            img.putpixel((x, y), (220, 30, 30, 255))
    return img


def test_foot_line_is_the_lowest_opaque_row_of_each_column() -> None:
    from ai_live.scene.render import foot_line

    img = _slanted_box(10, 20, rise=9)
    img.putpixel((4, 19), (255, 255, 255, 60))  # a see-through fringe is not the foot
    clear = Image.new("RGBA", (3, 20), (0, 0, 0, 0))
    assert list(foot_line(img.getchannel("A"))) == [19 - (9 - x) for x in range(10)]
    assert list(foot_line(clear.getchannel("A"))) == [-1, -1, -1]


def test_realistic_shadow_follows_a_slanted_foot_without_a_gap() -> None:
    """2026-11-23 review: a box shot at an angle looked as if it floated over a level shadow."""
    from ai_live.scene.layout import shadow_box
    from ai_live.scene.render import _draw_product

    geometry = estimate_geometry("AI", "top-right")
    art = _slanted_box()
    box = (100, 600, 100 + art.width, 600 + art.height)
    layer = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    area = shadow_box(geometry, box)
    _draw_product(
        layer, art, box, highlighted=False, dimmed=False, accent=(0, 0, 0), geometry=geometry, shadow_box=area
    )
    for x in (box[0] + 2, box[0] + art.width // 2, box[2] - 3):
        foot = box[1] + max(y for y in range(art.height) if art.getpixel((x - box[0], y))[3] == 255)
        under = layer.getpixel((x, foot + 1))
        assert under[3] >= 60 and max(under[:3]) < 60, (x, foot, under)  # shadow right under the edge, no desk gap
    # Only a short strip shows in front of the foot: well below it the desk is clear again.
    assert layer.getpixel((box[0] + art.width // 2, box[3] + 20))[3] < 8
    nothing_outside = layer.copy()
    for drawn in (area, box):
        nothing_outside.paste((0, 0, 0, 0), drawn)
    assert nothing_outside.getbbox() is None  # the shadow stays inside the box the layout kept clear


def test_defringe_recolours_the_see_through_edge_from_the_solid_inside() -> None:
    from ai_live.scene.render import defringe

    img = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    for x in range(20):
        for y in range(15):
            img.putpixel((x, y), (220, 30, 30, 255))
        img.putpixel((x, 15), (240, 200, 200, 100))  # red mixed with a white studio background
    out = defringe(img)
    assert out.getpixel((5, 15)) == (220, 30, 30, 100)
    assert out.getpixel((5, 5)) == (220, 30, 30, 255) and out.getpixel((5, 18)) == (0, 0, 0, 0)


def _red_square(size: int = 40, inset: int = 10) -> Image.Image:
    """A solid red square on fully transparent black, like a cut-out product after `defringe`."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste((220, 30, 30, 255), (inset, inset, size - inset, size - inset))
    return img


def test_camera_soften_softens_the_edge_and_keeps_the_solid_colour() -> None:
    """FR-029: a product photo is crisper than the camera image; soften it without changing its colour (FR-006)."""
    from ai_live.scene.render import camera_soften

    out = camera_soften(_red_square(), 0.7, 0.8)
    assert out.getpixel((20, 20)) == (220, 30, 30, 255)
    edge = [out.getpixel((x, 20))[3] for x in range(7, 13)]
    assert any(0 < a < 255 for a in edge)  # the cut-out edge is no longer a hard step


def test_camera_soften_does_not_darken_the_edge_with_the_transparent_black() -> None:
    from ai_live.scene.render import camera_soften

    out = camera_soften(_red_square(), 0.7, 0.8)
    for x in range(6, 14):
        r, g, b, a = out.getpixel((x, 20))
        if a > 8:
            assert r >= 200 and g <= 50 and b <= 50, (x, (r, g, b, a))


def test_camera_soften_lowers_the_fine_detail() -> None:
    from ai_live.scene.render import camera_soften

    img = Image.new("RGBA", (40, 40), (255, 255, 255, 255))
    for x in range(40):
        for y in range(40):
            if (x + y) % 2:
                img.putpixel((x, y), (0, 0, 0, 255))
    out = camera_soften(img, 0.7, 0.0)
    contrast = [abs(out.getpixel((x, 20))[0] - out.getpixel((x + 1, 20))[0]) for x in range(10, 30)]
    assert max(contrast) < 255 and out.getchannel("A").getextrema() == (255, 255)
