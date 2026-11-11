"""T016: `clean_spoken()` strips formatting symbols from a spoken line (004 contracts/adapters.md §3, FR-009)."""

from __future__ import annotations

import pytest

from ai_live.brain.sanitize import clean_spoken


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("- Kem thấm nhanh nha.", "Kem thấm nhanh nha."),
        ("* Kem thấm nhanh nha.", "Kem thấm nhanh nha."),
        ("• Kem thấm nhanh nha.", "Kem thấm nhanh nha."),
        ("– Kem thấm nhanh nha.", "Kem thấm nhanh nha."),
        ("1. Kem thấm nhanh nha.", "Kem thấm nhanh nha."),
        ("2) Kem thấm nhanh nha.", "Kem thấm nhanh nha."),
        ("  - 1. Kem thấm nhanh nha.", "Kem thấm nhanh nha."),
    ],
)
def test_leading_bullets_and_numbering_removed(raw, expected):
    assert clean_spoken(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("# Giá và phân loại", "Giá và phân loại"),
        ("### Giá và phân loại", "Giá và phân loại"),
    ],
)
def test_heading_marks_removed(raw, expected):
    assert clean_spoken(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Kem **thấm nhanh** lắm nha.", "Kem thấm nhanh lắm nha."),
        ("Kem __thấm nhanh__ lắm nha.", "Kem thấm nhanh lắm nha."),
        ("Kem `thấm nhanh` lắm nha.", "Kem thấm nhanh lắm nha."),
        ("**Kem chống nắng X** giá 250.000đ nha.", "Kem chống nắng X giá 250.000đ nha."),
    ],
)
def test_emphasis_and_code_marks_removed(raw, expected):
    assert clean_spoken(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Kem thấm nhanh lắm nha 😍.", "Kem thấm nhanh lắm nha."),
        ("Chào cả nhà ❤️ mình bắt đầu nha!", "Chào cả nhà mình bắt đầu nha!"),
        ("Cả nhà ơi 👩‍👩‍👧 vô live nè.", "Cả nhà ơi vô live nè."),
        ("✨ Kem thấm nhanh nha ✨", "Kem thấm nhanh nha"),
        ("Kem thấm nhanh️ nha.", "Kem thấm nhanh nha."),
    ],
)
def test_emoji_variation_selector_and_joiner_removed(raw, expected):
    assert clean_spoken(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Dạ kem chống nắng X loại 50 ml giá 250.000đ, loại 100 ml giá 420.000đ nha anh chị.",
        "Toner Z giá 1.250.000 VND, đang giảm 10% cho đơn đầu tiên ạ!",
        "Anh chị dùng thử chưa? Thấm nhanh lắm nè; không bết dính đâu.",
        "1.250.000đ là giá của Toner Z nha.",
        "Giá từ 250.000đ – 420.000đ tùy phân loại ạ.",
    ],
)
def test_vietnamese_numbers_percent_and_punctuation_kept(text):
    assert clean_spoken(text) == text


def test_whitespace_collapsed():
    assert clean_spoken("  Kem   thấm\nnhanh  nha.  ") == "Kem thấm nhanh nha."


def test_only_symbols_becomes_empty():
    assert clean_spoken("- ** 😍 ✨ **") == ""


@pytest.mark.parametrize(
    "raw",
    [
        "- **Kem** thấm nhanh 😍 nha.",
        "😀 - 1. Kem thấm nhanh nha.",
        "`- Kem thấm nhanh`",
        "# 1) __Giá__ 250.000đ ❤️ ạ",
        "Dòng một.\n- Dòng hai 👍 nha.",
        "Kem thấm nhanh 😍 .",
        "",
    ],
)
def test_idempotent(raw):
    once = clean_spoken(raw)
    assert clean_spoken(once) == once
