"""Shared pipeline models.

Comment path: specs/001-local-reply-pipeline/data-model.md §1, §3, §4.
Scripted show: specs/004-show-director/data-model.md §1-§9.
Avatar / lip-sync: specs/005-lipsync-livetalking/data-model.md §4-§6.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, Literal


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
    SHOW_ENDED = "show_ended"  # taken from the queue while the show is closing or ended (004 FR-030)

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
    DropReason.SHOW_ENDED: "phiên đã kết thúc",
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
    SEGMENT_REQUESTED = "segment_requested"  # start of a scripted sentence's clock, instead of comment_received
    # A reply's player got the floor; inside a show it waits there for the scripted sentence being spoken.
    # In memory only (latency `floor_wait`), not written to utterances.jsonl.
    FLOOR_ACQUIRED = "floor_acquired"


# The four milestones required by Article VIII; turn_started is extra, to separate queue wait time.
REQUIRED_MILESTONES: tuple[Milestone, ...] = (
    Milestone.COMMENT_RECEIVED,
    Milestone.LLM_FIRST_SENTENCE,
    Milestone.TTS_FIRST_CHUNK,
    Milestone.AVATAR_FIRST_FRAME,
)

# The same four for a scripted sentence: there is no comment, so the clock starts when the segment is requested.
REQUIRED_SCRIPT_MILESTONES: tuple[Milestone, ...] = (
    Milestone.SEGMENT_REQUESTED,
    Milestone.LLM_FIRST_SENTENCE,
    Milestone.TTS_FIRST_CHUNK,
    Milestone.AVATAR_FIRST_FRAME,
)


class GuardReason(StrEnum):
    FORBIDDEN_CLAIM = "forbidden_claim"
    UNKNOWN_AMOUNT = "unknown_amount"
    # feature 004 (research R9, ADR-031); checked on both the script and the comment path
    UNKNOWN_PERCENT = "unknown_percent"
    LINK = "link"
    PLATFORM_PHRASE = "platform_phrase"
    # ADR-050: safety, skin feel, testimonials, stock and urgency phrases the content file does not hold (FR-010)
    UNSUPPORTED_CLAIM = "unsupported_claim"

    @property
    def label(self) -> str:
        """Reason shown on the control page next to a blocked sentence (`reason_label`, 004 contracts/api.md §4)."""
        return _GUARD_LABELS[self]


_GUARD_LABELS = {
    GuardReason.FORBIDDEN_CLAIM: "khẳng định bị cấm",
    GuardReason.UNKNOWN_AMOUNT: "số tiền không có trong dữ liệu",
    GuardReason.UNKNOWN_PERCENT: "phần trăm không có trong dữ liệu",
    GuardReason.LINK: "chứa link",
    GuardReason.PLATFORM_PHRASE: "cơ chế nền tảng shop không có",
    GuardReason.UNSUPPORTED_CLAIM: "khẳng định không có trong dữ liệu",
}


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
    """One spoken unit: a comment reply (001) or one scripted sentence (004).

    Exactly one of `comment_id` and `segment_id` is set. `show_id` is set whenever the utterance happens inside a
    show, including a comment reply that cuts in. A scripted sentence uses `REQUIRED_SCRIPT_MILESTONES` for `marks`.
    """

    utterance_id: str
    comment_id: str | None
    catalog_version: str
    sentences: list[str] = field(default_factory=list)
    marks: dict[Milestone, float] = field(default_factory=dict)
    outcome: TurnOutcome = TurnOutcome.IN_PROGRESS
    error_step: ErrorStep | None = None
    error_message: str | None = None
    guard_reason: GuardReason | None = None
    # Keyword-only so every 001 call site (positional or keyword) keeps working unchanged.
    segment_id: str | None = field(default=None, kw_only=True)
    show_id: str | None = field(default=None, kw_only=True)
    # The `type` written to `errors.jsonl` (e.g. `quota_exhausted`), so the control page can show it with the message.
    error_kind: str | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if (self.comment_id is None) == (self.segment_id is None):
            raise ValueError("Utterance needs exactly one of comment_id and segment_id")

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
    # 005 FR-020: frames per second over completed lip-sync turns. A rate, not a duration, so it is kept out of
    # `steps`; static turns have no value and are not counted.
    render_fps: StepStats | None = None
    infer_fps: StepStats | None = None
    # Latest turns, newest first, each with its render columns (005 contracts/api.md §2); bounded by the tracker.
    turns: list[dict[str, Any]] = field(default_factory=list)

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
            "render_fps": asdict(self.render_fps) if self.render_fps is not None else None,
            "infer_fps": asdict(self.infer_fps) if self.infer_fps is not None else None,
            "turns": self.turns,
        }


# ---------- Scripted show (feature 004, specs/004-show-director/data-model.md) ----------


class ShowState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CLOSING = "closing"
    ENDED = "ended"

    @property
    def label(self) -> str:
        """Name shown on the control page (FR-019)."""
        return _SHOW_STATE_LABELS[self]


_SHOW_STATE_LABELS = {
    ShowState.IDLE: "chưa chạy",
    ShowState.RUNNING: "đang chạy",
    ShowState.PAUSED: "tạm dừng",
    ShowState.CLOSING: "đang chào kết",
    ShowState.ENDED: "đã kết thúc",
}


class ShowMode(StrEnum):
    NORMAL = "normal"
    FALLBACK = "fallback"  # after SCRIPT_FALLBACK_AFTER LLM failures in a row (FR-021)


class Topic(StrEnum):
    """Segment topics, in the rotation order of research R5."""

    OPENING = "opening"
    INTRO = "intro"
    HIGHLIGHTS = "highlights"
    SPECS = "specs"
    PRICE = "price"
    PROMOTION = "promotion"
    FAQ = "faq"
    CALL_TO_ACTION = "call_to_action"
    CLOSING = "closing"

    @property
    def label(self) -> str:
        """Name shown on the control page."""
        return _TOPIC_LABELS[self]

    @property
    def has_product(self) -> bool:
        """`opening` and `closing` belong to the show; every other topic belongs to one product."""
        return self not in (Topic.OPENING, Topic.CLOSING)


_TOPIC_LABELS = {
    Topic.OPENING: "Chào mở màn",
    Topic.INTRO: "Giới thiệu chung",
    Topic.HIGHLIGHTS: "Điểm nổi bật",
    Topic.SPECS: "Thông số",
    Topic.PRICE: "Giá và phân loại",
    Topic.PROMOTION: "Khuyến mãi",
    Topic.FAQ: "Câu hỏi thường gặp",
    Topic.CALL_TO_ACTION: "Kêu gọi mua",
    Topic.CLOSING: "Chào kết",
}

# Topics the rotation cycles through per product; the runner creates `opening` and `closing` itself.
ROTATION_TOPICS: tuple[Topic, ...] = tuple(t for t in Topic if t.has_product)


class SegmentOrigin(StrEnum):
    ROTATION = "rotation"
    OPERATOR = "operator"  # chosen on the control page (FR-018)
    FALLBACK = "fallback"


class SegmentStatus(StrEnum):
    PREPARING = "preparing"
    READY = "ready"
    SPEAKING = "speaking"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
    BLOCKED = "blocked"
    DISCARDED = "discarded"  # dropped because of a content change, an operator override or the end of the show


# A segment never changes after one of these; its `segments.jsonl` line is written then.
FINAL_SEGMENT_STATUSES: frozenset[SegmentStatus] = frozenset(
    {SegmentStatus.DONE, SegmentStatus.SKIPPED, SegmentStatus.FAILED, SegmentStatus.BLOCKED, SegmentStatus.DISCARDED}
)


class SentenceStatus(StrEnum):
    SPOKEN = "spoken"
    BLOCKED = "blocked"
    DROPPED = "dropped"  # see `ScriptSentence.drop_reason`
    TTS_ERROR = "tts_error"
    RENDER_ERROR = "render_error"
    INTERRUPTED = "interrupted"


class GapKind(StrEnum):
    """Why the silence before a scripted sentence happened (research R12)."""

    SCRIPT = "script"
    SEGMENT_BOUNDARY = "segment_boundary"
    COMMENT = "comment"
    PAUSED = "paused"
    FAULT = "fault"
    ERROR = "error"


@dataclass(frozen=True)
class SegmentRequest:
    """Input of `ReplyEngine.narrate()` (data-model §5).

    Checked here: `1 <= min_sentences <= max_sentences`, and a product exactly for the product topics. Whether the
    product exists and the topic has data is checked by the planner, which has the catalog.
    """

    segment_id: str
    topic: Topic
    product_id: str | None
    min_sentences: int
    max_sentences: int
    previous_sentence: str | None = None  # last sentence spoken, to keep the flow
    recent_lines: tuple[str, ...] = ()  # SpokenHistory.recent_for(product_id, SCRIPT_HISTORY_SENTENCES)

    def __post_init__(self) -> None:
        if not 1 <= self.min_sentences <= self.max_sentences:
            raise ValueError(
                f"SegmentRequest needs 1 <= min <= max, got min={self.min_sentences} max={self.max_sentences}"
            )
        if self.topic.has_product and self.product_id is None:
            raise ValueError(f"Topic {self.topic.value!r} needs a product_id")
        if not self.topic.has_product and self.product_id is not None:
            raise ValueError(f"Topic {self.topic.value!r} has no product, got product_id={self.product_id!r}")


@dataclass
class ScriptSentence:
    """One scripted sentence (data-model §6). A spoken one has an `Utterance` with the same `utterance_id`.

    `marks` and `played_at` are `time.monotonic()` values, like `Utterance.marks`, so gaps are a plain subtraction;
    `script_sentences.jsonl` stores them relative to `segment_requested`.
    """

    utterance_id: str
    segment_id: str
    seq: int  # order inside the segment, blocked sentences included
    raw_text: str  # as the LLM returned it, to debug the prompt
    text: str  # after clean_spoken(): what is spoken and subtitled
    word_form: str  # match form for the repeat filter (research R11)
    status: SentenceStatus = SentenceStatus.SPOKEN
    guard_reason: GuardReason | None = None
    guard_detail: str | None = None
    drop_reason: str | None = None  # duplicate, empty_after_clean, sentence_count_exceeded, paused_discard
    marks: dict[Milestone, float] = field(default_factory=dict)
    played_at: float | None = None  # when renderer.speak() returned


@dataclass
class Segment:
    """A run of a few sentences on one product and topic (data-model §4)."""

    segment_id: str
    show_id: str
    index: int  # order in the show, from 0
    product_id: str | None  # None for opening/closing
    topic: Topic
    origin: SegmentOrigin
    mode: ShowMode
    catalog_version: str  # checked again before the first sentence plays (research R7)
    status: SegmentStatus = SegmentStatus.PREPARING
    requested_at: datetime | None = None
    ready_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    sentences: list[ScriptSentence] = field(default_factory=list)
    error_step: str | None = None  # llm, tts, render
    error_kind: str | None = None
    error_message: str | None = None


RECENT_SHOW_ITEMS = 20

# 007 R6: `verbatim` reads the product's own intro and description, never the engine (the backup video).
ContentSource = Literal["script", "verbatim"]
CONTENT_SOURCES: tuple[ContentSource, ...] = ("script", "verbatim")


@dataclass
class ShowSession:
    """One show, from "Bắt đầu show" to `ended` (data-model §3)."""

    show_id: str
    session_id: str  # the 001 app session; show files go to its folder
    start_requested_at: float  # time.monotonic(), for SC-001
    catalog_version: str  # at start; every segment records its own
    state: ShowState = ShowState.IDLE
    mode: ShowMode = ShowMode.NORMAL
    started_at: datetime | None = None
    ended_at: datetime | None = None
    consecutive_llm_failures: int = 0  # back to 0 when narrate() succeeds (research R10)
    current_segment: Segment | None = None
    next_segment: Segment | None = None
    recent_blocked: deque[ScriptSentence] = field(default_factory=lambda: deque(maxlen=RECENT_SHOW_ITEMS))
    recent_errors: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=RECENT_SHOW_ITEMS))
    content_source: ContentSource = "script"  # fixed at start; a second start never changes it


SpokenSource = Literal["script", "fallback", "reply"]
_SPOKEN_SOURCES = ("script", "fallback", "reply")


@dataclass(frozen=True)
class SpokenLine:
    text: str
    word_form: str
    product_id: str | None
    source: SpokenSource
    comment_text: str | None = None  # the comment answered, when source is "reply"

    def __post_init__(self) -> None:
        if self.source not in _SPOKEN_SOURCES:
            raise ValueError(f"Bad SpokenLine source {self.source!r}")


@dataclass
class SpokenHistory:
    """What the host said during one show, in order (data-model §7). In memory only; a new show starts empty."""

    lines: list[SpokenLine] = field(default_factory=list)
    # Layer 2 of the repeat filter (research R11). Fallback lines stay out: they may be read again (SC-005).
    seen_word_forms: set[str] = field(default_factory=set)

    def add(self, line: SpokenLine) -> None:
        self.lines.append(line)
        if line.source != "fallback":
            self.seen_word_forms.add(line.word_form)

    def recent_for(self, product_id: str | None, n: int) -> tuple[str, ...]:
        """The last `n` lines about `product_id` (any source), oldest first, for `SegmentRequest.recent_lines`."""
        if n <= 0:
            return ()
        picked: list[str] = []
        for line in reversed(self.lines):
            if line.product_id == product_id:
                picked.append(line.text)
                if len(picked) == n:
                    break
        return tuple(reversed(picked))


@dataclass(frozen=True)
class SentenceGap:
    """Silence between two spoken scripted sentences: `avatar_first_frame(to) - played_at(from)` (data-model §8)."""

    from_utterance_id: str
    to_utterance_id: str
    seconds: float
    kind: GapKind


@dataclass
class ShowSummary:
    """Body of `show_summary_<show_id>.json` (data-model §9). `ShowStats` fills the nested sections."""

    show_id: str
    session_id: str
    started_at: datetime | None
    ended_at: datetime | None
    ended_by: Literal["operator", "shutdown"]
    show_first_sentence_s: float | None
    segments: dict[str, Any] = field(default_factory=dict)
    secondary_coverage: list[dict[str, Any]] = field(default_factory=list)
    sentences: dict[str, int] = field(default_factory=dict)
    gaps: dict[str, Any] = field(default_factory=dict)
    duplicates: dict[str, Any] = field(default_factory=dict)
    mode_changes: list[dict[str, Any]] = field(default_factory=list)
    comments: dict[str, Any] = field(default_factory=dict)
    # 008 data-model §7: per-entry counts of the model chain; None when REPLY_ENGINE is not `chain`.
    llm_chain: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "show_id": self.show_id,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "ended_by": self.ended_by,
            "show_first_sentence_s": self.show_first_sentence_s,
            "segments": self.segments,
            "secondary_coverage": self.secondary_coverage,
            "sentences": self.sentences,
            "gaps": self.gaps,
            "duplicates": self.duplicates,
            "mode_changes": self.mode_changes,
            "comments": self.comments,
            "llm_chain": self.llm_chain,
        }


# ---------- Avatar / lip-sync (feature 005, specs/005-lipsync-livetalking/data-model.md §4-§6) ----------

AvatarMode = Literal["static", "livetalking"]


@dataclass
class AvatarModeState:
    """Which renderer `SwitchingRenderer` uses; `active` differs from `configured` only after a fallback (§4)."""

    configured: AvatarMode
    active: AvatarMode
    reason: str | None = None  # "render_errors" after a fallback; None while active == configured
    consecutive_errors: int = 0
    # Last turn already counted, so a multi-sentence turn counts once (internal, not sent in the event).
    last_utterance_id: str | None = None
    changed_at: datetime | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "active": self.active,
            "reason": self.reason,
            "consecutive_errors": self.consecutive_errors,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
        }


@dataclass
class RenderTurnStats:
    """Per-turn render figures; `LiveTalkingRenderer` sums the fork's per-sentence `stats` (§5, FR-013, FR-020)."""

    utterance_id: str
    mode: AvatarMode
    clips_used: list[str] = field(default_factory=list)
    frames: int = 0
    render_fps: float | None = None
    infer_fps: float | None = None
    first_frame_at: float | None = None  # time.monotonic() of the first `playback_started` = avatar_first_frame
    # time.monotonic() of the latest `sentence_played`: with LIVETALKING_LEAD_S `speak` returns before it (R15)
    last_played_at: float | None = None
    error_kind: str | None = None
    scene_ms: float | None = None  # mean ms per frame the fork spent compositing the scene (009 FR-022)
    mouth_method: str | None = None  # 010 FR-010: mouth method the fork reported; None from a fork without one


@dataclass
class LipsyncHealth:
    """Latest state the fork reported, for the control page and `GET /health` (§6)."""

    connected: bool = False
    boot_id: str | None = None
    fork_commit: str | None = None
    session_id: str | None = None
    vram_used_mb: int | None = None
    infer_fps: float | None = None
    last_error: str | None = None
    updated_at: datetime | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "boot_id": self.boot_id,
            "fork_commit": self.fork_commit,
            "session_id": self.session_id,
            "vram_used_mb": self.vram_used_mb,
            "infer_fps": self.infer_fps,
            "last_error": self.last_error,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


_AUDIO_STATES = ("running", "suspended", "closed")


@dataclass(frozen=True)
class HostStatus:
    """The host tab's 1 s heartbeat: what the viewer's screen is actually doing (007 data-model §2, research R1).

    `received_at` is app-side monotonic time: the tab's clock is never trusted for thresholds.
    """

    frames: int | None  # WebRTC framesDecoded; None in static mode or before the first frame
    audio: Literal["running", "suspended", "closed"] | None
    video_muted: bool | None
    video_paused: bool | None
    visible: bool | None
    received_at: float

    @classmethod
    def from_message(cls, message: dict[str, Any], received_at: float) -> HostStatus:
        # The page is outside our control: a missing or wrong field is "unknown", never an error.
        frames = message.get("frames")
        audio = message.get("audio")

        def flag(name: str) -> bool | None:
            value = message.get(name)
            return value if isinstance(value, bool) else None

        return cls(
            frames=frames if isinstance(frames, int) and not isinstance(frames, bool) and frames >= 0 else None,
            audio=audio if audio in _AUDIO_STATES else None,
            video_muted=flag("video_muted"),
            video_paused=flag("video_paused"),
            visible=flag("visible"),
            received_at=received_at,
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
