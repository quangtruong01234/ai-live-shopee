"""Fake `google.genai` client for `GeminiTTS` tests: no network, no API key, no quota (003 research R2).

Only `client.aio.interactions.create(..., stream=True)` is faked, because that is the single call the adapter makes.
Errors are the SDK's own classes (`google.genai._interactions`), built from a fake `httpx.Response`, so the adapter's
mapping is tested against what the real client raises. Shared by the unit tests and the `TTSEngine` contract tests.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

import anyio
import httpx
from google.genai import _interactions

SECRET_KEY = "AIza-test-secret-key-do-not-log"


def audio_event(pcm: bytes, *, sample_rate: int = 16000, mime_type: str = "audio/l16") -> SimpleNamespace:
    """A `step.delta` event carrying base64 PCM, with only the attributes the adapter reads.

    The real API sends 24 kHz (research R2); 16 kHz is the default here so most tests can compare bytes exactly.
    """
    return SimpleNamespace(
        event_type="step.delta",
        delta=SimpleNamespace(
            type="audio", data=base64.b64encode(pcm).decode(), sample_rate=sample_rate, mime_type=mime_type
        ),
    )


def other_event(event_type: str = "interaction.created") -> SimpleNamespace:
    return SimpleNamespace(event_type=event_type)


def text_delta_event() -> SimpleNamespace:
    return SimpleNamespace(event_type="step.delta", delta=SimpleNamespace(type="text", text="không phải tiếng"))


def error_event(code: str, message: str = "boom") -> SimpleNamespace:
    return SimpleNamespace(event_type="error", error=SimpleNamespace(code=code, message=message))


def http_error(status: int, message: str = "boom") -> _interactions.APIStatusError:
    """The SDK error for an HTTP status; the request URL carries the key, as the real client's would."""
    request = httpx.Request("POST", f"https://generativelanguage.googleapis.com/v1beta/interactions?key={SECRET_KEY}")
    response = httpx.Response(status, request=request, json={"error": {"code": status, "message": message}})
    cls = _interactions.RateLimitError if status == 429 else _interactions.APIStatusError
    return cls(message, response=response, body={"error": {"code": status, "message": message}})


def connection_error() -> _interactions.APIConnectionError:
    request = httpx.Request("POST", f"https://generativelanguage.googleapis.com/v1beta/interactions?key={SECRET_KEY}")
    return _interactions.APIConnectionError(request=request)


def pcm_chunks(n: int = 3, size: int = 640) -> list[bytes]:
    """`n` distinct even-length PCM16 chunks, so order and content can be checked after decoding."""
    return [bytes([i + 1]) * size for i in range(n)]


class FakeStream:
    """Fake `AsyncStream`: yields scripted events; `close()` stands in for releasing the HTTP response."""

    def __init__(
        self, events: list[Any], *, iter_error: Exception | None = None, hang_after: int | None = None
    ) -> None:
        self._events = events
        self._iter_error = iter_error
        self._hang_after = hang_after
        self._index = 0
        self.closed = False

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> Any:
        if self.closed:
            raise StopAsyncIteration
        if self._hang_after is not None and self._index >= self._hang_after:
            await anyio.sleep_forever()
        if self._index < len(self._events):
            event = self._events[self._index]
            self._index += 1
            await anyio.lowlevel.checkpoint()
            return event
        if self._iter_error is not None:
            raise self._iter_error
        raise StopAsyncIteration

    async def close(self) -> None:
        self.closed = True


class FakeInteractions:
    """Fake `client.aio.interactions`: records call kwargs and returns a fresh scripted stream per call.

    - `call_error`: raised by `create` itself (before any event), like an HTTP error on the request.
    - `iter_error`: raised after every event was yielded, like a broken stream mid-sentence.
    - `hang_after`: after this many events the provider stalls forever, so skip/timeout paths can be tested.
    """

    def __init__(
        self,
        events: Iterable[Any] | None = None,
        *,
        call_error: Exception | None = None,
        iter_error: Exception | None = None,
        hang_after: int | None = None,
    ) -> None:
        self.events = list(events) if events is not None else [other_event(), *map(audio_event, pcm_chunks())]
        self.call_error = call_error
        self.iter_error = iter_error
        self.hang_after = hang_after
        self.calls: list[dict[str, Any]] = []
        self.streams: list[FakeStream] = []

    async def create(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        await anyio.lowlevel.checkpoint()
        if self.call_error is not None:
            raise self.call_error
        stream = FakeStream(list(self.events), iter_error=self.iter_error, hang_after=self.hang_after)
        self.streams.append(stream)
        return stream


class FakeGeminiClient:
    """Stands in for `genai.Client`; only `client.aio.interactions` exists."""

    def __init__(self, interactions: FakeInteractions | None = None) -> None:
        self.interactions = interactions or FakeInteractions()
        self.aio = SimpleNamespace(interactions=self.interactions)
