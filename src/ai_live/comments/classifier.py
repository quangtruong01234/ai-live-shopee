"""Rule-based priority classifier (FR-003, research R9; table in docs/ARCHITECTURE.md §5).

Keywords are whole-word phrases on the match form, so viewers who type without diacritics hit the same rules.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from ai_live.core.config import Settings
from ai_live.core.models import Priority
from ai_live.core.text import contains_phrase, phrase_pattern


class PriorityClassifier:
    def __init__(self, high: Iterable[str], medium: Iterable[str], question_words: Iterable[str]) -> None:
        self._high = phrase_pattern(high)
        self._medium = phrase_pattern(medium)
        self._question = phrase_pattern(question_words)

    @classmethod
    def from_file(cls, path: Path) -> PriorityClassifier:
        rules = json.loads(path.read_text(encoding="utf-8"))
        return cls(rules.get("high", []), rules.get("medium", []), rules.get("question_words", []))

    @classmethod
    def from_settings(cls, settings: Settings) -> PriorityClassifier:
        return cls.from_file(settings.priority_rules_path)

    def classify(self, text: str) -> Priority:
        if contains_phrase(text, self._high):
            return Priority.HIGH
        if contains_phrase(text, self._medium):
            return Priority.MEDIUM
        # An unlisted question still deserves an answer before small talk.
        if "?" in text or contains_phrase(text, self._question):
            return Priority.MEDIUM
        return Priority.LOW
