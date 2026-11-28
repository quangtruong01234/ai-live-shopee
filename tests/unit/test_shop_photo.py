"""014 T082-T085 (ADR-100): the `anh_shop` background, a confirmed shop photo behind the host (FR-009, FR-009a)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from ai_live.core.events import EventBus
from ai_live.core.protocols import ForkBackgroundStatus
from ai_live.scene.__main__ import main as scene_cli
from ai_live.scene.backdrop import LightStats, render_backdrop
from ai_live.scene.background import BackgroundController, fallback_text
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import BackgroundConfig
from ai_live.scene.shop_photo import (
    AI_MIN_SOFTNESS_PX,
    CONFIRMATION_NAME,
    PHOTO_DIR,
    ShopPhoto,
    ShopPhotoError,
    load_shop_photo,
    save_shop_photo,
)
from fixtures.background_builder import CHARACTER_ID, make_background_dir
from fixtures.fake_fork import FakeFork
from fixtures.scene_builder import make_scene_dir

pytestmark = pytest.mark.anyio

SIZE = (480, 832)
DESK_TOP_PX = 640
ANH_SHOP = {"background": {"style": "anh_shop", "softness_px": 0}}


def stripes(path: Path, size: tuple[int, int] = (300, 1000)) -> Path:
    """A wide-band test picture: thin black/white stripes (the 'small text') over a red top and a blue bottom."""
    image = Image.new("RGB", size, (200, 40, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, size[1] // 2, size[0], size[1]), fill=(40, 40, 200))
    for x in range(0, size[0], 4):
        draw.line((x, 0, x, size[1] // 10), fill=(0, 0, 0))
    image.save(path)
    return path


def decoded(png: bytes | None) -> np.ndarray:
    assert png is not None
    image = Image.open(io.BytesIO(png))
    assert image.mode == "RGB" and image.size == SIZE
    return np.asarray(image).astype(np.int32)


def scene_root(tmp_path: Path, scene: dict | None = None) -> Path:
    return make_scene_dir(tmp_path / "scenes" / "demo", ["a"], scene=scene or ANH_SHOP, distinct_colors=True)


# ---------- load / save (data-model §3) ----------


def test_no_photo_file_is_no_shop_photo(tmp_path: Path) -> None:
    assert load_shop_photo(tmp_path).reason == "no_shop_photo"


def test_a_photo_without_confirmation_is_unconfirmed(tmp_path: Path) -> None:
    (tmp_path / PHOTO_DIR).mkdir()
    stripes(tmp_path / PHOTO_DIR / "shop_photo.png")
    photo = load_shop_photo(tmp_path)
    assert (photo.image, photo.reason) == (None, "shop_photo_unconfirmed")


def test_saved_photo_loads_with_its_confirmation(tmp_path: Path) -> None:
    photo = save_shop_photo(tmp_path, stripes(tmp_path / "in.png"), confirmed_by="Quang", source="ai_generated")
    assert photo.image is not None and photo.reason is None
    assert (photo.source, photo.confirmed_by) == ("ai_generated", "Quang")
    record = json.loads((tmp_path / PHOTO_DIR / CONFIRMATION_NAME).read_text(encoding="utf-8"))
    assert record["source"] == "ai_generated" and record["confirmed_at"] and record["sha256"] == photo.sha256


def test_a_changed_file_needs_a_new_confirmation(tmp_path: Path) -> None:
    save_shop_photo(tmp_path, stripes(tmp_path / "in.png"), confirmed_by="Quang", source="photo")
    stripes(tmp_path / PHOTO_DIR / "shop_photo.png", (310, 1000))  # swapped after the confirmation
    assert load_shop_photo(tmp_path).reason == "shop_photo_unconfirmed"


@pytest.mark.parametrize("field", ["confirmed_by", "confirmed_at", "sha256", "source"])
def test_a_confirmation_missing_a_field_is_unconfirmed(tmp_path: Path, field: str) -> None:
    save_shop_photo(tmp_path, stripes(tmp_path / "in.png"), confirmed_by="Quang", source="photo")
    path = tmp_path / PHOTO_DIR / CONFIRMATION_NAME
    record = json.loads(path.read_text(encoding="utf-8"))
    del record[field]
    path.write_text(json.dumps(record), encoding="utf-8")
    assert load_shop_photo(tmp_path).reason == "shop_photo_unconfirmed"


def test_save_needs_a_name_and_an_image(tmp_path: Path) -> None:
    with pytest.raises(ShopPhotoError):
        save_shop_photo(tmp_path, stripes(tmp_path / "in.png"), confirmed_by="  ", source="photo")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ShopPhotoError):
        save_shop_photo(tmp_path, bad, confirmed_by="Quang", source="photo")
    assert not (tmp_path / PHOTO_DIR / CONFIRMATION_NAME).exists()


def test_save_replaces_a_photo_of_another_format(tmp_path: Path) -> None:
    save_shop_photo(tmp_path, stripes(tmp_path / "in.png"), confirmed_by="Quang", source="photo")
    jpg = tmp_path / "in.jpg"
    Image.open(tmp_path / "in.png").save(jpg)
    save_shop_photo(tmp_path, jpg, confirmed_by="Quang", source="photo")
    assert {p.name for p in (tmp_path / PHOTO_DIR).iterdir()} == {CONFIRMATION_NAME, "shop_photo.jpg"}
    assert load_shop_photo(tmp_path).image is not None


# ---------- the plate (FR-009, FR-009a) ----------


def photo_of(tmp_path: Path, source: str = "photo", size: tuple[int, int] = (300, 1000)) -> ShopPhoto:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return save_shop_photo(tmp_path, stripes(tmp_path / "in.png", size), confirmed_by="Quang", source=source)


def test_plate_covers_the_frame_without_stretching(tmp_path: Path) -> None:
    # 300x1000 is narrower than 480:832: cover scales to 480 wide and crops top and bottom, never squeezes.
    config = BackgroundConfig(style="anh_shop", softness_px=0, brightness=1.0)
    result = render_backdrop(config, {}, SIZE, DESK_TOP_PX, None, photo_of(tmp_path))
    rgb = decoded(result.png)
    assert (result.reason, result.items) == (None, ())
    # Scaled 1.6x to 480x1600, cropped 384 px off the top: the stripes band (top 160 px) is gone, red then blue remain.
    assert rgb[10, :, 0].mean() > rgb[10, :, 2].mean() + 50
    assert rgb[-10, :, 2].mean() > rgb[-10, :, 0].mean() + 50


def test_ai_generated_photo_is_never_sharper_than_the_minimum(tmp_path: Path) -> None:
    sharp = BackgroundConfig(style="anh_shop", softness_px=0, brightness=1.0)
    tall = (480, 832)  # same aspect as the frame: no crop, so the stripes stay in the top rows
    real_photo = photo_of(tmp_path / "r", "photo", tall)
    ai_photo = photo_of(tmp_path / "g", "ai_generated", tall)
    real = decoded(render_backdrop(sharp, {}, SIZE, DESK_TOP_PX, None, real_photo).png)
    ai = decoded(render_backdrop(sharp, {}, SIZE, DESK_TOP_PX, None, ai_photo).png)
    # Stripe contrast along a row: the real photo keeps it (softness 0), the AI one is blurred flat.
    assert real[20, 20:-20, 1].std() > 12
    assert ai[20, 20:-20, 1].std() < 2
    assert AI_MIN_SOFTNESS_PX >= 4


def test_as_is_sends_the_ai_photo_unblurred_and_ungraded(tmp_path: Path) -> None:
    """FR-009a exception (ADR-102): the OBS layer scene gets the cover-cropped photo pixel for pixel."""
    tall = (480, 832)
    photo = photo_of(tmp_path, "ai_generated", tall)
    config = BackgroundConfig(style="anh_shop", softness_px=3, brightness=0.8, as_is=True)
    light = LightStats(person_luma=80, person_rb=0, room_luma=200, room_rb=-30)
    rgb = decoded(render_backdrop(config, {}, SIZE, DESK_TOP_PX, light, photo).png)
    assert np.array_equal(rgb, np.asarray(photo.image.convert("RGB")))


def test_missing_or_unconfirmed_photo_draws_nothing(tmp_path: Path) -> None:
    config = BackgroundConfig(style="anh_shop")
    assert render_backdrop(config, {}, SIZE, DESK_TOP_PX, None).reason == "no_shop_photo"
    unconfirmed = ShopPhoto(None, "shop_photo_unconfirmed")
    result = render_backdrop(config, {}, SIZE, DESK_TOP_PX, None, unconfirmed)
    assert (result.png, result.reason) == (None, "shop_photo_unconfirmed")


def test_the_photo_does_not_need_product_art(tmp_path: Path) -> None:
    result = render_backdrop(BackgroundConfig(style="anh_shop"), {}, SIZE, DESK_TOP_PX, None, photo_of(tmp_path))
    assert result.png is not None and result.reason is None


# ---------- loader, controller, CLI ----------


def test_loader_reads_the_photo_only_for_anh_shop(tmp_path: Path) -> None:
    root = scene_root(tmp_path)
    assert load_scene_set(root, ["a"]).shop_photo.reason == "no_shop_photo"  # type: ignore[union-attr]
    save_shop_photo(root, stripes(tmp_path / "in.png"), confirmed_by="Quang", source="photo")
    assert load_scene_set(root, ["a"]).shop_photo.image is not None  # type: ignore[union-attr]
    other = make_scene_dir(tmp_path / "scenes" / "kh", ["a"], scene={"background": {"style": "ke_hang"}})
    assert load_scene_set(other, ["a"]).shop_photo is None


class Sink:
    """Just enough of `LiveTalkingRenderer` for the background: keeps the plate, reports a valid mask on `hello`."""

    def __init__(self) -> None:
        self.listeners: list = []
        self.plate: bytes | None = None

    def set_scene_background(self, plate_png: bytes | None) -> None:
        self.plate = plate_png

    def add_background_status_listener(self, listener) -> None:  # type: ignore[no-untyped-def]
        self.listeners.append(listener)

    def hello(self) -> None:
        status = ForkBackgroundStatus.from_hello(FakeFork.background_block())
        for listener in self.listeners:
            listener(status)


async def controller_for(tmp_path: Path, root: Path) -> tuple[BackgroundController, Sink]:
    avatar = tmp_path / "avatars" / CHARACTER_ID
    avatar.mkdir(parents=True)
    make_background_dir(avatar, "valid")
    sink = Sink()
    controller = BackgroundController(sink, EventBus(), avatar)
    await controller.start()
    await controller.on_scene_loaded(load_scene_set(root, ["a"]))
    sink.hello()
    return controller, sink


async def test_controller_falls_back_until_the_photo_is_confirmed(tmp_path: Path) -> None:
    controller, sink = await controller_for(tmp_path, scene_root(tmp_path))
    status = controller.status()
    assert (status["active"], status["fallback_reason"]) == (False, "no_shop_photo")
    assert "shop-photo" in status["fallback_message"]
    assert sink.plate is None


async def test_controller_shows_a_confirmed_photo(tmp_path: Path) -> None:
    root = scene_root(tmp_path)
    save_shop_photo(root, stripes(tmp_path / "in.png"), confirmed_by="Quang", source="ai_generated")
    controller, sink = await controller_for(tmp_path, root)
    status = controller.status()
    assert (status["active"], status["fallback_reason"], status["items"]) == (True, None, [])
    assert decoded(sink.plate).shape == (SIZE[1], SIZE[0], 3)


def test_fallback_texts_name_the_fix() -> None:
    for reason in ("no_shop_photo", "shop_photo_unconfirmed"):
        problem, fix = fallback_text(reason, "demo_host_01", style="anh_shop") or ("", "")
        assert "ảnh shop" in problem.lower() and "--confirmed-by" in fix


def test_cli_saves_an_ai_generated_photo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = scene_root(tmp_path)
    image = stripes(tmp_path / "gemini.png")
    code = scene_cli(["shop-photo", str(root), str(image), "--confirmed-by", "Quang", "--ai-generated"])
    assert code == 0, capsys.readouterr().out
    photo = load_shop_photo(root)
    assert (photo.source, photo.confirmed_by) == ("ai_generated", "Quang")
