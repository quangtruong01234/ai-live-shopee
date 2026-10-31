"""Kiểm file nội dung không cần chạy app: `uv run python -m ai_live.products validate <file.docx>`.

Thoát mã 0 nếu hợp lệ, 1 nếu có lỗi (in đủ danh sách lỗi), 2 nếu sai cách gọi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_live.core.config import Settings
from ai_live.products.docx_loader import load_catalog
from ai_live.products.models import ContentLoadError


def main(argv: list[str] | None = None) -> int:
    # Console Windows mặc định cp1252 sẽ hỏng chữ tiếng Việt.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m ai_live.products")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="kiểm file Word nội dung sản phẩm")
    validate.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    path: Path = args.file
    if not path.is_file():
        print(f"Không tìm thấy file: {path}")
        return 1
    try:
        catalog = load_catalog(path.read_bytes(), path.name, Settings().content_max_bytes)
    except ContentLoadError as exc:
        print(f"File '{path.name}' có {len(exc.issues)} lỗi:")
        for issue in exc.issues:
            print(f"  - [{issue.code}] {issue.message}")
        return 1

    print(f"File '{path.name}' hợp lệ (version {catalog.version}), {len(catalog.products)} sản phẩm:")
    for p in catalog.products:
        low, high = p.price_range
        price = f"{low:,}đ" if low == high else f"{low:,}đ – {high:,}đ"
        kind = "chính" if p.is_primary else "phụ"
        print(f"  - {p.name} ({kind}): {price.replace(',', '.')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
