"""Per-viewer rate limit (001 FR-027, ADR-077).

One account that posts fast would otherwise own the host: every comment gets a turn, and the filter's duplicate check
misses messages that differ by a word. The limiter runs first in intake, before the filter, so every comment counts,
duplicates and links included. More than `max_comments` in `window_s` mutes the viewer for `mute_s`; while muted every
comment from them is dropped as `spam`. Muting does not extend itself, so a viewer who keeps typing gets back in once
the mute ends instead of being locked out for the whole live.

The operator can also block a viewer by hand from the control page (001 FR-029, ADR-078): for some minutes or for the
whole session. A manual block is kept apart from the automatic mute, is checked first (`blocked`), and does not count
toward the rate limit. Everything lives in memory only; restarting the app clears it.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from ai_live.core.logging import log_event
from ai_live.core.models import Comment

logger = logging.getLogger("ai_live.comments")

# Forget idle viewers every so many checks, so a long live with many one-time viewers keeps the maps small.
_PRUNE_EVERY = 256


@dataclass(frozen=True)
class ViewerBlock:
    """One blocked or muted viewer as the control page lists it (001 data-model `ViewerBlock`)."""

    author_key: str
    author: str
    kind: Literal["manual", "auto"]
    remaining_s: float | None  # None: blocked for the whole session

    def to_json(self) -> dict[str, Any]:
        remaining = None if self.remaining_s is None else round(self.remaining_s, 1)
        return {"author_key": self.author_key, "author": self.author, "kind": self.kind, "remaining_s": remaining}


class AuthorLimiter:
    def __init__(
        self,
        max_comments: int = 3,
        window_s: float = 30,
        mute_s: float = 120,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_comments
        self._window_s = window_s
        self._mute_s = mute_s
        self._clock = clock
        self._recent: dict[str, deque[float]] = {}
        self._muted_until: dict[str, float] = {}
        # Manual blocks: author key -> end time, or None for the whole session.
        self._blocked_until: dict[str, float | None] = {}
        # Last display name per listed viewer, only for the control page.
        self._names: dict[str, str] = {}
        self._checks = 0
        # Bumped whenever the listed viewers change, so intake can tell the control page without diffing lists.
        self.version = 0

    def blocked(self, comment: Comment) -> bool:
        """True when the operator blocked this viewer; the caller drops the comment as `blocked` (FR-029)."""
        key = comment.author_key
        if key not in self._blocked_until:
            return False
        until = self._blocked_until[key]
        if until is not None and self._clock() >= until:
            del self._blocked_until[key]
            self._forget_name(key)
            return False
        self._names[key] = comment.author
        return True

    def block(self, key: str, minutes: float | None, author: str | None = None) -> None:
        """Block `key` for `minutes`, or for the whole session when None. Blocking again replaces the old end."""
        self._blocked_until[key] = None if minutes is None else self._clock() + minutes * 60
        self._names[key] = author or self._names.get(key) or key
        self.version += 1
        log_event(logger, "viewer_blocked", author_key=key, minutes=minutes)

    def unblock(self, key: str) -> bool:
        """Lift a manual block and an automatic mute; the rate count starts afresh. False when nothing was lifted."""
        lifted = key in self._blocked_until or key in self._muted_until
        self._blocked_until.pop(key, None)
        self._muted_until.pop(key, None)
        self._recent.pop(key, None)
        self._forget_name(key)
        if lifted:
            self.version += 1
            log_event(logger, "viewer_unblocked", author_key=key)
        return lifted

    def allow(self, comment: Comment) -> bool:
        """False when the viewer is over the limit or still muted; the caller drops the comment as `spam`."""
        now = self._clock()
        key = comment.author_key
        self._checks += 1
        if self._checks % _PRUNE_EVERY == 0:
            self._prune(now)
        until = self._muted_until.get(key)
        if until is not None:
            if now < until:
                return False
            # The mute is over: start counting afresh, or the burst that caused it would mute them again at once.
            del self._muted_until[key]
            self._recent.pop(key, None)
            self._forget_name(key)
        times = self._recent.setdefault(key, deque())
        while times and now - times[0] > self._window_s:
            times.popleft()
        times.append(now)
        if len(times) <= self._max:
            return True
        self._recent.pop(key, None)
        if self._mute_s > 0:
            self._muted_until[key] = now + self._mute_s
            self._names[key] = comment.author
            self.version += 1
        log_event(logger, "author_muted", comment_id=comment.id, count=len(times), mute_s=self._mute_s)
        return False

    def muted(self) -> list[str]:
        """Author keys muted by the rate limit right now."""
        now = self._clock()
        return [key for key, until in self._muted_until.items() if now < until]

    def viewers(self) -> list[ViewerBlock]:
        """Blocked and muted viewers, manual first; a viewer both blocked and muted is listed once, as manual."""
        now = self._clock()
        out: list[ViewerBlock] = []
        for key, until in self._blocked_until.items():
            if until is None or now < until:
                remaining = None if until is None else until - now
                out.append(ViewerBlock(key, self._names.get(key, key), "manual", remaining))
        manual = {v.author_key for v in out}
        for key, until in self._muted_until.items():
            if now < until and key not in manual:
                out.append(ViewerBlock(key, self._names.get(key, key), "auto", until - now))
        return out

    def _forget_name(self, key: str) -> None:
        if key not in self._blocked_until and key not in self._muted_until:
            self._names.pop(key, None)

    def _prune(self, now: float) -> None:
        self._muted_until = {k: u for k, u in self._muted_until.items() if now < u}
        self._blocked_until = {k: u for k, u in self._blocked_until.items() if u is None or now < u}
        self._names = {k: n for k, n in self._names.items() if k in self._muted_until or k in self._blocked_until}
        self._recent = {k: t for k, t in self._recent.items() if t and now - t[-1] <= self._window_s}
