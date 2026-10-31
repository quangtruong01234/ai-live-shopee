"""Run the comment filter + classifier + queue on their own (Article IV).

    uv run python -m ai_live.comments "Lan: giá bao nhiêu?" "Huy: hello shop" "chất liệu gì vậy?"

Each argument is one comment as `author: text`; without a colon the author is empty. Prints the priority or the
drop reason of each comment, then the order the host would answer them in. Uses the same rule files as the app.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ai_live.comment_queue.memory_queue import InMemoryCommentQueue
from ai_live.comments.classifier import PriorityClassifier
from ai_live.comments.filters import CommentFilter
from ai_live.comments.intake import CommentIntake, IntakeResult
from ai_live.comments.mock_source import MockSource
from ai_live.core.config import Settings
from ai_live.core.events import EventBus


def _split(arg: str) -> tuple[str, str]:
    author, sep, text = arg.partition(":")
    return (author.strip(), text.strip()) if sep else ("", arg)


def _describe(result: IntakeResult) -> str:
    who = f"{result.comment.author}: {result.comment.text}"
    if result.drop_reason is not None:
        return f"  [bỏ: {result.drop_reason.value}]  {who}"
    return f"  [{result.priority.name}]  {who}"


async def _run(settings: Settings, comments: list[str]) -> None:
    bus = EventBus()
    queue = InMemoryCommentQueue(max_size=settings.comment_queue_max, max_age_s=settings.comment_max_age_s, bus=bus)
    intake = CommentIntake(
        source=MockSource(max_chars=settings.comment_max_chars),
        comment_filter=CommentFilter.from_settings(settings),
        classifier=PriorityClassifier.from_settings(settings),
        queue=queue,
        bus=bus,
    )
    print("Kết quả lọc và phân loại:")
    for arg in comments:
        print(_describe(await intake.submit(*_split(arg))))
    print()
    print("Thứ tự hàng đợi (host trả lời lần lượt):")
    for i, item in enumerate(queue.snapshot(), start=1):
        print(f"  {i}. [{item.priority.name}] {item.comment.author}: {item.comment.text}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m ai_live.comments")
    parser.add_argument("comments", nargs="+", help='mỗi comment dạng "tên: nội dung"')
    args = parser.parse_args(argv)
    asyncio.run(_run(Settings(), args.comments))
    return 0


if __name__ == "__main__":
    sys.exit(main())
