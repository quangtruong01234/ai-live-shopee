"""T012: EventBus (contracts/adapters.md, contracts/events.md §3)."""

import time

import anyio
import pytest

from ai_live.core.events import Event, EventBus, EventType

pytestmark = pytest.mark.anyio


async def take(sub, n: int) -> list[Event]:
    out = []
    with anyio.fail_after(1):
        async for event in sub:
            out.append(event)
            if len(out) == n:
                break
    return out


async def test_every_subscriber_receives_in_publish_order():
    bus = EventBus()
    sub_a = bus.subscribe()
    sub_b = bus.subscribe()
    for i in range(3):
        bus.publish(Event(EventType.SENTENCE, {"seq": i}))
    for sub in (sub_a, sub_b):
        events = await take(sub, 3)
        assert [e.payload["seq"] for e in events] == [0, 1, 2]
        assert all(e.type is EventType.SENTENCE for e in events)


async def test_full_subscriber_drops_oldest_without_affecting_others():
    bus = EventBus(max_queue=1000)
    slow = bus.subscribe()
    fast = bus.subscribe()
    fast_seen: list[int] = []
    for i in range(1005):
        bus.publish(Event(EventType.QUEUE_CHANGED, {"i": i}))
        # subscriber nhanh đọc ngay nên không bao giờ đầy
        fast_seen += [e.payload["i"] for e in fast.drain()]
    assert fast_seen == list(range(1005))
    slow_events = await take(slow, 1000)
    assert [e.payload["i"] for e in slow_events] == list(range(5, 1005))
    assert slow.dropped == 5
    assert fast.dropped == 0


async def test_publish_does_not_wait_for_slow_subscriber():
    bus = EventBus(max_queue=10)
    bus.subscribe()  # không ai đọc
    # publish đồng bộ nên không có điểm await nào cho fail_after cắt ngang: đo thời gian trực tiếp.
    start = time.perf_counter()
    for i in range(10_000):
        bus.publish(Event(EventType.LATENCY, {"i": i}))
    assert time.perf_counter() - start < 0.5


async def test_closed_subscription_stops_receiving():
    bus = EventBus()
    sub = bus.subscribe()
    sub.close()
    bus.publish(Event(EventType.STATE, {}))
    assert bus.subscriber_count == 0
    with anyio.fail_after(1):
        assert [e async for e in sub] == []


def test_event_types_cover_contract():
    expected = {
        "state",
        "comment_accepted",
        "comment_dropped",
        "queue_changed",
        "turn_started",
        "sentence",
        "guard_blocked",
        "turn_finished",
        "session_state",
        "content_replaced",
        "host_connection",
        "latency",
    }
    assert {t.value for t in EventType} == expected
