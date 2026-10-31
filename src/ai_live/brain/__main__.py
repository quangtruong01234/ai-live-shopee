"""Chạy riêng khâu LLM + guard (Điều IV).

    uv run python -m ai_live.brain ask "<comment>" [--author Lan] [--content f.docx]

In từng câu kèm thời gian từ lúc gửi; câu bị guard chặn thì in lý do, câu từ chối, rồi dừng như pipeline thật.
Thoát mã 0 khi chạy xong, 1 khi lỗi nội dung, cấu hình hoặc lỗi LLM.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from ai_live.brain.factory import create_reply_engine
from ai_live.brain.guard import OutputGuard, refusal_sentence
from ai_live.brain.prompt import addressee
from ai_live.core.config import Settings
from ai_live.core.models import Comment
from ai_live.core.protocols import ReplyEngine, ReplyEngineError
from ai_live.products.docx_loader import load_catalog_file
from ai_live.products.models import ContentLoadError, ProductCatalog


async def _ask(engine: ReplyEngine, comment: Comment, catalog: ProductCatalog) -> None:
    guard = OutputGuard()
    started = time.perf_counter()
    async for sentence in engine.reply(comment, catalog):
        elapsed = time.perf_counter() - started
        result = guard.check(sentence, catalog)
        if not result.ok:
            print(f"[{elapsed:5.2f} s] BỊ CHẶN ({result.reason.value}: {result.detail}): {sentence}")
            print(f"[{elapsed:5.2f} s] {refusal_sentence(addressee(comment.author))}")
            return
        print(f"[{elapsed:5.2f} s] {sentence}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m ai_live.brain")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="hỏi như một comment, in câu trả lời đã qua guard")
    ask.add_argument("text")
    ask.add_argument("--author", default="")
    ask.add_argument("--content", type=Path, default=None, help="file Word; mặc định PRODUCT_DATA_PATH")
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

    comment = Comment(id="cli", source="cli", author=args.author, text=args.text, received_at=time.monotonic())
    try:
        engine = create_reply_engine(settings)
        asyncio.run(_ask(engine, comment, catalog))
    except ReplyEngineError as exc:
        print(f"Lỗi LLM ({exc.kind}): {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
