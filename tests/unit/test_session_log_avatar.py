"""T020 session files for 005: render fields, `avatar.jsonl` and render error kinds (contracts/events.md §3-§4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from ai_live.core.events import EventBus, avatar_mode_event, lipsync_health_event, show_error_event
from ai_live.core.models import AvatarModeState, LipsyncHealth, Milestone, RenderTurnStats, TurnOutcome, Utterance
from ai_live.director.session_log import (
    AVATAR_FILE,
    RENDER_ERROR_KINDS,
    SessionLog,
    avatar_mode_record,
    lipsync_health_record,
    utterance_record,
)

AT = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


def _utt() -> Utterance:
    utt = Utterance(utterance_id="u1", comment_id="c1", catalog_version="v1", outcome=TurnOutcome.COMPLETED)
    utt.mark(Milestone.COMMENT_RECEIVED, 1.0)
    utt.mark(Milestone.AVATAR_FIRST_FRAME, 2.5)
    return utt


def test_utterance_record_adds_render_fields_for_lipsync_turn():
    render = RenderTurnStats(
        utterance_id="u1",
        mode="livetalking",
        clips_used=["talk_01"],
        frames=50,
        render_fps=24.6,
        infer_fps=31.2,
        mouth_method="w2l",
    )
    record = utterance_record(_utt(), "m", render=render)
    assert record["render_fps"] == 24.6
    assert record["infer_fps"] == 31.2
    assert record["clips_used"] == ["talk_01"]
    assert record["mouth_method"] == "w2l"


def test_utterance_record_static_turn_keeps_old_shape():
    record = utterance_record(_utt(), "m")
    assert not {"render_fps", "infer_fps", "clips_used"} & set(record)


def test_render_error_kinds():
    assert {
        "timeout",
        "host_unavailable",
        "lipsync_unavailable",
        "vram_oom",
        "inference_failed",
        "bad_audio",
        "renderer_restarted",
    } <= RENDER_ERROR_KINDS


def test_avatar_mode_record():
    state = AvatarModeState("livetalking", "static", "render_errors", 2, "u9", AT)
    record = avatar_mode_record(state)
    assert record["kind"] == "mode"
    assert record["active"] == "static"
    assert record["reason"] == "render_errors"
    assert record["changed_at"] == AT.isoformat()
    assert "ts" in record


def test_lipsync_health_record_carries_peak_vram():
    health = LipsyncHealth(connected=True, boot_id="b1", vram_used_mb=2100, infer_fps=30.0, updated_at=AT)
    record = lipsync_health_record(health, vram_peak_mb=2600)
    assert record["kind"] == "health"
    assert record["vram_used_mb"] == 2100
    assert record["vram_peak_mb"] == 2600
    assert record["connected"] is True


@pytest.mark.anyio
async def test_record_avatar_writes_mode_and_health_events(tmp_path):
    log = await SessionLog.open(tmp_path, "s1")
    bus = EventBus()
    sub = bus.subscribe()
    secret = "AIza" + "Q" * 35
    bus.publish(avatar_mode_event(AvatarModeState("livetalking", "livetalking")))
    bus.publish(show_error_event(step="llm", kind="timeout", message="x"))  # not an avatar event: skipped
    bus.publish(lipsync_health_event(LipsyncHealth(connected=False, last_error=f"vram_oom {secret}", updated_at=AT)))
    sub.close()
    await log.record_avatar(sub)
    await log.close()

    lines = [json.loads(line) for line in (tmp_path / "s1" / AVATAR_FILE).read_text(encoding="utf-8").splitlines()]
    assert [line["kind"] for line in lines] == ["mode", "health"]
    assert lines[0]["configured"] == "livetalking"
    assert secret not in lines[1]["last_error"]
