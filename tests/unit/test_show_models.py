"""T005: show models of feature 004 (specs/004-show-director/data-model.md §1-§9)."""

from collections import deque
from datetime import UTC, datetime

import pytest

from ai_live.core.models import (
    REQUIRED_MILESTONES,
    REQUIRED_SCRIPT_MILESTONES,
    DropReason,
    GapKind,
    GuardReason,
    Milestone,
    ScriptSentence,
    Segment,
    SegmentOrigin,
    SegmentRequest,
    SegmentStatus,
    SentenceGap,
    SentenceStatus,
    ShowMode,
    ShowSession,
    ShowState,
    ShowSummary,
    SpokenHistory,
    SpokenLine,
    Topic,
    Utterance,
)

# ---------- §1 enums ----------


def test_enum_values_match_data_model():
    assert [s.value for s in ShowState] == ["idle", "running", "paused", "closing", "ended"]
    assert [m.value for m in ShowMode] == ["normal", "fallback"]
    assert [o.value for o in SegmentOrigin] == ["rotation", "operator", "fallback"]
    assert {s.value for s in SegmentStatus} == {
        "preparing",
        "ready",
        "speaking",
        "done",
        "skipped",
        "failed",
        "blocked",
        "discarded",
    }
    assert {s.value for s in SentenceStatus} == {
        "spoken",
        "blocked",
        "dropped",
        "tts_error",
        "render_error",
        "interrupted",
    }
    assert {k.value for k in GapKind} == {"script", "segment_boundary", "comment", "paused", "fault", "error"}


def test_topic_has_nine_values_in_research_r5_order():
    assert [t.value for t in Topic] == [
        "opening",
        "intro",
        "highlights",
        "specs",
        "price",
        "promotion",
        "faq",
        "call_to_action",
        "closing",
    ]


def test_topic_labels_are_vietnamese():
    expected = {
        Topic.OPENING: "Chào mở màn",
        Topic.INTRO: "Giới thiệu chung",
        Topic.HIGHLIGHTS: "Điểm nổi bật",
        Topic.SPECS: "Thông số",
        Topic.PRICE: "Giá và phân loại",
        Topic.PROMOTION: "Khuyến mãi",
        Topic.FAQ: "Câu hỏi thường gặp",
        Topic.CALL_TO_ACTION: "Kêu gọi mua",
        Topic.CLOSING: "Chào kết",
    }
    assert {t: t.label for t in Topic} == expected


def test_show_state_labels_for_control_page():
    assert ShowState.IDLE.label == "chưa chạy"
    assert ShowState.RUNNING.label == "đang chạy"
    assert ShowState.PAUSED.label == "tạm dừng"
    assert ShowState.CLOSING.label == "đang chào kết"
    assert ShowState.ENDED.label == "đã kết thúc"


def test_required_script_milestones_has_the_four_article_viii_marks():
    assert Milestone.SEGMENT_REQUESTED.value == "segment_requested"
    assert REQUIRED_SCRIPT_MILESTONES == (
        Milestone.SEGMENT_REQUESTED,
        Milestone.LLM_FIRST_SENTENCE,
        Milestone.TTS_FIRST_CHUNK,
        Milestone.AVATAR_FIRST_FRAME,
    )
    # The 001 comment path keeps its own set unchanged.
    assert REQUIRED_MILESTONES[0] is Milestone.COMMENT_RECEIVED
    assert Milestone.SEGMENT_REQUESTED not in REQUIRED_MILESTONES


def test_new_guard_and_drop_reasons():
    assert GuardReason.LINK.value == "link"
    assert GuardReason.UNKNOWN_PERCENT.value == "unknown_percent"
    assert GuardReason.PLATFORM_PHRASE.value == "platform_phrase"
    assert DropReason.SHOW_ENDED.value == "show_ended"
    assert DropReason.SHOW_ENDED.label == "phiên đã kết thúc"
    # Every drop reason still has a label (the control page shows it).
    assert all(reason.label for reason in DropReason)


# ---------- §2 Utterance ----------


def test_comment_utterance_still_built_like_001():
    utt = Utterance(utterance_id="u1", comment_id="c1", catalog_version="v1")
    assert utt.comment_id == "c1"
    assert utt.segment_id is None
    assert utt.show_id is None


def test_script_utterance_has_segment_and_show():
    utt = Utterance(utterance_id="u2", comment_id=None, catalog_version="v1", segment_id="s1", show_id="show1")
    assert utt.comment_id is None
    assert utt.segment_id == "s1"
    assert utt.show_id == "show1"


def test_reply_inside_show_carries_show_id():
    utt = Utterance(utterance_id="u3", comment_id="c1", catalog_version="v1", show_id="show1")
    assert utt.show_id == "show1"


@pytest.mark.parametrize(
    ("comment_id", "segment_id"),
    [(None, None), ("c1", "s1")],
)
def test_utterance_needs_exactly_one_of_comment_or_segment(comment_id, segment_id):
    with pytest.raises(ValueError):
        Utterance(utterance_id="u", comment_id=comment_id, catalog_version="v1", segment_id=segment_id)


# ---------- §5 SegmentRequest ----------


def _request(**overrides):
    values = {
        "segment_id": "s1",
        "topic": Topic.INTRO,
        "product_id": "p1",
        "min_sentences": 3,
        "max_sentences": 6,
    }
    values.update(overrides)
    return SegmentRequest(**values)


def test_segment_request_defaults():
    req = _request()
    assert req.previous_sentence is None
    assert req.recent_lines == ()


@pytest.mark.parametrize(("lo", "hi"), [(1, 1), (3, 6), (2, 3)])
def test_segment_request_accepts_valid_bounds(lo, hi):
    req = _request(min_sentences=lo, max_sentences=hi)
    assert (req.min_sentences, req.max_sentences) == (lo, hi)


@pytest.mark.parametrize(("lo", "hi"), [(4, 3), (0, 3), (-1, 2), (0, 0)])
def test_segment_request_rejects_bad_bounds(lo, hi):
    with pytest.raises(ValueError):
        _request(min_sentences=lo, max_sentences=hi)


@pytest.mark.parametrize("topic", [Topic.OPENING, Topic.CLOSING])
def test_opening_and_closing_have_no_product(topic):
    assert _request(topic=topic, product_id=None, min_sentences=1, max_sentences=2).product_id is None
    with pytest.raises(ValueError):
        _request(topic=topic, product_id="p1")


def test_product_topic_needs_a_product():
    with pytest.raises(ValueError):
        _request(topic=Topic.PRICE, product_id=None)


# ---------- §7 SpokenHistory ----------


def _line(text, product_id, source="script", comment_text=None):
    return SpokenLine(
        text=text, word_form=text.lower(), product_id=product_id, source=source, comment_text=comment_text
    )


def test_recent_for_returns_only_that_product_at_most_n_oldest_first():
    history = SpokenHistory()
    history.add(_line("A1", "p1"))
    history.add(_line("B1", "p2"))
    history.add(_line("A2", "p1"))
    history.add(_line("A3", "p1", source="reply", comment_text="giá sao?"))
    history.add(_line("B2", "p2"))
    history.add(_line("A4", "p1", source="fallback"))

    assert history.recent_for("p1", 3) == ("A2", "A3", "A4")
    assert history.recent_for("p1", 10) == ("A1", "A2", "A3", "A4")
    assert history.recent_for("p2", 5) == ("B1", "B2")
    assert history.recent_for("p3", 5) == ()
    assert history.recent_for("p1", 0) == ()


def test_recent_for_none_is_lines_without_product():
    history = SpokenHistory()
    history.add(_line("Chào cả nhà", None))
    history.add(_line("A1", "p1"))
    assert history.recent_for(None, 5) == ("Chào cả nhà",)


def test_fallback_lines_do_not_enter_seen_word_forms():
    history = SpokenHistory()
    history.add(_line("Script", "p1"))
    history.add(_line("Reply", "p1", source="reply", comment_text="hỏi"))
    history.add(_line("Fallback", "p1", source="fallback"))
    assert history.seen_word_forms == {"script", "reply"}
    assert [line.source for line in history.lines] == ["script", "reply", "fallback"]


def test_spoken_line_rejects_unknown_source():
    with pytest.raises(ValueError):
        _line("x", "p1", source="other")


# ---------- §3, §4, §6, §8, §9 records ----------


def test_show_session_defaults_and_bounded_recent_lists():
    show = ShowSession(show_id="show1", session_id="sess1", start_requested_at=1.0, catalog_version="v1")
    assert show.state is ShowState.IDLE
    assert show.mode is ShowMode.NORMAL
    assert show.consecutive_llm_failures == 0
    assert show.current_segment is None and show.next_segment is None
    assert isinstance(show.recent_blocked, deque) and show.recent_blocked.maxlen == 20
    assert isinstance(show.recent_errors, deque) and show.recent_errors.maxlen == 20


def test_segment_and_sentence_defaults():
    seg = Segment(
        segment_id="s1",
        show_id="show1",
        index=0,
        product_id=None,
        topic=Topic.OPENING,
        origin=SegmentOrigin.ROTATION,
        mode=ShowMode.NORMAL,
        catalog_version="v1",
    )
    assert seg.status is SegmentStatus.PREPARING
    assert seg.sentences == []
    sentence = ScriptSentence(
        utterance_id="u1", segment_id="s1", seq=0, raw_text="**Chào**", text="Chào", word_form="chao"
    )
    assert sentence.status is SentenceStatus.SPOKEN
    assert sentence.guard_reason is None and sentence.drop_reason is None
    assert sentence.marks == {}
    seg.sentences.append(sentence)
    assert seg.sentences[0].seq == 0


def test_sentence_gap_is_immutable():
    gap = SentenceGap(from_utterance_id="u1", to_utterance_id="u2", seconds=0.2, kind=GapKind.SCRIPT)
    with pytest.raises(AttributeError):
        gap.seconds = 1.0  # type: ignore[misc]


def test_show_summary_json_shape():
    started = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    summary = ShowSummary(
        show_id="show1",
        session_id="sess1",
        started_at=started,
        ended_at=None,
        ended_by="operator",
        show_first_sentence_s=2.1,
    )
    body = summary.to_json()
    assert set(body) == {
        "show_id",
        "session_id",
        "started_at",
        "ended_at",
        "ended_by",
        "show_first_sentence_s",
        "segments",
        "secondary_coverage",
        "sentences",
        "gaps",
        "duplicates",
        "mode_changes",
        "comments",
        "llm_chain",
    }
    # 008 contracts/events.md §3: null unless the show runs on the model chain.
    assert body["llm_chain"] is None
    assert body["started_at"] == started.isoformat()
    assert body["ended_at"] is None
    assert body["ended_by"] == "operator"
