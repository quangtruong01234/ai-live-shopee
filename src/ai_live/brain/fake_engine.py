"""ReplyEngine giả: chạy pipeline và test không cần mạng hay API key (Điều IV, research R11).

Câu trả lời mặc định bám dữ liệu sản phẩm để demo bằng `REPLY_ENGINE=fake` vẫn nói đúng giá.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable

from ai_live.brain.prompt import addressee, format_price
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.core.models import Comment
from ai_live.core.protocols import ReplyEngineError
from ai_live.core.text import match_form
from ai_live.products.models import ProductCatalog

AnswerFn = Callable[[Comment, ProductCatalog], str]

_PRICE_TOKENS = {"gia", "bn"}
_PRICE_PHRASES = ("bao nhieu", "nhieu tien")


def _asks_price(text: str) -> bool:
    form = match_form(text)
    return bool(_PRICE_TOKENS & set(re.findall(r"\w+", form))) or any(p in form for p in _PRICE_PHRASES)


def default_answer(comment: Comment, catalog: ProductCatalog) -> str:
    """Hỏi giá thì đọc giá sản phẩm chính; còn lại nói câu từ chối, vì engine giả không hiểu được câu hỏi."""
    who = addressee(comment.author)
    product = catalog.primary
    if _asks_price(comment.text):
        if product.variants:
            prices = ", ".join(f"loại {v.name} giá {format_price(v.price)}" for v in product.variants)
            return f"Dạ chào {who} nha. {product.name} có {prices}. {who[0].upper()}{who[1:]} chọn loại nào ạ?"
        return f"Dạ chào {who} nha. {product.name} giá {format_price(product.price_range[0])} ạ."
    return f"Dạ phần này em chưa có thông tin, {who} nhắn shop giúp em nha."


class FakeReplyEngine:
    def __init__(
        self,
        answer: str | AnswerFn | None = None,
        *,
        first_delay_s: float = 0.0,
        delta_chars: int = 12,
        error: ReplyEngineError | None = None,
        error_after_sentences: int = 0,
    ) -> None:
        self.answer = answer
        self.first_delay_s = first_delay_s
        self.delta_chars = delta_chars
        self.error = error
        self.error_after_sentences = error_after_sentences

    def _text(self, comment: Comment, catalog: ProductCatalog) -> str:
        if self.answer is None:
            return default_answer(comment, catalog)
        if isinstance(self.answer, str):
            return self.answer
        return self.answer(comment, catalog)

    async def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]:
        if self.first_delay_s:
            await asyncio.sleep(self.first_delay_s)
        text = self._text(comment, catalog)
        splitter = SentenceSplitter()
        emitted = 0
        # Cắt thành delta nhỏ như LLM stream thật, để splitter được thử ở ranh giới giữa các delta.
        for i in range(0, len(text), self.delta_chars):
            for sentence in splitter.feed(text[i : i + self.delta_chars]):
                if self.error is not None and emitted >= self.error_after_sentences:
                    raise self.error
                emitted += 1
                yield sentence
            await asyncio.sleep(0)
        for sentence in splitter.flush():
            if self.error is not None and emitted >= self.error_after_sentences:
                raise self.error
            emitted += 1
            yield sentence
        if self.error is not None:
            raise self.error
