"""T032: guard đầu ra theo từng câu (research R8; US1 #3, #4; FR-010, FR-011)."""

from __future__ import annotations

import pytest

from ai_live.brain.guard import OutputGuard, refusal_sentence
from ai_live.core.models import GuardReason
from ai_live.products.docx_loader import load_catalog
from fixtures.content_builder import valid_docx


@pytest.fixture
def catalog():
    return load_catalog(valid_docx(), "valid.docx", 5_000_000)


@pytest.fixture
def guard():
    return OutputGuard()


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ kem này dùng là chữa khỏi mụn luôn nha bạn Lan.",
        "Da kem nay dung la CHUA KHOI MUN luon nha.",
        "Dạ   chữa  khỏi   mụn ạ.",
    ],
)
def test_forbidden_claim_blocked(guard, catalog, sentence):
    result = guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.FORBIDDEN_CLAIM
    assert result.detail == "chữa khỏi mụn"


@pytest.mark.parametrize(
    ("sentence", "amount"),
    [
        ("Dạ giá chỉ 99k thôi bạn ơi.", 99_000),
        ("Dạ giá 1 nghìn nha.", 1_000),
        ("Dạ giá 199.000đ nha.", 199_000),
        ("Giảm còn 2 triệu nha.", 2_000_000),
    ],
)
def test_unknown_amount_blocked(guard, catalog, sentence, amount):
    result = guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.UNKNOWN_AMOUNT
    assert result.detail == str(amount)


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ kem chống nắng X loại 50 ml giá 250.000đ, loại 100 ml giá 420.000đ nha bạn Lan.",
        "Dạ giá từ 250.000đ đến 420.000đ ạ.",
        "Toner Z giá 1.250.000 VND nha.",
        "Đang giảm 30.000đ cho đơn từ 500k đó bạn.",
        "Dạ kem không chứa cồn, dùng cho da dầu được nha.",
        "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha.",
    ],
)
def test_grounded_sentence_passes(guard, catalog, sentence):
    assert guard.check(sentence, catalog).ok


def test_forbidden_claim_of_any_product_counts(guard, catalog):
    # Sữa rửa mặt Y không có khẳng định cấm, nhưng câu nhắc "chữa khỏi mụn" vẫn bị chặn: cấm theo toàn catalog.
    assert not guard.check("Sữa rửa mặt Y chữa khỏi mụn nha.", catalog).ok


def test_refusal_sentence_passes_guard(guard, catalog):
    sentence = refusal_sentence("bạn Lan")
    assert sentence == "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha."
    assert guard.check(sentence, catalog).ok
