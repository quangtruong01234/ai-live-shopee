"""Pick the `ReplyEngine` from `REPLY_ENGINE`. Shared by the app and the CLIs so they never pick differently."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_live.core.config import Settings
from ai_live.core.protocols import ReplyEngine, ReplyEngineError

if TYPE_CHECKING:
    from ai_live.brain.chain_engine import FaultHook


def create_reply_engine(
    settings: Settings,
    *,
    only: str | None = None,
    fault_hook: FaultHook | None = None,
) -> ReplyEngine:
    """Build the engine named by `settings.reply_engine` (`chain`, `gemini` or `fake`).

    `only` (one `LLM_CHAIN` label, qa_eval `--entry`) and `fault_hook` (dev fault injection) apply to `chain` only.
    Any problem is a `ReplyEngineError("config_error")`, so the app refuses to start instead of picking an engine
    the user did not ask for.
    """
    engine = settings.reply_engine
    if only is not None and engine != "chain":
        raise ReplyEngineError(
            "config_error", f'Chỉ chọn được mục "{only}" của LLM_CHAIN khi REPLY_ENGINE=chain (đang là {engine})'
        )
    # Lazy imports: `fake` needs neither the Gemini SDK nor the chain engine.
    if engine == "chain":
        from ai_live.brain.chain_engine import ChainReplyEngine

        return ChainReplyEngine.from_settings(settings, only=only, fault_hook=fault_hook)
    if engine == "gemini":
        from ai_live.brain.gemini_engine import GeminiReplyEngine

        return GeminiReplyEngine.from_settings(settings)
    if engine == "fake":
        from ai_live.brain.fake_engine import FakeReplyEngine

        return FakeReplyEngine()
    raise ReplyEngineError("config_error", f"REPLY_ENGINE={engine!r} không hợp lệ; dùng chain, gemini hoặc fake")
