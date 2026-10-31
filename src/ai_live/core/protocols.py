"""Adapter interfaces (contracts/adapters.md).

A new source or provider is a new class satisfying a Protocol, never a change to the pipeline core.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from ai_live.core.models import Comment, Priority, QueuedComment
from ai_live.products.models import Product, ProductCatalog


class RendererUnavailable(RuntimeError):
    """No `/host` page is connected to play audio."""


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
    """Generates the reply. Yields complete sentences (after the sentence splitter, before the guard)."""

    def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]: ...


class TTSEngine(Protocol):
    """PCM16 little-endian mono."""

    sample_rate: int

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
