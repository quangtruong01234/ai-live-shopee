"""Photo layers around the AI host in OBS (ADR-102): a shop picture behind and a product desk photo in front.

The app is not changed. It runs the scene `obs_layers`, which draws the host over a solid green plate and an empty
desk; OBS keys the green out (Chroma Key on the `/obs` Browser Source) and stacks, bottom to top:

1. `background.png`: the confirmed shop photo, cover-cropped to the 1080x1920 canvas, sharp by default (recipe
   `background_blur_px`; the user asked for a sharp room in the OBS demo, an exception to FR-009a, ADR-102);
2. the keyed host (`/obs` Browser Source at (0, 24), 1080x1872);
3. `desk_front.png`: the desk photo cut like an editor would: the table from its back edge down, plus the product
   groups standing on it (sharp against the blurred room, so a local-sharpness mask separates them), with any
   object that would hide the host's hands removed and the wood patched behind it; then the customer's real
   cut-outs (`hero` units) placed in front with contact shadows and reflections (helpers from `desk_overlay.py`).

Rules kept here:
- Each source picture needs a confirmation file (who allowed it, sha256): an edited or swapped file is refused.
- Nothing of the desk layer reaches the top band where the AI label is burned in (CLAUDE.md constraint 2).
- Still pictures only around a host that the app generates in real time; the Meet `/host` page does not show them.

Usage:
    uv run python scripts/obs/photo_layers.py                    # both layers with the recipe below
    uv run python scripts/obs/photo_layers.py --write-recipe     # dump the recipe to edit by hand
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desk_overlay import (  # noqa: E402
    FORK_HEIGHT,
    HEIGHT,
    LABEL_BAND,
    SHADOW_COLOR,
    OverlayError,
    Unit,
    active_cutout,
    desk_top,
    draw_units,
    parse_units,
)

from ai_live.scene.shop_photo import load_shop_photo  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CANVAS_W, CANVAS_H = 1080, 1920
SOURCE_Y = (CANVAS_H - HEIGHT) // 2  # where the 1080x1872 host source sits on the canvas (docs/RUNBOOK.md §8)
LAYER_DIR = "layers"
DESK_PHOTO = "source/desk_photo.png"
DESK_CONFIRMATION = "source/desk_photo.json"

# Recipe for the Gemini desk photo of 2026-11-28 (1536x2752; coordinates in that picture's pixels).
DEFAULT_RECIPE: dict = {
    "back_edge_row": 1958,  # where the table top meets the room (its front lip is row ~2460, canvas y ~1838)
    # Local sharpness: the room is blurred flat (energy ~3), products are sharp; very saturated red counts too.
    "energy_min": 5.0,
    "saturation_min": 90,
    "edge_trim_px": 2,  # shave the blurred-room halo off the product outline
    # The centre carton would hide the host's hands and carries garbled AI text: cut it out...
    # The carton's right side ends at x~1095 and the first Zero Sugar bottle starts at x~1101: stop at 1097 so the
    # bottle keeps its left edge (1104 shaved a flat strip off it).
    "remove": [[[466, 1650], [600, 1640], [1097, 1690], [1097, 2135], [985, 2228], [466, 2120]]],
    # ...and its shadow on the table, but keep the 6-pack bottles and carrier standing in front of it.
    "remove_on_table": [[[600, 2110], [1097, 2120], [1097, 2262], [600, 2262]]],
    "keep": [
        [[448, 1876], [507, 1876], [507, 2300], [448, 2300]],
        [[505, 1906], [565, 1906], [565, 1942], [505, 1942]],
        [[511, 1942], [559, 1942], [560, 1978], [600, 2045], [600, 2300], [483, 2300], [483, 2045], [511, 1978]],
        [[436, 2120], [618, 2120], [618, 2370], [436, 2370]],
    ],
    # Wood under the removed carton: clean front rows squeezed into the hole (farther wood looks shorter),
    # relit row by row from a clean strip at the same depth.
    "wood_rows": [2268, 2455],
    "light_columns": [1505, 1530],
    # The customer's real cut-outs, in canvas pixels (1080x1920): the main product front and centre, below the hands.
    "hero": [{"product": "thung-24-lon-coca-cola-tet-320ml", "x": 540, "feet": 1815, "height": 330}],
    # No ground shadow under the hero: the soft ellipse read as the carton hovering above the desk (user, 2026-11-28).
    # A recipe may still add {"alpha": 150, "blur": 14, "depth": 34} under "hero_shadow".
    "hero_shadow": None,
    # Gaussian radius on the 1080 px background. 0 = sharp (the user's call for the OBS demo, ADR-102); the app's own
    # minimum for an AI-made shop photo would be AI_MIN_SOFTNESS_PX * 1080 / 480 = 9.
    "background_blur_px": 0,
}


def _confirmed(path: Path, confirmation: Path) -> None:
    if not path.is_file():
        raise OverlayError(f"Thiếu ảnh {path}")
    try:
        record = json.loads(confirmation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OverlayError(f"Thiếu hoặc hỏng file xác nhận {confirmation}") from exc
    if not record.get("confirmed_by") or record.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
        raise OverlayError(f"{path.name} chưa được xác nhận hoặc đã bị sửa sau khi xác nhận ({confirmation.name})")


def _polygons(size: tuple[int, int], polygons: list) -> np.ndarray:
    mask = Image.new("L", size, 0)
    for points in polygons:
        ImageDraw.Draw(mask).polygon([tuple(p) for p in points], fill=255)
    return np.asarray(mask) > 0


def desk_front(photo: Image.Image, recipe: dict, canvas_desk_y: float) -> Image.Image:
    """The cut desk photo on a transparent canvas, its table back edge on the app's desk line."""
    a = np.asarray(photo.convert("RGB")).astype(np.float32)
    h0, w0 = a.shape[:2]
    back, size = int(recipe["back_edge_row"]), (w0, h0)

    high = sum(np.abs(a[..., c] - ndi.gaussian_filter(a[..., c], 2.0)) for c in range(3))
    energy = ndi.gaussian_filter(high, 3)
    saturation = a.max(axis=2) - a.min(axis=2)
    objects = (energy > recipe["energy_min"]) | (saturation > recipe["saturation_min"])
    objects = ndi.binary_opening(ndi.binary_fill_holes(ndi.binary_closing(objects, iterations=4)), iterations=3)

    keep = _polygons(size, recipe["keep"])
    remove = _polygons(size, recipe["remove"]) & ~keep
    hole = (remove | (_polygons(size, recipe["remove_on_table"]) & ~keep)) & (np.arange(h0)[:, None] >= back)

    above = objects & ~remove
    above = ndi.binary_opening(above, iterations=4)  # slivers left along a removed edge
    above = ndi.binary_erosion(above, iterations=int(recipe["edge_trim_px"]))
    above[back:] = True
    # Only what stands on the table: a blob that does not reach the back edge is the room, not a product.
    labels, _ = ndi.label(above)
    touching = np.unique(labels[back - 2 : back + 2])
    above = np.isin(labels, touching[touching > 0])

    table = a
    if hole.any():
        src0, src1 = recipe["wood_rows"]
        rows = np.arange(back, int(np.nonzero(hole.any(axis=1))[0].max()) + 1)
        src = np.round(src0 + (rows - back) * (src1 - src0) / max(1, rows[-1] - back)).astype(int)
        c0, c1 = recipe["light_columns"]
        ref = a[np.minimum(rows, back + 170), c0:c1].mean(axis=1)
        cur = a[src, c0:c1].mean(axis=1)
        fill = a.copy()
        fill[rows] = a[src] * (ref / np.maximum(cur, 1.0))[:, None, :]
        blend = np.clip(ndi.gaussian_filter(ndi.binary_dilation(hole, iterations=4).astype(np.float32), 3), 0, 1)
        table = a * (1 - blend[..., None]) + fill * blend[..., None]

    alpha = ndi.gaussian_filter(above.astype(np.float32), 0.8)
    alpha[back + 3 :] = 1.0
    cut = Image.fromarray(np.dstack([np.clip(table, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")

    scale = CANVAS_W / w0
    cut = cut.resize((CANVAS_W, round(h0 * scale)), Image.Resampling.LANCZOS)
    top = round(canvas_desk_y - back * scale)
    out = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    out.alpha_composite(cut.crop((0, max(0, -top), CANVAS_W, min(cut.height, CANVAS_H - top))), (0, max(0, top)))
    if top + cut.height < CANVAS_H:
        raise OverlayError(f"Ảnh bàn chỉ phủ tới y={top + cut.height}, phải phủ tới đáy khung {CANVAS_H}")
    return out


def background(scene_dir: Path, blur_px: float) -> Image.Image:
    """The scene's confirmed shop photo, cover-cropped to the canvas, blurred by `blur_px` (0 = sharp)."""
    photo = load_shop_photo(scene_dir)
    if photo.image is None:
        raise OverlayError(f"{scene_dir.name}: ảnh shop chưa có hoặc chưa xác nhận ({photo.reason})")
    im = photo.image
    scale = max(CANVAS_W / im.width, CANVAS_H / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    left, top = (im.width - CANVAS_W) // 2, (im.height - CANVAS_H) // 2
    im = im.crop((left, top, left + CANVAS_W, top + CANVAS_H))
    if blur_px > 0:
        im = im.filter(ImageFilter.GaussianBlur(blur_px))
    return im


def hero_shadows(shop_dir: Path, units: list[Unit], recipe: dict) -> Image.Image:
    """A soft ground shadow under each hero unit, pushed back-right like the photo's own shadows."""
    spec = recipe.get("hero_shadow") or {}
    depth = spec.get("depth", 34)
    mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    for unit in units:
        with Image.open(active_cutout(shop_dir, unit.product_id)) as im:
            box = im.getchannel("A").getbbox() or (0, 0, im.width, im.height)
        half = unit.height * (box[2] - box[0]) / max(1, box[3] - box[1]) / 2
        ImageDraw.Draw(mask).ellipse(
            [unit.x - half - 4, unit.feet - depth, unit.x + half * 1.15, unit.feet + 6], fill=spec.get("alpha", 150)
        )
    out = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*SHADOW_COLOR, 0))
    out.putalpha(mask.filter(ImageFilter.GaussianBlur(spec.get("blur", 14))))
    return out


def check_label_band(layer: Image.Image) -> None:
    band = np.asarray(layer.getchannel("A"))[: SOURCE_Y + round(LABEL_BAND * HEIGHT)]
    if band.any():
        raise OverlayError("Lớp bàn có điểm ảnh trong vùng nhãn AI phía trên")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lớp ảnh nền và bàn sản phẩm quanh host AI trong OBS (ADR-102)")
    parser.add_argument("--layers", default="assets/scenes/obs_layers", help="cảnh bàn trống, ảnh ra ở layers/")
    parser.add_argument("--shop", default="assets/scenes/demo", help="cảnh có ảnh shop và ảnh sản phẩm thật")
    parser.add_argument("--character", default="assets/avatars/demo_host_02", help="thư mục nhân vật (desk_top)")
    parser.add_argument("--recipe", help="file JSON công thức cắt ảnh bàn (mặc định: công thức trong script)")
    parser.add_argument("--write-recipe", action="store_true", help="ghi công thức mặc định ra để sửa tay")
    args = parser.parse_args(argv)

    out_dir = (REPO / args.layers).resolve() / LAYER_DIR
    shop_dir = (REPO / args.shop).resolve()
    recipe_path = Path(args.recipe) if args.recipe else out_dir / "recipe.json"
    if args.write_recipe:
        out_dir.mkdir(parents=True, exist_ok=True)
        recipe_path.write_text(json.dumps(DEFAULT_RECIPE, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã ghi {recipe_path}")
        return 0
    try:
        recipe = json.loads(recipe_path.read_text(encoding="utf-8")) if recipe_path.is_file() else DEFAULT_RECIPE
        _confirmed(out_dir / DESK_PHOTO, out_dir / DESK_CONFIRMATION)
        top = desk_top(shop_dir, (REPO / args.character) if args.character else None)
        desk_y = SOURCE_Y + round(top * FORK_HEIGHT) * HEIGHT / FORK_HEIGHT
        layer = desk_front(Image.open(out_dir / DESK_PHOTO), recipe, desk_y)
        heroes = parse_units(recipe.get("hero", []))
        if recipe.get("hero_shadow"):
            layer.alpha_composite(hero_shadows(shop_dir, heroes, recipe))
        ground = bool(recipe.get("hero_shadow"))
        layer.alpha_composite(draw_units(shop_dir, heroes, (CANVAS_W, CANVAS_H), ground=ground))
        check_label_band(layer)
        back = background(shop_dir, float(recipe.get("background_blur_px", 0)))
    except (OverlayError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    layer.save(out_dir / "desk_front.png")
    back.save(out_dir / "background.png")
    print(f"Đã ghép desk_front.png và background.png trong {out_dir} (bàn y={desk_y:.0f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
