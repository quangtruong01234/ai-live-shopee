"""Comment filter (FR-002, research R9): normalize, then drop empty, link, profanity and duplicate comments.

Rules run in that order and the first hit wins. The author name never drops a comment: an unsafe name is replaced
with "bạn" (data-model.md §1).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from ai_live.brain.prompt import safe_author_name
from ai_live.core.config import Settings
from ai_live.core.models import Comment, DropReason
from ai_live.core.text import contains_link, contains_phrase, match_form, normalize_text, phrase_pattern

PLACEHOLDER_AUTHOR = "bạn"

MIN_LETTERS = 2

_PUNCTUATION = re.compile(r"[^\w\s]")


def load_word_list(path: Path) -> list[str]:
    """One word or phrase per line; `#` lines and blank lines are skipped."""
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            words.append(word)
    return words


@dataclass(frozen=True)
class FilterResult:
    comment: Comment
    drop_reason: DropReason | None = None


def _dedup_text(text: str) -> str:
    # "giá bao nhiêu?" and "Gia bao nhieu" are the same question from the viewer's point of view.
    return normalize_text(_PUNCTUATION.sub(" ", match_form(text)))


class CommentFilter:
    def __init__(
        self,
        banned_words: Iterable[str],
        dedup_window_s: float = 60,
        max_chars: int = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._banned = list(banned_words)
        self._pattern = phrase_pattern(self._banned)
        self._dedup_window_s = dedup_window_s
        self._max_chars = max_chars
        self._clock = clock
        self._seen: dict[tuple[str, str], float] = {}

    @classmethod
    def from_settings(cls, settings: Settings, clock: Callable[[], float] = time.monotonic) -> CommentFilter:
        return cls(
            banned_words=load_word_list(settings.profanity_list_path),
            dedup_window_s=settings.comment_dedup_window_s,
            max_chars=settings.comment_max_chars,
            clock=clock,
        )

    def check(self, comment: Comment) -> FilterResult:
        full = normalize_text(comment.text)
        text = normalize_text(full, self._max_chars)
        truncated = bool(comment.meta.get("truncated")) or len(full) > self._max_chars
        author = safe_author_name(comment.author, self._banned) or PLACEHOLDER_AUTHOR
        cleaned = replace(comment, text=text, author=author, meta={**comment.meta, "truncated": truncated})
        reason = self._drop_reason(comment.author, text)
        return FilterResult(comment=cleaned, drop_reason=reason)

    def _drop_reason(self, raw_author: str, text: str) -> DropReason | None:
        if sum(ch.isalpha() for ch in text) < MIN_LETTERS:
            return DropReason.EMPTY
        if contains_link(text):
            return DropReason.LINK
        if contains_phrase(text, self._pattern):
            return DropReason.PROFANITY
        now = self._clock()
        self._prune(now)
        # Keyed on the raw author so two different unsafe names (both shown as "bạn") are not merged.
        key = (match_form(raw_author), _dedup_text(text))
        if key in self._seen:
            return DropReason.DUPLICATE
        self._seen[key] = now
        return None

    def _prune(self, now: float) -> None:
        cutoff = now - self._dedup_window_s
        self._seen = {k: t for k, t in self._seen.items() if t >= cutoff}
