"""T115: `CommentQueue` contract (contracts/adapters.md "Hành vi bắt buộc", `CommentQueue.put` / `get`).

Drops are reported, never raised: through the returned `QueuedComment` status and a `comment_dropped` event.
"""

from __future__ import annotations

import anyio
import pytest

from ai_live.core.events import EventBus, EventType
from ai_live.core.models import Comment, CommentStatus, DropReason, Priority

pytestmark = pytest.mark.anyio

MAX_AGE_S = 30.0


def _comment(cid: str, received_at: float) -> Comment:
    return Comment(id=cid, source="mock", author="Lan", text=cid, received_at=received_at)


def _dropped(events) -> list[tuple[str, str]]:
    return [(e.payload["comment_id"], e.payload["reason"]) for e in events if e.type == EventType.COMMENT_DROPPED]


async def test_get_order_equals_snapshot_order_equals_priority_then_seq(queue_harness, clock):
    q = queue_harness.make(max_size=50, max_age_s=MAX_AGE_S, bus=None, clock=clock)
    puts = [
        ("low-1", Priority.LOW),
        ("mid-1", Priority.MEDIUM),
        ("high-1", Priority.HIGH),
        ("low-2", Priority.LOW),
        ("high-2", Priority.HIGH),
        ("mid-2", Priority.MEDIUM),
    ]
    queued = [await q.put(_comment(cid, clock()), prio) for cid, prio in puts]
    assert all(item.status is CommentStatus.WAITING for item in queued)

    expected = [item.comment.id for item in sorted(queued, key=lambda item: (item.priority, item.seq))]
    assert expected == ["high-1", "high-2", "mid-1", "mid-2", "low-1", "low-2"]
    assert [item.comment.id for item in q.snapshot()] == expected
    assert q.size() == len(puts), "snapshot must not consume"

    with anyio.fail_after(2):
        got = [(await q.get()).comment.id for _ in puts]
    assert got == expected
    assert q.size() == 0


async def test_full_queue_evicts_lowest_priority_earliest(queue_harness, clock):
    bus = EventBus()
    q = queue_harness.make(max_size=3, max_age_s=MAX_AGE_S, bus=bus, clock=clock)
    low_1 = await q.put(_comment("low-1", clock()), Priority.LOW)
    await q.put(_comment("mid", clock()), Priority.MEDIUM)
    await q.put(_comment("low-2", clock()), Priority.LOW)

    async with bus.subscribe() as sub:
        new = await q.put(_comment("high", clock()), Priority.HIGH)
        events = sub.drain()
    assert new.status is CommentStatus.WAITING
    assert low_1.status is CommentStatus.DROPPED
    assert low_1.drop_reason is DropReason.QUEUE_FULL
    assert _dropped(events) == [("low-1", "queue_full")]
    assert [item.comment.id for item in q.snapshot()] == ["high", "mid", "low-2"]
    assert q.size() == 3


async def test_full_queue_drops_new_comment_when_strictly_lowest(queue_harness, clock):
    bus = EventBus()
    q = queue_harness.make(max_size=2, max_age_s=MAX_AGE_S, bus=bus, clock=clock)
    await q.put(_comment("high", clock()), Priority.HIGH)
    await q.put(_comment("mid", clock()), Priority.MEDIUM)

    async with bus.subscribe() as sub:
        new = await q.put(_comment("low", clock()), Priority.LOW)
        events = sub.drain()
    assert new.status is CommentStatus.DROPPED
    assert new.drop_reason is DropReason.QUEUE_FULL
    assert _dropped(events) == [("low", "queue_full")]
    assert [item.comment.id for item in q.snapshot()] == ["high", "mid"]


async def test_full_queue_same_level_evicts_earliest_existing(queue_harness, clock):
    # The new comment is not strictly lower than everything, so the earliest of the lowest level makes room.
    bus = EventBus()
    q = queue_harness.make(max_size=2, max_age_s=MAX_AGE_S, bus=bus, clock=clock)
    await q.put(_comment("low-1", clock()), Priority.LOW)
    await q.put(_comment("low-2", clock()), Priority.LOW)

    async with bus.subscribe() as sub:
        new = await q.put(_comment("low-3", clock()), Priority.LOW)
        events = sub.drain()
    assert new.status is CommentStatus.WAITING
    assert _dropped(events) == [("low-1", "queue_full")]
    assert [item.comment.id for item in q.snapshot()] == ["low-2", "low-3"]


async def test_get_drops_stale_comment_and_returns_next(queue_harness, clock):
    bus = EventBus()
    q = queue_harness.make(max_size=50, max_age_s=MAX_AGE_S, bus=bus, clock=clock)
    old = await q.put(_comment("old", clock()), Priority.HIGH)
    clock.advance(MAX_AGE_S / 2)
    await q.put(_comment("fresh", clock()), Priority.LOW)
    clock.advance(MAX_AGE_S / 2 + 1)  # "old" is now past max age, "fresh" is not

    async with bus.subscribe() as sub:
        with anyio.fail_after(2):
            got = await q.get()
        events = sub.drain()
    assert got.comment.id == "fresh"
    assert old.status is CommentStatus.DROPPED
    assert old.drop_reason is DropReason.STALE
    assert _dropped(events) == [("old", "stale")]
    assert q.size() == 0


async def test_get_skips_only_stale_comments_and_waits_for_a_fresh_one(queue_harness, clock):
    q = queue_harness.make(max_size=50, max_age_s=MAX_AGE_S, bus=None, clock=clock)
    old = await q.put(_comment("old", clock()), Priority.HIGH)
    clock.advance(MAX_AGE_S + 1)
    got: list[str] = []

    async def consumer() -> None:
        got.append((await q.get()).comment.id)

    with anyio.fail_after(2):
        async with anyio.create_task_group() as tg:
            tg.start_soon(consumer)
            await anyio.sleep(0.05)
            assert got == []
            await q.put(_comment("fresh", clock()), Priority.LOW)
    assert got == ["fresh"]
    assert old.drop_reason is DropReason.STALE
