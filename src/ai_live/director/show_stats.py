"""Running statistics of one scripted show (004; FR-022, FR-023, SC-002, SC-004, SC-005, data-model §9), plus the
`llm_chain` section of the model chain (008 FR-018, data-model §7).

Pure: no I/O. `SessionLog` writes `summary()` to `show_summary_<show_id>.json`. Percentiles come from
`director/latency.step_stats` (looked up on the module at call time), so the show and the 001 latency summary use
one implementation of p95.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from itertools import combinations
from typing import TYPE_CHECKING, Any, Literal

from ai_live.core.models import (
    P95_MIN_SAMPLES,
    GapKind,
    ScriptSentence,
    Segment,
    SegmentOrigin,
    SegmentStatus,
    SentenceGap,
    SentenceStatus,
    ShowMode,
    ShowSummary,
)
from ai_live.director import latency
from ai_live.products.models import ProductCatalog

if TYPE_CHECKING:
    from ai_live.brain.chain_engine import TurnRecord

COVERAGE_WINDOW_S = 600.0
# Silences the show itself is responsible for (SC-002); comment, paused and fault gaps are reported apart.
COUNTED_GAP_KINDS: frozenset[GapKind] = frozenset({GapKind.SCRIPT, GapKind.SEGMENT_BOUNDARY, GapKind.ERROR})
# Segments that actually played, so they count for the primary share and the secondary coverage.
_PLAYED = frozenset({SegmentStatus.DONE, SegmentStatus.SKIPPED})
# Drops that happen before the repeat filter, so those sentences never reached it.
_BEFORE_DEDUP_DROPS = frozenset({"empty_after_clean", "sentence_count_exceeded"})


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


class ShowStats:
    def __init__(
        self,
        show_id: str,
        session_id: str,
        catalog: ProductCatalog | None = None,
        *,
        window_s: float = COVERAGE_WINDOW_S,
        min_samples: int = P95_MIN_SAMPLES,
        llm_entries: Mapping[str, str] | None = None,
    ) -> None:
        """`llm_entries`: label -> model of each `LLM_CHAIN` entry, in chain order, when the show runs on the chain;
        `None` otherwise, which makes the summary's `llm_chain` null (data-model §7)."""
        self.show_id = show_id
        self.session_id = session_id
        self._catalog = catalog
        self._window_s = window_s
        self._min_samples = min_samples
        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None
        self._ended_by: Literal["operator", "shutdown"] = "shutdown"
        self._first_sentence_s: float | None = None
        self._mode_changes: list[dict[str, Any]] = []
        self._segments: list[Segment] = []
        self._segment_times: list[tuple[datetime | None, str | None, SegmentStatus]] = []
        self._sentence_counts: Counter[str] = Counter()
        self._fallback_spoken = 0
        self._reached_dedup = 0
        self._duplicate_drops = 0
        self._spoken_script_forms: list[str] = []
        self._spoken_by_segment: dict[str, list[str]] = {}
        self._gaps: list[SentenceGap] = []
        self._reply_latencies: list[float] = []
        self._llm = _ChainCounts(llm_entries) if llm_entries is not None else None

    # ---------- recording ----------

    def set_catalog(self, catalog: ProductCatalog) -> None:
        """Secondary coverage follows the current catalog's secondaries."""
        self._catalog = catalog

    def mark_started(self, at: datetime) -> None:
        if self._started_at is None:
            self._started_at = at

    def mark_ended(self, at: datetime, by: Literal["operator", "shutdown"]) -> None:
        self._ended_at = at
        self._ended_by = by

    def record_first_sentence(self, seconds: float) -> None:
        if self._first_sentence_s is None:
            self._first_sentence_s = round(seconds, 3)

    def record_mode_change(self, mode: ShowMode, at: datetime) -> None:
        self._mode_changes.append({"at": at.isoformat(), "mode": mode.value})

    def record_segment(self, segment: Segment) -> None:
        """Called once, when the segment reaches its final status (after its sentences were recorded)."""
        self._segments.append(segment)
        at = segment.started_at or segment.requested_at
        self._segment_times.append((at, segment.product_id, segment.status))

    def record_sentence(self, sentence: ScriptSentence, source: Literal["script", "fallback"]) -> None:
        status = sentence.status
        self._sentence_counts[status.value] += 1
        if status is SentenceStatus.SPOKEN:
            if source == "fallback":
                self._fallback_spoken += 1
            else:
                self._spoken_script_forms.append(sentence.word_form)
                self._spoken_by_segment.setdefault(sentence.segment_id, []).append(sentence.word_form)
        if source != "script" or status is SentenceStatus.BLOCKED:
            return
        if status is SentenceStatus.DROPPED and sentence.drop_reason in _BEFORE_DEDUP_DROPS:
            return
        self._reached_dedup += 1
        if status is SentenceStatus.DROPPED and sentence.drop_reason == "duplicate":
            self._duplicate_drops += 1

    def record_gap(self, gap: SentenceGap) -> None:
        self._gaps.append(gap)

    def record_reply_latency(self, seconds: float) -> None:
        self._reply_latencies.append(seconds)

    def record_llm_turn(self, record: TurnRecord) -> None:
        """One finished chain turn, segment or comment reply (the engine's turn observer). Ignored off the chain."""
        if self._llm is not None:
            self._llm.record(record)

    # ---------- results ----------

    def _gap_stats(self, values: list[float]) -> dict[str, Any]:
        stats = latency.step_stats(values, self._min_samples)
        return {
            "n": stats.count,
            "median_s": stats.median,
            "p95_s": stats.p95,
            "max_s": round(max(values), 3) if values else None,
        }

    def _counted_gaps(self) -> list[float]:
        return [g.seconds for g in self._gaps if g.kind in COUNTED_GAP_KINDS]

    def _primary_share(self) -> float | None:
        primary = None
        if self._catalog is not None:
            primary = next((p.id for p in self._catalog.products if p.is_primary), None)
        played = [s for s in self._segments if s.product_id is not None and s.status in _PLAYED]
        return _rate(sum(s.product_id == primary for s in played), len(played))

    def _segments_section(self) -> dict[str, Any]:
        return {
            "total": len(self._segments),
            "by_product": dict(Counter(s.product_id for s in self._segments if s.product_id is not None)),
            "by_topic": dict(Counter(s.topic.value for s in self._segments)),
            "by_status": dict(Counter(s.status.value for s in self._segments)),
            "primary_share": self._primary_share(),
        }

    def _coverage(self) -> list[dict[str, Any]]:
        start = self._started_at
        if start is None:
            return []
        end = self._ended_at
        if end is None:
            times = [at for at, _, _ in self._segment_times if at is not None]
            end = max(times, default=start)
        total_s = (end - start).total_seconds()
        secondaries: list[str] = []
        if self._catalog is not None:
            secondaries = sorted(p.id for p in self._catalog.products if not p.is_primary)
        windows: list[dict[str, Any]] = []
        window_start = 0.0
        while window_start < total_s:
            window_end = min(window_start + self._window_s, total_s)
            seen = {
                pid
                for at, pid, status in self._segment_times
                if at is not None
                and status in _PLAYED
                and window_start <= (at - start).total_seconds() < window_start + self._window_s
            }
            windows.append(
                {
                    "window_start_s": int(window_start) if window_start.is_integer() else window_start,
                    "window_end_s": round(window_end, 3),
                    "missing_products": [pid for pid in secondaries if pid not in seen],
                }
            )
            window_start += self._window_s
        return windows

    def _identical_segments(self) -> int:
        forms = [
            tuple(self._spoken_by_segment[s.segment_id])
            for s in self._segments
            if s.origin is not SegmentOrigin.FALLBACK and self._spoken_by_segment.get(s.segment_id)
        ]
        return sum(a == b for a, b in combinations(forms, 2))

    def _duplicates(self) -> dict[str, Any]:
        spoken = self._spoken_script_forms
        repeats = len(spoken) - len(set(spoken))
        return {
            "before_filter_rate": _rate(self._duplicate_drops, self._reached_dedup),
            "spoken_rate": _rate(repeats, len(spoken)),
            "identical_segments": self._identical_segments(),
        }

    def summary(self) -> ShowSummary:
        by_kind: dict[str, list[float]] = {}
        for gap in self._gaps:
            by_kind.setdefault(gap.kind.value, []).append(gap.seconds)
        counts = self._sentence_counts
        reply = latency.step_stats(self._reply_latencies, self._min_samples)
        return ShowSummary(
            show_id=self.show_id,
            session_id=self.session_id,
            started_at=self._started_at,
            ended_at=self._ended_at,
            ended_by=self._ended_by,
            show_first_sentence_s=self._first_sentence_s,
            segments=self._segments_section(),
            secondary_coverage=self._coverage(),
            sentences={
                "spoken": counts[SentenceStatus.SPOKEN.value],
                "blocked": counts[SentenceStatus.BLOCKED.value],
                "dropped": counts[SentenceStatus.DROPPED.value],
                "tts_error": counts[SentenceStatus.TTS_ERROR.value],
                "render_error": counts[SentenceStatus.RENDER_ERROR.value],
                "interrupted": counts[SentenceStatus.INTERRUPTED.value],
                "fallback_spoken": self._fallback_spoken,
            },
            gaps={
                "counted": self._gap_stats(self._counted_gaps()),
                "by_kind": {kind: self._gap_stats(values) for kind, values in by_kind.items()},
            },
            duplicates=self._duplicates(),
            mode_changes=list(self._mode_changes),
            comments={
                "answered": len(self._reply_latencies),
                "reply_latency": {"n": reply.count, "p95_s": reply.p95},
            },
            llm_chain=self._llm.section() if self._llm is not None else None,
        )

    def snapshot_stats(self) -> dict[str, Any]:
        """`ShowSnapshot.stats` of `GET /api/show` and the `show_stats` event (contracts/api.md)."""
        counted = self._gap_stats(self._counted_gaps())
        return {
            "segments": len(self._segments),
            "gap_p95_s": counted["p95_s"],
            "gap_max_s": counted["max_s"],
            "primary_share": self._primary_share(),
        }


class _ChainCounts:
    """Per-entry counts of the model chain for the show summary (data-model §7). No request or token count (FR-018).

    `segments` / `replies` count turns the engine finished (`ok`): a cut turn is a failure, a cancelled one (skip,
    stop) neither. A switch is a failed try followed by a try of a later entry, as the engine logs `llm_switch`;
    skipping a resting entry is neither a failure nor a switch.
    """

    def __init__(self, entries: Mapping[str, str]) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        for label, model in entries.items():
            self._entry(label, model)
        self._switches: Counter[str] = Counter()
        self._exhausted = 0

    def _entry(self, label: str, model: str | None) -> dict[str, Any]:
        entry = self._entries.get(label)
        if entry is None:
            entry = self._entries[label] = {"model": model, "segments": 0, "replies": 0, "failures": Counter()}
        elif entry["model"] is None and model is not None:
            entry["model"] = model
        return entry

    def record(self, record: TurnRecord) -> None:
        failed_before: str | None = None
        for attempt in record.attempts:
            if attempt.outcome == "skipped":
                continue
            if failed_before is not None:
                self._switches[failed_before] += 1
                failed_before = None
            if attempt.outcome == "failed" and attempt.reason is not None:
                reason = str(attempt.reason)
                model = record.model if attempt.label == record.label else None
                self._entry(attempt.label, model)["failures"][reason] += 1
                failed_before = reason
        if record.outcome == "exhausted":
            self._exhausted += 1
        elif record.outcome == "ok" and record.label is not None:
            entry = self._entry(record.label, record.model)
            entry["segments" if record.kind == "segment" else "replies"] += 1

    def section(self) -> dict[str, Any]:
        return {
            "entries": {
                label: {**entry, "failures": dict(entry["failures"])} for label, entry in self._entries.items()
            },
            "switches": dict(self._switches),
            "exhausted": self._exhausted,
        }
