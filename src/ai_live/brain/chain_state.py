"""Per-entry ready/resting state of the LLM provider chain (feature 008, data-model §2, §3).

Pure: no I/O, no asyncio. One instance is shared by the scripted and comment paths for the whole app run (research R5).
Operations never await, so the single-threaded event loop needs no lock.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

__all__ = ["RESTING_REASONS", "AttemptReason", "ChainState", "EntryState"]


class AttemptReason(StrEnum):
    """Why one attempt on one chain entry failed (mapping from HTTP/stream in research R3).

    Cancellation is deliberately not a reason: a cancelled attempt is not recorded as a failure.
    """

    RATE_LIMITED = "rate_limited"
    OVERLOADED = "overloaded"
    EMPTY = "empty"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    WRONG_PLATFORM = "wrong_platform"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"


# A content-filter block says nothing about the entry's health, so it switches entries without resting.
RESTING_REASONS: frozenset[AttemptReason] = frozenset(AttemptReason) - {AttemptReason.BLOCKED}


@dataclass(frozen=True, slots=True)
class EntryState:
    """Effective state of one entry as read at a given instant."""

    label: str
    status: Literal["ready", "resting"]
    reason: AttemptReason | None = None
    retry_at: datetime | None = None


class ChainState:
    """Tracks which chain entries are resting and until when.

    A resting entry becomes ready again purely by the clock passing `retry_at`; there is no background wake-up task.
    """

    def __init__(self, labels: Sequence[str], clock: Callable[[], datetime]) -> None:
        if len(set(labels)) != len(labels):
            raise ValueError(f"duplicate chain labels: {list(labels)}")
        self._clock = clock
        # Insertion order is chain order; snapshot() relies on it.
        self._rest: dict[str, tuple[AttemptReason, datetime] | None] = dict.fromkeys(labels)

    def status(self, label: str) -> EntryState:
        """Return the entry's effective state; a rest whose `retry_at` has passed reads as ready."""
        resting = self._rest[label]
        if resting is not None:
            reason, retry_at = resting
            if self._clock() < retry_at:
                return EntryState(label=label, status="resting", reason=reason, retry_at=retry_at)
        return EntryState(label=label, status="ready")

    def is_ready(self, label: str) -> bool:
        return self.status(label).status == "ready"

    def rest(self, label: str, seconds: float, reason: AttemptReason) -> datetime:
        """Put the entry to rest for `seconds` from now and return `retry_at`.

        A later rest overwrites an earlier one (research R5: two concurrent turns failing on the same entry).
        """
        if label not in self._rest:
            raise KeyError(label)
        if reason not in RESTING_REASONS:
            raise ValueError(f"reason {reason!r} does not rest an entry")
        retry_at = self._clock() + timedelta(seconds=seconds)
        self._rest[label] = (reason, retry_at)
        return retry_at

    def snapshot(self) -> list[EntryState]:
        """Effective state of every entry, in chain order."""
        return [self.status(label) for label in self._rest]
