"""Fan-out of "sentence heard" notices to `PlaybackListener`s (009 contracts/adapters.md §1).

Shared by the renderers so each one only says *when* a sentence is heard; a broken listener (the scene) must never
break a turn, so every call is guarded here once.
"""

from __future__ import annotations

import logging

from ai_live.core.protocols import PlaybackListener

logger = logging.getLogger("ai_live.avatar")


class PlaybackNotifier:
    def __init__(self) -> None:
        self._listeners: list[PlaybackListener] = []

    def add(self, listener: PlaybackListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def started(self, utterance_id: str, seq: int, text: str) -> None:
        for listener in list(self._listeners):
            try:
                listener.playback_started(utterance_id, seq, text)
            except Exception:
                logger.exception("playback listener failed")

    def ended(self, utterance_id: str, seq: int) -> None:
        for listener in list(self._listeners):
            try:
                listener.playback_ended(utterance_id, seq)
            except Exception:
                logger.exception("playback listener failed")

    def stopped(self) -> None:
        for listener in list(self._listeners):
            try:
                listener.playback_stopped()
            except Exception:
                logger.exception("playback listener failed")
