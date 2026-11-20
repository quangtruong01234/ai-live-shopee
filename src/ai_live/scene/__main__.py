"""Check or preview a scene set without running the app (contracts/scene-set.md §5).

`uv run python -m ai_live.scene check [SCENE_DIR] [--content PATH]`: one line per issue, exit 1 on any error.
`uv run python -m ai_live.scene preview [SCENE_DIR] --out FILE.png [--content PATH] [--highlight ID] [--subtitle TEXT]
[--debug-zones] [--label-position top-right]`: the still image as the host page would show it.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

from ai_live.core.config import Settings
from ai_live.products.docx_loader import load_catalog_file
from ai_live.products.models import ContentLoadError, ProductCatalog
from ai_live.scene.fonts import SceneFontError, load_fonts
from ai_live.scene.layout import compute_layout, estimate_geometry
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import SceneIssue, SceneSet
from ai_live.scene.render import compose_still, cover_crop, draw_debug_zones, render_base, render_subtitle
from ai_live.scene.uploads import ProductImageStore

LEVEL_LABEL = {"error": "LỖI ", "warning": "CHÚ Ý"}
LABEL_POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")


def _print_issues(issues: list[SceneIssue]) -> None:
    for issue in issues:
        print(f"{LEVEL_LABEL[issue.level]}  {issue.code}  {issue.message}")


def _uploads_summary(scene_dir: Path, scene: SceneSet, product_ids: list[str]) -> str | None:
    """One line about uploaded images (012 contracts/scene-set.md §5); None when the set has no uploads yet."""
    store = ProductImageStore(scene_dir)
    if not store.manifest_path.is_file():
        return None
    in_use = sum(art.source == "upload" for art in scene.art.values())
    unconfirmed = sum(issue.code == "missing_confirmation" for issue in scene.issues)
    entries = store.entries()
    removed = sum(1 for pid in product_ids if pid in entries and entries[pid].get("active", "kit") is None)
    return f"Ảnh tải lên: {in_use} đang dùng, {unconfirmed} thiếu xác nhận, {removed} đã gỡ"


def _catalog(path: Path, settings: Settings) -> ProductCatalog | None:
    try:
        return load_catalog_file(path, settings.content_max_bytes)
    except (ContentLoadError, OSError) as exc:
        print(f"LỖI   content  Không đọc được file nội dung {path}: {exc}")
        return None


def _face_image(settings: Settings) -> Image.Image:
    """The character's still image, as `/host` shows it in still mode or after a fall-back."""
    candidates = [settings.avatar_dir / "face.png", settings.avatar_static_image]
    if settings.avatar_mode != "livetalking":
        candidates.reverse()
    for path in candidates:
        if path.is_file():
            return Image.open(path).convert("RGB")
    return Image.new("RGB", (480, 832), (70, 70, 80))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings()
    parser = argparse.ArgumentParser(prog="python -m ai_live.scene")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "preview"):
        cmd = sub.add_parser(name)
        cmd.add_argument("scene_dir", type=Path, nargs="?", default=settings.scene_dir)
        cmd.add_argument("--content", type=Path, default=settings.product_data_path)
    preview = sub.choices["preview"]
    preview.add_argument("--out", type=Path, required=True)
    preview.add_argument("--highlight")
    preview.add_argument("--subtitle")
    preview.add_argument("--debug-zones", action="store_true")
    preview.add_argument("--label-position", choices=LABEL_POSITIONS, default=settings.ai_label_position)
    args = parser.parse_args(argv)

    catalog = _catalog(args.content, settings)
    if catalog is None:
        return 1
    scene = load_scene_set(args.scene_dir, [p.id for p in catalog.products], customer_id=settings.customer_id)
    position = getattr(args, "label_position", settings.ai_label_position)
    geometry = estimate_geometry(settings.ai_label_text, position)
    art_sizes = {pid: art.image.size for pid, art in scene.art.items()}
    layout = compute_layout(catalog.products, art_sizes, geometry, scene.layout, getattr(args, "highlight", None))
    issues = [*scene.issues, *layout.issues]
    _print_issues(issues)
    if args.command == "check":
        summary = _uploads_summary(args.scene_dir, scene, [p.id for p in catalog.products])
        if summary:
            print(summary)
        errors = sum(i.level == "error" for i in issues)
        print(f"Bộ cảnh {args.scene_dir}: {errors} lỗi, {len(issues) - errors} chú ý.")
        return 1 if errors else 0

    try:
        fonts = load_fonts(settings.scene_font_path)
    except SceneFontError as exc:
        print(f"LỖI   font  {exc}")
        return 1
    if scene.blocked:
        print("LỖI   blocked  Bộ cảnh bị chặn: không vẽ.")
        return 1
    products = {p.id: p for p in catalog.products}
    started = time.perf_counter()
    base = render_base(scene, layout, products, geometry, fonts)
    subtitle = render_subtitle(args.subtitle, layout, geometry, fonts) if args.subtitle else None
    render_ms = (time.perf_counter() - started) * 1000
    still = compose_still(cover_crop(_face_image(settings), geometry.width, geometry.height), [base, subtitle])
    if args.debug_zones:
        still = draw_debug_zones(still, geometry, layout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    still.save(args.out)
    size = len(base.png or b"")
    print(f"Đã ghi {args.out} ({geometry.width}×{geometry.height}); vẽ {render_ms:.0f} ms, lớp base {size // 1024} KB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
