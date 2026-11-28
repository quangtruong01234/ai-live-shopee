"""013 T016, T017, T046: the realistic desk layout, its cards and highlight (research R1–R4; data-model §4–§5).

Products stand on both sides of the host's hands, the main one in front on the right, the others smaller and further
back; nothing touches the face, the "AI" label, the watermark or the hands.
"""

from __future__ import annotations

import dataclasses
import itertools

import pytest

from ai_live.products.models import Product
from ai_live.scene.layout import (
    BOTTOM_MARGIN_PX,
    DESK_STATIONS,
    MIN_ART_HEIGHT,
    compute_layout,
    compute_realistic_layout,
    compute_scene_layout,
    default_hands_zone,
    estimate_geometry,
    glow_box,
)
from ai_live.scene.models import Box, FrameGeometry, LayoutParams, SceneLayout, intersects
from fixtures.scene_builder import product

LABEL = "AI-GENERATED CONTENT"
FRAMES = ((480, 832), (720, 1280))  # the lip-sync frame and a still-image frame
DESK_TOP = 0.868  # demo_host_02 as measured in the 2026-11-22 mock-up
HANDS = (0.30, 0.77, 0.70, 1.0)
PARAMS = LayoutParams(mode="realistic", cards="none", highlight_scale=1.04, max_slots=5)

# File order puts the main product second on purpose: the station order must not depend on it.
PRODUCTS = (
    product("toner", name="Toner"),
    product("kem", primary=True, name="Kem chống nắng"),
    product("serum", name="Serum"),
    product("son", name="Son"),
    product("mat-na", name="Mặt nạ"),
    product("sua-tam", name="Sữa tắm"),
)
SIZES = {
    "toner": (160, 220),
    "kem": (120, 240),
    "serum": (90, 300),
    "son": (60, 200),
    "mat-na": (140, 140),
    "sua-tam": (110, 260),
}


def _geometry(width: int = 480, height: int = 832, *, position: str = "top-right", label: str = LABEL, hands=HANDS):
    return estimate_geometry(label, position, width=width, height=height).with_hands_zone(hands)


def _products(n: int) -> list[Product]:
    """The first `n` products, always with the main one."""
    chosen = [p for p in PRODUCTS if p.is_primary] + [p for p in PRODUCTS if not p.is_primary]
    keep = {p.id for p in chosen[:n]}
    return [p for p in PRODUCTS if p.id in keep]


def _layout(products, geometry: FrameGeometry, highlight=None, *, sizes=None, params=PARAMS) -> SceneLayout:
    return compute_realistic_layout(products, sizes or SIZES, geometry, params, highlight, desk_top=DESK_TOP)


def _shown(layout: SceneLayout):
    return [s for s in layout.slots if s.art_box is not None]


def _forbidden(geometry: FrameGeometry) -> list[Box]:
    assert geometry.hands_zone is not None
    return [geometry.face_zone, *geometry.keep_out_boxes(), geometry.hands_zone]


def _area(box: Box) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _overlap(a: Box, b: Box) -> int:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


# ---------- T016: invariants ----------


def test_station_table_gets_smaller_and_further_back() -> None:
    assert [s.name for s in DESK_STATIONS] == ["P", "S1", "S2", "S3", "S4"]
    assert DESK_STATIONS[0].side == "right"
    for a, b in itertools.combinations(DESK_STATIONS, 2):
        assert a.height_frac > b.height_frac and a.depth > b.depth, (a, b)
    for s in DESK_STATIONS:
        assert 0.0 <= s.x_frac <= 1.0 and 0.0 < s.depth <= 1.0 and s.height_frac >= MIN_ART_HEIGHT


CASES = [
    (frame, n, highlight)
    for frame in FRAMES
    for n in range(1, 6)
    for highlight in [None, *(p.id for p in _products(n))]
]


@pytest.mark.parametrize(("frame", "n", "highlight"), CASES)
def test_every_product_stands_on_the_desk_clear_of_face_label_and_hands(frame, n: int, highlight) -> None:
    W, H = frame
    geometry = _geometry(W, H)
    layout = _layout(_products(n), geometry, highlight)
    assert layout.mode == "realistic" and layout.drawable
    desk_y = round(DESK_TOP * H)
    assert layout.desk_box == (0, desk_y, W, H)
    hx1, _, hx2, _ = geometry.hands_zone
    shown = _shown(layout)
    assert [s.product_id for s in shown] == [s.product_id for s in layout.slots], layout.issues
    for slot in shown:
        x1, y1, x2, y2 = slot.art_box
        assert desk_y <= y2 <= H, slot  # FR-002: the foot is on the desk
        cx = (x1 + x2) / 2
        assert not hx1 <= cx <= hx2, slot  # never between the hands
        assert slot.shadow_box is not None
        for box in (slot.art_box, slot.shadow_box):
            for zone in _forbidden(geometry):
                assert not intersects(box, zone), (slot, zone)
        aw, ah = SIZES[slot.product_id]
        assert abs((x2 - x1) - (y2 - y1) * aw / ah) <= 1, slot  # FR-004: never stretched
        assert slot.card_box is None and slot.station is not None
        assert slot.highlighted == (slot.product_id == highlight)


@pytest.mark.parametrize(("frame", "n", "highlight"), CASES)
def test_main_product_in_front_on_the_right_and_the_rest_smaller_further_back(frame, n: int, highlight) -> None:
    W, H = frame
    geometry = _geometry(W, H)
    layout = _layout(_products(n), geometry, highlight)
    shown = _shown(layout)
    main = shown[0]
    assert main.product_id == "kem" and main.primary and main.station == "P"
    assert main.art_box[0] >= geometry.hands_zone[2]  # right of the hands, as the viewer sees it
    assert [s.station for s in layout.slots] == [st.name for st in DESK_STATIONS[:n]]
    bottoms = [s.art_box[3] for s in shown]
    assert bottoms == sorted(bottoms, reverse=True) and len(set(bottoms)) == len(bottoms), bottoms
    # Smaller than every product in front: never both as tall and as big in area (a flat box in front may have a
    # taller, thinner bottle behind it; a thin bottle in front may have a lower, wider jar behind it).
    for front, back in itertools.combinations(shown, 2):
        fh, bh = front.art_box[3] - front.art_box[1], back.art_box[3] - back.art_box[1]
        assert bh < fh or _area(back.art_box) < _area(front.art_box), (front, back)


def test_a_product_behind_may_be_taller_and_thinner_but_never_bigger() -> None:
    """A flat main box must not squash the bottles behind it below its own height (2026-11-23 review)."""
    sizes = {**SIZES, "kem": (200, 150), "toner": (60, 220)}
    geometry = _geometry(hands=(0.38, 0.70, 0.73, 0.86))
    layout = compute_realistic_layout(_products(2), sizes, geometry, PARAMS, desk_top=0.78)
    main, bottle = _shown(layout)
    main_h, bottle_h = main.art_box[3] - main.art_box[1], bottle.art_box[3] - bottle.art_box[1]
    assert bottle_h > main_h
    assert _area(bottle.art_box) < _area(main.art_box)


@pytest.mark.parametrize("position", ["top-right", "top-left", "bottom-right", "bottom-left"])
@pytest.mark.parametrize("highlight", [None, "kem", "son"])
def test_invariants_hold_for_any_label_corner(position: str, highlight) -> None:
    geometry = _geometry(position=position, label="AI")
    layout = _layout(_products(5), geometry, highlight)
    for slot in _shown(layout):
        for box in (slot.art_box, slot.shadow_box):
            for zone in _forbidden(geometry):
                assert not intersects(box, zone), (slot, zone)
    # A product that found no room says so; it is never silently missing.
    for slot in layout.slots:
        if slot.art_box is None:
            assert any(i.product_id == slot.product_id for i in layout.issues), slot


# ---------- T017: edge cases ----------


def test_one_product_stands_on_the_right_and_the_left_stays_empty() -> None:
    geometry = _geometry()
    layout = _layout(_products(1), geometry)
    assert [(s.product_id, s.station) for s in layout.slots] == [("kem", "P")]
    assert layout.slots[0].art_box[0] >= geometry.hands_zone[2]
    assert layout.issues == ()


def test_sixth_product_overflows() -> None:
    layout = _layout(list(PRODUCTS), _geometry(), params=LayoutParams(mode="realistic", cards="none", max_slots=5))
    assert layout.overflow == ("sua-tam",)
    assert [i.code for i in layout.issues] == ["overflow"]
    assert len(layout.slots) == 5


def test_more_than_five_slots_is_still_five_on_the_desk() -> None:
    params = LayoutParams(mode="realistic", cards="none", max_slots=7)
    layout = _layout(list(PRODUCTS), _geometry(), params=params)
    assert len(layout.slots) == 5 and layout.overflow == ("sua-tam",)


def test_flat_picture_is_too_wide_for_its_side() -> None:
    sizes = {**SIZES, "toner": (500, 100)}  # 5:1
    layout = _layout(_products(3), _geometry(), sizes=sizes)
    toner = layout.slot("toner")
    assert toner is not None and toner.art_box is None
    codes = [(i.code, i.product_id) for i in layout.issues]
    assert codes == [("art_too_wide", "toner")]
    assert "(500×100)" in layout.issues[0].message


def test_tall_bottle_shrinks_to_stay_below_the_face() -> None:
    sizes = {**SIZES, "kem": (100, 400)}  # 1:4
    geometry = estimate_geometry(LABEL, "top-right", face_bottom=700).with_hands_zone(HANDS)
    layout = _layout(_products(1), geometry, sizes=sizes)
    kem = layout.slot("kem")
    assert kem is not None and kem.art_box is not None
    assert kem.art_box[1] >= geometry.face_zone[3]
    assert kem.art_box[3] - kem.art_box[1] < DESK_STATIONS[0].height_frac * 832
    x1, y1, x2, y2 = kem.art_box
    assert abs((x2 - x1) - (y2 - y1) / 4) <= 1


def _left_pair(hands_x1: float):
    """Two square products on the left (S1 in front of S2), with the hands zone starting at `hands_x1`.

    The zone is symmetric, so the other side is just as narrow and moving the main product there cannot help.
    """
    products = [product("kem", primary=True), product("a"), product("b")]
    sizes = {"kem": (120, 240), "a": (200, 200), "b": (200, 200)}
    geometry = _geometry(hands=(hands_x1, 0.77, 1 - hands_x1, 1.0))
    return _layout(products, geometry, sizes=sizes), geometry


@pytest.mark.parametrize("hands_x1", [0.30, 0.27, 0.26, 0.20])
def test_front_product_never_hides_more_than_half_of_the_one_behind(hands_x1: float) -> None:
    layout, _ = _left_pair(hands_x1)
    front, back = layout.slot("a"), layout.slot("b")
    assert front.station == "S1" and back.station == "S2"
    if back.art_box is not None:
        assert _overlap(front.art_box, back.art_box) <= 0.5 * _area(back.art_box)


def test_overlap_shrinks_both_before_dropping() -> None:
    wide, _ = _left_pair(0.30)
    narrow, _ = _left_pair(0.27)
    # Less room: both shrink rather than the back one going.
    assert narrow.slot("b").art_box is not None
    for pid in ("a", "b"):
        w_box, n_box = wide.slot(pid).art_box, narrow.slot(pid).art_box
        assert n_box[3] - n_box[1] < w_box[3] - w_box[1], pid


def test_overlap_that_cannot_be_solved_drops_the_back_product() -> None:
    layout, _ = _left_pair(0.20)
    assert layout.slot("a").art_box is not None
    assert layout.slot("b").art_box is None
    assert ("no_room", "b") in [(i.code, i.product_id) for i in layout.issues]


@pytest.mark.parametrize("highlight", [None, "kem", "serum", "mat-na"])
def test_draw_order_is_far_to_near_and_ignores_the_highlight(highlight) -> None:
    geometry = _geometry()
    plain = _layout(_products(5), geometry)
    layout = _layout(_products(5), geometry, highlight)
    assert layout.draw_order == plain.draw_order
    bottoms = [layout.slot(pid).art_box[3] for pid in layout.draw_order]
    assert bottoms == sorted(bottoms)
    assert layout.draw_order[-1] == "kem"


def test_missing_hands_zone_uses_the_default_and_warns() -> None:
    assert default_hands_zone(DESK_TOP) == pytest.approx((0.30, DESK_TOP - 0.10, 0.70, 1.0))
    geometry = estimate_geometry(LABEL, "top-right")
    assert geometry.hands_zone is None
    layout = _layout(_products(5), geometry)
    assert [i.code for i in layout.issues] == ["hands_zone_missing"]
    assert layout.issues[0].level == "warning"
    hx1, hx2 = round(0.30 * 480), round(0.70 * 480)
    for slot in _shown(layout):
        assert not hx1 <= (slot.art_box[0] + slot.art_box[2]) / 2 <= hx2


def test_desk_reaching_the_face_draws_nothing() -> None:
    geometry = estimate_geometry(LABEL, "top-right", face_bottom=760).with_hands_zone(HANDS)
    layout = _layout(_products(3), geometry)
    assert not layout.drawable and layout.slots == ()


def test_dispatch_follows_the_mode() -> None:
    geometry = _geometry()
    products = _products(3)
    rows = LayoutParams()

    def without_low_res(layout: SceneLayout) -> SceneLayout:
        # The dispatcher adds the FR-028 warnings on top of what each layout says (the test pictures are small).
        kept = tuple(i for i in layout.issues if i.code != "art_low_resolution")
        return dataclasses.replace(layout, issues=kept)

    assert without_low_res(
        compute_scene_layout(products, SIZES, geometry, rows, None, desk_top=DESK_TOP)
    ) == compute_layout(products, SIZES, geometry, rows, None, desk_top=DESK_TOP)
    assert without_low_res(compute_scene_layout(products, SIZES, geometry, PARAMS, None, desk_top=DESK_TOP)) == _layout(
        products, geometry
    )


# ---------- T025: `python -m ai_live.scene` reads the character and shows the 013 fields ----------


# ---------- T046: cards and the highlight (research R3, R4; US3 #1–#4, FR-019, FR-022) ----------

HIGH_DESK = 0.70  # a desk high enough in the frame for cards under the products' feet
SIDES = {st.name: st.side for st in DESK_STATIONS}
ALL_IDS = [p.id for p in _products(5)]


def _params(cards: str, scale: float = 1.04) -> LayoutParams:
    return LayoutParams(mode="realistic", cards=cards, highlight_scale=scale, max_slots=5)


def _at(desk_top: float, products, geometry, highlight, params) -> SceneLayout:
    return compute_realistic_layout(products, SIZES, geometry, params, highlight, desk_top=desk_top)


def _no_room(layout: SceneLayout) -> set[str]:
    found = {i.product_id for i in layout.issues if i.code == "card_no_room"}
    assert all(i.level == "warning" for i in layout.issues if i.code == "card_no_room")
    return found


def _assert_card_clear(layout: SceneLayout, geometry: FrameGeometry, card: Box) -> None:
    assert 0 <= card[0] < card[2] <= geometry.width and 0 <= card[1] < card[3] <= geometry.height, card
    for zone in _forbidden(geometry):
        assert not intersects(card, zone), (card, zone)
    for slot in _shown(layout):
        assert not intersects(card, slot.art_box), (card, slot)


@pytest.mark.parametrize("highlight", [None, "kem", "serum"])
@pytest.mark.parametrize("desk_top", [HIGH_DESK, DESK_TOP])
def test_cards_none_draws_no_card(highlight, desk_top: float) -> None:
    layout = _at(desk_top, _products(5), _geometry(), highlight, _params("none"))
    assert all(slot.card_box is None for slot in layout.slots)
    assert not _no_room(layout)


@pytest.mark.parametrize("highlight", [None, "kem", "son"])
@pytest.mark.parametrize("desk_top", [HIGH_DESK, DESK_TOP])
def test_cards_all_sit_under_each_foot_or_are_dropped_with_a_warning(highlight, desk_top: float) -> None:
    geometry = _geometry()
    layout = _at(desk_top, _products(5), geometry, highlight, _params("all"))
    no_room = _no_room(layout)
    cards = []
    for slot in _shown(layout):
        if slot.card_box is None:
            assert slot.product_id in no_room, slot  # never silently missing (US3 #3)
            continue
        assert slot.product_id not in no_room
        card, art = slot.card_box, slot.art_box
        assert card[1] > art[3], (card, art)  # right under the foot
        assert card[0] <= art[0] and art[2] <= card[2], (card, art)  # at least as wide as the product
        assert card[3] <= geometry.height - BOTTOM_MARGIN_PX
        _assert_card_clear(layout, geometry, card)
        cards.append(card)
    for a, b in itertools.combinations(cards, 2):
        assert not intersects(a, b), (a, b)
    if desk_top == HIGH_DESK:
        assert cards, layout.issues  # a high desk leaves room for some cards


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("highlight", ALL_IDS)
def test_cards_one_shows_only_the_spoken_product_above_its_side(frame, highlight: str) -> None:
    W, H = frame
    geometry = _geometry(W, H)
    layout = _layout(_products(5), geometry, highlight, params=_params("one"))
    assert [s.product_id for s in layout.slots if s.card_box is not None] == [highlight], layout.issues
    slot = layout.slot(highlight)
    card, side = slot.card_box, SIDES[slot.station]
    # Between the subtitle band and the tops of the products on the same side (research R4).
    assert card[1] >= layout.subtitle_box[3], (card, layout.subtitle_box)
    tops = [s.art_box[1] for s in _shown(layout) if SIDES[s.station] == side]
    assert card[3] <= min(tops), (card, tops)
    hx1, _, hx2, _ = geometry.hands_zone
    assert card[2] <= hx1 if side == "left" else card[0] >= hx2, (card, side)
    _assert_card_clear(layout, geometry, card)
    assert not _no_room(layout)


def test_cards_one_without_a_highlight_shows_no_card() -> None:
    layout = _layout(_products(5), _geometry(), None, params=_params("one"))
    assert all(slot.card_box is None for slot in layout.slots)
    assert not _no_room(layout)


def test_cards_one_falls_back_to_the_bottom_of_its_side_when_the_subtitle_band_is_low() -> None:
    # The face reaches far down, so the subtitle band sits on top of the products: no room above them.
    geometry = estimate_geometry(LABEL, "top-right", face_bottom=560).with_hands_zone(HANDS)
    layout = _at(HIGH_DESK, _products(1), geometry, "kem", _params("one"))
    kem = layout.slot("kem")
    card = kem.card_box
    assert card is not None, layout.issues
    assert card[1] >= kem.art_box[3] and card[3] <= geometry.height - BOTTOM_MARGIN_PX
    assert card[0] >= geometry.hands_zone[2]
    _assert_card_clear(layout, geometry, card)


def test_cards_one_with_no_room_anywhere_hides_the_card_and_warns() -> None:
    geometry = estimate_geometry(LABEL, "top-right", face_bottom=560).with_hands_zone(HANDS)
    layout = _layout(_products(1), geometry, "kem", params=_params("one"))
    assert layout.slot("kem").card_box is None
    assert _no_room(layout) == {"kem"}
    [issue] = [i for i in layout.issues if i.code == "card_no_room"]
    assert issue.message == "Không đủ chỗ cho thẻ của Kem chống nắng; thẻ bị ẩn"


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("highlight", ALL_IDS)
def test_highlight_grows_from_the_middle_of_the_foot_and_leaves_the_others(frame, highlight: str) -> None:
    W, H = frame
    geometry = _geometry(W, H)
    plain = _layout(_products(5), geometry)
    lit = _layout(_products(5), geometry, highlight)
    before, after = plain.slot(highlight).art_box, lit.slot(highlight).art_box
    assert after[3] == before[3]  # the foot stays on the desk (FR-002)
    assert abs((after[0] + after[2]) - (before[0] + before[2])) <= 1
    h_before, h_after = before[3] - before[1], after[3] - after[1]
    assert h_before <= h_after <= round(h_before * 1.04) + 1
    for slot in plain.slots:
        if slot.product_id != highlight:
            assert lit.slot(slot.product_id) == slot
    for zone in [geometry.face_zone, *geometry.keep_out_boxes()]:
        assert not intersects(glow_box(geometry, after), zone), zone


def test_main_product_visibly_grows_when_spoken_about() -> None:
    geometry = _geometry()
    before = _layout(_products(5), geometry).slot("kem").art_box
    after = _layout(_products(5), geometry, "kem").slot("kem").art_box
    assert after[3] - after[1] > before[3] - before[1]


@pytest.mark.parametrize("position", ["top-right", "bottom-right", "bottom-left"])
@pytest.mark.parametrize("highlight", ALL_IDS)
def test_biggest_highlight_is_clamped_clear_of_every_zone(position: str, highlight: str) -> None:
    geometry = _geometry(position=position, label="AI-GENERATED CONTENT ON SCREEN")
    layout = _layout(_products(5), geometry, highlight, params=_params("one", scale=1.10))
    slot = layout.slot(highlight)
    if slot.art_box is None:
        return
    for box in (slot.art_box, slot.shadow_box):
        for zone in _forbidden(geometry):
            assert not intersects(box, zone), (slot, zone)
    for zone in [geometry.face_zone, *geometry.keep_out_boxes()]:
        assert not intersects(glow_box(geometry, slot.art_box), zone), zone


def _cli(monkeypatch: pytest.MonkeyPatch, tmp_path, hands: object, argv: list[str]) -> int:
    """Run the scene CLI on a realistic set with a character whose `scene` block has `hands` (None = no zone)."""
    from PIL import Image

    from ai_live.scene import __main__ as cli
    from fixtures.character_builder import make_character_dir
    from fixtures.scene_builder import CUSTOMER, catalog, make_scene_dir

    ids = ["kem", "toner"]
    root = make_scene_dir(tmp_path / "scenes" / "real", ids, scene={"layout": {"mode": "realistic", "cards": "none"}})
    avatar_dir = make_character_dir(tmp_path / "avatars", desk_in_image=True, desk_top=DESK_TOP, hands_zone=hands)
    still = tmp_path / "idle.png"
    Image.new("RGB", (480, 832), (90, 90, 100)).save(still)
    for key, value in {
        "CUSTOMER_ID": CUSTOMER,
        "AVATAR_DIR": str(avatar_dir),
        "AVATAR_MODE": "static",
        "AVATAR_STATIC_IMAGE": str(still),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cli, "_catalog", lambda path, settings: catalog(*(product(pid) for pid in ids)))
    return cli.main([argv[0], str(root), *argv[1:]])


def test_cli_check_prints_the_layout_mode_and_card_mode(monkeypatch, tmp_path, capsys) -> None:
    assert _cli(monkeypatch, tmp_path, list(HANDS), ["check"]) == 0
    out = capsys.readouterr().out
    assert "realistic" in out
    assert "none" in out
    assert "hands_zone_missing" not in out


def test_cli_check_warns_when_the_character_has_no_hands_zone(monkeypatch, tmp_path, capsys) -> None:
    assert _cli(monkeypatch, tmp_path, None, ["check"]) == 0  # a warning, not an error
    assert "hands_zone_missing" in capsys.readouterr().out


def test_cli_preview_debug_zones_uses_the_character_desk_and_hands(monkeypatch, tmp_path) -> None:
    from PIL import Image

    out = tmp_path / "out.png"
    assert _cli(monkeypatch, tmp_path, list(HANDS), ["preview", "--out", str(out), "--debug-zones"]) == 0
    with Image.open(out) as image:
        frame = image.convert("RGB")
    w, h = frame.size
    desk_y = round(DESK_TOP * h)
    greens = [y for y in range(desk_y - 3, desk_y + 4) if _is_green(frame.getpixel((2, y)))]
    assert greens, "the desk edge must follow the character's desk_top"
    hx1, hy1 = round(HANDS[0] * w), round(HANDS[1] * h)
    r, g, b = frame.getpixel((hx1, hy1 + 2))
    assert r > 120 and b > 200 and g < 80, "the hands zone must come from the character"


def _is_green(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    return g > 150 and r < 80 and b < 80


def test_cli_preview_host_frame_draws_on_the_given_image(monkeypatch, tmp_path) -> None:
    from PIL import Image

    frame_path = tmp_path / "live_frame.png"
    Image.new("RGB", (480, 832), (200, 30, 30)).save(frame_path)
    out = tmp_path / "out.png"
    argv = ["preview", "--out", str(out), "--host-frame", str(frame_path)]
    assert _cli(monkeypatch, tmp_path, list(HANDS), argv) == 0
    with Image.open(out) as image:
        r, g, b = image.convert("RGB").getpixel((240, 40))
    assert r > 150 and g < 80 and b < 80, "the host behind the scene must be the given frame, not the still image"


def test_cli_preview_host_frame_missing_is_an_error(monkeypatch, tmp_path, capsys) -> None:
    argv = ["preview", "--out", str(tmp_path / "out.png"), "--host-frame", str(tmp_path / "nope.png")]
    assert _cli(monkeypatch, tmp_path, list(HANDS), argv) == 1
    assert "host_frame" in capsys.readouterr().out


REAL_HANDS = (0.38, 0.70, 0.73, 0.86)  # demo_host_02: the left side is wider than the right


def _flat_main(highlight=None) -> SceneLayout:
    products = [product("box", primary=True), product("a"), product("b")]
    sizes = {"box": (540, 380), "a": (180, 640), "b": (180, 640)}
    geometry = _geometry(hands=REAL_HANDS)
    return compute_realistic_layout(products, sizes, geometry, PARAMS, highlight, desk_top=0.78)


def test_main_product_moves_to_the_side_where_it_is_drawn_bigger() -> None:
    """A flat main box on the narrow right would be held to its width; the wider left lets it be big (2026-11-23)."""
    layout = _flat_main()
    geometry = _geometry(hands=REAL_HANDS)
    box, a, b = (layout.slot(pid) for pid in ("box", "a", "b"))
    assert box.art_box[2] <= geometry.hands_zone[0]  # left of the hands
    assert a.art_box[0] >= geometry.hands_zone[2] and b.art_box[0] >= geometry.hands_zone[2]
    assert all(_area(box.art_box) > _area(s.art_box) for s in (a, b))
    assert box.art_box[3] > a.art_box[3] > b.art_box[3]  # still in front, the others further back


def test_symmetric_hands_keep_the_main_product_on_the_right() -> None:
    layout = _layout(_products(3), _geometry())
    assert layout.slot("kem").art_box[0] >= _geometry().hands_zone[2]


@pytest.mark.parametrize("highlight", ["box", "a", "b"])
def test_highlight_never_moves_the_main_product_to_the_other_side(highlight) -> None:
    plain, lit = _flat_main(), _flat_main(highlight)
    for pid in ("box", "a", "b"):
        if pid != highlight:
            assert lit.slot(pid).art_box == plain.slot(pid).art_box
