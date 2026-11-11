"""Deliberate failures for testing a live session (001 FR-020, 004 FR-024; dev only, `POST /api/debug/fault`).

One `FaultInjector` is shared by the comment turns of `ShowDirector` and the scripted show, so a fault queued for a step
hits the next call that reaches that step on either path (an `llm` fault applies to `reply()` or `narrate()`).

008 adds faults per model-chain entry (`inject(..., entry=label)`, FR-016, research R8). They are kept apart from the
step queues: the chain engine pulls them through `take_entry`, its `fault_hook`, right before it would call that entry,
so a step-wide `llm` fault and an entry fault never consume each other.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import TypeVar

from ai_live.core.logging import log_event

logger = logging.getLogger("ai_live.director")

FAULT_STEPS = ("llm", "tts", "render")
FAULT_MODES = ("error", "timeout")
# One mode per failure reason of a chain entry (contracts/adapters.md §5); `timeout` is valid in both forms.
ENTRY_FAULT_MODES = ("rate_limited", "overloaded", "timeout", "empty", "wrong_platform", "interrupted")

T = TypeVar("T")


class InjectedFault(Exception):
    """A failure made on purpose through `FaultInjector.inject`; `kind` becomes the `type` in `errors.jsonl`."""

    kind = "fault_injected"


class FaultInjector:
    """Queue of pending faults per step, and per chain entry label; each call consumes at most one."""

    def __init__(self) -> None:
        self._pending: dict[str, deque[str]] = {step: deque() for step in FAULT_STEPS}
        self._entry: dict[str, deque[str]] = {}

    def inject(self, step: str, mode: str, count: int = 1, entry: str | None = None) -> None:
        """Make the next `count` calls that reach `step` fail there; with `entry`, the next `count` tries of that entry.

        The label is not checked against the chain here (the director does not know it); the API route does that.
        """
        if entry is not None:
            if step != "llm" or mode not in ENTRY_FAULT_MODES or count < 1 or not entry:
                raise ValueError(f"Bad entry fault: step={step!r} mode={mode!r} count={count!r} entry={entry!r}")
            self._entry.setdefault(entry, deque()).extend([mode] * count)
            log_event(logger, "fault_injected", step=step, mode=mode, count=count, entry=entry)
            return
        if step not in FAULT_STEPS or mode not in FAULT_MODES or count < 1:
            raise ValueError(f"Bad fault: step={step!r} mode={mode!r} count={count!r}")
        self._pending[step].extend([mode] * count)
        log_event(logger, "fault_injected", step=step, mode=mode, count=count)

    def take_entry(self, label: str) -> str | None:
        """Consume the next pending fault mode for chain entry `label`, or None; this is the engine's `fault_hook`."""
        pending = self._entry.get(label)
        return pending.popleft() if pending else None

    def pending_entry(self, label: str) -> int:
        pending = self._entry.get(label)
        return len(pending) if pending else 0

    def take(self, step: str) -> str | None:
        """Consume the next pending fault mode for `step`, or None when there is none."""
        pending = self._pending[step]
        return pending.popleft() if pending else None

    def pending(self, step: str) -> int:
        return len(self._pending[step])

    def stream(self, step: str, make: Callable[[], AsyncIterator[T]]) -> AsyncIterator[T]:
        """`make()` unless a fault is pending for `step` (`llm` or `tts`); then a stream that fails or hangs.

        `make` is only called when there is no fault, so a faulted call never reaches the real engine.
        """
        fault = self.take(step)
        return faulty_stream(fault, step) if fault else make()

    async def check_render(self, ack_timeout_s: float) -> None:
        """Apply a pending `render` fault before the renderer is called; returns at once when there is none."""
        fault = self.take("render")
        if fault == "error":
            raise InjectedFault("Lỗi giả lập ở bước render")
        if fault == "timeout":
            # Nothing is sent, so the host never acks: wait out the renderer's ack timeout like a silent host.
            await asyncio.sleep(ack_timeout_s)
            raise TimeoutError("Giả lập host không phản hồi")


async def faulty_stream(mode: str, step: str) -> AsyncIterator:
    """Stand-in for an LLM or TTS stream: fails at once (`error`) or never answers, so the step timeout fires."""
    if mode == "error":
        raise InjectedFault(f"Lỗi giả lập ở bước {step}")
    await asyncio.Event().wait()
    yield  # unreachable; makes this an async generator
