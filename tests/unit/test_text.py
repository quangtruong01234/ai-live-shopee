"""T014: hàm văn bản dùng chung (research R8, R9)."""

import unicodedata

import pytest

from ai_live.core.text import extract_amounts, match_form, normalize_text


def test_normalize_nfc_and_whitespace():
    decomposed = unicodedata.normalize("NFD", "Giá  bao   nhiêu\n vậy ")
    out = normalize_text(decomposed)
    assert out == "Giá bao nhiêu vậy"
    assert unicodedata.is_normalized("NFC", out)


def test_normalize_truncates():
    assert normalize_text("a" * 500, max_chars=300) == "a" * 300
    assert normalize_text("abc", max_chars=300) == "abc"


def test_match_form_lower_no_diacritics():
    assert match_form("Đã CHỮA khỏi Mụn") == "da chua khoi mun"
    assert match_form("  Giá   bao nhiêu? ") == "gia bao nhieu?"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Giá 1.250.000đ nha", [1_250_000]),
        ("chỉ 250k thôi", [250_000]),
        ("1 nghìn", [1_000]),
        ("2 ngàn", [2_000]),
        ("2,5 triệu", [2_500_000]),
        ("250.000 VND", [250_000]),
        ("420.000₫", [420_000]),
        ("giá 159.000 bạn nhé", [159_000]),
        ("50 ml giá 250.000đ, 100 ml giá 420.000đ", [250_000, 420_000]),
    ],
)
def test_extract_amounts(text, expected):
    assert extract_amounts(text) == expected


@pytest.mark.parametrize("text", ["Kem này thấm nhanh lắm", "dung tích 1.000 ml", "SPF 50", "mua 2 tặng 1"])
def test_extract_amounts_none(text):
    assert extract_amounts(text) == []
