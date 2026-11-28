"""Put several stills side by side with a label under each, to compare variants by eye (live-scene-realism skill).

    uv run python .claude/skills/live-scene-realism/scripts/contact_sheet.py out/realism/sheet.png \
        out/realism/base.png=base out/realism/v1.png="main 0.32"
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TILE_W = 480
LABEL_H = 34
GAP = 8


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    out, items = Path(argv[0]), argv[1:]
    tiles = []
    for item in items:
        path, _, label = item.partition("=")
        img = Image.open(path).convert("RGB")
        img = img.resize((TILE_W, round(img.height * TILE_W / img.width)), Image.Resampling.LANCZOS)
        tiles.append((img, label or Path(path).stem))
    height = max(t.height for t, _ in tiles) + LABEL_H
    sheet = Image.new("RGB", (len(tiles) * (TILE_W + GAP) - GAP, height), (24, 24, 24))
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(sheet)
    for i, (img, label) in enumerate(tiles):
        x = i * (TILE_W + GAP)
        sheet.paste(img, (x, 0))
        draw.text((x + 8, img.height + 6), label, fill=(240, 240, 240), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"{out} ({len(tiles)} tiles)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
