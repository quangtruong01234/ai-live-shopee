"""Builds scene sets (009 contracts/scene-set.md) and product catalogs for tests, drawn on the fly: no real photo."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from ai_live.products.models import Product, ProductCatalog, Variant

CUSTOMER = "shop_test_01"


def product(
    pid: str,
    *,
    primary: bool = False,
    name: str | None = None,
    price: int | None = 159_000,
    variants: tuple[tuple[str, int], ...] = (),
    promotions: tuple[str, ...] = (),
) -> Product:
    return Product(
        id=pid,
        name=name or f"Sản phẩm {pid}",
        is_primary=primary,
        description="d",
        intro="i",
        price=None if variants else price,
        variants=tuple(Variant(n, p) for n, p in variants),
        promotions=promotions,
    )


def catalog(*products: Product, version: str = "v1") -> ProductCatalog:
    return ProductCatalog(version, "test.docx", datetime.now(UTC), tuple(products))


def demo_catalog(version: str = "v1") -> ProductCatalog:
    """One primary in the middle, two secondary, Vietnamese names and a price range."""
    return catalog(
        product("sua-rua-mat", name="Sữa rửa mặt Dịu Nhẹ", price=159_000),
        product(
            "kem-chong-nang",
            primary=True,
            name="Kem chống nắng Mây Sáng SPF 50",
            variants=(("50 ml", 250_000), ("100 ml", 420_000)),
            promotions=("Giảm 30.000đ cho đơn từ 500.000đ", "Tặng túi"),
        ),
        product("toner", name="Nước hoa hồng Ẩm Mượt", price=1_250_000),
        version=version,
    )


def product_png(path: Path, size: tuple[int, int] = (120, 240), color: tuple[int, int, int] = (200, 120, 90)) -> None:
    """A transparent picture with an opaque bottle shape in the middle."""
    image = Image.new("RGBA", (size[0] + 20, size[1] + 20), (0, 0, 0, 0))
    image.paste((*color, 255), (10, 10, 10 + size[0], 10 + size[1]))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def make_scene_dir(
    root: Path,
    product_ids: list[str],
    *,
    customer_id: str = CUSTOMER,
    scene: dict[str, Any] | None = None,
    records: dict[str, dict[str, Any]] | None = None,
    desk: bool = True,
) -> Path:
    """A complete, valid scene set: desk, one PNG with alpha and one original photo per product, provenance."""
    root.mkdir(parents=True, exist_ok=True)
    if desk:
        Image.new("RGB", (540, 210), (150, 100, 60)).save(root / "desk.png")
    provenance_products: dict[str, dict[str, Any]] = {}
    for pid in product_ids:
        product_png(root / "products" / f"{pid}.png")
        original = root / "originals" / f"{pid}.jpg"
        original.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (60, 80), (240, 240, 240)).save(original)
        provenance_products[pid] = {
            "original": f"originals/{pid}.jpg",
            "received_from": "khách",
            "received_at": "2026-11-01",
            "edits": ["remove_background", "crop"],
        }
    provenance_products.update(records or {})
    scene_json = {
        "schema_version": 1,
        "scene_id": root.name,
        "customer_id": customer_id,
        "layout": {"desk_top": 0.76, "max_slots": 5, "highlight_scale": 1.3, "show_promotion": True},
        **(scene or {}),
    }
    provenance = {
        "schema_version": 1,
        "customer_id": customer_id,
        "desk": {"source": "drawn", "license": "own"},
        "products": provenance_products,
    }
    (root / "scene.json").write_text(json.dumps(scene_json, ensure_ascii=False), encoding="utf-8")
    (root / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False), encoding="utf-8")
    return root


ImageKind = Literal[
    "png",
    "webp",
    "jpeg",
    "png_rgb",
    "jpeg_exif_rotated",
    "mpo",
    "gif_animated",
    "webp_animated",
    "png_transparent",
    "png_sparse",
    "png_truncated",
    "text",
    "png_too_wide",
    "too_large",
]


def _encode(image: Image.Image, fmt: str, **params: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **params)
    return buffer.getvalue()


def _bottle(size: tuple[int, int], color: tuple[int, int, int], alpha: bool) -> Image.Image:
    """An opaque block centred on a transparent (or white) canvas 20 px larger."""
    canvas = Image.new("RGBA" if alpha else "RGB", (size[0] + 20, size[1] + 20), (0, 0, 0, 0) if alpha else (255,) * 3)
    canvas.paste((*color, 255) if alpha else color, (10, 10, 10 + size[0], 10 + size[1]))
    return canvas


def image_bytes(
    kind: ImageKind = "png",
    size: tuple[int, int] = (120, 240),
    color: tuple[int, int, int] = (200, 120, 90),
) -> bytes:
    """Upload bodies for 012 tests, drawn with Pillow so no picture is committed (SC-004)."""
    if kind == "png":
        return _encode(_bottle(size, color, True), "PNG")
    if kind == "webp":
        return _encode(_bottle(size, color, True), "WEBP", lossless=True)
    if kind == "jpeg":
        return _encode(_bottle(size, color, False), "JPEG", quality=90)
    if kind == "png_rgb":
        return _encode(_bottle(size, color, False), "PNG")
    if kind == "jpeg_exif_rotated":
        # Stored landscape; orientation 6 means "rotate 90° clockwise to display", so it shows portrait.
        exif = Image.Exif()
        exif[0x0112] = 6
        return _encode(Image.new("RGB", (size[1], size[0]), color), "JPEG", exif=exif.tobytes())
    if kind == "mpo":
        first = Image.new("RGB", size, color)
        second = Image.new("RGB", size, (10, 10, 10))
        return _encode(first, "MPO", save_all=True, append_images=[second])
    if kind == "gif_animated":
        frames = [Image.new("RGB", size, c) for c in (color, (10, 200, 10))]
        return _encode(frames[0], "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    if kind == "webp_animated":
        frames = [Image.new("RGBA", size, (*color, 255)), Image.new("RGBA", size, (10, 10, 10, 255))]
        return _encode(frames[0], "WEBP", save_all=True, append_images=frames[1:], duration=100, loop=0)
    if kind == "png_transparent":
        return _encode(Image.new("RGBA", size, (0, 0, 0, 0)), "PNG")
    if kind == "png_sparse":
        # One visible 2×2 dot on 200×200: 0.01 % of the pixels, well under the 1 % "empty" threshold.
        image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        image.paste((*color, 255), (5, 5, 7, 7))
        return _encode(image, "PNG")
    if kind == "png_truncated":
        data = _encode(_bottle(size, color, True), "PNG")
        return data[: len(data) // 2]
    if kind == "text":
        return "Đây không phải ảnh\n".encode() * 20
    if kind == "png_too_wide":
        return _encode(Image.new("RGBA", (4100, 300), (*color, 255)), "PNG")
    if kind == "too_large":
        return _encode(Image.new("RGBA", (10, 10), (*color, 255)), "PNG") + b"\0" * (10 * 1024 * 1024 + 1)
    raise ValueError(kind)


def write_manifest(scene_dir: Path, data: dict[str, Any] | str) -> Path:
    """Hand-write `uploads/images.json` (a dict, or raw text for broken-file cases)."""
    path = scene_dir / "uploads" / "images.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path
