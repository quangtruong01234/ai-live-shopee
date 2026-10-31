"""Model nội dung sản phẩm (data-model.md §2). Bất biến: thay nội dung là tạo catalog mới rồi đổi tham chiếu."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Variant:
    name: str
    price: int


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    is_primary: bool
    description: str
    intro: str
    price: int | None = None
    variants: tuple[Variant, ...] = ()
    specs: tuple[tuple[str, str], ...] = ()
    faq: tuple[tuple[str, str], ...] = ()
    promotions: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    link: str | None = None  # không bao giờ được đọc lên

    def __post_init__(self) -> None:
        if (self.price is None) == (not self.variants):
            raise ValueError(f"Sản phẩm '{self.name}': cần đúng một trong giá hoặc bảng phân loại")

    @property
    def price_range(self) -> tuple[int, int]:
        prices = [v.price for v in self.variants] if self.variants else [self.price or 0]
        return min(prices), max(prices)


@dataclass(frozen=True)
class ProductCatalog:
    version: str
    source_name: str
    loaded_at: datetime
    products: tuple[Product, ...]
    known_amounts: frozenset[int] = field(default_factory=frozenset)

    @property
    def primary(self) -> Product:
        return next(p for p in self.products if p.is_primary)


@dataclass(frozen=True)
class ContentIssue:
    code: str
    message: str
    product: str | None = None
    section: str | None = None


class ContentLoadError(Exception):
    """Mang toàn bộ lỗi của file nội dung, để người soạn sửa một lần thay vì sửa từng lỗi."""

    def __init__(self, issues: list[ContentIssue]) -> None:
        self.issues = issues
        super().__init__("\n".join(i.message for i in issues))
