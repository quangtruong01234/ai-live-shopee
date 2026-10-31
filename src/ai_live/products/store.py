"""`ProductStore` backed by a Word file (contracts/adapters.md). Content can be replaced mid-session (FR-022)."""

from __future__ import annotations

from pathlib import Path

from ai_live.core.events import Event, EventBus, EventType
from ai_live.products.docx_loader import load_catalog
from ai_live.products.models import Product, ProductCatalog


class DocxProductStore:
    def __init__(self, catalog: ProductCatalog, max_bytes: int, bus: EventBus | None = None) -> None:
        self._catalog = catalog
        self._max_bytes = max_bytes
        self._bus = bus

    @classmethod
    def from_file(cls, path: Path, max_bytes: int, bus: EventBus | None = None) -> DocxProductStore:
        """Load at startup; a bad file lets `ContentLoadError` propagate so the app exits with the issue list."""
        return cls(load_catalog(path.read_bytes(), path.name, max_bytes), max_bytes, bus)

    @property
    def catalog(self) -> ProductCatalog:
        return self._catalog

    def list_active(self) -> list[Product]:
        return list(self._catalog.products)

    def get(self, product_id: str) -> Product | None:
        return next((p for p in self._catalog.products if p.id == product_id), None)

    def replace(self, data: bytes, source_name: str) -> ProductCatalog:
        catalog = self.parse(data, source_name)
        self.install(catalog)
        return catalog

    def parse(self, data: bytes, source_name: str) -> ProductCatalog:
        """Validate and parse without touching the current catalog.

        Thread-safe and CPU-bound, so the API runs it in a worker thread and then calls `install` on the event loop.
        """
        return load_catalog(data, source_name, self._max_bytes)

    def install(self, catalog: ProductCatalog) -> None:
        """Swap in an already validated catalog. Must run on the event loop: it publishes to the EventBus."""
        self._catalog = catalog
        if self._bus is not None:
            self._bus.publish(
                Event(
                    EventType.CONTENT_REPLACED,
                    {
                        "version": catalog.version,
                        "products": [
                            {"id": p.id, "name": p.name, "is_primary": p.is_primary} for p in catalog.products
                        ],
                    },
                )
            )
