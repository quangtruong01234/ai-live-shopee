"""Editor-style product desk as a separate OBS layer (ADR-101): one transparent PNG laid over the app's Browser Source.

The app is not changed: OBS stacks this picture on top of the `/obs` Browser Source, the same way an editor stacks
layers in Photoshop. The picture holds the desk surface (drawn exactly where and how the app draws its own, so it
covers it seamlessly), then contact and cast shadows, satin reflections and the customer's real product cut-outs,
arranged in dense clusters with depth (back row smaller and dimmer) and a front-left key light.

Rules kept here, not in OBS:
- Only the customer's own confirmed cut-outs are used (the active version in `uploads/images.json` with
  `rights_confirmed_at`), never AI-drawn products (ADR-100, FR-009a).
- Nothing is drawn in the top band where the pipeline burns in the "AI-GENERATED CONTENT" label; the script fails
  rather than write a picture that could cover it (CLAUDE.md constraint 2).
- A still graphic layer only: the host, voice and lip-sync stay generated in real time by the app.

Usage:
    uv run python scripts/obs/desk_overlay.py                         # default arrangement, scene `demo`
    uv run python scripts/obs/desk_overlay.py --arrangement my.json   # your own placements
    uv run python scripts/obs/desk_overlay.py --write-arrangement     # dump the default to edit by hand
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

REPO = Path(__file__).resolve().parents[2]
# The OBS Browser Source size (docs/RUNBOOK.md §8) and the fork frame it upscales.
WIDTH, HEIGHT = 1080, 1872
FORK_WIDTH, FORK_HEIGHT = 480, 832
# The burned-in AI label sits in the top band of the frame; the overlay must stay fully transparent there.
LABEL_BAND = 0.12
OUT_DIR = "obs_overlay"

# Editor look, tuned on the mock (scratchpad compose.py) against the live host.
DEPTH_SCALE = 0.93  # a back-row unit is a little smaller...
DEPTH_DIM = 0.92  # ...and a little darker
SIDE_LIGHT = 0.14  # key light front-left: the right side of each unit falls off by this much
CUT_BRIGHTNESS, CUT_CONTRAST, CUT_BLUR = 0.9, 0.96, 0.6  # studio cut-outs pulled into the room light
REFLECT_ALPHA, REFLECT_PX, REFLECT_BLUR = 0.16, 70, 1.5
OCCLUSION_FILL, OCCLUSION_BLUR = 215, 3
CAST_FILL, CAST_BLUR = 120, 11
SHADOW_COLOR = (35, 22, 12)
METAL_DIM = 0.9  # bare aluminium catches studio light; tame it to the room


@dataclass(frozen=True)
class Unit:
    """One product unit on the desk: centre x and foot y in 1080x1872 OBS pixels, drawn height in pixels."""

    product_id: str
    x: int
    feet: int
    height: int
    back_row: bool = False
    metal: bool = False


# The mock's arrangement: two staggered bottle clusters left and right, a 6-pack and a can pyramid in front of them,
# the Tet carton front and centre below the host's hands (all feet below the desk line, nothing over the face).
DEFAULT_ARRANGEMENT: list[dict] = [
    *(
        {"product": "coca-cola-zero-chai-thuy-tinh-237ml", "x": x, "feet": 1515, "height": 240, "back_row": True}
        for x in (70, 150, 230)
    ),
    *({"product": "coca-cola-zero-chai-thuy-tinh-237ml", "x": x, "feet": 1560, "height": 240} for x in (110, 190)),
    {"product": "loc-6-chai-coca-cola-355ml", "x": 175, "feet": 1690, "height": 270},
    *(
        {"product": "coca-cola-chai-500ml", "x": x, "feet": 1515, "height": 280, "back_row": True}
        for x in (850, 930, 1010)
    ),
    *({"product": "coca-cola-chai-500ml", "x": x, "feet": 1560, "height": 280} for x in (890, 970)),
    {"product": "coca-cola-lon-355ml", "x": 860, "feet": 1690, "height": 160, "metal": True},
    {"product": "coca-cola-lon-355ml", "x": 950, "feet": 1690, "height": 160, "metal": True},
    {"product": "coca-cola-lon-355ml", "x": 905, "feet": 1730, "height": 160, "metal": True},
    {"product": "thung-24-lon-coca-cola-tet-320ml", "x": 540, "feet": 1820, "height": 300},
]


class OverlayError(RuntimeError):
    """Why the overlay cannot be made (message in Vietnamese, for the operator)."""


def parse_units(raw: list[dict]) -> list[Unit]:
    units = []
    for i, item in enumerate(raw):
        try:
            height = int(item["height"])
            back = bool(item.get("back_row", False))
            units.append(
                Unit(
                    str(item["product"]),
                    int(item["x"]),
                    int(item["feet"]),
                    round(height * DEPTH_SCALE) if back else height,
                    back,
                    bool(item.get("metal", False)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OverlayError(f"Mục {i} trong arrangement thiếu hoặc sai trường: {exc}") from exc
    return units


def active_cutout(scene_dir: Path, product_id: str) -> Path:
    """The product's active, rights-confirmed upload (012/013 `uploads/images.json`)."""
    manifest = json.loads((scene_dir / "uploads" / "images.json").read_text(encoding="utf-8"))
    entry = manifest.get("products", {}).get(product_id)
    if not isinstance(entry, dict) or not entry.get("active"):
        raise OverlayError(f"{product_id}: chưa có ảnh tải lên đang dùng (tải ảnh thật ở trang điều khiển)")
    version_id = entry["active"]
    version = entry.get("versions", {}).get(version_id, {})
    if not version.get("rights_confirmed_at"):
        raise OverlayError(f"{product_id}: ảnh {version_id} chưa được xác nhận quyền dùng")
    path = scene_dir / "uploads" / product_id / f"{version_id}.png"
    if not path.is_file():
        raise OverlayError(f"{product_id}: thiếu file {path}")
    return path


def desk_top(scene_dir: Path, character_dir: Path | None) -> float:
    """The desk line the app uses: the character's `desk_top` wins over the scene's (013 research R2)."""
    if character_dir is not None:
        manifest = character_dir / "character.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            found = _find_key(data, "desk_top")
            if isinstance(found, (int, float)):
                return float(found)
    scene = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
    return float(scene.get("layout", {}).get("desk_top", 0.72))


def _find_key(data: object, key: str) -> object:
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


def desk_layer(scene_dir: Path, top: float) -> Image.Image:
    """The desk drawn as the app draws it on the 480x832 fork frame, then upscaled like the video is."""
    scene = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
    small = Image.new("RGBA", (FORK_WIDTH, FORK_HEIGHT), (0, 0, 0, 0))
    y = round(top * FORK_HEIGHT)
    height = FORK_HEIGHT - y
    desk_path = scene_dir / scene.get("desk", "desk.png")
    if not desk_path.is_file():
        raise OverlayError(f"Thiếu ảnh mặt bàn {desk_path}")
    desk = Image.open(desk_path).convert("RGBA")
    scale = FORK_WIDTH / desk.width
    desk = desk.resize((FORK_WIDTH, max(height, round(desk.height * scale))), Image.Resampling.LANCZOS)
    small.alpha_composite(desk.crop((0, 0, FORK_WIDTH, height)), (0, y))
    return small.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)


def _cut(path: Path, height: int) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if bbox is None:
        raise OverlayError(f"{path.name} trong suốt hoàn toàn")
    im = im.crop(bbox)
    im = im.resize((max(1, round(im.width * height / im.height)), height), Image.Resampling.LANCZOS)
    rgb = ImageEnhance.Brightness(im.convert("RGB")).enhance(CUT_BRIGHTNESS)
    rgb = ImageEnhance.Contrast(rgb).enhance(CUT_CONTRAST)
    r, g, b = rgb.split()
    rgb = Image.merge("RGB", (r, g.point(lambda v: v * 0.985), b.point(lambda v: v * 0.95)))
    im = Image.merge("RGBA", (*rgb.split(), im.getchannel("A")))
    return im.filter(ImageFilter.GaussianBlur(CUT_BLUR))  # match the softness of the upscaled host


def _dim(im: Image.Image, factor: float) -> Image.Image:
    a = np.asarray(im).astype(np.float32)
    a[..., :3] *= factor
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def _side_light(im: Image.Image) -> Image.Image:
    ramp = np.linspace(1.0, 1.0 - SIDE_LIGHT, im.width, dtype=np.float32)[None, :, None]
    a = np.asarray(im).astype(np.float32)
    a[..., :3] *= ramp
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def compose(scene_dir: Path, units: list[Unit], top: float) -> Image.Image:
    desk_y = round(top * FORK_HEIGHT) * HEIGHT / FORK_HEIGHT
    for unit in units:
        if unit.feet <= desk_y:
            raise OverlayError(f"{unit.product_id} ở feet={unit.feet}: chân phải nằm dưới mép bàn y={desk_y:.0f}")
    out = desk_layer(scene_dir, top)
    out.alpha_composite(draw_units(scene_dir, units, (WIDTH, HEIGHT)))
    return out


def draw_units(scene_dir: Path, units: list[Unit], size: tuple[int, int], ground: bool = True) -> Image.Image:
    """Shadows, reflections and cut-outs of the units on a transparent layer of `size` (also used by photo_layers).

    `ground=False` draws the cut-outs only: on the real desk photo the extra shadow made the carton look afloat.
    """
    width, height = size
    cache: dict[str, Path] = {}
    shadows = Image.new("L", size, 0)
    reflect = Image.new("RGBA", size, (0, 0, 0, 0))
    products = Image.new("RGBA", size, (0, 0, 0, 0))
    # Painter's order: the farther the foot, the earlier the unit is drawn.
    for unit in sorted(units, key=lambda u: u.feet):
        if unit.product_id not in cache:
            cache[unit.product_id] = active_cutout(scene_dir, unit.product_id)
        im = _side_light(_cut(cache[unit.product_id], unit.height))
        if unit.back_row:
            im = _dim(im, DEPTH_DIM)
        if unit.metal:
            im = _dim(im, METAL_DIM)
        x, y = round(unit.x - im.width / 2), unit.feet - im.height
        # Satin desk reflection: flipped, faded out over a short distance below the foot.
        flip = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        fade = np.linspace(REFLECT_ALPHA, 0.0, min(flip.height, REFLECT_PX), dtype=np.float32)
        weight = np.zeros((flip.height, flip.width), np.float32)
        weight[: fade.size] = fade[:, None]
        flip.putalpha(Image.fromarray((np.asarray(flip.getchannel("A")) * weight).astype(np.uint8), "L"))
        _paste(reflect, flip.filter(ImageFilter.GaussianBlur(REFLECT_BLUR)), x, unit.feet)
        # Footprint from the real silhouette: the columns that touch the bottom rows of the cut-out.
        alpha = np.asarray(im.getchannel("A"))
        cols = np.where(alpha[-max(3, alpha.shape[0] // 30) :].max(axis=0) > 128)[0]
        if cols.size == 0:
            cols = np.arange(im.width)
        fx0, fx1 = x + int(cols.min()), x + int(cols.max())
        fw = fx1 - fx0
        occlusion = Image.new("L", size, 0)  # dark thin core right under the base
        ImageDraw.Draw(occlusion).ellipse([fx0 - 2, unit.feet - 7, fx1 + 2, unit.feet + 5], fill=OCCLUSION_FILL)
        cast = Image.new("L", size, 0)  # soft shadow pushed back-right, away from the key light
        ImageDraw.Draw(cast).ellipse([fx0 + fw * 0.08, unit.feet - 26, fx1 + fw * 0.25, unit.feet + 4], fill=CAST_FILL)
        shadows = ImageChops.lighter(
            shadows,
            ImageChops.lighter(
                occlusion.filter(ImageFilter.GaussianBlur(OCCLUSION_BLUR)),
                cast.filter(ImageFilter.GaussianBlur(CAST_BLUR)),
            ),
        )
        _paste(products, im, x, y)
    shadow_rgba = Image.new("RGBA", (width, height), (*SHADOW_COLOR, 0))
    shadow_rgba.putalpha(shadows)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if ground:
        out.alpha_composite(shadow_rgba)
        out.alpha_composite(reflect)
    out.alpha_composite(products)
    return out


def _paste(layer: Image.Image, image: Image.Image, x: int, y: int) -> None:
    """`alpha_composite` that accepts a place partly outside the layer."""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(image.width, layer.width - x), min(image.height, layer.height - y)
    if left < right and top < bottom:
        layer.alpha_composite(image.crop((left, top, right, bottom)), (x + left, y + top))


def check_label_band(image: Image.Image) -> None:
    band = np.asarray(image.getchannel("A"))[: round(LABEL_BAND * HEIGHT)]
    if band.any():
        raise OverlayError("Lớp ghép có điểm ảnh trong vùng nhãn AI phía trên: dời sản phẩm xuống")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ghép lớp bàn sản phẩm kiểu editor cho OBS (ADR-101)")
    parser.add_argument("--scene", default="assets/scenes/demo", help="thư mục cảnh")
    parser.add_argument("--character", default="assets/avatars/demo_host_02", help="thư mục nhân vật (desk_top)")
    parser.add_argument("--arrangement", help="file JSON vị trí từng sản phẩm (mặc định: bố cục mẫu)")
    parser.add_argument("--out", help="file PNG ra (mặc định <scene>/obs_overlay/desk_overlay.png)")
    parser.add_argument("--write-arrangement", action="store_true", help="ghi bố cục mặc định ra để sửa tay")
    args = parser.parse_args(argv)

    scene_dir = (REPO / args.scene).resolve()
    out_dir = scene_dir / OUT_DIR
    if args.write_arrangement:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "arrangement.json"
        path.write_text(json.dumps(DEFAULT_ARRANGEMENT, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã ghi {path}")
        return 0
    try:
        raw = DEFAULT_ARRANGEMENT
        if args.arrangement:
            raw = json.loads(Path(args.arrangement).read_text(encoding="utf-8"))
        elif (out_dir / "arrangement.json").is_file():
            raw = json.loads((out_dir / "arrangement.json").read_text(encoding="utf-8"))
        top = desk_top(scene_dir, (REPO / args.character) if args.character else None)
        image = compose(scene_dir, parse_units(raw), top)
        check_label_band(image)
    except (OverlayError, OSError, json.JSONDecodeError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else out_dir / "desk_overlay.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"Đã ghép {out} ({WIDTH}x{HEIGHT}, mép bàn {top:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
