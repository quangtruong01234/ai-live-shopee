"""Render the live scene still and measure how real the products on the desk look (live-scene-realism skill).

Run from the repo root:
    uv run python .claude/skills/live-scene-realism/scripts/realism_report.py --out out/realism/base \
        --host-frame assets/avatars/demo_host_02/face.png --head-px 232,410 --real-cm loc-6-chai-coca-cola-355ml=24

Experiments never touch the repo: `--layout key=value` overrides scene.json `layout`, `--const NAME=value` patches a
constant in every `ai_live.scene` module that defines it, and `--harmonize/--soften/--feather` try a light match on the
products. Writes `<out>.png`, `<out>_zones.png` and `<out>.json`, and prints one line per product with its flags.
`_zones.png` also tints the Shopee app's overlay zones and darkens the strips a phone crops off (014 FR-019,
ADR-085); the report gives the share of the AI label and of each product they hide.
The thresholds are starting points for the eye, not measured truth: always look at the picture as well.

`--background-frames dir[=label] ...` also measures the background behind the host (014 US4): the R12 leak index on
the fork's original loop frames (matched to `assets/avatars/<id>/background/` masks by crc32), and the background's
sharpness, brightness and light colour against the person on frames captured from `/host`. Adds the `background` key
to `<out>.json`, `<out>_leak_*.png` marked images and an `<out>_backgrounds.png` sheet of the styles side by side.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import importlib
import importlib.util
import json
import pkgutil
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import ai_live.scene as scene_pkg
from ai_live.avatar.character import load_character
from ai_live.core.config import Settings
from ai_live.products.docx_loader import load_catalog_file
from ai_live.scene import render
from ai_live.scene.fonts import load_fonts
from ai_live.scene.layout import compute_scene_layout, estimate_geometry, estimate_label_box
from ai_live.scene.loader import load_scene_set
from ai_live.scene.merchandise import with_stock
from ai_live.scene.shopee_overlay import PHONE_ASPECT, frame_boxes, shown_box, zone_mask

HEAD_CM = 23.0  # crown to chin of an adult
RING_PX = 14  # the surroundings a product is compared with
NEUTRAL_SAT = 0.15
NEUTRAL_MIN_Y = 110
# Heuristic bands (see REFERENCE.md "Metrics"): a product in front of the host looks a bit bigger than at head depth.
SCALE_FRONT = (1.0, 1.45)
SCALE_BACK = (0.85, 1.2)
HIGHLIGHT_OVER = 20  # product p95 luma above its surroundings' p95: it glows (a dark bottle is darker on purpose)
DESK_EDGE_TOLERANCE_PX = 12
DESK_SEARCH_FROM = 0.55  # x H: the desk edge is below the chest
DESK_BAND_PX = 8
DESK_SIDE_STRIP = 0.12  # x W per side: outside the host's body and arms
DESK_FLAT_PX = 32  # rows under a candidate edge that must look like one plain desk
DESK_FLAT_SCALE = 8.0  # colour spread (std, 0-255) that halves a step's score
ROOM_BAND_PX = 300
WARM_DIFF = 12  # R-B of neutral pixels, product vs room: a different light colour
SHARP_RATIO = (0.4, 2.5)
SOFT_EDGE_MIN = 0.15
# 014 US4: the R12 leak index, the same numbers as the fork's `background_prep` (keep them in step).
LEAK_BLOB_PX = 150  # a leaked room patch larger than ~12x12 px on a 480x832 frame is visible on a phone
LEAK_BAND_PX = 24  # only the band just inside the person edge can hold a leak
LEAK_ROOM_DIST_PX = 40  # "old room" colour samples are at least this far from the person
LEAK_RATIO = 4.0  # a pixel leaks when its colour is this much more likely room than person
CHAMFER_A, CHAMFER_B, CHAMFER_C = 1.0, 1.4, 2.1969  # cv2 DIST_L2 with a 5x5 mask, which the fork uses
LAB_GAMMA_SHIFT, LAB_SHIFT, LAB_SHIFT2 = 3, 12, 15  # cv2's fixed-point 8-bit Lab
# Heuristic, to re-measure in T048: background-minus-person luma moved this far from the original room's.
BG_LUMA_DIFF = 20
BG_SHARP_MARGIN = 1.1  # a background may be as sharp as the original room was, times this
STABLE_SHRINK_PX = 4  # keep the measured regions off the person edge, which moves from frame to frame
CLIPPED = 250  # pixels with a channel this high say nothing about the light colour
ASPECT_TOLERANCE = 0.02
FLAT_VAR = 1.0  # person-region Laplacian variance below this: not a host frame (a mask, a blank capture)
MIN_COLOUR_PX = 50  # unclipped pixels needed in each region for an R-B reading
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
# 014 FR-019 (ADR-085): the AI label must be fully visible on the phone; a product may lose a little of its foot.
OVERLAY_LABEL_MAX = 0.0
OVERLAY_PRODUCT_MAX = 0.10  # heuristic: past a tenth hidden under the app's UI, the product reads as cut off
OVERLAY_TINT = (255, 64, 160)
CROP_DARKEN = 0.45
GREEN = (0, 177, 64)
RED = (255, 0, 0)


def _kv(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep:
            sys.exit(f"expected key=value, got {item!r}")
        out[key.strip()] = value.strip()
    return out


def _literal(value: str) -> object:
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value


def _patch_constants(consts: dict[str, str]) -> None:
    """Set each constant in every scene module that defines it (render imports some from layout by name)."""
    modules = [importlib.import_module(f"ai_live.scene.{m.name}") for m in pkgutil.iter_modules(scene_pkg.__path__)]
    for name, raw in consts.items():
        hit = [m.__name__ for m in modules if hasattr(m, name)]
        if not hit:
            sys.exit(f"no ai_live.scene module defines {name}")
        for mod in modules:
            if hasattr(mod, name):
                setattr(mod, name, _literal(raw))
        print(f"const {name} = {raw} in {', '.join(hit)}")


def _luma(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _neutral(rgb: np.ndarray) -> np.ndarray:
    """Pixels lit by the room's light without much colour of their own (labels, glass highlights, wall, desk top)."""
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    return rgb[(sat < NEUTRAL_SAT) & (_luma(rgb) > NEUTRAL_MIN_Y)]


def _laplacian_var(y: np.ndarray, mask: np.ndarray) -> float:
    lap = np.zeros_like(y)
    lap[1:-1, 1:-1] = y[:-2, 1:-1] + y[2:, 1:-1] + y[1:-1, :-2] + y[1:-1, 2:] - 4 * y[1:-1, 1:-1]
    vals = lap[mask]
    return float(vals.var()) if vals.size > 50 else float("nan")


def _grow(mask: np.ndarray, px: int) -> np.ndarray:
    img = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * px + 1))
    return np.asarray(img) > 0


def _shrink(mask: np.ndarray, px: int) -> np.ndarray:
    img = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(2 * px + 1))
    return np.asarray(img) > 0


def _desk_edge(host: np.ndarray) -> int:
    """The row where the desk top starts in the host frame: the strongest colour step in the two side strips
    that has a flat desk just below it.

    Only the strips at the frame edges are measured because the host stands in the middle: a dark shirt meeting
    bare arms there is a stronger step than the desk edge (611 vs 649 on demo_host_02). A stocked shelf behind the
    host reaches the strips too, so a step counts less the busier the rows under it are: the desk is one plain
    surface, a shelf row is many products.
    """
    w = host.shape[1]
    strip = max(int(w * DESK_SIDE_STRIP), 1)
    sides = np.concatenate([host[:, :strip], host[:, w - strip :]], axis=1).astype(np.float32)
    rows = sides.mean(axis=1)
    busy = sides.std(axis=1).mean(axis=1)  # per row: how much the colour varies across the strips
    h = rows.shape[0]
    best, best_y = -1.0, h - 1
    for y in range(max(int(h * DESK_SEARCH_FROM), DESK_BAND_PX), h - DESK_BAND_PX):
        step = float(np.linalg.norm(rows[y : y + DESK_BAND_PX].mean(0) - rows[y - DESK_BAND_PX : y].mean(0)))
        below = float(busy[y : y + DESK_FLAT_PX].mean())
        score = step / (1.0 + below / DESK_FLAT_SCALE)
        if score > best:
            best, best_y = score, y
    return best_y


def _light_match(host: np.ndarray, arts: list[Image.Image], strength: float) -> tuple[np.ndarray, float]:
    """Channel gains and exposure that move the products' neutral pixels toward the room's light."""
    room = _neutral(host[int(host.shape[0] * 0.5) :])
    solid = [np.asarray(a.convert("RGB"), np.float32)[np.asarray(a)[..., 3] > 200] for a in arts]
    prod = np.concatenate([_neutral(px) for px in solid])
    if len(room) < 200 or len(prod) < 200:
        return np.ones(3), 1.0
    r, p = room.mean(axis=0), prod.mean(axis=0)
    gains = ((r / r[1]) / (p / p[1])) ** strength
    exposure = float(np.clip(np.percentile(_luma(room), 95) / np.percentile(_luma(prod), 95), 0.8, 1.05) ** strength)
    return gains, exposure


def _wrap_defringe(gains: np.ndarray, exposure: float, soften: float, feather: float) -> None:
    """Apply the trial light match to each product after it is resized for the frame (render calls defringe there)."""
    original = render.defringe

    def defringe(pic: Image.Image) -> Image.Image:
        pic = original(pic)
        rgb = np.asarray(pic.convert("RGB"), np.float32) * gains * exposure
        out = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
        if soften > 0:
            out = out.filter(ImageFilter.GaussianBlur(soften))
        alpha = pic.getchannel("A")
        if feather > 0:
            alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
        out.putalpha(alpha)
        return out

    render.defringe = defringe


# ---------- the background behind the host (014 US4) ----------


def _fingerprint(rgb: np.ndarray) -> str:
    """crc32 of the decoded BGR bytes, as the fork keys a frame's mask (`background_prep.fingerprint`)."""
    return f"{zlib.crc32(np.ascontiguousarray(rgb[:, :, ::-1]).tobytes()) & 0xFFFFFFFF:08x}"


def _chamfer(dy: np.ndarray, dx: np.ndarray) -> np.ndarray:
    """The distance cv2.distanceTransform(DIST_L2, 5) measures: a 5x5 chamfer with steps 1, 1.4 and 2.1969."""
    u, v = np.maximum(abs(dx), abs(dy)), np.minimum(abs(dx), abs(dy))
    return np.where(u >= 2 * v, v * CHAMFER_C + (u - 2 * v) * CHAMFER_A, (u - v) * CHAMFER_C + (2 * v - u) * CHAMFER_B)


def _near(mask: np.ndarray, radius: int, inclusive: bool) -> np.ndarray:
    """True where a `mask` pixel lies within `radius` px, measured as the fork's cv2 distance transform does.

    Outside the image counts as not in the mask, like cv2.distanceTransform's border. An FFT convolution with a
    chamfer disc, since the app venv has no cv2 and scipy is only a transitive dependency.
    """
    h, w = mask.shape
    r = int(radius)
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    d = _chamfer(yy, xx)
    disc = (d <= r + 1e-6) if inclusive else (d < r - 1e-6)
    shape = (h + 2 * r + 1, w + 2 * r + 1)
    spectrum = np.fft.rfft2(mask.astype(np.float64), shape) * np.fft.rfft2(disc.astype(np.float64), shape)
    conv = np.fft.irfft2(spectrum, shape)
    return conv[r : r + h, r : r + w] > 0.5


def _lab_tables() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The fixed-point tables of cv2's 8-bit sRGB->Lab (color_lab.cpp `RGB2Lab_b`): float Lab lands in other bins
    on ~1% of pixels, and those bridge leak blobs the fork sees apart."""
    x = np.arange(256) / 255.0
    gamma = np.rint(255.0 * (1 << LAB_GAMMA_SHIFT) * np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4))
    y = np.arange(256 * 3 // 2 * (1 << LAB_GAMMA_SHIFT)) / (255.0 * (1 << LAB_GAMMA_SHIFT))
    cbrt = np.rint((1 << LAB_SHIFT2) * np.where(y < 0.008856, y * 7.787 + 16.0 / 116.0, np.cbrt(y)))
    srgb_to_xyz = np.array(
        [[0.412453, 0.357580, 0.180423], [0.212671, 0.715160, 0.072169], [0.019334, 0.119193, 0.950227]]
    )
    coeffs = np.rint((1 << LAB_SHIFT) * srgb_to_xyz / np.array([0.950456, 1.0, 1.088754])[:, None])
    return gamma.astype(np.int64), cbrt.astype(np.int64), coeffs.astype(np.int64)


def _descale(x: np.ndarray, n: int) -> np.ndarray:
    return (x + (1 << (n - 1))) >> n


def _lab_bins(rgb: np.ndarray) -> np.ndarray:
    """cv2 8-bit Lab (L*255/100, a+128, b+128), 8 bins per channel: the fork's `_colour_bins`."""
    gamma, cbrt, coeffs = _lab_tables()
    lin = gamma[rgb.astype(np.intp)]
    f = [cbrt[np.clip(_descale(lin @ coeffs[i], LAB_SHIFT), 0, len(cbrt) - 1)] for i in range(3)]
    lum_scale, lum_shift = (116 * 255 + 50) // 100, -((16 * 255 * (1 << LAB_SHIFT2) + 50) // 100)
    mid = 128 * (1 << LAB_SHIFT2)
    lab = [
        _descale(lum_scale * f[1] + lum_shift, LAB_SHIFT2),
        _descale(500 * (f[0] - f[1]) + mid, LAB_SHIFT2),
        _descale(200 * (f[1] - f[2]) + mid, LAB_SHIFT2),
    ]
    q = [np.clip(c, 0, 255) >> 5 for c in lab]
    return (q[0] * 64 + q[1] * 8 + q[2]).astype(np.int64)


def leak_map(rgb: np.ndarray, alpha: np.ndarray, desk_top_px: int) -> np.ndarray:
    """Kept pixels near the person edge that are coloured like the old room (R12; port of the fork's `leak_map`)."""
    h = rgb.shape[0]
    top = min(max(int(desk_top_px), 0), h)
    kept = alpha >= 128
    above = np.zeros(kept.shape, bool)
    above[:top] = True
    room = above & ~_near(kept, LEAK_ROOM_DIST_PX, inclusive=False)
    person = above & kept & ~_near(~kept, LEAK_BAND_PX, inclusive=False)
    band = above & kept & _near(~kept, LEAK_BAND_PX, inclusive=True)
    if not room.any() or not person.any() or not band.any():
        return np.zeros(kept.shape, bool)
    bins = _lab_bins(rgb)
    room_hist = np.bincount(bins[room], minlength=512).astype(np.float64)
    person_hist = np.bincount(bins[person], minlength=512).astype(np.float64)
    room_hist = (room_hist + 1.0) / (room_hist.sum() + 512.0)
    person_hist = (person_hist + 1.0) / (person_hist.sum() + 512.0)
    return band & ((room_hist / person_hist) > LEAK_RATIO)[bins]


def _largest_blob(mask: np.ndarray) -> int:
    """Pixel count of the largest 8-connected patch."""
    ys, xs = np.nonzero(mask)
    left = set(zip(ys.tolist(), xs.tolist(), strict=True))
    best = 0
    while left:
        stack, size = [left.pop()], 0
        while stack:
            y, x = stack.pop()
            size += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    p = (y + dy, x + dx)
                    if p in left:
                        left.remove(p)
                        stack.append(p)
        best = max(best, size)
    return best


def _leak_marked(rgb: np.ndarray, alpha: np.ndarray, leaks: np.ndarray) -> Image.Image:
    """The kept person on flat green with leaked pixels in red, so a leak is easy to find by eye."""
    out = np.where((alpha >= 128)[..., None], rgb, np.array(GREEN, np.uint8)).astype(np.uint8)
    out[leaks] = RED
    return Image.fromarray(out)


def _zones_under(mask: np.ndarray, width: int, height: int, phone_aspect: float) -> list[str]:
    names = []
    for name, (x1, y1, x2, y2) in frame_boxes(width, height, phone_aspect):
        if mask[y1:y2, x1:x2].any():
            names.append(name)
    return names


def overlay_report(
    label_box: tuple[int, int, int, int] | None,
    products: dict[str, np.ndarray],
    width: int,
    height: int,
    phone_aspect: float = PHONE_ASPECT,
) -> dict:
    """What the Shopee app hides on a phone (014 FR-019, SC-008): the share of the AI label and of each product mask
    under the app's UI, and of each product outside the part of the frame the phone shows at all."""
    covered = zone_mask(width, height, phone_aspect)
    sx1, sy1, sx2, sy2 = shown_box(width, height, phone_aspect)
    outside = np.ones((height, width), bool)
    outside[sy1:sy2, sx1:sx2] = False
    flags: list[str] = []
    report: dict[str, object] = {"phone_aspect": phone_aspect, "shown_box": [sx1, sy1, sx2, sy2]}
    if label_box is not None:
        lx1, ly1 = max(label_box[0], 0), max(label_box[1], 0)
        lx2, ly2 = min(label_box[2], width), min(label_box[3], height)
        box = np.zeros((height, width), bool)
        box[ly1:ly2, lx1:lx2] = True
        area = max(int(box.sum()), 1)
        share = float((box & (covered | outside)).sum() / area)
        zones = _zones_under(box & covered, width, height, phone_aspect)
        report["label"] = {"box": list(label_box), "share": round(share, 3), "zones": zones}
        if share > OVERLAY_LABEL_MAX:
            where = ", ".join(zones) or "the phone crop"
            flags.append(f"AI label {share:.0%} hidden by the Shopee app ({where}): use AI_LABEL_POSITION=shopee-top")
    rows: dict[str, dict] = {}
    for pid, mask in products.items():
        area = max(int(mask.sum()), 1)
        hidden = float((mask & covered & ~outside).sum() / area)
        cropped = float((mask & outside).sum() / area)
        zones = _zones_under(mask & covered, width, height, phone_aspect)
        rows[pid] = {"covered_share": round(hidden, 3), "cropped_share": round(cropped, 3), "zones": zones}
        if hidden > OVERLAY_PRODUCT_MAX:
            flags.append(f"{pid}: {hidden:.0%} under the Shopee app's UI ({', '.join(zones)})")
        if cropped > OVERLAY_PRODUCT_MAX:
            flags.append(f"{pid}: {cropped:.0%} outside the phone crop (the app cuts the frame's sides)")
    report["products"] = rows
    report["flags"] = flags
    return report


def draw_overlay_zones(image: Image.Image, phone_aspect: float = PHONE_ASPECT) -> Image.Image:
    """A copy with the app's overlay zones tinted and named, and the strips the phone crops off darkened."""
    from PIL import ImageDraw

    out = image.convert("RGB")
    pixels = np.asarray(out, np.float32).copy()
    width, height = out.size
    sx1, sy1, sx2, sy2 = shown_box(width, height, phone_aspect)
    outside = np.ones((height, width), bool)
    outside[sy1:sy2, sx1:sx2] = False
    pixels[outside] *= CROP_DARKEN
    covered = zone_mask(width, height, phone_aspect) & ~outside
    pixels[covered] = pixels[covered] * 0.6 + np.asarray(OVERLAY_TINT, np.float32) * 0.4
    out = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(out)
    for name, (x1, y1, x2, y2) in frame_boxes(width, height, phone_aspect):
        x1, x2 = max(x1, sx1), min(x2, sx2)
        if x1 < x2 and y1 < y2:
            draw.rectangle((x1, y1, x2 - 1, y2 - 1), outline=OVERLAY_TINT)
            draw.text((x1 + 3, y1 + 2), name, fill=(255, 255, 255))
    return out


def _frame_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def _fit(img: Image.Image, w: int, h: int) -> Image.Image | None:
    """The frame at the manifest's size; None when the aspect differs (a capture of another part of the page)."""
    if img.size == (w, h):
        return img
    if abs(img.width / img.height - w / h) > ASPECT_TOLERANCE * (w / h):
        return None
    return img.resize((w, h), Image.Resampling.LANCZOS)


def _region_stats(rgb: np.ndarray, person: np.ndarray, room: np.ndarray) -> dict[str, float | None]:
    """Background-minus-person luma and R-B, and the background/person sharpness ratio.

    `rb` is None when a region is almost all clipped, `sharp` when the person region is flat: such a frame is not a
    host frame, and a ratio over a near-zero variance would be noise (and NaN/huge numbers break the JSON report).
    """
    f = rgb.astype(np.float32)
    y = _luma(f)

    def rb(region: np.ndarray) -> float | None:
        px = f[region]
        px = px[px.max(axis=1) < CLIPPED]
        return float((px[:, 0] - px[:, 2]).mean()) if len(px) >= MIN_COLOUR_PX else None

    room_rb, person_rb = rb(room), rb(person)
    person_var = _laplacian_var(y, person)
    return {
        "luma": float(y[room].mean() - y[person].mean()),
        "rb": None if room_rb is None or person_rb is None else room_rb - person_rb,
        "sharp": None if person_var < FLAT_VAR else _laplacian_var(y, room) / person_var,
    }


def _measure_loop_frame(rgb: np.ndarray, mask_path: Path, desk: int) -> tuple[dict, np.ndarray, np.ndarray]:
    alpha = np.asarray(Image.open(mask_path).convert("L"))
    leaks = leak_map(rgb, alpha, desk)
    blob = _largest_blob(leaks)
    row: dict[str, object] = {"source": "loop", "mask": mask_path.name, "leak_px": int(leaks.sum())}
    row["leak_blob_px"] = blob
    row["flags"] = [f"leak: a {blob} px patch of the old room kept beside the person"] if blob > LEAK_BLOB_PX else []
    return row, alpha, leaks


def _measure_live_frame(rgb: np.ndarray, person: np.ndarray, room: np.ndarray, ref: dict, sharp_limit: float) -> dict:
    stats = _region_stats(rgb, person, room)
    luma = stats["luma"] - ref["luma"]
    warm = None if stats["rb"] is None or ref["rb"] is None else stats["rb"] - ref["rb"]
    sharp = stats["sharp"]
    row: dict[str, object] = {
        "source": "live",
        "luma_diff": round(luma, 1),
        "warm_diff": None if warm is None else round(warm, 1),
        "sharpness_ratio": None if sharp is None else round(sharp, 2),
    }
    if sharp is None:
        # A flat person region means this is not a host frame; its other numbers mean nothing either.
        row["flags"] = ["cannot measure: the person region is flat (a mask or a blank capture, not a host frame?)"]
        return row
    flags = []
    if sharp > sharp_limit:
        flags.append(f"background sharper than the person: ratio {sharp:.2f} > {sharp_limit:.2f}")
    if abs(luma) > BG_LUMA_DIFF:
        side = "brighter" if luma > 0 else "darker"
        flags.append(f"background {side} against the person than the original room: {luma:+.0f} luma")
    if warm is not None and abs(warm) > WARM_DIFF:
        side = "warmer" if warm > 0 else "cooler"
        flags.append(f"background light {side} than the original room: R-B {warm:+.0f}")
    row["flags"] = flags
    return row


def _stable_regions(masks: list[Path], w: int, h: int, desk: int, exclude: np.ndarray | None) -> tuple:
    """Pixels that are person (or room) in every loop mask, above the desk, off the products and the AI label."""
    person = np.ones((h, w), bool)
    room = np.ones((h, w), bool)
    for mask_path in masks:
        a = np.asarray(Image.open(mask_path).convert("L"))
        person &= a >= 128
        room &= a == 0
    keep = np.zeros((h, w), bool)
    keep[:desk] = True
    if exclude is not None:
        keep &= ~(np.asarray(Image.fromarray(exclude.astype(np.uint8) * 255).resize((w, h))) > 0)
    return _shrink(person, STABLE_SHRINK_PX) & keep, _shrink(room, STABLE_SHRINK_PX) & keep


def _sheet(out: Path, tiles: list[str]) -> Path:
    sheet = out.parent / f"{out.name}_backgrounds.png"
    spec = importlib.util.spec_from_file_location("contact_sheet", Path(__file__).with_name("contact_sheet.py"))
    contact_sheet = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contact_sheet)
    contact_sheet.main([str(sheet), *tiles])
    return sheet


def measure_background(
    sets: list[tuple[str, Path]], background_dir: Path, out: Path, exclude: np.ndarray | None = None
) -> dict:
    """Measure each labelled set of frames (a folder or one image) against the character's background masks.

    Frames byte-equal to a fork loop frame get the R12 leak index with their own mask. Other frames (captured from
    `/host`, with the new background, the products and the AI label) have no mask of their own, so only the regions
    that are person (or room) in every mask are compared, against the original room in `preview_frame.png`.
    `exclude` (product and label pixels) is left out of those regions. Writes only `<out.name>*` files in `out.parent`.
    """
    manifest = json.loads((background_dir / "manifest.json").read_text(encoding="utf-8"))
    w, h, desk = int(manifest["width"]), int(manifest["height"]), int(manifest["desk_top_px"])
    masks = {e["fingerprint"]: background_dir / e["mask"] for e in manifest["frames"]}
    person, room = _stable_regions(list(masks.values()), w, h, desk, exclude)
    reference = None
    preview = background_dir / "preview_frame.png"
    ref_img = _fit(Image.open(preview).convert("RGB"), w, h) if preview.is_file() else None
    if ref_img is not None:
        reference = _region_stats(np.asarray(ref_img), person, room)
    sharp_limit = max(1.0, ((reference or {}).get("sharp") or 0.0) * BG_SHARP_MARGIN)

    out.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "background_dir": str(background_dir),
        "size": [w, h],
        "desk_top_px": desk,
        "regions_px": {"person": int(person.sum()), "background": int(room.sum())},
        "reference": {k: None if v is None else round(v, 2) for k, v in reference.items()} if reference else None,
        "sharp_limit": round(sharp_limit, 2),
        "sets": {},
    }
    tiles: list[str] = []
    for label, path in sets:
        rows: dict[str, dict] = {}
        best_blob, tile = -1, None
        for file in _frame_files(path):
            img = Image.open(file).convert("RGB")
            rgb = np.asarray(img)
            mask_path = masks.get(_fingerprint(rgb))
            if mask_path is not None and img.size == (w, h):
                row, alpha, leaks = _measure_loop_frame(rgb, mask_path, desk)
                # Marked images for the flagged frames and the worst frame so far, not for every loop frame.
                if row["flags"] or row["leak_blob_px"] > best_blob:
                    marked = out.parent / f"{out.name}_leak_{label}_{file.stem}.png"
                    _leak_marked(rgb, alpha, leaks).save(marked)
                    row["leak_marked"] = str(marked)
                    if row["leak_blob_px"] > best_blob:
                        best_blob, tile = row["leak_blob_px"], marked
            else:
                fitted = _fit(img, w, h)
                if fitted is None:
                    row = {"source": "live", "skipped": f"size {img.width}x{img.height}", "flags": []}
                else:
                    row = _measure_live_frame(
                        np.asarray(fitted), person, room, reference or {"luma": 0.0, "rb": 0.0}, sharp_limit
                    )
                    tile = tile or file
            rows[file.name] = row
        report["sets"][label] = {
            "path": str(path),
            "frames": rows,
            "flagged": sum(1 for r in rows.values() if r["flags"]),
        }
        if tile is not None:
            tiles.append(f"{tile}={label}")
    if tiles:
        report["sheet"] = str(_sheet(out, tiles))
    return report


def _background_sets(items: list[str]) -> list[tuple[str, Path]]:
    sets = []
    for item in items:
        raw, _, label = item.partition("=")
        path = Path(raw)
        if not path.exists():
            sys.exit(f"--background-frames: {path} does not exist")
        sets.append((label.strip() or path.stem, path))
    return sets


def _print_background(report: dict) -> None:
    print(f"background: {report['background_dir']}  regions {report['regions_px']}  reference {report['reference']}")
    for label, data in report["sets"].items():
        print(f"  [{label}] {len(data['frames'])} frames, {data['flagged']} flagged")
        for name, row in data["frames"].items():
            if row.get("skipped"):
                print(f"    {name}: skipped ({row['skipped']}, aspect differs from the manifest)")
            elif row["source"] == "loop":
                if row["flags"] or row.get("leak_marked"):
                    print(f"    {name}: leak blob {row['leak_blob_px']} px  {row.get('leak_marked', '')}")
            else:
                warm = "n/a" if row["warm_diff"] is None else f"{row['warm_diff']:+}"
                print(f"    {name}: sharp={row['sharpness_ratio']} luma={row['luma_diff']:+} warm={warm}")
            for flag in row["flags"]:
                print(f"      ! {flag}")
    if report.get("sheet"):
        print(f"  sheet: {report['sheet']}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True, help="output path without extension")
    ap.add_argument("--scene", type=Path, help="default SCENE_DIR")
    ap.add_argument("--content", type=Path, help="default PRODUCT_DATA_PATH")
    ap.add_argument("--host-frame", type=Path, help="a frame of the live avatar; default the character's face.png")
    ap.add_argument("--highlight")
    ap.add_argument("--layout", nargs="*", default=[], help="scene.json layout overrides, e.g. riser=false")
    ap.add_argument("--const", nargs="*", default=[], help="scene constants, e.g. SHOWCASE_MAIN_HEIGHT=0.32")
    ap.add_argument("--head-px", help="crown,chin y on the 832 px frame, to turn product heights into a scale")
    ap.add_argument("--real-cm", nargs="*", default=[], help="real product heights, e.g. some-id=24")
    ap.add_argument("--desk-top", type=float, help="try another character scene.desk_top (0..1 of the height)")
    ap.add_argument("--harmonize", type=float, default=0.0, help="0..1: match the products to the room's light")
    ap.add_argument("--soften", type=float, default=0.0, help="blur px on the products, to match the camera")
    ap.add_argument("--feather", type=float, default=0.0, help="blur px on the products' alpha edge")
    ap.add_argument(
        "--background-frames",
        nargs="+",
        metavar="PATH[=LABEL]",
        help="folders or images to measure the background in: fork full_imgs frames (leak) or /host captures",
    )
    ap.add_argument("--background-dir", type=Path, help="default <AVATAR_DIR>/background")
    ap.add_argument(
        "--phone-aspect", type=float, default=PHONE_ASPECT, help="phone screen width/height for the app's overlay zones"
    )
    return ap


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings()
    args = build_parser().parse_args()
    args.scene = args.scene or settings.scene_dir
    args.content = args.content or settings.product_data_path

    _patch_constants(_kv(args.const))
    catalog = load_catalog_file(args.content, settings.content_max_bytes)
    ids = [p.id for p in catalog.products]
    scene = load_scene_set(args.scene, ids, customer_id=settings.customer_id)
    overrides = {k: _literal(v) for k, v in _kv(args.layout).items()}
    if overrides:
        scene = dataclasses.replace(scene, layout=dataclasses.replace(scene.layout, **overrides))
        scene = dataclasses.replace(scene, art=with_stock(scene.art, scene.layout))
    character = load_character(settings.avatar_dir)
    geometry = estimate_geometry(settings.ai_label_text, settings.ai_label_position).with_hands_zone(
        character.hands_zone
    )
    W, H = geometry.width, geometry.height
    desk_top = args.desk_top if args.desk_top is not None else character.desk_top
    host_path = args.host_frame or character.face  # already resolved inside avatar_dir
    host_img = render.cover_crop(Image.open(host_path).convert("RGB"), W, H)
    host = np.asarray(host_img, np.float32)
    sizes = {pid: art.desk_image.size for pid, art in scene.art.items()}
    layout = compute_scene_layout(catalog.products, sizes, geometry, scene.layout, args.highlight, desk_top=desk_top)
    if args.harmonize or args.soften or args.feather:
        arts = [scene.art[s.product_id].desk_image for s in layout.slots if s.art_box and s.product_id in scene.art]
        gains, exposure = _light_match(host, arts, args.harmonize) if args.harmonize else (np.ones(3), 1.0)
        _wrap_defringe(gains, exposure, args.soften, args.feather)
        print(f"light match: gains {np.round(gains, 3).tolist()}, exposure {exposure:.3f}")
    fonts = load_fonts(settings.scene_font_path)
    products = {p.id: p for p in catalog.products}
    base = render.render_base(scene, layout, products, geometry, fonts, desk_in_image=character.desk_in_image)
    still = render.compose_still(host_img, [base])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    still.save(args.out.with_suffix(".png"))
    zones = draw_overlay_zones(render.draw_debug_zones(still, geometry, layout), args.phone_aspect)
    zones.save(args.out.with_name(args.out.name + "_zones.png"))
    shot = np.asarray(still.convert("RGB"), np.float32)

    masks: dict[str, np.ndarray] = {}
    edges: dict[str, float] = {}
    for slot in layout.slots:
        if slot.art_box is None or slot.product_id not in scene.art:
            continue
        x1, y1, x2, y2 = slot.art_box
        alpha = np.asarray(scene.art[slot.product_id].image.resize((x2 - x1, y2 - y1)).getchannel("A"))
        full = np.zeros((H, W), bool)
        cx1, cy1, cx2, cy2 = max(x1, 0), max(y1, 0), min(x2, W), min(y2, H)
        full[cy1:cy2, cx1:cx2] = alpha[cy1 - y1 : cy2 - y1, cx1 - x1 : cx2 - x1] > 127
        masks[slot.product_id] = full
        solid = alpha > 127
        rim = np.asarray(Image.fromarray(solid.astype(np.uint8) * 255).filter(ImageFilter.FIND_EDGES)) > 0
        edges[slot.product_id] = float(((alpha > 16) & (alpha < 240) & _grow(rim, 1)).sum() / max(rim.sum(), 1))
    union = np.zeros((H, W), bool)
    for m in masks.values():
        union |= m

    head_px = None
    if args.head_px:
        top, chin = (int(v) for v in args.head_px.split(","))
        head_px = chin - top
    real = {k: float(v) for k, v in _kv(args.real_cm).items()}
    desk_y = round((desk_top or scene.layout.desk_top) * H)
    edge_y = _desk_edge(host)
    report_desk = {"character_desk_top_px": desk_y, "detected_desk_edge_px": edge_y}
    # The room behind the products, above the desk edge: the wood and the shirt below it are not neutral.
    room_neutral = _neutral(host[max(edge_y - ROOM_BAND_PX, 0) : edge_y])
    report: dict[str, object] = {
        "frame": [W, H],
        "mode": layout.mode,
        "highlight": args.highlight,
        **report_desk,
        "products": {},
    }
    main_scale = None
    for slot in layout.slots:
        pid = slot.product_id
        if pid not in masks:
            continue
        m = masks[pid]
        inner, ring = _shrink(m, 2), _grow(m, RING_PX) & ~union
        x1, y1, x2, y2 = slot.art_box
        y_prod, y_ring = _luma(shot[inner]), _luma(host[ring])
        neutral = _neutral(shot[inner])
        sharp = _laplacian_var(_luma(shot), inner) / max(_laplacian_var(_luma(host), ring), 1e-6)
        row: dict[str, object] = {
            "box": [x1, y1, x2, y2],
            "height_px": y2 - y1,
            "foot_vs_desk_edge_px": y2 - edge_y,
            "p95_luma": round(float(np.percentile(y_prod, 95)), 1),
            "room_p95_luma": round(float(np.percentile(y_ring, 95)), 1),
            "sharpness_ratio": round(sharp, 2),
            "soft_edge_share": round(edges[pid], 3),
        }
        flags = []
        if len(neutral) > 100 and len(room_neutral) > 100:
            warm = float((neutral[:, 0] - neutral[:, 2]).mean() - (room_neutral[:, 0] - room_neutral[:, 2]).mean())
            row["warm_diff"] = round(warm, 1)
            if abs(warm) > WARM_DIFF:
                flags.append(
                    "light colour differs from the room"
                    + (" (warmer)" if warm > 0 else " (cooler)")
                    + ": 013 FR-006 bans recolouring, so pick a photo shot under similar light or accept it"
                )
        if row["p95_luma"] > row["room_p95_luma"] + HIGHLIGHT_OVER:
            flags.append("brighter than the room: looks lit separately")
        if not SHARP_RATIO[0] <= sharp <= SHARP_RATIO[1]:
            crisp = sharp > 1
            flags.append("crisper than the camera image: looks pasted" if crisp else "blurrier than the camera image")
        if edges[pid] < SOFT_EDGE_MIN:
            flags.append("hard cut-out edge")
        if y2 < edge_y:
            flags.append(f"foot {edge_y - y2} px above the desk edge seen in the frame: floats")
        if head_px and pid in real:
            scale = ((y2 - y1) / real[pid]) / (head_px / HEAD_CM)
            row["scale_vs_head"] = round(scale, 2)
            band = SCALE_FRONT if slot.primary else SCALE_BACK
            if slot.primary:
                main_scale = scale
            if not band[0] <= scale <= band[1]:
                flags.append(f"size off: {scale:.2f}x the head's scale (expected {band[0]}-{band[1]})")
        row["flags"] = flags
        report["products"][pid] = row
    if main_scale is not None:
        for pid, row in report["products"].items():
            if row.get("scale_vs_head", 0) > main_scale + 0.05 and pid in real:
                row["flags"].append("bigger scale than the main product although it stands behind it")

    boxes = {pid: r["box"] for pid, r in report["products"].items()}
    gaps = []
    for i, a in enumerate(boxes):
        for b in list(boxes)[i + 1 :]:
            overlap = (masks[a] & masks[b]).sum()
            gaps.append({"pair": [a, b], "overlap_px": int(overlap)})
    report["overlaps"] = [g for g in gaps if g["overlap_px"]]
    if geometry.hands_zone:
        hx1, hy1, hx2, hy2 = geometry.hands_zone
        zone = union[hy1:hy2, hx1:hx2]
        report["hands_zone_covered"] = round(float(zone.mean()), 3) if zone.size else None
    report["products_share_of_frame"] = round(float(union.mean()), 3)
    label = estimate_label_box(W, H, settings.ai_label_text, settings.ai_label_position)
    report["shopee_overlay"] = overlay_report(label, masks, W, H, args.phone_aspect)
    if args.background_frames:
        # Products and the AI label sit on the captured /host frames: keep them out of the background regions.
        exclude = union.copy()
        for x1, y1, x2, y2 in geometry.keep_out_boxes():
            exclude[max(y1, 0) : max(y2, 0), max(x1, 0) : max(x2, 0)] = True
        background_dir = args.background_dir or settings.avatar_dir / "background"
        sets = _background_sets(args.background_frames)
        report["background"] = measure_background(sets, background_dir, args.out, exclude)
    args.out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{args.out.with_suffix('.png')}  mode={layout.mode}  products cover {report['products_share_of_frame']:.0%}")
    print(f"  desk edge: character.json {desk_y} px, seen in the frame {edge_y} px")
    if abs(desk_y - edge_y) > DESK_EDGE_TOLERANCE_PX:
        print("  ! character desk_top does not match the desk in this frame: check the _zones image, then the")
        print(f"    character's scene.desk_top (seen {edge_y / H:.3f})")
    for pid, row in report["products"].items():
        print(
            f"  {pid}: h={row['height_px']} scale={row.get('scale_vs_head', '-')} sharp={row['sharpness_ratio']}"
            f" edge={row['soft_edge_share']} p95={row['p95_luma']}/{row['room_p95_luma']}"
            f" warm={row.get('warm_diff', '-')}"
        )
        for flag in row["flags"]:
            print(f"    ! {flag}")
    if report["overlaps"]:
        print(f"  ! overlaps: {report['overlaps']}")
    if report.get("hands_zone_covered") is not None:
        print(f"  hands zone covered by products: {report['hands_zone_covered']:.0%}")
    overlay = report["shopee_overlay"]
    label_row = overlay.get("label", {})
    print(
        f"  Shopee app (phone {args.phone_aspect:.3f}): AI label {settings.ai_label_position}"
        f" hidden {label_row.get('share', 0):.0%}, frame shown x {overlay['shown_box'][0]}-{overlay['shown_box'][2]}"
    )
    for flag in overlay["flags"]:
        print(f"    ! {flag}")
    if "background" in report:
        _print_background(report["background"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
