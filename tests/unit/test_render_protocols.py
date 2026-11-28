"""T018 optional renderer capabilities and `RendererError` (005 contracts/adapters.md §2)."""

from __future__ import annotations

from collections.abc import Callable

from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.core.models import RenderTurnStats
from ai_live.core.protocols import (
    BackgroundSink,
    ForkBackgroundStatus,
    RendererError,
    RenderOutcomeSink,
    RenderStatsSource,
)


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


# ---------- 014 T009: background behind the host (014 contracts/adapters.md §1) ----------
class _BackgroundLike:
    def set_scene_background(self, plate_png: bytes | None) -> None:
        return None

    def add_background_status_listener(self, callback: Callable[[ForkBackgroundStatus | None], None]) -> None:
        return None


def test_background_sink_is_runtime_checkable():
    assert isinstance(_BackgroundLike(), BackgroundSink)


def test_static_renderer_is_not_a_background_sink():
    # The controller falls back with `avatar_static` when the renderer cannot composite a backdrop (research R14).
    assert not isinstance(StaticRenderer(), BackgroundSink)


def test_fork_background_status_from_hello_block():
    block = {
        "status": "mismatch",
        "reason": "frame_not_prepared:3",
        "frames": 81,
        "width": 480,
        "height": 832,
        "method": "plate",
        "reviewed": False,
    }
    assert ForkBackgroundStatus.from_hello(block) == ForkBackgroundStatus(
        status="mismatch",
        reason="frame_not_prepared:3",
        frames=81,
        width=480,
        height=832,
        method="plate",
        reviewed=False,
    )


def test_fork_background_status_missing_block_is_none():
    # An older fork sends no `background` block: the app treats it as `fork_unsupported`.
    assert ForkBackgroundStatus.from_hello(None) is None


def test_fork_background_status_unknown_status_is_none():
    assert ForkBackgroundStatus.from_hello({"status": "weird"}) is None
    assert ForkBackgroundStatus.from_hello("valid") is None


def test_fork_background_status_tolerates_missing_numbers():
    status = ForkBackgroundStatus.from_hello({"status": "missing", "reason": "not_prepared"})
    assert status == ForkBackgroundStatus("missing", "not_prepared", 0, 0, 0, None, None)
