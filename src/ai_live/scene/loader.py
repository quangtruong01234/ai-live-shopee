"""Load a scene set from `SCENE_DIR` (contracts/scene-set.md).

Loading never raises: a live session must not stop because of a scene file (FR-003, FR-021). Every problem becomes a
`SceneIssue`, and the scene draws whatever is usable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from ai_live.core.logging import log_event
from ai_live.scene.limits import ART_MAX_SIDE
from ai_live.scene.merchandise import with_stock
from ai_live.scene.models import (
    ALLOWED_EDITS,
    DEFAULT_ACCENT_COLOR,
    DEFAULT_DESK_COLOR,
    DESK_SOURCES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_SIDE,
    BackgroundConfig,
    LayoutParams,
    ProductArt,
    Provenance,
    ProvenanceRecord,
    SceneIssue,
    SceneSet,
)
from ai_live.scene.shop_photo import load_shop_photo
from ai_live.scene.uploads import (
    KIT,
    MANIFEST_NAME,
    PRODUCT_ID_MAX,
    PRODUCT_ID_RE,
    SCHEMA_VERSION,
    UPLOADS_DIR,
    VERSION_ID_RE,
    version_path,
)

DESK_MAX_WIDTH = 1080
_PRODUCT_SUFFIXES = (".png", ".webp")
_IMAGE_SUFFIXES = (".png", ".webp", ".jpg", ".jpeg")
_SCENE_KEYS = frozenset(
    {
        "schema_version",
        "scene_id",
        "customer_id",
        "desk",
        "desk_color",
        "accent_color",
        "products_dir",
        "provenance",
        "layout",
        "background",
    }
)
# Values outside these are refused (009 rule: `bad_scene_json`, then the default).
_LAYOUT_LIMITS: dict[str, tuple[float, float]] = {
    "desk_top": (0.55, 0.92),
    "max_slots": (1, 7),
}
# Values outside these are clamped with `layout_clamped` (013 data-model §1).
_HIGHLIGHT_RANGE: dict[str, tuple[float, float]] = {
    "rows": (1.0, 1.6),
    "realistic": (1.0, 1.1),
    "showcase": (1.0, 1.1),
}
_HIGHLIGHT_DEFAULT = {"rows": 1.3, "realistic": 1.08, "showcase": 1.08}
_BRIGHTNESS_RANGE = (0.85, 1.1)
# The most products each desk layout places; `rows` keeps the 009 limit of `_LAYOUT_LIMITS`.
_MODE_MAX_SLOTS = {"realistic": 5, "showcase": 4}
_MODES = ("rows", "realistic", "showcase")
_CARDS = ("none", "one", "all")
# 013 FR-026, FR-027; 014 ADR-087; 013 FR-030 to FR-032 (ADR-095)
_FLAGS = ("riser", "sticker", "avoid_app_overlay", "stock", "price_tags", "promo_banner")
# 014 data-model §1: background block styles and number ranges (clamped with `background_clamped`).
_BACKGROUND_STYLES = ("goc", "ke_hang", "bang_shop", "anh_shop")
_BACKGROUND_RANGES: dict[str, tuple[float, float]] = {
    "softness_px": (0.0, 8.0),
    "brightness": (0.8, 1.1),
    "max_items": (1, 24),
}
_logger = logging.getLogger("ai_live.scene")
_KNOWN_LAYOUT_KEYS = {*_LAYOUT_LIMITS, *_FLAGS, "highlight_scale", "show_promotion", "mode", "cards", "brightness"}


class _Issues:
    def __init__(self) -> None:
        self.items: list[SceneIssue] = []

    def add(self, code: str, message: str, product_id: str | None = None) -> None:
        self.items.append(SceneIssue.of(code, message, product_id))


def _inside(root: Path, rel: Any, issues: _Issues, what: str) -> Path | None:
    """`root / rel` when it stays inside the scene folder; a path that escapes it is refused."""
    if not isinstance(rel, str) or not rel.strip():
        issues.add("bad_scene_json", f"{what}: cần một đường dẫn dạng chuỗi")
        return None
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        issues.add("bad_scene_json", f"{what} '{rel}' nằm ngoài thư mục cảnh")
        return None
    return path


def _color(value: Any, default: tuple[int, int, int], key: str, issues: _Issues) -> tuple[int, int, int]:
    if value is None:
        return default
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
        except ValueError:
            pass
    issues.add("bad_scene_json", f"scene.json: {key} '{value}' không phải màu #RRGGBB, dùng màu mặc định")
    return default


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _clamped(key: str, value: Any, low: float, high: float, default: float, issues: _Issues) -> float:
    """A number kept inside [low, high]: out of range is clamped and warned, not a number falls back to the default."""
    if not _is_number(value):
        issues.add("bad_scene_json", f"scene.json: layout.{key} = {value!r} không phải số, dùng {default}")
        return default
    used = min(max(float(value), low), high)
    if used != value:
        issues.add("layout_clamped", f"layout.{key} ngoài giới hạn, đã dùng {used:g}")
    return used


def _background(raw: Any, issues: _Issues) -> BackgroundConfig:
    """The optional `background` block; anything unusable keeps the original room (`goc`) so old scenes never change."""
    default = BackgroundConfig()
    if raw is None:
        return default
    if not isinstance(raw, dict):
        issues.add("bad_scene_json", "scene.json: background phải là object, dùng phòng gốc")
        return default
    style = raw.get("style", default.style)
    if style not in _BACKGROUND_STYLES:
        issues.add("bad_scene_json", f"scene.json: background.style {style!r} không hỗ trợ, dùng phòng gốc")
        style = default.style
    values: dict[str, float] = {}
    for key, (low, high) in _BACKGROUND_RANGES.items():
        fallback = getattr(default, key)
        value = raw.get(key, fallback)
        if not _is_number(value):
            issues.add("bad_scene_json", f"scene.json: background.{key} = {value!r} không phải số, dùng {fallback}")
            values[key] = fallback
            continue
        used = min(max(float(value), low), high)
        if key == "max_items":
            used = int(used)
        if used != value:
            issues.add("background_clamped", f"background.{key} ngoài giới hạn, đã dùng {used:g}")
            log_event(_logger, "background_clamped", field=key, value=value, clamped_to=used)
        values[key] = used
    as_is = raw.get("as_is", default.as_is)
    if not isinstance(as_is, bool):
        issues.add("bad_scene_json", f"scene.json: background.as_is = {as_is!r} không phải true/false, dùng false")
        as_is = default.as_is
    if as_is and style == "anh_shop":
        issues.add(
            "background_as_is",
            "Ảnh nền giữ nguyên, không làm mờ, không chỉnh sáng: chỉ cho demo qua OBS (ADR-102), không dùng cho Shopee",
        )
        log_event(_logger, "background_as_is", style=style)
    for key in sorted(set(raw) - {"style", "as_is", *_BACKGROUND_RANGES}):
        issues.add("background_unknown_key", f"scene.json: bỏ qua khóa lạ background.{key}")
        log_event(_logger, "background_unknown_key", key=key)
    return BackgroundConfig(
        style=style,
        softness_px=values["softness_px"],
        brightness=values["brightness"],
        max_items=int(values["max_items"]),
        as_is=as_is,
    )


def _layout(raw: Any, issues: _Issues) -> LayoutParams:
    default = LayoutParams()
    if raw is None:
        return default
    if not isinstance(raw, dict):
        issues.add("bad_scene_json", "scene.json: layout phải là object, dùng bố cục mặc định")
        return default
    values: dict[str, Any] = {}
    mode = raw.get("mode", "rows")
    if mode not in _MODES:
        # Still drawable: the scene falls back to the 009 rows (data-model §1).
        issues.add(
            "bad_layout", f"scene.json: layout.mode = {mode!r} không hợp lệ (rows | realistic | showcase), dùng rows"
        )
        mode = "rows"
    values["mode"] = mode
    for key, (low, high) in _LAYOUT_LIMITS.items():
        if key not in raw:
            continue
        value = raw[key]
        ok = _is_number(value) and low <= value <= high
        if key == "max_slots":
            ok = ok and float(value).is_integer()
        if ok:
            values[key] = int(value) if key == "max_slots" else float(value)
        else:
            default_value = getattr(default, key)
            issues.add(
                "bad_scene_json", f"scene.json: layout.{key} = {value!r} ngoài [{low}, {high}], dùng {default_value}"
            )
    mode_max = _MODE_MAX_SLOTS.get(mode)
    if mode_max is not None and values.get("max_slots", default.max_slots) > mode_max:
        values["max_slots"] = mode_max
        # Only a value the file wrote is worth a warning; the default 5 is simply the most the mode places.
        if "max_slots" in raw:
            issues.add("layout_clamped", f"layout.max_slots ngoài giới hạn, đã dùng {mode_max}")
    highlight_default = _HIGHLIGHT_DEFAULT[mode]
    values["highlight_scale"] = (
        _clamped("highlight_scale", raw["highlight_scale"], *_HIGHLIGHT_RANGE[mode], highlight_default, issues)
        if "highlight_scale" in raw
        else highlight_default
    )
    if "brightness" in raw:
        values["brightness"] = _clamped("brightness", raw["brightness"], *_BRIGHTNESS_RANGE, default.brightness, issues)
    values["cards"] = _cards(raw, mode, issues)
    if "show_promotion" in raw:
        if isinstance(raw["show_promotion"], bool):
            values["show_promotion"] = raw["show_promotion"]
        else:
            issues.add("bad_scene_json", "scene.json: layout.show_promotion phải là true/false")
    for key in _FLAGS:
        if key not in raw:
            continue
        if isinstance(raw[key], bool):
            values[key] = raw[key]
        else:
            issues.add("layout_clamped", f"scene.json: layout.{key} phải là true/false, dùng false")
    for key in sorted(set(raw) - _KNOWN_LAYOUT_KEYS):
        issues.add("unknown_key", f"scene.json: bỏ qua khóa lạ layout.{key}")
    return LayoutParams(**{**default.__dict__, **values})


def _cards(raw: dict[str, Any], mode: str, issues: _Issues) -> str:
    mode_default = "none" if mode in ("realistic", "showcase") else "all"
    if "cards" not in raw:
        return mode_default
    cards = raw["cards"]
    if cards not in _CARDS:
        issues.add(
            "bad_layout", f"scene.json: layout.cards = {cards!r} không hợp lệ (none | one | all), dùng {mode_default}"
        )
        return mode_default
    if mode == "rows" and cards != "all":
        issues.add("cards_ignored", "Cách bày hàng luôn có thẻ; bỏ qua layout.cards")
        return "all"
    return str(cards)


def _read_json(path: Path, issues: _Issues, code: str) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        issues.add(code, f"{path.name} không đọc được: {exc}")
        return None
    if not isinstance(data, dict):
        issues.add(code, f"{path.name} phải là một object JSON")
        return None
    return data


def _open_image(path: Path, issues: _Issues, product_id: str | None) -> Image.Image | None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        issues.add("bad_image", f"{path.name} không đọc được: {exc}", product_id)
        return None
    if size > MAX_IMAGE_BYTES:
        issues.add("too_large", f"{path.name} nặng {size / 1e6:.1f} MB, tối đa 10 MB", product_id)
        return None
    try:
        with Image.open(path) as im:
            if max(im.size) > MAX_IMAGE_SIDE:
                issues.add(
                    "too_large", f"{path.name} {im.size[0]}×{im.size[1]} px, mỗi cạnh tối đa 4000 px", product_id
                )
                return None
            im.load()
            return im.copy()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        issues.add("bad_image", f"{path.name} không mở được như ảnh: {exc}", product_id)
        return None


def _shrink(im: Image.Image, max_side: int) -> Image.Image:
    if max(im.size) <= max_side:
        return im
    ratio = max_side / max(im.size)
    return im.resize((max(1, round(im.width * ratio)), max(1, round(im.height * ratio))), Image.Resampling.LANCZOS)


def _load_art(path: Path, product_id: str, issues: _Issues) -> tuple[Image.Image, bool] | None:
    """(art cropped to its alpha, opaque): opaque means not one transparent pixel, so the picture keeps its
    background (013 FR-018) even though the file has an alpha channel."""
    im = _open_image(path, issues, product_id)
    if im is None:
        return None
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    if not has_alpha:
        issues.add("no_alpha", f"{path.name} không có nền trong suốt: cần PNG/WebP đã cắt nền", product_id)
        return None
    rgba = im.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        issues.add("bad_image", f"{path.name} trong suốt hoàn toàn, không có gì để vẽ", product_id)
        return None
    opaque = rgba.getchannel("A").getextrema()[0] == 255
    return _shrink(rgba.crop(bbox), ART_MAX_SIDE), opaque


def _product_files(products_dir: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    if products_dir.is_dir():
        for path in sorted(products_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
                found.setdefault(path.stem, []).append(path)
    return found


def _provenance(
    path: Path | None,
    root: Path,
    art_ids: Iterable[str],
    has_desk: bool,
    issues: _Issues,
    skip: frozenset[str] = frozenset(),
) -> Provenance | None:
    """`skip` = products whose image comes from the upload manifest: their kit records no longer describe what is drawn
    (the operator's rights confirmation replaces them, ADR-071), so they raise no kit issues."""
    data = _read_json(path, issues, "missing_provenance") if path is not None and path.is_file() else None
    if data is None:
        if path is not None and not path.is_file():
            for pid in art_ids:
                issues.add("missing_provenance", f"Thiếu provenance.json: không rõ nguồn ảnh {pid}", pid)
        return None
    desk = data.get("desk") if isinstance(data.get("desk"), dict) else {}
    desk_source = desk.get("source")
    if has_desk and desk_source not in DESK_SOURCES:
        issues.add(
            "missing_provenance",
            f"provenance.json: desk.source '{desk_source}' phải là một trong {sorted(DESK_SOURCES)}",
        )
    raw_products = data.get("products") if isinstance(data.get("products"), dict) else {}
    records: dict[str, ProvenanceRecord] = {}
    for pid, raw in raw_products.items():
        if pid in skip:
            continue
        if not isinstance(raw, dict):
            issues.add("missing_provenance", f"provenance.json: mục {pid} phải là object", pid)
            continue
        placeholder = raw.get("placeholder") is True
        edits = tuple(str(e) for e in raw.get("edits") or ())
        for edit in edits:
            if edit == "ai_generated":
                issues.add("ai_product", f"Ảnh {pid} do AI tạo: ảnh sản phẩm phải là ảnh thật của khách (FR-002)", pid)
            elif edit not in ALLOWED_EDITS:
                issues.add(
                    "bad_edit", f"Ảnh {pid}: thao tác '{edit}' không được phép (chỉ {sorted(ALLOWED_EDITS)})", pid
                )
        original = raw.get("original")
        if not placeholder:
            original_path = _inside(root, original, issues, f"provenance {pid}.original") if original else None
            if original_path is None or not original_path.is_file():
                issues.add("missing_original", f"Ảnh {pid}: không thấy ảnh gốc '{original}' trong thư mục cảnh", pid)
        else:
            issues.add("placeholder", f"Ảnh {pid} là ảnh mẫu: thay bằng ảnh thật của khách trước phiên thật", pid)
        records[pid] = ProvenanceRecord(str(original) if original else None, edits, placeholder)
    for pid in art_ids:
        if pid not in records:
            issues.add("missing_provenance", f"provenance.json không có mục cho ảnh {pid}", pid)
    customer = data.get("customer_id")
    return Provenance(str(customer) if customer else None, desk_source, records)


def _read_manifest(root: Path, issues: _Issues, customer_id: str) -> dict[str, Any]:
    """Product entries of `uploads/images.json` (contracts/scene-set.md §3); {} when absent or unusable."""
    path = root / UPLOADS_DIR / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        issues.add("bad_uploads", f"uploads/images.json hỏng: {exc}")
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("products"), dict):
        issues.add("bad_uploads", "uploads/images.json hỏng: cần object có khóa products")
        return {}
    if data.get("schema_version") != SCHEMA_VERSION:
        version = data.get("schema_version")
        issues.add("bad_uploads", f"uploads/images.json hỏng: schema_version {version!r} chưa hỗ trợ")
        return {}
    owner = data.get("customer_id")
    if owner and customer_id and str(owner) != customer_id:
        issues.add(
            "customer_mismatch",
            f"uploads/images.json của khách '{owner}' nhưng phiên là của '{customer_id}': không vẽ cảnh (Điều I)",
        )
        return {}
    entries: dict[str, Any] = {}
    for pid, entry in data["products"].items():
        if not isinstance(pid, str) or len(pid) > PRODUCT_ID_MAX or not PRODUCT_ID_RE.match(pid):
            issues.add("bad_uploads", f"uploads/images.json: bỏ qua mã sản phẩm lạ {pid!r}")
            continue
        entries[pid] = entry
    return entries


def _load_upload(root: Path, pid: str, entry: Any, issues: _Issues) -> ProductArt | None:
    """The art of a product the manifest manages (active is a version id or null)."""
    active = entry["active"]
    if active is None:
        issues.add("missing_image", f"Sản phẩm {pid} đã gỡ ảnh: chỉ hiện thẻ tên/giá", pid)
        return None
    unreadable = f"Ảnh tải lên {active} của sản phẩm {pid} không đọc được"
    versions = entry.get("versions")
    version = versions.get(active) if isinstance(versions, dict) else None
    if not isinstance(version, dict):
        issues.add("bad_uploads", unreadable, pid)
        return None
    if not version.get("rights_confirmed_at"):
        message = f"Ảnh tải lên của sản phẩm {pid} chưa có xác nhận quyền dùng: không hiện"
        issues.add("missing_confirmation", message, pid)
        return None
    path = root / UPLOADS_DIR / pid / f"{active}.png"
    scratch = _Issues()
    loaded = _load_art(path, pid, scratch)
    if loaded is None:
        issues.add("bad_uploads", unreadable, pid)
        return None
    image, opaque = loaded
    return ProductArt(pid, path, image, source="upload", version_id=active, opaque=opaque)


def _managed(pid: str, entry: Any, issues: _Issues) -> bool:
    """True when the manifest, not `products/`, decides this product's image."""
    if not isinstance(entry, dict):
        issues.add("bad_uploads", f"uploads/images.json: mục {pid} phải là object", pid)
        return False
    active = entry.get("active", KIT)
    if active == KIT:
        return False
    if active is None or (isinstance(active, str) and VERSION_ID_RE.match(active)):
        return True
    issues.add("bad_uploads", f"uploads/images.json: active {active!r} của sản phẩm {pid} không hợp lệ", pid)
    return False


def _scene_json(root: Path) -> dict[str, Any]:
    path = root / "scene.json"
    return (_read_json(path, _Issues(), "bad_scene_json") or {}) if path.is_file() else {}


def scene_customer(root: Path) -> str | None:
    """The `customer_id` written in `scene.json` (None when absent or unreadable)."""
    owner = _scene_json(root).get("customer_id")
    return str(owner) if owner else None


def kit_art_path(root: Path, product_id: str) -> Path | None:
    """The kit file the scene would draw for `product_id` (first usable PNG/WebP in `products_dir`), if any."""
    products_dir = _inside(root, _scene_json(root).get("products_dir", "products"), _Issues(), "products_dir")
    if products_dir is None:
        return None
    usable = [p for p in _product_files(products_dir).get(product_id, []) if p.suffix.lower() in _PRODUCT_SUFFIXES]
    return usable[0] if usable else None


def load_kit_art(root: Path, product_id: str) -> ProductArt | None:
    """The kit art as the scene draws it (cropped, ≤ `ART_MAX_SIDE`), for thumbnails; None when unusable."""
    path = kit_art_path(root, product_id)
    loaded = _load_art(path, product_id, _Issues()) if path is not None else None
    return ProductArt(product_id, path, loaded[0], opaque=loaded[1]) if path is not None and loaded else None


def load_version_art(root: Path, product_id: str, version_id: str) -> ProductArt | None:
    """One uploaded version as the scene would draw it, for previews; None when the file is missing or unreadable."""
    path = version_path(root / UPLOADS_DIR, product_id, version_id)
    if not path.is_file():
        return None
    loaded = _load_art(path, product_id, _Issues())
    if loaded is None:
        return None
    return ProductArt(product_id, path, loaded[0], source="upload", version_id=version_id, opaque=loaded[1])


def load_scene_set(root: Path, product_ids: Iterable[str] = (), *, customer_id: str = "") -> SceneSet:
    """Read `root` against the products of the loaded catalog. `customer_id` is `CUSTOMER_ID` ("" = not set)."""
    issues = _Issues()
    ids = list(dict.fromkeys(product_ids))
    if not root.is_dir():
        issues.add("missing_dir", f"Không có thư mục cảnh {root}")
        return SceneSet(root=root, scene_id=root.name, issues=tuple(issues.items))

    scene_json = root / "scene.json"
    data: dict[str, Any] = {}
    if scene_json.is_file():
        data = _read_json(scene_json, issues, "bad_scene_json") or {}
    else:
        issues.add("missing_scene_json", "Không có scene.json: dùng bố cục và màu mặc định")
    for key in sorted(set(data) - _SCENE_KEYS):
        issues.add("unknown_key", f"scene.json: bỏ qua khóa lạ {key}")
    if data.get("schema_version", 1) != 1:
        issues.add("bad_scene_json", f"scene.json: schema_version {data.get('schema_version')!r} chưa hỗ trợ (cần 1)")

    scene_customer = data.get("customer_id")
    scene_customer = str(scene_customer) if scene_customer else None
    if scene_customer and customer_id and scene_customer != customer_id:
        issues.add(
            "customer_mismatch",
            f"Bộ cảnh của khách '{scene_customer}' nhưng phiên là của '{customer_id}': không vẽ cảnh (Điều I)",
        )

    desk: Image.Image | None = None
    desk_path = _inside(root, data.get("desk", "desk.png"), issues, "desk")
    if desk_path is not None and desk_path.is_file():
        opened = _open_image(desk_path, issues, None)
        if opened is not None:
            desk = _shrink(opened.convert("RGBA"), DESK_MAX_WIDTH)
    elif desk_path is not None:
        issues.add("missing_desk", "Không có ảnh bàn: tô màu desk_color")

    products_dir = _inside(root, data.get("products_dir", "products"), issues, "products_dir")
    files = _product_files(products_dir) if products_dir is not None else {}
    manifest = _read_manifest(root, issues, customer_id)
    managed = frozenset(pid for pid in ids if pid in manifest and _managed(pid, manifest[pid], issues))
    art: dict[str, ProductArt] = {}
    for pid in ids:
        if pid in managed:
            upload = _load_upload(root, pid, manifest[pid], issues)
            if upload is not None:
                art[pid] = upload
            continue
        candidates = files.get(pid, [])
        usable = [p for p in candidates if p.suffix.lower() in _PRODUCT_SUFFIXES]
        if not candidates:
            issues.add("missing_image", f"Sản phẩm {pid} chưa có ảnh: chỉ hiện thẻ tên/giá", pid)
            continue
        if not usable:
            names = ", ".join(p.name for p in candidates)
            issues.add("no_alpha", f"{names}: cần PNG/WebP nền trong suốt cho sản phẩm {pid}", pid)
            continue
        loaded = _load_art(usable[0], pid, issues)
        if loaded is not None:
            art[pid] = ProductArt(pid, usable[0], loaded[0], opaque=loaded[1])
    for stem in sorted(set(files) - set(ids)):
        issues.add(
            "orphan_image", f"Ảnh {files[stem][0].name} không khớp mã sản phẩm nào trong file dữ liệu: không hiện"
        )

    provenance_path = _inside(root, data.get("provenance", "provenance.json"), issues, "provenance")
    kit_ids = [pid for pid, item in art.items() if item.source == "kit"]
    provenance = _provenance(provenance_path, root, kit_ids, desk is not None, issues, managed)
    if provenance is not None:
        if provenance.customer_id and customer_id and provenance.customer_id != customer_id:
            issues.add(
                "customer_mismatch",
                f"provenance.json của khách '{provenance.customer_id}' nhưng phiên là của '{customer_id}'",
            )
        for pid, item in art.items():
            record = provenance.products.get(pid)
            if item.source == "kit" and record is not None and record.placeholder:
                art[pid] = ProductArt(pid, item.path, item.image, placeholder=True)

    layout = _layout(data.get("layout"), issues)
    art = with_stock(art, layout)  # 013 FR-030 (ADR-095)
    background = _background(data.get("background"), issues)
    shop_photo = load_shop_photo(root) if background.style == "anh_shop" else None

    return SceneSet(
        root=root,
        scene_id=str(data.get("scene_id") or root.name),
        customer_id=scene_customer,
        desk=desk,
        desk_color=_color(data.get("desk_color"), DEFAULT_DESK_COLOR, "desk_color", issues),
        accent_color=_color(data.get("accent_color"), DEFAULT_ACCENT_COLOR, "accent_color", issues),
        layout=layout,
        background=background,
        shop_photo=shop_photo,
        art=art,
        provenance=provenance,
        issues=tuple(issues.items),
    )
