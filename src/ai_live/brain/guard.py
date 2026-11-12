"""Per-sentence output guard, run before TTS (001 research R8, 004 research R9; FR-010 -> FR-013, ADR-031).

Deterministic and only a few ms, so it is testable without an LLM. It is the second line of defence after the prompt.
The same guard runs on the comment path and the script path, so every check below protects both. Checks run in the
order of 004 contracts/adapters.md §4 and stop at the first failure.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

from ai_live.brain.prompt import REFUSAL_TEMPLATE
from ai_live.core.models import GuardReason, GuardResult
from ai_live.core.text import contains_link, extract_amounts, match_form
from ai_live.products.models import Product, ProductCatalog

# Runs of punctuation, symbols and whitespace become one space: TTS reads "chữa-khỏi, mụn" as the claim "chữa khỏi mụn".
_NON_WORD = re.compile(r"[\W_]+")

# A number right before `%` or "phần trăm" (match form, spaces allowed), same number syntax as `core.text`.
# Only a digit may not precede it: a letter may ("giam30%"), or gluing the number to a word would slip past.
_PERCENT = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+(?![.,]?\d)|\d+(?:[.,]\d+)?)\s*(?:%|phan\s*tram(?!\w))")

LINK_DETAIL_MAX_CHARS = 40


class GuardConfigError(RuntimeError):
    """The guard cannot be built from its rule files; the app must not start without them."""


def word_form(text: str) -> str:
    """Match form with punctuation runs folded to one space. Public so the grader matches by the same rule."""
    return _NON_WORD.sub(" ", match_form(text)).strip()


def claim_forms(text: str) -> set[str]:
    """Word forms of `text` with invisible format characters (soft hyphen, zero-width space) read both ways.

    Such a character can sit inside a word ("mụ\\u00adn") or replace the space between words ("khỏi\\u200bmụn"),
    so it is both dropped and turned into a space; a claim matching either form is blocked.
    """
    dropped = _drop_format_chars(text)
    spaced = "".join(" " if unicodedata.category(ch) == "Cf" else ch for ch in text)
    return {word_form(dropped), word_form(spaced)}


def refusal_sentence(addressee: str) -> str:
    """Fixed refusal sentence (FR-009). It holds no money amount, so it always passes the guard."""
    return REFUSAL_TEMPLATE.format(addressee=addressee)


def load_platform_phrases(path: Path) -> tuple[str, ...]:
    """One phrase per line; blank lines and `#` lines are skipped (like `profanity.txt` of 001).

    A missing file is a configuration error: running without it would let the host name platform mechanics
    the shop never offered (FR-013).
    """
    return _load_phrase_file(path, "cụm từ cơ chế nền tảng", "PLATFORM_PHRASES_PATH")


def load_claim_phrases(path: Path) -> tuple[str, ...]:
    """Same file format as `load_platform_phrases`; a missing file is a configuration error too (FR-010, ADR-050)."""
    return _load_phrase_file(path, "cụm khẳng định không có căn cứ", "CLAIM_PHRASES_PATH")


def load_guard(platform_phrases_path: Path, claim_phrases_path: Path) -> OutputGuard:
    """The guard every running entry point uses: both phrase files loaded (`GuardConfigError` when one is missing)."""
    return OutputGuard(load_platform_phrases(platform_phrases_path), load_claim_phrases(claim_phrases_path))


def _load_phrase_file(path: Path, what: str, env_name: str) -> tuple[str, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise GuardConfigError(f"Không tìm thấy file {what}: {path}. Kiểm tra {env_name} trong .env.") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise GuardConfigError(f"Không đọc được file {what} {path}: {exc}") from exc
    return tuple(p for line in lines if (p := line.strip()) and not p.startswith("#"))


def _padded(form: str) -> str:
    # Spaces on both ends turn a substring test into a whole-word test on a word form.
    return f" {form} "


def _catalog_text(product: Product) -> Iterable[str]:
    """Text a shop wrote about a product. Forbidden claims and the link are excluded: they are not allowed speech."""
    yield from (product.name, product.description, product.intro, *product.promotions)
    yield from (f"{k} {v}" for k, v in product.specs)
    yield from (f"{q} {a}" for q, a in product.faq)
    yield from (v.name for v in product.variants)


def _link_detail(sentence: str) -> str:
    token = next((t for t in sentence.split() if contains_link(t)), sentence)
    return token[:LINK_DETAIL_MAX_CHARS]


class OutputGuard:
    """`platform_phrases` and `claim_phrases` come from `load_platform_phrases` / `load_claim_phrases` in running code.

    Both are optional so 001 call sites and tests keep working: with no phrases that check is skipped and the
    others still run (analyze A4).
    """

    def __init__(self, platform_phrases: Sequence[str] = (), claim_phrases: Sequence[str] = ()) -> None:
        self._phrases = _phrase_forms(platform_phrases)
        self._claims = _phrase_forms(claim_phrases)
        self._catalog_key: ProductCatalog | None = None
        self._catalog_form = ""

    def _catalog_word_form(self, catalog: ProductCatalog) -> str:
        """Padded word form of all catalog text, computed once per catalog object (catalogs are immutable)."""
        if self._catalog_key is not catalog:
            texts = (t for p in catalog.products for t in _catalog_text(p))
            self._catalog_form = _padded(" ".join(word_form(t) for t in texts))
            self._catalog_key = catalog
        return self._catalog_form

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
        # `known_amounts` already holds every integer written in the file, not only prices (research R9).
        for match in _PERCENT.finditer(match_form(_drop_format_chars(sentence))):
            raw = match.group(1)
            if _number(raw) not in catalog.known_amounts:
                return GuardResult.blocked(GuardReason.UNKNOWN_PERCENT, f"{raw}%")
        for text in (sentence, _drop_format_chars(sentence)):
            if contains_link(text):
                return GuardResult.blocked(GuardReason.LINK, _link_detail(text))
        if self._phrases or self._claims:
            catalog_form = self._catalog_word_form(catalog)
            padded = {_padded(form) for form in forms}
            # A phrase the shop wrote itself is allowed: the content file is the ground truth (FR-010, FR-013).
            for phrases, reason in (
                (self._phrases, GuardReason.PLATFORM_PHRASE),
                (self._claims, GuardReason.UNSUPPORTED_CLAIM),
            ):
                for form, phrase in phrases:
                    needle = _padded(form)
                    if any(needle in f for f in padded) and needle not in catalog_form:
                        return GuardResult.blocked(reason, phrase)
        return GuardResult.passed()


def _phrase_forms(phrases: Sequence[str]) -> tuple[tuple[str, str], ...]:
    # Longest first: when phrases overlap, the reported detail is the most specific one.
    pairs = {(form, p) for p in phrases if (form := word_form(p))}
    return tuple(sorted(pairs, key=lambda fp: (-len(fp[0]), fp[0])))


def _drop_format_chars(text: str) -> str:
    # A zero-width space inside "30\u200b%" or "https\u200b://" must not hide the number or the link.
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _number(raw: str) -> float:
    """ "30" -> 30, "1.000" -> 1000, "2,5" -> 2.5 (never in the integer set, so a decimal percent is blocked)."""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    return float(raw.replace(",", "."))
