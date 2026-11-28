"""Greetings: spot "hello / hi / chào shop" comments and answer them from templates (001 FR-026, ADR-077).

A greeting needs no product knowledge, so sending it to the LLM only costs a call and a few seconds; a template reply is
instant and cannot invent anything. Intake tags a greeting (`meta.kind = "greeting"`) and drops a repeat greeting from a
viewer already greeted within `repeat_s`, so a room saying hi does not turn the live into a roll call. The director
then speaks `GreetingReplier`'s sentences instead of calling the engine; they still go through the output guard.

Keywords match the lowercase text with its diacritics, not the match form used by the other rules: on the match form
"cháo" (porridge) would read as "chao" and "hì" (a laugh) as "hi".
"""

from __future__ import annotations

import itertools
import json
import re
import time
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ai_live.brain.prompt import addressee
from ai_live.core.config import Settings
from ai_live.core.models import Comment, Priority
from ai_live.core.text import normalize_text
from ai_live.products.models import ProductCatalog

GREETING_KIND = "greeting"
_PRUNE_EVERY = 256


def is_greeting_comment(comment: Comment) -> bool:
    return comment.meta.get("kind") == GREETING_KIND


@dataclass(frozen=True)
class GreetingCheck:
    """`comment` is tagged when it is a greeting; `repeat` means the viewer was greeted recently (drop as `greeted`)."""

    comment: Comment
    is_greeting: bool = False
    repeat: bool = False


class GreetingRules:
    def __init__(
        self,
        keywords: Iterable[str],
        max_words: int = 8,
        repeat_s: float = 600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        forms = sorted({k for w in keywords if (k := normalize_text(w).lower())}, key=len, reverse=True)
        self._pattern = re.compile(rf"(?<!\w)(?:{'|'.join(re.escape(f) for f in forms)})(?!\w)") if forms else None
        self._max_words = max_words
        self._repeat_s = repeat_s
        self._clock = clock
        self._greeted: dict[str, float] = {}
        self._checks = 0

    @classmethod
    def from_file(cls, path: Path, repeat_s: float = 600) -> GreetingRules:
        rules = json.loads(path.read_text(encoding="utf-8"))
        return cls(rules.get("keywords", []), int(rules.get("max_words", 8)), repeat_s)

    @classmethod
    def from_settings(cls, settings: Settings) -> GreetingRules:
        return cls.from_file(settings.greeting_rules_path, settings.comment_greeting_repeat_s)

    def is_greeting(self, text: str, priority: Priority) -> bool:
        """A short small-talk comment with a greeting word; "chào shop, giá bao nhiêu" is a question for the LLM."""
        if self._pattern is None or priority is not Priority.LOW:
            return False
        lowered = normalize_text(text).lower()
        return len(lowered.split()) <= self._max_words and self._pattern.search(lowered) is not None

    def check(self, comment: Comment, priority: Priority) -> GreetingCheck:
        if not self.is_greeting(comment.text, priority):
            return GreetingCheck(comment)
        now = self._clock()
        self._checks += 1
        if self._checks % _PRUNE_EVERY == 0:
            self._greeted = {k: t for k, t in self._greeted.items() if now - t < self._repeat_s}
        key = comment.author_key
        last = self._greeted.get(key)
        if last is not None and now - last < self._repeat_s:
            return GreetingCheck(comment, is_greeting=True, repeat=True)
        # Counted when accepted, not when spoken: a greeting that later goes stale is not worth a second chance.
        self._greeted[key] = now
        tagged = replace(comment, meta={**comment.meta, "kind": GREETING_KIND})
        return GreetingCheck(tagged, is_greeting=True)


class GreetingReplier:
    """Template replies, taken in turn so back-to-back greetings do not sound identical."""

    def __init__(self, replies: Sequence[str], follow_ups: Sequence[str] = ()) -> None:
        if not replies:
            raise ValueError("greeting rules need at least one reply")
        self._replies = itertools.cycle(list(replies))
        self._follow_ups = itertools.cycle(list(follow_ups)) if follow_ups else None

    @classmethod
    def from_file(cls, path: Path) -> GreetingReplier:
        rules = json.loads(path.read_text(encoding="utf-8"))
        return cls(rules.get("replies", []), rules.get("follow_ups", []))

    @classmethod
    def from_settings(cls, settings: Settings) -> GreetingReplier:
        return cls.from_file(settings.greeting_rules_path)

    def sentences(self, comment: Comment, catalog: ProductCatalog) -> list[str]:
        who = addressee(comment.author)
        out = [_fill(next(self._replies), who, None)]
        product = next((p.name for p in catalog.products if p.is_primary), None)
        if self._follow_ups is not None and product:
            out.append(_fill(next(self._follow_ups), who, product))
        return out

    async def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]:
        """Same shape as `ReplyEngine.reply`, so the director's sentence loop handles both."""
        for sentence in self.sentences(comment, catalog):
            yield sentence


def _fill(template: str, who: str, product: str | None) -> str:
    text = template.replace("{who}", who).replace("{product}", product or "")
    return text[:1].upper() + text[1:]
