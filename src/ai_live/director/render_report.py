"""Tell the renderer how a turn's render step ended and log its figures (005 contracts/adapters.md §2, FR-020, FR-022).

Both hooks are optional on the renderer: `StaticRenderer` has neither, so the director only uses them when present
and keeps working with any `AvatarRenderer` (constitution: new renderers are adapters, not core changes).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ai_live.core.logging import log_event
from ai_live.core.models import RenderTurnStats
from ai_live.core.protocols import RenderOutcomeSink, RenderSettleSource, RenderStatsSource

logger = logging.getLogger(__name__)

# A handed-off sentence normally settles within its own length; this only bounds a fork that never answers.
SETTLE_TIMEOUT_S = 30.0
_pending: set[asyncio.Task[Any]] = set()


def report_render_outcome(renderer: object, utterance_id: str, ok: bool, error_kind: str | None = None) -> None:
    if isinstance(renderer, RenderOutcomeSink):
        renderer.record_render_outcome(utterance_id, ok, error_kind=error_kind)


def collect_render_stats(renderer: object, utterance_id: str) -> RenderTurnStats | None:
    """The turn's render figures, logged as `render_stats` when the renderer measured any frame.

    A turn the fork failed before its first frame has nothing to report, so it gets no log line.
    """
    if not isinstance(renderer, RenderStatsSource):
        return None
    stats = renderer.render_stats(utterance_id)
    if stats is not None and stats.frames > 0:
        log_event(
            logger,
            "render_stats",
            utterance_id=utterance_id,
            frames=stats.frames,
            render_fps=stats.render_fps,
            infer_fps=stats.infer_fps,
            clips_used=stats.clips_used,
        )
    return stats


def collect_render_stats_when_settled(
    renderer: object,
    utterance_id: str,
    on_late: Callable[[RenderTurnStats | None], None] | None = None,
) -> RenderTurnStats | None:
    """`collect_render_stats` once the turn has finished playing (005 R15, contracts/adapters.md §2).

    With LIVETALKING_LEAD_S the turn's last sentence is still playing when `speak` returns, so its figures are not
    in yet: they are collected in the background when the renderer says the turn settled, handed to `on_late`, and
    None is returned now. Otherwise this is `collect_render_stats`.
    """
    settled = renderer.turn_settled(utterance_id) if isinstance(renderer, RenderSettleSource) else None
    if settled is None:
        return collect_render_stats(renderer, utterance_id)

    async def later() -> None:
        await asyncio.wait({settled}, timeout=SETTLE_TIMEOUT_S)  # never raises: figures only
        stats = collect_render_stats(renderer, utterance_id)
        if on_late is not None:
            on_late(stats)

    task = asyncio.get_running_loop().create_task(later())
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return None
