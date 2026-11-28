"""ADR-088: budget advice may say totals computed from the file's prices and repeat the viewer's own amount."""

from __future__ import annotations

import pytest

from ai_live.brain.guard import OutputGuard, comment_amounts, derived_amounts, sentence_counts
from ai_live.core.models import GuardReason
from ai_live.products.docx_loader import load_catalog
from fixtures.content_builder import build_docx, product_blocks


@pytest.fixture
def catalog():
    blocks = product_blocks("Lốc A", "chính", price="95.000đ", promotions=("Mua 2 lốc giảm 10.000đ",))
    blocks += product_blocks("Chai B", "phụ", price="12.000đ", promotions=(), forbidden=())
    return load_catalog(build_docx(blocks), "budget.docx", 5_000_000)


@pytest.fixture
def guard():
    return OutputGuard()


def test_derived_amounts_cover_multiples_discounts_and_small_mixes(catalog):
    amounts = derived_amounts(catalog)
    assert {95_000, 190_000, 180_000, 36_000, 107_000, 119_000} <= amounts
    assert 101_000 not in amounts


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ mua 2 lốc là 190.000đ, được giảm 10.000đ nên còn 180.000đ nha bạn Lan.",
        "Dạ 3 chai B là 36.000đ ạ.",
        "Dạ 1 lốc A với 1 chai B là 107.000đ nha.",
    ],
)
def test_totals_from_the_file_pass(guard, catalog, sentence):
    assert guard.check(sentence, catalog).ok


def test_viewer_budget_may_be_repeated_next_to_a_price(guard, catalog):
    viewer = comment_amounts("mình có 100k thì mua gì được shop")
    sentence = "Dạ với 100.000đ bạn lấy được lốc A giá 95.000đ nha."
    assert guard.check(sentence, catalog, viewer_amounts=viewer).ok
    assert not guard.check(sentence, catalog).ok


def test_viewer_amount_alone_is_never_confirmed(guard, catalog):
    viewer = comment_amounts("lốc A giá 50k phải không shop")
    result = guard.check("Dạ đúng rồi, 50.000đ nha bạn.", catalog, viewer_amounts=viewer)
    assert not result.ok
    assert result.reason is GuardReason.UNKNOWN_AMOUNT


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ lốc A giảm còn 190.000đ thôi nha.",  # 2 x 95.000 without saying 2: reads as a made-up price
        "Dạ chai B giá 120.000đ nha.",  # 10 x 12.000
    ],
)
def test_a_total_without_its_count_is_blocked(guard, catalog, sentence):
    result = guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.UNKNOWN_AMOUNT


def test_a_total_with_its_count_in_words_passes(guard, catalog):
    assert guard.check("Dạ mười chai B là 120.000đ nha.", catalog).ok


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Dạ mua 2 lốc với hai chai nha.", {2}),
        ("Dạ 3 chai là 36.000đ.", {3}),
        ("Dạ giá 2 triệu, 5k hay 20 nghìn.", set()),
        ("Lốc 6 chai 355ml nha.", {6}),
    ],
)
def test_sentence_counts(sentence, expected):
    assert sentence_counts(sentence) == expected


def test_an_invented_total_is_still_blocked(guard, catalog):
    result = guard.check("Dạ 2 lốc chỉ còn 150.000đ thôi nha.", catalog)
    assert not result.ok
    assert result.detail == "150000"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mình có 100k", {100_000}),
        ("có 100 thì mua gì", {100_000}),
        ("tầm 50 nghìn", {50_000}),
        ("ngân sách 200.000đ", {200_000}),
        ("chai 500ml bao nhiêu", set()),
    ],
)
def test_comment_amounts(text, expected):
    assert comment_amounts(text) == expected
