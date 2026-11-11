"""`ReplyEngine` contract.

T113: `reply()` (001 contracts/adapters.md "Hành vi bắt buộc"). T013: `narrate()` (004 contracts/adapters.md §1).
T018 (008): `ChainReplyEngine` on the fake OpenAI-compatible provider runs every case (008 contracts/adapters.md §1).
"""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import AsyncIterator

import anyio
import pytest

from ai_live.core.models import SegmentRequest, Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.models import ProductCatalog

pytestmark = pytest.mark.anyio

ALLOWED_KINDS = {"api_error", "rate_limited", "provider_blocked", "config_error"}

SENTENCES = [
    "Dạ chào bạn Lan nha.",
    "Kem 50 ml giá 250.000đ, loại 100 ml giá 420.000đ ạ!",
    "Bạn chọn loại nào ạ?",
]


async def test_reply_yields_complete_nonempty_str_sentences(reply_engine_harness, comment, catalog):
    engine = reply_engine_harness.engine(SENTENCES)
    stream = engine.reply(comment, catalog)
    assert isinstance(stream, AsyncIterator)
    with anyio.fail_after(2):
        out = [s async for s in stream]
    assert all(isinstance(s, str) for s in out)
    assert all(s.strip() for s in out), out
    # Deltas cut words and sentences apart; the engine must reassemble whole sentences, nothing more or less.
    assert out == SENTENCES


async def test_provider_failure_raises_reply_engine_error_with_known_kind(reply_failure, comment, catalog):
    with pytest.raises(ReplyEngineError) as exc:
        engine = reply_failure.make()
        with anyio.fail_after(2):
            async for _ in engine.reply(comment, catalog):
                pass
    assert exc.value.kind in ALLOWED_KINDS
    assert exc.value.kind == reply_failure.kind


async def test_reply_does_not_change_catalog(reply_engine_harness, comment, catalog):
    before = copy.deepcopy(catalog)
    engine = reply_engine_harness.engine(SENTENCES)
    with anyio.fail_after(2):
        async for _ in engine.reply(comment, catalog):
            pass
    # The guard checks every sentence against this same catalog; an engine that edits it would weaken the guard.
    assert catalog == before
    assert dataclasses.asdict(catalog) == dataclasses.asdict(before)


async def test_aclose_mid_stream_stops_the_stream(reply_engine_harness, comment, catalog):
    engine = reply_engine_harness.open_engine(SENTENCES)
    stream = engine.reply(comment, catalog)
    with anyio.fail_after(2):
        first = await anext(stream)
    assert first == SENTENCES[0]

    # A skipped or timed-out turn closes the stream; that must not wait for the provider.
    with anyio.fail_after(1):
        await stream.aclose()
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    closed = reply_engine_harness.upstream_closed()
    if closed is not None:
        assert closed, "the provider stream (HTTP) must be released on aclose()"


# ---------------------------------------------------------------- narrate() (T013, 004 contracts/adapters.md §1)

# Show topics have no product; product topics need one (SegmentRequest checks it).
NARRATE_CASES = [
    (Topic.OPENING, False),
    (Topic.INTRO, True),
    (Topic.PRICE, True),
    (Topic.CLOSING, False),
]


def _segment(topic: Topic, catalog: ProductCatalog, with_product: bool) -> SegmentRequest:
    return SegmentRequest(
        segment_id=f"seg-{topic.value}",
        topic=topic,
        product_id=catalog.primary.id if with_product else None,
        min_sentences=2,
        max_sentences=4,
        previous_sentence="Dạ chào cả nhà.",
        recent_lines=("Dạ chào cả nhà.",),
    )


@pytest.mark.parametrize(("topic", "with_product"), NARRATE_CASES, ids=[t.value for t, _ in NARRATE_CASES])
async def test_narrate_yields_nonempty_str_sentences(reply_engine_harness, catalog, topic, with_product):
    engine = reply_engine_harness.narrator()
    stream = engine.narrate(_segment(topic, catalog, with_product), catalog)
    assert isinstance(stream, AsyncIterator)
    with anyio.fail_after(2):
        out = [s async for s in stream]
    # A segment that ends without a word and without an error would leave dead air the runner cannot explain.
    assert out, "narrate() finished without a sentence and without ReplyEngineError"
    assert all(isinstance(s, str) for s in out), out
    assert all(s.strip() for s in out), out


async def test_narrate_failure_raises_reply_engine_error_with_known_kind(narrate_failure, catalog):
    engine = narrate_failure.make()
    with pytest.raises(ReplyEngineError) as exc:
        with anyio.fail_after(2):
            async for _ in engine.narrate(_segment(Topic.INTRO, catalog, True), catalog):
                pass
    assert exc.value.kind in ALLOWED_KINDS
    assert exc.value.kind == narrate_failure.kind


@pytest.mark.parametrize(("topic", "with_product"), NARRATE_CASES[:2], ids=[t.value for t, _ in NARRATE_CASES[:2]])
async def test_narrate_does_not_change_catalog(reply_engine_harness, catalog, topic, with_product):
    before = copy.deepcopy(catalog)
    engine = reply_engine_harness.narrator()
    with anyio.fail_after(2):
        async for _ in engine.narrate(_segment(topic, catalog, with_product), catalog):
            pass
    # The catalog is shared by the guard, the planner and the control page; the engine only reads it.
    assert catalog == before
    assert dataclasses.asdict(catalog) == dataclasses.asdict(before)
