"""011 T042: `lipsync-compare` verdict from a mouth benchmark run and two shows (contracts/lipsync-compare.md §1–§4).

Every case is a fake benchmark `report.json` plus two session directories written like `SessionLog` writes them; nothing
here runs a model, the fork or the app.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from ai_live.ops import lipsync_compare as lc
from fixtures.session_logs import NORMAL_GAPS, START, AlertSpec, ShowLog, write_show_logs

SESSION_A = "20261120-100000"
SESSION_B = "20261120-110000"
FIFTEEN_MINUTES_S = 900.0
AB_KEY_SECRET = "X=ultralight"

W2L_LIPSYNC = {
    "model": "wav2lip",
    "teacher": None,
    "character_id": "demo_host_01",
    "avatar_id": "demo_host_01_talk_01",
    "checkpoint_sha256": None,
}
ULTRALIGHT_LIPSYNC = {
    "model": "ultralight",
    "teacher": "musetalk",
    "character_id": "demo_host_02",
    "avatar_id": "demo_host_02__ultralight_musetalk",
    "checkpoint_sha256": "8276636d" + "0" * 56,
}


def write_mouth(
    base: Path,
    *,
    better: int = 3,
    sync_ok: bool | None = True,
    sc001: bool = True,
    avatar: str = "demo_host_02__w2l_musetalk",
    ab: bool = True,
) -> Path:
    run = base / "mouth" / "runs" / "20261119-215609"
    run.mkdir(parents=True)
    ultralight: dict[str, Any] = {
        "method": "ultralight",
        "open_ratio": 1.12,
        "spread_ratio": 1.0,
        "closure_recall": 0.86,
        "silence_closed": 0.6,
        "corr_open_loud": 0.21,
        "sharp_ratio": 1.02,
        "lse_c": 6.2,
        "lse_d": 7.1,
        "render_fps": 81.0,
        "gpu_mb": 1937,
        "spec": "ultralight unet + HuBERT",
        "model": "ultralight data/avatars/demo_host_02__ultralight_musetalk/ultralight.pth",
        # Absolute targets fail on purpose: they are copied for reference and never decide the verdict.
        "pass": {"open_ratio": False, "spread_ratio": False, "closure_recall": False, "render_fps": True},
    }
    if sc001:
        ultralight["sc001"] = {
            "gains": {"closure_recall": 0.18, "open_ratio": 0.17, "corr_open_loud": 0.45, "sharp_ratio": 0.02},
            "better": better,
            "sync_ok": sync_ok,
            "pass": better >= 2 and bool(sync_ok),
        }
    report = {
        "meta": {
            "started_at": "2026-11-19T21:56:09",
            "avatar": avatar,
            "ultralight_avatar": avatar.split("__")[0] + "__ultralight_musetalk",
            "gpu": "NVIDIA GeForce GTX 1650 Ti",
            "sentences": 27,
        },
        "summaries": [
            {
                "method": "w2l",
                "open_ratio": 0.95,
                "spread_ratio": 0.98,
                "closure_recall": 0.73,
                "silence_closed": 0.5,
                "corr_open_loud": 0.144,
                "sharp_ratio": 1.0,
                "lse_c": 5.9,
                "lse_d": 7.46,
                "render_fps": 32.9,
                "gpu_mb": 2133,
                "spec": "ref=same",
                "model": "wav2lip256 models/wav2lip.pth",
                "pass": {"open_ratio": False, "spread_ratio": False, "closure_recall": False, "render_fps": True},
            },
            ultralight,
        ],
        "sentences": [],
    }
    (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
    if ab:
        (run / "ab").mkdir()
        (run / "ab" / "PHIEU.md").write_text("# Phiếu chấm mù\n", encoding="utf-8")
        (run / "ab_key.json").write_text(json.dumps({"moi": AB_KEY_SECRET}), encoding="utf-8")
    return run


def _iso(offset_s: float) -> str:
    return (START + timedelta(seconds=offset_s)).isoformat().replace("+00:00", "Z")


def _append(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def write_session(
    base: Path,
    session_id: str,
    *,
    lipsync: dict[str, Any] | None,
    mouth_method: str,
    duration_s: float = FIFTEEN_MINUTES_S,
    gaps: Sequence[tuple[str, float]] = NORMAL_GAPS,
    render_fps: Sequence[float] = (25.0, 24.6, 25.3),
    vram_used_mb: int | None = 2116,
    vram_peak_mb: int | None = None,
    first_sentence_s: float | None = 2.4,
    alerts: Sequence[AlertSpec] = (),
    error_types: Sequence[str] = (),
    ended_by: str = "operator",
) -> ShowLog:
    show = write_show_logs(
        base,
        session_id=session_id,
        duration_s=duration_s,
        gaps=gaps,
        render_fps=render_fps,
        mouth_method=mouth_method,
        alerts=alerts,
        ended_by=ended_by,
    )
    health: dict[str, Any] = {
        "ts": _iso(30.0),
        "kind": "health",
        "connected": True,
        "boot_id": "boot-1",
        "vram_used_mb": vram_used_mb,
        "infer_fps": None,
        "last_error": None,
        "lipsync": lipsync,
        "model_mismatch": False,
    }
    if vram_peak_mb is not None:
        health["vram_peak_mb"] = vram_peak_mb
    _append(show.directory / "avatar.jsonl", [health])
    if error_types:
        _append(
            show.directory / "errors.jsonl",
            [
                {"ts": _iso(60.0 + n), "show_id": show.show_id, "step": "render", "type": kind, "message": "lỗi"}
                for n, kind in enumerate(error_types)
            ],
        )
    summary_path = show.directory / f"show_summary_{show.show_id}.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["show_first_sentence_s"] = first_sentence_s
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return show


def write_a(base: Path, **kwargs: Any) -> ShowLog:
    return write_session(base, SESSION_A, lipsync=W2L_LIPSYNC, mouth_method="w2l", **kwargs)


def write_b(base: Path, **kwargs: Any) -> ShowLog:
    return write_session(base, SESSION_B, lipsync=ULTRALIGHT_LIPSYNC, mouth_method="ultralight", **kwargs)


def run(tmp_path: Path, mouth: Path, a: ShowLog, b: ShowLog) -> tuple[int, Path | None]:
    out = tmp_path / "out" / "011_compare"
    code = lc.cli_lipsync_compare(str(mouth), str(a.directory), str(b.directory), out=out)
    written = sorted(out.iterdir()) if out.is_dir() else []
    return code, written[-1] if written else None


def verdict_of(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "verdict.json").read_text(encoding="utf-8"))


def result_of(verdict: dict[str, Any], criterion: str) -> str:
    return next(c["result"] for c in verdict["criteria"] if c["id"] == criterion)


# --- the verdict ---


def test_all_thresholds_met_is_pass_and_exits_0(tmp_path: Path, capsys):
    code, folder = run(tmp_path, write_mouth(tmp_path), write_a(tmp_path), write_b(tmp_path))
    assert code == 0
    assert folder is not None
    verdict = verdict_of(folder)
    assert verdict["verdict"] == "Đạt"
    assert [c["id"] for c in verdict["criteria"]] == list(lc.CRITERIA_IDS)
    assert {c["result"] for c in verdict["criteria"]} == {"Đạt"}
    assert "Kết luận: Đạt" in capsys.readouterr().out


def test_criteria_ids_are_the_fixed_contract_list():
    assert lc.CRITERIA_IDS == (
        "mouth_metrics",
        "lse_c",
        "render_fps",
        "vram",
        "errors",
        "first_sentence",
        "gap_p95",
    )


@pytest.mark.parametrize(
    ("criterion", "mouth_kwargs", "b_kwargs", "a_kwargs"),
    [
        ("mouth_metrics", {"better": 1}, {}, {}),
        ("lse_c", {"sync_ok": False}, {}, {}),
        ("render_fps", {}, {"render_fps": (18.0, 19.5, 19.0)}, {}),
        ("vram", {}, {"vram_used_mb": 3700}, {}),
        ("vram", {}, {"vram_used_mb": 2100, "vram_peak_mb": 3600}, {}),
        ("errors", {}, {"alerts": (AlertSpec("frozen", "operator", 120.0, 4.0),)}, {}),
        ("errors", {}, {"error_types": ("vram_oom",)}, {}),
        ("errors", {}, {"error_types": ("renderer_restarted",)}, {}),
        ("errors", {}, {"ended_by": "crash"}, {}),
        ("first_sentence", {}, {"first_sentence_s": 5.6}, {}),
        ("gap_p95", {}, {"gaps": (("script", 1.8),) * 40}, {}),
        # 0.5 s is under 1.5 s but more than 1.1 × A's 0.4 s (SC-002).
        ("gap_p95", {}, {"gaps": (("script", 0.5),) * 40}, {}),
    ],
)
def test_one_threshold_missed_is_fail_and_exits_1(tmp_path: Path, criterion, mouth_kwargs, b_kwargs, a_kwargs):
    code, folder = run(
        tmp_path, write_mouth(tmp_path, **mouth_kwargs), write_a(tmp_path, **a_kwargs), write_b(tmp_path, **b_kwargs)
    )
    assert code == 1
    assert folder is not None
    verdict = verdict_of(folder)
    assert verdict["verdict"] == "Chưa đạt"
    assert result_of(verdict, criterion) == "Chưa đạt"
    others = [c["result"] for c in verdict["criteria"] if c["id"] != criterion]
    assert set(others) == {"Đạt"}


def test_gap_equal_to_one_point_one_times_a_still_passes(tmp_path: Path):
    a = write_a(tmp_path, gaps=(("script", 0.4),) * 40)
    b = write_b(tmp_path, gaps=(("script", 0.44),) * 40)
    code, folder = run(tmp_path, write_mouth(tmp_path), a, b)
    assert code == 0
    assert folder is not None
    assert result_of(verdict_of(folder), "gap_p95") == "Đạt"


@pytest.mark.parametrize(
    ("criterion", "mouth_kwargs", "b_kwargs"),
    [
        ("vram", {}, {"vram_used_mb": None}),
        ("errors", {}, {"duration_s": 300.0}),
        ("first_sentence", {}, {"first_sentence_s": None}),
        ("mouth_metrics", {"sc001": False}, {}),
        ("lse_c", {"sync_ok": None}, {}),
        ("render_fps", {}, {"render_fps": ()}),
    ],
)
def test_missing_numbers_are_missing_and_exit_2(tmp_path: Path, criterion, mouth_kwargs, b_kwargs):
    code, folder = run(
        tmp_path, write_mouth(tmp_path, **mouth_kwargs), write_a(tmp_path), write_b(tmp_path, **b_kwargs)
    )
    assert code == 2
    assert folder is not None
    verdict = verdict_of(folder)
    assert verdict["verdict"] == "Thiếu số"
    assert result_of(verdict, criterion) == "Thiếu số"
    assert "Chưa đạt" not in {c["result"] for c in verdict["criteria"]}


def test_gap_without_a_is_missing(tmp_path: Path):
    code, folder = run(
        tmp_path, write_mouth(tmp_path), write_a(tmp_path, gaps=(("pause", 0.4),) * 40), write_b(tmp_path)
    )
    assert code == 2
    assert folder is not None
    assert result_of(verdict_of(folder), "gap_p95") == "Thiếu số"


def test_a_failed_row_beats_a_missing_row(tmp_path: Path):
    code, folder = run(
        tmp_path, write_mouth(tmp_path, better=1), write_a(tmp_path), write_b(tmp_path, vram_used_mb=None)
    )
    assert code == 1
    assert folder is not None
    assert verdict_of(folder)["verdict"] == "Chưa đạt"


def test_absolute_benchmark_targets_do_not_decide(tmp_path: Path):
    # `summaries[].pass` is all false for both methods in `write_mouth`, yet every compare threshold is met.
    code, folder = run(tmp_path, write_mouth(tmp_path), write_a(tmp_path), write_b(tmp_path))
    assert code == 0
    assert folder is not None
    mouth = verdict_of(folder)["mouth"]
    assert mouth["better"] == 3
    assert mouth["sync_ok"] is True
    assert mouth["lse_c"] == {"a": 5.9, "b": 6.2}
    assert mouth["metrics"]["closure_recall"] == {"a": 0.73, "b": 0.86, "gain": 0.18}
    assert set(mouth["metrics"]) == {"closure_recall", "open_ratio", "corr_open_loud", "sharp_ratio"}


# --- bad input ---


def test_wrong_mouth_dir_exits_3_without_a_report(tmp_path: Path, capsys):
    out = tmp_path / "out"
    code = lc.cli_lipsync_compare(
        str(tmp_path / "nope"), str(write_a(tmp_path).directory), str(write_b(tmp_path).directory), out=out
    )
    assert code == 3
    assert not out.exists()
    assert "LỖI" in capsys.readouterr().out


def test_unreadable_benchmark_exits_3(tmp_path: Path):
    mouth = write_mouth(tmp_path)
    (mouth / "report.json").write_text("{not json", encoding="utf-8")
    out = tmp_path / "out"
    code = lc.cli_lipsync_compare(
        str(mouth), str(write_a(tmp_path).directory), str(write_b(tmp_path).directory), out=out
    )
    assert code == 3
    assert not out.exists()


def test_wrong_session_or_show_exits_3(tmp_path: Path, settings):
    mouth = write_mouth(tmp_path)
    b = write_b(tmp_path)
    s = settings.model_copy(update={"session_data_dir": tmp_path})
    out = tmp_path / "out"
    assert lc.cli_lipsync_compare(str(mouth), "no-such-session", str(b.directory), out=out, settings=s) == 3
    a = write_a(tmp_path)
    assert lc.cli_lipsync_compare(str(mouth), f"{a.directory}:missing-show", str(b.directory), out=out) == 3
    assert not out.exists()


# --- inputs and conditions ---


def test_takes_session_ids_and_an_explicit_show(tmp_path: Path, settings):
    mouth = write_mouth(tmp_path)
    a, b = write_a(tmp_path), write_b(tmp_path)
    s = settings.model_copy(update={"session_data_dir": tmp_path})
    out = tmp_path / "out"
    code = lc.cli_lipsync_compare(str(mouth), a.session_id, f"{b.session_id}:{b.show_id}", out=out, settings=s)
    assert code == 0
    verdict = verdict_of(next(out.iterdir()))
    assert verdict["inputs"]["show_a"] == {"session_id": SESSION_A, "show_id": a.show_id}
    assert verdict["inputs"]["show_b"] == {"session_id": SESSION_B, "show_id": b.show_id}
    assert verdict["inputs"]["mouth_dir"] == str(mouth)


def test_conditions_come_from_the_lipsync_connected_row(tmp_path: Path):
    code, folder = run(tmp_path, write_mouth(tmp_path), write_a(tmp_path), write_b(tmp_path))
    assert code == 0
    assert folder is not None
    conditions = verdict_of(folder)["conditions"]
    assert conditions["a"] == {
        "model": "wav2lip",
        "teacher": None,
        "character_id": "demo_host_01",
        "mouth_method": "w2l",
    }
    assert conditions["b"] == {
        "model": "ultralight",
        "teacher": "musetalk",
        "character_id": "demo_host_02",
        "mouth_method": "ultralight",
    }


def test_show_figures_are_recorded_for_both_sides(tmp_path: Path):
    code, folder = run(tmp_path, write_mouth(tmp_path), write_a(tmp_path), write_b(tmp_path, vram_peak_mb=2300))
    assert code == 0
    assert folder is not None
    show = verdict_of(folder)["show"]
    assert show["b"] == {
        "duration_s": FIFTEEN_MINUTES_S,
        "first_sentence_s": 2.4,
        "gap_p95_s": 0.4,
        "render_fps_p50": 25.0,
        "vram_peak_mb": 2300,
        "errors": 0,
        "ended_normally": True,
    }
    assert show["a"]["vram_peak_mb"] == 2116


@pytest.mark.parametrize(
    ("mouth_kwargs", "a_lipsync", "b_kwargs", "warning"),
    [
        ({}, ULTRALIGHT_LIPSYNC, {}, "Phiên A"),
        ({"avatar": "demo_host_01__w2l_musetalk"}, W2L_LIPSYNC, {}, "demo_host_02"),
        ({}, W2L_LIPSYNC, {"duration_s": 300.0}, "10 phút"),
    ],
)
def test_warnings_still_write_the_report(tmp_path: Path, mouth_kwargs, a_lipsync, b_kwargs, warning):
    a = write_session(tmp_path, SESSION_A, lipsync=a_lipsync, mouth_method="w2l")
    code, folder = run(tmp_path, write_mouth(tmp_path, **mouth_kwargs), a, write_b(tmp_path, **b_kwargs))
    assert code in (0, 2)
    assert folder is not None
    verdict = verdict_of(folder)
    assert any(warning in w for w in verdict["warnings"])
    assert any(warning in line for line in (folder / "report.md").read_text(encoding="utf-8").splitlines())


# --- the report files ---


def test_report_md_opens_with_the_verdict_and_names_the_ab_pack(tmp_path: Path):
    mouth = write_mouth(tmp_path)
    code, folder = run(tmp_path, mouth, write_a(tmp_path), write_b(tmp_path))
    assert code == 0
    assert folder is not None
    text = (folder / "report.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "**Kết luận: Đạt**"
    assert "ADR-066" in lines[1] and "ADR-062" in lines[1]
    assert str(mouth / "ab" / "PHIEU.md") in text
    assert verdict_of(folder)["ab_pack"] == str(mouth / "ab" / "PHIEU.md")
    for criterion in lc.CRITERIA_IDS:
        assert f"| `{criterion}` |" in text
    # The command never opens the answer key and copies no media.
    assert AB_KEY_SECRET not in text
    assert AB_KEY_SECRET not in (folder / "verdict.json").read_text(encoding="utf-8")
    assert sorted(p.name for p in folder.iterdir()) == ["report.md", "verdict.json"]


def test_no_ab_pack_is_null(tmp_path: Path):
    code, folder = run(tmp_path, write_mouth(tmp_path, ab=False), write_a(tmp_path), write_b(tmp_path))
    assert code == 0
    assert folder is not None
    assert verdict_of(folder)["ab_pack"] is None


def test_running_twice_gives_the_same_result(tmp_path: Path):
    mouth, a, b = write_mouth(tmp_path), write_a(tmp_path), write_b(tmp_path, vram_used_mb=3700)
    out = tmp_path / "out"
    first = lc.cli_lipsync_compare(str(mouth), str(a.directory), str(b.directory), out=out)
    second = lc.cli_lipsync_compare(str(mouth), str(a.directory), str(b.directory), out=out)
    assert first == second == 1
    folders = sorted(out.iterdir())
    assert len(folders) == 2
    one, two = (verdict_of(f) for f in folders)
    one.pop("created_at")
    two.pop("created_at")
    assert one == two
