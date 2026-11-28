"""Sinh `data/products/template.docx` (mẫu trống), `demo.docx` (dữ liệu hư cấu) và `coca.docx` (demo Coca-Cola).

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


# Coca-Cola set for the scene demo (013): matches the uploaded photos (main product the Tết gift case since ADR-096,
# a 6-bottle pack before, ADR-081). Names, sizes and labels follow the photos; prices, promotions and FAQ answers are
# demo values, not the brand's or any shop's real data. The ingredient and caution lines (ADR-088) follow the usual
# can label but are demo text too: TODO check them against the real label before showing the customer.
_COCA_INGREDIENTS = (
    "Thành phần: nước bão hòa CO2, đường mía, màu caramel, chất điều chỉnh độ acid, hương cola tự nhiên, caffeine"
)
_COCA_CAUTION = "Lưu ý: có đường và caffeine; ai cần hạn chế đường hoặc caffeine nên hỏi ý kiến bác sĩ trước khi uống"
COCA_PRODUCTS = [
    # ADR-096: the main product is the Tết gift case, the desk's centrepiece "gift box"; name, size and print follow
    # the photo already in the demo scene. It replaces the single 355 ml can of ADR-095.
    # Intro and description have several paragraphs: a `loop` show reads one of each per visit, in turn (FR-031,
    # 2026-11-28), so the main product, said every other block, does not repeat the same words for a long time.
    DemoProduct(
        name="Thùng 24 lon Coca-Cola Tết 320ml",
        kind="chính",
        price="235.000đ",
        description="\n".join(
            [
                "Một thùng có 24 lon Coca-Cola vị nguyên bản, mỗi lon 320 ml. Uống lạnh là ngon nhất nha cả nhà.",
                "Mặt thùng có sẵn dòng Chúc và dòng Từ để mình tự ghi người nhận, người gửi, ghi thêm lời chúc là "
                "thành món quà biếu Tết tươm tất liền ạ.",
                "Bao bì là thùng giấy in hình Tết đỏ rực, mang đi biếu ông bà, họ hàng hay bạn bè đều đẹp ạ.",
                "Mua về để nhà đãi khách mấy ngày Tết cũng tiện lắm, khách tới thì khui vài lon ướp lạnh ra mời "
                "là xong ạ.",
            ]
        ),
        specs=[
            "Quy cách: thùng 24 lon, mỗi lon 320 ml",
            "Hương vị: Coca-Cola vị nguyên bản",
            "Bao bì: thùng giấy in hình Tết",
            "Ngon nhất khi uống lạnh",
            _COCA_INGREDIENTS,
            _COCA_CAUTION,
        ],
        faq=[
            ("Thùng có mấy lon shop?", "Dạ một thùng có 24 lon, mỗi lon 320 ml ạ."),
            ("Có ghi lời chúc lên thùng được không?", "Dạ mặt thùng có sẵn dòng Chúc và Từ để mình tự ghi ạ."),
        ],
        forbidden=["tốt cho sức khỏe", "giúp giảm cân", "giải độc cơ thể", "mang lại may mắn"],
        intro="\n".join(
            [
                "Cả nhà ơi, Tết tới nơi rồi, thùng Coca-Cola 24 lon bao bì Tết đỏ rực đang nằm ngay trước mặt em "
                'đây nè. Mặt thùng in chữ "Tết phát lộc, năm phát tài", nhìn là thấy không khí Tết liền ạ.',
                "Anh chị nào đang tính quà biếu Tết thì nhìn món chính hôm nay nè, thùng Coca-Cola 24 lon 320 ml "
                "bao bì Tết.",
                "Nhà mình mấy ngày Tết hay có khách tới chơi thì để sẵn một thùng Coca-Cola 24 lon này là có nước "
                "mời khách liền nha cả nhà.",
                "Quay lại với thùng Coca-Cola Tết 24 lon màu đỏ ngay trên bàn nè cả nhà.",
            ]
        ),
    ),
    DemoProduct(
        name="Coca-Cola chai 500ml",
        kind="phụ",
        price="12.000đ",
        description="\n".join(
            [
                "Chai nhựa 500 ml có nắp vặn, uống chưa hết thì vặn nắp lại, bỏ túi mang đi học, đi làm, đi chơi "
                "đều tiện.",
                "Vẫn là vị Coca-Cola nguyên bản quen thuộc, ướp lạnh uống là ngon nhất ạ.",
                "Chai nắp vặn nên bỏ vào ba lô hay túi xách cũng gọn, khát lúc nào mở ra uống lúc đó nha.",
            ]
        ),
        specs=[
            "Dung tích: 500 ml",
            "Bao bì: chai nhựa, nắp vặn",
            "Ngon nhất khi uống lạnh",
            _COCA_INGREDIENTS,
            _COCA_CAUTION,
        ],
        faq=[("Chai này bao nhiêu ml?", "Dạ chai 500 ml ạ.")],
        forbidden=["tốt cho sức khỏe", "giúp giảm cân", "giải độc cơ thể"],
        intro="\n".join(
            [
                "Còn anh chị nào hay mang nước theo người thì xem chai Coca-Cola 500 ml này nè cả nhà.",
                "Bên cạnh thùng quà Tết là chai Coca-Cola 500 ml nắp vặn, nhỏ gọn dễ mang theo nè cả nhà.",
                "Anh chị cần một chai Coca-Cola mang theo đi làm, đi học thì có chai nhựa 500 ml này ạ.",
            ]
        ),
    ),
    DemoProduct(
        name="Coca-Cola Zero chai thủy tinh 237ml",
        kind="phụ",
        price="15.000đ",
        description="\n".join(
            [
                "Chai thủy tinh nhỏ gọn 237 ml, nhãn đen dễ nhận ra, là loại không đường, dùng chất tạo ngọt thay "
                "cho đường.",
                "Em lưu ý giúp cả nhà là Zero vẫn có caffeine và có chứa phenylalanin, ai cần hạn chế thì hỏi ý kiến "
                "bác sĩ trước khi uống nha.",
                "Zero không dùng đường mà dùng chất tạo ngọt aspartame và acesulfame kali thay cho đường ạ.",
            ]
        ),
        specs=[
            "Dung tích: 237 ml",
            "Bao bì: chai thủy tinh",
            "Không đường",
            (
                "Thành phần: nước bão hòa CO2, màu caramel, chất điều chỉnh độ acid, chất tạo ngọt aspartame và "
                "acesulfame kali, hương cola tự nhiên, chất bảo quản, caffeine"
            ),
            (
                "Lưu ý: có caffeine và có chứa phenylalanin; ai cần hạn chế caffeine hoặc phenylalanin nên hỏi ý kiến "
                "bác sĩ trước khi uống"
            ),
        ],
        faq=[("Zero là không đường hả shop?", "Dạ đúng rồi ạ, Coca-Cola Zero là loại không đường ạ.")],
        forbidden=["tốt cho sức khỏe", "giúp giảm cân", "an toàn cho người tiểu đường", "không ảnh hưởng đường huyết"],
        intro="\n".join(
            [
                "Anh chị nào thích vị Coca-Cola mà muốn chọn loại không đường thì nhìn qua đây nè, Coca-Cola Zero "
                "chai thủy tinh 237 ml.",
                "Chai nhãn đen nhỏ nhỏ trên bàn là Coca-Cola Zero chai thủy tinh 237 ml đó cả nhà.",
                "Nhà mình ai thích loại không đường thì để ý Coca-Cola Zero chai thủy tinh 237 ml nha.",
            ]
        ),
    ),
    # Off the desk since ADR-096 (three products fit beside the gift case); the host still presents it.
    DemoProduct(
        name="Lốc 6 chai Coca-Cola 355ml",
        kind="phụ",
        price="95.000đ",
        description="\n".join(
            [
                "Mỗi lốc có 6 chai thủy tinh Coca-Cola vị nguyên bản, mỗi chai 355 ml. Để sẵn trong tủ lạnh cho cả "
                "nhà, xách đi dã ngoại hay đãi bạn bè đều hợp.",
                "Hộp giấy có quai xách nên mang đi đâu cũng gọn tay, hạn sử dụng in ngay trên cổ chai, mình nhìn là "
                "thấy liền ạ.",
                "Lốc chai này mình cất nơi khô ráo, thoáng mát, tránh ánh nắng trực tiếp, trước khi uống ướp lạnh là "
                "ngon nhất nha.",
            ]
        ),
        specs=[
            "Quy cách: lốc 6 chai thủy tinh, mỗi chai 355 ml",
            "Hương vị: Coca-Cola vị nguyên bản",
            "Loại: nước giải khát có ga",
            "Bảo quản: nơi khô ráo, thoáng mát, tránh ánh nắng trực tiếp; ngon nhất khi uống lạnh",
            "Hạn sử dụng: in trên cổ chai",
            _COCA_INGREDIENTS,
            _COCA_CAUTION,
        ],
        faq=[
            ("Lốc có mấy chai shop?", "Dạ một lốc có 6 chai thủy tinh, mỗi chai 355 ml ạ."),
            (
                "Có bán lẻ từng chai không?",
                "Dạ món này shop bán theo lốc 6 chai ạ, mình hỏi shop nếu cần số lượng khác nha.",
            ),
        ],
        forbidden=[
            "tốt cho sức khỏe",
            "giúp giảm cân",
            "giải độc cơ thể",
            "chữa đầy bụng",
            "uống thay nước lọc",
            "phù hợp cho trẻ nhỏ",
        ],
        intro="\n".join(
            [
                "Còn đây là lốc 6 chai Coca-Cola thủy tinh 355 ml, đựng trong hộp giấy có quai xách, cầm rất gọn tay "
                "nè cả nhà.",
                "Anh chị thích uống Coca-Cola chai thủy tinh thì shop có lốc 6 chai 355 ml vị nguyên bản nha.",
                "Đi chơi cuối tuần mà muốn mang theo nước cho cả nhóm thì xem lốc 6 chai Coca-Cola 355 ml nè cả nhà.",
            ]
        ),
        link="https://example.com/coca-cola-loc-6-chai",
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
    for line in p.description.split("\n"):
        doc.add_paragraph(line)
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
    for line in p.intro.split("\n"):
        doc.add_paragraph(line)
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


def build_coca(path: Path) -> None:
    doc = Document()
    doc.add_paragraph(
        "Nội dung demo Coca-Cola: tên và quy cách theo ảnh sản phẩm; giá là số DEMO, không phải giá thật; bản demo "
        "không có khuyến mãi. Phần chữ trước tiêu đề sản phẩm đầu tiên bị hệ thống bỏ qua."
    )
    for p in COCA_PRODUCTS:
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
        "Bài giới thiệu và Mô tả viết được nhiều đoạn (mỗi đoạn một dòng). Khi không ai bình luận, mỗi lượt host đọc "
        "một đoạn của mỗi mục, lần lượt rồi quay vòng: viết nhiều đoạn khác nhau để host bớt nói lặp.",
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
    build_coca(OUT_DIR / "coca.docx")
    print(f"Đã ghi {OUT_DIR / 'template.docx'}, {OUT_DIR / 'demo.docx'} và {OUT_DIR / 'coca.docx'}")


if __name__ == "__main__":
    main()
