"""Product content model (data-model.md §2). Immutable: new content means a new catalog, then swapping the reference."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
    link: str | None = None  # never read out loud

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
    """Carries every issue of the content file, so the writer fixes them in one go instead of one by one."""

    def __init__(self, issues: list[ContentIssue]) -> None:
        self.issues = issues
        super().__init__("\n".join(i.message for i in issues))


def product_detail(product: Product) -> dict[str, Any]:
    """The product as the content file has it, for the control page's detail panel (012 FR-022, data-model §8).

    Word for word, nothing rewritten, so the operator checks what the AI reads from. The link is left out: it is never
    read out loud, and the panel is about what the host may say.
    """
    return {
        "id": product.id,
        "name": product.name,
        "is_primary": product.is_primary,
        "description": product.description,
        "intro": product.intro,
        "price": product.price,
        "variants": [{"name": v.name, "price": v.price} for v in product.variants],
        "specs": [[k, v] for k, v in product.specs],
        "faq": [[q, a] for q, a in product.faq],
        "promotions": list(product.promotions),
        "forbidden_claims": list(product.forbidden_claims),
    }
