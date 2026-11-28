"""CLI `python -m ai_live.avatar check | prepare` (005 T024, contracts/events.md §6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_live.avatar.__main__ import main
from fixtures.character_builder import CHARACTER_ID, DEFAULT_CLIPS, make_character_dir, read_character


class FakeForkRun:
    def __init__(self, returncode: int, out: dict) -> None:
        self.returncode = returncode
        self.out = out
        self.calls: list[list[str]] = []

    async def __call__(self, args: list[str], cwd: Path) -> tuple[int, str, str]:
        self.calls.append(args)
        return self.returncode, json.dumps(self.out), ""


def _ready() -> dict:
    return {
        "status": "ready",
        "fork_commit": "abc1234",
        "frame_size": [480, 832],
        "clips": {c["clip_id"]: {"frames": 121, "fps": 24.0} for c in DEFAULT_CLIPS},
        "errors": [],
    }


def test_check_valid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    avatar_dir = make_character_dir(tmp_path)
    assert main(["check", str(avatar_dir)]) == 0
    out = capsys.readouterr().out
    assert "Hồ sơ hợp lệ" in out
    assert CHARACTER_ID in out


def test_check_lists_every_error_with_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clips = [c for c in DEFAULT_CLIPS if c["kind"] != "talk"]
    avatar_dir = make_character_dir(tmp_path, character={"clips": clips}, write_provenance=False)
    assert main(["check", str(avatar_dir)]) != 0
    out = capsys.readouterr().out
    assert "[kind_missing]" in out
    assert "[missing_provenance]" in out
    assert "Hồ sơ hợp lệ" not in out


def test_check_never_calls_fork(tmp_path: Path) -> None:
    run = FakeForkRun(0, _ready())
    assert main(["check", str(make_character_dir(tmp_path))], run=run) == 0
    assert run.calls == []


def test_prepare_prints_clip_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    avatar_dir = make_character_dir(tmp_path)
    run = FakeForkRun(0, _ready())
    assert main(["prepare", str(avatar_dir), "--python", str(tmp_path / "python.exe")], run=run) == 0
    out = capsys.readouterr().out
    for clip in DEFAULT_CLIPS:
        assert clip["clip_id"] in out
    assert "121" in out
    assert "ready" in out
    assert run.calls[0][0] == str((tmp_path / "python.exe").resolve())
    assert read_character(avatar_dir)["prepare"]["status"] == "ready"


def test_prepare_prints_head_pose_of_talk_clips(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """010 US3 (FR-011): the operator sees which talk frames the fork will skip and why."""
    out_json = _ready()
    out_json["clips"]["talk_01"]["pose"] = {
        "usable_frames": 60,
        "excluded": [{"start": 60, "end": 120, "reason": "roll"}],
        "warning": "talk_too_short",
    }
    out_json["clips"]["talk_02"]["pose"] = {"skipped": "thiếu face_landmarker.task"}
    assert main(["prepare", str(make_character_dir(tmp_path)), "--python", "py"], run=FakeForkRun(0, out_json)) == 0
    out = capsys.readouterr().out
    assert "góc đầu: dùng 60 khung, loại 1 đoạn" in out
    assert "khung 60–120: đầu nghiêng" in out
    assert "quá ít khung" in out
    assert "góc đầu: bỏ qua, thiếu face_landmarker.task" in out


def test_prepare_failed_shows_clip_and_frame(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_json = {
        **_ready(),
        "status": "failed",
        "errors": [{"code": "face_count", "clip_id": "talk_01", "frame": 84, "message": "Khung 84 có 2 khuôn mặt"}],
    }
    code = main(["prepare", str(make_character_dir(tmp_path)), "--python", "py"], run=FakeForkRun(1, out_json))
    assert code == 1
    out = capsys.readouterr().out
    assert "[face_count]" in out
    assert "talk_01" in out
    assert "84" in out


def test_prepare_invalid_character_skips_fork(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = FakeForkRun(0, _ready())
    code = main(["prepare", str(make_character_dir(tmp_path, write_provenance=False)), "--python", "py"], run=run)
    assert code == 1
    assert run.calls == []
    assert "[missing_provenance]" in capsys.readouterr().out


# ---------- 014 T021: `background-prepare` (contracts/prepare-cli.md §1) ----------

BG_ID = "demo_host_09"


def _bg_dirs(
    tmp_path: Path, avatars: tuple[str, ...] = ("w2l", "ultralight"), *, empty: tuple[str, ...] = ()
) -> tuple[Path, Path]:
    """`<assets>/<id>/` with a character.json and `<fork>/data/avatars/<id>__<name>/full_imgs/` per avatar."""
    assets, fork = tmp_path / "assets_avatars", tmp_path / "fork"
    (assets / BG_ID).mkdir(parents=True)
    (assets / BG_ID / "character.json").write_text(json.dumps({"character_id": BG_ID}), encoding="utf-8")
    for name in avatars:
        full = fork / "data" / "avatars" / f"{BG_ID}__{name}" / "full_imgs"
        full.mkdir(parents=True)
        if name not in empty:
            (full / "00000000.png").write_bytes(b"png")
    (fork / "data" / "avatars" / "other_host__w2l" / "full_imgs").mkdir(parents=True)
    return assets, fork


def _bg_args(assets: Path, fork: Path, *extra: str) -> list[str]:
    return ["background-prepare", BG_ID, "--assets-dir", str(assets), "--fork-dir", str(fork), "--python", "py", *extra]


def _bg_ok(**kw: object) -> dict:
    return {
        "ok": True,
        "frames": 81,
        "method": "plate",
        "flagged_frames": [40, 41],
        "max_blob_px": 210,
        "review": f"assets/avatars/{BG_ID}/background/review.jpg",
        "errors": [],
        **kw,
    }


def test_background_prepare_calls_the_fork_with_every_avatar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assets, fork = _bg_dirs(tmp_path, ("w2l", "ultralight", "no_frames"), empty=("no_frames",))
    run = FakeForkRun(0, _bg_ok())
    assert main(_bg_args(assets, fork), run=run) == 0
    args = run.calls[0]
    assert args[:3] == [str(Path("py").resolve()), "-m", "ailive_ext.background_prep"]
    assert args[args.index("--ailive_character") + 1] == str((assets / BG_ID).resolve())
    avatars = args[args.index("--avatars") + 1 : args.index("--method")]
    assert sorted(Path(a).name for a in avatars) == [f"{BG_ID}__ultralight", f"{BG_ID}__w2l"]  # only dirs with frames
    assert args[args.index("--method") + 1] == "plate"
    assert "--json" in args and "--model" not in args
    out = capsys.readouterr().out
    assert "81 khung" in out
    assert "plate" in out
    assert "2 khung có cờ lọt" in out
    assert "review.jpg" in out


def test_background_prepare_json_prints_the_fork_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assets, fork = _bg_dirs(tmp_path)
    assert main(_bg_args(assets, fork, "--json"), run=FakeForkRun(0, _bg_ok())) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == _bg_ok()


def test_background_prepare_data_error_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assets, fork = _bg_dirs(tmp_path)
    out = {"ok": False, "errors": ["khung khác cỡ: 480x832 và 480x800"]}
    assert main(_bg_args(assets, fork), run=FakeForkRun(1, out)) == 1
    assert "khung khác cỡ" in capsys.readouterr().out


def test_background_prepare_program_error_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assets, fork = _bg_dirs(tmp_path)

    async def crash(args: list[str], cwd: Path) -> tuple[int, str, str]:
        return 1, "", "Traceback (most recent call last):\nMemoryError"

    assert main(_bg_args(assets, fork), run=crash) == 2
    assert "MemoryError" in capsys.readouterr().out


def test_background_prepare_without_avatar_dirs_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assets, fork = _bg_dirs(tmp_path, ())
    run = FakeForkRun(0, _bg_ok())
    assert main(_bg_args(assets, fork), run=run) == 1
    assert run.calls == []
    assert f"data/avatars/{BG_ID}__" in capsys.readouterr().out.replace("\\", "/")


def test_background_prepare_mediapipe_needs_the_model_setting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKGROUND_SEGMENTER_MODEL", "")
    assets, fork = _bg_dirs(tmp_path)
    run = FakeForkRun(0, _bg_ok())
    assert main(_bg_args(assets, fork, "--method", "mediapipe"), run=run) == 1
    assert run.calls == []
    assert "BACKGROUND_SEGMENTER_MODEL" in capsys.readouterr().out


def test_background_prepare_mediapipe_passes_the_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "selfie_multiclass.tflite"
    model.write_bytes(b"x")
    monkeypatch.setenv("BACKGROUND_SEGMENTER_MODEL", str(model))
    assets, fork = _bg_dirs(tmp_path)
    run = FakeForkRun(0, _bg_ok(method="mediapipe"))
    assert main(_bg_args(assets, fork, "--method", "mediapipe"), run=run) == 0
    args = run.calls[0]
    assert args[args.index("--method") + 1] == "mediapipe"
    assert args[args.index("--model") + 1] == str(model.resolve())


def _room_areas_passed(args: list[str]) -> list[str]:
    return [args[i + 1] for i, a in enumerate(args) if a == "--room-area"]


def test_background_prepare_passes_room_areas(tmp_path: Path) -> None:
    assets, fork = _bg_dirs(tmp_path)
    run = FakeForkRun(0, _bg_ok())
    extra = ("--room-area", "1,2 3,4 5,6", "--room-area", "7,8 9,10 11,12")
    assert main(_bg_args(assets, fork, *extra), run=run) == 0
    assert _room_areas_passed(run.calls[0]) == ["1,2 3,4 5,6", "7,8 9,10 11,12"]


def test_background_prepare_reuses_the_last_room_areas(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assets, fork = _bg_dirs(tmp_path)
    (assets / BG_ID / "background").mkdir()
    manifest = {"room_areas": [[[1, 2], [3, 4], [5, 6]]]}
    (assets / BG_ID / "background" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    run = FakeForkRun(0, _bg_ok())
    assert main(_bg_args(assets, fork), run=run) == 0
    assert _room_areas_passed(run.calls[0]) == ["1,2 3,4 5,6"]
    assert "Dùng lại 1 vùng phòng" in capsys.readouterr().out
    run = FakeForkRun(0, _bg_ok())
    assert main(_bg_args(assets, fork, "--no-room-areas"), run=run) == 0
    assert _room_areas_passed(run.calls[0]) == []


def test_background_mark_reviewed_sets_who_and_when(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from fixtures.background_builder import make_background_dir

    assets, fork = _bg_dirs(tmp_path)
    make_background_dir(assets / BG_ID, character_id=BG_ID)
    run = FakeForkRun(0, _bg_ok())
    assert main(_bg_args(assets, fork, "--mark-reviewed", "--by", "Quang"), run=run) == 0
    assert run.calls == []  # no fork run to review
    data = json.loads((assets / BG_ID / "background" / "manifest.json").read_text(encoding="utf-8"))
    assert (data["reviewed"], data["reviewed_by"]) == (True, "Quang")
    assert "T" in data["reviewed_at"] and data["reviewed_at"][-6] in "+-"
    assert "Đã đánh dấu" in capsys.readouterr().out


def test_background_mark_reviewed_needs_a_name_and_a_prepared_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assets, fork = _bg_dirs(tmp_path)
    assert main(_bg_args(assets, fork, "--mark-reviewed", "--by", "Quang")) == 1  # nothing prepared yet
    assert "background-prepare" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(_bg_args(assets, fork, "--mark-reviewed"))  # `--by` is required with it
