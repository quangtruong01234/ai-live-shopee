"""JSON logs keep Vietnamese text on a non-UTF-8 stdout (Windows cp1252 redirect); session file records."""

from __future__ import annotations

import io
import json
import logging
import sys
from datetime import UTC, datetime

import pytest

from ai_live.core.logging import configure_logging, log_event
from ai_live.core.models import (
    GuardReason,
    Milestone,
    ScriptSentence,
    Segment,
    SegmentOrigin,
    SegmentStatus,
    SentenceStatus,
    ShowMode,
    Topic,
    TurnOutcome,
    Utterance,
)
from ai_live.director.session_log import (
    error_record,
    script_sentence_record,
    segment_record,
    utterance_record,
)


def test_vietnamese_log_survives_non_utf8_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw, encoding="cp1252", write_through=True)
    monkeypatch.setattr(sys, "stdout", stdout)
    logger = logging.getLogger("ai_live.test_logging")
    root = logging.getLogger("ai_live")
    saved = (root.handlers[:], root.level, root.propagate)
    errors: list[str] = []
    monkeypatch.setattr(logging, "raiseExceptions", True)
    monkeypatch.setattr(logging.Handler, "handleError", lambda self, record: errors.append(record.getMessage()))
    try:
        configure_logging("INFO", "s1")
        log_event(logger, "turn_error", logging.WARNING, message="Renderer lỗi: chưa mở màn hình host")
        stdout.flush()
    finally:
        root.handlers[:], root.level, root.propagate = saved

    assert errors == []
    line = json.loads(raw.getvalue().decode("utf-8").strip())
    assert line["message"] == "Renderer lỗi: chưa mở màn hình host"


# --- Session file records (004 contracts/events.md §2; 001 shape kept) ---


def _reply_utterance():
    utt = Utterance(utterance_id="u1", comment_id="c1", catalog_version="v1", outcome=TurnOutcome.COMPLETED)
    for i, m in enumerate(
        (
            Milestone.COMMENT_RECEIVED,
            Milestone.TURN_STARTED,
            Milestone.LLM_FIRST_SENTENCE,
            Milestone.TTS_FIRST_CHUNK,
            Milestone.AVATAR_FIRST_FRAME,
        )
    ):
        utt.mark(m, 100.0 + i)
    return utt


def test_reply_utterance_record_keeps_the_001_shape() -> None:

    record = utterance_record(_reply_utterance(), "fake")

    assert set(record) == {
        "utterance_id",
        "comment_id",
        "catalog_version",
        "llm_model",
        "sentences",
        "outcome",
        "error_step",
        "guard_reason",
        "marks",
        "total_s",
        "queue_wait_s",
    }
    assert record["marks"]["comment_received"] == 0.0
    assert record["total_s"] == 4.0


def test_reply_inside_a_show_carries_show_id() -> None:

    utt = _reply_utterance()
    utt.show_id = "show-1"

    record = utterance_record(utt, "fake")
    assert record["show_id"] == "show-1"
    assert "segment_id" not in record


def test_scripted_utterance_record_is_relative_to_segment_requested() -> None:
    utt = Utterance(
        utterance_id="u2",
        comment_id=None,
        catalog_version="v1",
        outcome=TurnOutcome.COMPLETED,
        segment_id="seg-1",
        show_id="show-1",
    )
    utt.mark(Milestone.SEGMENT_REQUESTED, 50.0)
    utt.mark(Milestone.LLM_FIRST_SENTENCE, 51.25)
    utt.mark(Milestone.AVATAR_FIRST_FRAME, 52.0)

    record = utterance_record(utt, "fake")
    assert record["segment_id"] == "seg-1"
    assert record["show_id"] == "show-1"
    assert record["comment_id"] is None
    assert record["marks"] == {"segment_requested": 0.0, "llm_first_sentence": 1.25, "avatar_first_frame": 2.0}
    assert record["total_s"] == 2.0


def test_error_record_adds_segment_and_show_only_when_set() -> None:

    plain = error_record("llm", "api_error", "x", "u1")
    scripted = error_record("tts", "timeout", "y", "u2", segment_id="seg-1", show_id="show-1")

    assert set(plain) == {"ts", "utterance_id", "step", "type", "message"}
    assert scripted["segment_id"] == "seg-1"
    assert scripted["show_id"] == "show-1"


def test_segment_and_script_sentence_records() -> None:
    spoken = ScriptSentence("u1", "seg-1", 0, "**Chào** nha", "Chào nha", "chao nha")
    spoken.marks = {
        Milestone.SEGMENT_REQUESTED: 10.0,
        Milestone.LLM_FIRST_SENTENCE: 11.4,
        Milestone.TTS_FIRST_CHUNK: 11.41,
        Milestone.AVATAR_FIRST_FRAME: 12.0,
    }
    spoken.played_at = 14.5
    blocked = ScriptSentence(
        "u2",
        "seg-1",
        1,
        "Giá 999.000đ",
        "Giá 999.000đ",
        "gia 999 000d",
        status=SentenceStatus.BLOCKED,
        guard_reason=GuardReason.UNKNOWN_AMOUNT,
        guard_detail="999000",
    )
    segment = Segment(
        segment_id="seg-1",
        show_id="show-1",
        index=0,
        product_id="p1",
        topic=Topic.PRICE,
        origin=SegmentOrigin.ROTATION,
        mode=ShowMode.NORMAL,
        catalog_version="v1",
        status=SegmentStatus.DONE,
        requested_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
        sentences=[spoken, blocked],
    )

    line = script_sentence_record(spoken, "script")
    assert line["marks"] == {
        "segment_requested": 0.0,
        "llm_first_sentence": 1.4,
        "tts_first_chunk": 1.41,
        "avatar_first_frame": 2.0,
    }
    assert line["played_at"] == 4.5
    assert line["raw_text"] == "**Chào** nha"
    blocked_line = script_sentence_record(blocked, "script")
    assert blocked_line["guard_reason"] == "unknown_amount"
    assert blocked_line["marks"] == {}
    assert blocked_line["played_at"] is None

    record = segment_record(segment)
    assert record["sentences"] == {"spoken": 1, "blocked": 1, "dropped": 0, "tts_error": 0}
    assert record["topic"] == "price"
    assert record["requested_at"] == "2026-11-01T09:00:00.000Z"
    assert record["started_at"] is None
    json.dumps(record)
