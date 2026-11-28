"""Product images uploaded from the control page (specs/012-product-image-upload).

Uploads live next to the 009 scene kit, in `SCENE_DIR/uploads/`: one normalized PNG per version and one manifest,
`images.json`, that says which version each product shows (contracts/scene-set.md). The scene loader reads the same
manifest from disk; this module is the only writer. Every write goes through a temp file and `os.replace`, so a crash
never leaves half a manifest, and a failed write leaves memory and disk as they were (FR-011).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import logging
import os
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageOps, UnidentifiedImageError

from ai_live.core.logging import log_event
from ai_live.scene.matting import RETRYABLE_REASONS
from ai_live.scene.models import MAX_IMAGE_BYTES, MAX_IMAGE_SIDE, SceneIssue

if TYPE_CHECKING:
    from ai_live.scene.matting import CutResult

logger = logging.getLogger("ai_live.scene")

PRODUCT_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PRODUCT_ID_MAX = 120
VERSION_ID_RE = re.compile(r"^[0-9a-f]{12}$")
UPLOADS_DIR = "uploads"
MANIFEST_NAME = "images.json"
SCHEMA_VERSION = 1
KIT = "kit"
# Big enough for a 1080-wide frame at any zoom the layout uses; bigger files only cost disk and load time.
UPLOAD_MAX_SIDE = 1280
# Below this share of visible pixels nothing shows on the desk (R2 step 7).
EMPTY_ALPHA_RATIO = 0.01
HISTORY_MAX = 20
SOURCE_NAME_MAX = 200
# Background-removal fields of a version (013 contracts/scene-set.md §3); a 012 version has none of them.
BG_FIELDS = ("bg_removal", "cutout_version", "derived_from")
_FORMATS = frozenset({"PNG", "WEBP", "JPEG", "MPO"})
CUTOUT_SUFFIX = " (đã bỏ nền)"

ImageState = str | None  # a version id, "kit", or None for "removed"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ImageStoreError(Exception):
    """A refused or failed image operation; `code` and `message` go to the page as an `ApiError`."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class UploadRejected(ImageStoreError):
    """The uploaded file is not an image the live scene can use (contracts/api.md §6)."""


def check_product_id(product_id: str) -> str:
    if not isinstance(product_id, str) or len(product_id) > PRODUCT_ID_MAX or not PRODUCT_ID_RE.match(product_id):
        raise ImageStoreError("bad_id", f"Mã sản phẩm không hợp lệ: {product_id!r}")
    return product_id


def check_version_id(version_id: str) -> str:
    if not isinstance(version_id, str) or not VERSION_ID_RE.match(version_id):
        raise ImageStoreError("bad_id", f"Mã phiên bản ảnh không hợp lệ: {version_id!r}")
    return version_id


def version_path(uploads_root: Path, product_id: str, version_id: str) -> Path:
    """`uploads/<pid>/<vid>.png`, built only from checked ids and never outside `uploads/` (research R12)."""
    path = uploads_root / check_product_id(product_id) / f"{check_version_id(version_id)}.png"
    if not path.resolve().is_relative_to(uploads_root.resolve()):
        raise ImageStoreError("bad_id", f"Mã sản phẩm không hợp lệ: {product_id!r}")
    return path


@dataclass(frozen=True)
class NormalizedImage:
    png: bytes
    width: int
    height: int
    has_alpha: bool  # the source had see-through pixels; False = still has its background (FR-004)
    version_id: str


def _reject(code: str, message: str, status: int = 400) -> UploadRejected:
    return UploadRejected(code, message, status)


_BAD_IMAGE = ("bad_image", "Không đọc được file ảnh (hỏng hoặc không phải ảnh)")


def validate_and_normalize(data: bytes) -> NormalizedImage:
    """Check an uploaded file in the order of research R2 and turn it into a cropped RGBA PNG.

    CPU work (decode, resample, encode): call it from a worker thread.
    """
    if len(data) > MAX_IMAGE_BYTES:
        raise _reject("too_large", "Ảnh quá lớn (tối đa 10 MB)", 413)
    try:
        source = Image.open(io.BytesIO(data))
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError) as exc:
        raise _reject(*_BAD_IMAGE) from exc
    with source:
        if source.format not in _FORMATS:
            raise _reject("bad_format", "Chỉ nhận ảnh PNG, WebP hoặc JPEG", 415)
        longest = max(source.size)
        if longest > MAX_IMAGE_SIDE:
            raise _reject("too_big", f"Ảnh quá to: cạnh dài {longest} điểm ảnh (tối đa 4000)")
        # An MPO is a phone photo with extra views (depth, preview): only the first is the picture.
        if getattr(source, "n_frames", 1) > 1 and source.format != "MPO":
            raise _reject("animated", "Không nhận ảnh động")
        try:
            source.seek(0)
            source.load()
            upright = ImageOps.exif_transpose(source)
            rgba = upright.convert("RGBA")
        except (OSError, ValueError, SyntaxError) as exc:
            raise _reject(*_BAD_IMAGE) from exc
    alpha = rgba.getchannel("A")
    visible = rgba.width * rgba.height - alpha.histogram()[0]
    if visible / (rgba.width * rgba.height) < EMPTY_ALPHA_RATIO:
        raise _reject("empty", "Ảnh gần như trong suốt hoàn toàn, trên live sẽ không thấy gì")
    has_alpha = alpha.getextrema()[0] < 255
    bbox = alpha.getbbox()
    if bbox is not None:
        rgba = rgba.crop(bbox)
    if max(rgba.size) > UPLOAD_MAX_SIDE:
        ratio = UPLOAD_MAX_SIDE / max(rgba.size)
        size = (max(1, round(rgba.width * ratio)), max(1, round(rgba.height * ratio)))
        rgba = rgba.resize(size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    rgba.save(buffer, "PNG")
    png = buffer.getvalue()
    return NormalizedImage(png, rgba.width, rgba.height, has_alpha, hashlib.sha256(png).hexdigest()[:12])


def needs_bg_removal(version: dict[str, Any]) -> bool:
    """Whether an upload should go through background removal (013 data-model §9).

    A cut-out is never cut again; a stored result is reused, except a failure whose cause may be gone by now (model
    installed later, show stopped).
    """
    if version.get("derived_from") is not None:
        return False
    record = version.get("bg_removal")
    if not isinstance(record, dict):
        return True
    return record.get("result") == "failed" and record.get("reason") in RETRYABLE_REASONS


def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _save_failed(exc: BaseException) -> ImageStoreError:
    return ImageStoreError("save_failed", f"Không lưu được ảnh: {exc}", 500)


@dataclass(frozen=True)
class Assignment:
    """One image to make active in a batch (`apply_many`, US2)."""

    product_id: str
    version_id: str
    confirmed_at: str


class ProductImageStore:
    """Owner of `uploads/`: saves versions and moves each product between kit, upload and removed.

    The manifest is read once at start; after that memory is the truth and each change is written whole before it
    counts. A manifest that cannot be read is never overwritten: every write is refused until someone fixes it by hand.
    """

    def __init__(self, scene_dir: Path, customer_id: str = "", *, clock: Callable[[], str] = now_iso) -> None:
        self.scene_dir = scene_dir
        self.root = scene_dir / UPLOADS_DIR
        self.manifest_path = self.root / MANIFEST_NAME
        self._customer_id = customer_id
        self._clock = clock
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] | None = None
        self._broken: str | None = None
        self._read()

    # ---------- reading ----------

    def _read(self) -> None:
        if not self.manifest_path.is_file():
            return
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._broken = str(exc)
            return
        if not isinstance(data, dict) or not isinstance(data.get("products"), dict):
            self._broken = "không phải sổ ảnh hợp lệ"
        elif data.get("schema_version") != SCHEMA_VERSION:
            self._broken = f"schema_version {data.get('schema_version')!r} chưa hỗ trợ"
        else:
            self._data = data

    @property
    def broken(self) -> str | None:
        """Why the manifest on disk cannot be used (None = fine or absent)."""
        return self._broken

    @property
    def customer_id(self) -> str | None:
        return self._data.get("customer_id") if self._data else None

    def entry(self, product_id: str) -> dict[str, Any] | None:
        """A copy of one product's entry, or None when the product follows the kit."""
        products = self._data["products"] if self._data else {}
        entry = products.get(product_id)
        return copy.deepcopy(entry) if isinstance(entry, dict) else None

    def entries(self) -> dict[str, dict[str, Any]]:
        products = self._data["products"] if self._data else {}
        return {pid: copy.deepcopy(e) for pid, e in products.items() if isinstance(e, dict)}

    def version(self, product_id: str, version_id: str) -> dict[str, Any] | None:
        """A copy of one version with the 013 fields always present (None when a 012 version lacks them)."""
        entry = self.entry(product_id)
        versions = entry.get("versions") if entry else None
        version = versions.get(version_id) if isinstance(versions, dict) else None
        if not isinstance(version, dict):
            return None
        return {**dict.fromkeys(BG_FIELDS), **version}

    @property
    def issues(self) -> tuple[SceneIssue, ...]:
        """Warnings about the manifest content; none of them stops the store from working."""
        found: list[SceneIssue] = []
        for product_id, entry in self.entries().items():
            versions = entry.get("versions")
            if not isinstance(versions, dict):
                continue
            for version_id, version in versions.items():
                derived = version.get("derived_from") if isinstance(version, dict) else None
                if derived is not None and (not isinstance(derived, str) or derived not in versions):
                    found.append(
                        SceneIssue.of(
                            "bad_derived_from",
                            f"Phiên bản ảnh {version_id}: derived_from = {derived!r} không trỏ tới phiên bản nào",
                            product_id,
                        )
                    )
        return tuple(found)

    def active(self, product_id: str) -> ImageState:
        entry = self.entry(product_id)
        return KIT if entry is None else entry.get("active", KIT)

    def path(self, product_id: str, version_id: str) -> Path:
        return version_path(self.root, product_id, version_id)

    # ---------- writing ----------

    def _writable(self) -> dict[str, Any]:
        """A deep copy to change; the copy replaces memory only after it is on disk."""
        if self._broken is not None:
            raise _save_failed(f"uploads/images.json hỏng ({self._broken}), sửa tay trước")
        owner = self.customer_id
        if owner and self._customer_id and owner != self._customer_id:
            raise ImageStoreError("customer_mismatch", "Bộ cảnh không thuộc khách của phiên này", 409)
        if self._data is None:
            return {"schema_version": SCHEMA_VERSION, "customer_id": self._customer_id, "products": {}}
        return copy.deepcopy(self._data)

    async def _commit(self, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            await asyncio.to_thread(_write_atomic, self.manifest_path, body)
        except OSError as exc:
            raise _save_failed(exc) from exc
        self._data = data

    @staticmethod
    def _entry_of(data: dict[str, Any], product_id: str) -> dict[str, Any]:
        fresh = {"active": KIT, "history": [], "updated_at": None, "versions": {}}
        return data["products"].setdefault(product_id, fresh)

    def _version_of(self, entry: dict[str, Any], product_id: str, version_id: str) -> dict[str, Any]:
        version = entry["versions"].get(version_id)
        if not isinstance(version, dict):
            raise ImageStoreError(
                "unknown_version", f"Không có phiên bản ảnh {version_id} của sản phẩm {product_id}", 404
            )
        return version

    def _activate(self, entry: dict[str, Any], state: ImageState, now: str) -> None:
        if entry["active"] != state:
            entry["history"].append(entry["active"])
            del entry["history"][:-HISTORY_MAX]
            entry["active"] = state
        entry["updated_at"] = now

    async def save_version(
        self, product_id: str, image: NormalizedImage, source_name: str
    ) -> tuple[dict[str, Any], bool]:
        """Store one upload without showing it; `(version, reused)` where `reused` = same picture as before."""
        check_product_id(product_id)
        path = self.path(product_id, image.version_id)
        async with self._lock:
            data = self._writable()
            existing = data["products"].get(product_id, {}).get("versions", {}).get(image.version_id)
            file_there = await asyncio.to_thread(path.is_file)
            if existing is not None and file_there:
                return copy.deepcopy(existing), True
            try:
                await asyncio.to_thread(_write_atomic, path, image.png)
            except OSError as exc:
                raise _save_failed(exc) from exc
            if existing is not None:
                return copy.deepcopy(existing), True
            version = {
                "uploaded_at": self._clock(),
                "source_name": source_name[:SOURCE_NAME_MAX],
                "width": image.width,
                "height": image.height,
                "has_alpha": image.has_alpha,
                "bytes": len(image.png),
                "applied_at": None,
                "rights_confirmed_at": None,
            }
            self._entry_of(data, product_id)["versions"][image.version_id] = version
            try:
                await self._commit(data)
            except ImageStoreError:
                await asyncio.to_thread(path.unlink, True)
                raise
            return copy.deepcopy(version), False

    async def record_bg_removal(self, product_id: str, version_id: str, cut: CutResult) -> dict[str, Any]:
        """Store the outcome of removing an upload's background (013 data-model §7–§9, contracts/api.md §5).

        `removed` adds the cut-out as a new version (`derived_from` the upload) that is saved but never applied, and
        never inherits the upload's rights tick: the operator confirms each version when applying it (FR-011, FR-017).
        Returns the upload's version, with `cutout_version` set when there is a cut-out.
        """
        check_product_id(product_id)
        check_version_id(version_id)
        png = await asyncio.to_thread(_encode_png, cut.image) if cut.result == "removed" and cut.image else None
        cutout_id = hashlib.sha256(png).hexdigest()[:12] if png is not None else None
        async with self._lock:
            data = self._writable()
            entry = data["products"].get(product_id)
            if not isinstance(entry, dict):
                raise ImageStoreError(
                    "unknown_version", f"Không có phiên bản ảnh {version_id} của sản phẩm {product_id}", 404
                )
            upload = self._version_of(entry, product_id, version_id)
            record = {
                "method": cut.method,
                "result": cut.result,
                "reason": cut.reason,
                "ms": round(cut.ms, 1),
                "model": cut.model,
                "at": self._clock(),
            }
            upload["bg_removal"] = record
            upload["cutout_version"] = None
            written: Path | None = None
            if png is not None and cutout_id is not None and cutout_id != version_id:
                path = self.path(product_id, cutout_id)
                if not await asyncio.to_thread(path.is_file):
                    try:
                        await asyncio.to_thread(_write_atomic, path, png)
                    except OSError as exc:
                        raise _save_failed(exc) from exc
                    written = path
                cutout = entry["versions"].get(cutout_id)
                if not isinstance(cutout, dict):
                    name = upload.get("source_name") or ""
                    cutout = {
                        "uploaded_at": record["at"],
                        "source_name": name[: SOURCE_NAME_MAX - len(CUTOUT_SUFFIX)] + CUTOUT_SUFFIX,
                        "width": cut.image.width,  # type: ignore[union-attr]
                        "height": cut.image.height,  # type: ignore[union-attr]
                        "has_alpha": True,
                        "bytes": len(png),
                        "applied_at": None,
                        "rights_confirmed_at": None,
                    }
                    entry["versions"][cutout_id] = cutout
                cutout.update(bg_removal=dict(record), cutout_version=None, derived_from=version_id)
                upload["cutout_version"] = cutout_id
            try:
                await self._commit(data)
            except ImageStoreError:
                if written is not None:
                    await asyncio.to_thread(written.unlink, True)
                raise
            size = cut.image.size if cut.image is not None else (upload.get("width"), upload.get("height"))
            log_event(
                logger,
                "scene_bg_removed",
                product_id=product_id,
                version_id=version_id,
                cutout_version=upload["cutout_version"],
                method=cut.method,
                result=cut.result,
                reason=cut.reason,
                ms=record["ms"],
                model=cut.model,
                width=size[0],
                height=size[1],
                **{key: cut.metrics.get(key) for key in ("fg_ratio", "border_fg_ratio", "uncertain_ratio")},
            )
            return {**dict.fromkeys(BG_FIELDS), **copy.deepcopy(upload)}

    async def apply(self, product_id: str, version_id: str, confirmed_at: str) -> dict[str, Any]:
        """Make an uploaded version the product's image; `confirmed_at` is when the operator ticked the rights box."""
        return (await self.apply_many([Assignment(product_id, version_id, confirmed_at)]))[product_id]

    async def apply_many(self, assignments: Iterable[Assignment]) -> dict[str, dict[str, Any]]:
        """Several products in one manifest write: all of them land, or none (US2)."""
        items = list(assignments)
        for item in items:
            check_product_id(item.product_id)
            check_version_id(item.version_id)
        async with self._lock:
            data = self._writable()
            now = self._clock()
            for item in items:
                entry = data["products"].get(item.product_id)
                if not isinstance(entry, dict):
                    raise ImageStoreError(
                        "unknown_version",
                        f"Không có phiên bản ảnh {item.version_id} của sản phẩm {item.product_id}",
                        404,
                    )
                version = self._version_of(entry, item.product_id, item.version_id)
                version["applied_at"] = now
                version["rights_confirmed_at"] = item.confirmed_at
                self._activate(entry, item.version_id, now)
            if items:
                await self._commit(data)
            return {item.product_id: copy.deepcopy(data["products"][item.product_id]) for item in items}

    async def revert(self, product_id: str) -> dict[str, Any]:
        """Go back one step: the last state in `history` becomes active again (US3, FR-016).

        The current state is not pushed, so pressing it again keeps walking back instead of toggling.
        """
        check_product_id(product_id)
        async with self._lock:
            data = self._writable()
            entry = data["products"].get(product_id)
            if not isinstance(entry, dict) or not entry.get("history"):
                raise ImageStoreError("nothing_to_revert", "Không có ảnh trước để quay về", 409)
            now = self._clock()
            state = entry["history"].pop()
            if state not in (KIT, None):
                # Back on a version: it is live again from now (the rights tick stays the one given at apply time).
                self._version_of(entry, product_id, state)["applied_at"] = now
            entry["active"] = state
            entry["updated_at"] = now
            await self._commit(data)
            return copy.deepcopy(entry)

    async def remove(self, product_id: str) -> dict[str, Any]:
        """Show no picture for this product; its card stays (US3, FR-017)."""
        check_product_id(product_id)
        async with self._lock:
            data = self._writable()
            entry = self._entry_of(data, product_id)
            if entry["active"] is None:
                raise ImageStoreError("already_removed", "Ảnh của món này đã gỡ rồi", 409)
            self._activate(entry, None, self._clock())
            await self._commit(data)
            return copy.deepcopy(entry)

    def snapshot(self) -> dict[str, Any] | None:
        """The manifest as it is now (None = no manifest yet), for `restore` when a later step fails."""
        return copy.deepcopy(self._data)

    async def restore(self, snapshot: dict[str, Any] | None) -> None:
        """Put back a `snapshot`: "Áp dụng bộ mới" undoes its manifest write when installing the catalog fails (R7).

        Version files stay: they are only ever added, and the manifest no longer points at the new ones.
        """
        async with self._lock:
            if snapshot is None:
                try:
                    await asyncio.to_thread(self.manifest_path.unlink, True)
                except OSError as exc:
                    raise _save_failed(exc) from exc
                self._data = None
                return
            await self._commit(copy.deepcopy(snapshot))
