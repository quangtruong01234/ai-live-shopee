"""Ultralight vs Wav2Lip verdict for the demo (011 US2, contracts/lipsync-compare.md, data-model §6).

Two inputs, both already on disk: a mouth benchmark run (`report.json` of 010's `mouth_eval`) and two shows of the same
script, A on Wav2Lip and B on Ultralight. The thresholds are fixed by ADR-060 §5 / SC-001 / SC-002 and are never
lowered here. A number that is not in the files makes its row "Thiếu số": the command never guesses. The mouth rows
copy the benchmark's own SC-001 result instead of recomputing it, so the verdict cannot drift from the benchmark. The
blind A/B pack is only named; its answer key (`ab_key.json`) is never opened.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_live.director.session_log import ERRORS_FILE
from ai_live.ops.rehearsal import (
    PICTURE_SOUND_ALERTS,
    RehearsalReport,
    SessionNotFound,
    ShowLogs,
    ShowNotFound,
    _lipsync_block,
    _parse,
    _read_jsonl,
    _render_rows,
    build_report,
    last_show_id,
    load_show_logs,
    resolve_session_dir,
)

if TYPE_CHECKING:
    from ai_live.core.config import Settings

DEFAULT_OUT = Path("out/011_compare")
BENCHMARK_FILE = "report.json"
AB_PACK = Path("ab") / "PHIEU.md"

# contracts/lipsync-compare.md §3, in report order.
CRITERIA_IDS = ("mouth_metrics", "lse_c", "render_fps", "vram", "errors", "first_sentence", "gap_p95")
MOUTH_METRICS = ("closure_recall", "open_ratio", "corr_open_loud", "sharp_ratio")
MOUTH_BETTER_MIN = 2
RENDER_FPS_MIN = 20.0
VRAM_MAX_MB = 3584
COMPARE_MIN_S = 600.0
FIRST_SENTENCE_MAX_S = 5.0
GAP_P95_MAX_S = 1.5
GAP_VS_A_MAX = 1.1
# Render failures of the fork that count as errors on top of the watchdog's operator-level alerts.
ERROR_TYPES = frozenset({"vram_oom", "renderer_restarted"})
OPERATOR_LEVEL = "operator"
BENCH_CHARACTER = "demo_host_02"
EXPECTED_MODEL = {"a": "wav2lip", "b": "ultralight"}

VERDICT_LINE_2 = "Theo ADR-066: đạt thì demo dùng Ultralight thầy MuseTalk; chưa đạt giữ Wav2Lip (ADR-062)."


class Result(StrEnum):
    PASS = "Đạt"
    FAIL = "Chưa đạt"
    MISSING = "Thiếu số"


EXIT_CODES = {Result.PASS: 0, Result.FAIL: 1, Result.MISSING: 2}
EXIT_BAD_INPUT = 3


class CompareInputError(ValueError):
    """An input the command cannot read; the message is for the operator, in Vietnamese."""


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    threshold: str
    a: Any
    b: Any
    result: Result


@dataclass(frozen=True)
class SideInfo:
    """What one show contributes: where it came from, how it ran and its figures."""

    session_id: str
    show_id: str
    conditions: dict[str, Any]
    figures: dict[str, Any]
    power: str | None


@dataclass(frozen=True)
class CompareReport:
    created_at: str
    inputs: dict[str, Any]
    conditions: dict[str, Any]
    mouth: dict[str, Any]
    show: dict[str, Any]
    criteria: list[Criterion]
    verdict: Result
    ab_pack: str | None
    warnings: list[str] = field(default_factory=list)
    bench_meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("bench_meta")
        data["verdict"] = self.verdict.value
        data["criteria"] = [{**asdict(c), "result": c.result.value} for c in self.criteria]
        return data


# --- reading ---


def _round(value: Any, digits: int = 3) -> float | None:
    return round(float(value), digits) if isinstance(value, int | float) and not isinstance(value, bool) else None


def read_benchmark(mouth_dir: Path) -> dict[str, Any]:
    path = mouth_dir / BENCHMARK_FILE
    if not mouth_dir.is_dir():
        raise CompareInputError(f"Không tìm thấy thư mục bộ đo {mouth_dir}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompareInputError(f"Không đọc được {path}: {exc}.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("summaries"), list):
        raise CompareInputError(f"{path} không có mục `summaries` của bộ đo khẩu hình.")
    return data


def _summary(data: dict[str, Any], method: str) -> dict[str, Any]:
    for row in data["summaries"]:
        if isinstance(row, dict) and row.get("method") == method:
            return row
    return {}


def mouth_block(data: dict[str, Any]) -> dict[str, Any]:
    """data-model §6 `mouth`: Wav2Lip is the benchmark's `w2l` row, Ultralight its `ultralight` row with `sc001`."""
    w2l, ultralight = _summary(data, "w2l"), _summary(data, "ultralight")
    sc001 = ultralight.get("sc001") if isinstance(ultralight.get("sc001"), dict) else {}
    gains = sc001.get("gains") if isinstance(sc001.get("gains"), dict) else {}
    better = sc001.get("better")
    sync_ok = sc001.get("sync_ok")
    return {
        "metrics": {
            name: {"a": _round(w2l.get(name)), "b": _round(ultralight.get(name)), "gain": _round(gains.get(name))}
            for name in MOUTH_METRICS
        },
        "lse_c": {"a": _round(w2l.get("lse_c")), "b": _round(ultralight.get("lse_c"))},
        "better": better if isinstance(better, int) and not isinstance(better, bool) else None,
        "sync_ok": sync_ok if isinstance(sync_ok, bool) else None,
        # Absolute targets of 010, for reference only (contract §3): they never enter the verdict.
        "absolute_pass": {"a": w2l.get("pass"), "b": ultralight.get("pass")},
    }


def _resolve_show(spec: str, settings: Settings | None) -> tuple[Path, str | None]:
    """`<session_id or dir>[:<show_id>]`. A Windows path has a colon of its own, so the whole text is tried first."""
    try:
        return resolve_session_dir(spec, settings), None
    except SessionNotFound:
        pass
    if ":" in spec:
        session, show_id = spec.rsplit(":", 1)
        if session and show_id and "/" not in show_id and "\\" not in show_id:
            try:
                return resolve_session_dir(session, settings), show_id
            except SessionNotFound:
                pass
    raise CompareInputError(f"Không tìm thấy phiên {spec} (thư mục phiên hoặc session_id trong SESSION_DATA_DIR).")


def load_side(spec: str, settings: Settings | None = None) -> tuple[ShowLogs, RehearsalReport]:
    directory, show_id = _resolve_show(spec, settings)
    chosen = show_id or last_show_id(directory)
    if chosen is None:
        raise CompareInputError(f"Phiên {directory.name} chưa có show nào trong log.")
    try:
        logs = load_show_logs(directory, chosen)
    except (ShowNotFound, SessionNotFound) as exc:
        raise CompareInputError(f"Không tìm thấy show {chosen} trong phiên {directory.name}.") from exc
    return logs, build_report(logs)


def _in_window(row: dict[str, Any], report: RehearsalReport, *keys: str) -> bool:
    start, end = _parse(report.started_at), _parse(report.ended_at)
    if start is None or end is None:
        return True
    for key in keys:
        at = _parse(row.get(key))
        if at is not None:
            return start <= at <= end
    return False


def _vram_peak(logs: ShowLogs, report: RehearsalReport) -> int | None:
    """Largest VRAM the fork reported during the show: `vram_peak_mb` when sent, else the `vram_used_mb` samples."""
    values = [
        int(row[key])
        for row in logs.avatar
        if row.get("kind") == "health" and _in_window(row, report, "ts", "updated_at")
        for key in ("vram_peak_mb", "vram_used_mb")
        if isinstance(row.get(key), int | float) and not isinstance(row.get(key), bool)
    ]
    return max(values) if values else None


def _error_count(logs: ShowLogs, report: RehearsalReport) -> int:
    alerts = [
        a for a in report.alerts["list"] if a.get("level") == OPERATOR_LEVEL or a.get("kind") in PICTURE_SOUND_ALERTS
    ]
    rows, _ = _read_jsonl(logs.directory / ERRORS_FILE)
    failures = [
        row
        for row in rows
        if row.get("type") in ERROR_TYPES
        and (row.get("show_id") == logs.show_id or (row.get("show_id") is None and _in_window(row, report, "ts")))
    ]
    return len(alerts) + len(failures)


def show_figures(logs: ShowLogs, report: RehearsalReport) -> dict[str, Any]:
    first = (logs.summary or {}).get("show_first_sentence_s")
    return {
        "duration_s": report.duration_s,
        "first_sentence_s": _round(first),
        "gap_p95_s": report.gaps.get("p95_s"),
        "render_fps_p50": (report.render_fps or {}).get("p50"),
        "vram_peak_mb": _vram_peak(logs, report),
        "errors": _error_count(logs, report),
        "ended_normally": report.ended_normally,
    }


def side_conditions(logs: ShowLogs, report: RehearsalReport) -> dict[str, Any]:
    block = _lipsync_block(logs) or {}
    methods = [str(row["mouth_method"]) for row in _render_rows(logs) if row.get("mouth_method")]
    method = statistics.mode(methods) if methods else report.conditions.get("mouth_method")
    return {
        "model": block.get("model"),
        "teacher": block.get("teacher"),
        "character_id": block.get("character_id"),
        "mouth_method": method,
    }


def load_info(spec: str, settings: Settings | None = None) -> SideInfo:
    logs, report = load_side(spec, settings)
    return SideInfo(
        session_id=logs.session_id,
        show_id=logs.show_id,
        conditions=side_conditions(logs, report),
        figures=show_figures(logs, report),
        power=(logs.session or {}).get("power"),
    )


# --- judging ---


def _criteria(mouth: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> list[Criterion]:
    rows: list[Criterion] = []

    better = mouth["better"]
    rows.append(
        Criterion(
            "mouth_metrics",
            "Khẩu hình tốt hơn",
            f"≥ {MOUTH_BETTER_MIN}/4 chỉ số tốt hơn ≥ 15% (SC-001)",
            None,
            None if better is None else f"{better}/4",
            Result.MISSING if better is None else Result.PASS if better >= MOUTH_BETTER_MIN else Result.FAIL,
        )
    )

    sync_ok = mouth["sync_ok"]
    rows.append(
        Criterion(
            "lse_c",
            "Khớp tiếng",
            "LSE-C của Ultralight không thấp hơn",
            mouth["lse_c"]["a"],
            mouth["lse_c"]["b"],
            Result.MISSING if sync_ok is None else Result.PASS if sync_ok else Result.FAIL,
        )
    )

    fps = b["render_fps_p50"]
    rows.append(
        Criterion(
            "render_fps",
            "Tốc độ khung",
            f"p50 phiên B ≥ {RENDER_FPS_MIN:g}",
            a["render_fps_p50"],
            fps,
            Result.MISSING if fps is None else Result.PASS if fps >= RENDER_FPS_MIN else Result.FAIL,
        )
    )

    vram = b["vram_peak_mb"]
    rows.append(
        Criterion(
            "vram",
            "VRAM",
            f"lớn nhất phiên B ≤ {VRAM_MAX_MB} MB",
            a["vram_peak_mb"],
            vram,
            Result.MISSING if vram is None else Result.PASS if vram <= VRAM_MAX_MB else Result.FAIL,
        )
    )

    # A broken show fails even when short; a clean show shorter than 10 minutes has not shown it holds up yet.
    if b["errors"] or not b["ended_normally"]:
        errors_result = Result.FAIL
    elif b["duration_s"] < COMPARE_MIN_S:
        errors_result = Result.MISSING
    else:
        errors_result = Result.PASS
    rows.append(
        Criterion(
            "errors",
            "Không lỗi",
            f"phiên B 0 lỗi trong ≥ {COMPARE_MIN_S / 60:g} phút, kết thúc bình thường",
            a["errors"],
            b["errors"],
            errors_result,
        )
    )

    first = b["first_sentence_s"]
    rows.append(
        Criterion(
            "first_sentence",
            "Câu đầu",
            f"phiên B ≤ {FIRST_SENTENCE_MAX_S:g} s",
            a["first_sentence_s"],
            first,
            Result.MISSING if first is None else Result.PASS if first <= FIRST_SENTENCE_MAX_S else Result.FAIL,
        )
    )

    gap_a, gap_b = a["gap_p95_s"], b["gap_p95_s"]
    if gap_b is None:
        gap_result = Result.MISSING
    elif gap_b > GAP_P95_MAX_S:
        gap_result = Result.FAIL
    elif gap_a is None:
        gap_result = Result.MISSING
    else:
        # Rounded like the gap figures themselves, so 0.44 against 1.1 × 0.4 is not lost to float error.
        gap_result = Result.PASS if gap_b <= round(GAP_VS_A_MAX * gap_a, 3) else Result.FAIL
    rows.append(
        Criterion(
            "gap_p95",
            "Lặng giữa câu",
            f"p95 phiên B ≤ {GAP_P95_MAX_S:g} s và ≤ {GAP_VS_A_MAX:g} × A (SC-002)",
            gap_a,
            gap_b,
            gap_result,
        )
    )
    return rows


def overall(criteria: list[Criterion]) -> Result:
    results = {c.result for c in criteria}
    if Result.FAIL in results:
        return Result.FAIL
    if Result.MISSING in results:
        return Result.MISSING
    return Result.PASS


def _warnings(bench: dict[str, Any], a: SideInfo, b: SideInfo) -> list[str]:
    found = []
    for side, info in (("A", a), ("B", b)):
        expected = EXPECTED_MODEL[side.lower()]
        model = info.conditions["model"]
        if model != expected:
            found.append(
                f"Phiên {side} chạy model {model or 'không rõ'}, cần {expected} (theo dòng lipsync_connected)."
            )
        duration = info.figures["duration_s"]
        if duration < COMPARE_MIN_S:
            found.append(f"Show phiên {side} dài {duration / 60:.1f} phút, ngắn hơn {COMPARE_MIN_S / 60:g} phút.")
    meta = bench.get("meta") if isinstance(bench.get("meta"), dict) else {}
    avatars = [str(meta[key]) for key in ("avatar", "ultralight_avatar") if meta.get(key)]
    if not avatars or any(name.split("__")[0] != BENCH_CHARACTER for name in avatars):
        found.append(f"Bộ đo không chạy trên {BENCH_CHARACTER} (avatar: {', '.join(avatars) or 'không rõ'}).")
    return found


def build_compare(mouth_dir: Path, show_a: str, show_b: str, *, settings: Settings | None = None) -> CompareReport:
    bench = read_benchmark(mouth_dir)
    a = load_info(show_a, settings)
    b = load_info(show_b, settings)
    mouth = mouth_block(bench)
    criteria = _criteria(mouth, a.figures, b.figures)
    ab_pack = mouth_dir / AB_PACK
    meta = bench.get("meta") if isinstance(bench.get("meta"), dict) else {}
    return CompareReport(
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        inputs={
            "mouth_dir": str(mouth_dir),
            "show_a": {"session_id": a.session_id, "show_id": a.show_id},
            "show_b": {"session_id": b.session_id, "show_id": b.show_id},
        },
        conditions={"a": a.conditions, "b": b.conditions},
        mouth=mouth,
        show={"a": a.figures, "b": b.figures},
        criteria=criteria,
        verdict=overall(criteria),
        ab_pack=str(ab_pack) if ab_pack.is_file() else None,
        warnings=_warnings(bench, a, b),
        bench_meta={"gpu": meta.get("gpu"), "avatar": meta.get("avatar"), "power_a": a.power, "power_b": b.power},
    )


# --- output ---


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "có" if value else "không"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _model_line(conditions: dict[str, Any]) -> str:
    from ai_live.core.models import lipsync_label

    label = lipsync_label(conditions.get("model"), conditions.get("teacher"), conditions.get("character_id"))
    return f"{label} (mouth_method {_cell(conditions.get('mouth_method'))})"


def render_markdown(report: CompareReport) -> str:
    meta = report.bench_meta
    lines = [
        f"**Kết luận: {report.verdict.value}**",
        VERDICT_LINE_2,
        "",
        f"Tạo lúc {report.created_at}. Bộ đo khẩu hình: `{report.inputs['mouth_dir']}`.",
        "",
    ]
    if report.warnings:
        lines.append("## Cảnh báo")
        lines.append("")
        lines += [f"- {w}" for w in report.warnings]
        lines.append("")
    lines += [
        "## Ngưỡng (ADR-060 §5, SC-001, SC-002)",
        "",
        "| id | Tên | Ngưỡng | A (Wav2Lip) | B (Ultralight) | Kết quả |",
        "|----|-----|--------|-------------|----------------|---------|",
    ]
    lines += [
        f"| `{c.id}` | {c.name} | {c.threshold} | {_cell(c.a)} | {_cell(c.b)} | {c.result.value} |"
        for c in report.criteria
    ]
    lines += [
        "",
        "Chỉ số khẩu hình (bộ đo, A = w2l, B = ultralight, mức tăng do bộ đo tính):",
        "",
        "| Chỉ số | A | B | Tăng |",
        "|--------|---|---|------|",
    ]
    for name, row in report.mouth["metrics"].items():
        gain = row["gain"]
        lines.append(f"| {name} | {_cell(row['a'])} | {_cell(row['b'])} | {'—' if gain is None else f'{gain:+.0%}'} |")
    lines += ["", "## Điều kiện chạy", ""]
    for side, key in (("A", "a"), ("B", "b")):
        source = report.inputs[f"show_{key}"]
        figures = report.show[key]
        lines.append(
            f"- Phiên {side}: `{source['session_id']}` show `{source['show_id']}`; "
            f"model {_model_line(report.conditions[key])}; "
            f"dài {figures['duration_s'] / 60:.1f} phút; kết thúc bình thường: {_cell(figures['ended_normally'])}; "
            f"nguồn điện {_cell(meta.get(f'power_{key}'))}."
        )
    lines.append(f"- Bộ đo: máy {_cell(meta.get('gpu'))}, avatar {_cell(meta.get('avatar'))}.")
    lines += ["", "## Chấm mù A/B", ""]
    if report.ab_pack:
        lines.append(f"Phiếu chấm: `{report.ab_pack}` (lệnh này không mở đáp án).")
    else:
        lines.append("Bộ đo không có gói chấm mù (chạy `mouth_eval` với `--clips` để có).")
    return "\n".join(lines) + "\n"


def write_compare(report: CompareReport, out: Path) -> Path:
    stamp = datetime.fromisoformat(report.created_at).strftime("%Y-%m-%d_%H-%M-%S")
    folder = out / stamp
    n = 2
    while folder.exists():  # two runs in the same second keep both reports
        folder = out / f"{stamp}-{n}"
        n += 1
    folder.mkdir(parents=True)
    (folder / "verdict.json").write_text(json.dumps(report.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "report.md").write_text(render_markdown(report), encoding="utf-8")
    return folder


def cli_lipsync_compare(
    mouth: str, show_a: str, show_b: str, *, out: Path = DEFAULT_OUT, settings: Settings | None = None
) -> int:
    """Exit 0 Đạt, 1 Chưa đạt, 2 Thiếu số, 3 when an input cannot be read (nothing is written then)."""
    try:
        report = build_compare(Path(mouth), show_a, show_b, settings=settings)
    except CompareInputError as exc:
        print(f"LỖI  {exc}")
        return EXIT_BAD_INPUT
    folder = write_compare(report, out)
    print(render_markdown(report))
    print(f"Đã ghi {folder / 'report.md'} và verdict.json")
    return EXIT_CODES[report.verdict]
