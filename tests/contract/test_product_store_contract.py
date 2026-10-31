"""T116: `ProductStore` contract (contracts/adapters.md "Hành vi bắt buộc", `ProductStore.replace`; FR-022)."""

from __future__ import annotations

import pytest

from ai_live.core.events import EventBus, EventType
from ai_live.products.models import ContentLoadError


def _subset_of_catalog(store) -> None:
    catalog_products = list(store.catalog.products)
    active = store.list_active()
    assert all(p in catalog_products for p in active)
    for p in active:
        assert store.get(p.id) == p


def test_list_active_is_subset_of_catalog(product_store_harness):
    store = product_store_harness.make()
    assert store.list_active(), "a loaded store has at least one active product"
    _subset_of_catalog(store)

    store.replace(*product_store_harness.valid_replacement())
    _subset_of_catalog(store)


@pytest.mark.parametrize("product_id", ["", "khong-ton-tai", "0" * 32])
def test_get_unknown_id_returns_none(product_store_harness, product_id):
    store = product_store_harness.make()
    assert product_id not in {p.id for p in store.catalog.products}
    assert store.get(product_id) is None


def test_replace_valid_swaps_whole_catalog_and_publishes(product_store_harness):
    bus = EventBus()
    store = product_store_harness.make(bus)
    before = store.catalog
    sub = bus.subscribe()

    new = store.replace(*product_store_harness.valid_replacement())

    assert store.catalog == new
    assert new.version != before.version
    assert {p.id for p in store.list_active()} <= {p.id for p in new.products}
    assert not any(p in before.products for p in store.list_active())
    replaced = [e for e in sub.drain() if e.type == EventType.CONTENT_REPLACED]
    assert len(replaced) == 1
    assert replaced[0].payload["version"] == new.version


def test_replace_invalid_raises_and_keeps_catalog(store_and_invalid):
    factory, content = store_and_invalid
    harness = factory()
    bus = EventBus()
    store = harness.make(bus)
    before = store.catalog
    active_before = store.list_active()
    sub = bus.subscribe()

    with pytest.raises(ContentLoadError) as exc:
        store.replace(content.data, content.source_name)

    assert exc.value.issues, "ContentLoadError carries the list of issues for the editor"
    assert store.catalog is before
    assert store.list_active() == active_before
    for p in active_before:
        assert store.get(p.id) == p
    assert not [e for e in sub.drain() if e.type == EventType.CONTENT_REPLACED]
