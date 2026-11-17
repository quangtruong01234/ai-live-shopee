"""The `on_stats` sink of `render_report` and the `avatar.jsonl` `render` line (005 contracts/events.md §4)."""

from __future__ import annotations

import asyncio

import pytest

from ai_live.core.models import RenderTurnStats
from ai_live.director.render_report import collect_render_stats, collect_render_stats_when_settled
from ai_live.director.session_log import render_record


class _Renderer:
    def __init__(self, frames: int = 50, settled: asyncio.Future[None] | None = None) -> None:
        self.frames = frames
        self.settled = settled

    def render_stats(self, utterance_id: str) -> RenderTurnStats | None:
        return RenderTurnStats(
            utterance_id=utterance_id,
            mode="livetalking",
            clips_used=["talk_01"],
            frames=self.frames,
            render_fps=24.8,
            infer_fps=30.1,
            scene_ms=1.5,
            mouth_method="w2l",
        )

    def turn_settled(self, utterance_id: str) -> asyncio.Future[None] | None:
        return self.settled


def test_sink_gets_the_figures_of_a_rendered_turn():
    got: list[RenderTurnStats] = []
    stats = collect_render_stats(_Renderer(), "u1", on_stats=got.append)
    assert got == [stats]


def test_sink_is_quiet_when_no_frame_was_rendered():
    got: list[RenderTurnStats] = []
    collect_render_stats(_Renderer(frames=0), "u1", on_stats=got.append)
    assert got == []


@pytest.mark.anyio
async def test_sink_gets_late_figures_once_the_turn_settles():
    settled: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    got: list[RenderTurnStats] = []
    late: list[RenderTurnStats | None] = []
    now = collect_render_stats_when_settled(_Renderer(settled=settled), "u1", on_late=late.append, on_stats=got.append)
    assert now is None
    assert got == []
    settled.set_result(None)
    for _ in range(5):
        await asyncio.sleep(0)
    assert [s.utterance_id for s in got] == ["u1"]
    assert late == got


def test_render_record_shape():
    stats = _Renderer().render_stats("u1")
    assert stats is not None
    record = render_record(stats, "show-1")
    assert record.pop("ts")
    assert record == {
        "kind": "render",
        "utterance_id": "u1",
        "show_id": "show-1",
        "frames": 50,
        "render_fps": 24.8,
        "infer_fps": 30.1,
        "clips_used": ["talk_01"],
        "scene_ms": 1.5,
        "mouth_method": "w2l",
    }
