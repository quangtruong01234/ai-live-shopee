"""Rehearsal report of one show, read from its session log (007 US3, data-model §4, contracts/files.md §5).

Only the files the app already writes are read, so a show cut short by a crash still gets a report from what reached
disk (FR-013). Verdicts follow PRD criteria 3 (silence between sentences) and 4 (a 30-minute show that ends normally
without a frozen picture or lost sound). Nothing here talks to the app, an LLM or the fork.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_live.director.session_log import (
    ALERTS_FILE,
    AVATAR_FILE,
    GAPS_FILE,
    SCRIPT_SENTENCES_FILE,
    SEGMENTS_FILE,
    SESSION_INFO_FILE,
    SHOW_SUMMARY_FILE,
    UTTERANCES_FILE,
)

if TYPE_CHECKING:
    from ai_live.core.config import Settings

GAP_P95_LIMIT_S = 1.5
GAP_MAX_S = 5.0
REHEARSAL_MIN_S = 1800.0
P95_MIN_SAMPLES = 20
# Picture or sound lost on screen: any of these fails criterion 4. `silence` is not here: the watchdog skips the stuck
# sentence and the gap it leaves is judged by criterion 3.
PICTURE_SOUND_ALERTS = ("frozen", "audio_missing", "host_closed", "fork_lost")
LOST_SENTENCE_STATUSES = ("tts_error", "render_error")
REPORT_FILE = "rehearsal_{show_id}"
CONDITION_KEYS = (
    "app_env",
    "reply_engine",
    "tts_provider",
    "avatar_mode",
    "scene_enabled",
    "customer_id",
    "avatar_id",
    "catalog_version",
    "power",
    "watchdog",
)


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SHORT = "short"  # criterion 4 only: shorter than 30 minutes, nothing else wrong


VERDICT_TEXT = {Verdict.PASS: "ĐẠT", Verdict.FAIL: "KHÔNG ĐẠT", Verdict.SHORT: "CHƯA ĐỦ 30 PHÚT"}


class SessionNotFound(LookupError):
    pass


class ShowNotFound(LookupError):
    pass


@dataclass(frozen=True)
class ShowLogs:
    """The lines of one show, already filtered out of the session files."""

    directory: Path
    session_id: str
    show_id: str
    session: dict[str, Any] | None
    summary: dict[str, Any] | None
    segments: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    sentences: list[dict[str, Any]]
    utterances: list[dict[str, Any]]
    avatar: list[dict[str, Any]]
    text_by_utterance: dict[str, str]
    bad_lines: int


@dataclass(frozen=True)
class RehearsalReport:
    show_id: str
    session_id: str
    conditions: dict[str, Any]
    started_at: str | None
    ended_at: str | None
    duration_s: float
    ended_normally: bool
    gaps: dict[str, Any]
    excluded_gaps: dict[str, Any]
    sentences: dict[str, int]
    alerts: dict[str, Any]
    modes: dict[str, float]
    render_fps: dict[str, Any] | None
    criterion_3: Verdict
    criterion_4: Verdict
    notes: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["criterion_3"] = self.criterion_3.value
        data["criterion_4"] = self.criterion_4.value
        data["notes"] = list(self.notes)
        return data

    @property
    def passed(self) -> bool:
        return self.criterion_3 is Verdict.PASS and self.criterion_4 is Verdict.PASS


# --- reading ---


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Lines that parse, and how many did not: a crash can leave the last line half written."""
    if not path.is_file():
        return [], 0
    rows: list[dict[str, Any]] = []
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


def resolve_session_dir(session: str, settings: Settings | None = None) -> Path:
    """A path to a session directory, or a session id under `SESSION_DATA_DIR`."""
    path = Path(session)
    if path.is_dir():
        return path
    if settings is None:
        from ai_live.core.config import get_settings

        settings = get_settings()
    candidate = Path(settings.session_data_dir) / session
    if candidate.is_dir():
        return candidate
    raise SessionNotFound(session)


def last_show_id(directory: Path) -> str | None:
    """The show of the last segment written; failing that the last gap, then the newest end-of-show summary."""
    for name in (SEGMENTS_FILE, GAPS_FILE):
        rows, _ = _read_jsonl(directory / name)
        for row in reversed(rows):
            if row.get("show_id"):
                return str(row["show_id"])
    pattern = SHOW_SUMMARY_FILE.format(show_id="*")
    summaries = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime) if directory.is_dir() else []
    for path in reversed(summaries):
        data = _read_json(path)
        if data and data.get("show_id"):
            return str(data["show_id"])
    return None


def load_show_logs(directory: Path, show_id: str) -> ShowLogs:
    if not directory.is_dir():
        raise SessionNotFound(str(directory))
    session = _read_json(directory / SESSION_INFO_FILE)
    summary = _read_json(directory / SHOW_SUMMARY_FILE.format(show_id=show_id))
    bad_lines = 0

    def rows(name: str) -> list[dict[str, Any]]:
        nonlocal bad_lines
        found, bad = _read_jsonl(directory / name)
        bad_lines += bad
        return found

    segments = [row for row in rows(SEGMENTS_FILE) if row.get("show_id") == show_id]
    gaps = [row for row in rows(GAPS_FILE) if row.get("show_id") == show_id]
    if not segments and not gaps and summary is None:
        raise ShowNotFound(show_id)
    alerts = [row for row in rows(ALERTS_FILE) if (row.get("alert") or {}).get("show_id") == show_id]
    all_sentences = rows(SCRIPT_SENTENCES_FILE)
    segment_ids = {row.get("segment_id") for row in segments}
    sentences = [row for row in all_sentences if row.get("segment_id") in segment_ids]
    sentence_ids = {row.get("utterance_id") for row in sentences}
    all_utterances = rows(UTTERANCES_FILE)
    utterances = [
        row for row in all_utterances if row.get("show_id") == show_id or row.get("utterance_id") in sentence_ids
    ]
    # Text of every utterance in the session: a gap can follow a comment reply as well as a script sentence.
    text_by_utterance: dict[str, str] = {}
    for row in all_utterances:
        said = row.get("sentences")
        if row.get("utterance_id") and isinstance(said, list):
            text_by_utterance[row["utterance_id"]] = " ".join(str(s) for s in said)
    for row in all_sentences:
        if row.get("utterance_id") and row.get("text"):
            text_by_utterance[row["utterance_id"]] = str(row["text"])
    session_id = str((session or {}).get("session_id") or (summary or {}).get("session_id") or directory.name)
    return ShowLogs(
        directory=directory,
        session_id=session_id,
        show_id=show_id,
        session=session,
        summary=summary,
        segments=segments,
        gaps=gaps,
        alerts=alerts,
        sentences=sentences,
        utterances=utterances,
        avatar=rows(AVATAR_FILE),
        text_by_utterance=text_by_utterance,
        bad_lines=bad_lines,
    )


# --- building ---


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _times(rows: Iterable[dict[str, Any]], *keys: str) -> list[datetime]:
    found = []
    for row in rows:
        for key in keys:
            at = _parse(row.get(key))
            if at is not None:
                found.append(at)
    return found


def _window(logs: ShowLogs) -> tuple[datetime | None, datetime | None]:
    summary = logs.summary or {}
    start = _parse(summary.get("started_at"))
    if start is None:
        seen = _times(logs.segments, "requested_at", "started_at") + _times(logs.gaps, "at")
        start = min(seen, default=None)
    end = _parse(summary.get("ended_at"))
    if end is None:
        # No summary: the app went down. The show ran at least until the last line that reached disk.
        seen = (
            _times(logs.segments, "requested_at", "started_at", "finished_at")
            + _times(logs.gaps, "at")
            + _times(logs.alerts, "at")
        )
        end = max(seen, default=None)
    return start, end


def _p95(values: list[float]) -> float | None:
    """Same quantile as the show summary from 20 samples; below that the longest gap stands in, which never flatters."""
    if not values:
        return None
    if len(values) < P95_MIN_SAMPLES:
        return round(max(values), 3)
    return round(min(statistics.quantiles(values, n=20)[18], max(values)), 3)


def _gap_sections(logs: ShowLogs) -> tuple[dict[str, Any], dict[str, Any]]:
    counted = [g for g in logs.gaps if g.get("counted")]
    values = [float(g.get("seconds") or 0.0) for g in counted]
    over = [
        {
            "at": g.get("at"),
            "seconds": float(g.get("seconds") or 0.0),
            "kind": g.get("kind"),
            "before_text": logs.text_by_utterance.get(str(g.get("from_id"))),
        }
        for g in counted
        if float(g.get("seconds") or 0.0) > GAP_MAX_S
    ]
    excluded: dict[str, dict[str, Any]] = {}
    for g in logs.gaps:
        if g.get("counted"):
            continue
        entry = excluded.setdefault(str(g.get("kind")), {"count": 0, "total_s": 0.0})
        entry["count"] += 1
        entry["total_s"] = round(entry["total_s"] + float(g.get("seconds") or 0.0), 3)
    gaps = {
        "counted": len(values),
        "median_s": round(statistics.median(values), 3) if values else None,
        "p95_s": _p95(values),
        "max_s": round(max(values), 3) if values else None,
        "over_5s": over,
    }
    return gaps, excluded


def _sentence_counts(logs: ShowLogs) -> dict[str, int]:
    if not logs.sentences and logs.summary:
        from_summary = logs.summary.get("sentences") or {}
        keys = ("spoken", *LOST_SENTENCE_STATUSES, "fallback_spoken", "verbatim_spoken")
        return {key: int(from_summary.get(key) or 0) for key in keys}
    statuses = Counter(str(row.get("status")) for row in logs.sentences)
    spoken_by_source = Counter(str(row.get("source")) for row in logs.sentences if row.get("status") == "spoken")
    counts = {key: statuses.get(key, 0) for key in ("spoken", *LOST_SENTENCE_STATUSES)}
    counts["fallback_spoken"] = spoken_by_source.get("fallback", 0)
    counts["verbatim_spoken"] = spoken_by_source.get("verbatim", 0)
    return counts


def _sentence_before(logs: ShowLogs, at: datetime | None) -> str | None:
    """The sentence on air when `at` came: the one started by the last gap before it."""
    if at is None:
        return None
    before = [g for g in logs.gaps if (t := _parse(g.get("at"))) is not None and t <= at]
    if not before:
        return None
    return logs.text_by_utterance.get(str(before[-1].get("to_id")))


def _alert_sections(logs: ShowLogs) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for row in logs.alerts:
        alert = row.get("alert") or {}
        alert_id = str(alert.get("alert_id"))
        entry = merged.setdefault(alert_id, {"auto_action": None})
        auto = alert.get("auto_action") or entry["auto_action"]
        entry.update({key: value for key, value in alert.items() if value is not None or key not in entry})
        entry["auto_action"] = auto
    listed = []
    by_kind: dict[str, dict[str, Any]] = {}
    for alert in merged.values():
        started = alert.get("started_at")
        seconds = alert.get("seconds")
        listed.append(
            {
                "alert_id": alert.get("alert_id"),
                "kind": alert.get("kind"),
                "level": alert.get("level"),
                "started_at": started,
                "ended_at": alert.get("ended_at"),
                "seconds": float(seconds) if seconds is not None else None,
                "text": alert.get("text"),
                "message": alert.get("message"),
                "auto_action": alert.get("auto_action"),
                "close_reason": alert.get("close_reason"),
                "before_text": _sentence_before(logs, _parse(started)),
            }
        )
        entry = by_kind.setdefault(str(alert.get("kind")), {"count": 0, "total_s": 0.0})
        entry["count"] += 1
        if seconds is not None:
            entry["total_s"] = round(entry["total_s"] + float(seconds), 3)
    listed.sort(key=lambda a: a["started_at"] or "")
    return {"by_kind": by_kind, "list": listed}


def _span_seconds(changes: list[tuple[datetime, bool]], start: datetime | None, end: datetime | None) -> float:
    """Seconds inside [start, end] where the last change said "on"; the state before the first change is "off"."""
    if start is None or end is None or end <= start:
        return 0.0
    total = 0.0
    on_since: datetime | None = None
    for at, on in sorted(changes, key=lambda c: c[0]):
        if on and on_since is None:
            on_since = at
        elif not on and on_since is not None:
            lo, hi = max(on_since, start), min(at, end)
            total += max(0.0, (hi - lo).total_seconds())
            on_since = None
    if on_since is not None:
        total += max(0.0, (end - max(on_since, start)).total_seconds())
    return round(total, 3)


def _modes(logs: ShowLogs, start: datetime | None, end: datetime | None) -> dict[str, float]:
    fallback = [
        (at, change.get("mode") == "fallback")
        for change in (logs.summary or {}).get("mode_changes") or []
        if (at := _parse(change.get("at"))) is not None
    ]
    still = [
        (at, row.get("active") == "static" and row.get("configured") == "livetalking")
        for row in logs.avatar
        if row.get("kind") == "mode" and (at := _parse(row.get("changed_at") or row.get("ts"))) is not None
    ]
    return {"fallback_s": _span_seconds(fallback, start, end), "static_s": _span_seconds(still, start, end)}


def _render_rows(logs: ShowLogs) -> list[dict[str, Any]]:
    """The show's `avatar.jsonl` `render` lines (005 contracts/events.md §4); older sessions only had the figures
    on `utterances.jsonl` lines, which are used when there is no render line."""
    rows = [row for row in logs.avatar if row.get("kind") == "render" and row.get("show_id") == logs.show_id]
    return rows or logs.utterances


def _render_fps(logs: ShowLogs) -> tuple[dict[str, Any] | None, str | None]:
    rows = _render_rows(logs)
    fps = [float(row["render_fps"]) for row in rows if row.get("render_fps") is not None]
    methods = Counter(str(row["mouth_method"]) for row in rows if row.get("mouth_method"))
    method = methods.most_common(1)[0][0] if methods else None
    if not fps:
        return None, method
    return {"p50": round(statistics.median(fps), 2), "min": round(min(fps), 2), "turns": len(fps)}, method


def build_report(logs: ShowLogs) -> RehearsalReport:
    notes: list[str] = []
    session = logs.session or {}
    if logs.session is None:
        notes.append("Không đọc được session.json: điều kiện chạy không đầy đủ.")
    fake_run = session.get("reply_engine") == "fake" or session.get("tts_provider") == "fake"
    render_fps, mouth_method = _render_fps(logs)
    conditions = {key: session.get(key) for key in CONDITION_KEYS}
    conditions["mouth_method"] = mouth_method
    conditions["fake_run"] = fake_run

    start, end = _window(logs)
    duration_s = round((end - start).total_seconds(), 3) if start and end and end > start else 0.0
    summary = logs.summary
    ended_normally = summary is not None and summary.get("ended_by") == "operator"
    gaps, excluded = _gap_sections(logs)
    sentences = _sentence_counts(logs)
    alerts = _alert_sections(logs)

    # Criterion 3: sentence gaps, pauses and injected faults left out (FR-014).
    if gaps["counted"] == 0:
        criterion_3 = Verdict.FAIL
        notes.append("Tiêu chí 3: không đủ dữ liệu, show không có khoảng lặng nào được đếm.")
    else:
        criterion_3 = Verdict.PASS if gaps["p95_s"] <= GAP_P95_LIMIT_S and not gaps["over_5s"] else Verdict.FAIL
        if gaps["counted"] < P95_MIN_SAMPLES:
            notes.append(
                f"Tiêu chí 3: ít hơn {P95_MIN_SAMPLES} khoảng lặng ({gaps['counted']}), p95 lấy bằng khoảng dài nhất."
            )
        if gaps["p95_s"] > GAP_P95_LIMIT_S:
            notes.append(f"Tiêu chí 3: p95 {gaps['p95_s']} s vượt {GAP_P95_LIMIT_S} s.")
        if gaps["over_5s"]:
            notes.append(f"Tiêu chí 3: {len(gaps['over_5s'])} khoảng lặng dài quá {GAP_MAX_S:g} s.")

    # Criterion 4: a broken show fails even when short, so a 10-minute show that froze does not read as merely short.
    problems_4 = []
    if summary is None:
        problems_4.append("không có tóm tắt cuối show (app tắt giữa chừng?)")
    elif not ended_normally:
        problems_4.append(f"show không do người vận hành kết thúc (ended_by={summary.get('ended_by')})")
    lost_view = [kind for kind in PICTURE_SOUND_ALERTS if kind in alerts["by_kind"]]
    if lost_view:
        problems_4.append("có cảnh báo " + ", ".join(lost_view))
    lost = [f"{sentences[s]} câu {s}" for s in LOST_SENTENCE_STATUSES if sentences.get(s)]
    if lost:
        problems_4.append("mất câu: " + ", ".join(lost))
    if problems_4:
        criterion_4 = Verdict.FAIL
        notes.append("Tiêu chí 4: " + "; ".join(problems_4) + ".")
    elif duration_s < REHEARSAL_MIN_S:
        criterion_4 = Verdict.SHORT
        notes.append(f"Tiêu chí 4: show dài {duration_s / 60:.1f} phút, cần ít nhất {REHEARSAL_MIN_S / 60:.0f} phút.")
    else:
        criterion_4 = Verdict.PASS

    if fake_run:
        notes.append(
            "Chạy với bộ trả lời giả, chưa phải tổng duyệt thật; "
            "tiêu chí 2 (câu trả lời đúng dữ liệu) không chấm ở đây."
        )
    if logs.bad_lines:
        notes.append(f"Bỏ qua {logs.bad_lines} dòng log hỏng (thường là dòng cuối khi app tắt đột ngột).")

    return RehearsalReport(
        show_id=logs.show_id,
        session_id=logs.session_id,
        conditions=conditions,
        started_at=start.isoformat() if start else None,
        ended_at=end.isoformat() if end else None,
        duration_s=duration_s,
        ended_normally=ended_normally,
        gaps=gaps,
        excluded_gaps=excluded,
        sentences=sentences,
        alerts=alerts,
        modes=_modes(logs, start, end),
        render_fps=render_fps,
        criterion_3=criterion_3,
        criterion_4=criterion_4,
        notes=tuple(notes),
    )


# --- output ---


def _s(value: float | None) -> str:
    return "—" if value is None else f"{value:g} s"


def _clock(value: str | None) -> str:
    at = _parse(value)
    return at.astimezone().strftime("%H:%M:%S") if at else "—"


def _md_cell(value: Any) -> str:
    return "—" if value in (None, "") else str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: RehearsalReport) -> str:
    c = report.conditions
    g = report.gaps
    lines = [
        f"# Báo cáo tổng duyệt · show `{report.show_id}`",
        "",
        f"- **Tiêu chí 3** (khoảng lặng p95 ≤ {GAP_P95_LIMIT_S:g} s, không khoảng nào > {GAP_MAX_S:g} s): "
        f"**{VERDICT_TEXT[report.criterion_3]}**",
        f"- **Tiêu chí 4** (≥ {REHEARSAL_MIN_S / 60:.0f} phút, kết thúc bình thường, không đứng hình, "
        "không mất tiếng): "
        f"**{VERDICT_TEXT[report.criterion_4]}**",
        "",
        "## Điều kiện chạy",
        "",
        f"- Phiên `{report.session_id}` · môi trường {_md_cell(c.get('app_env'))}",
        f"- Bộ trả lời: {_md_cell(c.get('reply_engine'))} · giọng: {_md_cell(c.get('tts_provider'))}"
        + (" · **chạy giả**" if c.get("fake_run") else ""),
        f"- Nhân vật: {_md_cell(c.get('avatar_mode'))} · cách tạo miệng: {_md_cell(c.get('mouth_method'))} · "
        f"cảnh live: {_md_cell(c.get('scene_enabled'))}",
        f"- Khách / nhân vật / bản nội dung: {_md_cell(c.get('customer_id'))} / {_md_cell(c.get('avatar_id'))} / "
        f"{_md_cell(c.get('catalog_version'))}",
        f"- Nguồn điện lúc mở app: {_md_cell(c.get('power'))}",
        "",
        "## Số liệu",
        "",
        "| Mục | Giá trị |",
        "|---|---|",
        f"| Bắt đầu → kết thúc | {_clock(report.started_at)} → {_clock(report.ended_at)} |",
        f"| Thời lượng | {report.duration_s / 60:.1f} phút ({report.duration_s:g} s) |",
        f"| Kết thúc bình thường | {'có' if report.ended_normally else 'không'} |",
        f"| Khoảng lặng được đếm | {g['counted']} |",
        f"| Khoảng lặng trung vị / p95 / dài nhất | {_s(g['median_s'])} / {_s(g['p95_s'])} / {_s(g['max_s'])} |",
        f"| Khoảng lặng > {GAP_MAX_S:g} s | {len(g['over_5s'])} |",
        "| Không tính (tạm dừng, lỗi giả lập, bình luận) | "
        + (
            ", ".join(f"{kind}: {v['count']} lần, {v['total_s']:g} s" for kind, v in report.excluded_gaps.items())
            or "—"
        )
        + " |",
        "| Câu đã nói / lỗi giọng / lỗi hình / câu dự phòng | "
        f"{report.sentences.get('spoken', 0)} / {report.sentences.get('tts_error', 0)} / "
        f"{report.sentences.get('render_error', 0)} / {report.sentences.get('fallback_spoken', 0)} |",
        f"| Thời gian ở chế độ dự phòng kịch bản | {_s(report.modes['fallback_s'])} |",
        *(
            [f"| Câu đọc nguyên văn (video dự phòng) | {report.sentences['verbatim_spoken']} |"]
            if report.sentences.get("verbatim_spoken")
            else []
        ),
        f"| Thời gian rơi về ảnh tĩnh | {_s(report.modes['static_s'])} |",
    ]
    if report.render_fps:
        fps = report.render_fps
        lines.append(f"| FPS nhép miệng p50 / thấp nhất ({fps['turns']} lượt) | {fps['p50']:g} / {fps['min']:g} |")
    lines += ["", f"## Khoảng lặng quá {GAP_MAX_S:g} giây", ""]
    if g["over_5s"]:
        lines += ["| Lúc | Dài | Loại | Câu liền trước |", "|---|---|---|---|"]
        lines += [
            f"| {_clock(o['at'])} | {o['seconds']:g} s | {o['kind']} | {_md_cell(o['before_text'])} |"
            for o in g["over_5s"]
        ]
    else:
        lines.append("Không có.")
    lines += ["", "## Cảnh báo", ""]
    if report.alerts["list"]:
        lines += ["| Lúc | Loại | Mức | Kéo dài | Tự xử lý | Câu liền trước |", "|---|---|---|---|---|---|"]
        lines += [
            f"| {_clock(a['started_at'])} | {a['kind']} | {_md_cell(a['level'])} | "
            f"{_s(a['seconds']) if a['seconds'] is not None else 'chưa đóng'} | {_md_cell(a['auto_action'])} | "
            f"{_md_cell(a['text'] or a['before_text'])} |"
            for a in report.alerts["list"]
        ]
    else:
        lines.append("Không có.")
    lines += ["", "## Ghi chú", ""]
    lines += [f"- {note}" for note in report.notes] or ["- Không có."]
    return "\n".join(lines) + "\n"


def write_report(report: RehearsalReport, directory: Path) -> tuple[Path, Path]:
    base = REPORT_FILE.format(show_id=report.show_id)
    md_path = directory / f"{base}.md"
    json_path = directory / f"{base}.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def cli_report(
    session: str, *, show_id: str | None = None, as_json: bool = False, settings: Settings | None = None
) -> int:
    """Exit 0 when criteria 3 and 4 both pass, 1 when not, 2 when the session or show is not there."""
    try:
        directory = resolve_session_dir(session, settings)
    except SessionNotFound:
        print(f"LỖI  Không tìm thấy phiên {session} (thư mục phiên hoặc session_id trong SESSION_DATA_DIR).")
        return 2
    chosen = show_id or last_show_id(directory)
    if chosen is None:
        print(f"LỖI  Phiên {directory.name} chưa có show nào trong log.")
        return 2
    try:
        logs = load_show_logs(directory, chosen)
    except ShowNotFound:
        print(f"LỖI  Không tìm thấy show {chosen} trong phiên {directory.name}.")
        return 2
    report = build_report(logs)
    md_path, json_path = write_report(report, directory)
    if as_json:
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
        print(f"Đã ghi {md_path} và {json_path.name}")
    return 0 if report.passed else 1
