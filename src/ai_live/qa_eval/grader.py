"""Grading of the sample question set (research R13; FR-023; contracts/content-template.md §2).

An answer is correct when it holds every required idea and no forbidden idea, and says no money amount outside the
catalog (an automatic forbidden idea). Each idea is a list of equivalent phrasings; matching is deterministic so a
score change always comes from a reply change, never from the grader.

Matching rules, kept consistent with `OutputGuard`:
- Text is compared on the guard's word form (NFC, lowercase, no diacritics, punctuation runs folded to one space),
  as whole words, so "hỏi shop" does not match "hỏi shopee".
- A phrasing that contains a money amount ("420.000", "420k", "giảm 30.000đ") matches by integer amount through
  `core.text.extract_amounts`, so "420.000" matches "420 nghìn" but not "1.420.000đ".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_live.brain.guard import claim_forms
from ai_live.brain.prompt import format_price
from ai_live.core.text import extract_amounts
from ai_live.products.models import ProductCatalog

# Money unit words left in a phrasing once its amount is taken out ("259 nghìn đồng" -> nothing else to match).
# "dong" is listed although `extract_amounts` does not treat it as a unit, so "259 nghìn đồng" still matches "259k".
_UNIT_WORDS = frozenset({"trieu", "tr", "nghin", "ngan", "k", "vnd", "d", "dong"})

UNKNOWN_AMOUNT_IDEA = "số tiền không có trong dữ liệu"

Idea = tuple[str, ...]


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    author: str
    question: str
    required: tuple[Idea, ...] = ()
    forbidden: tuple[Idea, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class QuestionSet:
    content_version: str | None
    questions: tuple[EvalQuestion, ...]


class QuestionSetError(Exception):
    """Carries every issue of the question file, so the author fixes them in one pass."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("\n".join(issues))


@dataclass(frozen=True)
class Grade:
    passed: bool
    missing: list[str]
    found_forbidden: list[str]


# ---------- Matching ----------


@dataclass(frozen=True)
class _Answer:
    padded_forms: tuple[str, ...]
    words: frozenset[str]
    amounts: frozenset[int]


def _prepare(answer: str) -> _Answer:
    forms = claim_forms(answer)
    return _Answer(
        padded_forms=tuple(f" {f} " for f in forms),
        words=frozenset(w for f in forms for w in f.split()),
        amounts=frozenset(extract_amounts(answer)),
    )


def _phrase_present(phrase: str, answer: _Answer) -> bool:
    amounts = extract_amounts(phrase)
    if amounts:
        # Words beside the amount ("giảm" in "giảm 30.000đ") must also be said; digits and unit words are the amount.
        words = {w for f in claim_forms(phrase) for w in f.split()}
        context = {w for w in words if w not in _UNIT_WORDS and not any(ch.isdigit() for ch in w)}
        return set(amounts) <= answer.amounts and context <= answer.words
    return any(f" {form} " in padded for form in claim_forms(phrase) if form for padded in answer.padded_forms)


def _idea_present(idea: Idea, answer: _Answer) -> bool:
    return any(_phrase_present(p, answer) for p in idea)


def grade_answer(question: EvalQuestion, answer: str, catalog: ProductCatalog) -> Grade:
    """Grade the host's answer (sentences that passed the guard, joined). Ideas are named by their first phrasing."""
    prepared = _prepare(answer)
    missing = [idea[0] for idea in question.required if not _idea_present(idea, prepared)]
    found = [idea[0] for idea in question.forbidden if _idea_present(idea, prepared)]
    unknown: list[int] = []
    for amount in extract_amounts(answer):
        if amount not in catalog.known_amounts and amount not in unknown:
            unknown.append(amount)
    found += [f"{UNKNOWN_AMOUNT_IDEA}: {format_price(a)}" for a in unknown]
    return Grade(passed=not missing and not found, missing=missing, found_forbidden=found)


# ---------- Question file ----------


def _parse_ideas(value: Any, field: str, label: str, issues: list[str]) -> tuple[Idea, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        issues.append(f"{label}: '{field}' phải là danh sách ý, mỗi ý là danh sách cách nói")
        return ()
    ideas: list[Idea] = []
    for n, idea in enumerate(value, start=1):
        if not isinstance(idea, list) or not idea:
            issues.append(f"{label}: ý thứ {n} của '{field}' phải là danh sách cách nói, không rỗng")
            continue
        phrases = [p for p in idea if isinstance(p, str) and any(f for f in claim_forms(p))]
        if len(phrases) != len(idea):
            issues.append(f"{label}: ý thứ {n} của '{field}' có cách nói rỗng hoặc không phải chuỗi")
            continue
        ideas.append(tuple(phrases))
    return tuple(ideas)


def parse_question_set(data: Any) -> QuestionSet:
    """Validate the decoded JSON; raise `QuestionSetError` listing every issue."""
    issues: list[str] = []
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list) or not data["questions"]:
        raise QuestionSetError(["File phải là object JSON có 'questions' là danh sách câu hỏi, không rỗng"])
    version = data.get("content_version")
    if version is not None and not isinstance(version, str):
        issues.append("'content_version' phải là chuỗi")
        version = None

    questions: list[EvalQuestion] = []
    seen: set[str] = set()
    for n, raw in enumerate(data["questions"], start=1):
        if not isinstance(raw, dict):
            issues.append(f"Câu thứ {n}: phải là object JSON")
            continue
        qid = raw.get("id")
        label = f"Câu '{qid}'" if isinstance(qid, str) and qid.strip() else f"Câu thứ {n}"
        if not isinstance(qid, str) or not qid.strip():
            issues.append(f"{label}: thiếu 'id'")
        elif qid in seen:
            issues.append(f"{label}: 'id' bị trùng")
        else:
            seen.add(qid)
        text = raw.get("question")
        if not isinstance(text, str) or not text.strip():
            issues.append(f"{label}: thiếu nội dung 'question'")
        author = raw.get("author", "")
        if not isinstance(author, str):
            issues.append(f"{label}: 'author' phải là chuỗi")
            author = ""
        note = raw.get("note")
        required = _parse_ideas(raw.get("required"), "required", label, issues)
        forbidden = _parse_ideas(raw.get("forbidden"), "forbidden", label, issues)
        questions.append(
            EvalQuestion(
                id=qid if isinstance(qid, str) else "",
                author=author,
                question=text if isinstance(text, str) else "",
                required=required,
                forbidden=forbidden,
                note=note if isinstance(note, str) else None,
            )
        )
    if issues:
        raise QuestionSetError(issues)
    return QuestionSet(content_version=version, questions=tuple(questions))


def load_question_set(path: Path) -> QuestionSet:
    try:
        # utf-8-sig: files saved by Windows editors may start with a BOM.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise QuestionSetError([f"Không đọc được file câu hỏi '{path}': {exc.strerror or exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise QuestionSetError(
            [f"File câu hỏi '{path.name}' không phải JSON hợp lệ (dòng {exc.lineno}): {exc.msg}"]
        ) from exc
    try:
        return parse_question_set(data)
    except QuestionSetError as exc:
        raise QuestionSetError([f"{path.name}: {issue}" for issue in exc.issues]) from None
