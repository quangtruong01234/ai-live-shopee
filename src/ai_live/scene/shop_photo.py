"""The `anh_shop` picture behind the host (014 data-model §3, FR-009, FR-009a, ADR-100).

`assets/scenes/<scene_id>/background/shop_photo.<png|jpg|webp>` plus `shop_photo.json` (sha256, who confirmed the
right to use it and when, and whether it is a real photo or AI-generated). Without a valid confirmation that matches
the file byte for byte the picture is never shown: an edited or swapped file needs a new confirmation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from ai_live.scene.models import MAX_IMAGE_BYTES, MAX_IMAGE_SIDE

PhotoSource = Literal["photo", "ai_generated"]
SOURCES: tuple[PhotoSource, ...] = ("photo", "ai_generated")
PHOTO_DIR = "background"
PHOTO_STEM = "shop_photo"
CONFIRMATION_NAME = "shop_photo.json"
SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
# FR-009a: an AI-made shop scene always has made-up labels and logos on its shelves; at this blur on the 480 px wide
# fork frame they are colour patches, not words. A scene may ask for more softness, never less.
AI_MIN_SOFTNESS_PX = 4.0


@dataclass(frozen=True, eq=False)
class ShopPhoto:
    """The confirmed picture (RGB), or why there is none (`no_shop_photo` / `shop_photo_unconfirmed`)."""

    image: Image.Image | None
    reason: str | None
    source: PhotoSource = "photo"
    path: Path | None = None
    confirmed_by: str | None = None
    confirmed_at: str | None = None
    sha256: str | None = None


class ShopPhotoError(ValueError):
    """The picture cannot be used as a shop photo (message in Vietnamese, for the operator)."""


def _photo_file(directory: Path) -> Path | None:
    for suffix in SUFFIXES:
        path = directory / f"{PHOTO_STEM}{suffix}"
        if path.is_file():
            return path
    return None


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _open(path: Path) -> Image.Image:
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ShopPhotoError(f"{path.name} nặng hơn 10 MB")
    try:
        with Image.open(path) as im:
            if max(im.size) > MAX_IMAGE_SIDE:
                raise ShopPhotoError(f"{path.name} {im.size[0]}×{im.size[1]} px, mỗi cạnh tối đa {MAX_IMAGE_SIDE} px")
            return im.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ShopPhotoError(f"{path.name} không phải ảnh đọc được: {exc}") from exc


def load_shop_photo(scene_root: Path) -> ShopPhoto:
    """The scene's shop photo; never raises, a problem becomes the fallback reason (FR-011)."""
    path = _photo_file(scene_root / PHOTO_DIR)
    if path is None:
        return ShopPhoto(None, "no_shop_photo")
    unconfirmed = ShopPhoto(None, "shop_photo_unconfirmed", path=path)
    try:
        record = json.loads((path.parent / CONFIRMATION_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return unconfirmed
    if not isinstance(record, dict):
        return unconfirmed
    by, at, sha, source = (record.get(k) for k in ("confirmed_by", "confirmed_at", "sha256", "source"))
    if not (isinstance(by, str) and by.strip() and isinstance(at, str) and at and isinstance(sha, str)):
        return unconfirmed
    if source not in SOURCES:
        return unconfirmed
    try:
        if _digest(path) != sha:
            return unconfirmed
        image = _open(path)
    except (OSError, ShopPhotoError):
        return unconfirmed
    return ShopPhoto(image, None, source, path, by.strip(), at, sha)


def save_shop_photo(scene_root: Path, src: Path, *, confirmed_by: str, source: PhotoSource) -> ShopPhoto:
    """Copy `src` in as the scene's shop photo with the operator's confirmation; replaces any previous one."""
    if not confirmed_by.strip():
        raise ShopPhotoError("cần tên người xác nhận quyền dùng ảnh")
    if source not in SOURCES:
        raise ShopPhotoError(f"nguồn ảnh {source!r} không hợp lệ")
    suffix = src.suffix.lower()
    if suffix not in SUFFIXES:
        raise ShopPhotoError(f"{src.name}: chỉ nhận PNG, JPG hoặc WebP")
    _open(src)  # reject before touching the scene
    directory = scene_root / PHOTO_DIR
    directory.mkdir(parents=True, exist_ok=True)
    for old in SUFFIXES:
        (directory / f"{PHOTO_STEM}{old}").unlink(missing_ok=True)
    dest = directory / f"{PHOTO_STEM}{'.jpg' if suffix == '.jpeg' else suffix}"
    shutil.copyfile(src, dest)
    record = {
        "sha256": _digest(dest),
        "confirmed_by": confirmed_by.strip(),
        "confirmed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": source,
        "original_name": src.name,
    }
    (directory / CONFIRMATION_NAME).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_shop_photo(scene_root)
