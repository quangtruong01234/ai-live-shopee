"""Draw a demo scene set into `assets/scenes/demo/` (009 T003): a wooden desk and one "ẢNH MẪU" picture per product.

The product pictures are drawn shapes, not photos and not AI images: they only stand in until the customer's real photos
arrive, and `provenance.json` marks them `placeholder: true` so `check` warns before a real session.
Run: `uv run python scripts/make_demo_scene.py [--content data/products/demo.docx] [--out assets/scenes/demo]`.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ai_live.core.config import Settings
from ai_live.products.docx_loader import load_catalog_file
from ai_live.scene.fonts import load_fonts

DESK_SIZE = (1080, 420)
ART_SIZE = (360, 640)
# Pastel bodies with a darker cap, one per product in file order.
PALETTE = [
    ((250, 236, 214), (232, 120, 70)),
    ((222, 238, 246), (70, 130, 180)),
    ((232, 244, 226), (90, 150, 90)),
    ((246, 226, 236), (180, 90, 130)),
    ((238, 232, 250), (120, 100, 180)),
]


def draw_desk(size: tuple[int, int] = DESK_SIZE, seed: int = 9) -> Image.Image:
    """Warm wooden planks seen from the front, with a lit front edge."""
    rng = random.Random(seed)
    w, h = size
    desk = Image.new("RGB", size, (139, 94, 60))
    draw = ImageDraw.Draw(desk)
    for y in range(h):
        t = y / h
        base = (round(176 - 60 * t), round(122 - 44 * t), round(80 - 30 * t))
        draw.line([(0, y), (w, y)], fill=base)
    # Grain: long faint wavy streaks.
    for _ in range(140):
        y = rng.uniform(0, h)
        tone = rng.choice([-1, 1]) * rng.randint(6, 18)
        points = []
        for x in range(0, w + 40, 40):
            y += rng.uniform(-1.2, 1.2)
            points.append((x, y))
        color = desk.getpixel((0, max(0, min(h - 1, round(y)))))
        draw.line(points, fill=tuple(max(0, min(255, c + tone)) for c in color), width=rng.randint(1, 3))
    desk = desk.filter(ImageFilter.GaussianBlur(0.8))
    draw = ImageDraw.Draw(desk)
    draw.rectangle([0, 0, w, 5], fill=(214, 168, 120))
    draw.line([(0, 6), (w, 6)], fill=(96, 62, 38), width=2)
    return desk


def _outlined(body: tuple[int, int, int], edge: tuple[int, int, int]) -> dict[str, object]:
    return {"fill": (*body, 255), "outline": (*edge, 255), "width": 6}


def draw_placeholder(name: str, index: int, fonts_path: Path | None = None) -> Image.Image:
    """A bottle-like shape with "ẢNH MẪU" on it: obviously a stand-in, never mistaken for the real product."""
    body_color, cap_color = PALETTE[index % len(PALETTE)]
    w, h = ART_SIZE
    art = Image.new("RGBA", ART_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(art)
    shape = index % 3
    if shape == 0:  # tall bottle with a cap
        draw.rounded_rectangle([110, 20, 250, 150], radius=18, fill=(*cap_color, 255))
        draw.rounded_rectangle([40, 130, 320, 630], radius=60, **_outlined(body_color, cap_color))
        label_box = (60, 300, 300, 520)
    elif shape == 1:  # tube standing on its cap
        draw.polygon([(60, 40), (300, 40), (270, 520), (90, 520)], fill=(*body_color, 255), outline=(*cap_color, 255))
        draw.rectangle([60, 30, 300, 60], fill=(*cap_color, 255))
        draw.rounded_rectangle([110, 510, 250, 630], radius=14, fill=(*cap_color, 255))
        label_box = (90, 160, 270, 400)
    else:  # pump bottle
        draw.rectangle([165, 20, 195, 120], fill=(*cap_color, 255))
        draw.rounded_rectangle([110, 10, 260, 40], radius=10, fill=(*cap_color, 255))
        draw.rounded_rectangle([130, 110, 230, 190], radius=12, fill=(*cap_color, 255))
        draw.rounded_rectangle([50, 180, 310, 630], radius=40, **_outlined(body_color, cap_color))
        label_box = (70, 330, 290, 540)
    fonts = load_fonts(fonts_path)
    draw.rounded_rectangle(label_box, radius=16, fill=(255, 255, 255, 235))
    cx = (label_box[0] + label_box[2]) / 2
    draw.text((cx, label_box[1] + 24), "ẢNH MẪU", font=fonts.get(40), fill=(*cap_color, 255), anchor="ma")
    words, lines, line = name.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if fonts.get(24, bold=False).getlength(trial) > label_box[2] - label_box[0] - 24 and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    y = label_box[1] + 84
    for text in lines[:3]:
        draw.text((cx, y), text, font=fonts.get(24, bold=False), fill=(60, 60, 60, 255), anchor="ma")
        y += 32
    return art


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings()
    parser = argparse.ArgumentParser(prog="make_demo_scene")
    parser.add_argument("--content", type=Path, default=settings.product_data_path)
    parser.add_argument("--out", type=Path, default=Path("assets/scenes/demo"))
    args = parser.parse_args(argv)

    catalog = load_catalog_file(args.content, settings.content_max_bytes)
    out: Path = args.out
    (out / "products").mkdir(parents=True, exist_ok=True)
    draw_desk().save(out / "desk.png")
    customer_id = settings.customer_id or "demo_customer_01"
    today = date.today().isoformat()
    records = {}
    for index, product in enumerate(catalog.products):
        draw_placeholder(product.name, index, settings.scene_font_path).save(out / "products" / f"{product.id}.png")
        records[product.id] = {
            "original": None,
            "received_from": "",
            "received_at": "",
            "edits": [],
            "placeholder": True,
        }
    scene = {
        "schema_version": 1,
        "scene_id": out.name,
        "customer_id": customer_id,
        "desk": "desk.png",
        "desk_color": "#8B5E3C",
        "accent_color": "#E8573C",
        "products_dir": "products",
        "provenance": "provenance.json",
        "layout": {"desk_top": 0.76, "max_slots": 5, "highlight_scale": 1.3, "show_promotion": True},
    }
    provenance = {
        "schema_version": 1,
        "customer_id": customer_id,
        "desk": {
            "source": "drawn",
            "tool": "scripts/make_demo_scene.py",
            "license": "own",
            "created": today,
            "notes": "",
        },
        "products": records,
    }
    (out / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã tạo bộ cảnh mẫu {out} ({len(catalog.products)} ảnh ẢNH MẪU, bàn vẽ). Thay ảnh thật trước phiên thật.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
