"""T055 (004), T049 (008): the script self-check (004 US4 #1, #3; FR-025, FR-026, SC-003; data-model §10; 008 FR-022,
data-model §8).

Every run writes to `tmp_path`, never to the real `data/eval/script_runs/`. No test calls a real LLM: the chain cases
run a real `ChainReplyEngine` on the fake OpenAI-compatible provider.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.brain.guard import OutputGuard
from ai_live.core.config import ChainEntryConfig
from ai_live.core.models import Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.docx_loader import load_catalog
from ai_live.products.models import ProductCatalog
from ai_live.qa_eval.runner import GEMINI_PACE_S
from ai_live.qa_eval.script_eval import (
    ScriptEvalError,
    ScriptEvalRun,
    eval_combos,
    grade_session,
    render_markdown,
    run_script_check,
    run_script_eval,
)
from ai_live.qa_eval.script_grader import VIOLATION_KINDS
from fixtures.content_builder import SPARSE_PRODUCT_NAME, sparse_docx, valid_docx
from fixtures.fake_openai import FakeOpenAI, build_chain_engine, http_error, stream_reply

pytestmark = pytest.mark.anyio

ALL_TOPICS = (
    Topic.INTRO,
    Topic.HIGHLIGHTS,
    Topic.SPECS,
    Topic.PRICE,
    Topic.PROMOTION,
    Topic.CALL_TO_ACTION,
)  # FAQ left the rotation (ADR-088)
SPARSE_TOPICS = (Topic.INTRO, Topic.HIGHLIGHTS, Topic.PRICE, Topic.CALL_TO_ACTION)
GUARD = OutputGuard(("giỏ hàng", "voucher"))
REPO_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"


def _catalog(data: bytes, name: str) -> ProductCatalog:
    return load_catalog(data, name, 5_000_000)


@pytest.fixture
def sparse() -> ProductCatalog:
    return _catalog(sparse_docx(), "sparse.docx")


@pytest.fixture
def valid() -> ProductCatalog:
    return _catalog(valid_docx(), "valid.docx")


@pytest.fixture
def check_settings(settings):
    # An absolute path, so the test does not depend on the working directory.
    return settings.model_copy(update={"platform_phrases_path": REPO_PHRASES})


class Clock:
    """`now()` that moves one minute per call, so two runs never share a run id or a start time."""

    def __init__(self) -> None:
        self.at = datetime(2026, 11, 2, 9, 0, 0)

    def __call__(self) -> datetime:
        self.at += timedelta(minutes=1)
        return self.at


class SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _expected_combos(catalog: ProductCatalog) -> list[tuple[str | None, Topic]]:
    combos: list[tuple[str | None, Topic]] = [(None, Topic.OPENING)]
    for product in catalog.products:
        topics = SPARSE_TOPICS if product.name == SPARSE_PRODUCT_NAME else ALL_TOPICS
        combos += [(product.id, t) for t in topics]
    combos.append((None, Topic.CLOSING))
    return combos


async def _run(engine, catalog, **kwargs) -> ScriptEvalRun:
    kwargs.setdefault("guard", GUARD)
    kwargs.setdefault("engine_label", "fake")
    kwargs.setdefault("model", "fake")
    kwargs.setdefault("min_sentences", 3)
    kwargs.setdefault("max_sentences", 6)
    kwargs.setdefault("now", Clock())
    return await run_script_eval(engine, catalog, **kwargs)


# ---------- US4 #1: every combination with data, plus opening and closing ----------


def test_eval_combos_cover_every_product_topic_with_data(sparse):
    assert eval_combos(sparse) == _expected_combos(sparse)


async def test_every_combination_with_data_gets_a_graded_segment(sparse):
    engine = FakeReplyEngine()
    run = await _run(engine, sparse)
    got = [(s.product_id, Topic(s.topic)) for s in run.segments]
    assert got == _expected_combos(sparse)
    assert all(s.error is None and s.sentences for s in run.segments)
    # Missing data is never asked for (FR-004): the sparse product has no specs, FAQ or promotion segment.
    sparse_id = next(p.id for p in sparse.products if p.name == SPARSE_PRODUCT_NAME)
    asked = {(r.product_id, r.topic) for r in engine.narrate_requests}
    assert not asked & {(sparse_id, t) for t in (Topic.SPECS, Topic.FAQ, Topic.PROMOTION)}
    assert run.violation_count == 0


async def test_requests_use_live_sentence_bounds_and_closing_is_short(sparse):
    engine = FakeReplyEngine()
    await _run(engine, sparse, min_sentences=4, max_sentences=5)
    by_topic = {r.topic: r for r in engine.narrate_requests}
    assert (by_topic[Topic.INTRO].min_sentences, by_topic[Topic.INTRO].max_sentences) == (4, 5)
    assert (by_topic[Topic.OPENING].min_sentences, by_topic[Topic.OPENING].max_sentences) == (4, 5)
    assert (by_topic[Topic.CLOSING].min_sentences, by_topic[Topic.CLOSING].max_sentences) == (1, 2)


async def test_per_combo_repeats_each_combination(sparse):
    engine = FakeReplyEngine()
    run = await _run(engine, sparse, per_combo=2)
    expected = _expected_combos(sparse)
    assert len(run.segments) == 2 * len(expected)
    assert len(engine.narrate_requests) == 2 * len(expected)
    for combo in expected:
        assert sum((s.product_id, Topic(s.topic)) == combo for s in run.segments) == 2


async def test_per_combo_below_one_is_rejected(sparse):
    with pytest.raises(ValueError):
        await _run(FakeReplyEngine(), sparse, per_combo=0)


async def test_paces_between_two_calls_only(sparse):
    sleep = SleepRecorder()
    run = await _run(FakeReplyEngine(), sparse, pace_s=6.0, sleep=sleep, per_combo=2)
    assert sleep.calls == [6.0] * (len(run.segments) - 1)


# ---------- US4 #2: violations with sentence and reason; the count warning is not one ----------


async def test_bad_segment_is_flagged_with_sentence_and_reason(valid):
    pid = valid.primary.id
    engine = FakeReplyEngine(
        script={
            (pid, Topic.PRICE): [
                "Kem chống nắng X loại 50 ml giá 250.000đ nha anh chị.",
                "Hôm nay chỉ còn 99.000đ thôi ạ.",
                "Tôi thấy **rẻ** lắm luôn.",
            ]
        }
    )
    run = await _run(engine, valid)
    segment = next(s for s in run.segments if (s.product_id, s.topic) == (pid, "price"))
    assert [s.raw_text for s in segment.sentences] == [
        "Kem chống nắng X loại 50 ml giá 250.000đ nha anh chị.",
        "Hôm nay chỉ còn 99.000đ thôi ạ.",
        "Tôi thấy **rẻ** lắm luôn.",
    ]
    assert [[v.kind for v in s.violations] for s in segment.sentences] == [
        [],
        ["unknown_amount"],
        ["bad_pronoun", "formatting"],
    ]
    assert segment.sentences[1].violations[0].detail == "99000"
    assert run.totals == {k: 0 for k in VIOLATION_KINDS} | {"unknown_amount": 1, "bad_pronoun": 1, "formatting": 1}
    assert run.violation_count == 3


async def test_sentence_count_outside_bounds_warns_without_violation(valid):
    pid = valid.primary.id
    engine = FakeReplyEngine(script={(pid, Topic.SPECS): ["Da dầu dùng được nha anh chị."]})
    run = await _run(engine, valid)
    short = next(s for s in run.segments if (s.product_id, s.topic) == (pid, "specs"))
    assert short.sentence_count_warning is True
    assert run.violation_count == 0
    assert not any(s.sentence_count_warning for s in run.segments if s is not short)


# ---------- Service errors: recorded, never counted as violations ----------


async def test_rate_limit_is_an_error_not_a_violation(valid):
    engine = FakeReplyEngine()
    engine.fail_next("rate_limited")
    run = await _run(engine, valid)
    opening = run.segments[0]
    assert opening.topic == "opening"
    assert opening.error is not None and "rate_limited" in opening.error
    assert opening.sentences == []
    assert opening.sentence_count_warning is False
    assert all(s.error is None for s in run.segments[1:])
    assert run.violation_count == 0
    assert run.error_count == 1


async def test_timeout_is_an_error_not_a_violation(valid):
    engine = FakeReplyEngine(first_sentence_delay_s=0.5)
    run = await _run(engine, valid, timeout_s=0.01)
    assert run.segments
    assert all(s.error is not None and s.error.startswith("timeout") for s in run.segments)
    assert all(s.sentences == [] for s in run.segments)
    assert run.violation_count == 0
    assert run.error_count == len(run.segments)


async def test_error_after_some_sentences_drops_them(valid):
    pid = valid.primary.id

    class FailsMidStream(FakeReplyEngine):
        async def narrate(self, request, catalog):
            if (request.product_id, request.topic) == (pid, Topic.INTRO):
                yield "Hôm nay chỉ còn 99.000đ thôi ạ."
                raise ReplyEngineError("api_error", "đứt giữa chừng")
            async for line in super().narrate(request, catalog):
                yield line

    run = await _run(FailsMidStream(), valid)
    intro = next(s for s in run.segments if (s.product_id, s.topic) == (pid, "intro"))
    assert intro.error is not None and "api_error" in intro.error
    assert intro.sentences == []
    assert run.violation_count == 0


# ---------- FR-026: stored result, previous run and delta ----------


async def test_result_file_follows_data_model(check_settings, valid, tmp_path):
    runs_dir = tmp_path / "script_runs"
    result = await run_script_check(check_settings, valid, runs_dir=runs_dir, now=Clock())
    assert result.json_path.parent == runs_dir
    assert result.json_path.is_file()
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert {
        "run_id",
        "started_at",
        "finished_at",
        "engine",
        "model",
        "content_source",
        "catalog_version",
        "segments",
        "totals",
        "violation_count",
        "previous",
        "delta",
    } <= set(data)
    assert data["engine"] == "fake"
    assert data["content_source"] == "valid.docx"
    assert data["catalog_version"] == valid.version
    assert data["totals"] == {k: 0 for k in VIOLATION_KINDS}
    assert data["violation_count"] == 0
    assert data["previous"] is None and data["delta"] is None
    segment = data["segments"][0]
    assert {"product_id", "topic", "sentences", "sentence_count_warning", "error"} <= set(segment)
    assert set(segment["sentences"][0]) >= {"raw_text", "violations"}
    assert result.violation_count == 0
    assert ScriptEvalRun.from_json(data).run_id == result.run.run_id


async def test_fake_engine_uses_no_pace(check_settings, valid, tmp_path):
    sleep = SleepRecorder()
    await run_script_check(check_settings, valid, runs_dir=tmp_path, sleep=sleep, now=Clock())
    assert sleep.calls == []


async def test_gemini_engine_is_paced_by_default(check_settings, valid, tmp_path):
    gemini = check_settings.model_copy(update={"reply_engine": "gemini"})
    sleep = SleepRecorder()
    result = await run_script_check(
        gemini, valid, runs_dir=tmp_path, engine=FakeReplyEngine(), sleep=sleep, now=Clock()
    )
    assert sleep.calls == [GEMINI_PACE_S] * (len(result.run.segments) - 1)
    assert result.run.engine == "gemini"
    assert result.run.model == gemini.llm_model


async def test_second_run_has_previous_and_delta(check_settings, valid, tmp_path):
    clock = Clock()
    pid = valid.primary.id
    bad = FakeReplyEngine(script={(pid, Topic.PRICE): ["Hôm nay chỉ còn 99.000đ thôi ạ.", "Tôi thấy rẻ lắm."]})
    first = await run_script_check(check_settings, valid, runs_dir=tmp_path, engine=bad, now=clock)
    assert first.run.previous is None
    second = await run_script_check(check_settings, valid, runs_dir=tmp_path, now=clock)
    assert second.run.previous == {
        "run_id": first.run.run_id,
        "engine": "fake",
        "model": "fake",
        "violation_count": 2,
        "totals": first.run.totals,
    }
    assert second.run.delta == {k: 0 for k in VIOLATION_KINDS} | {"unknown_amount": -1, "bad_pronoun": -1}
    saved = json.loads(second.json_path.read_text(encoding="utf-8"))
    assert saved["previous"]["run_id"] == first.run.run_id
    assert saved["delta"]["unknown_amount"] == -1
    assert first.json_path != second.json_path
    assert second.md_path.is_file()


async def test_previous_run_must_have_the_same_content_source(check_settings, valid, sparse, tmp_path):
    clock = Clock()
    await run_script_check(check_settings, sparse, runs_dir=tmp_path, now=clock)
    first_valid = await run_script_check(check_settings, valid, runs_dir=tmp_path, now=clock)
    assert first_valid.run.previous is None
    second_valid = await run_script_check(check_settings, valid, runs_dir=tmp_path, now=clock)
    assert second_valid.run.previous is not None
    assert second_valid.run.previous["run_id"] == first_valid.run.run_id


# ---------- SC-003: regrade every spoken sentence of a session ----------


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _session(tmp_path: Path, catalog: ProductCatalog, sentences: list[tuple[str, str, str]]) -> Path:
    """`sentences` are `(segment_id, status, text)`; two segments: `s1` intro of the primary, `s2` closing."""
    directory = tmp_path / "sessions" / "20261102-090000"
    directory.mkdir(parents=True)
    pid = catalog.primary.id
    _write_jsonl(
        directory / "segments.jsonl",
        [
            {"segment_id": "s1", "product_id": pid, "topic": "intro", "catalog_version": catalog.version},
            {"segment_id": "s2", "product_id": None, "topic": "closing", "catalog_version": catalog.version},
        ],
    )
    rows = [
        {
            "utterance_id": f"u{i}",
            "segment_id": seg,
            "seq": i,
            "source": "script",
            "text": text,
            "raw_text": f"**{text}**",
            "status": status,
        }
        for i, (seg, status, text) in enumerate(sentences)
    ]
    _write_jsonl(directory / "script_sentences.jsonl", rows)
    return directory


async def test_session_regrades_every_spoken_sentence(valid, tmp_path):
    directory = _session(
        tmp_path,
        valid,
        [
            ("s1", "spoken", "Kem chống nắng X thấm nhanh nha anh chị."),
            ("s1", "spoken", "Hôm nay chỉ còn 99.000đ thôi ạ."),
            # Blocked and dropped lines were never said: SC-003 only grades what was spoken.
            ("s1", "blocked", "Kem này chữa khỏi mụn luôn đó."),
            ("s1", "dropped", "Anh chị xem ở https://example.com nha."),
            ("s2", "spoken", "Cảm ơn cả nhà đã xem live cùng em nha."),
        ],
    )
    run = await grade_session(directory, valid, guard=GUARD, now=Clock())
    graded = [s.text for seg in run.segments for s in seg.sentences]
    assert graded == [
        "Kem chống nắng X thấm nhanh nha anh chị.",
        "Hôm nay chỉ còn 99.000đ thôi ạ.",
        "Cảm ơn cả nhà đã xem live cùng em nha.",
    ]
    # The spoken (cleaned) text is graded, not the raw LLM text, so the raw `**` is not a formatting violation.
    assert run.totals == {k: 0 for k in VIOLATION_KINDS} | {"unknown_amount": 1}
    assert run.violation_count == 1
    assert [(s.product_id, s.topic) for s in run.segments] == [(valid.primary.id, "intro"), (None, "closing")]
    assert run.session == directory.as_posix()


async def test_session_check_is_saved_and_compared_with_the_same_session(check_settings, valid, tmp_path):
    directory = _session(tmp_path, valid, [("s1", "spoken", "Kem chống nắng X thấm nhanh nha anh chị.")])
    clock = Clock()
    runs_dir = tmp_path / "script_runs"
    # A generated run of the same content must not become the previous run of a session check.
    await run_script_check(check_settings, valid, runs_dir=runs_dir, now=clock)
    first = await run_script_check(check_settings, valid, session_dir=directory, runs_dir=runs_dir, now=clock)
    assert first.violation_count == 0
    assert first.json_path.is_file()
    assert first.run.previous is None
    second = await run_script_check(check_settings, valid, session_dir=directory, runs_dir=runs_dir, now=clock)
    assert second.run.previous is not None and second.run.previous["run_id"] == first.run.run_id


async def test_session_without_script_sentences_is_an_error(valid, tmp_path):
    with pytest.raises(ScriptEvalError):
        await grade_session(tmp_path, valid, guard=GUARD)


# ---------- 008 FR-022: who answered each segment, and the engine of both runs ----------

_BASE = "http://127.0.0.1:3001/v1"
_SEALION = {
    "label": "sealion",
    "base_url": _BASE,
    "model": "gemma-sea-lion-v4-27b",
    "key_env": "FREELLMAPI_KEY",
    "platform": "cloudflare",
    "first_sentence_timeout_s": 3.5,
}
_GPTOSS = {
    "label": "gptoss",
    "base_url": _BASE,
    "model": "gpt-oss-120b",
    "key_env": "FREELLMAPI_KEY",
    "platform": "groq",
    "first_sentence_timeout_s": 2.0,
}
_SEALION_VIA = "cloudflare/@cf/aisingapore/gemma-sea-lion-v4-27b-it"
_GPTOSS_VIA = "groq/openai/gpt-oss-120b"
_CLEAN = ("Dạ cả nhà ơi, em giới thiệu sản phẩm này nha. ", "Cả nhà xem thêm thông tin trong file của shop ạ.")
_COMPARISON = re.compile(r"^## So sánh.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)


@pytest.fixture
def chain_settings(check_settings):
    chain = [ChainEntryConfig.model_validate(entry) for entry in (_SEALION, _GPTOSS)]
    return check_settings.model_copy(update={"reply_engine": "chain", "llm_chain": chain})


async def test_segments_record_the_entry_that_answered(sparse):
    fake = FakeOpenAI()
    # sealion answers the opening, then is rate limited for good: every later segment switches to gptoss.
    fake.chat(
        _BASE,
        _SEALION["model"],
        stream_reply(*_CLEAN, routed_via=_SEALION_VIA),
        http_error(429, code="rate_limited"),
    )
    fake.chat(_BASE, _GPTOSS["model"], stream_reply(*_CLEAN, routed_via=_GPTOSS_VIA))
    engine = build_chain_engine(fake, _SEALION, _GPTOSS)
    try:
        run = await _run(engine, sparse, engine_label="chain", model="gemma-sea-lion-v4-27b, gpt-oss-120b")
    finally:
        await engine.aclose()
    first, *rest = run.segments
    assert (first.model_label, first.model, first.provider) == ("sealion", _SEALION["model"], _SEALION_VIA)
    assert rest and all((s.model_label, s.model, s.provider) == ("gptoss", _GPTOSS["model"], _GPTOSS_VIA) for s in rest)
    assert run.violation_count == 0 and run.error_count == 0
    # Stored and read back (data-model §8).
    again = ScriptEvalRun.from_json(json.loads(json.dumps(run.to_json())))
    assert [(s.model_label, s.model, s.provider) for s in again.segments] == [
        (s.model_label, s.model, s.provider) for s in run.segments
    ]


async def test_exhausted_segment_records_no_answering_entry(sparse):
    fake = FakeOpenAI()
    fake.chat(_BASE, _SEALION["model"], http_error(429, code="rate_limited"))
    engine = build_chain_engine(fake, _SEALION)
    try:
        run = await _run(engine, sparse, engine_label="chain:sealion", model=_SEALION["model"])
    finally:
        await engine.aclose()
    assert run.error_count == len(run.segments)
    assert all(s.model_label is None and s.model is None and s.provider is None for s in run.segments)


async def test_engine_without_turn_observer_records_none(sparse):
    run = await _run(FakeReplyEngine(), sparse)
    assert all(s.model_label is None and s.model is None and s.provider is None for s in run.segments)
    data = run.to_json()["segments"][0]
    assert {"model_label", "model", "provider"} <= set(data)


async def test_chain_result_file_has_engine_and_per_segment_models(chain_settings, valid, tmp_path):
    fake = FakeOpenAI()
    fake.chat(_BASE, _GPTOSS["model"], stream_reply(*_CLEAN, routed_via=_GPTOSS_VIA))
    engine = build_chain_engine(fake, _GPTOSS, cooldown_s=0.0)
    sleep = SleepRecorder()
    try:
        result = await run_script_check(
            chain_settings, valid, runs_dir=tmp_path, engine=engine, only="gptoss", sleep=sleep, now=Clock()
        )
    finally:
        await engine.aclose()
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["engine"] == "chain:gptoss"
    assert data["model"] == _GPTOSS["model"]
    assert all(
        (s["model_label"], s["model"], s["provider"]) == ("gptoss", _GPTOSS["model"], _GPTOSS_VIA)
        for s in data["segments"]
    )
    # Any LLM other than the fake one is paced for the free-tier limits, the chain included.
    assert sleep.calls == [GEMINI_PACE_S] * (len(data["segments"]) - 1)
    md = result.md_path.read_text(encoding="utf-8")
    assert "chain:gptoss" in md and _GPTOSS_VIA in md


async def test_whole_chain_run_is_labelled_chain_with_every_model(chain_settings, valid, tmp_path):
    fake = FakeOpenAI()
    fake.chat(_BASE, _SEALION["model"], stream_reply(*_CLEAN, routed_via=_SEALION_VIA))
    engine = build_chain_engine(fake, _SEALION, _GPTOSS)
    try:
        result = await run_script_check(
            chain_settings, valid, runs_dir=tmp_path, engine=engine, sleep=SleepRecorder(), now=Clock()
        )
    finally:
        await engine.aclose()
    assert result.run.engine == "chain"
    assert result.run.model == f"{_SEALION['model']}, {_GPTOSS['model']}"


async def test_comparison_names_the_engine_of_both_runs(check_settings, chain_settings, valid, tmp_path):
    clock = Clock()
    first = await run_script_check(check_settings, valid, runs_dir=tmp_path, now=clock)
    assert first.run.engine == "fake"
    fake = FakeOpenAI()
    fake.chat(_BASE, _SEALION["model"], stream_reply(*_CLEAN, routed_via=_SEALION_VIA))
    engine = build_chain_engine(fake, _SEALION, cooldown_s=0.0)
    try:
        second = await run_script_check(
            chain_settings, valid, runs_dir=tmp_path, engine=engine, only="sealion", sleep=SleepRecorder(), now=clock
        )
    finally:
        await engine.aclose()
    assert second.run.previous is not None
    assert second.run.previous["engine"] == "fake" and second.run.previous["model"] == "fake"
    saved = json.loads(second.json_path.read_text(encoding="utf-8"))
    assert saved["previous"]["engine"] == "fake"
    match = _COMPARISON.search(second.md_path.read_text(encoding="utf-8"))
    assert match, second.md_path.read_text(encoding="utf-8")
    assert "`fake`" in match.group(0) and "`chain:sealion`" in match.group(0), match.group(0)


async def test_old_result_file_without_engine_in_previous_still_loads(check_settings, valid, tmp_path):
    first = await run_script_check(check_settings, valid, runs_dir=tmp_path, now=Clock())
    data = json.loads(first.json_path.read_text(encoding="utf-8"))
    for segment in data["segments"]:
        for key in ("model_label", "model", "provider"):
            segment.pop(key, None)
    data["previous"] = {"run_id": "old", "violation_count": 0, "totals": {}}
    run = ScriptEvalRun.from_json(data)
    assert all(s.model_label is None for s in run.segments)
    assert "`old`" in render_markdown(run)
