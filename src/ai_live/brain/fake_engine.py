"""Fake ReplyEngine: runs the pipeline and tests without network or API key (Article IV, research R11).

The default reply is grounded in the product data, so a demo with `REPLY_ENGINE=fake` still reads the right price.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping, Sequence

from ai_live.brain.prompt import addressee, format_price
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.core.models import Comment, SegmentRequest, Topic
from ai_live.core.protocols import ReplyEngineError
from ai_live.core.text import match_form
from ai_live.products.models import ProductCatalog

AnswerFn = Callable[[Comment, ProductCatalog], str]
NarrateScript = Mapping[tuple[str | None, Topic], Sequence[str]]

_PRICE_TOKENS = {"gia", "bn"}
_PRICE_PHRASES = ("bao nhieu", "nhieu tien")


def _asks_price(text: str) -> bool:
    form = match_form(text)
    return bool(_PRICE_TOKENS & set(re.findall(r"\w+", form))) or any(p in form for p in _PRICE_PHRASES)


def default_answer(comment: Comment, catalog: ProductCatalog) -> str:
    """Price questions get the main product's price; anything else gets the refusal, since a fake cannot understand."""
    who = addressee(comment.author)
    product = catalog.primary
    if _asks_price(comment.text):
        if product.variants:
            prices = ", ".join(f"loại {v.name} giá {format_price(v.price)}" for v in product.variants)
            return f"Dạ chào {who} nha. {product.name} có {prices}. {who[0].upper()}{who[1:]} chọn loại nào ạ?"
        return f"Dạ chào {who} nha. {product.name} giá {format_price(product.price_range[0])} ạ."
    return f"Dạ phần này em chưa có thông tin, {who} nhắn shop giúp em nha."


class FakeReplyEngine:
    """`reply()` speaks `answer` (or `default_answer`); `narrate()` speaks `script` (or numbered default lines).

    The two paths have separate knobs: `first_delay_s` / `error` / `error_after_sentences` drive `reply()` exactly as
    in 001, while `first_sentence_delay_s` / `delay_s` / `fail_next()` drive `narrate()` only.
    """

    def __init__(
        self,
        answer: str | AnswerFn | None = None,
        *,
        first_delay_s: float = 0.0,
        delta_chars: int = 12,
        error: ReplyEngineError | None = None,
        error_after_sentences: int = 0,
        script: NarrateScript | None = None,
        first_sentence_delay_s: float = 0.0,
        delay_s: float = 0.0,
    ) -> None:
        self.answer = answer
        self.first_delay_s = first_delay_s
        self.delta_chars = delta_chars
        self.error = error
        self.error_after_sentences = error_after_sentences
        self.script: dict[tuple[str | None, Topic], tuple[str, ...]] = {
            key: tuple(lines) for key, lines in (script or {}).items()
        }
        self.first_sentence_delay_s = first_sentence_delay_s
        self.delay_s = delay_s
        self.narrate_requests: list[SegmentRequest] = []
        self._sentence_no = 0
        self._pending_failures: deque[str] = deque()

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
        # Small deltas like a real LLM stream, so the splitter is exercised across delta boundaries.
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

    def fail_next(self, kind: str, count: int = 1) -> None:
        """Make the next `count` `narrate()` calls raise `ReplyEngineError(kind)` before any sentence.

        Calls add up in order: `fail_next("api_error", 1); fail_next("rate_limited", 1)` fails twice, api_error first.
        """
        if count < 1:
            raise ValueError(f"fail_next needs count >= 1, got {count}")
        self._pending_failures.extend([kind] * count)

    def _default_lines(self, request: SegmentRequest, catalog: ProductCatalog) -> list[str]:
        # A rising per-engine counter keeps every line unique, so later dedup checks never trip on the fake itself.
        # Show topics have no product and stay shop-neutral; no number but the counter, so the guard passes them.
        name = None
        if request.product_id is not None:
            name = next((p.name for p in catalog.products if p.id == request.product_id), request.product_id)
        lines = []
        for _ in range(request.min_sentences):
            self._sentence_no += 1
            n = self._sentence_no
            lines.append(f"Câu {n} về {request.topic.label} của {name}." if name else f"Câu {n} {request.topic.label}.")
        return lines

    async def narrate(self, request: SegmentRequest, catalog: ProductCatalog) -> AsyncIterator[str]:
        self.narrate_requests.append(request)
        if self._pending_failures:
            raise ReplyEngineError(self._pending_failures.popleft(), "giả lập lỗi narrate")
        scripted = self.script.get((request.product_id, request.topic))
        lines = list(scripted) if scripted is not None else self._default_lines(request, catalog)
        for i, line in enumerate(lines):
            delay = self.first_sentence_delay_s if i == 0 else self.delay_s
            # sleep(0) still yields to the loop, so a runner can cancel between sentences like with a real stream.
            await asyncio.sleep(delay)
            yield line
