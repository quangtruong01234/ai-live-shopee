"""Per-turn latency milestones and the session summary (US3; FR-018, FR-019, data-model.md §4, research R12).

Only `completed` turns enter the step statistics: an error or a skip cuts the turn short, and counting it
would make the pipeline look faster than it is (US3 #3). They are counted separately instead.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai_live.core.models import (
    IDLE_QUEUE_WAIT_S,
    P95_MIN_SAMPLES,
    LatencySummary,
    Milestone,
    RenderTurnStats,
    StepStats,
    TurnOutcome,
    Utterance,
)

M = Milestone

NOT_ENOUGH_SAMPLES = "chưa đủ mẫu"

# Step name -> (from milestone, to milestone). Order is the display order on the control page.
STEPS: dict[str, tuple[Milestone, Milestone]] = {
    "received_to_first_sentence": (M.COMMENT_RECEIVED, M.LLM_FIRST_SENTENCE),
    "first_sentence_to_tts_first_chunk": (M.LLM_FIRST_SENTENCE, M.TTS_FIRST_CHUNK),
    "tts_first_chunk_to_first_frame": (M.TTS_FIRST_CHUNK, M.AVATAR_FIRST_FRAME),
    "queue_wait": (M.COMMENT_RECEIVED, M.TURN_STARTED),
    "total": (M.COMMENT_RECEIVED, M.AVATAR_FIRST_FRAME),
}
STEP_NAMES: tuple[str, ...] = tuple(STEPS)

# Rows of `LatencySummary.turns`: the `latency` event re-sends the summary after every turn, so the per-turn list
# stays short while the step and rate statistics still cover the whole session.
RECENT_TURNS = 20


@dataclass(frozen=True)
class TurnLatency:
    """What the tracker keeps of a finished turn: outcome, step durations (seconds) and, for a lip-sync turn,
    the render figures (005 data-model §5; None on a static turn).
    """

    utterance_id: str
    outcome: TurnOutcome
    durations: dict[str, float] = field(default_factory=dict)
    render_fps: float | None = None
    infer_fps: float | None = None
    clips_used: list[str] | None = None

    def to_row(self) -> dict[str, Any]:
        """One row of the latency table (005 contracts/api.md §2); render columns are null on a static turn."""
        total = self.durations.get("total")
        return {
            "utterance_id": self.utterance_id,
            "outcome": self.outcome.value,
            "total_s": round(total, 3) if total is not None else None,
            "render_fps": round(self.render_fps, 2) if self.render_fps is not None else None,
            "infer_fps": round(self.infer_fps, 2) if self.infer_fps is not None else None,
            "clips_used": list(self.clips_used) if self.clips_used is not None else None,
        }


def step_durations(marks: Mapping[Milestone, float]) -> dict[str, float]:
    """Duration of every step whose two milestones are both present."""
    return {name: marks[end] - marks[start] for name, (start, end) in STEPS.items() if start in marks and end in marks}


def step_stats(values: list[float], min_samples: int = P95_MIN_SAMPLES) -> StepStats:
    if not values:
        return StepStats(count=0, median=None, p95=None, note=NOT_ENOUGH_SAMPLES)
    median = round(statistics.median(values), 3)
    if len(values) < min_samples:
        return StepStats(count=len(values), median=median, p95=None, note=NOT_ENOUGH_SAMPLES)
    p95 = round(statistics.quantiles(values, n=20)[18], 3)
    return StepStats(count=len(values), median=median, p95=p95)


class LatencyTracker:
    """In-memory latency record of the current session.

    Turns are small (a few floats each); a 15-hour live has a few thousand turns, so nothing is evicted and the
    end-of-session summary covers the whole session.
    """

    def __init__(self, *, idle_threshold_s: float = IDLE_QUEUE_WAIT_S, min_samples: int = P95_MIN_SAMPLES) -> None:
        self.idle_threshold_s = idle_threshold_s
        self.min_samples = min_samples
        self._open: dict[str, dict[Milestone, float]] = {}
        self._turns: list[TurnLatency] = []

    @property
    def turns(self) -> list[TurnLatency]:
        return list(self._turns)

    def mark(self, utterance_id: str, milestone: Milestone, at: float) -> None:
        """Record a milestone; only the first value counts (a milestone is when a step *starts*)."""
        self._open.setdefault(utterance_id, {}).setdefault(milestone, at)

    def finish(
        self, utterance_id: str, outcome: TurnOutcome, *, render: RenderTurnStats | None = None
    ) -> TurnLatency | None:
        """Close a turn. `in_progress` is not a final outcome, so such a turn is dropped, not counted."""
        marks = self._open.pop(utterance_id, {})
        if outcome is TurnOutcome.IN_PROGRESS:
            return None
        turn = TurnLatency(
            utterance_id,
            outcome,
            step_durations(marks),
            render_fps=render.render_fps if render else None,
            infer_fps=render.infer_fps if render else None,
            clips_used=list(render.clips_used) if render else None,
        )
        self._turns.append(turn)
        return turn

    def record(self, utterance: Utterance, *, render: RenderTurnStats | None = None) -> TurnLatency | None:
        """Close a turn from a finished `Utterance` (its marks and outcome) and the renderer's stats, if any.

        A scripted sentence has no `comment_received`, so it is not a reply turn: it is left out (it goes to
        `ShowStats` instead) and `latency_summary.json` keeps describing comment replies only (004 research R2).
        """
        if utterance.segment_id is not None:
            self._open.pop(utterance.utterance_id, None)
            return None
        for milestone, at in utterance.marks.items():
            self.mark(utterance.utterance_id, milestone, at)
        return self.finish(utterance.utterance_id, utterance.outcome, render=render)

    def summary(self, *, idle_only: bool = False) -> LatencySummary:
        completed = [t for t in self._turns if t.outcome is TurnOutcome.COMPLETED]
        idle = [t for t in completed if self._is_idle(t)]
        idle_steps = self._stats(idle)
        return LatencySummary(
            steps=idle_steps if idle_only else self._stats(completed),
            idle_steps=idle_steps,
            completed=len(completed),
            errors=sum(t.outcome is TurnOutcome.ERROR for t in self._turns),
            skipped=sum(t.outcome is TurnOutcome.SKIPPED for t in self._turns),
            idle_only=idle_only,
            idle_completed=len(idle),
            idle_threshold_s=self.idle_threshold_s,
            min_samples=self.min_samples,
            render_fps=step_stats([t.render_fps for t in completed if t.render_fps is not None], self.min_samples),
            infer_fps=step_stats([t.infer_fps for t in completed if t.infer_fps is not None], self.min_samples),
            turns=[t.to_row() for t in reversed(self._turns[-RECENT_TURNS:])],
        )

    def _is_idle(self, turn: TurnLatency) -> bool:
        wait = turn.durations.get("queue_wait")
        return wait is not None and wait < self.idle_threshold_s

    def _stats(self, turns: list[TurnLatency]) -> dict[str, StepStats]:
        return {
            name: step_stats([t.durations[name] for t in turns if name in t.durations], self.min_samples)
            for name in STEP_NAMES
        }
