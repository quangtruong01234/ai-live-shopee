"""Builds scene sets (009 contracts/scene-set.md) and product catalogs for tests, drawn on the fly: no real photo."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
