"""`SpeechTTS`: the wrapper `create_tts()` always returns (003 contracts/adapters.md §2, data-model §4).

It normalizes text before any source sees it, counts what was sent (the free quota is counted in characters) and,
after a quota error, rejects sentences at once for a cooldown instead of hammering an exhausted source.
"""

from __future__ import annotations

import contextlib
import logging
import math
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass
from typing import Any

from ai_live.core.logging import log_event
from ai_live.core.protocols import TTSEngine, TTSEngineError

logger = logging.getLogger("ai_live.tts")

QUOTA_EXHAUSTED = "quota_exhausted"


@dataclass
class TTSUsage:
    """Written to `tts_usage.json` at shutdown (FR-015)."""

    provider: str
    requests: int = 0
    chars: int = 0
    quota_errors: int = 0
    rejected_in_cooldown: int = 0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class SpeechTTS:
    """Satisfies `TTSEngine`; wraps the concrete source chosen by `TTS_PROVIDER`."""

    def __init__(
        self,
        engine: TTSEngine,
        *,
        provider: str,
        normalize: Callable[[str], str],
        quota_cooldown_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.engine = engine
        self.usage = TTSUsage(provider=provider)
        self._normalize = normalize
        self._cooldown_s = quota_cooldown_s
        self._clock = clock
        self._cooldown_until: float | None = None
        self._quota_head = f"Hết hạn mức giọng nói ({provider})."

    @property
    def sample_rate(self) -> int:
        return self.engine.sample_rate

    async def warm_up(self) -> None:
        await self.engine.warm_up()

    def normalize(self, text: str) -> str:
        """The exact text the source is sent for `text` (shown by the `say` CLI)."""
        return self._normalize(text)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self._reject_if_cooling_down()
        spoken = self._normalize(text)
        if not spoken:
            # A sentence of only emoji or links has nothing to say; the director already handles an empty stream.
            return
        self.usage.requests += 1
        self.usage.chars += len(spoken)
        # Spoken text may carry a viewer's name, so it never goes above DEBUG (contracts/events.md §1).
        log_event(logger, "tts_request", logging.DEBUG, chars=len(spoken), text=spoken)
        stream = self.engine.synthesize(spoken)
        try:
            # `aclosing` so skipping a sentence stops the source at once instead of whenever the GC finalizes it.
            async with contextlib.aclosing(stream):
                async for chunk in stream:
                    yield chunk
        except TTSEngineError as exc:
            if exc.kind != QUOTA_EXHAUSTED:
                raise
            self._start_cooldown(exc.message)
            # The operator needs to know when voice comes back (contracts/events.md §2).
            raise TTSEngineError(QUOTA_EXHAUSTED, self._quota_text(self._cooldown_s)) from exc

    def _reject_if_cooling_down(self) -> None:
        if self._cooldown_until is None:
            return
        remaining = self._cooldown_until - self._clock()
        if remaining <= 0:
            # Cooldown over: the next real call decides whether the quota is back.
            self._cooldown_until = None
            return
        self.usage.rejected_in_cooldown += 1
        raise TTSEngineError(QUOTA_EXHAUSTED, self._quota_text(remaining))

    def _quota_text(self, seconds: float) -> str:
        return f"{self._quota_head} Thử lại sau {math.ceil(seconds)} giây."

    def _start_cooldown(self, message: str) -> None:
        # Keep the source's own wording (e.g. which free tier ran out) for the rejections that follow.
        head = message.strip() or f"Hết hạn mức giọng nói ({self.usage.provider})"
        self._quota_head = head if head.endswith(".") else f"{head}."
        self.usage.quota_errors += 1
        self._cooldown_until = self._clock() + self._cooldown_s
        log_event(
            logger, "tts_quota_exhausted", logging.WARNING, provider=self.usage.provider, cooldown_s=self._cooldown_s
        )
