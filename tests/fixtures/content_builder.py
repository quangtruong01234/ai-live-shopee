"""Build `.docx` content files in memory for tests (contracts/content-template.md).

Each file is described as a list of `(kind, value)` blocks:
- `("h1", text)`, `("h2", text)`: a heading in style Heading 1/2.
- `("p", text)`: a plain paragraph.
- `("table", [[cell, cell], ...])`: a table, the first row is the header.
Blocks let one helper build both the valid file and every broken variant, without a template per case.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence

from docx import Document

Block = tuple[str, object]


def build_docx(blocks: Iterable[Block]) -> bytes:
    """Write a list of blocks as the bytes of a `.docx` file."""
    doc = Document()
    for kind, value in blocks:
        if kind == "h1":
            doc.add_heading(str(value), level=1)
        elif kind == "h2":
            doc.add_heading(str(value), level=2)
        elif kind == "p":
            doc.add_paragraph(str(value))
        elif kind == "table":
            rows = list(value)  # type: ignore[call-overload]
            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            for r, row in enumerate(rows):
                for c, cell in enumerate(row):
                    table.cell(r, c).text = str(cell)
        else:
            raise ValueError(f"khối không hỗ trợ: {kind}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def product_blocks(
    name: str,
    kind: str = "chính",
    *,
    price: str | None = "250.000đ",
    variants: Sequence[tuple[str, str]] | None = None,
    description: str | None = "Kem chống nắng dạng sữa, thấm nhanh.",
    specs: Sequence[str] = ("Dung tích: 50 ml", "Chỉ số chống nắng: SPF 50"),
    faq: Sequence[tuple[str, str]] = (("Dùng cho da dầu được không?", "Dạ dùng được cho da dầu."),),
    promotions: Sequence[str] = ("Mua 2 tặng 1 túi đựng mỹ phẩm",),
    forbidden: Sequence[str] | None = ("chữa khỏi mụn",),
    intro: str | None = "Chào cả nhà, hôm nay em giới thiệu kem chống nắng.",
    link: str | None = "https://example.com/kem-x",
    type_line: str | None = None,
) -> list[Block]:
    """Blocks of one valid product; `None` leaves a section out (an empty sequence for `specs`, `faq`, `promotions`)."""
    blocks: list[Block] = [("h1", name)]
    if type_line is None:
        blocks.append(("p", f"Loại: {kind}"))
    elif type_line:
        blocks.append(("p", type_line))
    if price is not None or variants is not None:
        blocks.append(("h2", "Giá"))
        if price is not None:
            blocks.append(("p", price))
        if variants is not None:
            blocks.append(("table", [["Phân loại", "Giá"], *[[v, p] for v, p in variants]]))
    if description is not None:
        # A "\n" starts a new paragraph, so a test can write a section with several paragraphs.
        blocks += [("h2", "Mô tả"), *(("p", line) for line in description.split("\n"))]
    if specs:
        blocks.append(("h2", "Thông số"))
        blocks += [("p", s) for s in specs]
    if faq:
        blocks.append(("h2", "Câu hỏi thường gặp"))
        for q, a in faq:
            blocks += [("p", f"H: {q}"), ("p", f"Đ: {a}")]
    if promotions:
        blocks.append(("h2", "Khuyến mãi"))
        blocks += [("p", p) for p in promotions]
    if forbidden is not None:
        blocks.append(("h2", "Khẳng định bị cấm"))
        blocks += [("p", f) for f in forbidden] if forbidden else [("p", "Không có")]
    if intro is not None:
        blocks += [("h2", "Bài giới thiệu"), *(("p", line) for line in intro.split("\n"))]
    if link is not None:
        blocks += [("h2", "Link"), ("p", link)]
    return blocks


def valid_blocks() -> list[Block]:
    """Valid file: 1 main product and 2 secondary products; the main product has a variant table."""
    return [
        ("p", "Mẫu nội dung sản phẩm (ghi chú cho người soạn, hệ thống bỏ qua)"),
        *product_blocks(
            "Kem chống nắng X",
            "chính",
            price=None,
            variants=[("50 ml", "250.000đ"), ("100 ml", "420.000đ")],
            promotions=("Giảm 30.000đ cho đơn từ 500.000đ",),
        ),
        *product_blocks("Sữa rửa mặt Y", "phụ", price="159.000đ", forbidden=()),
        *product_blocks("Toner Z", "phụ", price="1.250.000 VND", link=None),
    ]


def valid_docx() -> bytes:
    return build_docx(valid_blocks())


SPARSE_PRODUCT_NAME = "Sữa rửa mặt Y"


def sparse_blocks() -> list[Block]:
    """Valid file whose secondary product has only the required sections.

    `SPARSE_PRODUCT_NAME` has no specs, FAQ or promotions, so `specs`, `faq` and `promotion` have no data for it
    (004 research R5). `price` cannot be the missing topic: the loader requires a price or a variant table.
    """
    return [
        *product_blocks("Kem chống nắng X", "chính"),
        *product_blocks(SPARSE_PRODUCT_NAME, "phụ", price="159.000đ", specs=(), faq=(), promotions=(), link=None),
    ]


def sparse_docx() -> bytes:
    return build_docx(sparse_blocks())
