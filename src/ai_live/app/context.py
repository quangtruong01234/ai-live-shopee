"""Components that live for the whole session, attached to `app.state.ctx` at startup (lifespan)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.intake import CommentIntake
from ai_live.comments.mock_source import MockSource
from ai_live.core.config import Settings
from ai_live.core.events import EventBus
from ai_live.director.session_log import SessionLog
from ai_live.director.show_director import ShowDirector
from ai_live.products.store import DocxProductStore


@dataclass
class AppContext:
    settings: Settings
    session_id: str
    bus: EventBus
    store: DocxProductStore
    queue: InMemoryCommentQueue
    source: MockSource
    intake: CommentIntake
    renderer: StaticRenderer
    director: ShowDirector
    session_log: SessionLog | None = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_state(ctx: AppContext) -> dict[str, Any]:
    """Body of `GET /api/state` and the first `state` message on `/ws/control`. Holds no config or secrets."""
    current = ctx.director.current
    catalog = ctx.store.catalog
    return {
        "session": {
            "session_id": ctx.session_id,
            "state": ctx.director.state,
            "host_connected": ctx.renderer.host_ready,
        },
        "queue": [item.to_json() for item in ctx.queue.snapshot()],
        "current_utterance": None
        if current is None
        else {
            "utterance_id": current.utterance_id,
            "comment_id": current.comment_id,
            "sentences": list(current.sentences),
            "outcome": current.outcome.value,
        },
        "catalog": {
            "version": catalog.version,
            "source_name": catalog.source_name,
            "products": [{"id": p.id, "name": p.name, "is_primary": p.is_primary} for p in catalog.products],
        },
    }
