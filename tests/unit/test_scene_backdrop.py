"""014 T019: the `ke_hang` backdrop drawn behind the host (adapters.md §2, R10, R11; FR-006, FR-007)."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from ai_live.scene.backdrop import BackdropResult, LightStats, render_backdrop, shelf_geometry
from ai_live.scene.models import BackgroundConfig

SIZE = (480, 832)
DESK_TOP_PX = 640

RED = (220, 20, 20, 255)
BLUE = (20, 40, 220, 255)


def art_image(color: tuple[int, int, int, int], size: tuple[int, int] = (120, 200)) -> Image.Image:
    """A cut-out bottle: one flat colour inside, transparent corners."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=20, fill=color)
    return image


def config(**kw) -> BackgroundConfig:
    return BackgroundConfig(**{"style": "ke_hang", **kw})


def decoded(result: BackdropResult) -> np.ndarray:
    assert result.png is not None
    image = Image.open(io.BytesIO(result.png))
    assert image.mode == "RGB"
    return np.asarray(image).astype(np.int32)


def luma(rgb: np.ndarray) -> float:
    return float((0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).mean())


def rb(rgb: np.ndarray) -> float:
    return float(rgb[..., 0].mean() - rgb[..., 2].mean())


def dominant(rgb: np.ndarray, channel: int, margin: int = 60) -> np.ndarray:
    others = [c for c in range(3) if c != channel]
    return (rgb[..., channel] > rgb[..., others[0]] + margin) & (rgb[..., channel] > rgb[..., others[1]] + margin)


def test_plate_is_an_rgb_png_of_the_frame_size() -> None:
    result = render_backdrop(config(), {"a": art_image(RED)}, SIZE, DESK_TOP_PX, None)
    image = Image.open(io.BytesIO(result.png or b""))
    assert image.format == "PNG" and image.mode == "RGB" and image.size == SIZE
    assert result.reason is None


def test_only_the_scene_set_products_are_on_the_shelves() -> None:
    result = render_backdrop(
        config(softness_px=0.0), {"a": art_image(RED), "b": art_image(BLUE)}, SIZE, DESK_TOP_PX, None
    )
    rgb = decoded(result)
    assert set(result.items) == {"a", "b"}
    assert dominant(rgb, 0).sum() > 500  # red bottles
    assert dominant(rgb, 2).sum() > 500  # blue bottles
    assert dominant(rgb, 1).sum() == 0  # no green: no product outside the set, no third-party picture


def test_shelf_products_are_small_and_above_the_desk() -> None:
    rgb = decoded(render_backdrop(config(softness_px=0.0), {"a": art_image(RED)}, SIZE, DESK_TOP_PX, None))
    ys = np.nonzero(dominant(rgb, 0))[0]
    assert ys.max() < DESK_TOP_PX
    # every single bottle is far shorter than a desk product (013 puts ~20-30% of the frame height on the desk).
    # The tiers slant toward the back shelf (ADR-086), so a bottle is measured down each column, not across rows.
    red = dominant(rgb, 0)
    tallest = 0
    for column in red.T:
        rows = np.nonzero(column)[0]
        if rows.size:
            runs = np.split(rows, np.nonzero(np.diff(rows) > 1)[0] + 1)
            tallest = max(tallest, *(len(r) for r in runs))
    assert 0 < tallest <= 0.1 * SIZE[1]


def test_no_text_is_ever_drawn(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_text(*args, **kwargs):
        raise AssertionError("the backdrop must not draw text (FR-007)")

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", no_text)
    monkeypatch.setattr(ImageDraw.ImageDraw, "multiline_text", no_text)
    result = render_backdrop(config(), {"a": art_image(RED)}, SIZE, DESK_TOP_PX, None)
    assert result.png is not None


def test_products_cycle_up_to_max_items() -> None:
    result = render_backdrop(config(max_items=5), {"a": art_image(RED), "b": art_image(BLUE)}, SIZE, DESK_TOP_PX, None)
    assert result.items == ("a", "b", "a", "b", "a")


def test_a_one_product_shop_repeats_that_product() -> None:
    result = render_backdrop(config(max_items=3), {"a": art_image(RED)}, SIZE, DESK_TOP_PX, None)
    assert result.items == ("a", "a", "a")


def test_no_product_art_means_no_plate() -> None:
    result = render_backdrop(config(), {}, SIZE, DESK_TOP_PX, None)
    assert (result.png, result.items, result.reason) == (None, (), "no_product_art")


@pytest.mark.parametrize("style", ["bang_shop"])
def test_later_styles_are_not_available_yet(style: str) -> None:
    result = render_backdrop(config(style=style), {"a": art_image(RED)}, SIZE, DESK_TOP_PX, None)
    assert (result.png, result.reason) == (None, "style_not_available")


def test_goc_draws_nothing() -> None:
    result = render_backdrop(BackgroundConfig(style="goc"), {"a": art_image(RED)}, SIZE, DESK_TOP_PX, None)
    assert (result.png, result.reason) == (None, "style_goc")


def sharpness(rgb: np.ndarray) -> float:
    gray = rgb[:DESK_TOP_PX].mean(axis=2)
    return float(np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean())


def test_softness_blurs_the_plate() -> None:
    art = {"a": art_image(RED), "b": art_image(BLUE)}
    sharp = decoded(render_backdrop(config(softness_px=0.0), art, SIZE, DESK_TOP_PX, None))
    soft = decoded(render_backdrop(config(softness_px=3.0), art, SIZE, DESK_TOP_PX, None))
    assert sharpness(soft) < 0.8 * sharpness(sharp)


def light(room_luma: float, room_rb: float) -> LightStats:
    return LightStats(person_luma=120.0, person_rb=30.0, room_luma=room_luma, room_rb=room_rb)


def test_mean_brightness_matches_the_old_room_times_brightness() -> None:
    art = {"a": art_image(RED), "b": art_image(BLUE)}
    for room_luma, brightness in ((100.0, 0.95), (160.0, 1.0), (140.0, 0.8)):
        rgb = decoded(render_backdrop(config(brightness=brightness), art, SIZE, DESK_TOP_PX, light(room_luma, 0.0)))
        assert luma(rgb[:DESK_TOP_PX]) == pytest.approx(room_luma * brightness, abs=3.0)


def test_white_balance_moves_toward_the_old_room_capped_at_12() -> None:
    art = {"a": art_image(RED), "b": art_image(BLUE)}

    def plate_rb(room_rb: float) -> float:
        rgb = decoded(render_backdrop(config(), art, SIZE, DESK_TOP_PX, light(130.0, room_rb)))
        return rb(rgb[:DESK_TOP_PX])

    warm, cold = plate_rb(1000.0), plate_rb(-1000.0)
    assert warm - cold == pytest.approx(24.0, abs=3.0)  # each side capped at 12
    natural = (warm + cold) / 2
    assert plate_rb(natural + 5.0) == pytest.approx(natural + 5.0, abs=2.0)  # within the cap: reached


def test_light_stats_read_from_a_manifest() -> None:
    stats = LightStats.from_manifest({"person_luma": 1, "person_rb": 2, "room_luma": 3.5, "room_rb": -4})
    assert stats == LightStats(person_luma=1.0, person_rb=2.0, room_luma=3.5, room_rb=-4.0)
    assert LightStats.from_manifest({"room_luma": "x"}) is None
    assert LightStats.from_manifest(None) is None


def test_two_customers_never_share_products() -> None:
    first = render_backdrop(config(), {"shop1_a": art_image(RED)}, SIZE, DESK_TOP_PX, None)
    second = render_backdrop(config(), {"shop2_b": art_image(BLUE)}, SIZE, DESK_TOP_PX, None)
    assert set(first.items) == {"shop1_a"} and set(second.items) == {"shop2_b"}
    assert dominant(decoded(second), 0).sum() == 0  # no red bottle from the first shop


# ---------- 014 T071: a dense, deep shelf aisle that keeps its contrast (FR-018, ADR-086) ----------

GREEN = (30, 200, 40, 255)
BRIGHT_ROOM = light(183.0, 18.0)  # demo_host_02: a bright room, the case that washed the old plate out


def stocked(**kw) -> np.ndarray:
    art = {"a": art_image(RED), "b": art_image(BLUE)}
    return decoded(render_backdrop(config(softness_px=0.0, **kw), art, SIZE, DESK_TOP_PX, BRIGHT_ROOM))


def product_pixels(rgb: np.ndarray) -> np.ndarray:
    return (dominant(rgb, 0) | dominant(rgb, 2))[:DESK_TOP_PX]


def test_the_shelves_are_stocked_across_the_whole_width() -> None:
    goods = product_pixels(stocked())
    bins = goods.reshape(DESK_TOP_PX, SIZE[0] // 16, 16).any(axis=(0, 2))
    assert bins.all()  # no empty strip of wall: every 16 px column holds product
    assert goods.mean() > 0.15  # stocked, not a few bottles on bare boards


def test_the_aisle_has_side_shelves_and_a_smaller_darker_back_shelf() -> None:
    aisle = shelf_geometry(SIZE[0], SIZE[1], DESK_TOP_PX)
    bx1, by1, bx2, by2 = aisle.back
    assert 0 < bx1 < bx2 < SIZE[0] and bx2 - bx1 < 0.7 * SIZE[0]
    # The back shelf spans every board line where the side shelves meet it.
    for inner in aisle.inner_lines:
        assert by1 - 1 <= inner <= by2 + 1
    outer_h = np.diff(aisle.outer_lines)
    inner_h = np.diff(aisle.inner_lines)
    assert (inner_h < 0.8 * outer_h).all()
    rgb = stocked()
    gray = rgb.mean(axis=2)
    back = gray[by1 : min(by2, DESK_TOP_PX), bx1:bx2].mean()
    sides = np.concatenate([gray[:DESK_TOP_PX, : bx1 // 2].ravel(), gray[:DESK_TOP_PX, SIZE[0] - bx1 // 2 :].ravel()])
    assert back < sides.mean() - 10


def test_matching_a_bright_room_keeps_contrast_and_colour() -> None:
    rgb = stocked()
    room = rgb[:DESK_TOP_PX]
    assert luma(room) == pytest.approx(183.0 * 0.95, abs=3.0)
    y = 0.299 * room[..., 0] + 0.587 * room[..., 1] + 0.114 * room[..., 2]
    p25, p75 = np.percentile(y, [25, 75])
    assert p75 - p25 > 40  # not a flat pale wall with a few bottles: the old plate had half its pixels within ~5 luma
    top, bottom = room.max(axis=2), room.min(axis=2)
    assert ((top - bottom) / np.maximum(top, 1)).mean() > 0.25  # mean saturation: colour, not grey (old plate: 0.17)
    assert (room >= 254).any(axis=2).mean() < 0.05  # not blown out to white
    assert dominant(room, 0).mean() > 0.04 and dominant(room, 2).mean() > 0.04  # the products keep their colour


def test_a_dense_shelf_still_shows_only_the_shops_products() -> None:
    rgb = stocked(max_items=24)
    assert dominant(rgb, 1).sum() == 0
    alone = decoded(render_backdrop(config(), {"g": art_image(GREEN)}, SIZE, DESK_TOP_PX, BRIGHT_ROOM))
    assert dominant(alone, 0, margin=80).sum() == 0 and dominant(alone, 2, margin=80).sum() == 0


def test_the_same_set_gives_the_same_plate_every_time() -> None:
    art = {"a": art_image(RED), "b": art_image(BLUE)}
    first = render_backdrop(config(), art, SIZE, DESK_TOP_PX, BRIGHT_ROOM)
    second = render_backdrop(config(), dict(art), SIZE, DESK_TOP_PX, BRIGHT_ROOM)
    assert first.png == second.png and first.items == second.items
