"""The staged set behind "Chuẩn bị bộ mới" (specs/012-product-image-upload, US2, data-model §6).

A new content file is read but not installed; the operator gives each product its picture, previews the whole set, then
applies catalog and images together. It lives in memory only (at most one): closing the app drops it, uploads stay.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from ai_live.app.errors import ApiError
from ai_live.products.models import Product, ProductCatalog
from ai_live.scene.uploads import KIT, Assignment, ProductImageStore

# Product states that count as "no image" when applying (FR-015 asks again before going live without one).
LACKING = frozenset({"removed", "missing"})


@dataclass(frozen=True)
class StagedAssignment:
    version_id: str
    rights_confirmed_at: str
    # Compared with the entry's `updated_at` on apply: a change made on the live set later wins (data-model §6).
    assigned_at: str


@dataclass
class StagedSet:
    staged_id: str
    catalog: ProductCatalog
    source_name: str
    created_at: str
    live_catalog_version: str
    assignments: dict[str, StagedAssignment] = field(default_factory=dict)
    # Products lacking an image as of the last `view()`, for `/api/state` (which must not touch the disk).
    missing_count: int = 0

    @classmethod
    def create(cls, catalog: ProductCatalog, source_name: str, live_catalog_version: str, *, now: str) -> StagedSet:
        return cls(uuid.uuid4().hex[:6], catalog, source_name, now, live_catalog_version)

    def check_id(self, staged_id: str) -> None:
        """Every change names the set it was made for, so a page left open never acts on a set replaced since."""
        if staged_id != self.staged_id:
            raise ApiError(409, "staging_changed", "Bộ chuẩn bị đã bị thay hoặc hủy, tải lại trang")

    def product(self, product_id: str) -> Product:
        found = next((p for p in self.catalog.products if p.id == product_id), None)
        if found is None:
            raise ApiError(404, "unknown_product", f"Không có sản phẩm {product_id} trong bộ chuẩn bị")
        return found

    def assign(
        self, store: ProductImageStore, product_id: str, version_id: str | None, *, rights_confirmed: Any, now: str
    ) -> None:
        """Give a staged product an uploaded version (None takes it back). Nothing on the live set changes."""
        self.product(product_id)
        if version_id is None:
            self.assignments.pop(product_id, None)
            return
        if rights_confirmed is not True:
            raise ApiError(422, "rights_not_confirmed", "Cần tick xác nhận quyền dùng ảnh trước khi gán")
        entry = store.entry(product_id) or {}
        if version_id not in (entry.get("versions") or {}):
            raise ApiError(404, "unknown_version", f"Không có phiên bản ảnh {version_id} của sản phẩm {product_id}")
        self.assignments[product_id] = StagedAssignment(version_id, now, now)

    def _wins(self, store: ProductImageStore, product_id: str) -> StagedAssignment | None:
        assignment = self.assignments.get(product_id)
        if assignment is None:
            return None
        updated_at = (store.entry(product_id) or {}).get("updated_at")
        # ISO stamps from one clock format compare as strings.
        return assignment if updated_at is None or assignment.assigned_at > updated_at else None

    def winning(self, store: ProductImageStore) -> list[Assignment]:
        """The assignments to write on apply, in catalog order."""
        out = []
        for p in self.catalog.products:
            won = self._wins(store, p.id)
            if won is not None:
                out.append(Assignment(p.id, won.version_id, won.rights_confirmed_at))
        return out

    def _image(self, store: ProductImageStore, product_id: str, kit_ids: Collection[str]) -> dict[str, Any]:
        won = self._wins(store, product_id)
        entry = store.entry(product_id)
        versions: dict[str, Any] = (entry or {}).get("versions") or {}
        if won is not None:
            version = versions.get(won.version_id) or {}
            return {
                "image": "staged",
                "version_id": won.version_id,
                "thumb_url": _version_url(product_id, won.version_id),
                "has_alpha": version.get("has_alpha"),
                "rights_confirmed_at": won.rights_confirmed_at,
            }
        active = KIT if entry is None else entry.get("active", KIT)
        if active is not None and active != KIT:
            return {"image": "reused_upload", "version_id": active, "thumb_url": _version_url(product_id, active)}
        if active == KIT and product_id in kit_ids:
            return {"image": "reused_kit", "version_id": None, "thumb_url": f"/api/scene/images/{product_id}/kit.png"}
        return {"image": "removed" if active is None else "missing", "version_id": None, "thumb_url": None}

    def missing_products(self, store: ProductImageStore, kit_ids: Collection[str]) -> list[Product]:
        return [p for p in self.catalog.products if self._image(store, p.id, kit_ids)["image"] in LACKING]

    def view(self, store: ProductImageStore, *, live_version: str, kit_ids: Collection[str]) -> dict[str, Any]:
        """`StagedSetView` (contracts/api.md §2); `kit_ids` = products with a usable kit file."""
        products = [
            {"product_id": p.id, "name": p.name, "is_primary": p.is_primary, **self._image(store, p.id, kit_ids)}
            for p in self.catalog.products
        ]
        missing = [p["product_id"] for p in products if p["image"] in LACKING]
        self.missing_count = len(missing)
        return {
            "staged_id": self.staged_id,
            "source_name": self.source_name,
            "created_at": self.created_at,
            "live_catalog_version": self.live_catalog_version,
            "live_changed": live_version != self.live_catalog_version,
            "products": products,
            "missing": missing,
        }


def _version_url(product_id: str, version_id: str) -> str:
    return f"/api/scene/images/{product_id}/versions/{version_id}.png"
