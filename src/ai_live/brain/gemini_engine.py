"""ReplyEngine gọi Gemini API, async streaming (ADR-018, research R5)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import errors, types

from ai_live.brain.prompt import build_system_prompt, build_user_message
from ai_live.brain.sentence_splitter import SentenceSplitter
from ai_live.core.config import Settings
from ai_live.core.logging import log_event
from ai_live.core.models import Comment
from ai_live.core.protocols import ReplyEngineError
from ai_live.products.models import ProductCatalog

logger = logging.getLogger("ai_live.brain")

_BLOCKED_FINISH = {
    types.FinishReason.SAFETY,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.SPII,
}


def _error_from_api(exc: errors.APIError) -> ReplyEngineError:
    # 429 không retry trong lượt live: chờ backoff là vượt ngân sách 5 s (research R5).
    kind = "rate_limited" if exc.code == 429 else "api_error"
    return ReplyEngineError(kind, f"Gemini lỗi HTTP {exc.code}: {exc.message or exc.status}")


class GeminiReplyEngine:
    def __init__(self, client: Any, *, model: str, thinking_level: str, max_output_tokens: int) -> None:
        self._client = client
        self.model = model
        self.max_output_tokens = max_output_tokens
        try:
            self.thinking_level = types.ThinkingLevel[thinking_level.upper()]
        except KeyError as exc:
            allowed = ", ".join(m.lower() for m in types.ThinkingLevel.__members__ if m != "THINKING_LEVEL_UNSPECIFIED")
            raise ReplyEngineError(
                "config_error", f"LLM_THINKING_LEVEL={thinking_level!r} không hợp lệ, dùng: {allowed}"
            ) from exc

    @classmethod
    def from_settings(cls, settings: Settings) -> GeminiReplyEngine:
        if settings.gemini_api_key is None:
            raise ReplyEngineError("config_error", "Chưa đặt GEMINI_API_KEY trong .env (REPLY_ENGINE=gemini)")
        client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
        return cls(
            client,
            model=settings.llm_model,
            thinking_level=settings.llm_thinking_level,
            max_output_tokens=settings.llm_max_tokens,
        )

    def _config(self, catalog: ProductCatalog) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=build_system_prompt(catalog),
            max_output_tokens=self.max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
        )

    async def reply(self, comment: Comment, catalog: ProductCatalog) -> AsyncIterator[str]:
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=build_user_message(comment),
                config=self._config(catalog),
            )
        except errors.APIError as exc:
            raise _error_from_api(exc) from exc

        splitter = SentenceSplitter()
        emitted = 0
        usage = None
        try:
            async for chunk in stream:
                feedback = getattr(chunk, "prompt_feedback", None)
                if feedback is not None and getattr(feedback, "block_reason", None):
                    raise ReplyEngineError("provider_blocked", f"Gemini chặn prompt: {feedback.block_reason}")
                for candidate in getattr(chunk, "candidates", None) or ():
                    if getattr(candidate, "finish_reason", None) in _BLOCKED_FINISH:
                        raise ReplyEngineError("provider_blocked", f"Gemini dừng vì {candidate.finish_reason}")
                usage = getattr(chunk, "usage_metadata", None) or usage
                for sentence in splitter.feed(chunk.text or ""):
                    emitted += 1
                    yield sentence
        except errors.APIError as exc:
            raise _error_from_api(exc) from exc
        finally:
            # Hủy lượt (bỏ qua, timeout) phải đóng stream để không giữ kết nối HTTP và không tốn thêm token.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()

        for sentence in splitter.flush():
            emitted += 1
            yield sentence
        if emitted == 0:
            raise ReplyEngineError("provider_blocked", "Gemini không trả chữ nào")
        if usage is not None:
            log_event(
                logger,
                "llm_usage",
                comment_id=comment.id,
                prompt_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
                cached_tokens=getattr(usage, "cached_content_token_count", None),
            )
