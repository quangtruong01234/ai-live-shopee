"""Adapter interfaces (contracts/adapters.md).

A new source or provider is a new class satisfying a Protocol, never a change to the pipeline core.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from ai_live.core.models import Comment, Priority, QueuedComment, RenderTurnStats, SegmentRequest
from ai_live.products.models import Product, ProductCatalog

if TYPE_CHECKING:
    from ai_live.scene.models import FrameGeometry, SceneLayer


class RendererUnavailable(RuntimeError):
    """No `/host` page is connected to play audio."""


class RendererError(RuntimeError):
    """Render-step failure reported by the renderer itself (005 contracts/adapters.md §2, FR-021).

    `kind` is written to `errors.jsonl`: `lipsync_unavailable`, `vram_oom`, `inference_failed`, `bad_audio`,
    `renderer_restarted`, `timeout`.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class ReplyEngineError(RuntimeError):
    """Failure in the `llm` step.

    `kind` is written to `errors.jsonl`: `api_error`, `rate_limited`, `provider_blocked`, `config_error`.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class CommentSource(Protocol):
    """Comment source. `stream()` is for pulled sources (YouTube in 006, Shopee later); MockSource does not use it."""

    name: str

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def stream(self) -> AsyncIterator[Comment]: ...


class CommentQueue(Protocol):
    """In-process priority queue. Dropped comments are reported on the EventBus (`comment_dropped`), never raised.

    `put` returns the queued item; its status is `dropped` (`queue_full`) when the queue was full and the new comment
    ranked strictly lowest.
    """

    async def put(self, comment: Comment, priority: Priority) -> QueuedComment: ...
    async def get(self) -> QueuedComment: ...
    def size(self) -> int: ...
    def snapshot(self) -> list[QueuedComment]: ...


class ProductStore(Protocol):
    """Product content loaded from a Word file. Replacing content swaps the whole catalog."""

    @property
    def catalog(self) -> ProductCatalog: ...
    def list_active(self) -> list[Product]: ...
    def get(self, product_id: str) -> Product | None: ...
    def replace(self, data: bytes, source_name: str) -> ProductCatalog: ...


class ReplyEngine(Protocol):
    """Generates host lines. Both methods yield complete sentences (after the sentence splitter, before sanitize/guard).

    Neither method changes `catalog`. Failures are raised as `ReplyEngineError` with `kind` in `api_error`,
    `rate_limited`, `provider_blocked`, `config_error`.

    Implementations: ChainReplyEngine (OpenAI-compatible model chain, ADR-035/037), GeminiReplyEngine, FakeReplyEngine.
    """

    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]:
        """Answer one viewer comment (feature 001)."""
        ...

    def narrate(self, request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]:
        """Speak one scripted segment about `request.topic` of `request.product_id` (feature 004, ADR-030).

        Raises `ReplyEngineError` like `reply()`. The engine does not handle timeouts: `ScriptRunner` wraps the whole
        segment in `SCRIPT_LLM_TIMEOUT_S` (`SCRIPT_RETRY_TIMEOUT_S` when retrying in fallback mode). The engine does
        not trim the sentence count either: the runner drops sentences beyond `request.max_sentences`
        (`sentence_count_exceeded`) and closes the stream, so it may yield more or fewer than asked.
        """
        ...


class TTSEngineError(RuntimeError):
    """Failure in the `tts` step (003 contracts/adapters.md §1).

    `kind` is written to `errors.jsonl`: `quota_exhausted`, `rate_limited`, `api_error`, `config_error`, `model_error`.
    `message` is Vietnamese, shown to the operator as is.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class TTSEngine(Protocol):
    """Vietnamese TTS. Output: PCM16 little-endian, mono, exactly `sample_rate` Hz (16000, ADR-025)."""

    sample_rate: int

    async def warm_up(self) -> None:
        """Load the model before the session so the first sentence is not slow; a no-op for sources without one.

        Raises `TTSEngineError("config_error", ...)`; the app logs it and keeps running.
        """
        ...

    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


class AvatarRenderer(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def speak(self, utterance_id: str, text: str, audio: AsyncIterator[bytes], sample_rate: int) -> None: ...
    async def interrupt(self) -> None: ...
    @property
    def is_speaking(self) -> bool: ...
    def first_playback_at(self, utterance_id: str) -> float | None:
        """`time.monotonic()` when the turn's first sentence started playing (`avatar_first_frame`), else `None`."""
        ...


# Optional renderer capabilities (005 contracts/adapters.md §2). The core checks them with `isinstance`, so a renderer
# that lacks them (StaticRenderer) keeps working unchanged.


@runtime_checkable
class RenderOutcomeSink(Protocol):
    """A renderer that wants to know how each turn's render step ended (FR-022, research R9)."""

    def record_render_outcome(self, utterance_id: str, ok: bool, *, error_kind: str | None = None) -> None: ...


@runtime_checkable
class RenderStatsSource(Protocol):
    """A renderer that measures its own frame rate per turn (FR-020)."""

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None: ...


@runtime_checkable
class RenderSettleSource(Protocol):
    """A renderer whose `speak` can return before the turn's last sentence has played (R15, LIVETALKING_LEAD_S).

    `turn_settled` gives a future that resolves once those sentences are played and counted, or None when nothing
    of the turn is still playing, so the core collects the turn's figures only when they are complete.
    """

    def turn_settled(self, utterance_id: str) -> asyncio.Future[None] | None: ...


# Live scene hooks (009 contracts/adapters.md §1–§3).


class PlaybackListener(Protocol):
    """Told when a sentence is really heard, not when it is prepared (FR-016).

    Called synchronously on the event loop; must return quickly. A listener that raises is logged and skipped.
    """

    def playback_started(self, utterance_id: str, seq: int, text: str) -> None: ...
    def playback_ended(self, utterance_id: str, seq: int) -> None: ...
    def playback_stopped(self) -> None: ...


@runtime_checkable
class PlaybackSource(Protocol):
    def add_playback_listener(self, listener: PlaybackListener) -> None: ...


@runtime_checkable
class SceneSink(Protocol):
    """A renderer that composites scene layers into its own frames (the lip-sync fork)."""

    def set_scene_layer(self, name: str, layer: SceneLayer | None) -> None: ...
    def add_scene_geometry_listener(self, callback: Callable[[FrameGeometry], None]) -> None: ...


BackgroundMaskStatus = Literal["valid", "missing", "mismatch"]
_MASK_STATUSES: tuple[BackgroundMaskStatus, ...] = ("valid", "missing", "mismatch")


@dataclass(frozen=True)
class ForkBackgroundStatus:
    """The fork's `hello.background` block (014 fork-protocol §2): whether its host masks match the frames it plays."""

    status: BackgroundMaskStatus
    reason: str | None
    frames: int
    width: int
    height: int
    method: str | None
    reviewed: bool | None

    @classmethod
    def from_hello(cls, raw: Any) -> ForkBackgroundStatus | None:
        """None for an older fork (no block) or a block this app cannot read: both mean the fork cannot composite."""
        if not isinstance(raw, dict) or raw.get("status") not in _MASK_STATUSES:
            return None

        def number(key: str) -> int:
            value = raw.get(key)
            return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0

        reason, method, reviewed = raw.get("reason"), raw.get("method"), raw.get("reviewed")
        return cls(
            status=raw["status"],
            reason=str(reason) if reason is not None else None,
            frames=number("frames"),
            width=number("width"),
            height=number("height"),
            method=str(method) if method is not None else None,
            reviewed=reviewed if isinstance(reviewed, bool) else None,
        )


@runtime_checkable
class BackgroundSink(Protocol):
    """A renderer whose fork can composite a backdrop under the host (014 fork-protocol §3)."""

    def set_scene_background(self, plate_png: bytes | None) -> None: ...
    def add_background_status_listener(self, callback: Callable[[ForkBackgroundStatus | None], None]) -> None: ...
