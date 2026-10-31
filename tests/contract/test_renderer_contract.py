"""T114: `AvatarRenderer` contract (contracts/adapters.md "Hành vi bắt buộc", `speak` and `interrupt`).

"Returns quickly" is checked against a generous bound (0.5 s), never a tight one: the Windows timer ticks ~15.6 ms.
"""

from __future__ import annotations

import asyncio

import anyio
import pytest

from ai_live.core.protocols import RendererUnavailable

pytestmark = pytest.mark.anyio

SAMPLE_RATE = 16000
QUICK_S = 0.5


async def _pcm(chunks: int = 3):
    for _ in range(chunks):
        yield b"\x00\x00" * 160


async def _wait_until(predicate, timeout_s: float = 2.0) -> None:
    # Polling on purpose: the Protocol exposes state only as properties, not as events to wait on.
    with anyio.fail_after(timeout_s):
        while not predicate():  # noqa: ASYNC110
            await anyio.sleep(0.01)


async def test_speak_without_host_raises_renderer_unavailable(renderer_harness):
    renderer = renderer_harness.make()
    await renderer.start()
    with anyio.fail_after(2):
        with pytest.raises(RendererUnavailable):
            await renderer.speak("u1", "Dạ chào bạn.", _pcm(), SAMPLE_RATE)
    assert not renderer.is_speaking
    assert renderer.first_playback_at("u1") is None
    await renderer.stop()


async def test_speak_returns_with_auto_acking_host(renderer_harness):
    renderer = renderer_harness.make()
    await renderer.start()
    await renderer_harness.connect_host(renderer, auto_ack=True)
    with anyio.fail_after(2):
        await renderer.speak("u1", "Dạ chào bạn Lan nha.", _pcm(), SAMPLE_RATE)
    assert not renderer.is_speaking
    assert isinstance(renderer.first_playback_at("u1"), float)
    await renderer.stop()


async def test_speak_returns_only_after_sentence_played(renderer_harness):
    renderer = renderer_harness.make()
    await renderer.start()
    await renderer_harness.connect_host(renderer, auto_ack=False)
    assert renderer.first_playback_at("u1") is None
    assert not renderer.is_speaking

    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn Lan nha.", _pcm(), SAMPLE_RATE))
    try:
        await _wait_until(lambda: renderer.is_speaking)
        # No playback ack yet: the avatar_first_frame milestone must not exist.
        assert renderer.first_playback_at("u1") is None

        await renderer_harness.report_playback_started(renderer)
        await _wait_until(lambda: renderer.first_playback_at("u1") is not None)
        first = renderer.first_playback_at("u1")
        assert isinstance(first, float)
        await anyio.sleep(0.05)
        assert not task.done(), "speak returned before the sentence finished playing"
        assert renderer.is_speaking

        await renderer_harness.report_sentence_played(renderer)
        with anyio.fail_after(2):
            await task
    finally:
        task.cancel()
    assert not renderer.is_speaking
    assert renderer.first_playback_at("u1") == first

    # A second sentence of the same turn keeps the turn's first milestone.
    task = asyncio.create_task(renderer.speak("u1", "Kem giá 250.000đ ạ.", _pcm(), SAMPLE_RATE))
    try:
        await renderer_harness.report_playback_started(renderer)
        await renderer_harness.report_sentence_played(renderer)
        with anyio.fail_after(2):
            await task
    finally:
        task.cancel()
    assert renderer.first_playback_at("u1") == first
    assert renderer.first_playback_at("u2") is None
    await renderer.stop()


async def test_interrupt_when_idle_returns_at_once_and_is_idempotent(renderer_harness):
    renderer = renderer_harness.make()
    await renderer.start()
    with anyio.fail_after(QUICK_S):
        await renderer.interrupt()
        await renderer.interrupt()
    await renderer_harness.connect_host(renderer, auto_ack=True)
    with anyio.fail_after(QUICK_S):
        await renderer.interrupt()
        await renderer.interrupt()
    assert not renderer.is_speaking
    await renderer.stop()


async def test_interrupt_during_speak_returns_at_once_and_ends_speak(renderer_harness):
    renderer = renderer_harness.make()
    await renderer.start()
    # The host never acks on its own, so only interrupt() can end this sentence.
    await renderer_harness.connect_host(renderer, auto_ack=False)
    task = asyncio.create_task(renderer.speak("u1", "Dạ chào bạn Lan nha.", _pcm(), SAMPLE_RATE))
    try:
        await _wait_until(lambda: renderer.is_speaking)
        with anyio.fail_after(QUICK_S):
            await renderer.interrupt()
        with anyio.fail_after(QUICK_S):
            await task  # returns normally: an interrupted sentence is not an error
        assert not renderer.is_speaking
        with anyio.fail_after(QUICK_S):
            await renderer.interrupt()
            await renderer.interrupt()
    finally:
        task.cancel()
    assert not renderer.is_speaking
    await renderer.stop()
