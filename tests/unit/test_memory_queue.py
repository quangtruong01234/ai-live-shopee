"""T011 basic queue, T060 size limit and stale comments (contracts/adapters.md, research R9)."""

import time

import anyio
import pytest

from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.core.events import EventBus, EventType
from ai_live.core.models import Comment, CommentStatus, DropReason, Priority

pytestmark = pytest.mark.anyio


def make_comment(text: str, received_at: float | None = None) -> Comment:
    return Comment(
        id=text,
        source="mock",
        author="Lan",
        text=text,
        received_at=time.monotonic() if received_at is None else received_at,
        platform_ts=None,
        meta={},
    )


async def test_get_orders_by_priority_then_seq():
    q = InMemoryCommentQueue()
    await q.put(make_comment("hello"), Priority.LOW)
    await q.put(make_comment("ship mấy ngày"), Priority.MEDIUM)
    await q.put(make_comment("giá 1"), Priority.HIGH)
    await q.put(make_comment("giá 2"), Priority.HIGH)
    order = [(await q.get()).comment.id for _ in range(4)]
    assert order == ["giá 1", "giá 2", "ship mấy ngày", "hello"]
    assert q.size() == 0


async def test_snapshot_matches_get_order_and_does_not_consume():
    q = InMemoryCommentQueue()
    await q.put(make_comment("a"), Priority.LOW)
    await q.put(make_comment("b"), Priority.HIGH)
    await q.put(make_comment("c"), Priority.MEDIUM)
    snap = [qc.comment.id for qc in q.snapshot()]
    assert snap == ["b", "c", "a"]
    assert q.size() == 3
    got = [(await q.get()).comment.id for _ in range(3)]
    assert got == snap


async def test_queued_comment_carries_priority_and_seq():
    q = InMemoryCommentQueue()
    await q.put(make_comment("a"), Priority.MEDIUM)
    await q.put(make_comment("b"), Priority.MEDIUM)
    first, second = q.snapshot()
    assert first.priority is Priority.MEDIUM
    assert first.seq < second.seq


async def test_get_waits_until_comment_arrives():
    q = InMemoryCommentQueue()
    got: list[str] = []

    async def consumer():
        got.append((await q.get()).comment.id)

    async with anyio.create_task_group() as tg:
        tg.start_soon(consumer)
        await anyio.sleep(0.05)
        assert got == []
        await q.put(make_comment("x"), Priority.HIGH)
    assert got == ["x"]


# --- T060: FIFO within a level, queue_full, stale ---


async def test_fifo_within_same_priority():
    q = InMemoryCommentQueue()
    for name in ["a", "b", "c", "d"]:
        await q.put(make_comment(name), Priority.MEDIUM)
    assert [(await q.get()).comment.id for _ in range(4)] == ["a", "b", "c", "d"]


async def test_put_returns_waiting_queued_comment():
    q = InMemoryCommentQueue()
    queued = await q.put(make_comment("a"), Priority.HIGH)
    assert queued.status is CommentStatus.WAITING
    assert queued.drop_reason is None
    assert q.snapshot() == [queued]


async def test_full_queue_evicts_lowest_priority_earliest(clock):
    bus = EventBus()
    q = InMemoryCommentQueue(max_size=3, bus=bus, clock=clock)
    await q.put(make_comment("low1", clock()), Priority.LOW)
    await q.put(make_comment("low2", clock()), Priority.LOW)
    await q.put(make_comment("mid", clock()), Priority.MEDIUM)
    async with bus.subscribe() as sub:
        queued = await q.put(make_comment("high", clock()), Priority.HIGH)
        events = sub.drain()
    assert queued.status is CommentStatus.WAITING
    assert [qc.comment.id for qc in q.snapshot()] == ["high", "mid", "low2"]
    dropped = [e.payload for e in events if e.type == EventType.COMMENT_DROPPED]
    assert dropped == [{"comment_id": "low1", "author": "Lan", "text": "low1", "reason": "queue_full"}]
    changed = [e.payload for e in events if e.type == EventType.QUEUE_CHANGED]
    assert [item["comment_id"] for item in changed[-1]["queue"]] == ["high", "mid", "low2"]


async def test_full_queue_drops_new_comment_when_strictly_lowest(clock):
    bus = EventBus()
    q = InMemoryCommentQueue(max_size=2, bus=bus, clock=clock)
    await q.put(make_comment("mid1", clock()), Priority.MEDIUM)
    await q.put(make_comment("mid2", clock()), Priority.MEDIUM)
    async with bus.subscribe() as sub:
        queued = await q.put(make_comment("low", clock()), Priority.LOW)
        events = sub.drain()
    assert queued.status is CommentStatus.DROPPED
    assert queued.drop_reason is DropReason.QUEUE_FULL
    assert [qc.comment.id for qc in q.snapshot()] == ["mid1", "mid2"]
    dropped = [e.payload for e in events if e.type == EventType.COMMENT_DROPPED]
    assert [d["comment_id"] for d in dropped] == ["low"]
    assert dropped[0]["reason"] == "queue_full"


async def test_full_queue_same_level_evicts_earliest_existing(clock):
    # The new comment is not strictly lower, so the earliest comment of the lowest level goes.
    q = InMemoryCommentQueue(max_size=2, clock=clock)
    await q.put(make_comment("low1", clock()), Priority.LOW)
    await q.put(make_comment("low2", clock()), Priority.LOW)
    queued = await q.put(make_comment("low3", clock()), Priority.LOW)
    assert queued.status is CommentStatus.WAITING
    assert [qc.comment.id for qc in q.snapshot()] == ["low2", "low3"]


async def test_evicted_comment_is_marked_dropped(clock):
    q = InMemoryCommentQueue(max_size=1, clock=clock)
    first = await q.put(make_comment("low", clock()), Priority.LOW)
    await q.put(make_comment("high", clock()), Priority.HIGH)
    assert first.status is CommentStatus.DROPPED
    assert first.drop_reason is DropReason.QUEUE_FULL


async def test_get_skips_stale_comments(clock):
    bus = EventBus()
    q = InMemoryCommentQueue(max_age_s=30, bus=bus, clock=clock)
    old = await q.put(make_comment("old", clock()), Priority.HIGH)
    clock.advance(20)
    await q.put(make_comment("fresh", clock()), Priority.LOW)
    clock.advance(15)  # "old" is now 35 s old, "fresh" 15 s
    async with bus.subscribe() as sub:
        got = await q.get()
        events = sub.drain()
    assert got.comment.id == "fresh"
    assert old.status is CommentStatus.DROPPED
    assert old.drop_reason is DropReason.STALE
    dropped = [e.payload for e in events if e.type == EventType.COMMENT_DROPPED]
    assert dropped == [{"comment_id": "old", "author": "Lan", "text": "old", "reason": "stale"}]


async def test_get_waits_when_only_stale_comments(clock):
    q = InMemoryCommentQueue(max_age_s=30, clock=clock)
    await q.put(make_comment("old", clock()), Priority.HIGH)
    clock.advance(31)
    with anyio.move_on_after(0.1) as scope:
        await q.get()
    assert scope.cancelled_caught
    assert q.size() == 0


async def test_sweep_drops_stale_and_publishes(clock):
    bus = EventBus()
    q = InMemoryCommentQueue(max_age_s=30, bus=bus, clock=clock)
    await q.put(make_comment("a", clock()), Priority.LOW)
    clock.advance(10)
    await q.put(make_comment("b", clock()), Priority.LOW)
    clock.advance(25)
    async with bus.subscribe() as sub:
        dropped = q.sweep()
        events = sub.drain()
    assert [qc.comment.id for qc in dropped] == ["a"]
    assert [qc.comment.id for qc in q.snapshot()] == ["b"]
    types = [e.type for e in events]
    assert EventType.COMMENT_DROPPED in types
    assert types[-1] == EventType.QUEUE_CHANGED


async def test_sweep_without_stale_publishes_nothing(clock):
    bus = EventBus()
    q = InMemoryCommentQueue(max_age_s=30, bus=bus, clock=clock)
    await q.put(make_comment("a", clock()), Priority.LOW)
    async with bus.subscribe() as sub:
        assert q.sweep() == []
        assert sub.drain() == []


async def test_run_sweeper_drops_stale_every_interval(clock):
    q = InMemoryCommentQueue(max_age_s=30, clock=clock)
    await q.put(make_comment("a", clock()), Priority.LOW)
    clock.advance(31)
    with anyio.move_on_after(0.2):
        await q.run_sweeper(interval_s=0.02)
    assert q.size() == 0


async def test_put_publishes_queue_changed(clock):
    bus = EventBus()
    q = InMemoryCommentQueue(bus=bus, clock=clock)
    async with bus.subscribe() as sub:
        await q.put(make_comment("a", clock()), Priority.HIGH)
        events = sub.drain()
    assert [e.type for e in events] == [EventType.QUEUE_CHANGED]
    assert events[0].payload["queue"][0] == {
        "comment_id": "a",
        "author": "Lan",
        "text": "a",
        "priority": "HIGH",
        "status": "waiting",
    }


async def test_get_publishes_queue_changed(clock):
    bus = EventBus()
    q = InMemoryCommentQueue(bus=bus, clock=clock)
    await q.put(make_comment("a", clock()), Priority.HIGH)
    async with bus.subscribe() as sub:
        await q.get()
        events = sub.drain()
    assert events[-1].type == EventType.QUEUE_CHANGED
    assert events[-1].payload == {"queue": []}
