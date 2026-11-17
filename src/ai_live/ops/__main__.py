"""`uv run python -m ai_live.ops readiness|report|backup-video` (specs/007-demo-readiness/contracts/cli.md).

Output is for the operator, in Vietnamese.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

DEFAULT_URL = "http://127.0.0.1:8000"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ai_live.ops", description="Việc vận hành ngày demo")
    sub = parser.add_subparsers(dest="command", required=True)

    readiness = sub.add_parser(
        "readiness", help="Kiểm tra trước demo (gọi app đang chạy, app tắt thì kiểm phần không cần app)"
    )
    readiness.add_argument("--url", default=DEFAULT_URL)
    readiness.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    report = sub.add_parser("report", help="Báo cáo tổng duyệt một show từ log phiên")
    report.add_argument("session", help="Thư mục phiên hoặc session_id trong SESSION_DATA_DIR")
    report.add_argument("--show", default=None, help="show_id (mặc định: show cuối của phiên)")
    report.add_argument("--json", action="store_true", help="In báo cáo dạng JSON")

    backup = sub.add_parser(
        "backup-video", help="Ghi video dự phòng 2–3 phút từ show thật (chỉ dùng cho demo Meet/YouTube)"
    )
    backup.add_argument("--seconds", type=float, default=150.0)
    backup.add_argument("--content", choices=("verbatim", "script"), default="verbatim")
    backup.add_argument("--url", default=DEFAULT_URL)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "readiness":
        from ai_live.ops.readiness import cli_readiness

        return cli_readiness(args.url, as_json=args.json)
    if args.command == "report":
        from ai_live.ops.rehearsal import cli_report

        return cli_report(args.session, show_id=args.show, as_json=args.json)
    from ai_live.ops.backup_video import cli_backup_video

    return cli_backup_video(args.url, seconds=args.seconds, content=args.content)


if __name__ == "__main__":
    sys.exit(main())
