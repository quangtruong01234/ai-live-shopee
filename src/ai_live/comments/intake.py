"""Comment intake: source -> filter -> classifier -> queue (FR-001 -> FR-004).

Shared by `POST /api/comments` and the `ai_live.comments` CLI so both apply exactly the same rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ai_live.comments.classifier import PriorityClassifier
from ai_live.comments.filters import CommentFilter
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
    ) -> None:
        self._source = source
        self._filter = comment_filter
        self._classifier = classifier
        self._queue = queue
        self._bus = bus

    async def submit(self, author: str, text: str) -> IntakeResult:
        checked = self._filter.check(self._source.push(author, text))
        comment = checked.comment
        if checked.drop_reason is not None:
            log_event(logger, "comment_dropped", comment_id=comment.id, reason=checked.drop_reason.value)
            self._bus.publish(comment_dropped_event(comment, checked.drop_reason))
            return IntakeResult(comment, CommentStatus.DROPPED, drop_reason=checked.drop_reason)

        priority = self._classifier.classify(comment.text)
        self._bus.publish(
            Event(
                EventType.COMMENT_ACCEPTED,
                {"comment_id": comment.id, "author": comment.author, "text": comment.text, "priority": priority.name},
            )
        )
        queued = await self._queue.put(comment, priority)
        return IntakeResult(comment, queued.status, priority=priority, drop_reason=queued.drop_reason)
