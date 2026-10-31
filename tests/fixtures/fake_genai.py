"""Fake `google.genai` client for `GeminiReplyEngine` tests: no network, no API key (research R5).

Only `client.aio.models.generate_content_stream` is faked, because that is the single call the engine makes.
Shared by the unit tests and the `ReplyEngine` contract tests so both script the provider the same way.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from types import SimpleNamespace
from typing import Any

import anyio
from google.genai import errors


def chunk(text: str | None, finish_reason: Any = None, block_reason: Any = None) -> SimpleNamespace:
    """One streamed response chunk, with only the attributes the engine reads."""
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=finish_reason)],
        prompt_feedback=SimpleNamespace(block_reason=block_reason) if block_reason else None,
    )


def text_chunks(text: str, size: int = 7) -> list[SimpleNamespace]:
    """Cut `text` into small deltas that break words and sentences, like a real token stream."""
    return [chunk(text[i : i + size]) for i in range(0, len(text), size)]


def api_error(code: int, status: str = "INTERNAL", message: str = "boom") -> errors.APIError:
    return errors.APIError(code, {"error": {"message": message, "status": status}})


class FakeModels:
    """Fake `client.aio.models`: records call kwargs and returns a scripted stream.

    - `call_error`: raised by the call itself (before any chunk).
    - `iter_error`: raised after every chunk was yielded.
    - `hang_after`: after this many chunks the provider stalls forever, so cancel/close paths can be tested.
    `closed` turns true once the stream generator is finalized, proving the HTTP stream would be released.
    """

    def __init__(
        self,
        chunks: Iterable[Any] = (),
        *,
        call_error: Exception | None = None,
        iter_error: Exception | None = None,
        hang_after: int | None = None,
    ) -> None:
        self.chunks = list(chunks)
        self.call_error = call_error
        self.iter_error = iter_error
        self.hang_after = hang_after
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def generate_content_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        if self.call_error is not None:
            raise self.call_error
        return self._stream()

    async def _stream(self):
        try:
            for i, item in enumerate(self.chunks):
                if self.hang_after is not None and i >= self.hang_after:
                    await anyio.sleep(3600)
                yield item
            if self.iter_error is not None:
                raise self.iter_error
            if self.hang_after is not None:
                await anyio.sleep(3600)
        finally:
            self.closed = True


def fake_client(models: FakeModels) -> SimpleNamespace:
    """Object shaped like `genai.Client` as far as the engine is concerned."""
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def scripted_client(sentences: Sequence[str], size: int = 7) -> tuple[SimpleNamespace, FakeModels]:
    """Client whose stream speaks `sentences` (joined by spaces) in small deltas."""
    models = FakeModels(text_chunks(" ".join(sentences), size))
    return fake_client(models), models
