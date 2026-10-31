"""Đọc và kiểm tra file Word nội dung theo mẫu cố định (contracts/content-template.md §1, research R1, R2).

Không đọc Word tự do: chỉ nhận cấu trúc Heading 1 (sản phẩm) / Heading 2 (mục). Gom mọi lỗi rồi báo một lần.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from ai_live.core.text import extract_numbers, match_form, normalize_text
from ai_live.products.models import ContentIssue, ContentLoadError, Product, ProductCatalog, Variant

MAX_SECONDARY = 3

SECTION_PRICE = "Giá"
SECTION_DESCRIPTION = "Mô tả"
SECTION_SPECS = "Thông số"
SECTION_FAQ = "Câu hỏi thường gặp"
SECTION_PROMOTIONS = "Khuyến mãi"
SECTION_FORBIDDEN = "Khẳng định bị cấm"
SECTION_INTRO = "Bài giới thiệu"
SECTION_LINK = "Link"

ALL_SECTIONS = (
    SECTION_PRICE,
    SECTION_DESCRIPTION,
    SECTION_SPECS,
    SECTION_FAQ,
    SECTION_PROMOTIONS,
    SECTION_FORBIDDEN,
    SECTION_INTRO,
    SECTION_LINK,
)
REQUIRED_SECTIONS = (SECTION_PRICE, SECTION_DESCRIPTION, SECTION_FORBIDDEN, SECTION_INTRO)
_SECTION_BY_FORM = {match_form(name): name for name in ALL_SECTIONS}

_TYPE_LINE = re.compile(r"loai\s*:\s*(chinh|phu)")
# Giá chặt hơn hàm trích số tiền: file nội dung là nguồn sự thật nên chỉ nhận dạng không mơ hồ
# (không "k", "triệu", số thập phân).
_PRICE = re.compile(r"(\d{1,3}(?:([.,])\d{3})(?:\2\d{3})*|\d+)\s*(?:đ|₫|vnđ|vnd)?", re.IGNORECASE)
_FAQ_PREFIX = re.compile(r"^(h|d)\s*:\s*", re.IGNORECASE)
_NONE_FORMS = {"khong co", "khong"}

Block = Paragraph | Table


@dataclass
class _RawProduct:
    name: str
    type_value: str | None = None
    sections: dict[str, list[Block]] = field(default_factory=dict)


def _heading_level(paragraph: Paragraph) -> int | None:
    style = paragraph.style
    if style is None:
        return None
    for candidate in (style.name or "", style.style_id or ""):
        compact = candidate.replace(" ", "").lower()
        if compact == "heading1":
            return 1
        if compact == "heading2":
            return 2
    return None


def _lines(blocks: list[Block]) -> list[str]:
    """Các dòng chữ không rỗng của một mục; bảng ngoài mục Giá/Thông số được đọc thành dòng 'ô | ô'."""
    out: list[str] = []
    for block in blocks:
        if isinstance(block, Paragraph):
            text = normalize_text(block.text)
            if text:
                out.append(text)
        else:
            for row in block.rows:
                cells = [normalize_text(c.text) for c in row.cells]
                if any(cells):
                    out.append(" | ".join(cells))
    return out


def _table_rows(table: Table) -> list[list[str]]:
    return [[normalize_text(c.text) for c in row.cells] for row in table.rows]


def parse_price(raw: str) -> int | None:
    """Trả giá VND nếu `raw` đúng dạng giá hợp lệ của file nội dung, ngược lại `None`."""
    m = _PRICE.fullmatch(raw.strip())
    if not m:
        return None
    value = int(re.sub(r"[.,]", "", m.group(1)))
    return value if value > 0 else None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", match_form(name)).strip("-")


class _Checker:
    def __init__(self) -> None:
        self.issues: list[ContentIssue] = []

    def add(self, code: str, message: str, product: str | None = None, section: str | None = None) -> None:
        self.issues.append(ContentIssue(code=code, message=message, product=product, section=section))

    def at(self, code: str, product: str, section: str, detail: str) -> None:
        self.add(code, f"Sản phẩm '{product}', mục {section}: {detail}", product, section)


def _split_products(doc_blocks: list[Block], check: _Checker) -> list[_RawProduct]:
    products: list[_RawProduct] = []
    current: _RawProduct | None = None
    section: str | None = None  # None: đoạn giữa Heading 1 và Heading 2 đầu tiên
    skip_section = False
    for block in doc_blocks:
        level = _heading_level(block) if isinstance(block, Paragraph) else None
        if level is not None and not normalize_text(block.text):
            continue  # tiêu đề trống (thường do bấm Enter thừa trong Word) không mở sản phẩm hay mục mới
        if level == 1:
            current = _RawProduct(name=normalize_text(block.text))
            products.append(current)
            section, skip_section = None, False
            continue
        if current is None:
            continue  # phần mở đầu cho người soạn, bỏ qua
        if level == 2:
            raw_title = normalize_text(block.text)
            name = _SECTION_BY_FORM.get(match_form(raw_title))
            if name is None:
                valid = ", ".join(ALL_SECTIONS)
                check.add(
                    "unknown_section",
                    f"Sản phẩm '{current.name}': không biết mục '{raw_title}' (các mục hợp lệ: {valid})",
                    current.name,
                    raw_title,
                )
                skip_section = True
            elif name in current.sections:
                check.add(
                    "duplicate_section",
                    f"Sản phẩm '{current.name}': mục {name} xuất hiện hai lần",
                    current.name,
                    name,
                )
                skip_section = True
            else:
                current.sections[name] = []
                section, skip_section = name, False
            continue
        if skip_section:
            continue
        if section is None:
            if current.type_value is None and isinstance(block, Paragraph) and normalize_text(block.text):
                m = _TYPE_LINE.fullmatch(match_form(block.text))
                current.type_value = m.group(1) if m else ""
            continue
        current.sections[section].append(block)
    return products


def _parse_price_section(name: str, blocks: list[Block], check: _Checker) -> tuple[int | None, tuple[Variant, ...]]:
    paragraphs = [b for b in blocks if isinstance(b, Paragraph) and normalize_text(b.text)]
    tables = [b for b in blocks if isinstance(b, Table)]
    if not paragraphs and not tables:
        check.at("empty_section", name, SECTION_PRICE, "đang trống")
        return None, ()
    if len(paragraphs) + len(tables) > 1:
        check.at("price_ambiguous", name, SECTION_PRICE, "chỉ ghi đúng một dòng giá hoặc một bảng phân loại")
        return None, ()
    if paragraphs:
        raw = normalize_text(paragraphs[0].text)
        price = parse_price(raw)
        if price is None:
            check.at("price_format", name, SECTION_PRICE, f"không đọc được '{raw}' (ghi dạng 250.000đ)")
        return price, ()

    rows = _table_rows(tables[0])
    header = [match_form(c) for c in rows[0]] if rows else []
    if any(len(r) != 2 for r in rows) or header != ["phan loai", "gia"]:
        check.at("price_table", name, SECTION_PRICE, "bảng phải có đúng 2 cột với tiêu đề 'Phân loại' và 'Giá'")
        return None, ()
    if len(rows) < 2:
        check.at("price_table", name, SECTION_PRICE, "bảng chưa có dòng phân loại nào")
        return None, ()
    variants: list[Variant] = []
    seen: set[str] = set()
    ok = True
    for variant_name, raw in rows[1:]:
        price = parse_price(raw)
        if not variant_name or price is None:
            ok = False
            shown = raw if variant_name else f"dòng phân loại trống tên, giá '{raw}'"
            check.at("price_format", name, SECTION_PRICE, f"không đọc được '{shown}' (ghi dạng 250.000đ)")
            continue
        key = match_form(variant_name)
        if key in seen:
            ok = False
            check.at("duplicate_variant", name, SECTION_PRICE, f"phân loại '{variant_name}' bị trùng")
            continue
        seen.add(key)
        variants.append(Variant(name=variant_name, price=price))
    return None, tuple(variants) if ok else ()


def _parse_faq(name: str, lines: list[str], check: _Checker) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    question: str | None = None
    for line in lines:
        m = _FAQ_PREFIX.match(match_form(line))
        kind = m.group(1).lower() if m else None
        body = line[m.end() :].strip() if m else line
        if kind == "h" and question is None:
            question = body
        elif kind == "d" and question is not None:
            pairs.append((question, body))
            question = None
        else:
            check.at("faq_format", name, SECTION_FAQ, f"dòng '{line}' không đúng cặp 'H: …' rồi 'Đ: …'")
            return ()
    if question is not None:
        check.at("faq_format", name, SECTION_FAQ, f"câu hỏi '{question}' chưa có dòng 'Đ: …' trả lời")
        return ()
    return tuple(pairs)


def _parse_specs(blocks: list[Block]) -> tuple[tuple[str, str], ...]:
    specs: list[tuple[str, str]] = []
    for block in blocks:
        if isinstance(block, Table):
            specs += [(r[0], r[1]) for r in _table_rows(block) if len(r) >= 2 and any(r)]
        else:
            text = normalize_text(block.text)
            if text:
                key, _, value = text.partition(":")
                specs.append((key.strip(), value.strip()))
    return tuple(specs)


def _build_product(raw: _RawProduct, check: _Checker) -> Product | None:
    name = raw.name
    before = len(check.issues)
    if not raw.type_value:
        check.add("missing_type", f"Sản phẩm '{name}': thiếu dòng 'Loại: chính' hoặc 'Loại: phụ'", name)
    for section in REQUIRED_SECTIONS:
        if section not in raw.sections:
            check.add("missing_section", f"Sản phẩm '{name}': thiếu mục {section}", name, section)

    lines = {s: _lines(b) for s, b in raw.sections.items()}
    for section in (SECTION_DESCRIPTION, SECTION_FORBIDDEN, SECTION_INTRO):
        if section in lines and not lines[section]:
            check.at("empty_section", name, section, "đang trống")

    price, variants = None, ()
    if SECTION_PRICE in raw.sections:
        price, variants = _parse_price_section(name, raw.sections[SECTION_PRICE], check)
    faq = _parse_faq(name, lines.get(SECTION_FAQ, []), check)
    forbidden = tuple(line for line in lines.get(SECTION_FORBIDDEN, []) if match_form(line) not in _NONE_FORMS)
    link_lines = lines.get(SECTION_LINK, [])

    if len(check.issues) > before:
        return None
    return Product(
        id=_slug(name),
        name=name,
        is_primary=raw.type_value == "chinh",
        price=price,
        variants=variants,
        description="\n".join(lines[SECTION_DESCRIPTION]),
        specs=_parse_specs(raw.sections.get(SECTION_SPECS, [])),
        faq=faq,
        promotions=tuple(lines.get(SECTION_PROMOTIONS, [])),
        forbidden_claims=forbidden,
        intro="\n".join(lines[SECTION_INTRO]),
        link=link_lines[0] if link_lines else None,
    )


def _known_amounts(products: list[Product]) -> frozenset[int]:
    """Mọi số trong nội dung (trừ link) cộng giá và khoảng giá.

    Guard chỉ cho host nói số tiền có trong tập này (research R8).
    """
    amounts: set[int] = set()
    for p in products:
        texts = [p.name, p.description, p.intro, *p.promotions, *p.forbidden_claims]
        texts += [f"{k}: {v}" for k, v in p.specs]
        texts += [f"{q} {a}" for q, a in p.faq]
        texts += [v.name for v in p.variants]
        for text in texts:
            amounts.update(extract_numbers(text))
        amounts.update(v.price for v in p.variants)
        if p.price is not None:
            amounts.add(p.price)
        amounts.update(p.price_range)
    return frozenset(amounts)


def load_catalog(data: bytes, source_name: str, max_bytes: int) -> ProductCatalog:
    """Đọc bytes `.docx` thành `ProductCatalog`; có lỗi thì ném `ContentLoadError` chứa đủ mọi lỗi."""
    if len(data) > max_bytes:
        size, limit = f"{len(data):,}".replace(",", "."), f"{max_bytes:,}".replace(",", ".")
        raise ContentLoadError([ContentIssue("too_large", f"File quá lớn ({size} byte, tối đa {limit} byte)")])
    not_docx = ContentIssue("not_docx", f"'{source_name}' không phải file Word .docx hợp lệ")
    if not data.startswith(b"PK\x03\x04"):
        raise ContentLoadError([not_docx])
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # file zip hỏng hoặc zip không phải Word: python-docx ném nhiều loại lỗi khác nhau
        raise ContentLoadError([not_docx]) from exc

    check = _Checker()
    raws = _split_products(list(doc.iter_inner_content()), check)
    if not raws:
        check.add("no_products", "File không có sản phẩm nào (cần tiêu đề Heading 1)")
        raise ContentLoadError(check.issues)

    seen: dict[str, str] = {}
    for raw in raws:
        key = match_form(raw.name)
        if key in seen:
            check.add("duplicate_product", f"Sản phẩm '{raw.name}' trùng tên với '{seen[key]}'", raw.name)
        else:
            seen[key] = raw.name

    products = [p for raw in raws if (p := _build_product(raw, check)) is not None]

    primary = sum(1 for r in raws if r.type_value == "chinh")
    secondary = sum(1 for r in raws if r.type_value == "phu")
    if primary != 1:
        check.add("primary_count", f"Cần đúng 1 sản phẩm chính, file có {primary}")
    if secondary > MAX_SECONDARY:
        check.add("secondary_count", f"Tối đa {MAX_SECONDARY} sản phẩm phụ, file có {secondary}")

    if check.issues:
        raise ContentLoadError(check.issues)

    return ProductCatalog(
        version=hashlib.sha256(data).hexdigest()[:12],
        source_name=Path(source_name).name,
        loaded_at=datetime.now(UTC),
        products=tuple(products),
        known_amounts=_known_amounts(products),
    )


def load_catalog_file(path: Path, max_bytes: int) -> ProductCatalog:
    return load_catalog(path.read_bytes(), path.name, max_bytes)
