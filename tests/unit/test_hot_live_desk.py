"""013 T080–T083 (ADR-095): the "hot live" showcase desk: stock groups, price tags and the promotions strip.

A shop live shows stock with a price on each item and the running deals below them. Everything shown comes verbatim
from the product data; the stock groups only repeat the product's own cut-out (FR-006, FR-030–FR-032).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from PIL import Image

from ai_live.products.models import Product
from ai_live.scene.fonts import SceneFontError, SceneFonts, load_fonts
from ai_live.scene.layout import (
    SHOWCASE_BACK,
    SHOWCASE_MAIN_MAX_WIDTH,
    compute_showcase_layout,
    estimate_geometry,
    price_text,
)
from ai_live.scene.loader import load_scene_set
from ai_live.scene.merchandise import stock_group, stock_kind, stock_size, with_stock
from ai_live.scene.models import Box, FrameGeometry, LayoutParams, ProductArt, intersects
from ai_live.scene.render import promo_banner_lines, render_base
from fixtures.scene_builder import CUSTOMER, make_scene_dir, product

LABEL = "AI-GENERATED CONTENT"
DESK_TOP = 0.76
HANDS = (0.30, 0.77, 0.70, 1.0)
SHOWCASE = LayoutParams(mode="showcase", cards="none", highlight_scale=1.08, max_slots=4)
HOT = dataclasses.replace(SHOWCASE, stock=True, price_tags=True, promo_banner=True)

PRODUCTS = (
    product("loc", primary=True, name="Lốc 6 chai", price=95_000, promotions=("Mua 2 lốc giảm 10.000đ",)),
    product("chai", name="Chai 500ml", price=12_000, promotions=("Mua 12 chai giảm 10.000đ",)),
    product("zero", name="Zero 237ml", price=15_000),
    product("lon", name="Lon 355ml", price=11_000, promotions=("Mua 24 lon giảm 20.000đ",)),
)
SIZES = {"loc": (300, 330), "chai": (180, 560), "zero": (150, 500), "lon": (160, 300)}


def _geometry() -> FrameGeometry:
    return estimate_geometry(LABEL, "top-right", width=480, height=832).with_hands_zone(HANDS)


def _layout(params: LayoutParams = HOT, products=PRODUCTS, sizes=None, highlight=None):
    sizes = {pid: stock_size(size, params) for pid, size in (sizes or SIZES).items()}
    return compute_showcase_layout(products, sizes, _geometry(), params, highlight, desk_top=DESK_TOP)


def _unit(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGBA", size, (200, 30, 30, 255))


# ---------- stock groups (FR-030) ----------


@pytest.mark.parametrize(
    ("size", "kind"),
    [
        ((100, 400), "row"),
        ((200, 400), "pyramid"),
        ((260, 400), "pyramid"),
        ((300, 340), "pair"),
        ((360, 300), "pair"),
        ((500, 300), "single"),
    ],
)
def test_the_shape_picks_how_a_product_is_stocked(size, kind) -> None:
    assert stock_kind(size) == kind


@pytest.mark.parametrize("size", [(100, 400), (200, 400), (300, 340), (500, 300)])
def test_the_group_has_the_size_the_layout_planned(size) -> None:
    assert stock_group(_unit(size)).size == stock_size(size, HOT)


def test_a_row_and_a_pair_are_one_unit_tall_and_a_pyramid_two() -> None:
    """The layout sizes a picture by its height (ADR-082): a row of bottles or a pair of packs must stand one unit
    tall, or each unit shows smaller than it is; only small cans stack, two cans being about one bottle."""
    assert stock_group(_unit((100, 400))).height == 400
    assert stock_group(_unit((300, 340))).height == 340
    assert stock_group(_unit((200, 400))).height == 800


def test_a_pair_keeps_the_front_pack_whole_and_shows_the_second_behind_it() -> None:
    group = stock_group(_unit((300, 340)))
    assert group.width > 300
    assert group.getpixel((5, 5)) == (200, 30, 30, 255)  # the front pack is untouched at its top-left corner
    assert group.getpixel((group.width - 3, 300))[3] == 255  # the second pack shows on the right


def test_the_group_only_repeats_the_unit_with_its_colour() -> None:
    """FR-006: the units behind may be darker, never another hue."""
    group = stock_group(_unit((100, 400)))
    for r, g, b, a in group.get_flattened_data():
        if a:
            assert g == b and r > g  # the same red, only darker
    assert group.getpixel((group.width // 2 - 5, 200)) == (200, 30, 30, 255)  # a front unit is untouched


def test_bottles_stand_as_two_staggered_rows_one_bottle_tall() -> None:
    """FR-035 (ADR-098): two bottles in front, three further back showing beside and between them, smaller, darker
    and standing higher, their tops level with the front row's so the group stays one bottle tall (ADR-082)."""
    group = stock_group(_unit((100, 400)))
    assert group.height == 400
    assert group.width >= 280  # three bottles across, not one bottle with two peeking behind it
    front = (200, 30, 30, 255)
    middle = group.width // 2
    assert group.getpixel((middle - 50, 399)) == front and group.getpixel((middle + 50, 399)) == front
    for x in (5, group.width - 5):  # the outer back bottles
        r, g, b, a = group.getpixel((x, 100))
        assert a == 255 and r < 200 and g == b  # darker, same hue
        assert group.getpixel((x, 0))[3] == 255  # its top is level with the front row's
        assert group.getpixel((x, 395))[3] == 0  # its foot stands higher, further back on the desk


def test_with_stock_skips_opaque_and_placeholder_art_and_clears_when_off() -> None:
    art = {
        "cut": ProductArt("cut", Path("cut.png"), _unit((100, 400))),
        "opaque": ProductArt("opaque", Path("o.jpg"), _unit((100, 400)), opaque=True),
        "sample": ProductArt("sample", Path("s.png"), _unit((100, 400)), placeholder=True),
    }
    on = with_stock(art, HOT)
    assert on["cut"].stock is not None and on["cut"].desk_image is on["cut"].stock
    assert on["opaque"].stock is None and on["sample"].stock is None
    assert on["cut"].image is art["cut"].image  # shelves and thumbnails keep the single unit
    off = with_stock(on, SHOWCASE)
    assert all(item.stock is None for item in off.values())


def test_stock_is_a_showcase_option_only() -> None:
    assert stock_size((100, 400), dataclasses.replace(HOT, mode="realistic")) == (100, 400)


# ---------- price tags (FR-031) ----------


def _art_boxes(layout) -> dict[str, Box]:
    return {s.product_id: s.art_box for s in layout.slots if s.art_box is not None}


def test_every_placed_product_gets_its_price_verbatim() -> None:
    layout = _layout()
    by_id = {p.id: p for p in PRODUCTS}
    tags = {t.product_id: t.text for t in layout.price_tags}
    assert set(tags) == set(_art_boxes(layout))
    for pid, text in tags.items():
        assert text == price_text(by_id[pid])


def test_a_tag_never_covers_another_product_tag_or_the_labels() -> None:
    geometry = _geometry()
    for highlight in (None, "chai", "lon"):
        layout = _layout(highlight=highlight)
        arts = _art_boxes(layout)
        forbidden = [geometry.face_zone, *geometry.keep_out_boxes()]
        for i, tag in enumerate(layout.price_tags):
            assert not any(intersects(tag.box, box) for pid, box in arts.items() if pid != tag.product_id)
            assert not any(intersects(tag.box, other.box) for other in layout.price_tags[i + 1 :])
            assert not any(intersects(tag.box, zone) for zone in forbidden)
            assert 0 <= tag.box[0] and tag.box[2] <= geometry.width and tag.box[3] <= geometry.height


def test_no_tag_without_a_price_or_with_the_flag_off() -> None:
    products = (*PRODUCTS[:3], product("lon", name="Lon 355ml", price=0))
    layout = _layout(products=products)
    assert "lon" not in {t.product_id for t in layout.price_tags}
    assert _layout(dataclasses.replace(HOT, price_tags=False)).price_tags == ()


def test_the_sticker_product_gets_no_second_tag() -> None:
    layout = _layout(dataclasses.replace(HOT, sticker=True))
    assert layout.sticker is not None
    assert layout.sticker.product_id not in {t.product_id for t in layout.price_tags}


# ---------- promotions strip (FR-032) ----------


def test_the_strip_lists_the_placed_products_promotions_verbatim() -> None:
    layout = _layout()
    assert layout.promo_banner is not None
    placed = set(_art_boxes(layout))
    expected = [(p.name, promo) for p in PRODUCTS if p.id in placed for promo in p.promotions]
    assert list(layout.promo_banner.lines) == expected


def test_the_strip_sits_below_every_product_and_tag() -> None:
    geometry = _geometry()
    layout = _layout()
    banner = layout.promo_banner
    assert banner is not None
    lowest = max([b[3] for b in _art_boxes(layout).values()] + [t.box[3] for t in layout.price_tags])
    assert banner.box[1] > lowest and banner.box[3] <= geometry.height
    assert not any(intersects(banner.box, zone) for zone in [geometry.face_zone, *geometry.keep_out_boxes()])


def test_no_strip_without_promotions_or_with_the_flag_off() -> None:
    plain = tuple(dataclasses.replace(p, promotions=()) for p in PRODUCTS)
    assert _layout(products=plain).promo_banner is None
    assert _layout(dataclasses.replace(HOT, promo_banner=False)).promo_banner is None


def test_the_hot_desk_is_off_by_default(tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "scene", ["a"], scene={"layout": {"mode": "showcase"}})
    layout = load_scene_set(root, ["a"], customer_id=CUSTOMER).layout
    assert (layout.stock, layout.price_tags, layout.promo_banner) == (False, False, False)


def test_the_loader_reads_the_flags_and_builds_the_groups(tmp_path: Path) -> None:
    flags = {"mode": "showcase", "stock": True, "price_tags": True, "promo_banner": True}
    root = make_scene_dir(tmp_path / "scene", ["a"], scene={"layout": flags})
    scene = load_scene_set(root, ["a"], customer_id=CUSTOMER)
    assert (scene.layout.stock, scene.layout.price_tags, scene.layout.promo_banner) == (True, True, True)
    assert {i.code for i in scene.issues} == set()
    assert scene.art["a"].stock is not None  # the fixture bottle is narrow: a row of three


# ---------- render ----------


@pytest.fixture(scope="module")
def fonts() -> SceneFonts:
    try:
        return load_fonts(None)
    except SceneFontError:
        pytest.skip("no font with Vietnamese diacritics on this machine")


def test_a_long_promotion_wraps_whole_or_is_left_out_whole(fonts: SceneFonts) -> None:
    geometry = _geometry()
    long = "Mua 2 lốc giảm 10.000đ, mua 3 lốc giảm 20.000đ, mua 5 lốc giảm 40.000đ và tặng thêm 1 chai 500ml"
    lines = (("Lốc 6 chai", long), ("Chai 500ml", "Mua 12 chai giảm 10.000đ"))
    from ai_live.scene.models import PromoBanner

    _, roomy = promo_banner_lines(PromoBanner((12, 600, 468, 820), lines), geometry, fonts)
    assert [" ".join(block) for block in roomy] == [f"{n}: {p}" for n, p in lines]
    _, tight = promo_banner_lines(PromoBanner((12, 600, 468, 660), lines), geometry, fonts)
    assert [" ".join(block) for block in tight] == [f"{n}: {p}" for n, p in lines][: len(tight)]


def test_render_draws_tags_and_strip_and_keeps_the_labels_clear(tmp_path: Path, fonts: SceneFonts) -> None:
    ids = [p.id for p in PRODUCTS]
    root = make_scene_dir(tmp_path / "scene", ids)
    scene = load_scene_set(root, ids, customer_id=CUSTOMER)
    scene = dataclasses.replace(scene, layout=HOT, art=with_stock(scene.art, HOT))
    geometry = _geometry()
    sizes = {pid: art.desk_image.size for pid, art in scene.art.items()}
    layout = compute_showcase_layout(PRODUCTS, sizes, geometry, HOT, "chai", desk_top=DESK_TOP)
    assert layout.price_tags and layout.promo_banner is not None
    by_id: dict[str, Product] = {p.id: p for p in PRODUCTS}
    layer = render_base(scene, layout, by_id, geometry, fonts)
    assert layer.image is not None
    frame = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    frame.alpha_composite(layer.image, (layer.x, layer.y))
    for x1, y1, x2, y2 in [geometry.face_zone, *geometry.keep_out_boxes()]:
        region = frame.crop((max(0, x1), max(0, y1), min(frame.width, x2), min(frame.height, y2)))
        assert region.getchannel("A").getextrema()[1] == 0
    tag = layout.price_tags[0].box
    assert frame.getpixel(((tag[0] + tag[2]) // 2, tag[1] + 2))[3] == 255
    bx1, by1, _, _ = layout.promo_banner.box
    assert frame.getpixel((bx1 + 30, by1 + 3))[3] > 200


# ---------- a gift box as the centrepiece (FR-033) ----------


def test_a_wide_gift_box_in_the_middle_leaves_the_bottles_room_beside_it() -> None:
    """ADR-096: a flat gift case as the main product takes at most half the frame width, so the bottle rows beside
    it keep most of their size instead of shrinking to a corner."""
    products = (
        product("tet", primary=True, name="Thùng Tết", price=235_000),
        product("chai", name="Chai 500ml", price=12_000),
        product("zero", name="Zero 237ml", price=15_000),
    )
    params = dataclasses.replace(SHOWCASE, stock=True, max_slots=3)
    sizes = {"tet": (1410, 1000), "chai": (180, 560), "zero": (150, 500)}
    layout = _layout(params, products, sizes)
    arts = _art_boxes(layout)
    assert set(arts) == {"tet", "chai", "zero"} and not layout.issues
    tet = arts["tet"]
    assert tet[2] - tet[0] <= SHOWCASE_MAIN_MAX_WIDTH * 480 + 1
    for pid, (_, target, _) in zip(("chai", "zero"), SHOWCASE_BACK, strict=False):
        assert arts[pid][3] - arts[pid][1] >= 0.55 * target * 832


# ---------- a stepped group: the gift box in front, the stock behind it (FR-034) ----------


def test_the_gift_box_stands_in_front_and_the_stock_steps_back_beside_it() -> None:
    """ADR-097: retail display reads as one stepped group, low in front and tall behind, around a centrepiece.

    The flat gift case stands in the middle near the desk's front edge (not on it); the taller bottle rows stand further
    back on each side, their feet and tops above the case's, so the stock behind it still shows.
    """
    products = (
        product("tet", primary=True, name="Thùng Tết", price=235_000),
        product("chai", name="Chai 500ml", price=12_000),
        product("zero", name="Zero 237ml", price=15_000),
    )
    params = dataclasses.replace(SHOWCASE, stock=True, max_slots=3)
    layout = _layout(params, products, {"tet": (1410, 1000), "chai": (180, 560), "zero": (150, 500)})
    arts = _art_boxes(layout)
    assert set(arts) == {"tet", "chai", "zero"} and not layout.issues
    tet, chai, zero = arts["tet"], arts["chai"], arts["zero"]
    desk_y = round(DESK_TOP * 832)
    assert abs((tet[0] + tet[2]) / 2 - 240) <= 2
    assert desk_y + 0.6 * (832 - desk_y) <= tet[3] <= 832 - 0.25 * (832 - desk_y)
    assert zero[2] <= tet[0] + 1 and chai[0] >= tet[2] - 1
    for back in (chai, zero):
        assert back[3] < tet[3] - 20
        assert back[1] < tet[1]
