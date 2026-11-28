"""Check or preview a scene set without running the app (contracts/scene-set.md §5).

`uv run python -m ai_live.scene check [SCENE_DIR] [--content PATH]`: one line per issue, exit 1 on any error.
`uv run python -m ai_live.scene preview [SCENE_DIR] --out FILE.png [--content PATH] [--highlight ID] [--subtitle TEXT]
[--debug-zones] [--label-position shopee-top] [--host-frame IMAGE]`: the still image as the host page would show it.

Both read the desk and hands settings of the character in `AVATAR_DIR` (013 contracts/scene-set.md §4), so the layout
matches the live one; `--debug-zones` then shows the desk edge and the hands zone to measure them against.
`--host-frame` draws on another image of the host, such as a frame of the lip-sync avatar, because the character's
still image may be framed differently from what the live stream shows.
`uv run python -m ai_live.scene shop-photo SCENE_DIR IMAGE --confirmed-by NAME [--ai-generated]`: put in the picture
the `anh_shop` background shows, with the operator's confirmation of the right to use it (014 FR-009, FR-009a).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

from ai_live.avatar.character import AvatarCharacter, CharacterError, load_character
from ai_live.core.config import AI_LABEL_POSITIONS, Settings
from ai_live.products.docx_loader import load_catalog_file
from ai_live.products.models import ContentLoadError, ProductCatalog
from ai_live.scene.fonts import SceneFontError, load_fonts
from ai_live.scene.layout import compute_scene_layout, estimate_geometry
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import SceneIssue, SceneSet
from ai_live.scene.render import compose_still, cover_crop, draw_debug_zones, render_base, render_subtitle
from ai_live.scene.shop_photo import AI_MIN_SOFTNESS_PX, ShopPhotoError, save_shop_photo
from ai_live.scene.uploads import ProductImageStore

LEVEL_LABEL = {"error": "LỖI ", "warning": "CHÚ Ý"}


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


def _character(settings: Settings) -> AvatarCharacter | None:
    """The character the layout is measured against; None (with a note) when its folder cannot be read."""
    try:
        return load_character(settings.avatar_dir)
    except (CharacterError, OSError, ValueError) as exc:
        print(f"CHÚ Ý  character  Không đọc được nhân vật {settings.avatar_dir}, bố cục dùng giá trị mặc định: {exc}")
        return None


def _shop_photo(args: argparse.Namespace) -> int:
    if not args.scene_dir.is_dir():
        print(f"LỖI   scene_dir  Không có thư mục cảnh {args.scene_dir}")
        return 1
    if not args.image.is_file():
        print(f"LỖI   image  Không thấy ảnh {args.image}")
        return 1
    if args.ai_generated:
        # FR-009a: the operator states this by running the command; the blur only makes small text unreadable.
        print(
            "Ảnh AI tạo: chỉ dùng cảnh cửa hàng chung, không người, không sản phẩm của khách,"
            " không logo hay chữ đọc được."
        )
    try:
        photo = save_shop_photo(
            args.scene_dir,
            args.image,
            confirmed_by=args.confirmed_by,
            source="ai_generated" if args.ai_generated else "photo",
        )
    except (ShopPhotoError, OSError) as exc:
        print(f"LỖI   shop_photo  {exc}")
        return 1
    if photo.image is None:
        print(f"LỖI   shop_photo  {photo.reason}")
        return 1
    blur = f", làm mờ ít nhất {AI_MIN_SOFTNESS_PX:g} px" if photo.source == "ai_generated" else ""
    print(f"Đã lưu ảnh shop {photo.path} ({photo.image.width}×{photo.image.height}, nguồn {photo.source}{blur}).")
    print('Đặt "background": {"style": "anh_shop"} trong scene.json rồi khởi động lại app.')
    return 0


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
    preview.add_argument("--label-position", choices=AI_LABEL_POSITIONS, default=settings.ai_label_position)
    preview.add_argument("--host-frame", type=Path)
    shop = sub.add_parser("shop-photo")
    shop.add_argument("scene_dir", type=Path)
    shop.add_argument("image", type=Path)
    shop.add_argument("--confirmed-by", required=True)
    shop.add_argument("--ai-generated", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "shop-photo":
        return _shop_photo(args)

    catalog = _catalog(args.content, settings)
    if catalog is None:
        return 1
    scene = load_scene_set(args.scene_dir, [p.id for p in catalog.products], customer_id=settings.customer_id)
    position = getattr(args, "label_position", settings.ai_label_position)
    character = _character(settings)
    desk_in_image = bool(character is not None and character.desk_in_image)
    desk_top = character.desk_top if character is not None else None
    hands_zone = character.hands_zone if character is not None else None
    geometry = estimate_geometry(settings.ai_label_text, position).with_hands_zone(hands_zone)
    art_sizes = {pid: art.desk_image.size for pid, art in scene.art.items()}
    highlight = getattr(args, "highlight", None)
    layout = compute_scene_layout(catalog.products, art_sizes, geometry, scene.layout, highlight, desk_top=desk_top)
    issues = [*scene.issues, *layout.issues]
    _print_issues(issues)
    if args.command == "check":
        print(f"Bố cục: layout_mode={layout.mode}, thẻ={scene.layout.cards}")
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
    base = render_base(scene, layout, products, geometry, fonts, desk_in_image=desk_in_image)
    subtitle = render_subtitle(args.subtitle, layout, geometry, fonts) if args.subtitle else None
    render_ms = (time.perf_counter() - started) * 1000
    if args.host_frame is not None and not args.host_frame.is_file():
        print(f"LỖI   host_frame  Không thấy ảnh {args.host_frame}")
        return 1
    host = Image.open(args.host_frame).convert("RGB") if args.host_frame is not None else _face_image(settings)
    still = compose_still(cover_crop(host, geometry.width, geometry.height), [base, subtitle])
    if args.debug_zones:
        still = draw_debug_zones(still, geometry, layout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    still.save(args.out)
    size = len(base.png or b"")
    print(f"Đã ghi {args.out} ({geometry.width}×{geometry.height}); vẽ {render_ms:.0f} ms, lớp base {size // 1024} KB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
