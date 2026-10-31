"""T113: `ReplyEngine` contract (contracts/adapters.md "Hành vi bắt buộc", `ReplyEngine.reply`)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import anyio
import pytest

from ai_live.core.protocols import ReplyEngineError

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
