"""T034: `GeminiReplyEngine` with a fake client, no network calls (research R5)."""

from __future__ import annotations

import anyio
import pytest
from google.genai import types

from ai_live.brain.gemini_engine import GeminiReplyEngine
from ai_live.core.models import Comment
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
