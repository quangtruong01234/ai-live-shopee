"""Comment intake: source -> operator block -> per-viewer limit -> filter -> classifier -> greetings -> queue (FR-001 ->
FR-004, FR-026, FR-027, FR-029).

Shared by `POST /api/comments` and the `ai_live.comments` CLI so both apply exactly the same rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.author_limits import AuthorLimiter
from ai_live.comments.classifier import PriorityClassifier
from ai_live.comments.filters import CommentFilter
from ai_live.comments.greetings import GreetingRules
from ai_live.comments.mock_source import MockSource
from ai_live.core.events import Event, EventBus, EventType, comment_dropped_event
from ai_live.core.logging import log_event
from ai_live.core.models import Comment, CommentStatus, DropReason, Priority
from ai_live.core.protocols import CommentQueue

logger = logging.getLogger("ai_live.comments")


@dataclass(frozen=True)
class IntakeResult:
    comment: Comment
    status: CommentStatus
    priority: Priority | None = None
    drop_reason: DropReason | None = None

    def to_json(self) -> dict[str, Any]:
        """Body of `POST /api/comments` (contracts/api.md §2); absent keys are omitted, not null."""
        body: dict[str, Any] = {"comment_id": self.comment.id, "status": self.status.value}
        if self.drop_reason is not None:
            body["drop_reason"] = self.drop_reason.value
        if self.priority is not None:
            body["priority"] = self.priority.name
        return body


class CommentIntake:
    def __init__(
        self,
        source: MockSource,
        comment_filter: CommentFilter,
        classifier: PriorityClassifier,
        queue: CommentQueue,
        bus: EventBus,
        limiter: AuthorLimiter | None = None,
        greetings: GreetingRules | None = None,
    ) -> None:
        self._source = source
        # Optional so tools and older tests keep the 001 behaviour; the app and the CLI pass both (ADR-077).
        self._limiter = limiter
        self._greetings = greetings
        self._filter = comment_filter
        self._classifier = classifier
        self._queue = queue
        self._bus = bus

    async def submit(self, author: str, text: str) -> IntakeResult:
        raw = self._source.push(author, text)
        if self._limiter is not None:
            # An operator block comes first and does not count toward the rate limit (FR-029).
            if self._limiter.blocked(raw):
                return self._dropped(raw, DropReason.BLOCKED)
            # Before the filter, so a viewer pasting the same line ten times is muted, not only deduplicated (FR-027).
            version = self._limiter.version
            allowed = self._limiter.allow(raw)
            if self._limiter.version != version:
                self.publish_viewers()
            if not allowed:
                return self._dropped(raw, DropReason.SPAM)
        checked = self._filter.check(raw)
        comment = checked.comment
        if checked.drop_reason is not None:
            return self._dropped(comment, checked.drop_reason)

        priority = self._classifier.classify(comment.text)
        if self._greetings is not None:
            greeting = self._greetings.check(comment, priority)
            if greeting.repeat:
                return self._dropped(comment, DropReason.GREETED)
            comment = greeting.comment
        accepted = {
            "comment_id": comment.id,
            "author": comment.author,
            "author_key": comment.author_key,
            "text": comment.text,
            "priority": priority.name,
        }
        if "kind" in comment.meta:
            accepted["kind"] = comment.meta["kind"]
        self._bus.publish(Event(EventType.COMMENT_ACCEPTED, accepted))
        queued = await self._queue.put(comment, priority)
        return IntakeResult(comment, queued.status, priority=priority, drop_reason=queued.drop_reason)

    def viewers(self) -> list[dict[str, Any]]:
        """Blocked and muted viewers (`ViewerBlock` JSON) for `GET /api/state` and `viewers_changed`."""
        return [] if self._limiter is None else [v.to_json() for v in self._limiter.viewers()]

    def publish_viewers(self) -> None:
        self._bus.publish(Event(EventType.VIEWERS_CHANGED, {"viewers": self.viewers()}))

    def block(self, author_key: str, minutes: float | None, author: str | None = None) -> int:
        """Block one viewer and drop their waiting comments; returns how many were dropped (FR-029, ADR-078).

        The turn speaking now is left alone: the operator skips it with "Bỏ qua" if needed.
        """
        if self._limiter is None:
            raise RuntimeError("viewer blocking needs the per-viewer limiter")
        self._limiter.block(author_key, minutes, author)
        removed = self._queue.remove_author(author_key) if isinstance(self._queue, InMemoryCommentQueue) else []
        self.publish_viewers()
        return len(removed)

    def unblock(self, author_key: str) -> None:
        if self._limiter is not None and self._limiter.unblock(author_key):
            self.publish_viewers()

    def _dropped(self, comment: Comment, reason: DropReason) -> IntakeResult:
        log_event(logger, "comment_dropped", comment_id=comment.id, reason=reason.value)
        self._bus.publish(comment_dropped_event(comment, reason))
        return IntakeResult(comment, CommentStatus.DROPPED, drop_reason=reason)
