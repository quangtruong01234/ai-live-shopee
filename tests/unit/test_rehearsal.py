"""007 US3 T037: the rehearsal report over sample session logs (SC-005, data-model §4, FR-013…FR-016)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_live.ops import rehearsal as rh
from fixtures.session_logs import NORMAL_GAPS, AlertSpec, sentence_text, write_show_logs


def report_of(tmp_path: Path, **kwargs) -> rh.RehearsalReport:
    show = write_show_logs(tmp_path, **kwargs)
    return rh.build_report(rh.load_show_logs(show.directory, show.show_id))


# --- the five SC-005 sample logs ---


def test_a_passing_rehearsal(tmp_path: Path):
    report = report_of(tmp_path)
    assert report.criterion_3 is rh.Verdict.PASS
    assert report.criterion_4 is rh.Verdict.PASS
    assert report.ended_normally
    assert report.duration_s == pytest.approx(1830.0)
    assert report.gaps["counted"] == 40
    assert report.gaps["p95_s"] == pytest.approx(0.4)
    assert report.gaps["over_5s"] == []
    assert report.sentences["spoken"] == 41


def test_a_show_shorter_than_30_minutes_is_short(tmp_path: Path):
    report = report_of(tmp_path, duration_s=600.0)
    assert report.criterion_4 is rh.Verdict.SHORT
    assert report.criterion_3 is rh.Verdict.PASS


def test_a_7_second_gap_fails_criterion_3_and_names_the_sentence_before(tmp_path: Path):
    gaps = list(NORMAL_GAPS)
    gaps[10] = ("script", 7.0)
    report = report_of(tmp_path, gaps=gaps)
    assert report.criterion_3 is rh.Verdict.FAIL
    assert report.gaps["max_s"] == pytest.approx(7.0)
    [over] = report.gaps["over_5s"]
    assert over["seconds"] == pytest.approx(7.0)
    assert over["kind"] == "script"
    assert over["before_text"] == sentence_text(10)
    assert over["at"].startswith("2026-11-13T03:")


def test_a_long_pause_is_not_counted(tmp_path: Path):
    gaps = list(NORMAL_GAPS)
    gaps[20] = ("paused", 120.0)
    gaps[21] = ("fault", 9.0)
    report = report_of(tmp_path, gaps=gaps)
    assert report.criterion_3 is rh.Verdict.PASS
    assert report.gaps["counted"] == 38
    assert report.excluded_gaps == {
        "paused": {"count": 1, "total_s": 120.0},
        "fault": {"count": 1, "total_s": 9.0},
    }


def test_app_down_mid_show_still_reports_from_what_is_left(tmp_path: Path):
    report = report_of(tmp_path, summary=False)
    assert report.criterion_4 is rh.Verdict.FAIL
    assert not report.ended_normally
    assert report.gaps["counted"] == 40
    assert report.criterion_3 is rh.Verdict.PASS
    # The last line seen closes the window: the last gap, before the planned end of the show.
    assert report.ended_at is not None
    assert 1700 < report.duration_s < 1830
    assert any("không có tóm tắt cuối show" in note for note in report.notes)


def test_a_shutdown_end_is_not_a_normal_end(tmp_path: Path):
    report = report_of(tmp_path, ended_by="shutdown")
    assert report.criterion_4 is rh.Verdict.FAIL
    assert not report.ended_normally


# --- the extra rules ---


def test_no_gap_at_all_fails_criterion_3_for_lack_of_data(tmp_path: Path):
    report = report_of(tmp_path, gaps=())
    assert report.criterion_3 is rh.Verdict.FAIL
    assert report.gaps["counted"] == 0
    assert report.gaps["p95_s"] is None
    assert any("không đủ dữ liệu" in note for note in report.notes)


def test_few_gaps_still_get_a_p95_with_a_note(tmp_path: Path):
    report = report_of(tmp_path, gaps=(("script", 0.3),) * 4 + (("script", 1.2),), duration_s=1830.0)
    assert report.gaps["p95_s"] == pytest.approx(1.2)
    assert any("ít hơn 20" in note for note in report.notes)


def test_p95_over_1_5_seconds_fails_criterion_3(tmp_path: Path):
    gaps = [("script", 0.4)] * 30 + [("segment_boundary", 2.5)] * 10
    report = report_of(tmp_path, gaps=gaps)
    assert report.gaps["p95_s"] > 1.5
    assert report.gaps["over_5s"] == []
    assert report.criterion_3 is rh.Verdict.FAIL


def test_an_error_gap_counts(tmp_path: Path):
    gaps = list(NORMAL_GAPS)
    gaps[5] = ("error", 13.3)
    report = report_of(tmp_path, gaps=gaps)
    assert report.criterion_3 is rh.Verdict.FAIL
    assert [g["kind"] for g in report.gaps["over_5s"]] == ["error"]


def test_a_fake_run_says_it_is_not_a_real_rehearsal(tmp_path: Path):
    report = report_of(tmp_path, reply_engine="fake")
    assert report.conditions["fake_run"] is True
    assert any("chưa phải tổng duyệt thật" in note for note in report.notes)
    assert any("tiêu chí 2" in note for note in report.notes)
    real = report_of(tmp_path / "real")
    assert real.conditions["fake_run"] is False
    assert not any("chưa phải tổng duyệt thật" in note for note in real.notes)


@pytest.mark.parametrize("kind", ["frozen", "audio_missing", "host_closed", "fork_lost"])
def test_a_picture_or_sound_alert_fails_criterion_4(tmp_path: Path, kind: str):
    report = report_of(tmp_path, alerts=[AlertSpec(kind, "warning", 300.0, 4.0)])
    assert report.criterion_4 is rh.Verdict.FAIL
    assert report.alerts["by_kind"][kind] == {"count": 1, "total_s": 4.0}


def test_a_silence_that_was_skipped_does_not_fail_criterion_4(tmp_path: Path):
    alert = AlertSpec("silence", "warning", 300.0, 15.2, text="Câu kẹt", auto_action="skip")
    report = report_of(tmp_path, alerts=[alert])
    assert report.criterion_4 is rh.Verdict.PASS
    [listed] = report.alerts["list"]
    assert listed["kind"] == "silence"
    assert listed["seconds"] == pytest.approx(15.2)
    assert listed["auto_action"] == "skip"
    assert listed["text"] == "Câu kẹt"


def test_an_alert_never_closed_is_listed_without_seconds(tmp_path: Path):
    report = report_of(tmp_path, alerts=[AlertSpec("host_closed", "operator", 100.0, None)])
    [listed] = report.alerts["list"]
    assert listed["seconds"] is None
    assert report.alerts["by_kind"]["host_closed"]["count"] == 1


@pytest.mark.parametrize("status", ["tts_error", "render_error"])
def test_a_sentence_lost_to_an_error_fails_criterion_4(tmp_path: Path, status: str):
    report = report_of(tmp_path, sentence_errors=["spoken", status])
    assert report.sentences[status] == 1
    assert report.criterion_4 is rh.Verdict.FAIL


def test_conditions_carry_mouth_method_and_power(tmp_path: Path):
    report = report_of(tmp_path, power="battery", mouth_method="w2l")
    assert report.conditions["mouth_method"] == "w2l"
    assert report.conditions["power"] == "battery"
    assert report.conditions["avatar_mode"] == "livetalking"
    assert report.conditions["reply_engine"] == "chain"
    assert report.render_fps == {"p50": pytest.approx(25.0), "min": pytest.approx(24.6), "turns": 3}


def test_render_figures_of_older_sessions_come_from_utterances(tmp_path: Path):
    report = report_of(tmp_path, render_in="utterances", mouth_method="w2l")
    assert report.conditions["mouth_method"] == "w2l"
    assert report.render_fps == {"p50": pytest.approx(25.0), "min": pytest.approx(24.6), "turns": 3}


def test_render_lines_of_another_show_are_left_out(tmp_path: Path):
    write_show_logs(tmp_path, show_id="first", render_fps=(5.0,), mouth_method="musetalk", duration_s=200.0)
    second = write_show_logs(tmp_path, show_id="second")
    report = rh.build_report(rh.load_show_logs(second.directory, "second"))
    assert report.conditions["mouth_method"] == "w2l"
    assert report.render_fps["min"] == pytest.approx(24.6)


def test_verbatim_lines_are_not_counted_as_fallback(tmp_path: Path):
    show = write_show_logs(tmp_path, sentence_source="verbatim", summary=False)
    report = rh.build_report(rh.load_show_logs(show.directory, show.show_id))
    assert report.sentences["fallback_spoken"] == 0
    assert report.sentences["verbatim_spoken"] == 41
    assert "| Câu đọc nguyên văn (video dự phòng) | 41 |" in rh.render_markdown(report)


def test_static_mode_has_no_render_fps(tmp_path: Path):
    report = report_of(tmp_path, avatar_mode="static")
    assert report.render_fps is None
    assert report.conditions["mouth_method"] is None


def test_time_on_fallback_and_on_the_still_image(tmp_path: Path):
    report = report_of(tmp_path, fallback_spans=[(100.0, 60.0)], static_spans=[(400.0, 30.0), (1800.0, 300.0)])
    assert report.modes["fallback_s"] == pytest.approx(60.0)
    # The second fall-back to the still image runs past the end of the show: only the part inside counts.
    assert report.modes["static_s"] == pytest.approx(60.0)


def test_only_the_chosen_show_is_counted(tmp_path: Path):
    write_show_logs(tmp_path, show_id="first", gaps=[("script", 9.0)] * 3, duration_s=200.0)
    second = write_show_logs(tmp_path, show_id="second")
    report = rh.build_report(rh.load_show_logs(second.directory, "second"))
    assert report.gaps["counted"] == 40
    assert report.criterion_3 is rh.Verdict.PASS
    first = rh.build_report(rh.load_show_logs(second.directory, "first"))
    assert first.criterion_3 is rh.Verdict.FAIL
    assert first.criterion_4 is rh.Verdict.SHORT


def test_last_show_is_the_last_segment(tmp_path: Path):
    write_show_logs(tmp_path, show_id="first")
    second = write_show_logs(tmp_path, show_id="second")
    assert rh.last_show_id(second.directory) == "second"
    assert rh.last_show_id(tmp_path / "nowhere") is None


def test_an_unknown_show_is_an_error(tmp_path: Path):
    show = write_show_logs(tmp_path)
    with pytest.raises(rh.ShowNotFound):
        rh.load_show_logs(show.directory, "missing")


def test_markdown_states_both_verdicts_and_the_gaps_over_5_seconds(tmp_path: Path):
    gaps = list(NORMAL_GAPS)
    gaps[10] = ("script", 7.0)
    report = report_of(tmp_path, gaps=gaps, reply_engine="fake", alerts=[AlertSpec("frozen", "warning", 500.0, 3.5)])
    md = rh.render_markdown(report)
    assert "Tiêu chí 3" in md and "Tiêu chí 4" in md
    assert "KHÔNG ĐẠT" in md
    assert sentence_text(10) in md
    assert "frozen" in md
    assert "chưa phải tổng duyệt thật" in md
    assert "w2l" in md


def test_write_report_puts_both_files_next_to_the_log(tmp_path: Path):
    report = report_of(tmp_path)
    md_path, json_path = rh.write_report(report, tmp_path / report.session_id)
    assert md_path.name == f"rehearsal_{report.show_id}.md"
    assert json_path.name == f"rehearsal_{report.show_id}.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["criterion_3"] == "pass" and data["criterion_4"] == "pass"
    assert data["gaps"]["counted"] == 40
    assert "Tiêu chí 3" in md_path.read_text(encoding="utf-8")


def test_a_short_show_that_froze_fails_rather_than_reads_short(tmp_path: Path):
    report = report_of(tmp_path, duration_s=600.0, alerts=[AlertSpec("frozen", "warning", 100.0, 3.0)])
    assert report.criterion_4 is rh.Verdict.FAIL


def test_an_alert_names_the_sentence_on_air(tmp_path: Path):
    # Sentence i starts at 1830/42 * (i + 1) s: sentence 3 at 174 s is on air when the alert opens at 200 s.
    report = report_of(tmp_path, alerts=[AlertSpec("frozen", "warning", 200.0, 3.0)])
    assert report.alerts["list"][0]["before_text"] == sentence_text(3)


def test_a_half_written_last_line_is_skipped_with_a_note(tmp_path: Path):
    show = write_show_logs(tmp_path, summary=False)
    with (show.directory / "gaps.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"show_id": "show-rehearsal-1", "kind": "scr')
    report = rh.build_report(rh.load_show_logs(show.directory, show.show_id))
    assert report.gaps["counted"] == 40
    assert any("dòng log hỏng" in note for note in report.notes)
