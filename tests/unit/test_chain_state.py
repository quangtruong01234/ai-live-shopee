"""ChainState: per-entry ready/resting state of the LLM chain (008 data-model §2, §3; contracts/adapters.md §4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_live.brain.chain_state import RESTING_REASONS, AttemptReason, ChainState, EntryState

T0 = datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def state(clock: FakeClock) -> ChainState:
    return ChainState(["sealion", "gptoss", "qwen"], clock)


def test_attempt_reason_has_exactly_nine_values() -> None:
    assert {r.value for r in AttemptReason} == {
        "rate_limited",
        "overloaded",
        "empty",
        "connection",
        "timeout",
        "rejected",
        "wrong_platform",
        "blocked",
        "interrupted",
    }
    assert AttemptReason.RATE_LIMITED == "rate_limited"


def test_resting_reasons_is_every_reason_except_blocked() -> None:
    assert isinstance(RESTING_REASONS, frozenset)
    assert RESTING_REASONS == frozenset(AttemptReason) - {AttemptReason.BLOCKED}
    assert AttemptReason.BLOCKED not in RESTING_REASONS


def test_new_entry_is_ready(state: ChainState) -> None:
    entry = state.status("sealion")
    assert entry == EntryState(label="sealion", status="ready", reason=None, retry_at=None)
    assert state.is_ready("sealion")


def test_rest_returns_retry_at_and_entry_becomes_resting(state: ChainState, clock: FakeClock) -> None:
    retry_at = state.rest("gptoss", 60, AttemptReason.RATE_LIMITED)

    assert retry_at == T0 + timedelta(seconds=60)
    entry = state.status("gptoss")
    assert entry.label == "gptoss"
    assert entry.status == "resting"
    assert entry.reason is AttemptReason.RATE_LIMITED
    assert entry.retry_at == retry_at
    assert not state.is_ready("gptoss")
    # Other entries are untouched.
    assert state.is_ready("sealion")
    assert state.is_ready("qwen")


def test_still_resting_just_before_retry_at(state: ChainState, clock: FakeClock) -> None:
    state.rest("sealion", 60, AttemptReason.TIMEOUT)
    clock.advance(59.9)
    assert state.status("sealion").status == "resting"
    assert not state.is_ready("sealion")


def test_past_retry_at_reads_ready_without_any_call(state: ChainState, clock: FakeClock) -> None:
    state.rest("sealion", 60, AttemptReason.OVERLOADED)
    clock.advance(60)

    entry = state.status("sealion")
    assert entry == EntryState(label="sealion", status="ready", reason=None, retry_at=None)
    assert state.is_ready("sealion")

    clock.advance(1000)
    assert state.is_ready("sealion")


def test_zero_cooldown_is_ready_immediately(state: ChainState) -> None:
    retry_at = state.rest("qwen", 0, AttemptReason.EMPTY)
    assert retry_at == T0
    assert state.is_ready("qwen")


def test_later_rest_overwrites_earlier(state: ChainState, clock: FakeClock) -> None:
    state.rest("sealion", 60, AttemptReason.TIMEOUT)
    clock.advance(0.5)
    retry_at = state.rest("sealion", 60, AttemptReason.CONNECTION)

    entry = state.status("sealion")
    assert entry.reason is AttemptReason.CONNECTION
    assert entry.retry_at == retry_at == T0 + timedelta(seconds=60.5)


@pytest.mark.parametrize("reason", sorted(RESTING_REASONS))
def test_every_resting_reason_can_rest(state: ChainState, reason: AttemptReason) -> None:
    state.rest("qwen", 60, reason)
    assert state.status("qwen").reason is reason


def test_blocked_is_not_a_resting_reason(state: ChainState) -> None:
    with pytest.raises(ValueError):
        state.rest("sealion", 60, AttemptReason.BLOCKED)
    assert state.is_ready("sealion")


def test_snapshot_keeps_entry_order_and_effective_status(state: ChainState, clock: FakeClock) -> None:
    state.rest("qwen", 60, AttemptReason.REJECTED)
    state.rest("sealion", 10, AttemptReason.WRONG_PLATFORM)

    snap = state.snapshot()
    assert [e.label for e in snap] == ["sealion", "gptoss", "qwen"]
    assert [e.status for e in snap] == ["resting", "ready", "resting"]

    clock.advance(10)
    snap = state.snapshot()
    assert [e.label for e in snap] == ["sealion", "gptoss", "qwen"]
    assert [e.status for e in snap] == ["ready", "ready", "resting"]
    assert snap[2].reason is AttemptReason.REJECTED


def test_unknown_label_raises(state: ChainState) -> None:
    with pytest.raises(KeyError):
        state.status("nope")
    with pytest.raises(KeyError):
        state.is_ready("nope")
    with pytest.raises(KeyError):
        state.rest("nope", 60, AttemptReason.TIMEOUT)


def test_duplicate_labels_rejected(clock: FakeClock) -> None:
    with pytest.raises(ValueError):
        ChainState(["a", "a"], clock)
