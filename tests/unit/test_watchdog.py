"""007 T027: the pure `ShowWatchdog` rules (research R1-R3, R9) over a fake clock: no app, no bus, no sleeping."""

from __future__ import annotations

import pytest

from ai_live.core.models import HostStatus
from ai_live.ops.watchdog import (
    COVERED_BY,
    OPERATOR_ACTION,
    AlertChange,
    AlertKind,
    AlertLevel,
    ShowWatchdog,
    WatchdogThresholds,
)

SHOW = "show-1"
K = AlertKind


def make(*, lipsync: bool = False, host: bool = True, **thresholds: float) -> ShowWatchdog:
    w = ShowWatchdog(WatchdogThresholds(**thresholds), lipsync=lipsync, wall=lambda: "2026-11-13T00:00:00.000Z")
    w.on_host_connection(host, 0.0)
    if lipsync:
        w.on_avatar_mode("livetalking", 0.0)
        w.on_lipsync_health(True, 0.0)
    return w


def running(w: ShowWatchdog, now: float = 0.0, mode: str = "normal") -> list[AlertChange]:
    return w.on_show_state(SHOW, "running", mode, now)


def say(w: ShowWatchdog, uid: str, start: float, end: float, text: str = "Câu chào") -> list[AlertChange]:
    """A sentence handed over, heard at `start` and finished at `end`; returns every change on the way."""
    return [
        *w.on_sentence(uid, 0, text, start),
        *w.on_playback_started(uid, 0, text, start),
        *w.tick((start + end) / 2),
        *w.on_playback_ended(uid, 0, end),
    ]


def kinds(changes: list[AlertChange], event: str = "open") -> list[AlertKind]:
    return [c.alert.kind for c in changes if c.event == event]


def open_kinds(w: ShowWatchdog) -> set[AlertKind]:
    return {a.kind for a in w.open_alerts}


def beat(frames: int | None, at: float, **fields) -> HostStatus:
    message = {"frames": frames, "audio": "running", "video_muted": False, "video_paused": False, "visible": True}
    return HostStatus.from_message({**message, **fields}, at)


# ---------- no show, no alerts ----------


def test_nothing_is_watched_without_a_show():
    w = make(host=False)
    assert w.tick(100.0) == []
    assert w.on_sentence("u", 0, "x", 100.0) == []
    assert w.tick(200.0) == []
    assert w.open_alerts == []


def test_an_idle_or_ended_show_is_not_watched():
    w = make()
    assert w.on_show_state(SHOW, "idle", "normal", 0.0) == []
    assert w.tick(60.0) == []
    running(w, 60.0)
    w.on_show_state(SHOW, "ended", "normal", 61.0)
    assert w.tick(120.0) == []


# ---------- silence (R2, R3) ----------


def test_silence_opens_after_the_threshold_and_closes_when_a_sentence_starts():
    w = make()
    assert running(w, 0.0) == []
    assert w.tick(5.0) == []  # not yet past 5 s
    opened = w.tick(5.25)
    assert kinds(opened) == [K.SILENCE]
    alert = opened[0].alert
    assert alert.level is AlertLevel.WARNING
    assert alert.state == "open" and alert.show_id == SHOW
    assert alert.message == "Host im lặng 5 giây"
    assert "15 giây" in alert.action
    closed = w.on_playback_started("u1", 0, "Xin chào", 7.0)
    assert kinds(closed, "close") == [K.SILENCE]
    done = closed[0].alert
    assert done.close_reason == "cleared"
    assert done.seconds == 7.0  # from the start of the gap, not from the threshold
    assert done.ended_at is not None and done.state == "closed"
    assert w.open_alerts == []


def test_no_silence_while_a_sentence_is_playing():
    w = make()
    running(w)
    w.on_sentence("long", 0, "Một câu rất dài", 1.0)
    w.on_playback_started("long", 0, "Một câu rất dài", 1.0)
    assert w.tick(30.0) == []
    w.on_playback_ended("long", 0, 30.0)
    assert w.tick(35.0) == []
    assert kinds(w.tick(35.5)) == [K.SILENCE]


def test_silence_names_the_last_sentence_heard():
    w = make()
    running(w)
    long_text = "Sản phẩm " * 30
    say(w, "u1", 1.0, 2.0, long_text)
    alert = kinds_alert = w.tick(8.0)[0].alert
    assert kinds_alert.kind is K.SILENCE
    assert alert.utterance_id == "u1"
    assert alert.text is not None and len(alert.text) == 120 and alert.text.endswith("…")


def test_auto_skip_once_then_operator():
    """R3: one skip at `autoskip_s`; a further `silence_s` without speech asks for a person; never a second skip."""
    w = make()
    running(w)
    w.tick(6.0)
    assert w.tick(14.9) == []
    skipped = w.tick(15.0)
    assert [c.event for c in skipped] == ["auto_skip"]
    alert = skipped[0].alert
    assert alert.auto_action == "skip"
    assert alert.message == "Host im lặng 15 giây, đã tự bỏ câu đang kẹt"
    assert alert.level is AlertLevel.WARNING
    assert w.tick(19.9) == []
    raised = w.tick(20.0)
    assert [c.event for c in raised] == ["level"]
    assert raised[0].alert.level is AlertLevel.OPERATOR
    assert raised[0].alert.action == OPERATOR_ACTION
    assert "20 giây" in raised[0].alert.message
    for t in range(21, 120):
        assert w.tick(float(t)) == []
    assert open_kinds(w) == {K.SILENCE}


def test_a_sentence_after_the_skip_ends_the_stretch_and_a_new_gap_can_skip_again():
    w = make()
    running(w)
    w.tick(6.0)
    assert [c.event for c in w.tick(15.0)] == ["auto_skip"]
    say(w, "u2", 16.0, 18.0)
    assert w.open_alerts == []
    w.tick(23.5)
    assert [c.event for c in w.tick(33.0)] == ["auto_skip"]


def test_the_alert_changes_are_copies():
    w = make()
    running(w)
    opened = w.tick(6.0)[0].alert
    w.tick(15.0)
    assert opened.auto_action is None
    assert w.open_alerts[0].auto_action == "skip"


def test_thresholds_come_from_settings(settings):
    s = settings.model_copy(
        update={
            "watchdog_silence_s": 2.0,
            "watchdog_frozen_s": 1.0,
            "watchdog_autoskip_s": 4.0,
            "watchdog_audio_ack_s": 0.5,
            "watchdog_audio_ack_lipsync_s": 1.5,
        }
    )
    t = WatchdogThresholds.from_settings(s)
    assert (t.silence_s, t.frozen_s, t.autoskip_s, t.audio_ack_s, t.audio_ack_lipsync_s) == (2.0, 1.0, 4.0, 0.5, 1.5)
    w = ShowWatchdog(t)
    w.on_host_connection(True, 0.0)
    running(w)
    assert kinds(w.tick(2.1)) == [K.SILENCE]
    assert [c.event for c in w.tick(4.0)] == ["auto_skip"]


# ---------- pause and end ----------


def test_pause_closes_the_flow_alerts_and_restarts_the_silence_count():
    w = make()
    running(w)
    w.tick(6.0)
    paused = w.on_show_state(SHOW, "paused", "normal", 7.0)
    assert kinds(paused, "close") == [K.SILENCE]
    assert paused[0].alert.close_reason == "paused"
    assert w.tick(60.0) == []  # a long pause is not silence
    assert running(w, 60.0) == []
    assert w.tick(65.0) == []
    assert kinds(w.tick(65.5)) == [K.SILENCE]


def test_pause_keeps_the_root_alerts():
    w = make()
    running(w)
    w.on_host_connection(False, 2.0)
    w.on_show_state(SHOW, "paused", "normal", 3.0)
    assert open_kinds(w) == {K.HOST_CLOSED}


def test_show_end_closes_everything():
    w = make()
    running(w, mode="fallback")
    w.on_host_connection(False, 1.0)
    assert open_kinds(w) == {K.HOST_CLOSED, K.FALLBACK_MODE}
    ended = w.on_show_state(SHOW, "ended", "fallback", 2.0)
    assert sorted(kinds(ended, "close")) == sorted([K.HOST_CLOSED, K.FALLBACK_MODE])
    assert {c.alert.close_reason for c in ended} == {"show_ended"}
    assert w.open_alerts == []


def test_a_new_show_starts_clean():
    w = make()
    running(w)
    w.tick(6.0)
    changes = w.on_show_state("show-2", "running", "normal", 7.0)
    assert kinds(changes, "close") == [K.SILENCE]
    assert changes[0].alert.show_id == SHOW
    assert w.tick(12.0) == []
    assert w.tick(12.5)[0].alert.show_id == "show-2"


# ---------- host_closed and covering ----------


def test_host_closed_is_an_operator_alert_that_covers_silence():
    w = make()
    running(w)
    w.tick(6.0)
    lost = w.on_host_connection(False, 7.0)
    assert kinds(lost) == [K.HOST_CLOSED]
    assert kinds(lost, "close") == [K.SILENCE]
    assert [c.alert.close_reason for c in lost if c.event == "close"] == ["covered"]
    host = w.open_alerts[0]
    assert host.level is AlertLevel.OPERATOR
    assert host.message == "Màn hình host đã đóng"
    assert "/host" in host.action
    # Covered: no silence while the root stays open, however long.
    assert w.tick(60.0) == []
    back = w.on_host_connection(True, 61.0)
    assert kinds(back, "close") == [K.HOST_CLOSED]
    assert back[0].alert.close_reason == "cleared"
    assert back[0].alert.seconds == 54.0
    # The silence count starts again from the reconnect.
    assert w.tick(66.0) == []
    assert kinds(w.tick(66.5)) == [K.SILENCE]


def test_no_host_tab_when_the_show_starts_is_an_alert():
    w = make(host=False)
    assert kinds(running(w)) == [K.HOST_CLOSED]


def test_covering_table_matches_research_r2():
    assert COVERED_BY[K.SILENCE] == {K.HOST_CLOSED, K.FORK_LOST, K.FROZEN, K.AUDIO_MISSING}
    assert COVERED_BY[K.FROZEN] == {K.HOST_CLOSED, K.FORK_LOST, K.STATIC_MODE}
    assert COVERED_BY[K.FORK_LOST] == COVERED_BY[K.STATIC_MODE] == COVERED_BY[K.AUDIO_MISSING] == {K.HOST_CLOSED}
    assert COVERED_BY[K.HOST_CLOSED] == COVERED_BY[K.FALLBACK_MODE] == frozenset()


# ---------- fork_lost, static_mode, fallback_mode ----------


def test_fork_lost_covers_frozen_and_silence():
    w = make(lipsync=True)
    running(w)
    w.on_host_status(beat(100, 1.0))
    w.on_host_status(beat(100, 4.5))
    assert open_kinds(w) == {K.FROZEN}
    w.tick(6.0)
    assert open_kinds(w) == {K.FROZEN}  # silence sits under frozen
    lost = w.on_lipsync_health(False, 7.0)
    assert kinds(lost) == [K.FORK_LOST]
    assert kinds(lost, "close") == [K.FROZEN]
    assert w.open_alerts[0].level is AlertLevel.OPERATOR
    assert "fork" in w.open_alerts[0].message
    assert w.tick(40.0) == []
    back = w.on_lipsync_health(True, 41.0)
    assert kinds(back, "close") == [K.FORK_LOST]


def test_fork_and_static_mode_only_matter_in_lipsync_mode():
    w = make()
    running(w)
    w.on_lipsync_health(False, 1.0)
    w.on_avatar_mode("static", 1.0)
    assert w.open_alerts == []


def test_static_fallback_is_a_warning_until_lipsync_returns():
    w = make(lipsync=True)
    running(w)
    opened = w.on_avatar_mode("static", 2.0)
    assert kinds(opened) == [K.STATIC_MODE]
    assert opened[0].alert.level is AlertLevel.WARNING
    assert opened[0].alert.message == "Nhân vật nhép miệng lỗi, đang dùng ảnh tĩnh"
    assert "Bật lại nhân vật nhép miệng" in opened[0].alert.action
    assert kinds(w.on_avatar_mode("livetalking", 9.0), "close") == [K.STATIC_MODE]


def test_fallback_mode_follows_the_show_mode():
    w = make()
    opened = running(w, mode="fallback")
    assert kinds(opened) == [K.FALLBACK_MODE]
    assert "video dự phòng" in opened[0].alert.action
    assert running(w, 1.0, mode="verbatim") != []  # leaving fallback closes it
    assert w.open_alerts == []


# ---------- frozen (R9) ----------


def test_frozen_needs_two_heartbeats_with_the_same_frames():
    w = make(lipsync=True)
    running(w)
    assert w.on_host_status(beat(100, 1.0)) == []
    # Only time passing, with no newer heartbeat, never says the picture froze.
    assert K.FROZEN not in kinds(w.tick(9.0))
    w2 = make(lipsync=True)
    running(w2)
    w2.on_host_status(beat(100, 1.0))
    assert w2.on_host_status(beat(100, 4.0)) == []  # exactly 3 s: not over
    frozen = w2.on_host_status(beat(100, 4.2))
    assert kinds(frozen) == [K.FROZEN]
    assert frozen[0].alert.message == "Hình trên tab host đứng 3 giây"
    cleared = w2.on_host_status(beat(130, 5.2))
    assert kinds(cleared, "close") == [K.FROZEN]


def test_frames_moving_is_never_frozen():
    w = make(lipsync=True)
    running(w)
    for i in range(30):
        w.on_host_status(beat(25 * i, float(i)))
    assert K.FROZEN not in open_kinds(w)


def test_missing_frames_reset_the_frozen_tracking():
    w = make(lipsync=True)
    running(w)
    w.on_host_status(beat(100, 1.0))
    w.on_host_status(beat(None, 2.0))
    assert w.on_host_status(beat(100, 4.5)) == []
    assert K.FROZEN not in kinds(w.on_host_status(beat(100, 7.0)))
    assert K.FROZEN in kinds(w.on_host_status(beat(100, 7.6)))


def test_frozen_is_not_watched_on_the_still_image():
    w = make()
    running(w)
    w.on_host_status(beat(100, 1.0))
    assert K.FROZEN not in kinds(w.on_host_status(beat(100, 9.0)))
    w2 = make(lipsync=True)
    running(w2)
    w2.on_avatar_mode("static", 0.5)
    w2.on_host_status(beat(100, 1.0))
    w2.on_host_status(beat(100, 9.0))
    assert K.FROZEN not in open_kinds(w2) and K.STATIC_MODE in open_kinds(w2)


# ---------- audio_missing (R1) ----------


def test_a_sentence_never_heard_is_audio_missing():
    w = make()
    running(w)
    w.on_sentence("u1", 0, "Câu không ra tiếng", 1.0)
    assert w.tick(4.0) == []
    missing = w.tick(4.25)
    assert kinds(missing) == [K.AUDIO_MISSING]
    alert = missing[0].alert
    assert alert.utterance_id == "u1" and alert.text == "Câu không ra tiếng"
    assert alert.message.startswith("Có thể mất tiếng ở tab host")
    assert "3 giây" in alert.message
    # It covers silence while open.
    assert w.tick(30.0) == []
    heard = w.on_playback_started("u1", 0, "Câu không ra tiếng", 31.0)
    assert kinds(heard, "close") == [K.AUDIO_MISSING]


def test_lipsync_waits_for_the_fork_start_lag_before_audio_missing():
    # 007 T054: the fork's normal ~3 s start lag (3.03 s, 3.16 s) opened and closed alerts within 3 ms.
    w = make(lipsync=True, silence_s=20.0, autoskip_s=30.0)
    running(w)
    w.on_sentence("u1", 0, "Câu nhép miệng", 1.0)
    assert w.tick(4.2) == []
    assert w.on_playback_started("u1", 0, "Câu nhép miệng", 4.25) == []
    w.on_playback_ended("u1", 0, 6.0)
    w.on_sentence("u2", 0, "Câu kẹt ở fork", 6.5)
    assert w.tick(12.5) == []
    missing = w.tick(12.75)
    assert kinds(missing) == [K.AUDIO_MISSING]
    assert "6 giây" in missing[0].alert.message


def test_static_fallback_in_lipsync_mode_uses_the_still_image_deadline():
    w = make(lipsync=True)
    w.on_avatar_mode("static", 0.0)
    running(w)
    w.on_sentence("u1", 0, "x", 1.0)
    assert kinds(w.tick(4.25)) == [K.AUDIO_MISSING]


def test_sentence_reported_after_its_own_start_is_not_unheard():
    w = make()
    running(w)
    w.on_playback_started("u1", 0, "x", 1.0)
    w.on_sentence("u1", 0, "x", 1.01)
    w.on_playback_ended("u1", 0, 2.0)
    assert w.tick(5.0) == []


def test_a_cut_sentence_is_not_unheard():
    w = make()
    running(w)
    w.on_sentence("u1", 0, "x", 1.0)
    w.on_playback_stopped(1.5)
    assert w.tick(5.0) == []


def test_heartbeat_with_suspended_audio_is_audio_missing_on_the_still_image():
    w = make()
    running(w)
    missing = w.on_host_status(beat(None, 1.0, audio="suspended"))
    assert kinds(missing) == [K.AUDIO_MISSING]
    assert "không phát được tiếng" in missing[0].alert.message
    assert kinds(w.on_host_status(beat(None, 2.0)), "close") == [K.AUDIO_MISSING]


def test_heartbeat_with_a_muted_video_is_audio_missing_in_lipsync_mode():
    w = make(lipsync=True)
    running(w)
    # The AudioContext is not the sound path with the lip-sync video.
    assert w.on_host_status(beat(10, 1.0, audio="suspended")) == []
    assert kinds(w.on_host_status(beat(20, 2.0, video_muted=True))) == [K.AUDIO_MISSING]
    assert kinds(w.on_host_status(beat(30, 3.0)), "close") == [K.AUDIO_MISSING]


def test_pause_closes_audio_missing_and_frozen():
    w = make(lipsync=True)
    running(w)
    w.on_host_status(beat(100, 1.0, video_paused=True))
    w.on_host_status(beat(100, 5.0, video_paused=True))
    assert open_kinds(w) == {K.FROZEN, K.AUDIO_MISSING}
    paused = w.on_show_state(SHOW, "paused", "normal", 6.0)
    assert sorted(kinds(paused, "close")) == sorted([K.FROZEN, K.AUDIO_MISSING])
    assert {c.alert.close_reason for c in paused} == {"paused"}


@pytest.mark.parametrize("kind", list(AlertKind))
def test_every_kind_has_vietnamese_words(kind: AlertKind):
    w = make(lipsync=True)
    signal = type("S", (), {"since": 0.0, "detail": None})()
    assert w._message(kind, signal, 6.0)
    assert w._action(kind)


# ---------- 006 T021: OUTPUT_MODE=obs (contracts/api.md §8) ----------


def make_obs(*, lipsync: bool = False, role: str | None = "obs", **thresholds: float) -> ShowWatchdog:
    w = ShowWatchdog(
        WatchdogThresholds(**thresholds), lipsync=lipsync, output_mode="obs", wall=lambda: "2026-11-13T00:00:00.000Z"
    )
    w.on_host_connection(role is not None, 0.0, role)
    if lipsync:
        w.on_avatar_mode("livetalking", 0.0)
        w.on_lipsync_health(True, 0.0)
    return w


def test_obs_mode_a_host_tab_playing_is_output_lost():
    w = make_obs(role="host")
    assert kinds(running(w)) == [K.HOST_CLOSED]
    alert = w.open_alerts[0]
    assert alert.message == "Nguồn OBS đã ngắt"
    assert "Refresh" in alert.action and "/host" in alert.action
    # The OBS source connects and takes over: the alert clears.
    back = w.on_host_connection(True, 2.0, "obs")
    assert kinds(back, "close") == [K.HOST_CLOSED]


def test_obs_mode_source_closes_then_reconnects():
    w = make_obs()
    running(w)
    lost = w.on_host_connection(False, 1.0, None)
    assert kinds(lost) == [K.HOST_CLOSED]
    assert lost[0].alert.message == "Nguồn OBS đã ngắt"
    assert lost[0].alert.level is AlertLevel.OPERATOR
    back = w.on_host_connection(True, 3.0, "obs")
    assert kinds(back, "close") == [K.HOST_CLOSED]
    assert back[0].alert.close_reason == "cleared"


def test_obs_mode_stale_heartbeat_is_output_lost_and_a_beat_clears_it():
    w = make_obs(host_stale_s=10.0, silence_s=100.0)
    running(w)
    w.on_host_status(beat(None, 2.0))
    assert w.tick(12.0) == []
    stale = w.tick(12.5)
    assert kinds(stale) == [K.HOST_CLOSED]
    assert stale[0].alert.message.startswith("Nguồn OBS đã ngắt")
    assert "nhịp" in stale[0].alert.message
    cleared = w.on_host_status(beat(None, 13.0))
    assert kinds(cleared, "close") == [K.HOST_CLOSED]
    assert w.open_alerts == []


def test_obs_mode_stale_counts_from_the_connect_when_no_beat_came():
    w = make_obs(host_stale_s=10.0, silence_s=100.0)
    running(w)
    assert w.tick(10.0) == []
    assert kinds(w.tick(10.5)) == [K.HOST_CLOSED]


def test_meet_mode_has_no_stale_rule():
    w = make(silence_s=100.0)
    running(w)
    w.on_host_status(beat(None, 1.0))
    assert w.tick(90.0) == []
    assert w.open_alerts == []


def test_obs_mode_frozen_and_audio_wording():
    w = make_obs(lipsync=True, frozen_s=3.0, silence_s=100.0, host_stale_s=100.0)
    running(w)
    w.on_host_status(beat(10, 1.0))
    changes = w.on_host_status(beat(10, 4.5))
    frozen = [c.alert for c in changes if c.event == "open" and c.alert.kind is K.FROZEN][0]
    assert frozen.message.startswith("Hình trong nguồn OBS đứng")
    assert "Refresh" in frozen.action and "Meet" not in frozen.action
    muted = w.on_host_status(beat(11, 5.0, video_muted=True))
    audio = [c.alert for c in muted if c.event == "open" and c.alert.kind is K.AUDIO_MISSING][0]
    assert audio.message.startswith("Có thể mất tiếng ở nguồn OBS")
    assert "Control audio via OBS" in audio.action


def test_meet_mode_keeps_the_007_wording():
    w = make(lipsync=True, frozen_s=3.0, silence_s=100.0)
    running(w)
    w.on_host_status(beat(10, 1.0))
    w.on_host_status(beat(10, 4.5))
    w.on_host_status(beat(11, 5.0, video_muted=True))
    by_kind = {a.kind: a for a in w.open_alerts}
    assert by_kind[K.AUDIO_MISSING].message.startswith("Có thể mất tiếng ở tab host")
    assert "Meet" in by_kind[K.AUDIO_MISSING].action
    w2 = make(lipsync=True, frozen_s=3.0, silence_s=100.0)
    running(w2)
    w2.on_host_status(beat(10, 1.0))
    w2.on_host_status(beat(10, 4.5))
    frozen = [a for a in w2.open_alerts if a.kind is K.FROZEN][0]
    assert frozen.message.startswith("Hình trên tab host đứng")
    assert "Meet" in frozen.action


def test_meet_mode_a_replacing_page_leaves_no_host_closed():
    # The renderer publishes the old page's close, then the new page's ready (4000 replace).
    w = make()
    running(w)
    w.on_host_connection(False, 1.0, None)
    w.on_host_connection(True, 1.1, "host")
    assert K.HOST_CLOSED not in open_kinds(w)


def test_thresholds_read_the_stale_setting(settings):
    s = settings.model_copy(update={"watchdog_host_stale_s": 7.0})
    assert WatchdogThresholds.from_settings(s).host_stale_s == 7.0
