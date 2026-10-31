"""Comment source typed in by the operator on the control page (contracts/adapters.md; FR-001)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable

from ai_live.core.logging import log_event
from ai_live.core.models import Comment
from ai_live.core.text import normalize_text

logger = logging.getLogger("ai_live.comments")

AUTHOR_MAX_CHARS = 30


class MockSource:
    name = "mock"

    def __init__(self, max_chars: int = 300, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_chars = max_chars
        self._clock = clock

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def stream(self) -> AsyncIterator[Comment]:
        # Comments arrive through `push()` from HTTP, nothing is pulled; the stream ends at once.
        return
        yield  # pragma: no cover

    def push(self, author: str, text: str) -> Comment:
        """Create the comment and log the `comment_received` milestone at the moment it arrives."""
        full = normalize_text(text)
        comment = Comment(
            id=uuid.uuid4().hex,
            source=self.name,
            author=normalize_text(author, AUTHOR_MAX_CHARS) or "bạn",
            text=normalize_text(full, self.max_chars),
            received_at=self._clock(),
            # Cutting happens here, so the filter could not tell otherwise (data-model.md §1 `meta.truncated`).
            meta={"truncated": len(full) > self.max_chars},
        )
        log_event(logger, "comment_received", comment_id=comment.id, t_mono=comment.received_at)
        log_event(
            logger, "comment_text", logging.DEBUG, comment_id=comment.id, author=comment.author, text=comment.text
        )
        return comment
