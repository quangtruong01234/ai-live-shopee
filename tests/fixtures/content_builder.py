"""Dựng file nội dung `.docx` trong bộ nhớ cho test (contracts/content-template.md).

Mỗi file được mô tả bằng danh sách khối `(loại, nội dung)`:
- `("h1", text)`, `("h2", text)`: tiêu đề theo style Heading 1/2.
- `("p", text)`: đoạn văn thường.
- `("table", [[ô, ô], ...])`: bảng, dòng đầu là tiêu đề.
Cách mô tả bằng khối giúp tạo được cả file hợp lệ lẫn từng biến thể lỗi mà không cần mẫu riêng cho mỗi case.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence

from docx import Document

Block = tuple[str, object]


def build_docx(blocks: Iterable[Block]) -> bytes:
    """Ghi danh sách khối thành bytes của một file `.docx`."""
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
    """Khối của một sản phẩm hợp lệ; truyền `None` cho một mục để bỏ hẳn mục đó."""
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
        blocks += [("h2", "Mô tả"), ("p", description)]
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
        blocks += [("h2", "Bài giới thiệu"), ("p", intro)]
    if link is not None:
        blocks += [("h2", "Link"), ("p", link)]
    return blocks


def valid_blocks() -> list[Block]:
    """File hợp lệ: 1 sản phẩm chính, 2 sản phẩm phụ, trong đó 1 sản phẩm có bảng phân loại."""
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
