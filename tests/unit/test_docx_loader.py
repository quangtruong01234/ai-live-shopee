"""T010: đọc và kiểm tra file Word nội dung (FR-007, FR-025, contracts/content-template.md)."""

import hashlib

import pytest

from ai_live.products.docx_loader import load_catalog
from ai_live.products.models import ContentLoadError, product_detail
from fixtures.content_builder import build_docx, product_blocks, valid_blocks, valid_docx

MAX = 5 * 1024 * 1024


def load(blocks):
    return load_catalog(build_docx(blocks), "demo.docx", max_bytes=MAX)


def issue_codes(blocks) -> list[str]:
    with pytest.raises(ContentLoadError) as exc:
        load(blocks)
    return [i.code for i in exc.value.issues]


# ---------- File hợp lệ ----------


def test_valid_file_builds_catalog():
    data = valid_docx()
    catalog = load_catalog(data, "demo.docx", max_bytes=MAX)
    assert catalog.version == hashlib.sha256(data).hexdigest()[:12]
    assert catalog.source_name == "demo.docx"
    assert [p.name for p in catalog.products] == ["Kem chống nắng X", "Sữa rửa mặt Y", "Toner Z"]
    assert [p.is_primary for p in catalog.products] == [True, False, False]
    assert len({p.id for p in catalog.products}) == 3


def test_product_with_variants_and_price_range():
    kem = load(valid_blocks()).products[0]
    assert kem.price is None
    assert [(v.name, v.price) for v in kem.variants] == [("50 ml", 250_000), ("100 ml", 420_000)]
    assert kem.price_range == (250_000, 420_000)


def test_single_price_product():
    catalog = load(valid_blocks())
    sua, toner = catalog.products[1], catalog.products[2]
    assert sua.price == 159_000 and sua.variants == ()
    assert sua.price_range == (159_000, 159_000)
    assert toner.price == 1_250_000
    assert toner.link is None


def test_sections_are_read_in_order():
    kem = load(valid_blocks()).products[0]
    assert kem.description.startswith("Kem chống nắng dạng sữa")
    assert kem.specs == (("Dung tích", "50 ml"), ("Chỉ số chống nắng", "SPF 50"))
    assert kem.faq == (("Dùng cho da dầu được không?", "Dạ dùng được cho da dầu."),)
    assert kem.promotions == ("Giảm 30.000đ cho đơn từ 500.000đ",)
    assert kem.forbidden_claims == ("chữa khỏi mụn",)
    assert kem.intro.startswith("Chào cả nhà")
    assert kem.link == "https://example.com/kem-x"


def test_forbidden_none_is_empty_tuple():
    assert load(valid_blocks()).products[1].forbidden_claims == ()


def test_known_amounts_cover_prices_promotions_and_range():
    amounts = load(valid_blocks()).known_amounts
    assert {250_000, 420_000, 159_000, 1_250_000, 30_000, 500_000} <= amounts


def test_preamble_before_first_heading_is_ignored():
    catalog = load([("p", "Ghi chú: giá 999.000đ chỉ là ví dụ"), *valid_blocks()])
    assert 999_000 not in catalog.known_amounts


def test_section_names_match_case_insensitive_and_extra_spaces():
    blocks = [("h2", "  GIÁ  ") if b == ("h2", "Giá") else b for b in valid_blocks()]
    assert len(load(blocks).products) == 3


def test_price_with_thousand_separator_variants_and_suffixes():
    for raw, expected in [("250000", 250_000), ("250,000 vnđ", 250_000), ("250.000 ₫", 250_000)]:
        blocks = product_blocks("Kem X", price=raw)
        assert load(blocks).products[0].price == expected


# ---------- Mỗi mã lỗi một case ----------


def test_no_products():
    assert issue_codes([("p", "chỉ có ghi chú")]) == ["no_products"]


def test_primary_count_zero_and_two():
    assert "primary_count" in issue_codes(product_blocks("A", "phụ"))
    assert "primary_count" in issue_codes(product_blocks("A", "chính") + product_blocks("B", "chính"))


def test_secondary_count():
    blocks = product_blocks("A", "chính")
    for name in "BCDE":
        blocks += product_blocks(name, "phụ")
    assert issue_codes(blocks) == ["secondary_count"]


@pytest.mark.parametrize("type_line", ["", "Loại: khác", "Sản phẩm chính"])
def test_missing_type(type_line):
    assert "missing_type" in issue_codes(product_blocks("A", type_line=type_line))


@pytest.mark.parametrize(
    ("kwargs", "section"),
    [
        ({"price": None}, "Giá"),
        ({"description": None}, "Mô tả"),
        ({"forbidden": None}, "Khẳng định bị cấm"),
        ({"intro": None}, "Bài giới thiệu"),
    ],
)
def test_missing_section(kwargs, section):
    with pytest.raises(ContentLoadError) as exc:
        load(product_blocks("Kem X", **kwargs))
    [issue] = exc.value.issues
    assert issue.code == "missing_section"
    assert issue.product == "Kem X"
    assert issue.section == section
    assert section in issue.message


def test_empty_section():
    blocks = product_blocks("Kem X", description=None)
    blocks.insert(blocks.index(("p", "250.000đ")) + 1, ("h2", "Mô tả"))
    with pytest.raises(ContentLoadError) as exc:
        load(blocks)
    [issue] = exc.value.issues
    assert (issue.code, issue.section) == ("empty_section", "Mô tả")


def test_unknown_section():
    blocks = product_blocks("Kem X") + [("h2", "Ưu đãi"), ("p", "giảm 10%")]
    with pytest.raises(ContentLoadError) as exc:
        load(blocks)
    [issue] = exc.value.issues
    assert issue.code == "unknown_section"
    assert "Ưu đãi" in issue.message


def test_duplicate_section():
    blocks = product_blocks("Kem X") + [("h2", "Mô tả"), ("p", "mô tả lần hai")]
    assert issue_codes(blocks) == ["duplicate_section"]


def test_duplicate_product():
    blocks = product_blocks("Kem X", "chính") + product_blocks("kem  x", "phụ")
    assert "duplicate_product" in issue_codes(blocks)


def test_duplicate_variant():
    blocks = product_blocks("Kem X", price=None, variants=[("50 ml", "250.000đ"), ("50 ML", "260.000đ")])
    assert issue_codes(blocks) == ["duplicate_variant"]


@pytest.mark.parametrize("raw", ["250k", "250 nghìn", "2,5 triệu", "250.5", "0đ", "liên hệ"])
def test_price_format(raw):
    with pytest.raises(ContentLoadError) as exc:
        load(product_blocks("Kem X", price=raw))
    [issue] = exc.value.issues
    assert issue.code == "price_format"
    assert raw in issue.message


def test_variant_price_format():
    assert issue_codes(product_blocks("Kem X", price=None, variants=[("50 ml", "250k")])) == ["price_format"]


def test_price_ambiguous_line_and_table():
    blocks = product_blocks("Kem X", price="250.000đ", variants=[("50 ml", "250.000đ")])
    assert issue_codes(blocks) == ["price_ambiguous"]


def test_price_ambiguous_two_lines():
    blocks = product_blocks("Kem X")
    blocks.insert(blocks.index(("p", "250.000đ")) + 1, ("p", "260.000đ"))
    assert issue_codes(blocks) == ["price_ambiguous"]


def test_price_table_wrong_header_or_columns():
    bad_header = product_blocks("Kem X", price=None)
    bad_header.insert(2, ("h2", "Giá"))
    bad_header.insert(3, ("table", [["Loại", "Tiền"], ["50 ml", "250.000đ"]]))
    assert issue_codes(bad_header) == ["price_table"]

    three_cols = product_blocks("Kem X", price=None)
    three_cols.insert(2, ("h2", "Giá"))
    three_cols.insert(3, ("table", [["Phân loại", "Giá", "Ghi chú"], ["50 ml", "250.000đ", ""]]))
    assert issue_codes(three_cols) == ["price_table"]


def test_faq_format_unpaired_question():
    blocks = product_blocks("Kem X", faq=())
    i = blocks.index(("h2", "Khuyến mãi"))
    blocks[i:i] = [("h2", "Câu hỏi thường gặp"), ("p", "H: Có ship COD không?")]
    assert issue_codes(blocks) == ["faq_format"]


def test_not_docx_and_too_large():
    with pytest.raises(ContentLoadError) as exc:
        load_catalog(b"hello world", "x.docx", max_bytes=MAX)
    assert [i.code for i in exc.value.issues] == ["not_docx"]

    data = valid_docx()
    with pytest.raises(ContentLoadError) as exc:
        load_catalog(data, "x.docx", max_bytes=len(data) - 1)
    assert [i.code for i in exc.value.issues] == ["too_large"]


def test_corrupt_zip_is_not_docx():
    with pytest.raises(ContentLoadError) as exc:
        load_catalog(b"PK\x03\x04" + b"\x00" * 100, "x.docx", max_bytes=MAX)
    assert [i.code for i in exc.value.issues] == ["not_docx"]


# ---------- Nhiều lỗi báo đủ một lần, mâu thuẫn bị từ chối ----------


def test_multiple_errors_reported_together():
    blocks = product_blocks("Kem X", price="250k", forbidden=None) + product_blocks("Kem X", "phụ", intro=None)
    codes = issue_codes(blocks)
    assert {"price_format", "missing_section", "duplicate_product"} <= set(codes)
    assert codes.count("missing_section") == 2


def test_issue_messages_are_vietnamese_with_product_and_section():
    with pytest.raises(ContentLoadError) as exc:
        load(product_blocks("Kem X", price="250k"))
    [issue] = exc.value.issues
    assert issue.product == "Kem X"
    assert issue.section == "Giá"
    assert "Kem X" in issue.message and "Giá" in issue.message
    assert "Kem X" in str(exc.value)


# ---------- Product detail for the control page (012 FR-022, data-model §8) ----------


def test_product_detail_is_the_file_word_for_word_without_the_link():
    kem, sua = load(valid_blocks()).products[:2]
    detail = product_detail(kem)
    assert detail == {
        "id": kem.id,
        "name": "Kem chống nắng X",
        "is_primary": True,
        "description": kem.description,
        "intro": kem.intro,
        "price": None,
        "variants": [{"name": "50 ml", "price": 250_000}, {"name": "100 ml", "price": 420_000}],
        "specs": [["Dung tích", "50 ml"], ["Chỉ số chống nắng", "SPF 50"]],
        "faq": [["Dùng cho da dầu được không?", "Dạ dùng được cho da dầu."]],
        "promotions": ["Giảm 30.000đ cho đơn từ 500.000đ"],
        "forbidden_claims": ["chữa khỏi mụn"],
    }
    # The link is never read aloud, and the operator does not need it to check what the AI says.
    assert "link" not in detail
    assert product_detail(sua)["price"] == 159_000
    assert product_detail(sua)["variants"] == []
    assert product_detail(sua)["forbidden_claims"] == []
