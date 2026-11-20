"""The staged set behind "Chuẩn bị bộ mới" (specs/012-product-image-upload, US2, data-model §6, FR-013–FR-015)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_live.app.errors import ApiError
from ai_live.app.staging import StagedSet
from ai_live.scene.uploads import Assignment, ProductImageStore, validate_and_normalize
from fixtures.scene_builder import CUSTOMER, catalog, image_bytes, product, write_manifest

pytestmark = pytest.mark.anyio

T0 = "2026-11-20T09:00:00.000Z"
T1 = "2026-11-20T09:05:00.000Z"
T2 = "2026-11-20T09:10:00.000Z"


class Clock:
    def __init__(self, now: str = T0) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> ProductImageStore:
    return ProductImageStore(tmp_path / "scene", CUSTOMER, clock=clock)


def _staged(*pids: str, live_version: str = "live1") -> StagedSet:
    products = [product(pid, primary=i == 0, name=f"Món {pid}") for i, pid in enumerate(pids)]
    return StagedSet.create(catalog(*products, version="new1"), "bo-moi.docx", live_version, now=T0)


async def _upload(store: ProductImageStore, pid: str, color=(10, 200, 30)) -> str:
    image = validate_and_normalize(image_bytes("png", size=(200, 300), color=color))
    await store.save_version(pid, image, "a.png")
    return image.version_id


def _by_id(view: dict) -> dict[str, dict]:
    return {p["product_id"]: p for p in view["products"]}


async def test_image_state_follows_the_priority_order(store: ProductImageStore, clock: Clock) -> None:
    staged = _staged("moi", "da-tai", "co-kit", "da-go", "trong")
    vid_old = await _upload(store, "da-tai")
    await store.apply("da-tai", vid_old, T0)
    vid_new = await _upload(store, "moi", color=(200, 30, 30))
    # "da-go" was removed by hand in an earlier session: the manifest says so.
    data = store.snapshot()
    assert data is not None
    data["products"]["da-go"] = {"active": None, "history": ["kit"], "updated_at": T0, "versions": {}}
    write_manifest(store.scene_dir, data)
    store = ProductImageStore(store.scene_dir, CUSTOMER, clock=clock)
    staged.assign(store, "moi", vid_new, rights_confirmed=True, now=T1)

    view = staged.view(store, live_version="live1", kit_ids={"co-kit", "da-go"})
    products = _by_id(view)
    assert {pid: p["image"] for pid, p in products.items()} == {
        "moi": "staged",
        "da-tai": "reused_upload",
        "co-kit": "reused_kit",
        "da-go": "removed",
        "trong": "missing",
    }
    assert products["moi"]["version_id"] == vid_new
    assert products["moi"]["rights_confirmed_at"] == T1
    assert products["moi"]["has_alpha"] is True
    assert products["moi"]["thumb_url"] == f"/api/scene/images/moi/versions/{vid_new}.png"
    assert products["da-tai"]["version_id"] == vid_old
    assert products["da-tai"]["thumb_url"] == f"/api/scene/images/da-tai/versions/{vid_old}.png"
    assert products["co-kit"]["thumb_url"] == "/api/scene/images/co-kit/kit.png"
    assert products["trong"]["thumb_url"] is None and products["trong"]["version_id"] is None
    # FR-015: both "removed" and "missing" count as lacking an image.
    assert view["missing"] == ["da-go", "trong"]
    assert [p.name for p in staged.missing_products(store, {"co-kit", "da-go"})] == ["Món da-go", "Món trong"]
    assert products["moi"]["is_primary"] is True and products["moi"]["name"] == "Món moi"


async def test_a_product_not_on_the_live_catalog_reuses_its_old_upload(store: ProductImageStore) -> None:
    # FR-014: images are kept per product id, so a product coming back after another file brings its picture.
    vid = await _upload(store, "quay-lai")
    await store.apply("quay-lai", vid, T0)
    view = _staged("quay-lai").view(store, live_version="live1", kit_ids=set())
    assert _by_id(view)["quay-lai"]["image"] == "reused_upload"
    assert view["missing"] == []


async def test_assigning_needs_the_rights_box(store: ProductImageStore) -> None:
    staged = _staged("moi")
    vid = await _upload(store, "moi")
    with pytest.raises(ApiError) as caught:
        staged.assign(store, "moi", vid, rights_confirmed=False, now=T1)
    assert (caught.value.status, caught.value.error) == (422, "rights_not_confirmed")
    assert staged.assignments == {}


async def test_assigning_checks_product_and_version(store: ProductImageStore) -> None:
    staged = _staged("moi")
    vid = await _upload(store, "khac")
    with pytest.raises(ApiError) as caught:
        staged.assign(store, "khac", vid, rights_confirmed=True, now=T1)
    assert (caught.value.status, caught.value.error) == (404, "unknown_product")
    with pytest.raises(ApiError) as caught:
        staged.assign(store, "moi", vid, rights_confirmed=True, now=T1)
    assert (caught.value.status, caught.value.error) == (404, "unknown_version")
    with pytest.raises(ApiError) as caught:
        staged.product("khac")
    assert caught.value.error == "unknown_product"


async def test_unassigning_needs_no_rights_box(store: ProductImageStore) -> None:
    staged = _staged("moi")
    vid = await _upload(store, "moi")
    staged.assign(store, "moi", vid, rights_confirmed=True, now=T1)
    staged.assign(store, "moi", None, rights_confirmed=False, now=T2)
    assert staged.assignments == {}
    assert _by_id(staged.view(store, live_version="live1", kit_ids=set()))["moi"]["image"] == "missing"


def test_a_stale_staged_id_is_refused() -> None:
    staged = _staged("moi")
    staged.check_id(staged.staged_id)
    with pytest.raises(ApiError) as caught:
        staged.check_id("khac00")
    assert (caught.value.status, caught.value.error) == (409, "staging_changed")


def test_ids_are_short_and_fresh_and_the_view_names_the_file() -> None:
    first, second = _staged("moi"), _staged("moi")
    assert len(first.staged_id) == 6 and first.staged_id != second.staged_id
    assert first.created_at == T0


async def test_live_changed_compares_the_live_catalog_version(store: ProductImageStore) -> None:
    staged = _staged("moi", live_version="live1")
    view = staged.view(store, live_version="live1", kit_ids=set())
    assert view["live_changed"] is False
    assert view["live_catalog_version"] == "live1" and view["source_name"] == "bo-moi.docx"
    assert staged.view(store, live_version="live2", kit_ids=set())["live_changed"] is True


async def test_an_assignment_wins_only_when_newer_than_the_live_change(store: ProductImageStore, clock: Clock) -> None:
    staged = _staged("a", "b")
    vid_a = await _upload(store, "a")
    vid_b = await _upload(store, "b")
    vid_b_live = await _upload(store, "b", color=(30, 30, 200))
    staged.assign(store, "a", vid_a, rights_confirmed=True, now=T1)
    staged.assign(store, "b", vid_b, rights_confirmed=True, now=T1)
    # Someone applied another picture of "b" on the live set after it was staged: that newer choice stays.
    clock.now = T2
    await store.apply("b", vid_b_live, T2)

    assert staged.winning(store) == [Assignment("a", vid_a, T1)]
    products = _by_id(staged.view(store, live_version="live1", kit_ids=set()))
    assert (products["a"]["image"], products["a"]["version_id"]) == ("staged", vid_a)
    assert (products["b"]["image"], products["b"]["version_id"]) == ("reused_upload", vid_b_live)


async def test_an_assignment_beats_an_older_live_change(store: ProductImageStore, clock: Clock) -> None:
    staged = _staged("a")
    vid_old = await _upload(store, "a")
    await store.apply("a", vid_old, T0)
    vid_new = await _upload(store, "a", color=(1, 2, 3))
    staged.assign(store, "a", vid_new, rights_confirmed=True, now=T1)
    assert staged.winning(store) == [Assignment("a", vid_new, T1)]
