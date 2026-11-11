"""T018 optional renderer capabilities and `RendererError` (005 contracts/adapters.md §2)."""

from __future__ import annotations

from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.core.models import RenderTurnStats
from ai_live.core.protocols import RendererError, RenderOutcomeSink, RenderStatsSource


class _LipsyncLike:
    def record_render_outcome(self, utterance_id: str, ok: bool) -> None:
        return None

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None:
        return None


def test_renderer_error_carries_kind():
    exc = RendererError("vram_oom", "hết VRAM")
    assert isinstance(exc, RuntimeError)
    assert exc.kind == "vram_oom"
    assert str(exc) == "hết VRAM"


def test_optional_protocols_are_runtime_checkable():
    renderer = _LipsyncLike()
    assert isinstance(renderer, RenderOutcomeSink)
    assert isinstance(renderer, RenderStatsSource)


def test_static_renderer_has_neither_capability():
    # The core skips both calls for StaticRenderer, so static mode behaves exactly as in 001/004 (FR-014).
    renderer = StaticRenderer()
    assert not isinstance(renderer, RenderOutcomeSink)
    assert not isinstance(renderer, RenderStatsSource)
