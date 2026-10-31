"""Chọn ReplyEngine theo `REPLY_ENGINE`. Dùng chung cho app và CLI để hai nơi không chọn lệch nhau."""

from __future__ import annotations

from ai_live.core.config import Settings
from ai_live.core.protocols import ReplyEngine


def create_reply_engine(settings: Settings) -> ReplyEngine:
    if settings.reply_engine == "fake":
        from ai_live.brain.fake_engine import FakeReplyEngine

        return FakeReplyEngine()
    # Import muộn: chạy `fake` không cần nạp SDK Gemini.
    from ai_live.brain.gemini_engine import GeminiReplyEngine

    return GeminiReplyEngine.from_settings(settings)
