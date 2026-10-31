"""Sinh `data/products/template.docx` (mẫu trống) và `data/products/demo.docx` (dữ liệu hư cấu).

Định dạng theo contracts/content-template.md. Chạy: `uv run python scripts/make_demo_content.py`.
Toàn bộ thương hiệu, giá và nội dung ở đây là bịa để demo, không phải dữ liệu khách.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from docx import Document

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "products"


@dataclass
class DemoProduct:
    name: str
    kind: str
    description: str
    intro: str
    forbidden: Sequence[str]
    price: str | None = None
    variants: Sequence[tuple[str, str]] = ()
    specs: Sequence[str] = ()
    faq: Sequence[tuple[str, str]] = ()
    promotions: Sequence[str] = ()
    link: str | None = None


DEMO_PRODUCTS = [
    DemoProduct(
        name="Kem chống nắng Mây Sáng SPF 50",
        kind="chính",
        variants=[("50 ml", "259.000đ"), ("100 ml", "439.000đ")],
        description=(
            "Kem chống nắng dạng sữa, kết cấu mỏng nhẹ, thấm nhanh, không để lại vệt trắng. "
            "Phù hợp dùng hằng ngày cho da thường, da dầu và da hỗn hợp."
        ),
        specs=[
            "Chỉ số chống nắng: SPF 50, PA++++",
            "Kết cấu: dạng sữa lỏng",
            "Loại da phù hợp: da thường, da dầu, da hỗn hợp",
            "Hạn sử dụng: 36 tháng kể từ ngày sản xuất",
            "Xuất xứ: Việt Nam",
        ],
        faq=[
            ("Da dầu dùng được không shop?", "Dạ được ạ, kem dạng sữa mỏng nhẹ, không gây bết dính."),
            ("Có cần tẩy trang không?", "Dạ nên làm sạch bằng nước tẩy trang hoặc sữa rửa mặt vào cuối ngày ạ."),
            ("Bôi lại sau bao lâu?", "Dạ nên bôi lại sau mỗi 2 đến 3 tiếng khi ở ngoài trời ạ."),
        ],
        promotions=[
            "Giảm 30.000đ cho đơn từ 500.000đ",
            "Mua chai 100 ml tặng 1 túi đựng mỹ phẩm",
        ],
        forbidden=["chữa khỏi mụn", "trị nám", "làm trắng da vĩnh viễn", "an toàn tuyệt đối cho bà bầu"],
        intro=(
            "Chào cả nhà, hôm nay em giới thiệu kem chống nắng Mây Sáng SPF 50. "
            "Kem dạng sữa mỏng nhẹ, thấm nhanh, có hai dung tích 50 ml và 100 ml cho cả nhà lựa chọn."
        ),
        link="https://example.com/may-sang-spf50",
    ),
    DemoProduct(
        name="Sữa rửa mặt Mây Sáng dịu nhẹ",
        kind="phụ",
        price="159.000đ",
        description="Sữa rửa mặt tạo bọt mịn, làm sạch nhẹ nhàng, không gây khô căng sau khi rửa.",
        specs=["Dung tích: 120 ml", "Độ pH: 5,5"],
        faq=[("Rửa mấy lần một ngày?", "Dạ dùng 2 lần mỗi ngày, sáng và tối ạ.")],
        forbidden=[],
        intro="Sữa rửa mặt Mây Sáng dịu nhẹ, bọt mịn, rửa xong da không bị khô căng ạ.",
    ),
    DemoProduct(
        name="Nước cân bằng Mây Sáng",
        kind="phụ",
        price="189.000đ",
        description="Nước cân bằng dạng lỏng, cấp ẩm nhẹ, giúp da sẵn sàng cho các bước dưỡng tiếp theo.",
        specs=["Dung tích: 150 ml", "Không chứa cồn"],
        promotions=["Mua kèm kem chống nắng Mây Sáng giảm 20.000đ"],
        forbidden=["se khít lỗ chân lông vĩnh viễn"],
        intro="Nước cân bằng Mây Sáng không chứa cồn, cấp ẩm nhẹ sau bước rửa mặt ạ.",
    ),
]


def _add_product(doc, p: DemoProduct) -> None:
    doc.add_heading(p.name, level=1)
    doc.add_paragraph(f"Loại: {p.kind}")
    doc.add_heading("Giá", level=2)
    if p.variants:
        table = doc.add_table(rows=len(p.variants) + 1, cols=2)
        table.style = "Table Grid"
        for r, (left, right) in enumerate([("Phân loại", "Giá"), *p.variants]):
            table.cell(r, 0).text = left
            table.cell(r, 1).text = right
    else:
        doc.add_paragraph(p.price or "")
    doc.add_heading("Mô tả", level=2)
    doc.add_paragraph(p.description)
    if p.specs:
        doc.add_heading("Thông số", level=2)
        for line in p.specs:
            doc.add_paragraph(line)
    if p.faq:
        doc.add_heading("Câu hỏi thường gặp", level=2)
        for q, a in p.faq:
            doc.add_paragraph(f"H: {q}")
            doc.add_paragraph(f"Đ: {a}")
    if p.promotions:
        doc.add_heading("Khuyến mãi", level=2)
        for line in p.promotions:
            doc.add_paragraph(line)
    doc.add_heading("Khẳng định bị cấm", level=2)
    for line in p.forbidden or ["Không có"]:
        doc.add_paragraph(line)
    doc.add_heading("Bài giới thiệu", level=2)
    doc.add_paragraph(p.intro)
    if p.link:
        doc.add_heading("Link", level=2)
        doc.add_paragraph(p.link)


def build_demo(path: Path) -> None:
    doc = Document()
    doc.add_paragraph(
        "Nội dung demo HƯ CẤU (thương hiệu, giá, khuyến mãi đều bịa). "
        "Phần chữ trước tiêu đề sản phẩm đầu tiên bị hệ thống bỏ qua."
    )
    for p in DEMO_PRODUCTS:
        _add_product(doc, p)
    doc.save(path)


def build_template(path: Path) -> None:
    doc = Document()
    for line in [
        "Mẫu nội dung sản phẩm. Phần chữ trước tiêu đề sản phẩm đầu tiên bị hệ thống bỏ qua.",
        "Mỗi sản phẩm bắt đầu bằng tiêu đề Heading 1 (tên sản phẩm), dòng ngay sau là 'Loại: chính' hoặc 'Loại: phụ'.",
        "Đúng 1 sản phẩm chính và tối đa 3 sản phẩm phụ. Các mục dùng Heading 2, giữ đúng tên mục như dưới.",
        "Mục bắt buộc: Giá, Mô tả, Khẳng định bị cấm, Bài giới thiệu.",
        "Mục tùy chọn: Thông số, Câu hỏi thường gặp, Khuyến mãi, Link.",
        "Giá ghi dạng 250.000đ (không ghi 250k). Có nhiều phân loại thì xóa dòng giá và dùng bảng 'Phân loại | Giá'.",
        "Kiểm file: uv run python -m ai_live.products validate <file.docx>",
    ]:
        doc.add_paragraph(line)
    _add_product(
        doc,
        DemoProduct(
            name="[Tên sản phẩm]",
            kind="chính",
            price="[giá, ví dụ 250.000đ]",
            description="[Mô tả ngắn: chất liệu, công dụng đã được xác nhận, đối tượng dùng]",
            specs=["[Tên thông số]: [giá trị]"],
            faq=[("[Câu hỏi khách hay hỏi]", "[Câu trả lời]")],
            promotions=["[Mỗi dòng một khuyến mãi]"],
            forbidden=["[Mỗi dòng một khẳng định host không được nói, hoặc ghi 'Không có']"],
            intro="[Bài giới thiệu sản phẩm cho host đọc khi không có comment]",
            link="[https://... (không bao giờ được đọc lên)]",
        ),
    )
    doc.save(path)


def main() -> None:
    # Console Windows mặc định cp1252 không in được chữ tiếng Việt.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build_template(OUT_DIR / "template.docx")
    build_demo(OUT_DIR / "demo.docx")
    print(f"Đã ghi {OUT_DIR / 'template.docx'} và {OUT_DIR / 'demo.docx'}")


if __name__ == "__main__":
    main()
