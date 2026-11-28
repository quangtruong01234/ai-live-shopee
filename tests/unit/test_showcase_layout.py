"""013 T064–T069: the showcase layout, its riser, its price sticker and the low-resolution warning (FR-025–FR-028).

The main product stands big in the middle in front of the host, up to three smaller ones behind it. The cluster may
cover the hands and the chest, never the face, the "AI" label or the watermark.
"""

from __future__ import annotations

import dataclasses
import itertools
from pathlib import Path

import pytest
from PIL import Image

from ai_live.products.models import Product
from ai_live.scene.fonts import SceneFontError, SceneFonts, load_fonts
from ai_live.scene.layout import (
    LOW_RES_FACTOR,
    SHOWCASE_BACK,
    SHOWCASE_MAIN_MAX_WIDTH,
    compute_scene_layout,
    compute_showcase_layout,
    estimate_geometry,
    glow_box,
    low_resolution_issues,
    price_text,
)
from ai_live.scene.limits import ART_MAX_SIDE
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import Box, FrameGeometry, LayoutParams, SceneLayout, intersects
from ai_live.scene.render import render_base, sticker_lines
from ai_live.scene.shopee_overlay import frame_boxes
from fixtures.scene_builder import CUSTOMER, make_scene_dir, product

LABEL = "AI-GENERATED CONTENT"
FRAMES = ((480, 832), (720, 1280))
DESK_TOP = 0.76
HANDS = (0.30, 0.77, 0.70, 1.0)
PARAMS = LayoutParams(mode="showcase", cards="none", highlight_scale=1.08, max_slots=4)
FULL = dataclasses.replace(PARAMS, riser=True, sticker=True)

PRODUCTS = (
    product("lon", name="Lon 320ml"),
    product("chai", primary=True, name="Chai 1.5L", price=None, variants=(("1 chai", 18_000), ("thùng 12", 199_000))),
    product("loc", name="Lốc 6 lon"),
    product("ly", name="Ly"),
)
# Big enough that nothing here trips the FR-028 warning.
SIZES = {"lon": (300, 560), "chai": (300, 900), "loc": (700, 520), "ly": (400, 560)}
# The main product with two slim ones beside it: room enough for everything at full size.
SPARSE = (PRODUCTS[0], PRODUCTS[1], PRODUCTS[3])


def _geometry(width: int = 480, height: int = 832, *, position: str = "top-right") -> FrameGeometry:
    return estimate_geometry(LABEL, position, width=width, height=height).with_hands_zone(HANDS)


def _layout(geometry: FrameGeometry, params: LayoutParams = PARAMS, highlight=None, *, products=PRODUCTS, sizes=None):
    return compute_showcase_layout(products, sizes or SIZES, geometry, params, highlight, desk_top=DESK_TOP)


def _shown(layout: SceneLayout):
    return [s for s in layout.slots if s.art_box is not None]


def _forbidden(geometry: FrameGeometry) -> list[Box]:
    return [geometry.face_zone, *geometry.keep_out_boxes()]


def _painted(layout: SceneLayout, geometry: FrameGeometry) -> list[Box]:
    boxes: list[Box] = []
    for s in _shown(layout):
        assert s.art_box is not None
        boxes += [s.art_box, glow_box(geometry, s.art_box)]
        if s.shadow_box is not None:
            boxes.append(s.shadow_box)
        if s.card_box is not None:
            boxes.append(s.card_box)
    if layout.riser_box is not None:
        boxes.append(layout.riser_box)
    if layout.sticker is not None:
        boxes.append(layout.sticker.box)
    return boxes


def _main(layout: SceneLayout):
    return next(s for s in layout.slots if s.station == "showcase_middle")


@pytest.mark.parametrize(("width", "height"), FRAMES)
@pytest.mark.parametrize("position", ["top-right", "top-left", "bottom-right", "bottom-left"])
@pytest.mark.parametrize("params", [PARAMS, FULL, dataclasses.replace(FULL, cards="all")])
@pytest.mark.parametrize("highlight", [None, "chai", "lon", "ly"])
def test_nothing_painted_touches_the_face_or_the_labels(width, height, position, params, highlight) -> None:
    geometry = _geometry(width, height, position=position)
    layout = _layout(geometry, params, highlight)
    assert layout.mode == "showcase"
    for box, zone in itertools.product(_painted(layout, geometry), _forbidden(geometry)):
        assert not intersects(box, zone), (box, zone)
    for box in _painted(layout, geometry):
        assert box[0] >= 0 and box[2] <= geometry.width and box[1] >= 0


@pytest.mark.parametrize(("width", "height"), FRAMES)
def test_the_main_product_is_centred_at_about_its_real_size(width, height) -> None:
    """FR-025 (ADR-082): 0.26-0.30 H, near real size against the host's head; no back product is taller."""
    geometry = _geometry(width, height)
    layout = _layout(geometry, products=SPARSE)
    main = _main(layout)
    assert main.product_id == "chai" and main.art_box is not None
    x1, y1, x2, y2 = main.art_box
    assert 0.26 * height <= y2 - y1 <= 0.30 * height
    assert abs((x1 + x2) / 2 - width / 2) <= 2
    for slot in _shown(layout):
        assert slot.art_box is not None and slot.art_box[3] - slot.art_box[1] <= y2 - y1


def test_the_cluster_may_cover_the_hands() -> None:
    geometry = _geometry()
    assert geometry.hands_zone is not None
    main = _main(_layout(geometry))
    assert main.art_box is not None and intersects(main.art_box, geometry.hands_zone)


def test_the_main_product_is_drawn_last_and_the_others_stand_behind() -> None:
    layout = _layout(_geometry())
    assert len(_shown(layout)) == 4
    assert layout.draw_order[-1] == "chai"
    main = _main(layout)
    assert main.art_box is not None
    for s in _shown(layout):
        if s.product_id != "chai":
            assert s.art_box is not None
            assert s.art_box[3] < main.art_box[3]
            assert s.art_box[3] - s.art_box[1] < main.art_box[3] - main.art_box[1]
    stations = {s.product_id: s.station for s in layout.slots}
    assert stations == {
        "chai": "showcase_middle",
        "lon": "showcase_right",
        "loc": "showcase_left",
        "ly": "showcase_right",
    }


@pytest.mark.parametrize(("width", "height"), FRAMES)
@pytest.mark.parametrize("params", [PARAMS, FULL])
@pytest.mark.parametrize("highlight", [None, "chai", "lon", "loc", "ly"])
def test_no_product_hides_another(width, height, params, highlight) -> None:
    """FR-025 (ADR-081): no two products overlap, lit or not, and the sticker covers only the main one."""
    layout = _layout(_geometry(width, height), params, highlight)
    shown = _shown(layout)
    for a, b in itertools.combinations(shown, 2):
        assert a.art_box is not None and b.art_box is not None
        assert not intersects(a.art_box, b.art_box), (a.product_id, b.product_id)
    if layout.sticker is not None:
        for s in shown:
            if s.station != "showcase_middle":
                assert s.art_box is not None and not intersects(layout.sticker.box, s.art_box), s.product_id


def test_more_than_four_products_overflow() -> None:
    extra = (*PRODUCTS, product("nap", name="Nắp"))
    layout = _layout(
        _geometry(), dataclasses.replace(PARAMS, max_slots=9), products=extra, sizes={**SIZES, "nap": (300, 300)}
    )
    assert len(layout.slots) == 4
    assert layout.overflow == ("nap",)
    assert "overflow" in {i.code for i in layout.issues}


def test_riser_lifts_the_main_product_and_stands_under_it() -> None:
    geometry = _geometry()
    plain = _main(_layout(geometry))
    lifted_layout = _layout(geometry, dataclasses.replace(PARAMS, riser=True))
    lifted = _main(lifted_layout)
    assert plain.art_box is not None and lifted.art_box is not None
    assert _layout(geometry).riser_box is None
    riser = lifted_layout.riser_box
    assert riser is not None
    assert lifted.art_box[3] < plain.art_box[3]
    assert riser[0] < lifted.art_box[0] and riser[2] > lifted.art_box[2]
    assert riser[1] < lifted.art_box[3] < riser[3]


def test_sticker_shows_the_catalog_price_verbatim() -> None:
    layout = _layout(_geometry(), FULL, products=SPARSE)
    assert layout.sticker is not None
    assert layout.sticker.product_id == "chai"
    assert layout.sticker.text == price_text(PRODUCTS[1])
    assert "18" in layout.sticker.text and "199" in layout.sticker.text
    main = _main(layout)
    assert main.art_box is not None and intersects(layout.sticker.box, main.art_box)
    assert _layout(_geometry(), products=SPARSE).sticker is None


def test_sticker_is_never_drawn_for_a_product_without_price() -> None:
    no_price = (*PRODUCTS[:1], product("chai", primary=True, name="Chai", price=0), *PRODUCTS[2:])
    layout = _layout(_geometry(), FULL, products=no_price)
    assert layout.sticker is None
    assert [i.code for i in layout.issues].count("sticker_no_price") == 1


def test_sticker_never_shows_a_promotion() -> None:
    promo = (PRODUCTS[0], product("chai", primary=True, name="Chai", promotions=("Giảm 50%",)), PRODUCTS[3])
    layout = _layout(_geometry(), FULL, products=promo)
    assert layout.sticker is not None
    assert "50" not in layout.sticker.text and layout.sticker.text == price_text(promo[1])


@pytest.mark.parametrize(
    ("text", "lines"),
    [("159.000đ", ("159.000đ",)), ("18.000đ – 199.000đ", ("18.000đ –", "199.000đ"))],
)
def test_sticker_lines_keep_each_price_whole(text: str, lines: tuple[str, ...]) -> None:
    assert sticker_lines(text) == lines


def test_cards_one_puts_a_card_over_the_spoken_product_or_says_no_room() -> None:
    layout = _layout(_geometry(), dataclasses.replace(PARAMS, cards="one"), "chai")
    main = _main(layout)
    no_room = {i.product_id for i in layout.issues if i.code == "card_no_room"}
    assert main.card_box is not None or "chai" in no_room
    assert all(s.card_box is None for s in layout.slots if s.product_id != "chai")


def test_the_lit_product_grows_without_breaking_the_hiding_rule() -> None:
    geometry = _geometry()
    calm = {s.product_id: s.art_box for s in _layout(geometry).slots}
    lit = _layout(geometry, highlight="chai")
    main = _main(lit)
    assert main.highlighted and main.art_box is not None and calm["chai"] is not None
    assert main.art_box[3] - main.art_box[1] >= calm["chai"][3] - calm["chai"][1]


def test_too_wide_main_product_is_reported() -> None:
    layout = _layout(_geometry(), sizes={**SIZES, "chai": (3000, 100)})
    assert _main(layout).art_box is None
    assert "art_too_wide" in {i.code for i in layout.issues}


def test_desk_over_the_face_draws_nothing() -> None:
    geometry = _geometry()
    layout = compute_showcase_layout(PRODUCTS, SIZES, geometry, PARAMS, desk_top=0.1)
    assert not layout.slots
    assert "layout_keep_out" in {i.code for i in layout.issues}


# ---------- FR-028: low resolution, in every mode ----------


@pytest.mark.parametrize("mode", ["rows", "realistic", "showcase"])
def test_a_small_picture_warns_in_every_mode(mode: str) -> None:
    geometry = _geometry()
    params = dataclasses.replace(PARAMS, mode=mode, max_slots=4)
    small = {**SIZES, "chai": (30, 90)}
    layout = compute_scene_layout(PRODUCTS, small, geometry, params, desk_top=DESK_TOP)
    low = [i for i in layout.issues if i.code == "art_low_resolution"]
    assert [i.product_id for i in low] == ["chai"]
    assert "Chai 1.5L" in low[0].message and "sẽ mờ" in low[0].message
    big = compute_scene_layout(PRODUCTS, SIZES, geometry, params, desk_top=DESK_TOP)
    assert "art_low_resolution" not in {i.code for i in big.issues}


def test_low_resolution_judges_the_lit_size() -> None:
    geometry = _geometry()
    layout = _layout(geometry)
    main = _main(layout)
    assert main.art_box is not None
    drawn = main.art_box[3] - main.art_box[1]
    lit = round(drawn * PARAMS.highlight_scale)
    # Enough for the calm size, not for the lit one: it still warns, so the warning does not flicker per sentence.
    just = round(LOW_RES_FACTOR * drawn) + 1
    assert just < LOW_RES_FACTOR * lit
    sizes = {**SIZES, "chai": (300 * just // 900, just)}
    issues = low_resolution_issues(layout, PRODUCTS, sizes, PARAMS)
    assert [i.product_id for i in issues] == ["chai"]


# ---------- loader ----------

IDS = ["a", "b"]


def _loaded(tmp_path: Path, layout: dict):
    root = make_scene_dir(tmp_path / "scene", IDS, scene={"layout": layout})
    scene = load_scene_set(root, IDS, customer_id=CUSTOMER)
    return scene.layout, {i.code: i.level for i in scene.issues}


def test_showcase_defaults(tmp_path: Path) -> None:
    layout, codes = _loaded(tmp_path, {"mode": "showcase"})
    assert layout.mode == "showcase"
    assert layout.cards == "none"
    assert layout.max_slots == 4
    assert layout.highlight_scale == pytest.approx(1.08)
    assert layout.riser is False and layout.sticker is False
    assert codes == {}


def test_showcase_reads_riser_and_sticker(tmp_path: Path) -> None:
    layout, codes = _loaded(tmp_path, {"mode": "showcase", "riser": True, "sticker": True})
    assert layout.riser is True and layout.sticker is True
    assert codes == {}


def test_showcase_max_slots_is_clamped_to_four(tmp_path: Path) -> None:
    layout, codes = _loaded(tmp_path, {"mode": "showcase", "max_slots": 6})
    assert layout.max_slots == 4
    assert codes  # the clamp is reported


# ---------- render ----------


@pytest.fixture(scope="module")
def fonts() -> SceneFonts:
    try:
        return load_fonts(None)
    except SceneFontError:
        pytest.skip("no font with Vietnamese diacritics on this machine")


def test_render_with_riser_and_sticker_keeps_the_face_and_labels_clear(tmp_path: Path, fonts: SceneFonts) -> None:
    ids = [p.id for p in PRODUCTS]
    root = make_scene_dir(tmp_path / "scene", ids)
    scene = load_scene_set(root, ids, customer_id=CUSTOMER)
    geometry = _geometry()
    sizes = {pid: art.image.size for pid, art in scene.art.items()}
    layout = compute_showcase_layout(PRODUCTS, sizes, geometry, FULL, "chai", desk_top=DESK_TOP)
    assert layout.riser_box is not None and layout.sticker is not None
    by_id: dict[str, Product] = {p.id: p for p in PRODUCTS}
    layer = render_base(scene, layout, by_id, geometry, fonts)
    assert layer.image is not None
    frame = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    frame.alpha_composite(layer.image, (layer.x, layer.y))
    for x1, y1, x2, y2 in _forbidden(geometry):
        region = frame.crop((max(0, x1), max(0, y1), min(frame.width, x2), min(frame.height, y2)))
        assert region.getchannel("A").getextrema()[1] == 0
    # The sticker is painted, in the accent colour, where the layout put it.
    sx1, sy1, sx2, sy2 = layout.sticker.box
    assert frame.getpixel(((sx1 + sx2) // 2, sy1 + 4))[3] == 255


def test_a_picture_at_the_kept_size_is_not_flagged() -> None:
    """A bigger upload would be shrunk to `ART_MAX_SIDE` anyway, so asking for one would be useless advice."""
    layout = _layout(_geometry())
    assert low_resolution_issues(layout, PRODUCTS, {**SIZES, "chai": (ART_MAX_SIDE, 120)}, PARAMS) == []
    assert low_resolution_issues(layout, PRODUCTS, {**SIZES, "chai": (ART_MAX_SIDE - 1, 120)}, PARAMS)


def test_a_wide_main_product_shrinks_to_make_room_beside_it() -> None:
    """ADR-081: a 6-can pack as wide as the desk gives room so both bottles stand whole beside it."""
    pack = (
        product("chai500", name="Chai 500ml"),
        product("loc6", primary=True, name="Lốc 6 lon"),
        product("zero", name="Zero 237ml"),
    )
    sizes = {"chai500": (260, 900), "loc6": (900, 640), "zero": (250, 800)}
    geometry = _geometry()
    layout = _layout(geometry, FULL, products=pack, sizes=sizes)
    shown = {s.product_id: s for s in _shown(layout)}
    assert set(shown) == {"chai500", "loc6", "zero"}
    main = shown["loc6"].art_box
    assert main is not None
    # ADR-096: a pack this wide is held to half the frame width before the 0.22 H floor.
    floor = min(0.22 * geometry.height, SHOWCASE_MAIN_MAX_WIDTH * geometry.width * 640 / 900)
    assert floor - 1 <= main[3] - main[1] < 0.38 * geometry.height
    for a, b in itertools.combinations(shown.values(), 2):
        assert a.art_box is not None and b.art_box is not None and not intersects(a.art_box, b.art_box)
    for pid in ("chai500", "zero"):
        box = shown[pid].art_box
        target = min(h for _, h, _ in SHOWCASE_BACK[:2])
        assert box is not None and box[3] - box[1] >= 0.85 * target * geometry.height - 1
    assert {shown["chai500"].station, shown["zero"].station} == {"showcase_left", "showcase_right"}


def test_a_crowded_desk_still_shows_every_product_whole() -> None:
    """ADR-081: four products on a narrow frame all stand, none on another, none past the frame."""
    geometry = _geometry()
    layout = _layout(geometry, FULL)
    assert len(_shown(layout)) == 4
    for box in _painted(layout, geometry):
        assert box[0] >= 0 and box[2] <= geometry.width


# ---------- 014 FR-019, ADR-087: the cluster stands clear of the Shopee app's comments and chat bar ----------

AVOID = dataclasses.replace(FULL, avoid_app_overlay=True)


def _bottom_zones(width: int, height: int) -> list[Box]:
    return [box for name, box in frame_boxes(width, height) if name in ("comments", "chat_bar")]


@pytest.mark.parametrize(("width", "height"), FRAMES)
@pytest.mark.parametrize("params", [dataclasses.replace(PARAMS, avoid_app_overlay=True), AVOID])
@pytest.mark.parametrize("highlight", [None, "chai", "loc"])
def test_avoid_app_overlay_keeps_every_product_out_of_the_comments(width, height, params, highlight) -> None:
    geometry = _geometry(width, height)
    layout = _layout(geometry, params, highlight)
    shown = _shown(layout)
    assert len(shown) == 4
    zones = _bottom_zones(width, height)
    desk_y = round(DESK_TOP * height)
    for s in shown:
        assert s.art_box is not None
        assert not any(intersects(s.art_box, z) for z in zones), s.product_id
        assert s.art_box[3] > desk_y, s.product_id  # still standing on the desk
    # The main product still stands in front of the others.
    main = _main(layout)
    assert main.art_box is not None
    assert all(s.art_box[3] <= main.art_box[3] for s in shown if s.art_box is not None)
    assert layout.draw_order[-1] == "chai"
    for a, b in itertools.combinations(shown, 2):
        assert not intersects(a.art_box, b.art_box), (a.product_id, b.product_id)
    for box in _painted(layout, geometry):
        assert not any(intersects(box, z) for z in _forbidden(geometry))


def test_without_the_flag_the_cluster_keeps_its_depth() -> None:
    geometry = _geometry()
    plain = _main(_layout(geometry, FULL))
    assert plain.art_box is not None
    assert any(intersects(plain.art_box, z) for z in _bottom_zones(480, 832))


def test_showcase_reads_avoid_app_overlay(tmp_path: Path) -> None:
    layout, codes = _loaded(tmp_path, {"mode": "showcase"})
    assert layout.avoid_app_overlay is False
    layout, codes = _loaded(tmp_path, {"mode": "showcase", "avoid_app_overlay": True})
    assert layout.avoid_app_overlay is True
    assert codes == {}


def test_the_spoken_product_gets_a_faint_light_not_a_halo(tmp_path: Path, fonts: SceneFonts) -> None:
    """ADR-093: in front of the host's dark shirt the realistic-desk light (230) showed as a milky halo."""
    from ai_live.scene.layout import HIGHLIGHT_ALPHA, SHOWCASE_HIGHLIGHT_ALPHA, scaled

    ids = [p.id for p in PRODUCTS]
    scene = load_scene_set(make_scene_dir(tmp_path / "scene", ids), ids, customer_id=CUSTOMER)
    geometry = _geometry()
    sizes = {pid: art.image.size for pid, art in scene.art.items()}
    layout = compute_showcase_layout(PRODUCTS, sizes, geometry, PARAMS, "chai", desk_top=DESK_TOP)
    layer = render_base(scene, layout, {p.id: p for p in PRODUCTS}, geometry, fonts)
    assert layer.image is not None
    frame = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    frame.alpha_composite(layer.image, (layer.x, layer.y))
    x1, y1, x2, _ = layout.slot("chai").art_box
    above = frame.getpixel(((x1 + x2) // 2, y1 - scaled(geometry, 4)))
    assert 0 < above[3] <= SHOWCASE_HIGHLIGHT_ALPHA < HIGHLIGHT_ALPHA, above
