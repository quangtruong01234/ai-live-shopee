"""Tell the renderer how a turn's render step ended and log its figures (005 contracts/adapters.md §2, FR-020, FR-022).

Both hooks are optional on the renderer: `StaticRenderer` has neither, so the director only uses them when present
and keeps working with any `AvatarRenderer` (constitution: new renderers are adapters, not core changes).
"""

from __future__ import annotations

import logging

from ai_live.core.logging import log_event
from ai_live.core.models import RenderTurnStats
from ai_live.core.protocols import RenderOutcomeSink, RenderStatsSource

logger = logging.getLogger(__name__)


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
