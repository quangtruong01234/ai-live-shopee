"""Background removal of uploaded product photos (specs/013-realistic-desk-products research R5–R8, data-model §6, §9).

The model never runs here: `tests/fixtures/fake_matting.py` (T005) stands in for the child process.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from ai_live.scene import matting
from ai_live.scene.matting import (
    BORDER_FG_MAX,
    FG_RATIO_MAX,
    FG_RATIO_MIN,
    LARGEST_COMPONENT_MIN,
    LIVE_REASON,
    MODEL_UNSURE_REASON,
    NO_MODEL_REASON,
    TIMEOUT_REASON,
    UNCERTAIN_MAX,
    assess_cut,
    postprocess,
    preprocess,
    remove_background,
    remove_flat_background,
)
from fixtures import fake_matting
from fixtures.scene_builder import PRODUCT_COLOR, matting_box, matting_image

pytestmark = pytest.mark.anyio

METRIC_KEYS = {"fg_ratio", "border_fg_ratio", "uncertain_ratio", "largest_component_ratio"}


def _rgba(kind: str, size: tuple[int, int] = (320, 400)) -> Image.Image:
    return matting_image(kind, size).convert("RGBA")  # type: ignore[arg-type]


# --- T030: flat backgrounds (R5) ----------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["white_bg", "flat_gray_bg", "flat_blue_bg"])
def test_flat_background_is_removed(kind: str) -> None:
    cut = remove_flat_background(_rgba(kind))
    assert (cut.result, cut.method, cut.reason) == ("removed", "flat", None)
    assert cut.image is not None and cut.image.mode == "RGBA"
    alpha = np.asarray(cut.image.getchannel("A"))
    # Cropped to the alpha box: every outer row and column keeps at least one visible pixel ...
    assert alpha[0].any() and alpha[-1].any() and alpha[:, 0].any() and alpha[:, -1].any()
    # ... and the corners, background in the source, are see-through.
    assert alpha[0, 0] == alpha[0, -1] == alpha[-1, 0] == alpha[-1, -1] == 0
    assert set(cut.metrics) == METRIC_KEYS


def test_cut_is_cropped_to_the_product_box() -> None:
    x1, y1, x2, y2 = matting_box("white_bg")
    cut = remove_flat_background(_rgba("white_bg"))
    assert cut.image is not None
    width, height = x2 - x1 + 1, y2 - y1 + 1
    # The soft edge may spread or shrink the box by a couple of pixels, never more.
    assert abs(cut.image.width - width) <= 4
    assert abs(cut.image.height - height) <= 4


@pytest.mark.parametrize("kind", ["white_bg", "flat_blue_bg", "white_inside"])
def test_only_alpha_changes(kind: str) -> None:
    source = _rgba(kind)
    cut = remove_flat_background(source)
    assert cut.image is not None
    bbox = _crop_box(source, cut.image)
    original = np.asarray(source.crop(bbox))
    result = np.asarray(cut.image)
    visible = result[..., 3] > 0
    assert np.array_equal(result[..., :3][visible], original[..., :3][visible])


def _crop_box(source: Image.Image, cut: Image.Image) -> tuple[int, int, int, int]:
    """Where the cut sits in the source, found from where the product colour starts in each picture.

    Visible (alpha > 0), not fully opaque: the soft edge (R5) makes the product's outer pixels partly see-through.
    """
    src = (np.asarray(source)[..., :3] == PRODUCT_COLOR).all(axis=-1)
    out = (np.asarray(cut)[..., :3] == PRODUCT_COLOR).all(axis=-1) & (np.asarray(cut)[..., 3] > 0)
    src_ys, src_xs = np.nonzero(src)
    out_ys, out_xs = np.nonzero(out)
    left = int(src_xs.min() - out_xs.min())
    top = int(src_ys.min() - out_ys.min())
    return (left, top, left + cut.width, top + cut.height)


def test_white_label_inside_the_product_is_kept() -> None:
    """US2 #4: background-coloured pixels not connected to the border stay."""
    source = _rgba("white_inside")
    x1, y1, x2, y2 = matting_box("white_inside")
    cut = remove_flat_background(source)
    assert cut.result == "removed"
    assert cut.image is not None
    left, top, _, _ = _crop_box(source, cut.image)
    alpha = np.asarray(cut.image.getchannel("A"))
    rgb = np.asarray(cut.image)[..., :3]
    # The white label sits at (x1 + 15 .. x2 - 15, y1 + 20 .. y1 + 20 + h/3), with "LABEL" text near its top:
    # below the text it is fully opaque and still white.
    label = (slice(y1 + 50 - top, y1 + 100 - top), slice(x1 + 40 - left, x2 - 40 - left))
    assert (alpha[label] == 255).all()
    assert (rgb[label] == 255).all()


def test_soft_edge_only_touches_pixels_near_the_edge() -> None:
    source = _rgba("white_bg")
    cut = remove_flat_background(source)
    assert cut.image is not None
    left, top, _, _ = _crop_box(source, cut.image)
    x1, y1, x2, y2 = matting_box("white_bg")
    alpha = np.asarray(cut.image.getchannel("A"))
    ys, xs = np.nonzero((alpha > 0) & (alpha < 255))
    assert len(ys) > 0
    for y, x in zip(ys + top, xs + left, strict=True):
        distance = min(abs(x - x1), abs(x - x2), abs(y - y1), abs(y - y2))
        assert distance <= 3, (x, y)
    # Deep inside the product nothing changed.
    inner = alpha[y1 + 5 - top : y2 - 5 - top, x1 + 5 - left : x2 - 5 - left]
    assert (inner == 255).all()


def test_border_mostly_off_colour_is_not_flat() -> None:
    """Fewer than 90% of border pixels within Chebyshev 28 of the median: not a flat background."""
    image = _rgba("white_bg")
    draw = ImageDraw.Draw(image)
    w, h = image.size
    # Paint 15% of every side a far colour (distance 60 > 28): 85% of the border stays near white.
    for x in range(0, w, 20):
        draw.rectangle((x, 0, x + 2, 1), fill=(195, 195, 195, 255))
        draw.rectangle((x, h - 2, x + 2, h - 1), fill=(195, 195, 195, 255))
    for y in range(0, h, 20):
        draw.rectangle((0, y, 1, y + 2), fill=(195, 195, 195, 255))
        draw.rectangle((w - 2, y, w - 1, y + 2), fill=(195, 195, 195, 255))
    cut = remove_flat_background(image)
    assert cut.result == "failed"
    assert cut.image is None


def test_border_close_to_the_median_still_counts_as_flat() -> None:
    """Pixels within Chebyshev 28 of the border colour are background: a light gradient is still flat."""
    image = _rgba("white_bg")
    w, h = image.size
    pixels = image.load()
    assert pixels is not None
    for y in range(h):
        for x in range(w):
            if pixels[x, y] == (255, 255, 255, 255):
                shade = 255 - (x * 20) // w  # 255 .. 236, within 28 of the median
                pixels[x, y] = (shade, shade, shade, 255)
    cut = remove_flat_background(image)
    assert cut.result == "removed"


def test_noisy_background_is_not_flat() -> None:
    cut = remove_flat_background(_rgba("noisy_bg"))
    assert cut.result == "failed"


async def test_transparent_png_is_kept() -> None:
    """US2 #2: a picture that already has see-through pixels is not touched."""
    settings = SimpleNamespace(matting_model_path=None, matting_during_show=True)
    image = matting_image("transparent")
    cut = await remove_background(image, show_running=False, settings=settings)
    assert (cut.result, cut.method, cut.image) == ("kept", "already_transparent", None)


async def test_has_alpha_flag_wins_over_a_cropped_opaque_picture() -> None:
    """A 012 upload is cropped to its alpha box, so its pixels may all be opaque although the source had alpha."""
    settings = SimpleNamespace(matting_model_path=None, matting_during_show=True)
    cut = await remove_background(_rgba("white_bg"), has_alpha=True, show_running=False, settings=settings)
    assert (cut.result, cut.method) == ("kept", "already_transparent")


# --- T031: confidence check (R8) ----------------------------------------------------------------------------------


def _alpha(size: tuple[int, int] = (200, 200)) -> np.ndarray:
    return np.zeros((size[1], size[0]), dtype=np.uint8)


def test_thresholds_are_the_research_values() -> None:
    assert (FG_RATIO_MIN, FG_RATIO_MAX, BORDER_FG_MAX, UNCERTAIN_MAX, LARGEST_COMPONENT_MIN) == (
        0.05,
        0.95,
        0.25,
        0.12,
        0.85,
    )


def test_a_clean_box_passes() -> None:
    alpha = _alpha()
    alpha[50:150, 60:140] = 255
    check = assess_cut(alpha, flat=True)
    assert check.ok and check.reason is None
    assert set(check.metrics) == METRIC_KEYS
    assert check.metrics["fg_ratio"] == pytest.approx(0.2)
    assert check.metrics["border_fg_ratio"] == 0
    assert check.metrics["largest_component_ratio"] == 1


def test_almost_nothing_left_fails() -> None:
    alpha = _alpha()
    alpha[90:100, 90:100] = 255  # 0.25%
    check = assess_cut(alpha, flat=True)
    assert not check.ok
    assert check.reason == "gần như không còn gì sau khi bỏ nền"


def test_almost_everything_kept_fails() -> None:
    alpha = np.full((200, 200), 255, dtype=np.uint8)
    alpha[0:3, 0:3] = 0
    check = assess_cut(alpha, flat=False)
    assert not check.ok
    assert check.reason == "không tách được nền"


def test_product_touching_the_border_fails() -> None:
    alpha = _alpha()
    alpha[:, 40:160] = 255  # top and bottom rows: 60% of them is product
    check = assess_cut(alpha, flat=False)
    assert not check.ok
    assert check.metrics["border_fg_ratio"] > BORDER_FG_MAX
    assert check.reason == "sản phẩm dính viền ảnh, có thể bị cắt hoặc nền chưa bỏ hết"


def test_blurry_edges_fail() -> None:
    alpha = _alpha()
    alpha[40:160, 40:160] = 128  # all of it half see-through
    alpha[60:140, 60:140] = 255
    check = assess_cut(alpha, flat=False)
    assert not check.ok
    assert check.metrics["uncertain_ratio"] > UNCERTAIN_MAX
    assert check.reason == "mép sản phẩm nhòe, không chắc đã tách đúng"


def test_broken_pieces_fail_only_for_the_flat_method() -> None:
    alpha = _alpha()
    alpha[20:100, 20:100] = 255
    alpha[120:180, 120:180] = 255  # second piece: largest is 64% of the total
    flat = assess_cut(alpha, flat=True)
    assert not flat.ok
    assert flat.metrics["largest_component_ratio"] < LARGEST_COMPONENT_MIN
    assert flat.reason == "sản phẩm bị vỡ thành nhiều mảnh, có thể đã khoét mất phần cùng màu nền"
    assert assess_cut(alpha, flat=False).ok


def test_pieces_touching_by_a_corner_only_are_separate() -> None:
    alpha = _alpha()
    alpha[20:100, 20:100] = 255
    alpha[100:180, 100:180] = 255
    assert assess_cut(alpha, flat=True).metrics["largest_component_ratio"] == pytest.approx(0.5)


def test_white_box_on_white_fails_instead_of_a_hollowed_cut() -> None:
    """US2 #4, FR-014: a pure white product on white has no edge; the result is a failure, never a carved picture."""
    image = Image.new("RGBA", (320, 400), (255, 255, 255, 255))
    ImageDraw.Draw(image).rectangle((80, 66, 240, 333), fill=(250, 250, 250, 255))
    cut = remove_flat_background(image)
    assert cut.result == "failed"
    assert cut.image is None
    assert cut.reason
    assert set(cut.metrics) == METRIC_KEYS


# --- T032: the model (R6, R7) ---------------------------------------------------------------------------------------


def test_isnet_preprocessing() -> None:
    image = Image.new("RGB", (300, 200), (100, 50, 200))
    tensor = preprocess(image, "isnet")
    assert tensor.shape == (1, 3, 1024, 1024)
    assert tensor.dtype == np.float32
    # Divided by the picture's maximum (200), not 255, then minus 0.5.
    assert tensor[0, 0, 10, 10] == pytest.approx(100 / 200 - 0.5, abs=1e-3)
    assert tensor[0, 1, 10, 10] == pytest.approx(50 / 200 - 0.5, abs=1e-3)
    assert tensor[0, 2, 10, 10] == pytest.approx(1 - 0.5, abs=1e-3)


def test_birefnet_preprocessing_uses_imagenet_mean_and_std() -> None:
    image = Image.new("RGB", (64, 64), (200, 200, 200))
    tensor = preprocess(image, "birefnet")
    assert tensor.shape == (1, 3, 1024, 1024)
    assert tensor[0, 0, 0, 0] == pytest.approx((1 - 0.485) / 0.229, abs=1e-3)
    assert tensor[0, 2, 0, 0] == pytest.approx((1 - 0.406) / 0.225, abs=1e-3)


def test_isnet_postprocessing_stretches_min_max_and_resizes() -> None:
    raw = np.full((1, 1, 1024, 1024), 2.0, dtype=np.float32)
    raw[0, 0, :512] = -3.0
    mask = postprocess(raw, (300, 200), "isnet")
    assert mask.mode == "L" and mask.size == (300, 200)
    pixels = np.asarray(mask)
    assert pixels[5, 150] == 0 and pixels[195, 150] == 255


def test_birefnet_postprocessing_applies_sigmoid_before_stretching() -> None:
    raw = np.zeros((1, 1, 1024, 1024), dtype=np.float32)
    raw[0, 0, :, :256] = -10.0
    raw[0, 0, :, 256:512] = 0.0
    raw[0, 0, :, 512:] = 10.0
    pixels = np.asarray(postprocess(raw, (1024, 1024), "birefnet"))
    # sigmoid(0) = 0.5 sits halfway after stretching; a plain min-max would also give 0.5, so check the shape.
    assert pixels[500, 100] == 0 and pixels[500, 900] == 255
    assert 120 <= pixels[500, 384] <= 135


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("isnet-general-use.onnx", "isnet"),
        ("birefnet-general-lite.onnx", "birefnet"),
        ("BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx", "birefnet"),
        ("u2net.onnx", None),
    ],
)
def test_model_kind_follows_the_file_name(name: str, kind: str | None) -> None:
    assert matting.model_kind(Path(name)) == kind


def test_cli_unknown_model_name_exits_3(tmp_path: Path) -> None:
    model = tmp_path / "u2net.onnx"
    model.write_bytes(b"x")
    src = tmp_path / "in.png"
    Image.new("RGB", (10, 10)).save(src)
    assert matting.main(["--model", str(model), "--in", str(src), "--out", str(tmp_path / "m.png")]) == 3


def test_cli_bad_arguments_exit_2() -> None:
    assert matting.main(["--model", "x.onnx"]) == 2


def test_cli_lowers_its_priority_on_posix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(matting.os, "nice", calls.append, raising=False)
    matting.main(["--model", str(tmp_path / "u2net.onnx"), "--in", "a.png", "--out", "b.png"])
    assert calls == [10]


@pytest.fixture
def fake_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Settings with a model file, and the child process swapped for the fake script."""
    model = tmp_path / "isnet-general-use.onnx"
    model.write_bytes(b"not a real model")
    monkeypatch.setattr(matting, "CHILD_ARGS", (fake_matting.SCRIPT,))
    monkeypatch.delenv(fake_matting.MODE_ENV, raising=False)
    return SimpleNamespace(matting_model_path=model, matting_during_show=True)


async def test_complex_background_goes_to_the_model(fake_model: SimpleNamespace) -> None:
    cut = await remove_background(_rgba("noisy_bg"), show_running=False, settings=fake_model)
    assert (cut.result, cut.method, cut.model) == ("removed", "model", "isnet-general-use.onnx")
    assert cut.image is not None
    # Cropped to the fake's ellipse (w/4 .. 3w/4, h/6 .. 5h/6), with the source RGB.
    assert abs(cut.image.width - 160) <= 2 and abs(cut.image.height - 267) <= 2
    assert set(cut.metrics) == METRIC_KEYS
    assert cut.ms > 0


async def test_unsure_flat_cut_tries_the_model(fake_model: SimpleNamespace) -> None:
    image = Image.new("RGBA", (320, 400), (255, 255, 255, 255))
    ImageDraw.Draw(image).rectangle((80, 66, 240, 333), fill=(250, 250, 250, 255))
    cut = await remove_background(image, show_running=False, settings=fake_model)
    assert (cut.result, cut.method) == ("removed", "model")


@pytest.mark.parametrize("path", [None, Path("models/matting/missing-isnet.onnx")])
async def test_no_model_fails_with_a_reason(path: Path | None) -> None:
    settings = SimpleNamespace(matting_model_path=path, matting_during_show=True)
    cut = await remove_background(_rgba("noisy_bg"), show_running=False, settings=settings)
    assert (cut.result, cut.reason, cut.image) == ("failed", NO_MODEL_REASON, None)
    assert NO_MODEL_REASON == "chưa cài model tách nền"


async def test_flat_background_never_needs_the_model() -> None:
    settings = SimpleNamespace(matting_model_path=None, matting_during_show=False)
    cut = await remove_background(_rgba("white_bg"), show_running=True, settings=settings)
    assert (cut.result, cut.method) == ("removed", "flat")


async def test_model_is_skipped_during_a_show_when_configured(fake_model: SimpleNamespace) -> None:
    fake_model.matting_during_show = False
    cut = await remove_background(_rgba("noisy_bg"), show_running=True, settings=fake_model)
    assert (cut.result, cut.reason) == ("failed", LIVE_REASON)
    assert LIVE_REASON == "đang live, bỏ nền phức tạp sau khi dừng show"
    # Off show the same settings run the model.
    cut = await remove_background(_rgba("noisy_bg"), show_running=False, settings=fake_model)
    assert cut.result == "removed"


async def test_model_runs_during_a_show_by_default(fake_model: SimpleNamespace) -> None:
    cut = await remove_background(_rgba("noisy_bg"), show_running=True, settings=fake_model)
    assert cut.result == "removed"


async def test_timeout_kills_the_child(fake_model: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(fake_matting.MODE_ENV, "sleep")
    monkeypatch.setenv(fake_matting.SLEEP_ENV, "30")
    monkeypatch.setattr(matting, "MODEL_TIMEOUT_S", 1.5)
    started = time.perf_counter()
    cut = await remove_background(_rgba("noisy_bg"), show_running=False, settings=fake_model)
    assert time.perf_counter() - started < 10
    assert (cut.result, cut.reason) == ("failed", TIMEOUT_REASON)
    assert TIMEOUT_REASON == "tách nền quá lâu"


@pytest.mark.parametrize("code", [3, 4, 5])
async def test_child_errors_fail(fake_model: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    monkeypatch.setenv(fake_matting.MODE_ENV, f"exit{code}")
    cut = await remove_background(_rgba("noisy_bg"), show_running=False, settings=fake_model)
    assert cut.result == "failed"
    assert cut.method == "model"
    assert cut.image is None
    assert cut.reason


async def test_unsure_model_mask_fails(fake_model: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(fake_matting.MODE_ENV, "uncertain")
    cut = await remove_background(_rgba("noisy_bg"), show_running=False, settings=fake_model)
    assert (cut.result, cut.method, cut.image) == ("failed", "model", None)
    assert cut.reason is not None and MODEL_UNSURE_REASON in cut.reason
    assert "model không chắc" in MODEL_UNSURE_REASON


async def test_model_calls_run_one_at_a_time(fake_model: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    running = 0
    peak = 0
    real = asyncio.create_subprocess_exec

    async def counting(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        try:
            process = await real(*args, **kwargs)  # type: ignore[arg-type]
            await process.wait()
            return process
        finally:
            running -= 1

    monkeypatch.setattr(matting.asyncio, "create_subprocess_exec", counting)
    results = await asyncio.gather(
        *(remove_background(_rgba("noisy_bg"), show_running=False, settings=fake_model) for _ in range(3))
    )
    assert peak == 1
    assert all(r.result == "removed" for r in results)


async def test_child_runs_below_normal_priority(fake_model: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    real = asyncio.create_subprocess_exec

    async def spy(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        seen["args"] = args
        seen.update(kwargs)
        return await real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(matting.asyncio, "create_subprocess_exec", spy)
    await remove_background(_rgba("noisy_bg"), show_running=False, settings=fake_model)
    args = seen["args"]
    assert isinstance(args, tuple) and args[0] == sys.executable
    assert "--threads" in args and "2" in args
    if sys.platform == "win32":
        assert seen.get("creationflags") == subprocess.BELOW_NORMAL_PRIORITY_CLASS
    else:
        assert "creationflags" not in seen


def test_default_child_is_the_matting_module() -> None:
    assert matting.CHILD_ARGS == ("-m", "ai_live.scene.matting")
    assert matting.MODEL_TIMEOUT_S == 60


async def test_flat_removal_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    threads: list[int] = []
    real = matting.remove_flat_background

    def spy(image: Image.Image):  # noqa: ANN202
        threads.append(threading.get_ident())
        return real(image)

    monkeypatch.setattr(matting, "remove_flat_background", spy)
    settings = SimpleNamespace(matting_model_path=None, matting_during_show=True)
    cut = await remove_background(_rgba("white_bg"), show_running=False, settings=settings)
    assert cut.result == "removed"
    assert threads and threads[0] != threading.get_ident()


async def test_model_cut_keeps_the_source_colours(fake_model: SimpleNamespace) -> None:
    source = _rgba("noisy_bg")
    cut = await remove_background(source, show_running=False, settings=fake_model)
    assert cut.image is not None
    out = np.asarray(cut.image)
    visible = out[..., 3] > 0
    bbox = _crop_box(source, cut.image)
    assert np.array_equal(out[..., :3][visible], np.asarray(source.crop(bbox))[..., :3][visible])
    # Sanity: the product colour is in there.
    assert (out[..., :3] == PRODUCT_COLOR).all(axis=-1).any()
