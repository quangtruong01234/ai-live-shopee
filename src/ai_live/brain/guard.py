"""Per-sentence output guard, run before TTS (research R8; FR-010, FR-011).

Deterministic and only a few ms, so it is testable without an LLM. It is the second line of defence after the prompt.
"""

from __future__ import annotations

import re
import unicodedata

from ai_live.brain.prompt import REFUSAL_TEMPLATE
from ai_live.core.models import GuardReason, GuardResult
from ai_live.core.text import extract_amounts, match_form
from ai_live.products.models import ProductCatalog

# Runs of punctuation, symbols and whitespace become one space: TTS reads "chữa-khỏi, mụn" as the claim "chữa khỏi mụn".
_NON_WORD = re.compile(r"[\W_]+")


def word_form(text: str) -> str:
    """Match form with punctuation runs folded to one space. Public so the grader matches by the same rule."""
    return _NON_WORD.sub(" ", match_form(text)).strip()


def claim_forms(text: str) -> set[str]:
    """Word forms of `text` with invisible format characters (soft hyphen, zero-width space) read both ways.

    Such a character can sit inside a word ("mụ\\u00adn") or replace the space between words ("khỏi\\u200bmụn"),
    so it is both dropped and turned into a space; a claim matching either form is blocked.
    """
    dropped = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    spaced = "".join(" " if unicodedata.category(ch) == "Cf" else ch for ch in text)
    return {word_form(dropped), word_form(spaced)}


def refusal_sentence(addressee: str) -> str:
    """Fixed refusal sentence (FR-009). It holds no money amount, so it always passes the guard."""
    return REFUSAL_TEMPLATE.format(addressee=addressee)


class OutputGuard:
    def check(self, sentence: str, catalog: ProductCatalog) -> GuardResult:
        forms = claim_forms(sentence)
        # Forbidden claims apply catalog-wide: a sentence about a secondary product that carries the main product's
        # forbidden claim is still a false statement.
        for product in catalog.products:
            for claim in product.forbidden_claims:
                claim_form = word_form(claim)
                if claim_form and any(claim_form in form for form in forms):
                    return GuardResult.blocked(GuardReason.FORBIDDEN_CLAIM, claim)
        for amount in extract_amounts(sentence):
            if amount not in catalog.known_amounts:
                return GuardResult.blocked(GuardReason.UNKNOWN_AMOUNT, str(amount))
        return GuardResult.passed()
