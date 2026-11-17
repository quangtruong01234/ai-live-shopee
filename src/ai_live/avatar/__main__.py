"""`uv run python -m ai_live.avatar check|prepare <dir>`: validate a character folder, then prepare it in the fork.

Output is for the operator, in Vietnamese (contracts/events.md §6). Exit code 0 = ok, 1 = something to fix.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_live.avatar.character import (
    AvatarCharacter,
    CharacterError,
    ForkRun,
    PrepareResult,
    load_character,
    prepare_character,
)


def _default_fork_python() -> Path:
    # Read lazily: `check` must work without a filled-in `.env`.
    from ai_live.core.config import Settings

    return Settings().livetalking_python


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ai_live.avatar", description="Kiểm tra và chuẩn bị thư mục nhân vật"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Kiểm tra character.json, provenance.json và file (không cần fork)")
    check.add_argument("avatar_dir", type=Path)
    prepare = sub.add_parser("prepare", help="Kiểm tra rồi cho fork đọc từng clip, cắt mặt sẵn")
    prepare.add_argument("avatar_dir", type=Path)
    prepare.add_argument("--python", type=Path, default=None, help="Python của venv fork (mặc định LIVETALKING_PYTHON)")
    return parser


def _print_errors(error: CharacterError) -> None:
    print(f"Hồ sơ chưa hợp lệ ({len(error.errors)} lỗi):")
    for item in error.errors:
        print(f"  {item.describe()}")


def _print_valid(character: AvatarCharacter) -> None:
    kinds = ", ".join(f"{kind}: {len(character.clips_of(kind))}" for kind in ("idle", "talk"))
    print(f"Hồ sơ hợp lệ: {character.character_id} (khách {character.customer_id}; clip {kinds})")
    for warning in character.warnings:
        print(f"  Cảnh báo: {warning}")


_POSE_REASONS = {"roll": "đầu nghiêng", "pitch": "đầu ngửa/cúi", "yaw": "đầu quay", "no_face": "không thấy mặt"}


def _print_pose(pose: Any) -> None:
    """Talk-clip frames the fork will not speak on (010 US3, FR-011)."""
    if not isinstance(pose, dict):
        return
    if pose.get("skipped"):
        print(f"    góc đầu: bỏ qua, {pose['skipped']}")
        return
    excluded = [e for e in pose.get("excluded") or [] if isinstance(e, dict)]
    print(f"    góc đầu: dùng {pose.get('usable_frames', '?')} khung, loại {len(excluded)} đoạn")
    for e in excluded:
        reason = _POSE_REASONS.get(e.get("reason"), "đoạn còn lại quá ngắn")
        print(f"      khung {e.get('start')}–{e.get('end')}: {reason}")
    if pose.get("warning") == "talk_too_short":
        print("    Cảnh báo: clip nói còn quá ít khung dùng được (< 4 giây), nên quay lại clip nói mặt thẳng hơn")


def _print_prepare(result: PrepareResult) -> None:
    print(f"Kết quả prepare: {result.status} (fork {result.fork_commit or '?'}, khung {result.frame_size or '?'})")
    if result.clips:
        print(f"  {'clip':<16}{'khung':>8}{'fps':>8}")
        for clip_id, info in result.clips.items():
            info = info if isinstance(info, dict) else {}
            print(f"  {clip_id:<16}{info.get('frames', '?')!s:>8}{info.get('fps', '?')!s:>8}")
            _print_pose(info.get("pose"))
    for item in result.errors:
        print(f"  {item.describe()}")


def main(argv: Sequence[str] | None = None, *, run: ForkRun | None = None) -> int:
    args = _parser().parse_args(argv)
    # A Windows pipe defaults to cp1252 and the Vietnamese report would raise (a console is fine either way).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        character = load_character(args.avatar_dir)
    except CharacterError as error:
        _print_errors(error)
        return 1
    _print_valid(character)
    if args.command == "check":
        return 0

    fork_python = args.python or _default_fork_python()
    try:
        result = asyncio.run(prepare_character(args.avatar_dir, fork_python, run=run))
    except CharacterError as error:
        _print_errors(error)
        return 1
    _print_prepare(result)
    return 0 if result.status == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
