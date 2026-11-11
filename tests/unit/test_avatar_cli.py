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
