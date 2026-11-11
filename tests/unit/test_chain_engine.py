"""`ChainReplyEngine` on the fake provider, no network (contracts/adapters.md §2, config.md §3–§4, research R3–R8).

T017 (008 US1): one-entry turns, `from_settings`, `preflight`, logs.
T027 (008 US2): multi-entry switching, rests on a fake clock, cancellation, exhaustion, the per-entry fault hook.
T037 (008 US3): `snapshot()` and the state observer for the control page.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import SecretStr

from ai_live.brain.chain_engine import (
    Attempt,
    ChainReplyEngine,
    ChainSnapshot,
    PreflightResult,
    ResolvedEntry,
    TurnRecord,
    Usage,
)
from ai_live.brain.chain_state import AttemptReason
from ai_live.brain.prompt import build_system_prompt, build_user_message
from ai_live.brain.script_prompt import build_script_system_prompt, build_segment_message
from ai_live.core.config import ChainEntryConfig, Settings
from ai_live.core.models import Comment, SegmentRequest, Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.docx_loader import load_catalog
from fixtures import fake_openai as fo
from fixtures.content_builder import valid_docx

pytestmark = pytest.mark.anyio

LOCAL = "http://127.0.0.1:3001/v1"
GROQ = "https://api.groq.com/openai/v1"
FREELLMAPI_KEY = fo.FAKE_KEYS["FREELLMAPI_KEY"]
GROQ_KEY = fo.FAKE_KEYS["GROQ_API_KEY"]
SEALION_ROUTE = "cloudflare/@cf/aisingapore/gemma-sea-lion-v4-27b-it"

SEALION: dict[str, Any] = {
    "label": "sealion",
    "base_url": LOCAL,
    "model": "gemma-sea-lion-v4-27b",
    "key_env": "FREELLMAPI_KEY",
    "first_sentence_timeout_s": 3.5,
    "platform": "cloudflare",
}
GPTOSS: dict[str, Any] = {
    "label": "gptoss",
    "base_url": LOCAL,
    "model": "gpt-oss-120b",
    "key_env": "FREELLMAPI_KEY",
    "first_sentence_timeout_s": 2.0,
    "platform": "groq",
    "params": {"reasoning_effort": "low"},
}
QWEN: dict[str, Any] = {
    "label": "qwen",
    "base_url": GROQ,
    "model": "qwen/qwen3.8-27b",
    "key_env": "GROQ_API_KEY",
    "first_sentence_timeout_s": 2.0,
    "params": {"reasoning_effort": "none"},
}
# The ADR-035 chain before ADR-040 trimmed the default: two entries share the freellmapi base_url, so the config and
# preflight rules (one /models request per base_url and key, every failing entry named) are checked on it.
RULES_CHAIN: tuple[dict[str, Any], ...] = (SEALION, GPTOSS, QWEN)


@pytest.fixture
def catalog():
    return load_catalog(valid_docx(), "valid.docx", 5_000_000)


@pytest.fixture
def comment():
    return Comment(id="c1", source="mock", author="Lan", text="giá bao nhiêu vậy shop?", received_at=0.0)


@pytest.fixture
def segment(catalog):
    return SegmentRequest(
        segment_id="seg-0007",
        topic=Topic.PRICE,
        product_id=catalog.primary.id,
        min_sentences=3,
        max_sentences=6,
        previous_sentence="Kem này thấm nhanh lắm nha anh chị.",
    )


@pytest.fixture
def fake():
    return fo.FakeOpenAI()


@pytest.fixture
async def engines() -> AsyncIterator[list[ChainReplyEngine]]:
    """Engines built by a test; closed afterwards so no httpx client is left open."""
    made: list[ChainReplyEngine] = []
    yield made
    for engine in made:
        await engine.aclose()


@pytest.fixture
def brain_logs() -> Any:
    """Every record of `ai_live.brain`, with a handler of our own: `configure_logging` may have stopped propagation."""
    records: list[logging.LogRecord] = []

    class _Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Keep(level=logging.DEBUG)
    brain = logging.getLogger("ai_live.brain")
    old_level = brain.level
    brain.addHandler(handler)
    brain.setLevel(logging.DEBUG)
    yield records
    brain.removeHandler(handler)
    brain.setLevel(old_level)


def _events(records: list[logging.LogRecord], name: str) -> list[logging.LogRecord]:
    return [r for r in records if r.getMessage() == name]


def _engine(engines: list[ChainReplyEngine], fake: fo.FakeOpenAI, *entries: Any, **kw: Any) -> ChainReplyEngine:
    engine = fo.build_chain_engine(fake, *entries, **kw)
    engines.append(engine)
    return engine


def _recorder(engine: ChainReplyEngine) -> list[TurnRecord]:
    turns: list[TurnRecord] = []
    engine.add_turn_observer(turns.append)
    return turns


async def _reply(engine: ChainReplyEngine, comment: Comment, catalog: Any) -> list[str]:
    return [s async for s in engine.reply(comment, catalog)]


async def _narrate(engine: ChainReplyEngine, segment: SegmentRequest, catalog: Any) -> list[str]:
    return [s async for s in engine.narrate(segment, catalog)]


# ---------------------------------------------------------------------------------------------------------------------
# One-entry turns
# ---------------------------------------------------------------------------------------------------------------------


async def test_reply_yields_complete_sentences_and_flushes_the_tail(engines, fake, catalog, comment):
    fake.chat(
        LOCAL,
        SEALION["model"],
        fo.stream_reply(
            "Dạ chào bạn ",
            "Lan. Kem 50 ml giá 250.",
            "000đ, loại 100 ml giá 420.000đ nha! Bạn chọn",
            " loại nào",
            routed_via=SEALION_ROUTE,
        ),
    )
    out = await _reply(_engine(engines, fake, SEALION), comment, catalog)
    assert out == [
        "Dạ chào bạn Lan.",
        "Kem 50 ml giá 250.000đ, loại 100 ml giá 420.000đ nha!",
        "Bạn chọn loại nào",  # no terminator: only `flush()` at the end of the stream yields it
    ]


async def test_narrate_yields_complete_sentences(engines, fake, catalog, segment):
    fake.chat(
        LOCAL,
        SEALION["model"],
        fo.stream_reply("Kem 50 ml giá 250.000đ nha. ", "Loại 100 ml", " giá 420.000đ!", routed_via=SEALION_ROUTE),
    )
    out = await _narrate(_engine(engines, fake, SEALION), segment, catalog)
    assert out == ["Kem 50 ml giá 250.000đ nha.", "Loại 100 ml giá 420.000đ!"]


async def test_reply_builds_messages_like_gemini_and_uses_llm_max_tokens(engines, fake, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.stream_reply("Dạ chào bạn Lan nha.", routed_via=SEALION_ROUTE))
    engine = _engine(engines, fake, SEALION, max_tokens=321, script_max_tokens=654)
    await _reply(engine, comment, catalog)
    (request,) = fake.chat_requests()
    assert request.body["messages"] == [
        {"role": "system", "content": build_system_prompt(catalog)},
        {"role": "user", "content": build_user_message(comment)},
    ]
    assert request.body["max_tokens"] == 321
    assert request.body["stream"] is True


async def test_narrate_builds_script_messages_and_uses_script_max_tokens(engines, fake, catalog, segment):
    fake.chat(LOCAL, SEALION["model"], fo.stream_reply("Kem này giá 250.000đ nha.", routed_via=SEALION_ROUTE))
    engine = _engine(engines, fake, SEALION, max_tokens=321, script_max_tokens=654)
    await _narrate(engine, segment, catalog)
    (request,) = fake.chat_requests()
    assert request.body["messages"] == [
        {"role": "system", "content": build_script_system_prompt(catalog)},
        {"role": "user", "content": build_segment_message(segment, catalog)},
    ]
    assert request.body["max_tokens"] == 654


async def test_turn_record_ok_carries_label_model_provider_and_usage(engines, fake, catalog, comment):
    fake.chat(
        LOCAL,
        SEALION["model"],
        fo.stream_reply(
            "Dạ chào bạn Lan nha.",
            routed_via=SEALION_ROUTE,
            response_model="gemma-sea-lion-v4-27b-it",
            usage=fo.UsageChunk(prompt_tokens=900, completion_tokens=40, cached_tokens=800),
        ),
    )
    engine = _engine(engines, fake, SEALION)
    turns = _recorder(engine)
    await _reply(engine, comment, catalog)
    (turn,) = turns
    assert turn.turn_key == "c1"
    assert turn.kind == "reply"
    assert turn.outcome == "ok"
    assert turn.label == "sealion"
    assert turn.model == "gemma-sea-lion-v4-27b-it"  # the response's `model` wins over the entry's
    assert turn.provider == SEALION_ROUTE  # full X-Routed-Via value
    assert turn.usage == Usage(prompt_tokens=900, completion_tokens=40, cached_tokens=800)
    (attempt,) = turn.attempts
    assert isinstance(attempt, Attempt)
    assert (attempt.label, attempt.outcome, attempt.reason) == ("sealion", "ok", None)
    assert attempt.routed_via == SEALION_ROUTE
    assert attempt.elapsed_s >= 0
    assert attempt.injected is False


async def test_provider_falls_back_to_base_url_host_and_model_to_entry(engines, fake, catalog, comment):
    # Groq sends no X-Routed-Via; the fake echoes the requested model in the chunks.
    fake.chat(GROQ, QWEN["model"], fo.stream_reply("Dạ chào bạn Lan nha."))
    engine = _engine(engines, fake, QWEN)
    turns = _recorder(engine)
    await _reply(engine, comment, catalog)
    (turn,) = turns
    assert turn.provider == "api.groq.com"
    assert turn.model == "qwen/qwen3.8-27b"
    assert turn.usage is None  # no usage chunk was sent


async def test_narrate_turn_record_is_a_segment(engines, fake, catalog, segment):
    fake.chat(LOCAL, SEALION["model"], fo.stream_reply("Kem này giá 250.000đ nha.", routed_via=SEALION_ROUTE))
    engine = _engine(engines, fake, SEALION)
    turns = _recorder(engine)
    await _narrate(engine, segment, catalog)
    (turn,) = turns
    assert (turn.turn_key, turn.kind, turn.outcome) == ("seg-0007", "segment", "ok")


async def test_a_failing_observer_does_not_break_the_turn(engines, fake, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.stream_reply("Dạ chào bạn Lan nha.", routed_via=SEALION_ROUTE))
    engine = _engine(engines, fake, SEALION)

    def boom(_turn: TurnRecord) -> None:
        raise RuntimeError("observer bug")

    engine.add_turn_observer(boom)
    turns = _recorder(engine)
    assert await _reply(engine, comment, catalog) == ["Dạ chào bạn Lan nha."]
    assert len(turns) == 1


async def test_reply_logs_llm_attempt_and_llm_usage(engines, fake, catalog, comment, brain_logs):
    fake.chat(
        LOCAL,
        SEALION["model"],
        fo.stream_reply(
            "Dạ chào bạn Lan nha.",
            routed_via=SEALION_ROUTE,
            usage=fo.UsageChunk(prompt_tokens=900, completion_tokens=40, cached_tokens=800),
        ),
    )
    await _reply(_engine(engines, fake, SEALION), comment, catalog)
    (attempt,) = _events(brain_logs, "llm_attempt")
    assert attempt.levelno == logging.INFO
    fields = attempt.fields
    assert fields["comment_id"] == "c1"
    assert fields["label"] == "sealion"
    assert fields["model"] == "gemma-sea-lion-v4-27b"
    assert fields["provider"] == SEALION_ROUTE
    assert fields["routed_via"] == SEALION_ROUTE
    assert fields["outcome"] == "ok"
    assert fields["injected"] is False
    assert isinstance(fields["elapsed_s"], float)
    (usage,) = _events(brain_logs, "llm_usage")
    assert usage.fields == {
        "comment_id": "c1",
        "label": "sealion",
        "model": "gemma-sea-lion-v4-27b",
        "provider": SEALION_ROUTE,
        "prompt_tokens": 900,
        "output_tokens": 40,
        "cached_tokens": 800,
    }


async def test_narrate_logs_carry_segment_id_and_topic(engines, fake, catalog, segment, brain_logs):
    fake.chat(
        LOCAL,
        SEALION["model"],
        fo.stream_reply("Kem này giá 250.000đ nha.", routed_via=SEALION_ROUTE, usage=fo.UsageChunk()),
    )
    await _narrate(_engine(engines, fake, SEALION), segment, catalog)
    for name in ("llm_attempt", "llm_usage"):
        (record,) = _events(brain_logs, name)
        assert record.fields["segment_id"] == "seg-0007"
        assert record.fields["topic"] == "price"
        assert "comment_id" not in record.fields


async def test_logs_never_carry_the_key_the_auth_header_or_the_request_body(
    engines, fake, catalog, comment, brain_logs
):
    fake.chat(LOCAL, SEALION["model"], fo.stream_reply("Dạ chào bạn Lan nha.", routed_via=SEALION_ROUTE))
    # The provider echoes the key it got in its error body (research R12).
    fake.chat(GROQ, QWEN["model"], fo.http_error(401, type="invalid_api_key", message=f"Invalid API Key {GROQ_KEY}"))
    await _reply(_engine(engines, fake, SEALION), comment, catalog)
    with pytest.raises(ReplyEngineError) as exc:
        await _reply(_engine(engines, fake, QWEN), comment, catalog)
    assert GROQ_KEY not in str(exc.value)
    assert brain_logs, "the turns must have logged something"
    system_prompt = build_system_prompt(catalog)
    for record in brain_logs:
        text = f"{record.getMessage()} {getattr(record, 'fields', {})!r}"
        for forbidden in (FREELLMAPI_KEY, GROQ_KEY, "Authorization", "Bearer", comment.text, system_prompt[:60]):
            assert forbidden not in text, (record.getMessage(), forbidden)


async def test_http_429_on_a_one_entry_chain_is_rate_limited(engines, fake, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429, code="rate_limited", routed_via=SEALION_ROUTE))
    engine = _engine(engines, fake, SEALION)
    turns = _recorder(engine)
    with pytest.raises(ReplyEngineError) as exc:
        await _reply(engine, comment, catalog)
    assert exc.value.kind == "rate_limited"
    assert "sealion" in str(exc.value)
    (turn,) = turns
    assert (turn.outcome, turn.label) == ("exhausted", None)
    assert [(a.outcome, a.reason) for a in turn.attempts] == [("failed", AttemptReason.RATE_LIMITED)]
    assert len(fake.chat_requests()) == 1  # no retry inside one entry


@pytest.mark.parametrize(
    "reply",
    [
        fo.http_error(401, type="invalid_api_key"),
        fo.connect_error(),
        fo.empty_stream(),
        fo.content_filtered(),
    ],
    ids=["401", "connect", "empty", "content_filter"],
)
async def test_other_failures_on_a_one_entry_chain_are_api_error(engines, fake, catalog, comment, reply):
    fake.chat(GROQ, QWEN["model"], reply)
    engine = _engine(engines, fake, QWEN)
    turns = _recorder(engine)
    with pytest.raises(ReplyEngineError) as exc:
        await _reply(engine, comment, catalog)
    assert exc.value.kind == "api_error"
    assert turns[0].outcome == "exhausted"


async def test_first_sentence_timeout_fails_the_entry_and_closes_the_stream(engines, fake, catalog, comment):
    fake.chat(GROQ, QWEN["model"], fo.hang_without_text())
    engine = _engine(engines, fake, {**QWEN, "first_sentence_timeout_s": 0.1})
    turns = _recorder(engine)
    with pytest.raises(ReplyEngineError) as exc:
        async with asyncio.timeout(2):
            await _reply(engine, comment, catalog)
    assert exc.value.kind == "api_error"
    assert [a.reason for a in turns[0].attempts] == [AttemptReason.TIMEOUT]
    assert fake.served[0].closed


async def test_text_without_a_sentence_end_within_the_timeout_is_flushed(engines, fake, catalog, comment):
    fake.chat(GROQ, QWEN["model"], fo.stream_reply("Dạ chào bạn Lan"))
    out = await _reply(_engine(engines, fake, {**QWEN, "first_sentence_timeout_s": 0.5}), comment, catalog)
    assert out == ["Dạ chào bạn Lan"]


async def test_slow_text_after_the_first_sentence_is_not_cut(engines, fake, catalog, comment):
    events = [fo.Role(), fo.Text("Dạ chào bạn Lan. "), fo.Delay(0.3), fo.Text("Kem giá 250.000đ nha."), fo.Done()]
    fake.chat(GROQ, QWEN["model"], fo.ChatReply(events=events))
    engine = _engine(engines, fake, {**QWEN, "first_sentence_timeout_s": 0.1})
    turns = _recorder(engine)
    assert await _reply(engine, comment, catalog) == ["Dạ chào bạn Lan.", "Kem giá 250.000đ nha."]
    assert turns[0].outcome == "ok"


async def test_each_step_can_run_in_its_own_task(engines, fake, catalog, comment):
    """Research R1: `ShowDirector` pulls with `wait_for(anext(...))`, a new task per step, so no timeout block may
    stay open across a `yield`."""
    fake.chat(GROQ, QWEN["model"], fo.stream_reply("Dạ chào bạn Lan. ", "Kem giá 250.000đ nha. ", "Bạn chọn nha."))
    stream = _engine(engines, fake, QWEN).reply(comment, catalog)
    out = []
    try:
        while True:
            out.append(await asyncio.wait_for(anext(stream), 1))
    except StopAsyncIteration:
        pass
    assert out == ["Dạ chào bạn Lan.", "Kem giá 250.000đ nha.", "Bạn chọn nha."]


async def test_closing_the_turn_after_the_first_sentence_closes_the_response(engines, fake, catalog, comment):
    fake.chat(GROQ, QWEN["model"], fo.stream_reply("Dạ chào bạn Lan. ", "Câu này không được đọc.", delay=0.05))
    engine = _engine(engines, fake, QWEN)
    turns = _recorder(engine)
    stream = engine.reply(comment, catalog)
    assert await anext(stream) == "Dạ chào bạn Lan."
    await stream.aclose()
    assert fake.served[0].closed
    (turn,) = turns
    assert turn.outcome == "cancelled"
    # A cancelled turn does not rest the entry: the next turn tries it again.
    fake.chat(GROQ, QWEN["model"], fo.stream_reply("Dạ chào bạn nha."))
    await _reply(engine, comment, catalog)
    assert [a.outcome for a in turns[1].attempts] == ["ok"]


async def test_cancelling_before_the_first_sentence_records_a_cancelled_attempt(engines, fake, catalog, comment):
    fake.chat(GROQ, QWEN["model"], fo.hang_without_text())
    engine = _engine(engines, fake, QWEN)
    turns = _recorder(engine)
    task = asyncio.create_task(_reply(engine, comment, catalog))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (turn,) = turns
    assert turn.outcome == "cancelled"
    assert [a.outcome for a in turn.attempts] == ["cancelled"]
    assert fake.served[0].closed


async def test_aclose_closes_the_shared_http_client(fake):
    engine = fo.build_chain_engine(fake, QWEN)
    await engine.aclose()
    assert engine._http.is_closed


# ---------------------------------------------------------------------------------------------------------------------
# from_settings (contracts/config.md §3)
# ---------------------------------------------------------------------------------------------------------------------


def _chain(**changes: dict[str, Any]) -> list[dict[str, Any]]:
    """`RULES_CHAIN` with per-label field changes; a `None` value removes the field."""
    out = []
    for entry in RULES_CHAIN:
        entry = {**entry, **changes.get(entry["label"], {})}
        out.append({k: v for k, v in entry.items() if v is not None})
    return out


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "reply_engine": "chain",
        "freellmapi_key": FREELLMAPI_KEY,
        "groq_api_key": GROQ_KEY,
        "llm_chain": [dict(e) for e in RULES_CHAIN],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _config_error(settings: Settings, **kw: Any) -> str:
    with pytest.raises(ReplyEngineError) as exc:
        ChainReplyEngine.from_settings(settings, **kw)
    assert exc.value.kind == "config_error"
    message = str(exc.value)
    for key in (FREELLMAPI_KEY, GROQ_KEY):
        assert key not in message
    return message


async def test_from_settings_builds_the_default_chain():
    settings = Settings(_env_file=None, reply_engine="chain", freellmapi_key=FREELLMAPI_KEY, groq_api_key=GROQ_KEY)
    engine = ChainReplyEngine.from_settings(settings)
    try:
        assert [e.label for e in engine.entries] == ["sealion", "qwen"]
        assert [e.position for e in engine.entries] == [1, 2]
        assert engine.cooldown_s == 60
    finally:
        await engine.aclose()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"llm_chain": []},
            "LLM_CHAIN trống: cần ít nhất một mục khi REPLY_ENGINE=chain",
        ),
        (
            {"llm_chain": _chain(gptoss={"model": "auto"})},
            'LLM_CHAIN mục 2 (gptoss): không được dùng model "auto"; ghi tên model cụ thể (ADR-035)',
        ),
        (
            {"llm_chain": _chain(gptoss={"model": "Auto:fast"})},
            'LLM_CHAIN mục 2 (gptoss): không được dùng model "Auto:fast"; ghi tên model cụ thể (ADR-035)',
        ),
        (
            {"llm_chain": _chain(qwen={"model": "FUSION"})},
            'LLM_CHAIN mục 3 (qwen): không được dùng model "FUSION"; ghi tên model cụ thể (ADR-035)',
        ),
        (
            {"llm_chain": _chain(sealion={"platform": None})},
            'LLM_CHAIN mục 1 (sealion): base_url trỏ tới dịch vụ gom key nên phải khai platform (ví dụ "cloudflare")',
        ),
        (
            {"llm_chain": _chain(sealion={"base_url": "http://localhost:3001/v1", "platform": None})},
            'LLM_CHAIN mục 1 (sealion): base_url trỏ tới dịch vụ gom key nên phải khai platform (ví dụ "cloudflare")',
        ),
        (
            {"llm_chain": _chain(sealion={"model": "  "})},
            "LLM_CHAIN mục 1 (sealion): thiếu model",
        ),
        (
            {"llm_chain": _chain(qwen={"key_env": "FOO_KEY"})},
            'LLM_CHAIN mục 3 (qwen): key_env "FOO_KEY" không hợp lệ; '
            "dùng GEMINI_API_KEY, FREELLMAPI_KEY hoặc GROQ_API_KEY",
        ),
        (
            {"groq_api_key": None},
            "LLM_CHAIN mục 3 (qwen): GROQ_API_KEY chưa có giá trị trong .env",
        ),
        (
            {"groq_api_key": "   "},
            "LLM_CHAIN mục 3 (qwen): GROQ_API_KEY chưa có giá trị trong .env",
        ),
        (
            {"llm_chain": _chain(gptoss={"label": "sealion"})},
            'LLM_CHAIN: nhãn "sealion" bị trùng',
        ),
        (
            {"llm_chain": _chain(gptoss={"params": {"model": "x"}})},
            'LLM_CHAIN mục 2 (gptoss): params không được đặt "model"',
        ),
        (
            {"llm_chain": _chain(gptoss={"params": {"stream_options": {}}})},
            'LLM_CHAIN mục 2 (gptoss): params không được đặt "stream_options"',
        ),
        (
            {"llm_chain": _chain(sealion={"first_sentence_timeout_s": 5.0})},
            "LLM_CHAIN: tổng first_sentence_timeout_s là 9.0 s, vượt 8.0 s "
            "(min của LLM_TIMEOUT_S và SCRIPT_LLM_TIMEOUT_S)",
        ),
        (
            {"script_llm_timeout_s": 6},
            "LLM_CHAIN: tổng first_sentence_timeout_s là 7.5 s, vượt 6.0 s "
            "(min của LLM_TIMEOUT_S và SCRIPT_LLM_TIMEOUT_S)",
        ),
    ],
    ids=[
        "empty",
        "auto",
        "auto-prefix",
        "fusion",
        "loopback-no-platform",
        "localhost-no-platform",
        "blank-model",
        "bad-key-env",
        "missing-key",
        "blank-key",
        "duplicate-label",
        "param-model",
        "param-stream-options",
        "total-timeout",
        "total-timeout-script",
    ],
)
def test_from_settings_config_errors(overrides, expected):
    assert expected in _config_error(_settings(**overrides)).splitlines()


def test_from_settings_lists_every_problem_at_once():
    settings = _settings(llm_chain=_chain(sealion={"platform": None}, gptoss={"model": "auto"}), groq_api_key=None)
    lines = _config_error(settings).splitlines()
    assert any(line.startswith("LLM_CHAIN mục 1 (sealion)") for line in lines)
    assert any(line.startswith("LLM_CHAIN mục 2 (gptoss)") for line in lines)
    assert any(line.startswith("LLM_CHAIN mục 3 (qwen)") for line in lines)


@pytest.mark.parametrize(
    "llm_chain",
    [
        '[{"label": "sealion"',  # bad JSON
        [{"label": "sealion", "model": "m", "key_env": "FREELLMAPI_KEY", "first_sentence_timeout_s": 1}],  # no base_url
        [{**SEALION, "base_url": "ftp://127.0.0.1/v1"}],
    ],
    ids=["bad-json", "missing-base-url", "not-http"],
)
def test_malformed_llm_chain_is_rejected_by_settings_naming_the_variable(llm_chain):
    with pytest.raises(ValueError, match="llm_chain"):
        _settings(llm_chain=llm_chain)


async def test_only_builds_a_one_entry_chain_without_cooldown():
    # Only the chosen entry is checked: the missing GROQ key of `qwen` does not matter.
    engine = ChainReplyEngine.from_settings(_settings(groq_api_key=None), only="gptoss")
    try:
        assert [e.label for e in engine.entries] == ["gptoss"]
        assert engine.cooldown_s == 0
    finally:
        await engine.aclose()


def test_only_with_an_unknown_label_is_a_config_error():
    message = _config_error(_settings(), only="llama")
    assert '"llama"' in message
    for label in ("sealion", "gptoss", "qwen"):
        assert label in message


async def test_from_settings_passes_the_fault_hook_and_the_transport(fake, catalog, comment):
    def hook(label: str) -> str | None:
        return None  # no fault: the turn runs normally (per-attempt faults are in the US2 part below)

    fake.chat(GROQ, QWEN["model"], fo.stream_reply("Dạ chào bạn Lan nha."))
    engine = ChainReplyEngine.from_settings(_settings(), only="qwen", fault_hook=hook, transport=fake.transport)
    try:
        assert await _reply(engine, comment, catalog) == ["Dạ chào bạn Lan nha."]
        (request,) = fake.chat_requests()
        assert request.headers["authorization"] == f"Bearer {GROQ_KEY}"
    finally:
        await engine.aclose()


# ---------------------------------------------------------------------------------------------------------------------
# preflight (contracts/config.md §4, research R9)
# ---------------------------------------------------------------------------------------------------------------------

DEFAULT_ENTRIES = [dict(e) for e in RULES_CHAIN]


def _healthy(fake: fo.FakeOpenAI) -> fo.FakeOpenAI:
    fake.models(
        LOCAL,
        fo.models_list(
            fo.ModelRow("gemma-sea-lion-v4-27b", available=True, execution_status="ready"),
            fo.ModelRow("gpt-oss-120b", available=True, execution_status="ready"),
        ),
    )
    fake.models(GROQ, fo.models_list("qwen/qwen3.8-27b", "llama-3.3-70b-versatile"))
    return fake


async def test_preflight_passes_with_one_request_per_base_url_and_key(engines, fake, brain_logs):
    engine = _engine(engines, _healthy(fake), *DEFAULT_ENTRIES)
    results = await engine.preflight()
    assert [(r.label, r.position, r.ok) for r in results] == [
        ("sealion", 1, True),
        ("gptoss", 2, True),
        ("qwen", 3, True),
    ]
    assert all(isinstance(r, PreflightResult) and r.problem is None for r in results)
    assert sorted(r.base_url for r in fake.models_requests()) == sorted([LOCAL, GROQ])
    assert fake.chat_requests() == []
    logs = _events(brain_logs, "llm_preflight")
    assert [(r.fields["label"], r.fields["ok"], r.levelno) for r in logs] == [
        ("sealion", True, logging.INFO),
        ("gptoss", True, logging.INFO),
        ("qwen", True, logging.INFO),
    ]
    assert all("comment_id" not in r.fields and "segment_id" not in r.fields for r in logs)


@pytest.mark.parametrize(
    ("script", "expected", "problem"),
    [
        (
            {LOCAL: fo.models_connect_error()},
            [
                "LLM_CHAIN mục 1 (sealion): không kết nối được http://127.0.0.1:3001/v1; dịch vụ gom key đã chạy chưa?",
                "LLM_CHAIN mục 2 (gptoss): không kết nối được http://127.0.0.1:3001/v1; dịch vụ gom key đã chạy chưa?",
            ],
            "unreachable",
        ),
        (
            {GROQ: fo.models_error(401, message=f"Invalid API Key {GROQ_KEY}")},
            ["LLM_CHAIN mục 3 (qwen): GROQ_API_KEY bị từ chối (401)"],
            "auth",
        ),
        (
            {GROQ: fo.models_error(403)},
            ["LLM_CHAIN mục 3 (qwen): GROQ_API_KEY bị từ chối (403)"],
            "auth",
        ),
        (
            {LOCAL: fo.models_list(fo.ModelRow("gemma-sea-lion-v4-27b", available=True))},
            ['LLM_CHAIN mục 2 (gptoss): không có model "gpt-oss-120b" ở http://127.0.0.1:3001/v1'],
            "model_missing",
        ),
        (
            {
                LOCAL: fo.models_list(
                    fo.ModelRow("gemma-sea-lion-v4-27b", available=False, unavailable_reason="no_key"),
                    fo.ModelRow("gpt-oss-120b", available=True),
                )
            },
            ['LLM_CHAIN mục 1 (sealion): model "gemma-sea-lion-v4-27b" chưa dùng được (unavailable_reason=no_key)'],
            "model_unavailable",
        ),
        (
            {LOCAL: fo.models_error(500)},
            [
                "LLM_CHAIN mục 1 (sealion): kiểm model trả status 500",
                "LLM_CHAIN mục 2 (gptoss): kiểm model trả status 500",
            ],
            "http_error",
        ),
    ],
    ids=["unreachable", "auth-401", "auth-403", "model-missing", "model-unavailable", "http-error"],
)
async def test_preflight_problems_are_config_errors_naming_every_failing_entry(
    engines, fake, brain_logs, script, expected, problem
):
    for base_url, reply in script.items():
        fake.models(base_url, reply)
    _healthy(fake)  # queued after: the scripted failure is served first and repeats
    engine = _engine(engines, fake, *DEFAULT_ENTRIES)
    with pytest.raises(ReplyEngineError) as exc:
        await engine.preflight()
    assert exc.value.kind == "config_error"
    assert str(exc.value).splitlines() == expected
    for key in (FREELLMAPI_KEY, GROQ_KEY):
        assert key not in str(exc.value)
    failed = [r for r in _events(brain_logs, "llm_preflight") if not r.fields["ok"]]
    assert len(failed) == len(expected)
    assert all(r.levelno == logging.ERROR and r.fields["problem"] == problem for r in failed)
    for record in _events(brain_logs, "llm_preflight"):
        for key in (FREELLMAPI_KEY, GROQ_KEY):
            assert key not in repr(record.fields)


async def test_preflight_unavailable_needs_available_false(engines, fake):
    # Groq rows carry no `available` field: that is not "unavailable".
    fake.models(GROQ, fo.models_list("qwen/qwen3.8-27b"))
    results = await _engine(engines, fake, QWEN).preflight()
    assert [r.ok for r in results] == [True]


async def test_preflight_exhausted_is_only_a_warning(engines, fake, brain_logs):
    fake.models(
        LOCAL,
        fo.models_list(
            fo.ModelRow("gemma-sea-lion-v4-27b", available=True, execution_status="exhausted"),
            fo.ModelRow("gpt-oss-120b", available=True, execution_status="ready"),
        ),
    )
    _healthy(fake)
    results = await _engine(engines, fake, *DEFAULT_ENTRIES).preflight()
    assert all(r.ok for r in results)
    assert results[0].execution_status == "exhausted"
    sealion = next(r for r in _events(brain_logs, "llm_preflight") if r.fields["label"] == "sealion")
    assert sealion.levelno == logging.WARNING
    assert sealion.fields["execution_status"] == "exhausted"


# =====================================================================================================================
# US2 (T027): switching, rests, cancellation, exhaustion, fault hook
# =====================================================================================================================

GPTOSS_ROUTE = "groq/openai/gpt-oss-120b"
GPTOSS_SAYS = ["Dạ gptoss chào bạn.", "Kem giá 250.000đ nha."]
SEALION_SAYS = ["Dạ SEA-LION chào bạn.", "Kem 50 ml giá 250.000đ nha."]
QWEN_SAYS = ["Dạ qwen chào bạn.", "Bạn chọn loại nào nha."]
T0 = datetime(2026, 11, 4, 20, 0, 0, tzinfo=UTC)
COOLDOWN = 60.0


class _Clock:
    """Wall clock for `ChainState`: only moves when the test says so."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


def _chain_engine(
    engines: list[ChainReplyEngine],
    fake: fo.FakeOpenAI,
    clock: _Clock,
    *entries: dict[str, Any],
    fault_hook: Any = None,
) -> ChainReplyEngine:
    """Like `fo.build_chain_engine`, plus the injected clock (the fixture builder has no `clock` argument)."""
    resolved = []
    for position, raw in enumerate(entries or (SEALION, GPTOSS, QWEN), start=1):
        config = ChainEntryConfig.model_validate(raw)
        config._position = position
        key = SecretStr(fo.FAKE_KEYS[config.key_env])
        resolved.append(ResolvedEntry(config=config, position=position, local=config.local, key=key))
    engine = ChainReplyEngine(
        resolved,
        cooldown_s=COOLDOWN,
        max_tokens=300,
        script_max_tokens=600,
        transport=fake.transport,
        clock=clock,
        fault_hook=fault_hook,
    )
    engines.append(engine)
    return engine


def _sealion_ok() -> fo.ChatReply:
    return fo.stream_reply("Dạ SEA-LION chào bạn. ", "Kem 50 ml giá 250.000đ nha.", routed_via=SEALION_ROUTE)


def _gptoss_ok() -> fo.ChatReply:
    return fo.stream_reply("Dạ gptoss chào bạn. ", "Kem giá 250.000đ nha.", routed_via=GPTOSS_ROUTE)


def _qwen_ok() -> fo.ChatReply:
    return fo.stream_reply("Dạ qwen chào bạn. ", "Bạn chọn loại nào nha.")


def _requests(fake: fo.FakeOpenAI, entry: dict[str, Any]) -> int:
    return len(fake.chat_requests(entry["base_url"], entry["model"]))


def _summary(turn: TurnRecord) -> list[tuple[str, str, AttemptReason | None]]:
    return [(a.label, a.outcome, a.reason) for a in turn.attempts]


def _retry_at(seconds: float = COOLDOWN, start: datetime = T0) -> str:
    return (start + timedelta(seconds=seconds)).isoformat(timespec="seconds")


async def _wait_for(predicate: Any, polls: int = 400) -> None:
    """Let the event loop run until `predicate()` holds; fail after `polls` short sleeps (about 2 s)."""
    for _ in range(polls):
        if predicate():
            return
        await asyncio.sleep(0.005)
    pytest.fail("condition not reached while waiting on the event loop")


# ------------------------------------------------------------------------- every failure before the first sentence


SWITCH_CASES = [
    pytest.param(
        fo.ChatReply(
            status=429,
            error_body=fo.error_body("slow down", code="rate_limited"),
            headers={"Retry-After": "3600"},
        ),
        AttemptReason.RATE_LIMITED,
        id="429-retry-after-ignored",
    ),
    pytest.param(fo.http_error(503), AttemptReason.OVERLOADED, id="503"),
    pytest.param(
        fo.ChatReply(events=[fo.Role(), fo.ErrorFrame(), fo.Done()], routed_via=SEALION_ROUTE),
        AttemptReason.OVERLOADED,
        id="sse-error-frame",
    ),
    pytest.param(fo.empty_stream(routed_via=SEALION_ROUTE), AttemptReason.EMPTY, id="empty-stream"),
    pytest.param(fo.http_error(502, code="empty_completion"), AttemptReason.EMPTY, id="502-empty_completion"),
    pytest.param(fo.connect_error(), AttemptReason.CONNECTION, id="connect"),
    pytest.param(
        fo.ChatReply(events=[fo.Role(), fo.Disconnect()], routed_via=SEALION_ROUTE),
        AttemptReason.CONNECTION,
        id="disconnect",
    ),
    pytest.param(fo.hang_without_text(routed_via=SEALION_ROUTE), AttemptReason.TIMEOUT, id="hang"),
    pytest.param(
        fo.hang_without_text(routed_via=SEALION_ROUTE, keepalive_every=0.02),
        AttemptReason.TIMEOUT,
        id="keepalive-forever",
    ),
    pytest.param(fo.ChatReply(hang_before_headers=True), AttemptReason.TIMEOUT, id="hang-before-headers"),
    pytest.param(fo.http_error(401, type="invalid_api_key"), AttemptReason.REJECTED, id="401"),
    pytest.param(fo.http_error(404, code="model_not_found"), AttemptReason.REJECTED, id="404-model_not_found"),
    pytest.param(fo.http_error(502, code="provider_error"), AttemptReason.REJECTED, id="502-provider_error"),
    pytest.param(fo.stream_reply("Câu cũ. ", routed_via="cache"), AttemptReason.WRONG_PLATFORM, id="cache"),
    pytest.param(
        fo.stream_reply("Câu khác. ", routed_via="groq/llama-3.3-70b"),
        AttemptReason.WRONG_PLATFORM,
        id="other-platform",
    ),
]


@pytest.mark.parametrize(("failure", "reason"), SWITCH_CASES)
async def test_a_failure_before_the_first_sentence_switches_to_the_next_entry_and_rests_the_failed_one(
    engines, fake, clock, catalog, comment, brain_logs, failure, reason
):
    fake.chat(LOCAL, SEALION["model"], failure)
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock, {**SEALION, "first_sentence_timeout_s": 0.2}, GPTOSS, QWEN)
    turns = _recorder(engine)

    async with asyncio.timeout(3):
        assert await _reply(engine, comment, catalog) == GPTOSS_SAYS

    (turn,) = turns
    assert (turn.outcome, turn.label) == ("ok", "gptoss")
    assert _summary(turn) == [("sealion", "failed", reason), ("gptoss", "ok", None)]
    assert not any(a.injected for a in turn.attempts)
    assert _requests(fake, QWEN) == 0
    assert fake.unscripted == []
    if reason is AttemptReason.WRONG_PLATFORM:
        assert fake.served[0].lines_read == 0  # closed before any SSE line (FR-024)
    assert all(s.closed for s in fake.served)

    (switch,) = _events(brain_logs, "llm_switch")
    assert switch.levelno == logging.WARNING
    assert switch.fields == {"comment_id": "c1", "from_label": "sealion", "to_label": "gptoss", "reason": reason.value}
    (rest,) = _events(brain_logs, "llm_entry_rest")
    assert rest.levelno == logging.WARNING
    # Fixed rest: `Retry-After: 3600` (first case) changes nothing (FR-010, research R3).
    assert rest.fields == {
        "comment_id": "c1",
        "label": "sealion",
        "reason": reason.value,
        "seconds": COOLDOWN,
        "retry_at": _retry_at(),
    }
    failed = [r for r in _events(brain_logs, "llm_attempt") if r.fields["outcome"] == "failed"]
    assert [(r.fields["label"], r.fields["reason"]) for r in failed] == [("sealion", reason.value)]

    # The rest is real: the next turn does not call sealion (SC-004).
    await _reply(engine, comment, catalog)
    assert _summary(turns[1])[0] == ("sealion", "skipped", reason)
    assert _requests(fake, SEALION) == 1


async def test_two_failures_switch_twice_and_the_third_entry_answers(
    engines, fake, clock, catalog, segment, brain_logs
):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], fo.http_error(503))
    fake.chat(GROQ, QWEN["model"], _qwen_ok())
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)
    assert await _narrate(engine, segment, catalog) == QWEN_SAYS
    assert _summary(turns[0]) == [
        ("sealion", "failed", AttemptReason.RATE_LIMITED),
        ("gptoss", "failed", AttemptReason.OVERLOADED),
        ("qwen", "ok", None),
    ]
    switches = _events(brain_logs, "llm_switch")
    assert [(r.fields["from_label"], r.fields["to_label"], r.fields["reason"]) for r in switches] == [
        ("sealion", "gptoss", "rate_limited"),
        ("gptoss", "qwen", "overloaded"),
    ]
    assert all(r.fields["segment_id"] == "seg-0007" for r in switches)
    assert [r.fields["label"] for r in _events(brain_logs, "llm_entry_rest")] == ["sealion", "gptoss"]


async def test_each_hung_entry_is_dropped_after_its_own_first_sentence_timeout(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.hang_without_text(routed_via=SEALION_ROUTE))
    fake.chat(LOCAL, GPTOSS["model"], fo.hang_without_text(routed_via=GPTOSS_ROUTE))
    fake.chat(GROQ, QWEN["model"], _qwen_ok())
    engine = _chain_engine(
        engines,
        fake,
        clock,
        {**SEALION, "first_sentence_timeout_s": 0.3},
        {**GPTOSS, "first_sentence_timeout_s": 0.1},
        QWEN,
    )
    turns = _recorder(engine)
    started = time.monotonic()
    async with asyncio.timeout(3):
        assert await _reply(engine, comment, catalog) == QWEN_SAYS
    total = time.monotonic() - started
    sealion, gptoss, qwen = turns[0].attempts
    assert (sealion.reason, gptoss.reason, qwen.outcome) == (AttemptReason.TIMEOUT, AttemptReason.TIMEOUT, "ok")
    assert 0.28 <= sealion.elapsed_s < 0.6
    assert 0.08 <= gptoss.elapsed_s < 0.4
    assert total < 1.0
    assert all(s.closed for s in fake.served)


# ------------------------------------------------------------------------------- failure after the first sentence


@pytest.mark.parametrize(
    "tail",
    [fo.ErrorFrame(), fo.Disconnect(), fo.Disconnect(protocol=True)],
    ids=["sse-error-frame", "ReadError", "RemoteProtocolError"],
)
async def test_failure_after_the_first_sentence_is_interrupted_and_never_mixes_two_models(
    engines, fake, clock, catalog, comment, brain_logs, tail
):
    events = [fo.Role(), fo.Text("Dạ SEA-LION chào bạn. "), tail]
    fake.chat(LOCAL, SEALION["model"], fo.ChatReply(events=events, routed_via=SEALION_ROUTE))
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)

    out: list[str] = []
    with pytest.raises(ReplyEngineError) as exc:
        async for sentence in engine.reply(comment, catalog):
            out.append(sentence)
    assert exc.value.kind == "api_error"
    assert out == ["Dạ SEA-LION chào bạn."]  # nothing from gptoss in this turn (FR-008)
    assert _requests(fake, GPTOSS) == 0
    (turn,) = turns
    assert (turn.outcome, turn.label) == ("interrupted", "sealion")
    assert _summary(turn) == [("sealion", "failed", AttemptReason.INTERRUPTED)]
    assert turn.attempts[0].routed_via == SEALION_ROUTE
    assert _events(brain_logs, "llm_switch") == []
    (rest,) = _events(brain_logs, "llm_entry_rest")
    assert (rest.fields["label"], rest.fields["reason"]) == ("sealion", "interrupted")

    # US2 #3: the next turn starts on the next entry.
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert _summary(turns[1]) == [("sealion", "skipped", AttemptReason.INTERRUPTED), ("gptoss", "ok", None)]


# ------------------------------------------------------------------------------------------- rest and come back


async def test_a_resting_entry_gets_no_request_until_retry_at_then_is_tried_first_again(
    engines, fake, clock, catalog, comment, brain_logs
):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429), _sealion_ok())
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)

    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    for _ in range(3):  # SC-004: no turn calls sealion while it rests
        clock.advance(10)
        assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
        assert _summary(turns[-1]) == [("sealion", "skipped", AttemptReason.RATE_LIMITED), ("gptoss", "ok", None)]
        assert turns[-1].attempts[0].elapsed_s == 0.0
    assert _requests(fake, SEALION) == 1
    skipped = [r for r in _events(brain_logs, "llm_attempt") if r.fields["outcome"] == "skipped"]
    assert len(skipped) == 3
    assert all(r.fields["label"] == "sealion" and r.fields["reason"] == "rate_limited" for r in skipped)

    clock.advance(30)  # T0 + 60 s = retry_at (FR-015, US2 #6)
    assert await _reply(engine, comment, catalog) == SEALION_SAYS
    assert _summary(turns[-1]) == [("sealion", "ok", None)]
    assert _requests(fake, SEALION) == 2
    assert _requests(fake, QWEN) == 0


async def test_a_rest_is_counted_from_the_failure_time(engines, fake, clock, catalog, comment, brain_logs):
    fake.chat(LOCAL, SEALION["model"], _sealion_ok(), fo.http_error(503), _sealion_ok())
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    await _reply(engine, comment, catalog)
    clock.advance(100)
    await _reply(engine, comment, catalog)  # sealion fails at T0 + 100 s
    (rest,) = _events(brain_logs, "llm_entry_rest")
    assert rest.fields["retry_at"] == _retry_at(start=T0 + timedelta(seconds=100))
    clock.advance(59)
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    clock.advance(1)
    assert await _reply(engine, comment, catalog) == SEALION_SAYS


async def test_content_filter_switches_without_resting_the_entry(engines, fake, clock, catalog, comment, brain_logs):
    fake.chat(LOCAL, SEALION["model"], fo.content_filtered(routed_via=SEALION_ROUTE), _sealion_ok())
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert _summary(turns[0]) == [("sealion", "failed", AttemptReason.BLOCKED), ("gptoss", "ok", None)]
    (switch,) = _events(brain_logs, "llm_switch")
    assert switch.fields["reason"] == "blocked"
    assert _events(brain_logs, "llm_entry_rest") == []
    # Same clock instant: the next turn still tries sealion first.
    assert await _reply(engine, comment, catalog) == SEALION_SAYS
    assert _summary(turns[1]) == [("sealion", "ok", None)]


# --------------------------------------------------------------------------------------------- cancellation (FR-013)


async def test_cancelling_before_the_first_sentence_leaves_the_chain_unchanged(
    engines, fake, clock, catalog, comment, brain_logs
):
    fake.chat(LOCAL, SEALION["model"], fo.hang_without_text(routed_via=SEALION_ROUTE), _sealion_ok())
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)
    task = asyncio.create_task(_reply(engine, comment, catalog))
    await _wait_for(lambda: _requests(fake, SEALION) == 1)
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (turn,) = turns
    assert turn.outcome == "cancelled"
    assert _summary(turn) == [("sealion", "cancelled", None)]
    assert _events(brain_logs, "llm_entry_rest") == []
    assert _events(brain_logs, "llm_switch") == []
    assert _requests(fake, GPTOSS) == 0
    assert fake.served[0].closed
    assert await _reply(engine, comment, catalog) == SEALION_SAYS


async def test_cancelling_during_the_second_attempt_only_keeps_the_first_entry_rest(
    engines, fake, clock, catalog, comment, brain_logs
):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], fo.hang_without_text(routed_via=GPTOSS_ROUTE), _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)
    task = asyncio.create_task(_reply(engine, comment, catalog))
    await _wait_for(lambda: _requests(fake, GPTOSS) == 1)
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert turns[0].outcome == "cancelled"
    assert _summary(turns[0]) == [
        ("sealion", "failed", AttemptReason.RATE_LIMITED),
        ("gptoss", "cancelled", None),
    ]
    assert [r.fields["label"] for r in _events(brain_logs, "llm_entry_rest")] == ["sealion"]
    assert _requests(fake, QWEN) == 0
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert _summary(turns[1]) == [("sealion", "skipped", AttemptReason.RATE_LIMITED), ("gptoss", "ok", None)]


@pytest.mark.parametrize("how", ["aclose", "cancel"])
async def test_stopping_after_the_first_sentence_leaves_the_chain_unchanged(
    engines, fake, clock, catalog, comment, brain_logs, how
):
    slow = fo.stream_reply("Dạ SEA-LION chào bạn. ", "Câu này không được đọc.", delay=0.3, routed_via=SEALION_ROUTE)
    fake.chat(LOCAL, SEALION["model"], slow, _sealion_ok())
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)
    if how == "aclose":
        stream = engine.reply(comment, catalog)
        assert await anext(stream) == "Dạ SEA-LION chào bạn."
        await stream.aclose()
    else:
        out: list[str] = []

        async def consume() -> None:
            async for sentence in engine.reply(comment, catalog):
                out.append(sentence)

        task = asyncio.create_task(consume())
        await _wait_for(lambda: bool(out))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert out == ["Dạ SEA-LION chào bạn."]
    (turn,) = turns
    assert (turn.outcome, turn.label) == ("cancelled", "sealion")
    assert fake.served[0].closed
    assert _events(brain_logs, "llm_entry_rest") == []
    assert _events(brain_logs, "llm_switch") == []
    assert await _reply(engine, comment, catalog) == SEALION_SAYS


# ------------------------------------------------------------------------------------------- exhausted chain (R7)


async def test_every_entry_rate_limited_is_kind_rate_limited(engines, fake, clock, catalog, comment, brain_logs):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429, message=f"limit for {FREELLMAPI_KEY}"))
    fake.chat(LOCAL, GPTOSS["model"], fo.http_error(429, code="rate_limited"))
    fake.chat(GROQ, QWEN["model"], fo.http_error(429, type="tokens", message=f"limit for {GROQ_KEY}"))
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)
    with pytest.raises(ReplyEngineError) as exc:
        await _reply(engine, comment, catalog)
    assert exc.value.kind == "rate_limited"
    message = str(exc.value)
    for label in ("sealion", "gptoss", "qwen"):
        assert f"{label} lỗi rate_limited" in message
    (turn,) = turns
    assert (turn.outcome, turn.label) == ("exhausted", None)
    (exhausted,) = _events(brain_logs, "llm_chain_exhausted")
    assert exhausted.levelno == logging.ERROR
    assert exhausted.fields["kind"] == "rate_limited"
    assert exhausted.fields["entries"] == [
        {"label": "sealion", "reason": "rate_limited"},
        {"label": "gptoss", "reason": "rate_limited"},
        {"label": "qwen", "reason": "rate_limited"},
    ]
    for key in (FREELLMAPI_KEY, GROQ_KEY):
        assert key not in message
        for record in brain_logs:
            assert key not in record.getMessage()
            assert key not in repr(getattr(record, "fields", {}))


async def test_mixed_failures_exhaust_as_api_error(engines, fake, clock, catalog, comment, brain_logs):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], fo.http_error(503))
    fake.chat(GROQ, QWEN["model"], fo.http_error(429))
    engine = _chain_engine(engines, fake, clock)
    with pytest.raises(ReplyEngineError) as exc:
        await _reply(engine, comment, catalog)
    assert exc.value.kind == "api_error"
    assert "gptoss lỗi overloaded" in str(exc.value)
    (exhausted,) = _events(brain_logs, "llm_chain_exhausted")
    assert exhausted.fields["kind"] == "api_error"


@pytest.mark.parametrize(
    ("gptoss_failure", "kind"),
    [(fo.http_error(429), "rate_limited"), (fo.http_error(503), "api_error")],
    ids=["all-rate-limited", "mixed"],
)
async def test_every_entry_resting_fails_fast_without_any_request(
    engines, fake, clock, catalog, comment, brain_logs, gptoss_failure, kind
):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], gptoss_failure)
    fake.chat(GROQ, QWEN["model"], fo.http_error(429))
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)
    with pytest.raises(ReplyEngineError):
        await _reply(engine, comment, catalog)
    sent = len(fake.chat_requests())

    clock.advance(5)
    started = time.monotonic()
    with pytest.raises(ReplyEngineError) as exc:
        await _reply(engine, comment, catalog)
    assert time.monotonic() - started < 1.0  # SC-006
    assert len(fake.chat_requests()) == sent  # 0 new requests
    assert exc.value.kind == kind  # R7 counts resting reasons too
    assert [a.outcome for a in turns[1].attempts] == ["skipped", "skipped", "skipped"]
    assert turns[1].outcome == "exhausted"
    message = str(exc.value)
    for label in ("sealion", "gptoss", "qwen"):
        assert f"{label} đang nghỉ" in message
    assert len(_events(brain_logs, "llm_chain_exhausted")) == 2


async def test_resting_rate_limit_plus_tried_rate_limits_is_still_rate_limited(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok(), fo.http_error(429))
    fake.chat(GROQ, QWEN["model"], fo.http_error(429))
    engine = _chain_engine(engines, fake, clock)
    await _reply(engine, comment, catalog)  # sealion rests, gptoss answers
    with pytest.raises(ReplyEngineError) as exc:
        await _reply(engine, comment, catalog)
    assert exc.value.kind == "rate_limited"


# -------------------------------------------------------------------------------------- one shared ChainState (R5)


async def test_reply_and_narrate_running_together_share_one_chain_state(
    engines, fake, clock, catalog, comment, segment
):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    slow = fo.stream_reply("Dạ gptoss chào bạn. ", "Kem giá 250.000đ nha.", delay=0.1, routed_via=GPTOSS_ROUTE)
    fake.chat(LOCAL, GPTOSS["model"], slow)
    engine = _chain_engine(engines, fake, clock)
    turns = _recorder(engine)

    narrate = asyncio.create_task(_narrate(engine, segment, catalog))
    await _wait_for(lambda: _requests(fake, GPTOSS) == 1)  # sealion failed and rests; narrate is still on gptoss
    reply = asyncio.create_task(_reply(engine, comment, catalog))
    async with asyncio.timeout(3):
        script, answer = await asyncio.gather(narrate, reply)

    assert script == answer == GPTOSS_SAYS
    assert _requests(fake, SEALION) == 1  # the comment turn saw the rest the scripted turn caused
    by_kind = {t.kind: t for t in turns}
    assert _summary(by_kind["segment"])[0] == ("sealion", "failed", AttemptReason.RATE_LIMITED)
    assert _summary(by_kind["reply"]) == [("sealion", "skipped", AttemptReason.RATE_LIMITED), ("gptoss", "ok", None)]


# ------------------------------------------------------------------------------------------- fault hook (R8, FR-016)


class _Faults:
    """Stand-in for `director/faults.py` `take_entry`: a queue of modes per label, recording every call."""

    def __init__(self, **queued: list[str]) -> None:
        self.queued = {label: list(modes) for label, modes in queued.items()}
        self.calls: list[str] = []

    def __call__(self, label: str) -> str | None:
        self.calls.append(label)
        modes = self.queued.get(label)
        return modes.pop(0) if modes else None


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("rate_limited", AttemptReason.RATE_LIMITED),
        ("overloaded", AttemptReason.OVERLOADED),
        ("wrong_platform", AttemptReason.WRONG_PLATFORM),
        ("empty", AttemptReason.EMPTY),
        ("timeout", AttemptReason.TIMEOUT),
    ],
)
async def test_an_injected_fault_takes_the_real_failure_path_without_a_request(
    engines, fake, clock, catalog, comment, brain_logs, mode, reason
):
    fake.chat(LOCAL, SEALION["model"], _sealion_ok())
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    faults = _Faults(sealion=[mode])
    engine = _chain_engine(
        engines, fake, clock, {**SEALION, "first_sentence_timeout_s": 0.2}, GPTOSS, QWEN, fault_hook=faults
    )
    turns = _recorder(engine)
    async with asyncio.timeout(3):
        assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert faults.calls == ["sealion", "gptoss"]
    assert _requests(fake, SEALION) == 0  # no network call for an injected fault
    (turn,) = turns
    assert _summary(turn) == [("sealion", "failed", reason), ("gptoss", "ok", None)]
    assert [a.injected for a in turn.attempts] == [True, False]
    if mode == "timeout":
        assert turn.attempts[0].elapsed_s >= 0.18  # waits the entry's own limit, like a real hang
    attempts = _events(brain_logs, "llm_attempt")
    assert [(r.fields["label"], r.fields["injected"]) for r in attempts] == [("sealion", True), ("gptoss", False)]
    (rest,) = _events(brain_logs, "llm_entry_rest")
    assert (rest.fields["label"], rest.fields["reason"]) == ("sealion", reason.value)
    (switch,) = _events(brain_logs, "llm_switch")
    assert switch.fields["reason"] == reason.value


async def test_injected_interrupted_cuts_the_real_stream_after_the_first_sentence(
    engines, fake, clock, catalog, comment, brain_logs
):
    fake.chat(LOCAL, SEALION["model"], _sealion_ok())
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    faults = _Faults(sealion=["interrupted"])
    engine = _chain_engine(engines, fake, clock, fault_hook=faults)
    turns = _recorder(engine)
    out: list[str] = []
    with pytest.raises(ReplyEngineError) as exc:
        async for sentence in engine.reply(comment, catalog):
            out.append(sentence)
    assert exc.value.kind == "api_error"
    assert out == SEALION_SAYS[:1]
    assert _requests(fake, SEALION) == 1  # the real stream was opened (research R8)
    assert fake.served[0].closed
    assert _requests(fake, GPTOSS) == 0
    (turn,) = turns
    assert (turn.outcome, turn.label) == ("interrupted", "sealion")
    assert _summary(turn) == [("sealion", "failed", AttemptReason.INTERRUPTED)]
    assert turn.attempts[0].injected is True
    (rest,) = _events(brain_logs, "llm_entry_rest")
    assert rest.fields["reason"] == "interrupted"
    assert _events(brain_logs, "llm_attempt")[-1].fields["injected"] is True


async def test_a_fault_queued_for_a_resting_entry_waits_until_it_is_tried(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429), _sealion_ok())
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    faults = _Faults()
    engine = _chain_engine(engines, fake, clock, fault_hook=faults)
    turns = _recorder(engine)
    await _reply(engine, comment, catalog)  # sealion now rests
    faults.calls.clear()
    faults.queued["sealion"] = ["overloaded"]

    await _reply(engine, comment, catalog)
    assert faults.calls == ["gptoss"]  # never asked for a resting entry
    assert faults.queued["sealion"] == ["overloaded"]

    clock.advance(COOLDOWN)
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert faults.queued["sealion"] == []
    assert _summary(turns[-1])[0] == ("sealion", "failed", AttemptReason.OVERLOADED)
    assert turns[-1].attempts[0].injected is True
    assert _requests(fake, SEALION) == 1


@pytest.mark.parametrize("hook_result", ["no-such-mode", "error", "raises"])
async def test_an_unusable_fault_hook_answer_runs_the_turn_normally(
    engines, fake, clock, catalog, comment, hook_result
):
    # `error` is a whole-step mode of 004, not an entry mode: it must not be guessed into a reason here.
    def hook(label: str) -> str | None:
        if hook_result == "raises":
            raise RuntimeError("hook bug")
        return hook_result if label == "sealion" else None

    fake.chat(LOCAL, SEALION["model"], _sealion_ok())
    engine = _chain_engine(engines, fake, clock, fault_hook=hook)
    turns = _recorder(engine)
    assert await _reply(engine, comment, catalog) == SEALION_SAYS
    assert _summary(turns[0]) == [("sealion", "ok", None)]
    assert turns[0].attempts[0].injected is False


async def test_cancelling_during_an_injected_timeout_does_not_rest_the_entry(
    engines, fake, clock, catalog, comment, brain_logs
):
    # Quickstart US2 step 8: inject `timeout` for entry 1, then press "Bỏ qua" at once.
    fake.chat(LOCAL, SEALION["model"], _sealion_ok())
    faults = _Faults(sealion=["timeout"])
    engine = _chain_engine(engines, fake, clock, fault_hook=faults)
    turns = _recorder(engine)
    task = asyncio.create_task(_reply(engine, comment, catalog))
    await _wait_for(lambda: faults.calls == ["sealion"])
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert turns[0].outcome == "cancelled"
    assert [(a.outcome, a.injected) for a in turns[0].attempts] == [("cancelled", True)]
    assert _events(brain_logs, "llm_entry_rest") == []
    assert await _reply(engine, comment, catalog) == SEALION_SAYS


@pytest.mark.parametrize("mode", ["rate_limited", "overloaded", "wrong_platform"])
async def test_an_immediate_injected_fault_adds_under_a_second_to_the_first_sentence(
    engines, fake, clock, catalog, segment, mode
):
    """SC-003 on the fake provider: entry 1 failing at once costs < 1 s against entry 2 answering by itself."""

    async def first_sentence_after(engine: ChainReplyEngine) -> float:
        started = time.monotonic()
        stream = engine.narrate(segment, catalog)
        try:
            await anext(stream)
        finally:
            await stream.aclose()
        return time.monotonic() - started

    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    alone = await first_sentence_after(_chain_engine(engines, fake, clock, GPTOSS, QWEN))
    switched = await first_sentence_after(
        _chain_engine(engines, fake, clock, SEALION, GPTOSS, QWEN, fault_hook=_Faults(sealion=[mode]))
    )
    assert switched - alone < 1.0
    assert _requests(fake, SEALION) == 0


# =====================================================================================================================
# US3 (T037): snapshot() and the state observer (data-model §6, contracts/api.md §2, FR-017, FR-019)
# =====================================================================================================================


def _row(
    raw: dict[str, Any],
    position: int,
    status: str = "ready",
    reason: str | None = None,
    retry_at: str | None = None,
) -> dict[str, Any]:
    """One `entries[]` item of a `ChainSnapshot`, as the control page reads it."""
    return {
        "label": raw["label"],
        "model": raw["model"],
        "platform": raw.get("platform"),
        "position": position,
        "status": status,
        "reason": reason,
        "retry_at": retry_at,
    }


def _states(engine: ChainReplyEngine) -> list[ChainSnapshot]:
    snapshots: list[ChainSnapshot] = []
    engine.add_state_observer(snapshots.append)
    return snapshots


def _statuses(snapshot: ChainSnapshot) -> list[tuple[str, str]]:
    return [(row["label"], row["status"]) for row in snapshot["entries"]]


async def test_snapshot_before_any_turn_lists_every_entry_ready_in_chain_order(engines, fake, clock):
    engine = _chain_engine(engines, fake, clock)
    snapshot = engine.snapshot()
    assert snapshot == {
        "entries": [_row(SEALION, 1), _row(GPTOSS, 2), _row(QWEN, 3)],
        "last_entry": None,
        "using_backup": False,
    }
    # The app publishes it as is on the EventBus and in `/api/state` (contracts/api.md §1, §2).
    assert json.loads(json.dumps(snapshot)) == snapshot


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        pytest.param(fo.http_error(429), "rate_limited", id="rate-limited"),
        # FR-019: the key gateway going down mid-show is shown like any other rest, no special warning.
        pytest.param(fo.connect_error(), "connection", id="gateway-down"),
    ],
)
async def test_snapshot_after_a_switch_shows_the_rest_and_the_backup_entry(
    engines, fake, clock, catalog, comment, failure, reason
):
    fake.chat(LOCAL, SEALION["model"], failure)
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    snapshot = engine.snapshot()
    assert snapshot == {
        "entries": [
            _row(SEALION, 1, "resting", reason, _retry_at()),
            _row(GPTOSS, 2),
            _row(QWEN, 3),
        ],
        "last_entry": "gptoss",
        "using_backup": True,
    }
    assert json.loads(json.dumps(snapshot)) == snapshot


async def test_state_observer_gets_the_rest_then_the_new_entry_before_the_first_sentence(
    engines, fake, clock, catalog, comment
):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    states = _states(engine)

    stream = engine.reply(comment, catalog)
    try:
        # SC-007: the page must learn about the switch while the backup entry speaks, not when the turn ends.
        assert await anext(stream) == GPTOSS_SAYS[0]
        assert len(states) == 2
    finally:
        await stream.aclose()

    rested, switched = states
    assert rested["entries"][0] == _row(SEALION, 1, "resting", "rate_limited", _retry_at())
    assert (rested["last_entry"], rested["using_backup"]) == (None, False)
    assert switched["entries"][0] == _row(SEALION, 1, "resting", "rate_limited", _retry_at())
    assert (switched["last_entry"], switched["using_backup"]) == ("gptoss", True)


async def test_state_observer_is_called_only_when_the_chain_state_changes(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], _sealion_ok(), _sealion_ok(), fo.http_error(429), _sealion_ok())
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    states = _states(engine)

    # First turn of the run: no entry has spoken yet, so entry 1 speaking is a change.
    assert await _reply(engine, comment, catalog) == SEALION_SAYS
    assert len(states) == 1
    assert (states[-1]["last_entry"], states[-1]["using_backup"]) == ("sealion", False)

    # Same entry again: nothing to tell the page.
    assert await _reply(engine, comment, catalog) == SEALION_SAYS
    assert len(states) == 1

    # Entry 1 rests and entry 2 speaks: two changes.
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert len(states) == 3
    assert _statuses(states[1]) == [("sealion", "resting"), ("gptoss", "ready"), ("qwen", "ready")]
    assert states[1]["last_entry"] == "sealion"
    assert (states[2]["last_entry"], states[2]["using_backup"]) == ("gptoss", True)

    # Skipping a resting entry changes nothing.
    clock.advance(10)
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert len(states) == 3

    # Back on entry 1 after the rest (FR-015): the page drops the backup warning.
    clock.advance(COOLDOWN)
    assert await _reply(engine, comment, catalog) == SEALION_SAYS
    assert len(states) == 4
    assert states[3] == {
        "entries": [_row(SEALION, 1), _row(GPTOSS, 2), _row(QWEN, 3)],
        "last_entry": "sealion",
        "using_backup": False,
    }


async def test_a_rest_past_retry_at_reads_ready_without_a_new_event(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(503))
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    await _reply(engine, comment, catalog)
    states = _states(engine)

    clock.advance(COOLDOWN - 1)
    assert engine.snapshot()["entries"][0] == _row(SEALION, 1, "resting", "overloaded", _retry_at())
    clock.advance(1)  # retry_at reached (FR-019, research R9: no background wake-up)
    snapshot = engine.snapshot()
    assert snapshot["entries"][0] == _row(SEALION, 1)
    # The last turn still spoke on the backup entry; only a new turn changes that.
    assert (snapshot["last_entry"], snapshot["using_backup"]) == ("gptoss", True)
    assert states == []


async def test_failure_after_the_first_sentence_reports_the_interrupted_rest(engines, fake, clock, catalog, comment):
    events = [fo.Role(), fo.Text("Dạ SEA-LION chào bạn. "), fo.Disconnect()]
    fake.chat(LOCAL, SEALION["model"], fo.ChatReply(events=events, routed_via=SEALION_ROUTE))
    engine = _chain_engine(engines, fake, clock)
    states = _states(engine)
    with pytest.raises(ReplyEngineError):
        await _reply(engine, comment, catalog)
    assert len(states) == 2
    assert (states[0]["last_entry"], _statuses(states[0])[0]) == ("sealion", ("sealion", "ready"))
    assert states[1]["entries"][0] == _row(SEALION, 1, "resting", "interrupted", _retry_at())
    assert (states[1]["last_entry"], states[1]["using_backup"]) == ("sealion", False)


async def test_content_filter_switch_reports_only_the_new_entry(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.content_filtered(routed_via=SEALION_ROUTE))
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    states = _states(engine)
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    (state,) = states  # `blocked` does not rest the entry (research R3)
    assert state["entries"][0] == _row(SEALION, 1)
    assert (state["last_entry"], state["using_backup"]) == ("gptoss", True)


async def test_every_entry_resting_shows_every_status_resting(engines, fake, clock, catalog, comment):
    """Edge case "the whole chain rests when the show starts": the page shows the red warning from the snapshot."""
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], fo.connect_error())
    fake.chat(GROQ, QWEN["model"], fo.http_error(503))
    engine = _chain_engine(engines, fake, clock)
    states = _states(engine)
    with pytest.raises(ReplyEngineError):
        await _reply(engine, comment, catalog)

    expected = {
        "entries": [
            _row(SEALION, 1, "resting", "rate_limited", _retry_at()),
            _row(GPTOSS, 2, "resting", "connection", _retry_at()),
            _row(QWEN, 3, "resting", "overloaded", _retry_at()),
        ],
        "last_entry": None,
        "using_backup": False,
    }
    assert engine.snapshot() == expected
    assert len(states) == 3  # one per rest
    assert states[-1] == expected

    # A turn that only skips resting entries changes nothing.
    clock.advance(5)
    with pytest.raises(ReplyEngineError):
        await _reply(engine, comment, catalog)
    assert len(states) == 3
    assert all(row["status"] == "resting" for row in engine.snapshot()["entries"])


async def test_cancelling_before_the_first_sentence_reports_nothing(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.hang_without_text(routed_via=SEALION_ROUTE))
    engine = _chain_engine(engines, fake, clock)
    states = _states(engine)
    task = asyncio.create_task(_reply(engine, comment, catalog))
    await _wait_for(lambda: _requests(fake, SEALION) == 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert states == []
    assert _statuses(engine.snapshot())[0] == ("sealion", "ready")


async def test_a_failing_state_observer_does_not_break_the_turn(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)

    def boom(_snapshot: ChainSnapshot) -> None:
        raise RuntimeError("observer bug")

    engine.add_state_observer(boom)
    states = _states(engine)
    assert await _reply(engine, comment, catalog) == GPTOSS_SAYS
    assert len(states) == 2  # later observers still run


async def test_each_observer_call_gets_its_own_snapshot(engines, fake, clock, catalog, comment):
    fake.chat(LOCAL, SEALION["model"], fo.http_error(429))
    fake.chat(LOCAL, GPTOSS["model"], _gptoss_ok())
    engine = _chain_engine(engines, fake, clock)
    states = _states(engine)
    await _reply(engine, comment, catalog)
    states[0]["entries"][0]["status"] = "resting-edited"
    assert states[1]["entries"][0]["status"] == "resting"
    assert engine.snapshot()["entries"][0]["status"] == "resting"
