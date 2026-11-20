"""012 US4: the "AI vừa nói" ring buffer (data-model §7, FR-020, FR-021)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ai_live.app.spoken import SpokenLog
from ai_live.core.events import Event, EventBus, EventType


def _catalog(names: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(products=[SimpleNamespace(id=pid, name=name) for pid, name in names.items()])


def _sentence(n: int, *, product_id: str | None = "kem", segment_id: str | None = "seg-1", topic: str | None = "intro"):
    payload = {"utterance_id": f"u{n}", "seq": 0, "text": f"Câu số {n}.", "product_id": product_id, "topic": topic}
    if segment_id is not None:
        payload["segment_id"] = segment_id
    return Event(EventType.SENTENCE, payload)


def _show(state: str) -> Event:
    return Event(EventType.SHOW_STATE, {"show_id": "s1", "state": state, "mode": "script"})


def _log(names: dict[str, str] | None = None) -> tuple[SpokenLog, dict]:
    holder = {"catalog": _catalog(names or {"kem": "Kem chống nắng X"})}
    return SpokenLog(EventBus(), lambda: holder["catalog"], clock=lambda: "2026-11-20T10:00:00.000Z"), holder


def test_only_scripted_sentences_are_kept_with_every_field():
    log, _ = _log()
    log.on_event(_sentence(1))
    log.on_event(_sentence(2, segment_id=None))  # a comment reply, not the script
    blocked = {"utterance_id": "u3", "text": "Chữa khỏi mụn.", "segment_id": "seg-1"}
    log.on_event(Event(EventType.GUARD_BLOCKED, blocked))
    assert log.entries() == [
        {
            "ts": "2026-11-20T10:00:00.000Z",
            "utterance_id": "u1",
            "segment_id": "seg-1",
            "text": "Câu số 1.",
            "product_id": "kem",
            "product_name": "Kem chống nắng X",
            "topic": "intro",
        }
    ]


def test_product_name_is_looked_up_when_the_sentence_arrives():
    log, holder = _log()
    log.on_event(_sentence(1))
    holder["catalog"] = _catalog({"kem": "Kem chống nắng X mới"})
    log.on_event(_sentence(2))
    names = [e["product_name"] for e in log.entries()]
    assert names == ["Kem chống nắng X mới", "Kem chống nắng X"]


def test_unknown_product_and_old_events_without_topic_give_null():
    log, _ = _log()
    log.on_event(_sentence(1, product_id="khong-co", topic=None))
    log.on_event(_sentence(2, product_id=None))
    first, second = log.entries()[1], log.entries()[0]
    assert first["product_name"] is None and first["topic"] is None
    assert second["product_id"] is None and second["product_name"] is None


def test_newest_first_and_at_most_100():
    log, _ = _log()
    for n in range(130):
        log.on_event(_sentence(n))
    entries = log.entries()
    assert len(entries) == 100
    assert [e["utterance_id"] for e in entries[:3]] == ["u129", "u128", "u127"]
    assert entries[-1]["utterance_id"] == "u30"
    # FR-020: the 50 newest are always there.
    assert {f"u{n}" for n in range(80, 130)} <= {e["utterance_id"] for e in entries}


def test_a_repeated_utterance_id_is_one_row():
    log, _ = _log()
    log.on_event(_sentence(1))
    log.on_event(_sentence(1))
    assert [e["utterance_id"] for e in log.entries()] == ["u1"]


def test_a_new_show_clears_the_list_but_an_ended_show_keeps_it():
    log, _ = _log()
    log.on_event(_show("running"))
    log.on_event(_sentence(1))
    log.on_event(_show("paused"))
    log.on_event(_show("running"))  # resume: same show
    assert len(log.entries()) == 1
    log.on_event(_show("closing"))
    log.on_event(_show("ended"))
    assert len(log.entries()) == 1  # still readable after the show
    log.on_event(_show("running"))  # the next show
    assert log.entries() == []


def test_the_first_running_state_clears_what_came_before():
    log, _ = _log()
    log.on_event(_sentence(1))
    log.on_event(_show("idle"))
    log.on_event(_sentence(2))
    log.on_event(_show("running"))
    assert log.entries() == []


@pytest.mark.anyio
async def test_start_reads_the_bus_and_stop_unsubscribes():
    bus = EventBus()
    log = SpokenLog(bus, lambda: _catalog({"kem": "Kem"}))
    before = bus.subscriber_count
    log.start()
    assert bus.subscriber_count == before + 1
    bus.publish(_sentence(1))
    for _ in range(20):
        if log.entries():
            break
        await asyncio.sleep(0.01)
    assert [e["utterance_id"] for e in log.entries()] == ["u1"]
    await log.stop()
    assert bus.subscriber_count == before
