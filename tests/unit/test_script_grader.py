"""T054: grading one scripted sentence on its raw text (004 US4 #2, FR-025, research R15).

Every check uses the same `OutputGuard` as the live path, plus the two grader-only kinds `bad_pronoun` and
`formatting`. The guard gets an explicit phrase list, so these tests do not depend on `data/rules/platform_phrases.txt`.
"""

from __future__ import annotations

import pytest

from ai_live.brain.guard import OutputGuard
from ai_live.core.models import GuardReason
from ai_live.products.docx_loader import load_catalog
from ai_live.qa_eval.script_grader import (
    BAD_PRONOUNS,
    VIOLATION_KINDS,
    GradedSentence,
    Violation,
    grade_sentence,
    grade_sentences,
    sentence_count_warning,
)
from fixtures.content_builder import valid_docx

CATALOG = load_catalog(valid_docx(), "valid.docx", 5_000_000)
# Known numbers in the test catalog: 250.000 / 420.000 (variants), 159.000, 1.250.000, promo 30.000 / 500.000,
# plus 50, 100, 2, 1 from specs and promotions. "chữa khỏi mụn" is the main product's forbidden claim.
GUARD = OutputGuard(("giỏ hàng", "voucher"))


def kinds(text: str) -> list[str]:
    return [v.kind for v in grade_sentence(text, CATALOG, GUARD)]


def test_violation_kinds_follow_data_model_order():
    assert VIOLATION_KINDS == (
        "unknown_amount",
        "unknown_percent",
        "forbidden_claim",
        "link",
        "platform_phrase",
        "bad_pronoun",
        "formatting",
    )
    # Every guard reason is a grader kind, so a new guard check cannot be silently ignored by the report.
    assert {r.value for r in GuardReason} <= set(VIOLATION_KINDS)


def test_clean_grounded_sentence_has_no_violation():
    assert grade_sentence("Loại 50 ml giá 250.000đ nha anh chị.", CATALOG, GUARD) == []


@pytest.mark.parametrize(
    ("text", "kind", "detail"),
    [
        ("Giá chỉ 99.000đ thôi ạ.", "unknown_amount", "99000"),
        ("Hôm nay giảm 45% cho anh chị nha.", "unknown_percent", "45%"),
        ("Kem này chữa khỏi mụn luôn đó anh chị.", "forbidden_claim", "chữa khỏi mụn"),
        ("Anh chị xem thêm ở https://example.com nha.", "link", None),
        ("Anh chị thêm vào giỏ hàng giúp em nha.", "platform_phrase", "giỏ hàng"),
    ],
)
def test_guard_kinds_are_reported_with_detail(text, kind, detail):
    violations = grade_sentence(text, CATALOG, GUARD)
    assert [v.kind for v in violations] == [kind]
    if detail is not None:
        assert violations[0].detail == detail
    else:
        assert violations[0].detail


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        ("Tôi thấy kem này thấm nhanh lắm.", "tôi"),
        ("Bạn dùng thử là mê liền nha.", "bạn"),
        ("Quý khách yên tâm về chất lượng nha.", "quý khách"),
        ("Các bạn ơi, kem này thấm nhanh lắm.", "các bạn"),
    ],
)
def test_wrong_pronoun_is_bad_pronoun(text, detail):
    violations = grade_sentence(text, CATALOG, GUARD)
    assert [v.kind for v in violations] == ["bad_pronoun"]
    assert violations[0].detail == detail


@pytest.mark.parametrize(
    "text",
    [
        "Bên mình có hai loại cho anh chị chọn nha.",
        # Same letters as "bạn" / "tôi" without their diacritics: matching must keep diacritics.
        "Shop bán kem này lâu rồi nha anh chị.",
        "Tối nay em live tới khuya nha anh chị.",
        "Em gửi anh chị bảng giá nha.",
    ],
)
def test_right_pronouns_and_lookalike_words_pass(text):
    assert kinds(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Em thấy nhiều bạn hỏi về cách sử dụng đó, nên em nhắc lại nha.",
        "Em thấy sản phẩm này rất phù hợp cho những bạn da cần thêm ẩm nha.",
        "Mấy bạn da dầu dùng loại này là hợp nha anh chị.",
        "Một số bạn thích loại 100 ml hơn nha anh chị.",
        "Các bạn khác cũng chọn loại 50 ml nha anh chị.",
        "Bạn nào da dầu thì chọn loại này nha.",
        "Hôm qua có bạn ấy hỏi em về loại 50 ml nha anh chị.",
    ],
)
def test_third_person_ban_is_not_bad_pronoun(text):
    # Talking about other customers is not calling the viewer "bạn" (research R15, approved 2026-11-03).
    assert kinds(text) == []


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        ("Mấy bạn ơi, kem này thấm nhanh lắm.", "bạn"),
        ("Những bạn ơi, chốt đơn nha.", "bạn"),
        ("Em thấy nhiều bạn hỏi, bạn cũng thử đi nha.", "bạn"),
        ("Bạn nào cũng mê, bạn dùng thử nha.", "bạn"),
    ],
)
def test_direct_address_next_to_third_person_is_still_bad(text, detail):
    violations = grade_sentence(text, CATALOG, GUARD)
    assert [v.kind for v in violations] == ["bad_pronoun"]
    assert violations[0].detail == detail


def test_bad_pronoun_counts_once_per_sentence():
    violations = grade_sentence("Tôi nói bạn nghe, các bạn ơi.", CATALOG, GUARD)
    assert [v.kind for v in violations] == ["bad_pronoun"]
    assert "tôi" in (violations[0].detail or "")


@pytest.mark.parametrize(
    "text",
    [
        "**Kem** thấm nhanh nha anh chị.",
        "- Kem thấm nhanh nha anh chị.",
        "1. Kem thấm nhanh nha anh chị.",
        "# Giá và phân loại",
        "Kem thấm nhanh nha anh chị 😍",
    ],
)
def test_formatting_symbols_are_formatting(text):
    assert kinds(text) == ["formatting"]


def test_extra_whitespace_alone_is_not_formatting():
    # `normalize_text` collapses whitespace too, so only real symbols make the two forms differ.
    assert kinds("Kem   thấm  nhanh nha anh chị.") == []


def test_grading_runs_on_raw_text_so_guard_and_formatting_both_hit():
    assert kinds("**99.000đ** thôi đó anh chị.") == ["unknown_amount", "formatting"]


def test_one_sentence_can_carry_several_kinds():
    assert kinds("Tôi giảm 45% cho bạn nha.") == ["unknown_percent", "bad_pronoun"]


def test_bad_pronoun_list_matches_research_r15():
    assert set(BAD_PRONOUNS) >= {"tôi", "bạn", "quý khách", "các bạn"}
    assert "mình" not in BAD_PRONOUNS
    assert "bên mình" not in BAD_PRONOUNS


def test_grade_sentences_keeps_order_and_raw_text():
    graded = grade_sentences(["Kem thấm nhanh nha anh chị.", "Giá chỉ 99.000đ thôi ạ."], CATALOG, GUARD)
    assert graded == [
        GradedSentence(raw_text="Kem thấm nhanh nha anh chị.", violations=[]),
        GradedSentence(raw_text="Giá chỉ 99.000đ thôi ạ.", violations=[Violation("unknown_amount", "99000")]),
    ]


@pytest.mark.parametrize(
    ("count", "warn"),
    [(0, True), (2, True), (3, False), (4, False), (6, False), (7, True)],
)
def test_sentence_count_outside_min_max_is_a_warning(count, warn):
    assert sentence_count_warning(count, 3, 6) is warn


def test_sentence_count_warning_is_not_a_violation():
    lines = ["Kem thấm nhanh nha anh chị.", "Bên mình có hai loại nha."]
    assert sentence_count_warning(len(lines), 3, 6) is True
    assert all(g.violations == [] for g in grade_sentences(lines, CATALOG, GUARD))
