"""T027 (003): `normalize_for_speech` turns numbers, prices, units and codes into Southern Vietnamese words.

The 10 rules of data-model §3 in order, with at least 2 sentences each (SC-001), the US2 acceptance scenarios
verbatim, the number-reading rules of FR-007 and FR-008. Pure functions: no TTS source is built (FR-010).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ai_live.tts.normalize import load_abbreviations, normalize_for_speech

ABBREVIATIONS = {"SP": "sản phẩm", "KM": "khuyến mãi", "SL": "số lượng", "VND": "đồng"}

CASES = [
    # US2 acceptance scenarios #1-#4, verbatim.
    ("Giá chỉ 259.000đ", "Giá chỉ hai trăm năm mươi chín ngàn đồng"),
    ("Combo 250k, giảm 15%", "Combo hai trăm năm mươi ngàn, giảm mười lăm phần trăm"),
    (
        "Giá 259.000đ–439.000đ",
        "Giá từ hai trăm năm mươi chín ngàn đồng đến bốn trăm ba mươi chín ngàn đồng",
    ),
    ("Chai 1,5L", "Chai một phẩy năm lít"),
    ("Tuýp 500ml", "Tuýp năm trăm mi li lít"),
    # Rule 1: links and emoji are dropped.
    ("Xem 👉 https://x.vn", "Xem"),
    ("Liên hệ www.shop.vn để biết thêm nha", "Liên hệ để biết thêm nha"),
    ("Kem siêu nhẹ ✨✨ luôn ạ!", "Kem siêu nhẹ luôn ạ!"),
    ("Thơm lắm \N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16} nha", "Thơm lắm nha"),
    # Rule 2: abbreviations, whole word, any case.
    ("SP này đang KM nha", "sản phẩm này đang khuyến mãi nha"),
    ("sl có hạn nha chị", "số lượng có hạn nha chị"),
    ("Giá 250 VND", "Giá hai trăm năm mươi đồng"),
    # Rule 3: letter sizes.
    ("Áo size M nha chị", "Áo sai em nha chị"),
    ("Còn size S và size L", "Còn sai ét và sai eo"),
    ("Còn size XL ạ", "Còn sai ích eo ạ"),
    # Rule 4: ranges of numbers, with or without units; no doubled "từ".
    (
        "Giá từ 259.000đ - 439.000đ nha.",
        "Giá từ hai trăm năm mươi chín ngàn đồng đến bốn trăm ba mươi chín ngàn đồng nha.",
    ),
    ("Áo giá 199k – 249k", "Áo giá từ một trăm chín mươi chín ngàn đến hai trăm bốn mươi chín ngàn"),
    ("Hợp người từ 50 ~ 60kg", "Hợp người từ năm mươi đến sáu mươi ki lô gam"),
    ("Giảm 10% - 20%", "Giảm từ mười phần trăm đến hai mươi phần trăm"),
    ("Combo 2-3 hộp", "Combo từ hai đến ba hộp"),
    # Rule 5: prices.
    ("Giá 99.000 đồng", "Giá chín mươi chín ngàn đồng"),
    ("Giá 120.000vnđ", "Giá một trăm hai mươi ngàn đồng"),
    ("Giá 1.050.000đ", "Giá một triệu không trăm năm mươi ngàn đồng"),
    ("Giá 15.500đ", "Giá mười lăm ngàn năm trăm đồng"),
    ("Tổng 2.000.000.000đ", "Tổng hai tỷ đồng"),
    # Rule 6: number + k.
    ("Combo 2 hộp chỉ 499k thôi ạ!", "Combo hai hộp chỉ bốn trăm chín mươi chín ngàn thôi ạ!"),
    ("Giảm thêm 30K", "Giảm thêm ba mươi ngàn"),
    # Rule 7: percent.
    ("Giảm 0,5%", "Giảm không phẩy năm phần trăm"),
    ("Giảm 45%", "Giảm bốn mươi lăm phần trăm"),
    ("Giảm 11 %", "Giảm mười một phần trăm"),
    # Rule 8: units of measure after a number.
    ("Túi 2kg", "Túi hai ki lô gam"),
    ("Dài 30cm", "Dài ba mươi xen ti mét"),
    ("Vải rộng 2m", "Vải rộng hai mét"),
    ("Gói 200g", "Gói hai trăm gam"),
    ("Dung tích 1L", "Dung tích một lít"),
    (
        "Loại 50 ml giá 259.000đ, loại 100 ml giá 439.000đ.",
        "Loại năm mươi mi li lít giá hai trăm năm mươi chín ngàn đồng, "
        "loại một trăm mi li lít giá bốn trăm ba mươi chín ngàn đồng.",
    ),
    # Rule 9: digit by digit (phone numbers, long runs, codes).
    ("Gọi 0909123456 nha", "Gọi không chín không chín một hai ba bốn năm sáu nha"),
    ("Mã 0123", "Mã không một hai ba"),
    ("Mã đơn 1234567890", "Mã đơn một hai ba bốn năm sáu bảy tám chín không"),
    ("Nhập mã GIAM50K", "Nhập mã giê i a em năm không ca"),
    ("Nhập mã km50", "Nhập mã ca em năm không"),
    # Rule 10: remaining numbers, Southern reading (FR-007).
    ("Tổng 1.250.000", "Tổng một triệu hai trăm năm mươi ngàn"),
    ("Nặng 3,75", "Nặng ba phẩy bảy mươi lăm"),
    ("Tỷ lệ 0,05", "Tỷ lệ không phẩy không năm"),
    ("Phiên bản 1.5", "Phiên bản một chấm năm"),
    ("Có 105 đánh giá", "Có một trăm lẻ năm đánh giá"),
    ("Có 101 màu", "Có một trăm lẻ một màu"),
    ("Có 110 màu", "Có một trăm mười màu"),
    ("Đã bán 21 hộp", "Đã bán hai mươi mốt hộp"),
    ("Có 31 màu", "Có ba mươi mốt màu"),
    ("Còn 24 hộp", "Còn hai mươi bốn hộp"),
    ("Còn 14 hộp", "Còn mười bốn hộp"),
    ("Còn 15 hộp", "Còn mười lăm hộp"),
    ("Còn 25 hộp", "Còn hai mươi lăm hộp"),
    ("Còn 10 hộp", "Còn mười hộp"),
    ("Shop có 0 phí ship", "Shop có không phí ship"),
    ("Hơn 1.000.005 lượt xem", "Hơn một triệu không trăm lẻ năm lượt xem"),
    ("Có 1.001 bình luận", "Có một ngàn không trăm lẻ một bình luận"),
    ("Năm 2026 nha", "Năm hai ngàn không trăm hai mươi sáu nha"),
    (
        "Đếm 999.999.999.999",
        "Đếm chín trăm chín mươi chín tỷ chín trăm chín mươi chín triệu "
        "chín trăm chín mươi chín ngàn chín trăm chín mươi chín",
    ),
    ("Số 1.000.000.000.000", "Số một" + " không" * 12),
    # Kept as is: English words, brands, short replies.
    ("Dùng serum Vitamin C mỗi sáng", "Dùng serum Vitamin C mỗi sáng"),
    ("Kem chống nắng Mây Sáng SPF 50 nha", "Kem chống nắng Mây Sáng SPF năm mươi nha"),
    ("Dạ.", "Dạ."),
]


@pytest.mark.parametrize(("text", "expected"), CASES, ids=[text for text, _ in CASES])
def test_normalize_reads_like_a_southern_host(text, expected):
    assert normalize_for_speech(text, ABBREVIATIONS) == expected


def test_sample_set_is_large_enough_for_sc001():
    assert len(CASES) >= 40


@pytest.mark.parametrize("text", [text for text, _ in CASES])
def test_output_has_only_letters_spaces_and_basic_punctuation(text):
    spoken = normalize_for_speech(text, ABBREVIATIONS)
    assert re.fullmatch(r"[^\W\d_]*(?:[ ,.?!]+[^\W\d_]*)*", spoken), spoken


def test_no_abbreviations_still_reads_numbers():
    assert normalize_for_speech("SP giá 250k") == "SP giá hai trăm năm mươi ngàn"


def test_only_emoji_and_links_give_empty_text():
    assert normalize_for_speech("👉 https://x.vn ✨") == ""


# ---------- load_abbreviations ----------


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "abbr.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_abbreviations_reads_a_valid_file(tmp_path):
    assert load_abbreviations(_write(tmp_path, ABBREVIATIONS)) == ABBREVIATIONS


def test_repo_abbreviations_file_is_valid():
    assert load_abbreviations(Path("data/rules/tts_abbreviations.json"))["SP"] == "sản phẩm"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"": "rỗng"}, id="empty-key"),
        pytest.param({"  ": "rỗng"}, id="blank-key"),
        pytest.param({"SP": "sản phẩm", "sp": "sản phẩm"}, id="duplicate-ignoring-case"),
        pytest.param({"SP": "sản phẩm 2"}, id="digit-in-value"),
        pytest.param({"SP": ""}, id="empty-value"),
        pytest.param({"SP": 1}, id="value-not-text"),
        pytest.param(["SP"], id="not-an-object"),
    ],
)
def test_load_abbreviations_rejects_a_bad_file(tmp_path, data):
    with pytest.raises(ValueError):
        load_abbreviations(_write(tmp_path, data))
