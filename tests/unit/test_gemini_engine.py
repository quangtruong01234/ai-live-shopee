"""T034 (001) and T021 (004): `GeminiReplyEngine` with a fake client, no network calls (research R5, 004 R3)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import anyio
import pytest
from google.genai import types

from ai_live.brain.gemini_engine import GeminiReplyEngine
from ai_live.brain.prompt import build_system_prompt, build_user_message
from ai_live.brain.script_prompt import build_script_system_prompt, build_segment_message
from ai_live.core.config import Settings
from ai_live.core.models import Comment, SegmentRequest, Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.docx_loader import load_catalog
from fixtures.content_builder import valid_docx
from fixtures.fake_genai import FakeModels, api_error, chunk, fake_client

pytestmark = pytest.mark.anyio


@pytest.fixture
def catalog():
    return load_catalog(valid_docx(), "valid.docx", 5_000_000)


@pytest.fixture
def comment():
    return Comment(id="c1", source="mock", author="Lan", text="giá bao nhiêu vậy shop?", received_at=0.0)


def _engine(models: FakeModels) -> GeminiReplyEngine:
    return GeminiReplyEngine(fake_client(models), model="gemini-test", thinking_level="low", max_output_tokens=300)


async def _collect(engine, comment, catalog) -> list[str]:
    return [s async for s in engine.reply(comment, catalog)]


async def test_deltas_go_through_splitter_and_yield_sentences(catalog, comment):
    models = FakeModels(
        [
            chunk("Dạ chào bạn "),
            chunk("Lan. Kem 50 ml giá 250."),
            chunk("000đ, loại 100 ml giá 420.000đ nha! Bạn chọn"),
            chunk(" loại nào ạ?", finish_reason=types.FinishReason.STOP),
        ]
    )
    out = await _collect(_engine(models), comment, catalog)
    assert out == [
        "Dạ chào bạn Lan.",
        "Kem 50 ml giá 250.000đ, loại 100 ml giá 420.000đ nha!",
        "Bạn chọn loại nào ạ?",
    ]


async def test_call_uses_settings_and_prompt(catalog, comment):
    models = FakeModels([chunk("Dạ chào bạn Lan nha.")])
    await _collect(_engine(models), comment, catalog)
    call = models.calls[0]
    assert call["model"] == "gemini-test"
    config = call["config"]
    assert config.max_output_tokens == 300
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert "<products>" in config.system_instruction
    assert '<comment author="Lan">' in str(call["contents"])


async def test_http_429_becomes_llm_error_without_retry(catalog, comment):
    models = FakeModels(call_error=api_error(429, "RESOURCE_EXHAUSTED", "quota"))
    with pytest.raises(ReplyEngineError) as exc:
        await _collect(_engine(models), comment, catalog)
    assert exc.value.kind == "rate_limited"
    assert len(models.calls) == 1


async def test_api_error_during_stream(catalog, comment):
    models = FakeModels(
        [chunk("Dạ chào bạn Lan. ")],
        iter_error=api_error(500, "INTERNAL", "boom"),
    )
    out = []
    with pytest.raises(ReplyEngineError) as exc:
        async for s in _engine(models).reply(comment, catalog):
            out.append(s)
    assert exc.value.kind == "api_error"
    assert out == ["Dạ chào bạn Lan."]


@pytest.mark.parametrize("reason", [types.FinishReason.SAFETY, types.FinishReason.PROHIBITED_CONTENT])
async def test_safety_finish_reason_is_provider_blocked(catalog, comment, reason):
    models = FakeModels([chunk(None, finish_reason=reason)])
    with pytest.raises(ReplyEngineError) as exc:
        await _collect(_engine(models), comment, catalog)
    assert exc.value.kind == "provider_blocked"


async def test_prompt_block_reason_is_provider_blocked(catalog, comment):
    models = FakeModels([chunk(None, block_reason=types.BlockedReason.SAFETY)])
    with pytest.raises(ReplyEngineError) as exc:
        await _collect(_engine(models), comment, catalog)
    assert exc.value.kind == "provider_blocked"


async def test_empty_text_is_provider_blocked(catalog, comment):
    models = FakeModels([chunk(""), chunk(None, finish_reason=types.FinishReason.STOP)])
    with pytest.raises(ReplyEngineError) as exc:
        await _collect(_engine(models), comment, catalog)
    assert exc.value.kind == "provider_blocked"


async def test_cancel_closes_stream(catalog, comment):
    models = FakeModels([chunk("Dạ chào bạn Lan. ")], hang_after=1)
    got: list[str] = []

    async def consume():
        async for s in _engine(models).reply(comment, catalog):
            got.append(s)

    with anyio.move_on_after(0.2):
        await consume()
    assert got == ["Dạ chào bạn Lan."]
    assert models.closed


# ---------------------------------------------------------------- narrate() (004 T021, contracts/adapters.md §1)


@pytest.fixture
def segment(catalog):
    return SegmentRequest(
        segment_id="seg-0007",
        topic=Topic.PRICE,
        product_id=catalog.primary.id,
        min_sentences=3,
        max_sentences=6,
        previous_sentence="Kem này thấm nhanh lắm nha anh chị.",
        recent_lines=("Câu đã nói về kem.",),
    )


def _script_engine(models: FakeModels) -> GeminiReplyEngine:
    return GeminiReplyEngine(
        fake_client(models), model="gemini-test", thinking_level="low", max_output_tokens=300, script_max_tokens=600
    )


async def _narrate(engine, segment, catalog) -> list[str]:
    return [s async for s in engine.narrate(segment, catalog)]


async def test_reply_prompt_is_unchanged_by_004(catalog, comment):
    # The 001 comment path keeps its own prompt and token budget.
    models = FakeModels([chunk("Dạ chào bạn Lan nha.")])
    await _collect(_script_engine(models), comment, catalog)
    call = models.calls[0]
    assert call["config"].system_instruction == build_system_prompt(catalog)
    assert call["contents"] == build_user_message(comment)
    assert call["config"].max_output_tokens == 300


async def test_narrate_uses_script_prompt_segment_message_and_script_tokens(catalog, segment):
    models = FakeModels([chunk("Dạ kem có hai phân loại nha anh chị.")])
    await _narrate(_script_engine(models), segment, catalog)
    call = models.calls[0]
    assert call["model"] == "gemini-test"
    config = call["config"]
    assert config.system_instruction == build_script_system_prompt(catalog)
    assert call["contents"] == build_segment_message(segment, catalog)
    assert config.max_output_tokens == 600
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW


async def test_narrate_yields_split_sentences(catalog, segment):
    models = FakeModels(
        [
            chunk("Kem chống nắng X có hai "),
            chunk("phân loại nha anh chị. Loại 50 ml giá 250."),
            chunk("000đ, loại 100 ml giá 420.000đ ạ!", finish_reason=types.FinishReason.STOP),
        ]
    )
    out = await _narrate(_script_engine(models), segment, catalog)
    assert out == [
        "Kem chống nắng X có hai phân loại nha anh chị.",
        "Loại 50 ml giá 250.000đ, loại 100 ml giá 420.000đ ạ!",
    ]


async def test_narrate_logs_llm_usage_with_segment_id(catalog, segment):
    last = chunk("Dạ kem có hai phân loại nha anh chị.", finish_reason=types.FinishReason.STOP)
    last.usage_metadata = SimpleNamespace(
        prompt_token_count=1200, candidates_token_count=80, cached_content_token_count=1024
    )
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    brain_logger = logging.getLogger("ai_live.brain")
    brain_logger.addHandler(handler)
    old_level = brain_logger.level
    brain_logger.setLevel(logging.INFO)
    try:
        await _narrate(_script_engine(FakeModels([last])), segment, catalog)
    finally:
        brain_logger.removeHandler(handler)
        brain_logger.setLevel(old_level)
    usage = [r for r in records if r.getMessage() == "llm_usage"]
    assert len(usage) == 1
    fields = usage[0].fields  # type: ignore[attr-defined]
    assert fields["segment_id"] == "seg-0007"
    assert "comment_id" not in fields
    assert fields["prompt_tokens"] == 1200
    assert fields["output_tokens"] == 80
    assert fields["cached_tokens"] == 1024


async def test_narrate_http_429_is_rate_limited_without_retry(catalog, segment):
    models = FakeModels(call_error=api_error(429, "RESOURCE_EXHAUSTED", "quota"))
    with pytest.raises(ReplyEngineError) as exc:
        await _narrate(_script_engine(models), segment, catalog)
    assert exc.value.kind == "rate_limited"
    assert len(models.calls) == 1


async def test_narrate_empty_text_is_provider_blocked(catalog, segment):
    models = FakeModels([chunk(""), chunk(None, finish_reason=types.FinishReason.STOP)])
    with pytest.raises(ReplyEngineError) as exc:
        await _narrate(_script_engine(models), segment, catalog)
    assert exc.value.kind == "provider_blocked"


async def test_narrate_cancel_closes_stream(catalog, segment):
    models = FakeModels([chunk("Dạ kem có hai phân loại nha. ")], hang_after=1)
    got: list[str] = []

    async def consume():
        async for s in _script_engine(models).narrate(segment, catalog):
            got.append(s)

    with anyio.move_on_after(0.2):
        await consume()
    assert got == ["Dạ kem có hai phân loại nha."]
    assert models.closed


def test_from_settings_reads_script_max_tokens(monkeypatch):
    monkeypatch.setattr("ai_live.brain.gemini_engine.genai.Client", lambda **_: SimpleNamespace())
    settings = Settings(
        _env_file=None,
        reply_engine="gemini",
        gemini_api_key="fake-key",
        llm_max_tokens=300,
        script_max_tokens=700,
    )
    engine = GeminiReplyEngine.from_settings(settings)
    assert engine.max_output_tokens == 300
    assert engine.script_max_tokens == 700
