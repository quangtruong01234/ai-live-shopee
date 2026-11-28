"""T012: EventBus (contracts/adapters.md, contracts/events.md §3)."""

import time
from datetime import UTC, datetime

import anyio
import pytest

from ai_live.core.events import Event, EventBus, EventType, show_error_event

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
        # the fast subscriber reads right away, so it is never full
        fast_seen += [e.payload["i"] for e in fast.drain()]
    assert fast_seen == list(range(1005))
    slow_events = await take(slow, 1000)
    assert [e.payload["i"] for e in slow_events] == list(range(5, 1005))
    assert slow.dropped == 5
    assert fast.dropped == 0


async def test_publish_does_not_wait_for_slow_subscriber():
    bus = EventBus(max_queue=10)
    bus.subscribe()  # nobody reads
    # publish is synchronous, so fail_after has no await point to cut in: measure the time directly.
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
        "viewers_changed",  # 001 FR-029 (ADR-078)
        "turn_started",
        "sentence",
        "guard_blocked",
        "turn_finished",
        "session_state",
        "content_replaced",
        "host_connection",
        "latency",
        # feature 004 (specs/004-show-director/contracts/events.md §3)
        "show_state",
        "segment_started",
        "segment_finished",
        "segment_next",
        "show_stats",
        "show_error",
        # feature 008 (specs/008-llm-provider-chain/contracts/events.md §2)
        "llm_chain",
        # feature 005 (specs/005-lipsync-livetalking/contracts/events.md §1)
        "avatar_mode",
        "lipsync_health",
        # feature 009 (specs/009-live-scene-layout/contracts/api.md §6)
        "scene",
        # feature 007 (specs/007-demo-readiness/contracts/api.md)
        "host_status",
        "alert",
    }
    assert {t.value for t in EventType} == expected


def test_show_error_event_redacts_message():
    secret = "AIza" + "Q" * 35
    event = show_error_event(step="llm", kind="api_error", message=f"401 bad key {secret} GEMINI_API_KEY=abc123")
    assert event.type is EventType.SHOW_ERROR
    body = event.to_json()
    assert body["type"] == "show_error"
    assert secret not in body["message"]
    assert "abc123" not in body["message"]
    assert "***" in body["message"]
    assert body["step"] == "llm"
    assert body["kind"] == "api_error"
    assert body["segment_id"] is None


def test_show_error_event_keeps_segment_id():
    event = show_error_event(step="tts", kind="timeout", message="TTS quá 5 s", segment_id="s1")
    assert event.payload == {"segment_id": "s1", "step": "tts", "kind": "timeout", "message": "TTS quá 5 s"}


# ---------- Feature 005 (specs/005-lipsync-livetalking/contracts/events.md §1, data-model §4, §6) ----------

CHANGED_AT = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


def test_avatar_mode_event_payload():
    from ai_live.core.events import avatar_mode_event
    from ai_live.core.models import AvatarModeState

    state = AvatarModeState(
        configured="livetalking",
        active="static",
        reason="render_errors",
        consecutive_errors=2,
        last_utterance_id="u9",
        changed_at=CHANGED_AT,
    )
    event = avatar_mode_event(state)
    assert event.type is EventType.AVATAR_MODE
    # last_utterance_id is internal bookkeeping, not part of the event (events.md §1).
    assert event.to_json() == {
        "type": "avatar_mode",
        "configured": "livetalking",
        "active": "static",
        "reason": "render_errors",
        "consecutive_errors": 2,
        "changed_at": CHANGED_AT.isoformat(),
    }


def test_avatar_mode_event_initial_state():
    from ai_live.core.events import avatar_mode_event
    from ai_live.core.models import AvatarModeState

    body = avatar_mode_event(AvatarModeState(configured="static", active="static")).to_json()
    assert body == {
        "type": "avatar_mode",
        "configured": "static",
        "active": "static",
        "reason": None,
        "consecutive_errors": 0,
        "changed_at": None,
    }


def test_lipsync_health_event_payload():
    from ai_live.core.events import lipsync_health_event
    from ai_live.core.models import LipsyncHealth

    health = LipsyncHealth(
        connected=True,
        boot_id="b1",
        fork_commit="abc123",
        session_id=7,
        vram_used_mb=2100,
        infer_fps=31.5,
        last_error=None,
        updated_at=CHANGED_AT,
    )
    event = lipsync_health_event(health)
    assert event.type is EventType.LIPSYNC_HEALTH
    assert event.to_json() == {
        "type": "lipsync_health",
        "connected": True,
        "boot_id": "b1",
        "fork_commit": "abc123",
        "session_id": 7,
        "vram_used_mb": 2100,
        "infer_fps": 31.5,
        "last_error": None,
        "updated_at": CHANGED_AT.isoformat(),
        "lipsync": None,
        "model_mismatch": False,
    }


def test_lipsync_health_event_carries_lipsync_block():
    """011 data-model §4: the fork's `lipsync` block and the app's mismatch flag reach the control page."""
    from ai_live.core.events import lipsync_health_event
    from ai_live.core.models import LipsyncHealth

    block = {
        "model": "ultralight",
        "teacher": "musetalk",
        "character_id": "demo_host_02",
        "avatar_id": "demo_host_02__ultralight_musetalk",
        "checkpoint_sha256": "a" * 64,
    }
    health = LipsyncHealth(connected=True, lipsync=block, model_mismatch=True, updated_at=CHANGED_AT)
    body = lipsync_health_event(health).to_json()
    assert body["lipsync"] == block
    assert body["model_mismatch"] is True


def test_lipsync_health_event_redacts_error():
    from ai_live.core.events import lipsync_health_event
    from ai_live.core.models import LipsyncHealth

    secret = "AIza" + "Q" * 35
    health = LipsyncHealth(
        connected=False, last_error=f"inference_failed: {secret} api_key=abc123", updated_at=CHANGED_AT
    )
    body = lipsync_health_event(health).to_json()
    assert secret not in body["last_error"]
    assert "abc123" not in body["last_error"]
    assert body["last_error"].startswith("inference_failed")
    assert body["boot_id"] is None
