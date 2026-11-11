"""Run the LLM + guard stage on its own (Article IV).

    uv run python -m ai_live.brain ask "<comment>" [--author Lan] [--content f.docx]
    uv run python -m ai_live.brain narrate --product ID --topic T [--content f.docx]   (feature 004)
    uv run python -m ai_live.brain narrate --topic opening|closing [--content f.docx]

Prints each sentence with the time since sending; a sentence blocked by the guard prints the reason (and, for `ask`,
the refusal sentence), then stops like the real pipeline. The guard is the live one, with the platform phrases.
Every sentence is cleaned with `clean_spoken` before the guard, as on the live path (ADR-031).
With `REPLY_ENGINE=chain` (feature 008) the chain is checked first with `preflight()` (one `GET /models` per provider);
a failed check prints which entry is wrong and why, never the key, and no `/chat/completions` call is made. The engine
is always closed at the end, also after an error.
Exit code 0 when done, 1 on a content, configuration, preflight, request or LLM error.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from ai_live.brain.factory import create_reply_engine
from ai_live.brain.guard import GuardConfigError, OutputGuard, load_platform_phrases, refusal_sentence
from ai_live.brain.prompt import addressee
from ai_live.brain.sanitize import clean_spoken
from ai_live.core.config import Settings
from ai_live.core.models import Comment, SegmentRequest, Topic
from ai_live.core.protocols import ReplyEngine, ReplyEngineError
from ai_live.director.segment_planner import topics_for
from ai_live.products.docx_loader import load_catalog_file
from ai_live.products.models import ContentLoadError, ProductCatalog


async def _ask(engine: ReplyEngine, guard: OutputGuard, comment: Comment, catalog: ProductCatalog) -> None:
    started = time.perf_counter()
    async for raw in engine.reply(comment, catalog):
        elapsed = time.perf_counter() - started
        # Cleaned before the guard, as on the live path (ADR-031); a symbols-only sentence is not spoken.
        sentence = clean_spoken(raw)
        if not sentence:
            continue
        result = guard.check(sentence, catalog)
        if not result.ok:
            print(f"[{elapsed:5.2f} s] BỊ CHẶN ({result.reason.value}: {result.detail}): {sentence}")
            print(f"[{elapsed:5.2f} s] {refusal_sentence(addressee(comment.author))}")
            return
        print(f"[{elapsed:5.2f} s] {sentence}")


async def _narrate(engine: ReplyEngine, guard: OutputGuard, request: SegmentRequest, catalog: ProductCatalog) -> None:
    started = time.perf_counter()
    async for raw in engine.narrate(request, catalog):
        elapsed = time.perf_counter() - started
        sentence = clean_spoken(raw)
        if not sentence:
            continue
        result = guard.check(sentence, catalog)
        if not result.ok:
            # No viewer to address in a scripted segment, so no refusal sentence: the segment just ends here.
            print(f"[{elapsed:5.2f} s] BỊ CHẶN ({result.reason.value}: {result.detail}): {sentence}")
            return
        print(f"[{elapsed:5.2f} s] {sentence}")


async def _session(engine: ReplyEngine, turn: Callable[[], Awaitable[None]]) -> None:
    """Preflight, one turn and close in one event loop: the chain's httpx client is bound to the loop it first ran on.

    The turn is a factory, not a coroutine, so a failed preflight leaves no coroutine that was never awaited.
    """
    from ai_live.brain.chain_engine import ChainReplyEngine  # lazy, like the factory: `fake` does not need it

    if not isinstance(engine, ChainReplyEngine):
        await turn()
        return
    try:
        # One `GET /models` before any `/chat/completions` call; a failure raises `config_error` (FR-011).
        await engine.preflight()
        await turn()
    finally:
        await engine.aclose()


def _segment_request(args: argparse.Namespace, catalog: ProductCatalog, settings: Settings) -> SegmentRequest | str:
    """The request to narrate, or a Vietnamese error message. Checked before the engine is built (data-model §5)."""
    topic = Topic(args.topic)
    product_id: str | None = args.product
    if not topic.has_product:
        if product_id is not None:
            return f"Chủ đề '{topic.value}' là của cả phiên live, không gắn sản phẩm: bỏ --product."
    else:
        if product_id is None:
            return f"Chủ đề '{topic.value}' cần --product (mã sản phẩm trong file nội dung)."
        product = next((p for p in catalog.products if p.id == product_id), None)
        if product is None:
            known = ", ".join(p.id for p in catalog.products)
            return f"Không có sản phẩm mã '{product_id}' trong file nội dung. Các mã hiện có: {known}"
        if topic not in topics_for(product):
            return f"Sản phẩm '{product.name}' không có dữ liệu cho chủ đề '{topic.value}' ({topic.label})."
    return SegmentRequest(
        segment_id=f"cli-{uuid.uuid4().hex[:12]}",
        topic=topic,
        product_id=product_id,
        min_sentences=settings.script_segment_min_sentences,
        max_sentences=settings.script_segment_max_sentences,
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m ai_live.brain")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="hỏi như một comment, in câu trả lời đã qua guard")
    ask.add_argument("text")
    ask.add_argument("--author", default="")
    ask.add_argument("--content", type=Path, default=None, help="file Word; mặc định PRODUCT_DATA_PATH")
    narrate = sub.add_parser("narrate", help="nói một phân đoạn kịch bản, in từng câu đã qua guard")
    narrate.add_argument("--topic", required=True, choices=[t.value for t in Topic])
    narrate.add_argument("--product", default=None, help="mã sản phẩm; bỏ trống với opening/closing")
    narrate.add_argument("--content", type=Path, default=None, help="file Word; mặc định PRODUCT_DATA_PATH")
    args = parser.parse_args(argv)

    settings = Settings()
    path: Path = args.content or settings.product_data_path
    if not path.is_file():
        print(f"Không tìm thấy file nội dung: {path}")
        return 1
    try:
        catalog = load_catalog_file(path, settings.content_max_bytes)
    except ContentLoadError as exc:
        print(f"File '{path.name}' có {len(exc.issues)} lỗi:")
        for issue in exc.issues:
            print(f"  - [{issue.code}] {issue.message}")
        return 1

    try:
        guard = OutputGuard(load_platform_phrases(settings.platform_phrases_path))
    except GuardConfigError as exc:
        print(f"Lỗi cấu hình guard: {exc}")
        return 1

    request: SegmentRequest | None = None
    if args.command == "narrate":
        checked = _segment_request(args, catalog, settings)
        if isinstance(checked, str):
            print(checked)
            return 1
        request = checked
    try:
        engine = create_reply_engine(settings)
        if request is not None:
            narrate_request = request
            asyncio.run(_session(engine, lambda: _narrate(engine, guard, narrate_request, catalog)))
        else:
            comment = Comment(id="cli", source="cli", author=args.author, text=args.text, received_at=time.monotonic())
            asyncio.run(_session(engine, lambda: _ask(engine, guard, comment, catalog)))
    except ReplyEngineError as exc:
        if exc.kind == "config_error":
            # Engine messages never carry the key (contracts/config.md §4), so they are safe to print as they are.
            print(f"Lỗi cấu hình LLM: {exc}")
        else:
            print(f"Lỗi LLM ({exc.kind}): {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
