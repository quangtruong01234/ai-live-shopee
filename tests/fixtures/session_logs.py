"""007 T036: writes the session log files of one scripted show, shaped like `SessionLog` writes them.

The rehearsal report reads only these files (contracts/files.md), so each SC-005 case is a few parameters: show length,
the gaps between sentences, alerts, lip-sync turns, whether the app wrote the end-of-show summary.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SESSION_ID = "20261113-100000"
SHOW_ID = "show-rehearsal-1"
START = datetime(2026, 11, 13, 3, 0, 0, tzinfo=UTC)
THIRTY_MINUTES_S = 1830.0
NORMAL_GAPS: tuple[tuple[str, float], ...] = (("script", 0.4),) * 40


@dataclass(frozen=True)
class ShowLog:
    directory: Path
    session_id: str
    show_id: str

    def text_of(self, index: int) -> str:
        return sentence_text(index)


@dataclass(frozen=True)
class AlertSpec:
    kind: str
    level: str
    at_s: float  # from the show start
    seconds: float | None  # None: never closed (the app went down first)
    text: str | None = None
    auto_action: str | None = None


def sentence_text(index: int) -> str:
    return f"Câu {index} giới thiệu kem chống nắng."


def _iso(offset_s: float) -> str:
    return (START + timedelta(seconds=offset_s)).isoformat().replace("+00:00", "Z")


def _jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    # Appends, like `SessionLog`: a second call with another show_id makes a session with two shows.
    if rows:
        with path.open("a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def write_show_logs(
    base: Path,
    *,
    duration_s: float = THIRTY_MINUTES_S,
    gaps: Sequence[tuple[str, float]] = NORMAL_GAPS,
    summary: bool = True,
    ended_by: str = "operator",
    reply_engine: str = "chain",
    tts_provider: str = "vieneu",
    avatar_mode: str = "livetalking",
    power: str | None = "ac",
    alerts: Sequence[AlertSpec] = (),
    render_fps: Sequence[float] = (25.0, 24.6, 25.3),
    mouth_method: str | None = "w2l",
    render_in: str = "avatar",
    sentence_source: str = "script",
    sentence_errors: Sequence[str] = (),
    static_spans: Sequence[tuple[float, float]] = (),
    fallback_spans: Sequence[tuple[float, float]] = (),
    session_id: str = SESSION_ID,
    show_id: str = SHOW_ID,
) -> ShowLog:
    """One show of `duration_s`; gap `i` sits before sentence `i + 1`, the sentences spread evenly over the show.

    Without `summary` the log ends like a crash: no `show_summary_<show>.json`, the last line is the last gap.
    `render_in`: where the lip-sync figures sit, `avatar` (`render` lines, 005 contracts/events.md §4) or
    `utterances` (sessions written before 2026-11-17).
    """
    directory = base / session_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "session.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "started_at": _iso(-5.0),
                "app_env": "demo",
                "reply_engine": reply_engine,
                "tts_provider": tts_provider,
                "avatar_mode": avatar_mode,
                "scene_enabled": True,
                "customer_id": "demo_customer_01",
                "avatar_id": "demo_host_01",
                "catalog_version": "2a1a52d5ae99",
                "power": power,
                "watchdog": {"enabled": True, "silence_s": 5.0, "frozen_s": 3.0, "autoskip_s": 15.0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    segment_id = f"seg-{show_id}"
    uid = [f"{show_id}-u{i}" for i in range(len(gaps) + 1)]
    count = len(gaps) + 1
    step = duration_s / (count + 1)
    played = [step * (i + 1) for i in range(count)]
    sentences = []
    for i in range(count):
        status = sentence_errors[i] if i < len(sentence_errors) else "spoken"
        sentences.append(
            {
                "utterance_id": uid[i],
                "segment_id": segment_id,
                "seq": i,
                "source": sentence_source,
                "text": sentence_text(i),
                "raw_text": sentence_text(i),
                "status": status,
                "marks": {},
                "played_at": round(played[i], 3) if status == "spoken" else None,
            }
        )
    _jsonl(directory / "script_sentences.jsonl", sentences)
    _jsonl(
        directory / "gaps.jsonl",
        [
            {
                "show_id": show_id,
                "kind": kind,
                "counted": kind in {"script", "segment_boundary", "error"},
                "seconds": seconds,
                "from_id": uid[i],
                "to_id": uid[i + 1],
                "at": _iso(played[i + 1]),
            }
            for i, (kind, seconds) in enumerate(gaps)
        ],
    )
    end = duration_s if summary else played[-1]
    _jsonl(
        directory / "segments.jsonl",
        [
            {
                "segment_id": segment_id,
                "show_id": show_id,
                "index": 0,
                "status": "done",
                "requested_at": _iso(0.0),
                "started_at": _iso(0.05),
                "finished_at": _iso(end),
            }
        ],
    )

    alert_rows = []
    for n, spec in enumerate(alerts):
        body = {
            "alert_id": f"{show_id}-a{n}",
            "kind": spec.kind,
            "level": spec.level,
            "show_id": show_id,
            "started_at": _iso(spec.at_s),
            "text": spec.text,
            "message": f"Cảnh báo {spec.kind}",
            "action": "Làm theo hướng dẫn",
        }
        alert_rows.append({"event": "open", "at": _iso(spec.at_s), "alert": {**body, "state": "open"}})
        if spec.auto_action is not None:
            alert_rows.append(
                {"event": "auto_skip", "at": _iso(spec.at_s + 1), "alert": {**body, "auto_action": spec.auto_action}}
            )
        if spec.seconds is not None:
            closed = {**body, "ended_at": _iso(spec.at_s + spec.seconds), "seconds": spec.seconds, "state": "closed"}
            alert_rows.append({"event": "close", "at": _iso(spec.at_s + spec.seconds), "alert": closed})
    alert_rows.sort(key=lambda row: row["at"])
    _jsonl(directory / "alerts.jsonl", alert_rows)

    _jsonl(
        directory / "utterances.jsonl",
        [
            {"utterance_id": uid[i], "show_id": show_id, "render_fps": fps, "mouth_method": mouth_method}
            for i, fps in enumerate(render_fps[: len(uid)])
        ]
        if avatar_mode == "livetalking" and render_in == "utterances"
        else [{"utterance_id": u, "show_id": show_id} for u in uid],
    )
    avatar_rows = []
    if avatar_mode == "livetalking" and render_in == "avatar":
        avatar_rows += [
            {
                "ts": _iso(played[i]),
                "kind": "render",
                "utterance_id": uid[i],
                "show_id": show_id,
                "frames": 50,
                "render_fps": fps,
                "infer_fps": fps + 5,
                "clips_used": ["talk_01"],
                "scene_ms": 1.2,
                "mouth_method": mouth_method,
            }
            for i, fps in enumerate(render_fps[: len(uid)])
        ]
    for at_s, seconds in static_spans:
        for when, active in ((at_s, "static"), (at_s + seconds, "livetalking")):
            avatar_rows.append(
                {
                    "ts": _iso(when),
                    "kind": "mode",
                    "configured": "livetalking",
                    "active": active,
                    "changed_at": _iso(when),
                }
            )
    _jsonl(directory / "avatar.jsonl", avatar_rows)

    if summary:
        mode_changes = []
        for at_s, seconds in fallback_spans:
            mode_changes += [{"at": _iso(at_s), "mode": "fallback"}, {"at": _iso(at_s + seconds), "mode": "normal"}]
        statuses = [s["status"] for s in sentences]
        (directory / f"show_summary_{show_id}.json").write_text(
            json.dumps(
                {
                    "show_id": show_id,
                    "session_id": session_id,
                    "started_at": START.isoformat(),
                    "ended_at": (START + timedelta(seconds=duration_s)).isoformat(),
                    "ended_by": ended_by,
                    "mode_changes": mode_changes,
                    "sentences": {
                        "spoken": statuses.count("spoken"),
                        "tts_error": statuses.count("tts_error"),
                        "render_error": statuses.count("render_error"),
                        "fallback_spoken": 0,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return ShowLog(directory, session_id, show_id)
