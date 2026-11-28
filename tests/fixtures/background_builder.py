"""014 T004: builds a fake `assets/avatars/<id>/background/` folder (014 data-model §2) for app tests.

Masks are ellipses drawn on the fly at frame size; the preview frame is a flat two-tone image. No real model photo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw

CHARACTER_ID = "demo_host_01"
WIDTH, HEIGHT = 480, 832
DESK_TOP_PX = 640
FINGERPRINTS = ("0a1b2c3d", "1b2c3d4e", "2c3d4e5f")

Variant = Literal["valid", "missing", "mismatch"]


def ellipse_mask(width: int = WIDTH, height: int = HEIGHT, *, shift_px: int = 0) -> Image.Image:
    """8-bit gray mask: 0 = background, 255 = person (head + body ellipses) and the desk band."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    cx = width // 2 + shift_px
    draw.ellipse((cx - 70, height // 4 - 95, cx + 70, height // 4 + 95), fill=255)
    draw.ellipse((cx - 170, height // 4 + 80, cx + 170, height // 4 + 520), fill=255)
    draw.rectangle((0, DESK_TOP_PX, width, height), fill=255)
    return mask


def preview_frame(width: int = WIDTH, height: int = HEIGHT) -> Image.Image:
    """Frame 0 of the loop: gray room, darker person shape from the first mask."""
    frame = Image.new("RGB", (width, height), (140, 130, 120))
    frame.paste((160, 40, 70), mask=ellipse_mask(width, height))
    return frame


def manifest(
    *,
    character_id: str = CHARACTER_ID,
    method: str = "plate",
    width: int = WIDTH,
    height: int = HEIGHT,
    reviewed: bool = False,
    fingerprints: tuple[str, ...] = FINGERPRINTS,
    source: str = "demo_host_01__w2l",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "character_id": character_id,
        "method": method,
        "model": None,
        "width": width,
        "height": height,
        "desk_top_px": DESK_TOP_PX,
        "frames": [
            {"fingerprint": fp, "mask": f"masks/{fp}.png", "sources": [f"cycle:{source}:{i}"]}
            for i, fp in enumerate(fingerprints)
        ],
        "light": {"person_luma": 132.0, "person_rb": 1.08, "room_luma": 118.0, "room_rb": 0.97},
        "leak": {"frames_flagged": 0, "max_blob_px": 0},
        "created_at": "2026-11-24T09:00:00+07:00",
        "reviewed": reviewed,
        "reviewed_by": "operator" if reviewed else None,
        "reviewed_at": "2026-11-24T10:00:00+07:00" if reviewed else None,
    }


def make_background_dir(
    character_dir: Path,
    variant: Variant = "valid",
    *,
    reviewed: bool = False,
    character_id: str = CHARACTER_ID,
    width: int = WIDTH,
    height: int = HEIGHT,
    overrides: dict[str, Any] | None = None,
) -> Path:
    """Write `<character_dir>/background/` and return it.

    `missing` writes nothing (no `manifest.json`). `mismatch` writes a manifest whose `character_id` differs from the
    character's and drops the mask file of the last frame, so both a wrong owner and a missing frame can be tested.
    """
    background = character_dir / "background"
    if variant == "missing":
        return background
    (background / "masks").mkdir(parents=True, exist_ok=True)
    data = manifest(
        character_id=character_id if variant == "valid" else f"{character_id}_other",
        width=width,
        height=height,
        reviewed=reviewed,
    )
    data.update(overrides or {})
    for i, entry in enumerate(data["frames"]):
        if variant == "mismatch" and i == len(data["frames"]) - 1:
            continue
        ellipse_mask(width, height, shift_px=4 * i).save(background / entry["mask"])
    preview_frame(width, height).save(background / "preview_frame.png")
    (background / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return background
