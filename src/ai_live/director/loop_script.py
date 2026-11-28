"""The fixed passage a `loop` show repeats while nobody comments (ADR-088).

Pure: no asyncio and no I/O. Every line comes from the content file (intro, description, price, promotions) or is a
fixed invite to ask the host for advice, so nothing here can invent a fact, and the guard still checks each line.
The host never asks itself a question and answers it: the FAQ pairs are kept for real comments.
"""

from __future__ import annotations

from ai_live.brain.prompt import format_price
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.core.text import match_form
from ai_live.products.models import Product, ProductCatalog

# Spec keys that mean the file lists what the product is made of; only then does an invite mention ingredients.
INGREDIENT_KEYS = ("thanh phan",)  # match form: no diacritics, lower case

OPENING_LINES = (
    "Chào anh chị đã ghé phòng live của shop nha.",
    "Em là trợ lý AI của shop, anh chị cần tư vấn gì cứ bình luận hỏi em, em trả lời liền nè.",
)

# Each invite names a kind of question the reply prompt knows how to answer (budget, ingredients, comparing).
_BUDGET_INVITE = (
    "Anh chị đang có ngân sách bao nhiêu, cứ bình luận cho em biết để em tư vấn chọn loại vừa túi tiền nha."
)
_INGREDIENT_INVITE = (
    "Anh chị muốn biết thành phần có hợp với thể trạng của mình không, cứ bình luận hỏi em, em đọc kỹ cho nghe nè."
)
_COMPARE_INVITE = "Anh chị còn phân vân không biết chọn loại nào, cứ hỏi em, em so sánh giúp liền nha."
_GENERAL_INVITE = "Anh chị muốn hỏi giá, khuyến mãi hay cách bảo quản, cứ để lại bình luận, em trả lời ngay nha."
# Without any promotion in the file, inviting questions about one only earns a "no information" reply.
_GENERAL_INVITE_NO_PROMO = "Anh chị muốn hỏi giá, quy cách hay cách bảo quản, cứ để lại bình luận, em trả lời ngay nha."


def _sentences(text: str) -> list[str]:
    splitter = SentenceSplitter()
    return [*splitter.feed(text or ""), *splitter.flush()]


def has_ingredients(product: Product) -> bool:
    return any(match_form(key).strip() in INGREDIENT_KEYS for key, _ in product.specs)


def invite_lines(catalog: ProductCatalog) -> tuple[str, ...]:
    """Invites that fit this catalog: no ingredient invite without ingredient data, no comparing with one product."""
    lines = [_BUDGET_INVITE]
    if any(has_ingredients(p) for p in catalog.products):
        lines.append(_INGREDIENT_INVITE)
    if len(catalog.products) > 1:
        lines.append(_COMPARE_INVITE)
    lines.append(_GENERAL_INVITE if any(p.promotions for p in catalog.products) else _GENERAL_INVITE_NO_PROMO)
    return tuple(lines)


def _names(catalog: ProductCatalog) -> str:
    names = [p.name for p in sorted(catalog.products, key=lambda p: not p.is_primary)]
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} và {names[-1]}"


def opening_passage(catalog: ProductCatalog) -> list[str]:
    """Greeting, what the shop sells today, and who to ask: said once when the show starts."""
    return [OPENING_LINES[0], f"Hôm nay shop có {_names(catalog)} nè.", OPENING_LINES[1]]


# Fixed wordings of the price sentence, taken in turn so the same product does not say the same line every visit.
# Name and price always come from the file; `{price}` is one price or "từ X đến Y tùy phân loại".
PRICE_TEMPLATES = (
    "{name} giá {price} nha anh chị.",
    "Giá của {name} là {price} ạ.",
    "{name} shop để giá {price} nha cả nhà.",
)


def _price_line(product: Product, turn: int = 0) -> str:
    low, high = product.price_range
    if product.variants and low != high:
        price = f"từ {format_price(low)} đến {format_price(high)} tùy phân loại"
    else:
        price = format_price(low)
    return PRICE_TEMPLATES[turn % len(PRICE_TEMPLATES)].format(name=product.name, price=price)


def _paragraph(text: str, turn: int) -> str:
    """The `turn`-th paragraph of a section (one per line), wrapping around; the whole text when it has one."""
    paragraphs = [line for line in (text or "").split("\n") if line.strip()]
    return paragraphs[turn % len(paragraphs)] if paragraphs else ""


def _promotion_line(promotion: str) -> str:
    text = promotion.strip().rstrip(".!")
    if not text:
        return ""
    return f"Shop đang có khuyến mãi {text[0].lower()}{text[1:]} nha."


def product_passage(product: Product, invite: str, turn: int = 0) -> list[str]:
    """One product's block for its `turn`-th visit: intro, description, price, promotions, then one invite.

    A section written as several paragraphs gives one paragraph per visit, in order and wrapping around, so the loop
    does not read the same block every time (FR-031, 2026-11-28).
    """
    lines = [
        *_sentences(_paragraph(product.intro, turn)),
        *_sentences(_paragraph(product.description, turn)),
        _price_line(product, turn),
    ]
    lines += [line for promo in product.promotions if (line := _promotion_line(promo))]
    lines.append(invite)
    return lines
