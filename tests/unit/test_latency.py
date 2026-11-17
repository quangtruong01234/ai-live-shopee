"""T071 latency aggregation (US3; FR-018, FR-019, research R12, data-model.md §4)."""

from __future__ import annotations

import statistics

import pytest

from ai_live.core.models import Milestone, TurnOutcome, Utterance
from ai_live.director.latency import NOT_ENOUGH_SAMPLES, STEP_NAMES, LatencyTracker

M = Milestone


def _turn(
    uid: str,
    *,
    received: float = 0.0,
    queue_wait: float = 0.1,
    first_sentence: float = 1.0,
    first_chunk: float = 0.2,
    first_frame: float = 0.3,
    outcome: TurnOutcome = TurnOutcome.COMPLETED,
) -> Utterance:
    """Marks given as step durations, so expected values stay readable."""
    utt = Utterance(utterance_id=uid, comment_id=f"c-{uid}", catalog_version="v1", outcome=outcome)
    utt.mark(M.COMMENT_RECEIVED, received)
    utt.mark(M.TURN_STARTED, received + queue_wait)
    utt.mark(M.FLOOR_ACQUIRED, received + queue_wait)  # no show: the player takes the floor at once
    utt.mark(M.LLM_FIRST_SENTENCE, received + first_sentence)
    utt.mark(M.TTS_FIRST_CHUNK, received + first_sentence + first_chunk)
    utt.mark(M.AVATAR_FIRST_FRAME, received + first_sentence + first_chunk + first_frame)
    return utt


def test_single_turn_step_durations():
    tracker = LatencyTracker()
    tracker.record(_turn("u1", received=10.0, queue_wait=0.1, first_sentence=1.0, first_chunk=0.2, first_frame=0.3))
    s = tracker.summary()

    assert s.completed == 1
    assert set(s.steps) == set(STEP_NAMES)
    assert s.steps["total"].median == pytest.approx(1.5)  # avatar_first_frame - comment_received
    assert s.steps["queue_wait"].median == pytest.approx(0.1)  # turn_started - comment_received
    assert s.steps["received_to_first_sentence"].median == pytest.approx(1.0)
    assert s.steps["first_sentence_to_tts_first_chunk"].median == pytest.approx(0.2)
    assert s.steps["tts_first_chunk_to_first_frame"].median == pytest.approx(0.3)
    for stats in s.steps.values():
        assert stats.count == 1


def test_median_and_p95_with_20_samples():
    tracker = LatencyTracker()
    totals = [1.0 + 0.1 * i for i in range(25)]
    for i, total in enumerate(totals):
        tracker.record(_turn(f"u{i}", first_sentence=total - 0.5, first_chunk=0.2, first_frame=0.3))
    total = tracker.summary().steps["total"]

    assert total.count == 25
    assert total.median == pytest.approx(statistics.median(totals), abs=1e-3)
    assert total.p95 == pytest.approx(statistics.quantiles(totals, n=20)[18], abs=1e-3)
    assert total.note is None


def test_p95_per_step_uses_quantiles():
    tracker = LatencyTracker()
    chunks = [0.05 * (i + 1) for i in range(20)]
    for i, chunk in enumerate(chunks):
        tracker.record(_turn(f"u{i}", first_chunk=chunk))
    step = tracker.summary().steps["first_sentence_to_tts_first_chunk"]
    assert step.count == 20
    assert step.p95 == pytest.approx(statistics.quantiles(chunks, n=20)[18], abs=1e-3)


def test_under_20_samples_reports_not_enough():
    tracker = LatencyTracker()
    for i in range(19):
        tracker.record(_turn(f"u{i}"))
    total = tracker.summary().steps["total"]
    assert total.count == 19
    assert total.median is not None
    assert total.p95 is None
    assert total.note == NOT_ENOUGH_SAMPLES == "chưa đủ mẫu"


def test_empty_tracker():
    s = LatencyTracker().summary()
    assert s.completed == s.errors == s.skipped == 0
    for stats in s.steps.values():
        assert stats.count == 0
        assert stats.median is None and stats.p95 is None
        assert stats.note == NOT_ENOUGH_SAMPLES


def test_error_and_skipped_turns_not_counted():
    tracker = LatencyTracker()
    tracker.record(_turn("ok", first_sentence=1.0, first_chunk=0.2, first_frame=0.3))
    # Huge durations: if counted, they would move the median.
    tracker.record(_turn("err", first_sentence=50.0, outcome=TurnOutcome.ERROR))
    tracker.record(_turn("skip", first_sentence=60.0, outcome=TurnOutcome.SKIPPED))
    partial = Utterance(utterance_id="err2", comment_id="c", catalog_version="v1", outcome=TurnOutcome.ERROR)
    partial.mark(M.COMMENT_RECEIVED, 0.0)
    tracker.record(partial)
    s = tracker.summary()

    assert s.completed == 1
    assert s.errors == 2
    assert s.skipped == 1
    assert s.steps["total"].count == 1
    assert s.steps["total"].median == pytest.approx(1.5)


def test_in_progress_turn_ignored():
    tracker = LatencyTracker()
    tracker.record(_turn("u", outcome=TurnOutcome.IN_PROGRESS))
    s = tracker.summary()
    assert s.completed == s.errors == s.skipped == 0
    assert s.steps["total"].count == 0


def test_idle_only_set_uses_queue_wait_below_0_3_s():
    tracker = LatencyTracker()
    tracker.record(_turn("idle1", queue_wait=0.05, first_sentence=1.0))  # total 1.5
    tracker.record(_turn("idle2", queue_wait=0.29, first_sentence=2.0))  # total 2.5
    tracker.record(_turn("edge", queue_wait=0.3, first_sentence=8.0))  # not strictly below 0.3 s
    tracker.record(_turn("busy", queue_wait=5.0, first_sentence=9.0))

    everything = tracker.summary()
    idle = tracker.summary(idle_only=True)

    assert everything.idle_only is False
    assert everything.steps["total"].count == 4
    assert idle.idle_only is True
    assert idle.steps["total"].count == 2
    assert idle.steps["total"].median == pytest.approx(2.0)
    assert idle.idle_completed == everything.idle_completed == 2
    # The "idle host only" row is always present, so the control page can show both rows.
    assert everything.idle_steps["total"].count == 2
    assert idle.steps == idle.idle_steps
    # Outcome counts describe the whole session in both modes.
    assert idle.completed == everything.completed == 4


def test_summary_json_shape():
    tracker = LatencyTracker()
    tracker.record(_turn("u1"))
    body = tracker.summary().to_json()
    assert set(body) >= {
        "idle_only",
        "idle_threshold_s",
        "min_samples",
        "completed",
        "errors",
        "skipped",
        "idle_completed",
        "steps",
        "idle_steps",
    }
    assert body["min_samples"] == 20
    assert body["idle_threshold_s"] == pytest.approx(0.3)
    assert list(body["steps"]) == list(STEP_NAMES)
    assert set(body["steps"]["total"]) == {"count", "median", "p95", "note"}


def test_mark_and_finish_by_utterance_id():
    tracker = LatencyTracker()
    tracker.mark("u1", M.COMMENT_RECEIVED, 1.0)
    tracker.mark("u1", M.TURN_STARTED, 1.1)
    tracker.mark("u1", M.LLM_FIRST_SENTENCE, 2.0)
    tracker.mark("u1", M.LLM_FIRST_SENTENCE, 9.0)  # later sentences do not move the milestone
    tracker.mark("u1", M.TTS_FIRST_CHUNK, 2.1)
    tracker.mark("u1", M.AVATAR_FIRST_FRAME, 2.4)
    tracker.finish("u1", TurnOutcome.COMPLETED)
    s = tracker.summary()
    assert s.completed == 1
    assert s.steps["total"].median == pytest.approx(1.4)
    assert s.steps["received_to_first_sentence"].median == pytest.approx(1.0)


def test_scripted_sentence_is_not_a_reply_turn():
    """004 research R2: a scripted sentence has no comment_received; it goes to ShowStats, not the 001 summary."""
    tracker = LatencyTracker()
    tracker.record(_turn("u1"))
    scripted = Utterance(
        utterance_id="s1",
        comment_id=None,
        catalog_version="v1",
        outcome=TurnOutcome.COMPLETED,
        segment_id="seg-1",
        show_id="show-1",
    )
    scripted.mark(M.SEGMENT_REQUESTED, 0.0)
    scripted.mark(M.LLM_FIRST_SENTENCE, 1.0)
    scripted.mark(M.TTS_FIRST_CHUNK, 1.1)
    scripted.mark(M.AVATAR_FIRST_FRAME, 1.2)
    tracker.mark("s1", M.TTS_FIRST_CHUNK, 1.1)

    assert tracker.record(scripted) is None
    s = tracker.summary()
    assert s.completed == 1
    assert [t.utterance_id for t in tracker.turns] == ["u1"]
    assert s.steps["total"].count == 1


# ---------- Feature 005: render stats per turn (data-model §5, FR-020, T012) ----------


def _render(uid: str, render_fps: float | None = 25.0, infer_fps: float | None = 30.0, clips=("talk_01",)):
    from ai_live.core.models import RenderTurnStats

    return RenderTurnStats(
        utterance_id=uid,
        mode="livetalking",
        clips_used=list(clips),
        frames=50,
        render_fps=render_fps,
        infer_fps=infer_fps,
    )


def test_turn_latency_render_fields_default_none():
    tracker = LatencyTracker()
    turn = tracker.record(_turn("u1"))
    assert turn is not None
    assert (turn.render_fps, turn.infer_fps, turn.clips_used) == (None, None, None)


def test_record_copies_render_stats():
    tracker = LatencyTracker()
    turn = tracker.record(_turn("u1"), render=_render("u1", 24.5, 31.0, ("talk_02", "talk_01")))
    assert turn is not None
    assert turn.render_fps == pytest.approx(24.5)
    assert turn.infer_fps == pytest.approx(31.0)
    assert turn.clips_used == ["talk_02", "talk_01"]


def test_render_fps_stats_skip_turns_without_value():
    tracker = LatencyTracker()
    tracker.record(_turn("u1"), render=_render("u1", 20.0))
    tracker.record(_turn("u2"), render=_render("u2", 24.0))
    tracker.record(_turn("u3"))  # static turn: no render stats
    tracker.record(_turn("u4"), render=_render("u4", None))
    s = tracker.summary()
    assert s.render_fps.count == 2
    assert s.render_fps.median == pytest.approx(22.0)
    assert s.render_fps.p95 is None
    assert s.render_fps.note == NOT_ENOUGH_SAMPLES
    # render_fps is a rate, not a duration step: the step table is unchanged.
    assert set(s.steps) == set(STEP_NAMES)


def test_render_fps_p95_after_20_samples():
    tracker = LatencyTracker()
    values = [15.0 + 0.5 * i for i in range(20)]
    for i, fps in enumerate(values):
        tracker.record(_turn(f"u{i}"), render=_render(f"u{i}", fps))
    stats = tracker.summary().render_fps
    assert stats.count == 20
    assert stats.p95 == pytest.approx(statistics.quantiles(values, n=20)[18], abs=1e-3)
    assert stats.note is None


def test_render_fps_only_from_completed_turns():
    tracker = LatencyTracker()
    tracker.record(_turn("u1", outcome=TurnOutcome.ERROR), render=_render("u1", 5.0))
    assert tracker.summary().render_fps.count == 0


def test_summary_json_has_render_fps():
    tracker = LatencyTracker()
    tracker.record(_turn("u1"), render=_render("u1", 25.0))
    body = tracker.summary().to_json()
    assert body["render_fps"] == {"count": 1, "median": 25.0, "p95": None, "note": NOT_ENOUGH_SAMPLES}
    assert list(body["steps"]) == list(STEP_NAMES)


def test_attach_render_fills_a_recorded_turn():
    # LIVETALKING_LEAD_S: the turn is recorded before the fork's figures for its last sentence are in (005 R15).
    tracker = LatencyTracker()
    tracker.record(_turn("u1"))
    tracker.record(_turn("u2"))
    assert tracker.attach_render("u1", _render("u1", 22.0, 30.0, ("talk_01",))) is True
    turn = tracker.turns[0]
    assert (turn.render_fps, turn.infer_fps, turn.clips_used) == (22.0, 30.0, ["talk_01"])
    assert tracker.summary().render_fps.count == 1
    assert tracker.attach_render("u9", _render("u9", 20.0)) is False
    assert tracker.attach_render("u2", None) is False


# --- floor_wait: a reply waiting for the scripted sentence being spoken (sửa lỗi 2026-11-17, data-model.md §4) ---


def test_wait_for_the_scripted_sentence_is_floor_wait_not_render():
    tracker = LatencyTracker()
    utt = _turn("u1", queue_wait=0.0, first_sentence=1.0, first_chunk=0.2, first_frame=2.5)
    utt.marks[M.FLOOR_ACQUIRED] = 1.2 + 2.2  # the scripted sentence ended 2.2 s after the first chunk
    tracker.record(utt)
    s = tracker.summary()

    assert s.steps["floor_wait"].median == pytest.approx(2.2)
    assert s.steps["tts_first_chunk_to_first_frame"].median == pytest.approx(0.3)
    assert s.steps["total"].median == pytest.approx(3.7)
    assert s.idle_completed == 0  # not an idle host, though queue_wait is 0


def test_floor_taken_before_the_first_chunk_is_no_wait():
    tracker = LatencyTracker()
    utt = _turn("u1", queue_wait=0.0, first_sentence=1.0, first_chunk=0.2, first_frame=0.3)
    utt.marks[M.FLOOR_ACQUIRED] = 0.01
    tracker.record(utt)
    s = tracker.summary()

    assert s.steps["floor_wait"].median == pytest.approx(0.0)
    assert s.steps["tts_first_chunk_to_first_frame"].median == pytest.approx(0.3)
    assert s.idle_completed == 1
