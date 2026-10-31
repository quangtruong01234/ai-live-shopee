"""Shared pipeline models (data-model.md §1, §3, §4)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any


@dataclass(frozen=True)
class Comment:
    """Immutable: status and priority live on `QueuedComment`. In logs/JSON `id` is named `comment_id`."""

    id: str
    source: str
    author: str
    text: str
    received_at: float  # time.monotonic(); this is the comment_received milestone
    platform_ts: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Priority(IntEnum):
    """A smaller number is a higher priority, so a `(priority, seq)` heap pops in the right order."""

    HIGH = 0
    MEDIUM = 1
    LOW = 2


class DropReason(StrEnum):
    EMPTY = "empty"
    LINK = "link"
    PROFANITY = "profanity"
    DUPLICATE = "duplicate"
    STALE = "stale"
    QUEUE_FULL = "queue_full"

    @property
    def label(self) -> str:
        return _DROP_LABELS[self]


_DROP_LABELS = {
    DropReason.EMPTY: "không có nội dung",
    DropReason.LINK: "chứa link",
    DropReason.PROFANITY: "từ ngữ không phù hợp",
    DropReason.DUPLICATE: "trùng",
    DropReason.STALE: "quá cũ",
    DropReason.QUEUE_FULL: "hàng đợi đầy",
}


class CommentStatus(StrEnum):
    WAITING = "waiting"
    ANSWERING = "answering"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    ERROR = "error"
    DROPPED = "dropped"


@dataclass
class QueuedComment:
    comment: Comment
    priority: Priority
    seq: int
    status: CommentStatus = CommentStatus.WAITING
    drop_reason: DropReason | None = None

    def to_json(self) -> dict[str, Any]:
        """Item shape of `state.queue` and `queue_changed.queue` (contracts/events.md)."""
        return {
            "comment_id": self.comment.id,
            "author": self.comment.author,
            "text": self.comment.text,
            "priority": self.priority.name,
            "status": self.status.value,
        }


class TurnOutcome(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ERROR = "error"


class ErrorStep(StrEnum):
    LLM = "llm"
    GUARD = "guard"  # only when the guard itself raises; a blocked sentence still leaves the turn completed
    TTS = "tts"
    RENDER = "render"


class Milestone(StrEnum):
    COMMENT_RECEIVED = "comment_received"
    TURN_STARTED = "turn_started"
    LLM_FIRST_SENTENCE = "llm_first_sentence"
    TTS_FIRST_CHUNK = "tts_first_chunk"
    AVATAR_FIRST_FRAME = "avatar_first_frame"


# The four milestones required by Article VIII; turn_started is extra, to separate queue wait time.
REQUIRED_MILESTONES: tuple[Milestone, ...] = (
    Milestone.COMMENT_RECEIVED,
    Milestone.LLM_FIRST_SENTENCE,
    Milestone.TTS_FIRST_CHUNK,
    Milestone.AVATAR_FIRST_FRAME,
)


class GuardReason(StrEnum):
    FORBIDDEN_CLAIM = "forbidden_claim"
    UNKNOWN_AMOUNT = "unknown_amount"


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    reason: GuardReason | None = None
    detail: str | None = None

    @classmethod
    def passed(cls) -> GuardResult:
        return cls(ok=True)

    @classmethod
    def blocked(cls, reason: GuardReason, detail: str | None = None) -> GuardResult:
        return cls(ok=False, reason=reason, detail=detail)


@dataclass
class Utterance:
    utterance_id: str
    comment_id: str
    catalog_version: str
    sentences: list[str] = field(default_factory=list)
    marks: dict[Milestone, float] = field(default_factory=dict)
    outcome: TurnOutcome = TurnOutcome.IN_PROGRESS
    error_step: ErrorStep | None = None
    error_message: str | None = None
    guard_reason: GuardReason | None = None

    def mark(self, milestone: Milestone, at: float) -> None:
        # Record only the first time: a milestone is when each step *starts*.
        self.marks.setdefault(milestone, at)


# LatencySummary rules (data-model.md §4, research R12).
P95_MIN_SAMPLES = 20
IDLE_QUEUE_WAIT_S = 0.3


@dataclass(frozen=True)
class StepStats:
    """Seconds, rounded to milliseconds. `p95` is None below `P95_MIN_SAMPLES`; `note` then says why (UI text)."""

    count: int
    median: float | None
    p95: float | None  # None until there are 20 samples ("chưa đủ mẫu" in the UI)
    note: str | None = None


@dataclass(frozen=True)
class LatencySummary:
    """Body of `GET /api/latency`, the `latency` event and each half of `latency_summary.json`.

    `steps` covers the selected set: every completed turn, or only idle-host turns when `idle_only`.
    `idle_steps` is always the idle-host set (queue_wait < `idle_threshold_s`), so the control page
    can show both rows from a single message. Outcome counts always describe the whole session.
    """

    steps: dict[str, StepStats]
    idle_steps: dict[str, StepStats]
    completed: int
    errors: int
    skipped: int
    idle_only: bool = False
    idle_completed: int = 0
    idle_threshold_s: float = IDLE_QUEUE_WAIT_S
    min_samples: int = P95_MIN_SAMPLES

    def to_json(self) -> dict[str, Any]:
        return {
            "idle_only": self.idle_only,
            "idle_threshold_s": self.idle_threshold_s,
            "min_samples": self.min_samples,
            "completed": self.completed,
            "errors": self.errors,
            "skipped": self.skipped,
            "idle_completed": self.idle_completed,
            "steps": {name: asdict(stats) for name, stats in self.steps.items()},
            "idle_steps": {name: asdict(stats) for name, stats in self.idle_steps.items()},
        }
