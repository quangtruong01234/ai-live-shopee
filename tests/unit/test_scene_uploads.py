"""Upload checks, ids and the image manifest (specs/012-product-image-upload research R2, R12; data-model §1–§2)."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from ai_live.scene import uploads
from ai_live.scene.uploads import (
    EMPTY_ALPHA_RATIO,
    UPLOAD_MAX_SIDE,
    ImageStoreError,
    ProductImageStore,
    UploadRejected,
    needs_bg_removal,
    validate_and_normalize,
    version_path,
)
from fixtures.scene_builder import CUSTOMER, image_bytes

pytestmark = pytest.mark.anyio


def _open(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png))


# --- T003: validation and normalization -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "code", "message"),
    [
        ("too_large", "too_large", "Ảnh quá lớn (tối đa 10 MB)"),
        ("png_truncated", "bad_image", "Không đọc được file ảnh (hỏng hoặc không phải ảnh)"),
        ("text", "bad_image", "Không đọc được file ảnh (hỏng hoặc không phải ảnh)"),
        ("gif_animated", "bad_format", "Chỉ nhận ảnh PNG, WebP hoặc JPEG"),
        ("png_too_wide", "too_big", "Ảnh quá to: cạnh dài 4100 điểm ảnh (tối đa 4000)"),
        ("webp_animated", "animated", "Không nhận ảnh động"),
        ("png_transparent", "empty", "Ảnh gần như trong suốt hoàn toàn, trên live sẽ không thấy gì"),
        ("png_sparse", "empty", "Ảnh gần như trong suốt hoàn toàn, trên live sẽ không thấy gì"),
    ],
)
def test_bad_files_are_rejected_with_the_contract_code_and_message(kind: str, code: str, message: str) -> None:
    with pytest.raises(UploadRejected) as caught:
        validate_and_normalize(image_bytes(kind))  # type: ignore[arg-type]
    assert caught.value.code == code
    assert caught.value.message == message


def test_http_status_follows_the_contract() -> None:
    statuses = {}
    for kind in ("too_large", "text", "gif_animated", "png_too_wide"):
        with pytest.raises(UploadRejected) as caught:
            validate_and_normalize(image_bytes(kind))  # type: ignore[arg-type]
        statuses[caught.value.code] = caught.value.status
    assert statuses == {"too_large": 413, "bad_image": 400, "bad_format": 415, "too_big": 400}


def test_size_is_checked_before_decoding() -> None:
    """A huge body that is also not an image reports `too_large`: the cheap check runs first (R2 order)."""
    with pytest.raises(UploadRejected) as caught:
        validate_and_normalize(b"x" * (10 * 1024 * 1024 + 1))
    assert caught.value.code == "too_large"


@pytest.mark.parametrize("kind", ["jpeg", "png_rgb"])
def test_images_without_alpha_become_solid_rgba(kind: str) -> None:
    result = validate_and_normalize(image_bytes(kind))  # type: ignore[arg-type]
    image = _open(result.png)
    assert image.format == "PNG"
    assert image.mode == "RGBA"
    assert result.has_alpha is False
    assert image.getchannel("A").getextrema() == (255, 255)


def test_transparent_png_keeps_alpha_and_is_cropped_to_it() -> None:
    result = validate_and_normalize(image_bytes("png", size=(120, 240)))
    assert result.has_alpha is True
    # The fixture draws a 120×240 block with a 10 px transparent margin; the margin is cropped away.
    assert (result.width, result.height) == (120, 240)
    assert _open(result.png).size == (120, 240)


def test_webp_is_accepted() -> None:
    assert validate_and_normalize(image_bytes("webp")).has_alpha is True


def test_exif_rotation_is_applied() -> None:
    """Phone photos store landscape pixels with an orientation tag; the result must stand upright."""
    result = validate_and_normalize(image_bytes("jpeg_exif_rotated", size=(120, 240)))
    assert (result.width, result.height) == (120, 240)


def test_mpo_uses_the_first_frame() -> None:
    result = validate_and_normalize(image_bytes("mpo", size=(100, 150), color=(200, 30, 30)))
    image = _open(result.png).convert("RGB")
    assert image.size == (100, 150)
    assert image.getpixel((50, 75)) == pytest.approx((200, 30, 30), abs=6)


def test_long_side_is_shrunk_to_the_upload_limit() -> None:
    result = validate_and_normalize(image_bytes("png", size=(600, 3000)))
    assert max(result.width, result.height) == UPLOAD_MAX_SIDE
    assert result.height == UPLOAD_MAX_SIDE
    assert result.width == round(600 * UPLOAD_MAX_SIDE / 3000)


def test_just_above_the_empty_threshold_is_accepted() -> None:
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    side = 11  # 121 px > 1 % of 10 000
    assert side * side / 10_000 > EMPTY_ALPHA_RATIO
    image.paste((10, 20, 30, 255), (0, 0, side, side))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    assert validate_and_normalize(buffer.getvalue()).width == side


def test_version_id_is_the_sha256_prefix_and_stable() -> None:
    first = validate_and_normalize(image_bytes("png"))
    second = validate_and_normalize(image_bytes("png"))
    assert first.version_id == hashlib.sha256(first.png).hexdigest()[:12]
    assert first.version_id == second.version_id
    assert validate_and_normalize(image_bytes("png", color=(1, 2, 3))).version_id != first.version_id


# --- T004: ids, paths and the manifest -------------------------------------------------------------------------


@pytest.mark.parametrize("pid", ["", "Kem", "kem_chong", "../x", "kem--a", "-kem", "kem-", "a" * 121, "kem/../a"])
def test_bad_product_ids_are_rejected_before_building_a_path(tmp_path: Path, pid: str) -> None:
    with pytest.raises(ImageStoreError) as caught:
        version_path(tmp_path / "uploads", pid, "0123456789ab")
    assert caught.value.code == "bad_id"
    assert caught.value.status == 400


@pytest.mark.parametrize("vid", ["", "0123456789AB", "0123456789a", "0123456789abc", "../../x.png", "kit"])
def test_bad_version_ids_are_rejected(tmp_path: Path, vid: str) -> None:
    with pytest.raises(ImageStoreError) as caught:
        version_path(tmp_path / "uploads", "kem-chong-nang", vid)
    assert caught.value.code == "bad_id"


def test_good_ids_stay_inside_uploads(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    path = version_path(root, "kem-chong-nang-spf50", "0123456789ab")
    assert path == root / "kem-chong-nang-spf50" / "0123456789ab.png"
    assert path.resolve().is_relative_to(root.resolve())


async def test_first_upload_creates_the_manifest(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    assert not (tmp_path / "uploads").exists()
    image = validate_and_normalize(image_bytes("png"))
    version, reused = await store.save_version("kem-chong-nang", image, "kem moi.png")
    assert reused is False
    assert version["source_name"] == "kem moi.png"
    assert version["has_alpha"] is True
    assert version["rights_confirmed_at"] is None
    assert version["applied_at"] is None
    file = tmp_path / "uploads" / "kem-chong-nang" / f"{image.version_id}.png"
    assert file.read_bytes() == image.png
    manifest = json.loads((tmp_path / "uploads" / "images.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["customer_id"] == CUSTOMER
    entry = manifest["products"]["kem-chong-nang"]
    assert entry["active"] == "kit"
    assert entry["history"] == []
    assert image.version_id in entry["versions"]


async def test_same_image_is_reused_not_duplicated(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    image = validate_and_normalize(image_bytes("png"))
    await store.save_version("toner", image, "a.png")
    _, reused = await store.save_version("toner", validate_and_normalize(image_bytes("png")), "b.png")
    assert reused is True
    assert len(list((tmp_path / "uploads" / "toner").iterdir())) == 1
    assert store.entry("toner")["versions"][image.version_id]["source_name"] == "a.png"  # type: ignore[index]


async def test_source_name_is_trimmed(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    version, _ = await store.save_version("toner", validate_and_normalize(image_bytes("png")), "x" * 500)
    assert len(version["source_name"]) == 200


async def test_manifest_survives_a_restart(tmp_path: Path) -> None:
    image = validate_and_normalize(image_bytes("png"))
    first = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    await first.save_version("toner", image, "a.png")
    await first.apply("toner", image.version_id, confirmed_at="2026-11-20T09:00:00.000Z")
    second = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    entry = second.entry("toner")
    assert entry is not None
    assert entry["active"] == image.version_id
    assert entry["history"] == ["kit"]
    assert entry["versions"][image.version_id]["rights_confirmed_at"]


async def test_failed_manifest_write_keeps_memory_and_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    image = validate_and_normalize(image_bytes("png"))
    await store.save_version("toner", image, "a.png")
    manifest = tmp_path / "uploads" / "images.json"
    before_disk = manifest.read_text(encoding="utf-8")
    before_entry = store.entry("toner")

    real_replace = os.replace

    def failing_replace(src: str | Path, dst: str | Path) -> None:
        if Path(dst).name == "images.json":
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(uploads.os, "replace", failing_replace)
    with pytest.raises(ImageStoreError) as caught:
        await store.apply("toner", image.version_id, confirmed_at="2026-11-20T09:00:00.000Z")
    assert caught.value.code == "save_failed"
    assert caught.value.status == 500
    assert "disk full" in caught.value.message
    assert caught.value.message.startswith("Không lưu được ảnh: ")
    assert store.entry("toner") == before_entry
    assert manifest.read_text(encoding="utf-8") == before_disk
    assert not [p for p in manifest.parent.iterdir() if p.name.endswith(".tmp")]


async def test_failed_upload_write_leaves_no_new_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    image = validate_and_normalize(image_bytes("png"))

    def failing_replace(src: str | Path, dst: str | Path) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(uploads.os, "replace", failing_replace)
    with pytest.raises(ImageStoreError) as caught:
        await store.save_version("toner", image, "a.png")
    assert caught.value.code == "save_failed"
    assert store.entry("toner") is None
    assert not (tmp_path / "uploads" / "toner" / f"{image.version_id}.png").exists()


async def test_store_refuses_another_customers_manifest(tmp_path: Path) -> None:
    other = ProductImageStore(tmp_path, customer_id="shop_khac")
    await other.save_version("toner", validate_and_normalize(image_bytes("png")), "a.png")
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    with pytest.raises(ImageStoreError) as caught:
        await store.save_version("toner", validate_and_normalize(image_bytes("webp")), "b.png")
    assert caught.value.code == "customer_mismatch"
    assert caught.value.status == 409


async def test_broken_manifest_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "images.json").write_text("{không phải json", encoding="utf-8")
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    with pytest.raises(ImageStoreError) as caught:
        await store.save_version("toner", validate_and_normalize(image_bytes("png")), "a.png")
    assert caught.value.code == "save_failed"
    assert (tmp_path / "uploads" / "images.json").read_text(encoding="utf-8") == "{không phải json"


# ---------- US1: apply (T013, data-model §2 "state transitions") ----------


def _ticking_clock() -> Callable[[], str]:
    ticks = iter(range(1, 1000))
    return lambda: f"2026-11-20T09:00:{next(ticks):02d}.000Z"


async def _two_versions(store: ProductImageStore) -> tuple[str, str]:
    a = validate_and_normalize(image_bytes("png"))
    b = validate_and_normalize(image_bytes("webp", size=(320, 480)))
    assert a.version_id != b.version_id
    await store.save_version("toner", a, "a.png")
    await store.save_version("toner", b, "b.webp")
    return a.version_id, b.version_id


async def test_apply_pushes_the_old_state_into_history(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    a, b = await _two_versions(store)
    entry = await store.apply("toner", a, confirmed_at="2026-11-20T08:59:00.000Z")
    assert entry["active"] == a
    assert entry["history"] == ["kit"]
    version = entry["versions"][a]
    assert version["rights_confirmed_at"] == "2026-11-20T08:59:00.000Z"
    assert version["applied_at"] == entry["updated_at"]

    entry = await store.apply("toner", b, confirmed_at="2026-11-20T09:01:00.000Z")
    assert entry["active"] == b
    assert entry["history"] == ["kit", a]
    assert store.active("toner") == b


async def test_reapplying_the_active_version_only_updates_times(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    a, _ = await _two_versions(store)
    first = await store.apply("toner", a, confirmed_at="2026-11-20T08:59:00.000Z")
    again = await store.apply("toner", a, confirmed_at="2026-11-20T09:05:00.000Z")
    assert again["history"] == first["history"] == ["kit"]
    assert again["updated_at"] > first["updated_at"]
    assert again["versions"][a]["applied_at"] > first["versions"][a]["applied_at"]
    assert again["versions"][a]["rights_confirmed_at"] == "2026-11-20T09:05:00.000Z"


async def test_history_keeps_the_last_twenty_states(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    a, b = await _two_versions(store)
    for i in range(30):
        await store.apply("toner", a if i % 2 == 0 else b, confirmed_at="2026-11-20T09:00:00.000Z")
    entry = store.entry("toner")
    assert entry is not None
    assert len(entry["history"]) == uploads.HISTORY_MAX


@pytest.mark.parametrize("pid", ["toner", "kem-chua-tai"])
async def test_applying_an_unknown_version_is_refused(tmp_path: Path, pid: str) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    await _two_versions(store)
    before = store.entries()
    with pytest.raises(ImageStoreError) as caught:
        await store.apply(pid, "0123456789ab", confirmed_at="2026-11-20T09:00:00.000Z")
    assert (caught.value.code, caught.value.status) == ("unknown_version", 404)
    assert store.entries() == before


# ---------- US2: several products in one write (T029, research R7) ----------


async def _versions_for(store: ProductImageStore, pids: list[str]) -> dict[str, str]:
    kinds = ["png", "webp", "jpeg"]
    out = {}
    for i, pid in enumerate(pids):
        image = validate_and_normalize(image_bytes(kinds[i % 3], size=(200 + 40 * i, 300)))
        await store.save_version(pid, image, f"{pid}.png")
        out[pid] = image.version_id
    return out


async def test_apply_many_writes_every_assignment_in_one_manifest_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    vids = await _versions_for(store, ["toner", "serum", "kem-moi"])
    writes: list[Path] = []
    real_replace = os.replace

    def counting_replace(src: str | Path, dst: str | Path) -> None:
        if Path(dst).name == "images.json":
            writes.append(Path(dst))
        real_replace(src, dst)

    monkeypatch.setattr(uploads.os, "replace", counting_replace)
    assignments = [uploads.Assignment(pid, vid, "2026-11-20T08:59:00.000Z") for pid, vid in vids.items()]
    entries = await store.apply_many(assignments)
    assert len(writes) == 1
    assert {pid: e["active"] for pid, e in entries.items()} == vids
    on_disk = json.loads((tmp_path / "uploads" / "images.json").read_text(encoding="utf-8"))
    assert {pid: on_disk["products"][pid]["active"] for pid in vids} == vids


async def test_apply_many_writes_nothing_when_the_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vids = await _versions_for(store, ["toner", "serum"])
    manifest = tmp_path / "uploads" / "images.json"
    before_disk = manifest.read_text(encoding="utf-8")
    before = store.entries()

    def failing_replace(src: str | Path, dst: str | Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(uploads.os, "replace", failing_replace)
    with pytest.raises(ImageStoreError) as caught:
        await store.apply_many([uploads.Assignment(p, v, "2026-11-20T09:00:00.000Z") for p, v in vids.items()])
    assert caught.value.code == "save_failed"
    assert store.entries() == before
    assert manifest.read_text(encoding="utf-8") == before_disk


async def test_apply_many_with_one_unknown_version_applies_none(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vids = await _versions_for(store, ["toner"])
    before = store.entries()
    with pytest.raises(ImageStoreError) as caught:
        await store.apply_many(
            [
                uploads.Assignment("toner", vids["toner"], "2026-11-20T09:00:00.000Z"),
                uploads.Assignment("serum", "0123456789ab", "2026-11-20T09:00:00.000Z"),
            ]
        )
    assert caught.value.code == "unknown_version"
    assert store.entries() == before


async def test_restore_puts_back_a_snapshot_on_disk_and_in_memory(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vids = await _versions_for(store, ["toner"])
    manifest = tmp_path / "uploads" / "images.json"
    snapshot = store.snapshot()
    before_disk = manifest.read_text(encoding="utf-8")
    await store.apply_many([uploads.Assignment("toner", vids["toner"], "2026-11-20T09:00:00.000Z")])
    assert store.active("toner") == vids["toner"]
    await store.restore(snapshot)
    assert store.active("toner") == "kit"
    assert json.loads(manifest.read_text(encoding="utf-8")) == json.loads(before_disk)
    assert ProductImageStore(tmp_path, customer_id=CUSTOMER).active("toner") == "kit"


async def test_restore_of_an_empty_snapshot_drops_the_manifest(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    snapshot = store.snapshot()
    assert snapshot is None
    image = validate_and_normalize(image_bytes("png"))
    await store.save_version("toner", image, "a.png")
    await store.restore(snapshot)
    assert store.entries() == {}
    assert not (tmp_path / "uploads" / "images.json").exists()


# ---------- US3: revert and remove (T055, data-model §2, FR-016, FR-017) ----------


async def test_revert_walks_back_through_history(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    a, b = await _two_versions(store)
    await store.apply("toner", a, confirmed_at="2026-11-20T08:59:00.000Z")
    applied_a = store.entry("toner")["versions"][a]["applied_at"]  # type: ignore[index]
    await store.apply("toner", b, confirmed_at="2026-11-20T08:59:30.000Z")

    entry = await store.revert("toner")
    assert entry["active"] == a
    assert entry["history"] == ["kit"]
    # Back on a version: it is live again from now on.
    assert entry["versions"][a]["applied_at"] > applied_a
    assert entry["updated_at"] == entry["versions"][a]["applied_at"]

    entry = await store.revert("toner")
    assert entry["active"] == "kit"
    assert entry["history"] == []
    assert store.active("toner") == "kit"

    with pytest.raises(ImageStoreError) as caught:
        await store.revert("toner")
    assert (caught.value.code, caught.value.status) == ("nothing_to_revert", 409)


async def test_revert_of_a_product_never_changed_has_nothing_to_go_back_to(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    with pytest.raises(ImageStoreError) as caught:
        await store.revert("toner")
    assert caught.value.code == "nothing_to_revert"
    assert not (tmp_path / "uploads" / "images.json").exists()


async def test_remove_pushes_the_active_state_and_revert_brings_it_back(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    a, _ = await _two_versions(store)
    await store.apply("toner", a, confirmed_at="2026-11-20T08:59:00.000Z")

    entry = await store.remove("toner")
    assert entry["active"] is None
    assert entry["history"] == ["kit", a]
    assert ProductImageStore(tmp_path, customer_id=CUSTOMER).active("toner") is None  # on disk

    with pytest.raises(ImageStoreError) as caught:
        await store.remove("toner")
    assert (caught.value.code, caught.value.status) == ("already_removed", 409)

    entry = await store.revert("toner")
    assert entry["active"] == a


async def test_removing_a_kit_image_records_the_kit_in_history(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    entry = await store.remove("kem")
    assert entry["active"] is None
    assert entry["history"] == ["kit"]
    assert (await store.revert("kem"))["active"] == "kit"


async def test_remove_and_revert_keep_history_at_twenty(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    a, _ = await _two_versions(store)
    for _ in range(15):
        await store.apply("toner", a, confirmed_at="2026-11-20T09:00:00.000Z")
        await store.remove("toner")
    entry = store.entry("toner")
    assert entry is not None
    assert len(entry["history"]) == uploads.HISTORY_MAX


async def test_revert_and_remove_refuse_a_bad_product_id(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    for call in (store.revert, store.remove):
        with pytest.raises(ImageStoreError):
            await call("../x")


# ---------- 013 T009: background-removal fields of a version (contracts/scene-set.md §3, data-model §8) ----------

_UPLOADED = "3f9a0c1b2d4e"
_CUTOUT = "a81c55d09e2f"
_BG = {
    "method": "flat",
    "result": "removed",
    "reason": None,
    "ms": 182.4,
    "model": None,
    "at": "2026-11-22T10:15:03+07:00",
}


def _old_version(**extra: object) -> dict[str, object]:
    return {
        "uploaded_at": "2026-11-20T09:00:00.000Z",
        "source_name": "thung coca.jpg",
        "width": 320,
        "height": 400,
        "has_alpha": False,
        "bytes": 1000,
        "applied_at": None,
        "rights_confirmed_at": None,
        **extra,
    }


def _write_manifest(scene_dir: Path, versions: dict[str, dict[str, object]], active: str | None = "kit") -> None:
    uploads_dir = scene_dir / "uploads"
    uploads_dir.mkdir(parents=True)
    data = {
        "schema_version": 1,
        "customer_id": CUSTOMER,
        "products": {"coca": {"active": active, "history": [], "updated_at": None, "versions": versions}},
    }
    (uploads_dir / "images.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_background_removal_fields_are_read(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        {
            _UPLOADED: _old_version(bg_removal=_BG, cutout_version=_CUTOUT),
            _CUTOUT: _old_version(bg_removal=_BG, derived_from=_UPLOADED, has_alpha=True),
        },
    )
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    assert store.broken is None
    uploaded = store.version("coca", _UPLOADED)
    cutout = store.version("coca", _CUTOUT)
    assert uploaded is not None and cutout is not None
    assert uploaded["bg_removal"] == _BG
    assert uploaded["cutout_version"] == _CUTOUT
    assert uploaded["derived_from"] is None
    assert cutout["derived_from"] == _UPLOADED
    assert cutout["cutout_version"] is None
    assert store.issues == ()


def test_012_version_without_the_new_fields_reads_as_none(tmp_path: Path) -> None:
    _write_manifest(tmp_path, {_UPLOADED: _old_version()})
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    version = store.version("coca", _UPLOADED)
    assert version is not None
    assert (version["bg_removal"], version["cutout_version"], version["derived_from"]) == (None, None, None)
    assert store.version("coca", _CUTOUT) is None
    assert store.version("other", _UPLOADED) is None


async def test_unknown_version_keys_are_ignored_and_kept(tmp_path: Path) -> None:
    _write_manifest(tmp_path, {_UPLOADED: _old_version(future_key={"x": 1})})
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    assert store.broken is None and store.issues == ()
    assert store.version("coca", _UPLOADED)["source_name"] == "thung coca.jpg"  # type: ignore[index]
    # A later write must not drop what a newer version of the app wrote.
    await store.save_version("toner", validate_and_normalize(image_bytes("png")), "a.png")
    manifest = json.loads((tmp_path / "uploads" / "images.json").read_text(encoding="utf-8"))
    assert manifest["products"]["coca"]["versions"][_UPLOADED]["future_key"] == {"x": 1}


@pytest.mark.parametrize("derived_from", ["000000000000", 42], ids=["missing_version", "not_a_string"])
def test_bad_derived_from_only_warns(tmp_path: Path, derived_from: object) -> None:
    _write_manifest(tmp_path, {_CUTOUT: _old_version(derived_from=derived_from, has_alpha=True)}, active=_CUTOUT)
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    assert store.broken is None
    assert [(i.level, i.product_id) for i in store.issues] == [("warning", "coca")]
    assert "derived_from" in store.issues[0].message
    assert store.active("coca") == _CUTOUT
    assert store.version("coca", _CUTOUT) is not None


# ---------- 013 T034: saving a background removal as a version (data-model §8–§9, research R9) ----------


def _cut(result: str, *, method: str = "flat", reason: str | None = None, image: Image.Image | None = None) -> object:
    """A `CutResult` stand-in: the store only reads its attributes."""
    if result == "removed" and image is None:
        image = Image.new("RGBA", (40, 60), (200, 60, 40, 255))
        image.putpixel((0, 0), (200, 60, 40, 0))
    metrics = {"fg_ratio": 0.5, "border_fg_ratio": 0.0, "uncertain_ratio": 0.01, "largest_component_ratio": 1.0}
    return SimpleNamespace(
        image=image,
        method=method,
        result=result,
        reason=reason,
        metrics=metrics,
        ms=12.5,
        model="isnet-general-use.onnx" if method == "model" else None,
    )


async def _uploaded(store: ProductImageStore, name: str = "thùng coca.jpg") -> str:
    image = validate_and_normalize(image_bytes("jpeg"))
    await store.save_version("coca", image, name)
    return image.version_id


async def test_removed_cut_becomes_a_new_version(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vid = await _uploaded(store)
    upload = await store.record_bg_removal("coca", vid, _cut("removed"))  # type: ignore[arg-type]
    cutout_vid = upload["cutout_version"]
    png = store.path("coca", cutout_vid).read_bytes()
    assert cutout_vid == hashlib.sha256(png).hexdigest()[:12]
    assert _open(png).mode == "RGBA" and _open(png).size == (40, 60)
    cutout = store.version("coca", cutout_vid)
    assert cutout is not None
    assert cutout["derived_from"] == vid
    assert cutout["cutout_version"] is None
    assert cutout["source_name"] == "thùng coca.jpg (đã bỏ nền)"
    assert cutout["has_alpha"] is True
    assert (cutout["width"], cutout["height"], cutout["bytes"]) == (40, 60, len(png))
    assert cutout["applied_at"] is None and cutout["rights_confirmed_at"] is None
    record = {"method": "flat", "result": "removed", "reason": None, "ms": 12.5, "model": None}
    assert {k: cutout["bg_removal"][k] for k in record} == record
    assert cutout["bg_removal"]["at"]
    assert store.version("coca", vid)["bg_removal"] == cutout["bg_removal"]  # type: ignore[index]
    assert store.version("coca", vid)["cutout_version"] == cutout_vid  # type: ignore[index]
    # Saved, never applied: the product still shows the kit picture.
    assert store.active("coca") == "kit"
    # It survives a restart.
    again = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    assert again.version("coca", cutout_vid)["derived_from"] == vid  # type: ignore[index]
    assert again.issues == ()


async def test_source_name_with_suffix_stays_within_the_limit(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vid = await _uploaded(store, "a" * 300)
    upload = await store.record_bg_removal("coca", vid, _cut("removed"))  # type: ignore[arg-type]
    assert len(store.version("coca", upload["cutout_version"])["source_name"]) <= 200  # type: ignore[index]


@pytest.mark.parametrize(
    ("result", "method", "reason"),
    [("failed", "model", "nền quá phức tạp, model không chắc"), ("kept", "already_transparent", None)],
)
async def test_failed_or_kept_only_records_the_result(
    tmp_path: Path, result: str, method: str, reason: str | None
) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vid = await _uploaded(store)
    upload = await store.record_bg_removal("coca", vid, _cut(result, method=method, reason=reason))  # type: ignore[arg-type]
    assert upload["cutout_version"] is None
    assert (upload["bg_removal"]["result"], upload["bg_removal"]["reason"]) == (result, reason)
    assert list(store.entry("coca")["versions"]) == [vid]  # type: ignore[index]


async def test_when_to_run_the_removal(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vid = await _uploaded(store)
    assert needs_bg_removal(store.version("coca", vid)) is True  # type: ignore[arg-type]
    upload = await store.record_bg_removal("coca", vid, _cut("removed"))  # type: ignore[arg-type]
    # Same picture again: the stored result is reused, not run again.
    assert needs_bg_removal(store.version("coca", vid)) is False  # type: ignore[arg-type]
    # A cut-out is never cut again.
    assert needs_bg_removal(store.version("coca", upload["cutout_version"])) is False  # type: ignore[arg-type]
    assert needs_bg_removal({"derived_from": vid, "bg_removal": None}) is False


@pytest.mark.parametrize(
    ("reason", "again"),
    [
        ("chưa cài model tách nền", True),
        ("đang live, bỏ nền phức tạp sau khi dừng show", True),
        ("nền quá phức tạp, model không chắc", False),
        ("tách nền quá lâu", False),
    ],
)
def test_a_failure_whose_cause_may_have_changed_runs_again(reason: str, again: bool) -> None:
    version = {"derived_from": None, "bg_removal": {"method": "flat", "result": "failed", "reason": reason}}
    assert needs_bg_removal(version) is again
    kept = {"derived_from": None, "bg_removal": {"method": "already_transparent", "result": "kept", "reason": None}}
    assert needs_bg_removal(kept) is False


async def test_rerun_after_a_failure_replaces_the_result(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vid = await _uploaded(store)
    await store.record_bg_removal("coca", vid, _cut("failed", reason="chưa cài model tách nền"))  # type: ignore[arg-type]
    upload = await store.record_bg_removal("coca", vid, _cut("removed", method="model"))  # type: ignore[arg-type]
    assert upload["bg_removal"]["result"] == "removed"
    assert upload["bg_removal"]["model"] == "isnet-general-use.onnx"
    assert upload["cutout_version"] is not None


async def test_the_cutout_does_not_inherit_the_rights_tick(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER, clock=_ticking_clock())
    vid = await _uploaded(store)
    await store.apply("coca", vid, "2026-11-22T10:00:00.000Z")
    upload = await store.record_bg_removal("coca", vid, _cut("removed"))  # type: ignore[arg-type]
    assert upload["rights_confirmed_at"] == "2026-11-22T10:00:00.000Z"
    cutout = store.version("coca", upload["cutout_version"])
    assert cutout is not None and cutout["rights_confirmed_at"] is None
    # Applying the cut-out is a normal 012 apply, and "Về ảnh trước" goes back to the upload.
    await store.apply("coca", upload["cutout_version"], "2026-11-22T10:05:00.000Z")
    assert store.active("coca") == upload["cutout_version"]
    await store.revert("coca")
    assert store.active("coca") == vid


async def test_recording_for_an_unknown_version_is_refused(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    with pytest.raises(ImageStoreError):
        await store.record_bg_removal("coca", "000000000000", _cut("removed"))  # type: ignore[arg-type]


async def test_removal_is_logged_with_its_metrics(tmp_path: Path) -> None:
    store = ProductImageStore(tmp_path, customer_id=CUSTOMER)
    vid = await _uploaded(store)
    got: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = got.append  # type: ignore[method-assign]
    logger = logging.getLogger("ai_live.scene")
    logger.addHandler(handler)
    saved = logger.level
    logger.setLevel(logging.INFO)
    try:
        upload = await store.record_bg_removal("coca", vid, _cut("removed"))  # type: ignore[arg-type]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(saved)
    records = [r for r in got if r.getMessage() == "scene_bg_removed"]
    assert len(records) == 1
    assert records[0].fields == {  # type: ignore[attr-defined]
        "product_id": "coca",
        "version_id": vid,
        "cutout_version": upload["cutout_version"],
        "method": "flat",
        "result": "removed",
        "reason": None,
        "ms": 12.5,
        "model": None,
        "width": 40,
        "height": 60,
        "fg_ratio": 0.5,
        "border_fg_ratio": 0.0,
        "uncertain_ratio": 0.01,
    }
