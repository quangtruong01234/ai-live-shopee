"""014 US4 (T044): `realism_report.py --background-frames` measures the background behind the host.

The skill script is not a package, so it is loaded with importlib. Synthetic loop: a cream room with plants, a navy
body with a skin head, a desk at the bottom; masks and a manifest laid out like `background_prep.prepare` writes them.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".claude" / "skills" / "live-scene-realism" / "scripts"
W, H, DESK = 240, 240, 200
CREAM = (205, 195, 175)  # low enough that +40 does not clip to 255 and fake a colour change
PATCH = (slice(100, 114), slice(156, 170))  # 14 x 14 = 196 px of room kept beside the right shoulder


def _load():
    spec = importlib.util.spec_from_file_location("realism_report_under_test", SCRIPTS / "realism_report.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rr():
    return _load()


def _person() -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W]
    head = (yy - 60) ** 2 + (xx - 120) ** 2 <= 22**2
    body = (yy >= 85) & (yy < DESK) & (xx >= 85) & (xx < 156)
    return head | body


def _frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rgb = np.empty((H, W, 3), np.float32)
    rgb[:] = CREAM
    rgb[20:70, 10:40] = (60, 140, 70)  # a plant on the left
    rgb[120:170, 205:232] = (60, 140, 70)  # and one on the right
    rgb += rng.normal(0, 4, rgb.shape)
    yy, xx = np.mgrid[0:H, 0:W]
    head = (yy - 60) ** 2 + (xx - 120) ** 2 <= 22**2
    body = (yy >= 85) & (yy < DESK) & (xx >= 85) & (xx < 156)
    rgb[head] = np.array((200, 150, 120)) + rng.normal(0, 10, (int(head.sum()), 3))
    rgb[body] = np.array((40, 50, 100)) + rng.normal(0, 10, (int(body.sum()), 3))
    rgb[DESK:] = (120, 80, 50)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _fingerprint(rgb: np.ndarray) -> str:
    return f"{zlib.crc32(np.ascontiguousarray(rgb[:, :, ::-1]).tobytes()) & 0xFFFFFFFF:08x}"


def _blur(rgb: np.ndarray, radius: float = 3.0) -> np.ndarray:
    return np.asarray(Image.fromarray(rgb).filter(ImageFilter.GaussianBlur(radius)))


def _composite(person_from: np.ndarray, plate: np.ndarray) -> np.ndarray:
    out = plate.copy()
    out[_person()] = person_from[_person()]
    out[DESK:] = person_from[DESK:]
    return out


@pytest.fixture
def scene(tmp_path: Path) -> dict[str, Path]:
    """Two loop frames (one with a leaked room patch in its mask) and five captured live frames."""
    leaky, clean = _frame(1), _frame(2)
    bg = tmp_path / "character" / "background"
    (bg / "masks").mkdir(parents=True)
    leak_mask = _person().astype(np.uint8) * 255
    leak_mask[PATCH] = 255
    entries = []
    for rgb, mask in ((leaky, leak_mask), (clean, _person().astype(np.uint8) * 255)):
        fp = _fingerprint(rgb)
        Image.fromarray(mask).save(bg / "masks" / f"{fp}.png")
        entries.append({"fingerprint": fp, "mask": f"masks/{fp}.png", "sources": []})
    Image.fromarray(clean).save(bg / "preview_frame.png")
    manifest = {"schema_version": 1, "width": W, "height": H, "desk_top_px": DESK, "frames": entries}
    (bg / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    loop = tmp_path / "frames" / "loop"
    loop.mkdir(parents=True)
    Image.fromarray(leaky).save(loop / "00000000.png")
    Image.fromarray(clean).save(loop / "00000001.png")

    soft_plate = _blur(clean)
    checker = (np.indices((H, W)).sum(axis=0) // 2) % 2 == 0
    sharp_plate = np.where(checker[..., None], np.array((245, 235, 215)), np.array((205, 195, 175))).astype(np.uint8)
    bright_plate = np.clip(soft_plate.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    cool = soft_plate.astype(np.int16)
    cool[..., 0] -= 25
    cool[..., 2] += 25
    goc = clean.copy()
    goc[2:12, 2:12] = 0  # the AI label: the captured frame is no longer byte-equal to a loop frame
    live = {
        "ke_hang": _composite(clean, soft_plate),
        "sharp": _composite(clean, sharp_plate),
        "bright": _composite(clean, bright_plate),
        "cool": _composite(clean, np.clip(cool, 0, 255).astype(np.uint8)),
        "goc": goc,
    }
    paths = {"background": bg, "loop": loop}
    for name, rgb in live.items():
        folder = tmp_path / "frames" / name
        folder.mkdir()
        Image.fromarray(rgb).save(folder / "live_000.png")
        paths[name] = folder
    return paths


def _run(rr, scene: dict[str, Path], out: Path, names: list[str]) -> dict:
    sets = [(name, scene[name]) for name in names]
    return rr.measure_background(sets, scene["background"], out)


def _row(report: dict, label: str, index: int = 0) -> dict:
    return list(report["sets"][label]["frames"].values())[index]


def test_leaked_room_patch_is_flagged_with_a_red_marked_image(rr, scene, tmp_path):
    report = _run(rr, scene, tmp_path / "out" / "bg", ["loop"])
    leaky, clean = _row(report, "loop", 0), _row(report, "loop", 1)
    assert leaky["source"] == "loop"
    assert leaky["leak_blob_px"] > rr.LEAK_BLOB_PX
    assert any("leak" in f for f in leaky["flags"])
    marked = np.asarray(Image.open(leaky["leak_marked"]).convert("RGB")).astype(int)
    patch = marked[PATCH]
    assert ((patch[..., 0] > 200) & (patch[..., 1] < 60) & (patch[..., 2] < 60)).mean() > 0.5
    assert clean["leak_blob_px"] <= rr.LEAK_BLOB_PX
    assert not any("leak" in f for f in clean["flags"])
    assert report["sets"]["loop"]["flagged"] == 1


def test_soft_matching_background_has_no_flag(rr, scene, tmp_path):
    report = _run(rr, scene, tmp_path / "out" / "bg", ["ke_hang"])
    row = _row(report, "ke_hang")
    assert row["source"] == "live"
    assert "leak_blob_px" not in row
    assert row["sharpness_ratio"] < 1.0
    assert row["flags"] == []


def test_background_sharper_than_the_person_is_flagged(rr, scene, tmp_path):
    row = _row(_run(rr, scene, tmp_path / "out" / "bg", ["sharp"]), "sharp")
    assert row["sharpness_ratio"] > 1.0
    assert any("sharper than the person" in f for f in row["flags"])


def test_brightness_and_light_colour_offsets_are_flagged(rr, scene, tmp_path):
    report = _run(rr, scene, tmp_path / "out" / "bg", ["bright", "cool"])
    bright, cool = _row(report, "bright"), _row(report, "cool")
    assert bright["luma_diff"] > rr.BG_LUMA_DIFF
    assert any("brighter" in f for f in bright["flags"])
    assert cool["warm_diff"] < -rr.WARM_DIFF
    assert any("cooler" in f for f in cool["flags"])
    assert not any("cooler" in f or "warmer" in f for f in bright["flags"])


def test_original_room_frame_is_not_reported_as_a_leak(rr, scene, tmp_path):
    row = _row(_run(rr, scene, tmp_path / "out" / "bg", ["goc"]), "goc")
    assert "leak_blob_px" not in row
    assert row["flags"] == []


def test_flat_frame_is_reported_as_not_measurable(rr, scene, tmp_path):
    flat = tmp_path / "frames" / "flat"
    flat.mkdir()
    Image.fromarray(np.full((H, W, 3), 255, np.uint8)).save(flat / "white.png")  # e.g. a mask passed by mistake
    report = rr.measure_background([("flat", flat)], scene["background"], tmp_path / "out" / "bg")
    row = _row(report, "flat")
    assert row["sharpness_ratio"] is None and row["warm_diff"] is None
    assert any("cannot measure" in f for f in row["flags"])
    assert not any("sharper" in f or "warmer" in f or "cooler" in f for f in row["flags"])
    json.dumps(report, allow_nan=False)


def test_contact_sheet_puts_the_styles_side_by_side(rr, scene, tmp_path):
    report = _run(rr, scene, tmp_path / "out" / "bg", ["goc", "ke_hang", "sharp"])
    sheet = Image.open(report["sheet"])
    assert sheet.width >= 3 * 200 and sheet.height > sheet.width / 3


def test_nothing_is_written_outside_out(rr, scene, tmp_path):
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    out = tmp_path / "out" / "bg"
    _run(rr, scene, out, ["loop", "ke_hang", "goc"])
    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    changed = [p for p in after if before.get(p) != after[p]]
    assert changed
    for path in changed:
        if path == out.parent:
            continue  # the folder --out lives in may be created
        assert path.parent == out.parent and path.name.startswith(out.name), path


def test_cli_accepts_background_frames(rr):
    args = rr.build_parser().parse_args(["--out", "x", "--background-frames", "a=ke_hang", "b"])
    assert args.background_frames == ["a=ke_hang", "b"]
