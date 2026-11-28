"""Builds scene sets (009 contracts/scene-set.md) and product catalogs for tests, drawn on the fly: no real photo."""

from __future__ import annotations

import io
import json
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw

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


def product_color(pid: str) -> tuple[int, int, int]:
    """A stable, product-specific colour (never green-dominant: the 014 backdrop test reads green as stray)."""
    seed = zlib.crc32(pid.encode("utf-8"))
    return (90 + seed % 150, 40 + (seed >> 8) % 60, 60 + (seed >> 16) % 150)


def product_png(path: Path, size: tuple[int, int] = (200, 400), color: tuple[int, int, int] = (200, 120, 90)) -> None:
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
    distinct_colors: bool = False,
) -> Path:
    """A complete, valid scene set: desk, one PNG with alpha and one original photo per product, provenance.

    `distinct_colors` gives each product its own colour, so a picture that shows other products looks different (014).
    """
    root.mkdir(parents=True, exist_ok=True)
    if desk:
        Image.new("RGB", (540, 210), (150, 100, 60)).save(root / "desk.png")
    provenance_products: dict[str, dict[str, Any]] = {}
    for pid in product_ids:
        if distinct_colors:
            product_png(root / "products" / f"{pid}.png", color=product_color(pid))
        else:
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
    size: tuple[int, int] = (200, 400),
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


# ---------- 013: product photos for background removal (drawn on the fly, never committed) ----------

MattingKind = Literal[
    "white_bg",
    "flat_gray_bg",
    "flat_blue_bg",
    "white_inside",
    "white_on_white",
    "baked_shadow",
    "noisy_bg",
    "transparent",
    "very_wide",
    "very_tall",
]

PRODUCT_COLOR = (200, 60, 40)


def matting_image(kind: MattingKind, size: tuple[int, int] = (320, 400)) -> Image.Image:
    """A product photo for 013 background-removal tests; the product is a solid box in the middle.

    The box covers the centre third of the picture and never touches the border, so a correct flood fill from the
    border removes everything outside it and nothing inside it.
    """
    w, h = size
    if kind == "very_wide":
        w, h = 1000, 200
    elif kind == "very_tall":
        w, h = 150, 600
    box = (w // 4, h // 6, 3 * w // 4, 5 * h // 6)
    if kind == "transparent":
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        image.paste((*PRODUCT_COLOR, 255), box)
        return image
    background = {
        "flat_gray_bg": (128, 128, 128),
        "flat_blue_bg": (40, 90, 200),
    }.get(kind, (255, 255, 255))
    image = Image.new("RGB", (w, h), background)
    draw = ImageDraw.Draw(image)
    if kind == "noisy_bg":
        # Many-coloured stripes: no single border colour, so it is never "flat".
        for x in range(0, w, 8):
            draw.rectangle((x, 0, x + 7, h), fill=((x * 37) % 256, (x * 91) % 256, (x * 53) % 256))
    if kind == "white_on_white":
        # An off-white box with a thin grey outline: hard, but the outline keeps it separable from the border.
        draw.rectangle(box, fill=(246, 246, 246), outline=(150, 150, 150), width=3)
        return image
    if kind == "baked_shadow":
        x1, y1, x2, y2 = box
        draw.ellipse((x1 - 10, y2 - 12, x2 + 10, y2 + 14), fill=(190, 190, 190))
    draw.rectangle(box, fill=PRODUCT_COLOR)
    if kind == "white_inside":
        # A white label inside the box, same colour as the background but not connected to the border (US2 #4).
        x1, y1, x2, y2 = box
        draw.rectangle((x1 + 15, y1 + 20, x2 - 15, y1 + 20 + (y2 - y1) // 3), fill=(255, 255, 255))
        draw.text((x1 + 22, y1 + 28), "LABEL", fill=(20, 20, 20))
    return image


def matting_box(kind: MattingKind, size: tuple[int, int] = (320, 400)) -> tuple[int, int, int, int]:
    """The product box `matting_image` draws, to check what a cut kept."""
    w, h = size
    if kind == "very_wide":
        w, h = 1000, 200
    elif kind == "very_tall":
        w, h = 150, 600
    return (w // 4, h // 6, 3 * w // 4, 5 * h // 6)


def matting_bytes(kind: MattingKind, size: tuple[int, int] = (320, 400), fmt: str = "PNG") -> bytes:
    return _encode(matting_image(kind, size), fmt)
