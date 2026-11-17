"""T020 ShowStats (004 US1; FR-022, FR-023, SC-002, SC-004, SC-005, data-model §9, contracts/adapters.md §8) and the
008 T038 `llm_chain` section (FR-018, data-model §7)."""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from ai_live.brain.chain_engine import Attempt, TurnRecord
from ai_live.brain.chain_state import AttemptReason
from ai_live.brain.openai_compat import Usage
from ai_live.core.models import (
    P95_MIN_SAMPLES,
    GapKind,
    ScriptSentence,
    Segment,
    SegmentOrigin,
    SegmentStatus,
    SentenceGap,
    SentenceStatus,
    ShowMode,
    Topic,
)
from ai_live.director import latency
from ai_live.director.show_stats import ShowStats
from ai_live.products.models import Product, ProductCatalog

START = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
_ids = count()


def _catalog() -> ProductCatalog:
    def product(pid: str, primary: bool) -> Product:
        return Product(id=pid, name=pid, is_primary=primary, description="d", intro="i", price=100_000)

    return ProductCatalog(
        version="v1",
        source_name="test.docx",
        loaded_at=START,
        products=(product("p1", True), product("p2", False), product("p3", False)),
    )


def _stats(**kwargs) -> ShowStats:
    stats = ShowStats("show-1", "sess-1", _catalog(), **kwargs)
    stats.mark_started(START)
    return stats


def _segment(
    product_id: str | None,
    topic: Topic = Topic.INTRO,
    *,
    status: SegmentStatus = SegmentStatus.DONE,
    at_s: float = 0.0,
    origin: SegmentOrigin = SegmentOrigin.ROTATION,
) -> Segment:
    n = next(_ids)
    return Segment(
        segment_id=f"seg-{n}",
        show_id="show-1",
        index=n,
        product_id=product_id,
        topic=topic,
        origin=origin,
        mode=ShowMode.NORMAL,
        catalog_version="v1",
        status=status,
        requested_at=START + timedelta(seconds=at_s),
        started_at=START + timedelta(seconds=at_s),
    )


def _sentence(
    segment_id: str,
    word_form: str,
    status: SentenceStatus = SentenceStatus.SPOKEN,
    drop_reason: str | None = None,
) -> ScriptSentence:
    return ScriptSentence(
        utterance_id=f"u-{next(_ids)}",
        segment_id=segment_id,
        seq=0,
        raw_text=word_form,
        text=word_form,
        word_form=word_form,
        status=status,
        drop_reason=drop_reason,
    )


def _gap(seconds: float, kind: GapKind) -> SentenceGap:
    return SentenceGap(f"u-{next(_ids)}", f"u-{next(_ids)}", seconds, kind)


# --- gaps ---


def test_gaps_grouped_by_kind():
    stats = _stats()
    for kind, seconds in [
        (GapKind.SCRIPT, 0.2),
        (GapKind.SCRIPT, 0.4),
        (GapKind.SEGMENT_BOUNDARY, 0.6),
        (GapKind.COMMENT, 3.0),
        (GapKind.PAUSED, 40.0),
        (GapKind.FAULT, 6.2),
        (GapKind.ERROR, 1.1),
    ]:
        stats.record_gap(_gap(seconds, kind))

    by_kind = stats.summary().gaps["by_kind"]
    assert by_kind["script"]["n"] == 2
    assert by_kind["script"]["median_s"] == pytest.approx(0.3)
    assert by_kind["script"]["max_s"] == pytest.approx(0.4)
    assert by_kind["fault"] == {"n": 1, "median_s": 6.2, "p95_s": None, "max_s": 6.2}
    assert by_kind["comment"]["n"] == 1
    assert by_kind["paused"]["n"] == 1


def test_counted_gaps_are_script_boundary_and_error_only():
    stats = _stats()
    stats.record_gap(_gap(0.2, GapKind.SCRIPT))
    stats.record_gap(_gap(0.5, GapKind.SEGMENT_BOUNDARY))
    stats.record_gap(_gap(1.5, GapKind.ERROR))
    stats.record_gap(_gap(9.0, GapKind.COMMENT))
    stats.record_gap(_gap(30.0, GapKind.PAUSED))
    stats.record_gap(_gap(7.0, GapKind.FAULT))

    counted = stats.summary().gaps["counted"]
    assert counted["n"] == 3
    assert counted["max_s"] == pytest.approx(1.5)
    assert counted["median_s"] == pytest.approx(0.5)


def test_gap_p95_is_null_below_20_samples():
    stats = _stats()
    for i in range(P95_MIN_SAMPLES - 1):
        stats.record_gap(_gap(0.1 + i * 0.01, GapKind.SCRIPT))

    counted = stats.summary().gaps["counted"]
    assert counted["n"] == P95_MIN_SAMPLES - 1
    assert counted["p95_s"] is None
    assert counted["median_s"] is not None


def test_gap_p95_uses_the_latency_module(monkeypatch):
    values = [0.1 + i * 0.05 for i in range(30)]
    stats = _stats()
    for v in values:
        stats.record_gap(_gap(v, GapKind.SCRIPT))

    counted = stats.summary().gaps["counted"]
    assert counted["p95_s"] == pytest.approx(round(statistics.quantiles(values, n=20)[18], 3))

    calls: list[int] = []
    real = latency.step_stats

    def spy(vals, *args, **kwargs):
        calls.append(len(vals))
        return real(vals, *args, **kwargs)

    monkeypatch.setattr(latency, "step_stats", spy)
    stats.summary()
    assert 30 in calls  # the p95 comes from director/latency.py, not a second implementation


def test_no_gaps_gives_empty_counted_stats():
    counted = _stats().summary().gaps["counted"]
    assert counted == {"n": 0, "median_s": None, "p95_s": None, "max_s": None}


# --- first sentence, mode changes, comments ---


def test_show_first_sentence_keeps_the_first_value():
    stats = _stats()
    stats.record_first_sentence(2.1234)
    stats.record_first_sentence(9.0)

    assert stats.summary().show_first_sentence_s == pytest.approx(2.123)


def test_show_first_sentence_is_null_until_recorded():
    assert _stats().summary().show_first_sentence_s is None


def test_mode_changes_and_end():
    stats = _stats()
    stats.record_mode_change(ShowMode.FALLBACK, START + timedelta(minutes=3))
    stats.record_mode_change(ShowMode.NORMAL, START + timedelta(minutes=5))
    stats.mark_ended(START + timedelta(minutes=20), "operator")

    summary = stats.summary()
    assert [m["mode"] for m in summary.mode_changes] == ["fallback", "normal"]
    assert summary.ended_by == "operator"
    assert summary.ended_at == START + timedelta(minutes=20)
    assert summary.started_at == START
    data = summary.to_json()
    assert data["show_id"] == "show-1"
    assert data["session_id"] == "sess-1"


def test_reply_latency_of_comment_turns():
    stats = _stats()
    for v in (3.0, 3.5, 4.0):
        stats.record_reply_latency(v)

    assert stats.summary().comments == {"answered": 3, "reply_latency": {"n": 3, "p95_s": None}}


# --- segments ---


def test_segment_counts_and_primary_share():
    stats = _stats()
    stats.record_segment(_segment(None, Topic.OPENING))
    for pid, topic in [("p1", Topic.INTRO), ("p2", Topic.INTRO), ("p1", Topic.PRICE), ("p3", Topic.INTRO)]:
        stats.record_segment(_segment(pid, topic))
    stats.record_segment(_segment("p2", Topic.PRICE, status=SegmentStatus.FAILED))

    segments = stats.summary().segments
    assert segments["total"] == 6
    # Like primary_share, by_product counts played segments only: the failed p2 segment is left out.
    assert segments["by_product"] == {"p1": 2, "p2": 1, "p3": 1}
    assert segments["by_topic"]["intro"] == 3
    assert segments["by_topic"]["opening"] == 1
    assert segments["by_status"] == {"done": 5, "failed": 1}
    # Share of spoken product segments (done/skipped): 2 of 4; the failed one never played.
    assert segments["primary_share"] == pytest.approx(0.5)


def test_primary_share_null_without_product_segments():
    stats = _stats()
    stats.record_segment(_segment(None, Topic.OPENING))

    assert stats.summary().segments["primary_share"] is None


def test_snapshot_stats_shape():
    stats = _stats()
    stats.record_segment(_segment("p1"))
    stats.record_gap(_gap(0.6, GapKind.SCRIPT))
    stats.record_gap(_gap(9.0, GapKind.COMMENT))

    assert stats.snapshot_stats() == {"segments": 1, "gap_p95_s": None, "gap_max_s": 0.6, "primary_share": 1.0}


# --- secondary coverage (SC-004) ---


def test_secondary_coverage_by_10_minute_window():
    stats = _stats()
    stats.record_segment(_segment("p1", at_s=10))
    stats.record_segment(_segment("p2", at_s=60))
    stats.record_segment(_segment("p3", at_s=120))
    stats.record_segment(_segment("p2", at_s=700))  # second window: p3 missing
    stats.record_segment(_segment("p3", at_s=1300, status=SegmentStatus.FAILED))  # third window: failed does not count
    stats.mark_ended(START + timedelta(seconds=1500), "operator")

    coverage = stats.summary().secondary_coverage
    assert [w["window_start_s"] for w in coverage] == [0, 600, 1200]
    assert coverage[0]["missing_products"] == []
    assert coverage[1]["missing_products"] == ["p3"]
    assert coverage[2]["missing_products"] == ["p2", "p3"]


def test_secondary_coverage_empty_before_start():
    stats = ShowStats("show-1", "sess-1", _catalog())

    assert stats.summary().secondary_coverage == []


# --- sentences and duplicates (SC-005) ---


def test_sentence_counts_include_fallback_spoken():
    stats = _stats()
    seg = _segment("p1")
    stats.record_sentence(_sentence(seg.segment_id, "a"), "script")
    stats.record_sentence(_sentence(seg.segment_id, "b", SentenceStatus.BLOCKED), "script")
    stats.record_sentence(_sentence(seg.segment_id, "c", SentenceStatus.DROPPED, "duplicate"), "script")
    stats.record_sentence(_sentence(seg.segment_id, "d", SentenceStatus.TTS_ERROR), "script")
    stats.record_sentence(_sentence(seg.segment_id, "e"), "fallback")

    sentences = stats.summary().sentences
    assert sentences["spoken"] == 2  # fallback lines are spoken too
    assert sentences["fallback_spoken"] == 1
    assert sentences["blocked"] == 1
    assert sentences["dropped"] == 1
    assert sentences["tts_error"] == 1


def test_verbatim_lines_are_not_fallback_lines():
    stats = _stats()
    seg = _segment("p1")
    stats.record_sentence(_sentence(seg.segment_id, "a"), "verbatim")
    stats.record_sentence(_sentence(seg.segment_id, "b"), "verbatim")
    stats.record_sentence(_sentence(seg.segment_id, "c"), "fallback")

    sentences = stats.summary().sentences
    assert sentences["spoken"] == 3
    assert sentences["verbatim_spoken"] == 2
    assert sentences["fallback_spoken"] == 1
    # Verbatim lines are the customer's own text, not LLM script: they stay out of the duplicate rates.
    assert stats.summary().duplicates["before_filter_rate"] is None


def test_duplicate_rate_before_filter():
    stats = _stats()
    seg = _segment("p1").segment_id
    for wf in ("a", "b", "c"):
        stats.record_sentence(_sentence(seg, wf), "script")
    stats.record_sentence(_sentence(seg, "a", SentenceStatus.DROPPED, "duplicate"), "script")
    # These never reach the repeat filter, so they stay out of the rate.
    stats.record_sentence(_sentence(seg, "x", SentenceStatus.BLOCKED), "script")
    stats.record_sentence(_sentence(seg, "", SentenceStatus.DROPPED, "empty_after_clean"), "script")
    stats.record_sentence(_sentence(seg, "y", SentenceStatus.DROPPED, "sentence_count_exceeded"), "script")

    duplicates = stats.summary().duplicates
    assert duplicates["before_filter_rate"] == pytest.approx(0.25)
    assert duplicates["spoken_rate"] == pytest.approx(0.0)


def test_spoken_rate_counts_repeated_spoken_script_lines():
    stats = _stats()
    seg = _segment("p1").segment_id
    for wf in ("a", "b", "a", "c"):
        stats.record_sentence(_sentence(seg, wf), "script")

    assert stats.summary().duplicates["spoken_rate"] == pytest.approx(0.25)


def test_fallback_lines_do_not_count_in_spoken_rate():
    stats = _stats()
    seg = _segment("p1").segment_id
    stats.record_sentence(_sentence(seg, "a"), "script")
    stats.record_sentence(_sentence(seg, "b"), "script")
    for _ in range(3):  # a fallback line may be read again (SC-005)
        stats.record_sentence(_sentence(seg, "a"), "fallback")

    assert stats.summary().duplicates["spoken_rate"] == pytest.approx(0.0)


def test_rates_null_without_script_sentences():
    duplicates = _stats().summary().duplicates
    assert duplicates == {"before_filter_rate": None, "spoken_rate": None, "identical_segments": 0}


def test_identical_segments_compare_spoken_word_forms():
    stats = _stats()
    one, two, three, four = (_segment("p1") for _ in range(4))
    for seg in (one, two, three):
        for wf in ("a", "b"):
            stats.record_sentence(_sentence(seg.segment_id, wf), "script")
    stats.record_sentence(_sentence(four.segment_id, "a"), "script")
    stats.record_sentence(_sentence(four.segment_id, "c"), "script")
    for seg in (one, two, three, four):
        stats.record_segment(seg)

    # one, two and three have the same list: 3 pairs.
    assert stats.summary().duplicates["identical_segments"] == 3


def test_identical_segments_ignore_fallback_segments():
    stats = _stats()
    first = _segment("p1")
    fb1 = _segment("p1", origin=SegmentOrigin.FALLBACK)
    fb2 = _segment("p1", origin=SegmentOrigin.FALLBACK)
    stats.record_sentence(_sentence(first.segment_id, "a"), "script")
    stats.record_sentence(_sentence(fb1.segment_id, "z"), "fallback")
    stats.record_sentence(_sentence(fb2.segment_id, "z"), "fallback")
    for seg in (first, fb1, fb2):
        stats.record_segment(seg)

    assert stats.summary().duplicates["identical_segments"] == 0


# --- 008 T038: the `llm_chain` section (FR-018, data-model §7) ---

CHAIN_MODELS = {"sealion": "gemma-sea-lion-v4-27b", "qwen": "qwen/qwen3.8-27b", "gptoss": "openai/gpt-oss-120b"}
_turn_ids = count()


def _chain_stats(**kwargs) -> ShowStats:
    return _stats(llm_entries=dict(CHAIN_MODELS), **kwargs)


def _attempt(label: str, outcome: str = "ok", reason: AttemptReason | None = None, *, injected: bool = False):
    return Attempt(label, outcome, reason, None, 0.5, injected)  # type: ignore[arg-type]


def _turn(kind: str, outcome: str, *attempts: Attempt, label: str | None = None) -> TurnRecord:
    """One engine turn; the speaking label defaults to the last attempt's when the turn spoke."""
    if label is None and outcome in ("ok", "interrupted") and attempts:
        label = attempts[-1].label
    return TurnRecord(
        turn_key=f"turn-{next(_turn_ids)}",
        kind=kind,  # type: ignore[arg-type]
        label=label,
        model=CHAIN_MODELS.get(label) if label is not None else None,
        provider="cloudflare/x" if label is not None else None,
        attempts=list(attempts),
        outcome=outcome,  # type: ignore[arg-type]
        usage=Usage(prompt_tokens=900, completion_tokens=120, cached_tokens=0) if label is not None else None,
    )


def _llm_chain(stats: ShowStats) -> dict:
    body = stats.summary().to_json()
    assert "llm_chain" in body
    return body["llm_chain"]


def test_llm_chain_is_null_when_the_engine_is_not_the_chain():
    stats = _stats()
    # A record reaching a non-chain show (it should not happen) changes nothing.
    stats.record_llm_turn(_turn("segment", "ok", _attempt("sealion")))
    assert stats.summary().llm_chain is None
    assert _llm_chain(stats) is None


def test_llm_chain_lists_every_entry_in_chain_order_before_any_turn():
    section = _llm_chain(_chain_stats())

    assert set(section) == {"entries", "switches", "exhausted"}
    assert list(section["entries"]) == ["sealion", "qwen", "gptoss"]
    assert section["entries"]["qwen"] == {"model": "qwen/qwen3.8-27b", "segments": 0, "replies": 0, "failures": {}}
    assert (section["switches"], section["exhausted"]) == ({}, 0)


def test_llm_chain_counts_segments_and_replies_per_entry():
    stats = _chain_stats()
    for _ in range(3):
        stats.record_llm_turn(_turn("segment", "ok", _attempt("sealion")))
    stats.record_llm_turn(_turn("reply", "ok", _attempt("sealion")))
    stats.record_llm_turn(
        _turn("segment", "ok", _attempt("sealion", "failed", AttemptReason.RATE_LIMITED), _attempt("qwen"))
    )
    stats.record_llm_turn(
        _turn("reply", "ok", _attempt("sealion", "skipped", AttemptReason.RATE_LIMITED), _attempt("qwen"))
    )

    entries = _llm_chain(stats)["entries"]
    assert (entries["sealion"]["segments"], entries["sealion"]["replies"]) == (3, 1)
    assert (entries["qwen"]["segments"], entries["qwen"]["replies"]) == (1, 1)
    assert (entries["gptoss"]["segments"], entries["gptoss"]["replies"]) == (0, 0)
    assert entries["sealion"]["model"] == "gemma-sea-lion-v4-27b"


def test_failures_count_failed_tries_by_reason_with_injected_ones_and_not_skipped():
    stats = _chain_stats()
    stats.record_llm_turn(
        _turn(
            "segment",
            "ok",
            _attempt("sealion", "failed", AttemptReason.RATE_LIMITED, injected=True),
            _attempt("qwen", "failed", AttemptReason.TIMEOUT),
            _attempt("gptoss"),
        )
    )
    stats.record_llm_turn(
        _turn(
            "reply",
            "ok",
            _attempt("sealion", "skipped", AttemptReason.RATE_LIMITED),
            _attempt("qwen", "skipped", AttemptReason.TIMEOUT),
            _attempt("gptoss"),
        )
    )
    stats.record_llm_turn(
        _turn(
            "segment",
            "ok",
            _attempt("sealion", "failed", AttemptReason.RATE_LIMITED),
            _attempt("qwen", "failed", AttemptReason.EMPTY),
            _attempt("gptoss"),
        )
    )

    entries = _llm_chain(stats)["entries"]
    # The injected rate limit counts like a real one; the turn that skipped resting entries adds nothing.
    assert entries["sealion"]["failures"] == {"rate_limited": 2}
    assert entries["qwen"]["failures"] == {"timeout": 1, "empty": 1}
    assert entries["gptoss"]["failures"] == {}


def test_a_blocked_try_is_a_failure_of_that_entry():
    stats = _chain_stats()
    stats.record_llm_turn(
        _turn("segment", "ok", _attempt("sealion", "failed", AttemptReason.BLOCKED), _attempt("qwen"))
    )
    assert _llm_chain(stats)["entries"]["sealion"]["failures"] == {"blocked": 1}


def test_switches_count_each_move_to_a_later_entry_by_the_reason_of_the_failure():
    stats = _chain_stats()
    stats.record_llm_turn(
        _turn("segment", "ok", _attempt("sealion", "failed", AttemptReason.TIMEOUT), _attempt("qwen"))
    )
    stats.record_llm_turn(
        _turn(
            "segment",
            "ok",
            _attempt("sealion", "failed", AttemptReason.RATE_LIMITED),
            _attempt("qwen", "failed", AttemptReason.OVERLOADED),
            _attempt("gptoss"),
        )
    )
    # A failure, then a resting entry skipped, then a try: one switch, for the failure (the `llm_switch` log line).
    stats.record_llm_turn(
        _turn(
            "reply",
            "ok",
            _attempt("sealion", "failed", AttemptReason.RATE_LIMITED),
            _attempt("qwen", "skipped", AttemptReason.OVERLOADED),
            _attempt("gptoss"),
        )
    )
    # Skipping resting entries is not a switch: nothing was tried before the entry that spoke.
    stats.record_llm_turn(
        _turn("segment", "ok", _attempt("sealion", "skipped", AttemptReason.RATE_LIMITED), _attempt("qwen"))
    )

    assert _llm_chain(stats)["switches"] == {"timeout": 1, "rate_limited": 2, "overloaded": 1}


def test_exhausted_turns_are_counted_with_their_failures_and_no_switch_after_the_last_entry():
    stats = _chain_stats()
    stats.record_llm_turn(
        _turn(
            "segment",
            "exhausted",
            _attempt("sealion", "failed", AttemptReason.RATE_LIMITED),
            _attempt("qwen", "failed", AttemptReason.RATE_LIMITED),
            _attempt("gptoss", "failed", AttemptReason.CONNECTION),
        )
    )
    stats.record_llm_turn(
        _turn(
            "reply",
            "exhausted",
            _attempt("sealion", "skipped", AttemptReason.RATE_LIMITED),
            _attempt("qwen", "skipped", AttemptReason.RATE_LIMITED),
            _attempt("gptoss", "skipped", AttemptReason.CONNECTION),
        )
    )

    section = _llm_chain(stats)
    assert section["exhausted"] == 2
    # Two switches inside the first turn; the last failure leads nowhere.
    assert section["switches"] == {"rate_limited": 2}
    assert section["entries"]["gptoss"]["failures"] == {"connection": 1}
    assert all(e["segments"] == e["replies"] == 0 for e in section["entries"].values())


def test_an_interrupted_turn_is_a_failure_of_its_entry_not_a_finished_segment():
    stats = _chain_stats()
    stats.record_llm_turn(_turn("segment", "interrupted", _attempt("sealion", "failed", AttemptReason.INTERRUPTED)))

    section = _llm_chain(stats)
    # data-model §7: `segments` / `replies` are turns the engine finished; the cut one is in `failures`.
    assert section["entries"]["sealion"] == {
        "model": "gemma-sea-lion-v4-27b",
        "segments": 0,
        "replies": 0,
        "failures": {"interrupted": 1},
    }
    assert (section["switches"], section["exhausted"]) == ({}, 0)


def test_a_cancelled_turn_counts_no_finished_turn_and_no_failure_for_the_cancelled_try():
    stats = _chain_stats()
    # A skip while entry 1 streams, and a stop while entry 2 was being tried after entry 1 failed.
    stats.record_llm_turn(_turn("segment", "cancelled", _attempt("sealion"), label="sealion"))
    stats.record_llm_turn(
        _turn(
            "segment",
            "cancelled",
            _attempt("sealion", "failed", AttemptReason.TIMEOUT),
            _attempt("qwen", "cancelled"),
        )
    )

    section = _llm_chain(stats)
    assert all(e["segments"] == e["replies"] == 0 for e in section["entries"].values())
    assert section["entries"]["sealion"]["failures"] == {"timeout": 1}
    assert section["entries"]["qwen"]["failures"] == {}
    # The engine did log the switch before it tried entry 2.
    assert section["switches"] == {"timeout": 1}
    assert section["exhausted"] == 0


def test_llm_chain_has_no_request_or_token_counts():
    stats = _chain_stats()
    stats.record_llm_turn(_turn("segment", "ok", _attempt("sealion")))
    section = _llm_chain(stats)

    # FR-018, clarified 2026-11-03: tokens stay in the `llm_usage` log lines only.
    assert set(section) == {"entries", "switches", "exhausted"}
    assert all(set(entry) == {"model", "segments", "replies", "failures"} for entry in section["entries"].values())
    text = json.dumps(section)
    assert "token" not in text and "request" not in text and "900" not in text


def test_a_label_outside_the_configured_chain_is_added_with_the_record_model():
    stats = _stats(llm_entries={"sealion": CHAIN_MODELS["sealion"]})
    stats.record_llm_turn(_turn("reply", "ok", _attempt("qwen")))

    entries = _llm_chain(stats)["entries"]
    assert list(entries) == ["sealion", "qwen"]
    assert entries["qwen"]["model"] == "qwen/qwen3.8-27b" and entries["qwen"]["replies"] == 1
