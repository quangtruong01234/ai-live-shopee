"""T115: `CommentSource` contract (contracts/adapters.md, `CommentSource`).

Only lifecycle and shape are checked: what `stream()` yields depends on the source (MockSource yields nothing, a
pulled source like YouTube yields live comments), so the body of the stream is not iterated here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import anyio
import pytest

pytestmark = pytest.mark.anyio


def test_name_is_nonempty_str(source_harness):
    source = source_harness.make()
    assert isinstance(source.name, str)
    assert source.name.strip()


async def test_start_and_stop_twice_do_not_raise(source_harness):
    source = source_harness.make()
    with anyio.fail_after(2):
        await source.start()
        await source.start()
        await source.stop()
        await source.stop()


async def test_stream_is_async_iterator(source_harness):
    source = source_harness.make()
    await source.start()
    try:
        stream = source.stream()
        assert isinstance(stream, AsyncIterator)
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            with anyio.fail_after(2):
                await aclose()
    finally:
        await source.stop()
