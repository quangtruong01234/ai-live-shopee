"""Grade scripted sentences for the script self-check (004 US4, FR-025, research R15).

A sentence is graded on its **raw** text, before `clean_spoken()`, so a weak prompt shows up even where the cleaner
would hide it. Invented amounts and percents, forbidden claims, links, platform and claim phrases go through the very
`OutputGuard` of the live path, so "passes the check" means "passes the guard on live". Two kinds only the grader
knows: a wrong pronoun (`bad_pronoun`) and formatting symbols (`formatting`). A segment whose sentence count is out
of its min-max range only gets a warning: the live path accepts it too.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ai_live.brain.guard import OutputGuard
from ai_live.brain.sanitize import clean_spoken
from ai_live.core.models import GuardReason
from ai_live.core.text import normalize_text
from ai_live.products.models import ProductCatalog

BAD_PRONOUN = "bad_pronoun"
FORMATTING = "formatting"

# Report and `totals` order (data-model §10): the guard reasons first, then the grader-only kinds.
VIOLATION_KINDS: tuple[str, ...] = (
    GuardReason.UNKNOWN_AMOUNT.value,
    GuardReason.UNKNOWN_PERCENT.value,
    GuardReason.FORBIDDEN_CLAIM.value,
    GuardReason.LINK.value,
    GuardReason.PLATFORM_PHRASE.value,
    GuardReason.UNSUPPORTED_CLAIM.value,
    BAD_PRONOUN,
    FORMATTING,
)

# The host says "em" and calls viewers "anh chị" (FR-009). "mình" is left out on purpose: Southern speech uses
# "bên mình" for "our shop" (research R15). The user approved this list on 2026-11-03.
BAD_PRONOUNS: tuple[str, ...] = ("tôi", "bạn", "các bạn", "quý khách", "quí khách")

# Matched on lowercase NFC text that keeps diacritics: without them "bạn" would hit "bán" (sell) and "tôi" would
# hit "tối" (evening). Longest first, so "các bạn" is reported rather than its "bạn".
_PRONOUN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(p) for p in sorted(BAD_PRONOUNS, key=len, reverse=True)) + r")(?!\w)"
)

# "bạn" in the third person talks about other customers, not to the viewer ("nhiều bạn hỏi", "các bạn khác",
# "bạn nào da dầu"), so it is fine (research R15). A following "ơi" turns it back into a call to the viewer.
_THIRD_PERSON_BEFORE = re.compile(r"(?<!\w)(?:nhiều|những|mấy|một số|một vài|vài)\s+$")
_THIRD_PERSON_AFTER = re.compile(r"\s+(?:khác|nào|ấy)(?!\w)")
_VOCATIVE_AFTER = re.compile(r"\s*,?\s*ơi(?!\w)")
_THIRD_PERSON_CAPABLE = frozenset({"bạn", "các bạn"})


@dataclass(frozen=True)
class Violation:
    kind: str  # one of VIOLATION_KINDS
    detail: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail}


@dataclass
class GradedSentence:
    """`raw_text` is the LLM text of a generated segment. In a session regrade `text` holds the spoken line,
    which is what was graded there (SC-003 is about what viewers heard)."""

    raw_text: str
    violations: list[Violation] = field(default_factory=list)
    text: str | None = None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"raw_text": self.raw_text, "violations": [v.to_json() for v in self.violations]}
        if self.text is not None:
            data["text"] = self.text
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> GradedSentence:
        return cls(
            raw_text=data["raw_text"],
            violations=[Violation(v["kind"], v.get("detail")) for v in data.get("violations", [])],
            text=data.get("text"),
        )


def _is_third_person(text: str, match: re.Match[str]) -> bool:
    if match.group() not in _THIRD_PERSON_CAPABLE or _VOCATIVE_AFTER.match(text, match.end()):
        return False
    if _THIRD_PERSON_AFTER.match(text, match.end()):
        return True
    return match.group() == "bạn" and _THIRD_PERSON_BEFORE.search(text, 0, match.start()) is not None


def _bad_pronouns(text: str) -> list[str]:
    lowered = unicodedata.normalize("NFC", text).lower()
    found = [m.group() for m in _PRONOUN.finditer(lowered) if not _is_third_person(lowered, m)]
    return list(dict.fromkeys(found))


def grade_sentence(text: str, catalog: ProductCatalog, guard: OutputGuard) -> list[Violation]:
    """Every violation kind found in one sentence, in `VIOLATION_KINDS` order.

    The guard stops at its first failure, so a sentence carries at most one guard kind; that is enough to fail it,
    exactly as on live. `bad_pronoun` counts once per sentence, its detail lists every pronoun found.
    """
    violations: list[Violation] = []
    result = guard.check(text, catalog)
    if not result.ok and result.reason is not None:
        violations.append(Violation(result.reason.value, result.detail))
    pronouns = _bad_pronouns(text)
    if pronouns:
        violations.append(Violation(BAD_PRONOUN, ", ".join(pronouns)))
    cleaned = clean_spoken(text)
    if cleaned != normalize_text(text):
        violations.append(Violation(FORMATTING, cleaned))
    return violations


def grade_sentences(texts: Iterable[str], catalog: ProductCatalog, guard: OutputGuard) -> list[GradedSentence]:
    return [GradedSentence(raw_text=t, violations=grade_sentence(t, catalog, guard)) for t in texts]


def sentence_count_warning(count: int, min_sentences: int, max_sentences: int) -> bool:
    """A segment shorter or longer than asked is a warning, not a violation (research R15)."""
    return not min_sentences <= count <= max_sentences


def count_by_kind(sentences: Iterable[GradedSentence]) -> dict[str, int]:
    totals = dict.fromkeys(VIOLATION_KINDS, 0)
    for sentence in sentences:
        for violation in sentence.violations:
            totals[violation.kind] = totals.get(violation.kind, 0) + 1
    return totals
