"""`uv run python -m ai_live.avatar check|prepare <dir>`: validate a character folder, then prepare it in the fork.

`background-prepare <character_id>` (014 contracts/prepare-cli.md §1) cuts the host out of every frame the fork plays,
once per character, so a new room can be drawn behind them.

Output is for the operator, in Vietnamese (contracts/events.md §6). Exit code 0 = ok, 1 = something to fix,
2 = the fork tool itself broke (`background-prepare` only).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_live.avatar.character import (
    DEFAULT_FORK_DIR,
    AvatarCharacter,
    CharacterError,
    ForkRun,
    PrepareResult,
    load_character,
    prepare_character,
)

DEFAULT_ASSETS_DIR = DEFAULT_FORK_DIR.parents[1] / "assets" / "avatars"
BACKGROUND_MANIFEST = Path("background") / "manifest.json"


def _default_fork_python() -> Path:
    # Read lazily: `check` must work without a filled-in `.env`.
    from ai_live.core.config import Settings

    return Settings().livetalking_python


def _segmenter_model() -> str:
    from ai_live.core.config import Settings

    return Settings().background_segmenter_model


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
    background = sub.add_parser("background-prepare", help="Tách người khỏi phòng cũ để vẽ nền mới sau host (014)")
    background.add_argument("character_id")
    background.add_argument(
        "--method", choices=("plate", "mediapipe"), default="plate", help="Cách tách (mặc định plate)"
    )
    background.add_argument(
        "--room-area",
        action="append",
        default=[],
        metavar='"x,y x,y x,y ..."',
        help="Đa giác (pixel khung) quanh khe phòng cũ còn sót, như dưới nách; lặp lại được (ADR-094)",
    )
    background.add_argument(
        "--no-room-areas", action="store_true", help="Không dùng lại vùng phòng đã khoanh ở lần chạy trước"
    )
    background.add_argument("--json", action="store_true", help="Chỉ in dòng JSON của fork")
    background.add_argument("--mark-reviewed", action="store_true", help="Đánh dấu đã xem review.jpg, không chạy lại")
    background.add_argument("--by", default=None, help="Tên người duyệt (bắt buộc với --mark-reviewed)")
    background.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS_DIR, help="Thư mục assets/avatars")
    background.add_argument("--fork-dir", type=Path, default=DEFAULT_FORK_DIR, help="Thư mục fork LiveTalking")
    background.add_argument(
        "--python", type=Path, default=None, help="Python của venv fork (mặc định LIVETALKING_PYTHON)"
    )
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


# ---------- 014 `background-prepare` ----------


async def _low_priority_run(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run the fork tool below normal priority, so a live show on the same laptop keeps its voice and lip-sync."""
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS
    else:
        kwargs["preexec_fn"] = lambda: os.nice(10)
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **kwargs,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _fork_avatars(fork_dir: Path, character_id: str) -> list[Path]:
    """`data/avatars/<id>__*` folders that hold frames: the frames the fork plays for this character."""
    found = []
    for path in sorted((fork_dir / "data" / "avatars").glob(f"{character_id}__*")):
        full = path / "full_imgs"
        if full.is_dir() and any(full.iterdir()):
            found.append(path.resolve())
    return found


def _room_areas(args: argparse.Namespace, character_dir: Path) -> tuple[list[str], bool]:
    """`--room-area` texts for the fork, and whether they came from the last manifest (ADR-094).

    The marked gaps belong to the character's frames, not to one run: a re-run without them would quietly bring the old
    room back under the arm, so the last run's areas are reused unless new ones are given or `--no-room-areas` is set.
    """
    if args.no_room_areas:
        return [], False
    if args.room_area:
        return list(args.room_area), False
    try:
        manifest = json.loads((character_dir / "background" / "manifest.json").read_text(encoding="utf-8"))
        saved = manifest.get("room_areas") or []
        return [" ".join(f"{int(x)},{int(y)}" for x, y in corners) for corners in saved], bool(saved)
    except (OSError, ValueError, TypeError, AttributeError):
        return [], False


def _background_prepare(args: argparse.Namespace, run: ForkRun | None) -> int:
    character_dir = (args.assets_dir / args.character_id).resolve()
    if not character_dir.is_dir():
        print(f"Không thấy thư mục nhân vật {character_dir}")
        return 1
    avatars = _fork_avatars(args.fork_dir, args.character_id)
    if not avatars:
        where = args.fork_dir / "data" / "avatars" / f"{args.character_id}__*"
        print(f"Không thấy khung nào của nhân vật: cần thư mục {where} có full_imgs (chạy prepare của fork trước)")
        return 1
    model: Path | None = None
    if args.method == "mediapipe":
        setting = _segmenter_model().strip()
        if not setting or not Path(setting).is_file():
            print(
                "Cách mediapipe cần file model: tải model tách người theo ADR-083 (sau khi được duyệt), "
                "rồi đặt đường dẫn vào BACKGROUND_SEGMENTER_MODEL trong .env. Hoặc dùng --method plate."
            )
            return 1
        model = Path(setting).resolve()

    python = (args.python or _default_fork_python()).resolve()
    command = [str(python), "-m", "ailive_ext.background_prep", "--ailive_character", str(character_dir)]
    command += ["--avatars", *(str(a) for a in avatars), "--method", args.method]
    if model is not None:
        command += ["--model", str(model)]
    areas, reused = _room_areas(args, character_dir)
    for area in areas:
        command += ["--room-area", area]
    command.append("--json")
    if not args.json:
        print(f"Đang tách người trên {len(avatars)} thư mục khung ({args.method}), có thể mất vài phút...")
        if reused:
            print(f"  Dùng lại {len(areas)} vùng phòng khoanh lần trước (bỏ bằng --no-room-areas)")
    try:
        returncode, stdout, stderr = asyncio.run((run or _low_priority_run)(command, args.fork_dir))
    except OSError as exc:
        print(f"Không chạy được {python}: {exc}")
        return 2

    data = _fork_line(returncode, stdout)
    if data is None:
        print(f"Công cụ của fork bị lỗi (mã {returncode}):")
        print((stderr or stdout).strip()[-2000:] or "(không có thông báo)")
        return 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
        return 0 if data.get("ok") else 1
    if not data.get("ok"):
        print("Chưa chuẩn bị được nền:")
        for error in data.get("errors") or []:
            print(f"  {error}")
        return 1
    flagged = data.get("flagged_frames") or []
    print(
        f"Đã chuẩn bị nền: {data.get('frames', '?')} khung, cách tách {data.get('method', args.method)}, "
        f"{len(flagged)} khung có cờ lọt (mảng lọt lớn nhất {data.get('max_blob_px', '?')} px)"
    )
    if flagged:
        print(f"  Khung có cờ (số ô trong ảnh duyệt): {', '.join(str(f) for f in flagged)}")
    print(f"Xem ảnh duyệt: {data.get('review')}")
    print(
        f"Duyệt xong thì chạy: uv run python -m ai_live.avatar background-prepare {args.character_id} "
        '--mark-reviewed --by "<tên>"'
    )
    return 0


def _fork_line(returncode: int, stdout: str) -> dict[str, Any] | None:
    # rc 0 = prepared, 1 = data problems listed in the JSON line; anything else (or no JSON) = the tool broke.
    if returncode not in (0, 1):
        return None
    lines = [line for line in stdout.strip().splitlines() if line.strip()]
    if not lines:
        return None
    try:
        data = json.loads(lines[-1])
    except ValueError:
        return None
    return data if isinstance(data, dict) and "ok" in data else None


def _mark_reviewed(args: argparse.Namespace) -> int:
    path = args.assets_dir / args.character_id / BACKGROUND_MANIFEST
    hint = f"Chạy trước: uv run python -m ai_live.avatar background-prepare {args.character_id}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Chưa có nền nào để duyệt. {hint}")
        return 1
    except (OSError, ValueError) as exc:
        print(f"Không đọc được {path}: {exc}. {hint}")
        return 1
    if not isinstance(data, dict):
        print(f"{path} không đúng dạng. {hint}")
        return 1
    data.update(
        reviewed=True,
        reviewed_by=args.by.strip(),
        reviewed_at=datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
    )
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    print(f"Đã đánh dấu nền của {args.character_id} là đã duyệt (người duyệt: {args.by.strip()})")
    return 0


def main(argv: Sequence[str] | None = None, *, run: ForkRun | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    # A Windows pipe defaults to cp1252 and the Vietnamese report would raise (a console is fine either way).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if args.command == "background-prepare":
        if args.mark_reviewed:
            if not args.by or not args.by.strip():
                parser.error('--mark-reviewed cần --by "<tên người duyệt>"')
            return _mark_reviewed(args)
        return _background_prepare(args, run)
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
