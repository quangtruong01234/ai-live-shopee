"""009 T012, T028: the drawn layers. Transparent where the face, the "AI" label and the watermark are; fast enough."""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from PIL import Image

from ai_live.scene.fonts import SceneFontError, SceneFonts, load_fonts
from ai_live.scene.layout import card_text, compute_layout, estimate_geometry, price_text
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import FrameGeometry, LayoutParams, SceneLayer, SceneSet
from ai_live.scene.render import compose_still, render_base, render_subtitle
from fixtures.scene_builder import CUSTOMER, demo_catalog, make_scene_dir

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
