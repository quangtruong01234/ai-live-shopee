"""Components that live for the whole session, attached to `app.state.ctx` at startup (lifespan)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ai_live.avatar.static_renderer import HostConnection, HostRole
from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.intake import CommentIntake
from ai_live.comments.mock_source import MockSource
from ai_live.core.config import Settings
from ai_live.core.events import EventBus
from ai_live.core.protocols import AvatarRenderer
from ai_live.director.session_log import SessionLog
from ai_live.director.show_director import ShowDirector
from ai_live.products.store import DocxProductStore

if TYPE_CHECKING:
    from ai_live.avatar.character import AvatarCharacter
    from ai_live.brain.chain_engine import ChainReplyEngine
    from ai_live.ops.watchdog import WatchdogService
    from ai_live.scene.controller import SceneController


class HostRenderer(AvatarRenderer, Protocol):
    """What the host page attaches to over `/ws/host`: `StaticRenderer` or `SwitchingRenderer` (005 adapters.md §6)."""

    async def attach(self, conn: HostConnection, role: str = "host") -> bool: ...
    def detach(self, conn: HostConnection) -> None: ...
    def handle_message(self, conn: HostConnection, message: dict[str, Any]) -> None: ...
    @property
    def host_ready(self) -> bool: ...
    @property
    def host_role(self) -> HostRole | None: ...


@dataclass
class AppContext:
    settings: Settings
    session_id: str
    bus: EventBus
    store: DocxProductStore
    queue: InMemoryCommentQueue
    source: MockSource
    intake: CommentIntake
    renderer: HostRenderer
    director: ShowDirector
    session_log: SessionLog | None = None
    # 008: the reply engine when it is the model chain, for `llm_chain` and `/health`; None on any other engine.
    chain: ChainReplyEngine | None = None
    # 005: the still image `/avatar-image` serves: the character's face in `livetalking`; None = `AVATAR_STATIC_IMAGE`.
    avatar_image: Path | None = None
    # 005: the lip-sync character this session runs, for `GET /api/avatar`; None in `static`.
    character: AvatarCharacter | None = None
    # 009: the live scene around the host; None when `SCENE_ENABLED` is off.
    scene: SceneController | None = None
    # 007: the show watchdog; None when `WATCHDOG_ENABLED` is off.
    watchdog: WatchdogService | None = None


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
            # 006: which page plays and which one this session expects (contracts/api.md §5).
            "output_mode": ctx.settings.output_mode,
            "host_role": ctx.renderer.host_role,
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
        # 004: `ShowSnapshot`, or null before the first "Bắt đầu show" (contracts/api.md §4).
        "show": ctx.director.show_snapshot(),
        # 008: `ChainSnapshot`, or null when the reply engine is not the chain (contracts/api.md §1).
        "llm_chain": dict(ctx.chain.snapshot()) if ctx.chain is not None else None,
        # 007: the open watchdog alerts, so a reloaded control page still shows them (contracts/api.md §3).
        "alerts": [alert.to_json() for alert in ctx.watchdog.open_alerts] if ctx.watchdog is not None else [],
    }
