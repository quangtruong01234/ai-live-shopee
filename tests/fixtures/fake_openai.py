"""Fake OpenAI-compatible provider for `ChainReplyEngine` / `OpenAICompatClient` tests (feature 008, FR-023).

Built on `httpx.MockTransport`, so the code under test uses a real `httpx.AsyncClient(transport=fake.transport)` and its
real SSE parsing; nothing touches the network and no key is needed.

Usage::

    fake = FakeOpenAI()
    fake.chat(BASE, "gpt-oss-120b", stream_reply("Xin chào. ", "Áo mới.", routed_via="groq/openai/gpt-oss-120b"))
    fake.chat(BASE, "gemma-sea-lion-v4-27b", http_error(429, code="rate_limited"))
    fake.models(BASE, models_list(ModelRow("gpt-oss-120b", available=True)))
    async with httpx.AsyncClient(transport=fake.transport) as client:
        ...
    assert fake.requests == []              # "0 requests"
    assert fake.served[0].lines_read == 0   # "no SSE line read" (e.g. wrong_platform closed after headers)

    engine = build_chain_engine(fake, {"label": "gptoss", "base_url": BASE, ...})  # real ChainReplyEngine on the fake

Scripting rules:
- Chat replies are keyed by (`base_url`, `model`): `base_url` is the request URL minus `/chat/completions` (trailing `/`
  ignored), `model` is the `model` field of the JSON body. Model listings are keyed by `base_url` (URL minus `/models`).
- Each key holds a queue: every request takes the next reply, and the last reply repeats forever, so one
  `http_error(429)` means "always 429".
- A request with no script is recorded in `unscripted` and answered with HTTP 501 and error code `fake_unscripted`;
  assert `fake.unscripted == []` when a test must not reach an unexpected entry.
- Delays and hangs use `asyncio.sleep`, so tests bound them with short `asyncio.timeout(...)` values.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

CHAT_PATH = "/chat/completions"
MODELS_PATH = "/models"

# ---------------------------------------------------------------------------------------------------------------------
# SSE events of a chat stream. A `ChatReply.events` sequence is replayed in order; each line-producing event becomes one
# SSE line followed by a blank line, sent as one byte chunk.
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Role:
    """Opening chunk real providers send: `delta = {"role": "assistant", "content": ""}` (no text)."""


@dataclass(frozen=True)
class Text:
    """A text delta in `choices[0].delta.content`."""

    text: str


@dataclass(frozen=True)
class Reasoning:
    """A reasoning delta the client must ignore (`reasoning_content` on some providers, `reasoning` on Groq)."""

    text: str
    field: Literal["reasoning", "reasoning_content"] = "reasoning_content"


@dataclass(frozen=True)
class Keepalive:
    """An SSE comment line such as freellmapi's `: keepalive`."""

    comment: str = "keepalive"


@dataclass(frozen=True)
class Finish:
    """A chunk with an empty delta and `finish_reason` (`stop`, `length`, `content_filter`, ...)."""

    reason: str = "stop"


@dataclass(frozen=True)
class UsageChunk:
    """The final usage chunk (`choices: []`). `where="x_groq"` puts it under `x_groq.usage` (research R6 TODO)."""

    prompt_tokens: int = 120
    completion_tokens: int = 30
    cached_tokens: int | None = None
    where: Literal["usage", "x_groq"] = "usage"


@dataclass(frozen=True)
class ErrorFrame:
    """An in-stream `data: {"error": {...}}` frame, like freellmapi's `stream_error`. `None` fields are omitted."""

    message: str = "upstream stream failed"
    type: str | None = "stream_error"
    code: str | None = None


@dataclass(frozen=True)
class Done:
    """`data: [DONE]`."""


@dataclass(frozen=True)
class Raw:
    """Any literal SSE line (no trailing newline), for malformed-input tests."""

    line: str


@dataclass(frozen=True)
class Delay:
    """Pause before the next event (`asyncio.sleep`); produces no line."""

    seconds: float


@dataclass(frozen=True)
class Hang:
    """Stall forever before the next event; produces no line. The client must time out or cancel."""


@dataclass(frozen=True)
class KeepaliveForever:
    """Send `: keepalive` every `interval` seconds and never anything else (freellmapi retrying upstream)."""

    interval: float


@dataclass(frozen=True)
class Disconnect:
    """Drop the connection: the body stream raises `httpx.ReadError` (or `RemoteProtocolError` when `protocol=True`)."""

    protocol: bool = False


Event = (
    Role
    | Text
    | Reasoning
    | Keepalive
    | Finish
    | UsageChunk
    | ErrorFrame
    | Done
    | Raw
    | Delay
    | Hang
    | KeepaliveForever
    | Disconnect
)


@dataclass(frozen=True)
class ChatReply:
    """One scripted answer to `POST {base_url}/chat/completions`.

    - `status != 200`: the body is `error_body` as JSON and `events` is ignored.
    - `routed_via`: value of the `X-Routed-Via` response header; `None` leaves the header out.
    - `response_model`: `model` field put in every chunk; `None` echoes the requested model.
    - `connect_error`: the transport raises `httpx.ConnectError` (no response at all).
    - `headers_delay`: seconds before the status line arrives; `hang_before_headers` never sends it.
    """

    events: Sequence[Event] = ()
    status: int = 200
    error_body: Mapping[str, Any] | None = None
    routed_via: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    response_model: str | None = None
    connect_error: bool = False
    headers_delay: float = 0.0
    hang_before_headers: bool = False


@dataclass(frozen=True)
class ModelRow:
    """One `data[]` row of `GET /models`. Optional freellmapi fields set to `None` are left out of the JSON."""

    id: str
    available: bool | None = None
    unavailable_reason: str | None = None
    execution_status: str | None = None


@dataclass(frozen=True)
class ModelsReply:
    """One scripted answer to `GET {base_url}/models` (same `connect_error` / hang knobs as `ChatReply`)."""

    rows: Sequence[ModelRow] = ()
    status: int = 200
    error_body: Mapping[str, Any] | None = None
    connect_error: bool = False
    headers_delay: float = 0.0
    hang_before_headers: bool = False


Reply = ChatReply | ModelsReply

# ---------------------------------------------------------------------------------------------------------------------
# Builders for the common cases.
# ---------------------------------------------------------------------------------------------------------------------


def stream_reply(
    *texts: str,
    routed_via: str | None = None,
    usage: UsageChunk | None = None,
    finish: str = "stop",
    delay: float = 0.0,
    response_model: str | None = None,
) -> ChatReply:
    """A normal stream: role chunk, one `Text` per argument (`delay` before each), finish, optional usage, `[DONE]`."""
    events: list[Event] = [Role()]
    for text in texts:
        if delay:
            events.append(Delay(delay))
        events.append(Text(text))
    events.append(Finish(finish))
    if usage is not None:
        events.append(usage)
    events.append(Done())
    return ChatReply(events=events, routed_via=routed_via, response_model=response_model)


def empty_stream(*, routed_via: str | None = None, finish: str = "stop") -> ChatReply:
    """A 200 stream that ends without any text."""
    return ChatReply(events=[Role(), Finish(finish), Done()], routed_via=routed_via)


def content_filtered(*, routed_via: str | None = None) -> ChatReply:
    """No text and `finish_reason = content_filter` (classified `blocked`, research R3)."""
    return empty_stream(routed_via=routed_via, finish="content_filter")


def error_body(message: str = "fake provider error", *, code: str | None = None, type: str | None = None) -> dict:
    """`{"error": {"message", "code"?, "type"?}}` as freellmapi (`code`) or OpenAI/Groq (`type`) send it."""
    err: dict[str, Any] = {"message": message}
    if code is not None:
        err["code"] = code
    if type is not None:
        err["type"] = type
    return {"error": err}


def http_error(
    status: int,
    *,
    code: str | None = None,
    type: str | None = None,
    message: str = "fake provider error",
    routed_via: str | None = None,
) -> ChatReply:
    """A non-200 chat answer with a JSON error body, e.g. `http_error(502, code="empty_completion")`."""
    return ChatReply(status=status, error_body=error_body(message, code=code, type=type), routed_via=routed_via)


def connect_error() -> ChatReply:
    """The provider cannot be reached (`httpx.ConnectError`)."""
    return ChatReply(connect_error=True)


def hang_without_text(*, routed_via: str | None = None, keepalive_every: float | None = None) -> ChatReply:
    """Status 200 and headers arrive, then no text ever comes (first-sentence timeout).

    `keepalive_every` sends a `: keepalive` line at that interval forever, like freellmapi while it retries upstream.
    """
    if keepalive_every is None:
        return ChatReply(events=[Role(), Hang()], routed_via=routed_via)
    return ChatReply(events=[KeepaliveForever(keepalive_every)], routed_via=routed_via)


def models_list(*rows: ModelRow | str) -> ModelsReply:
    """A 200 listing; plain strings become rows with only `id` (Groq style)."""
    return ModelsReply(rows=[ModelRow(r) if isinstance(r, str) else r for r in rows])


def models_error(status: int, *, code: str | None = None, message: str = "fake models error") -> ModelsReply:
    """A non-200 listing, e.g. `models_error(401)`."""
    return ModelsReply(status=status, error_body=error_body(message, code=code))


def models_connect_error() -> ModelsReply:
    return ModelsReply(connect_error=True)


# ---------------------------------------------------------------------------------------------------------------------
# Recording.
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedRequest:
    """Everything the client sent. `body` is the parsed JSON (or `None` when the body is empty)."""

    method: str
    url: str
    path: str
    base_url: str
    headers: dict[str, str]
    body: Any

    @property
    def model(self) -> str | None:
        return self.body.get("model") if isinstance(self.body, dict) else None


@dataclass
class ServedStream:
    """A chat stream handed to the client, observed live.

    `lines_read` counts SSE lines (data, comment and `[DONE]` lines, not blank separators) the client has pulled from
    the body so far; it stays 0 when the client closed the response right after the headers. `closed` turns true once
    the client released the response (or the body ran to the end).
    """

    request: RecordedRequest
    status: int
    lines_read: int = 0
    closed: bool = False
    finished: bool = False


class _SSEStream(httpx.AsyncByteStream):
    def __init__(self, reply: ChatReply, model: str, served: ServedStream) -> None:
        self._reply = reply
        self._model = model
        self._served = served

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            for event in self._reply.events:
                if isinstance(event, Delay):
                    await asyncio.sleep(event.seconds)
                    continue
                if isinstance(event, Hang):
                    await asyncio.Event().wait()
                if isinstance(event, Disconnect):
                    request = httpx.Request("POST", self._served.request.url)
                    if event.protocol:
                        raise httpx.RemoteProtocolError("fake: peer closed connection", request=request)
                    raise httpx.ReadError("fake: connection reset", request=request)
                if isinstance(event, KeepaliveForever):
                    while True:
                        await asyncio.sleep(event.interval)
                        self._served.lines_read += 1
                        yield b": keepalive\n\n"
                self._served.lines_read += 1
                yield (_sse_line(event, self._model) + "\n\n").encode("utf-8")
            self._served.finished = True
        finally:
            self._served.closed = True

    async def aclose(self) -> None:
        self._served.closed = True


def _chunk(model: str, delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _sse_line(event: Event, model: str) -> str:
    match event:
        case Keepalive(comment=comment):
            return f": {comment}"
        case Done():
            return "data: [DONE]"
        case Raw(line=line):
            return line
        case Role():
            payload = _chunk(model, {"role": "assistant", "content": ""})
        case Text(text=text):
            payload = _chunk(model, {"content": text})
        case Reasoning(text=text, field=name):
            payload = _chunk(model, {"content": None, name: text})
        case Finish(reason=reason):
            payload = _chunk(model, {}, reason)
        case UsageChunk() as u:
            usage: dict[str, Any] = {
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.prompt_tokens + u.completion_tokens,
            }
            if u.cached_tokens is not None:
                usage["prompt_tokens_details"] = {"cached_tokens": u.cached_tokens}
            payload = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [],
            }
            if u.where == "x_groq":
                payload["x_groq"] = {"usage": usage}
            else:
                payload["usage"] = usage
        case ErrorFrame(message=message, type=type_, code=code):
            err: dict[str, Any] = {"message": message}
            if type_ is not None:
                err["type"] = type_
            if code is not None:
                err["code"] = code
            payload = {"error": err}
        case _:
            raise TypeError(f"not an SSE event: {event!r}")
    return "data: " + json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------------------------------
# The fake provider.
# ---------------------------------------------------------------------------------------------------------------------


def _norm(base_url: str) -> str:
    return base_url.rstrip("/")


class FakeOpenAI:
    """Scripted OpenAI-compatible provider(s) behind one `httpx.MockTransport`.

    Several base URLs (freellmapi on loopback, Groq, ...) can share one instance, as one engine shares one client.
    """

    def __init__(self) -> None:
        self._chat: dict[tuple[str, str], list[ChatReply]] = {}
        self._models: dict[str, list[ModelsReply]] = {}
        self.requests: list[RecordedRequest] = []
        self.unscripted: list[RecordedRequest] = []
        self.served: list[ServedStream] = []
        self.transport = httpx.MockTransport(self._handle)

    # -- scripting --------------------------------------------------------------------------------------------------

    def chat(self, base_url: str, model: str, *replies: ChatReply) -> FakeOpenAI:
        """Queue chat replies for (`base_url`, `model`); the last one repeats. Returns `self` for chaining."""
        if not replies:
            raise ValueError("at least one ChatReply is required")
        self._chat.setdefault((_norm(base_url), model), []).extend(replies)
        return self

    def models(self, base_url: str, *replies: ModelsReply) -> FakeOpenAI:
        """Queue `GET /models` replies for `base_url`; the last one repeats. Returns `self` for chaining."""
        if not replies:
            raise ValueError("at least one ModelsReply is required")
        self._models.setdefault(_norm(base_url), []).extend(replies)
        return self

    # -- queries ----------------------------------------------------------------------------------------------------

    def chat_requests(self, base_url: str | None = None, model: str | None = None) -> list[RecordedRequest]:
        """Recorded chat requests, optionally filtered by base URL and/or model."""
        return [
            r
            for r in self.requests
            if r.path == CHAT_PATH
            and (base_url is None or r.base_url == _norm(base_url))
            and (model is None or r.model == model)
        ]

    def models_requests(self, base_url: str | None = None) -> list[RecordedRequest]:
        """Recorded `GET /models` requests, optionally filtered by base URL."""
        return [
            r for r in self.requests if r.path == MODELS_PATH and (base_url is None or r.base_url == _norm(base_url))
        ]

    def lines_read(self, base_url: str | None = None, model: str | None = None) -> int:
        """Total SSE lines the client pulled across the matching served streams."""
        return sum(
            s.lines_read
            for s in self.served
            if (base_url is None or s.request.base_url == _norm(base_url))
            and (model is None or s.request.model == model)
        )

    # -- transport --------------------------------------------------------------------------------------------------

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url.copy_with(query=None))
        if url.endswith(CHAT_PATH):
            path, base_url = CHAT_PATH, _norm(url[: -len(CHAT_PATH)])
        elif url.endswith(MODELS_PATH):
            path, base_url = MODELS_PATH, _norm(url[: -len(MODELS_PATH)])
        else:
            path, base_url = request.url.path, _norm(url)
        raw = request.content
        body = json.loads(raw) if raw else None
        recorded = RecordedRequest(
            method=request.method,
            url=url,
            path=path,
            base_url=base_url,
            headers={k.lower(): v for k, v in request.headers.items()},
            body=body,
        )
        self.requests.append(recorded)

        reply: Reply | None = None
        if path == CHAT_PATH and request.method == "POST":
            reply = self._take(self._chat.get((base_url, recorded.model or "")))
        elif path == MODELS_PATH and request.method == "GET":
            reply = self._take(self._models.get(base_url))
        if reply is None:
            self.unscripted.append(recorded)
            return httpx.Response(501, json=error_body("no script for this request", code="fake_unscripted"))

        if reply.connect_error:
            raise httpx.ConnectError("fake: connection refused", request=request)
        if reply.hang_before_headers:
            await asyncio.Event().wait()
        if reply.headers_delay:
            await asyncio.sleep(reply.headers_delay)

        if isinstance(reply, ModelsReply):
            if reply.status != 200:
                return httpx.Response(reply.status, json=dict(reply.error_body or {}))
            data = [_row_json(row) for row in reply.rows]
            return httpx.Response(200, json={"object": "list", "data": data})

        headers = dict(reply.headers)
        if reply.routed_via is not None:
            headers["X-Routed-Via"] = reply.routed_via
        if reply.status != 200:
            return httpx.Response(reply.status, headers=headers, json=dict(reply.error_body or {}))
        headers["Content-Type"] = "text/event-stream"
        served = ServedStream(request=recorded, status=200)
        self.served.append(served)
        stream = _SSEStream(reply, reply.response_model or recorded.model or "", served)
        return httpx.Response(200, headers=headers, stream=stream)

    @staticmethod
    def _take(queue: list[Reply] | None) -> Reply | None:
        if not queue:
            return None
        return queue.pop(0) if len(queue) > 1 else queue[0]


def _row_json(row: ModelRow) -> dict[str, Any]:
    out: dict[str, Any] = {"id": row.id, "object": "model"}
    for name in ("available", "unavailable_reason", "execution_status"):
        value = getattr(row, name)
        if value is not None:
            out[name] = value
    return out


# ---------------------------------------------------------------------------------------------------------------------
# A real `ChainReplyEngine` on the fake provider.
# ---------------------------------------------------------------------------------------------------------------------

# Fake key values, one per `key_env` a chain entry may name. Distinctive so a leak check can grep for them.
FAKE_KEYS: Mapping[str, str] = {
    "FREELLMAPI_KEY": "freellmapi-FAKE-KEY-do-not-print-0001",
    "GROQ_API_KEY": "gsk_FAKE_KEY_do_not_print_0002",
    "GEMINI_API_KEY": "AIzaFAKE-KEY-do-not-print-0003",
}


def build_chain_engine(
    fake: FakeOpenAI,
    *entries: Any,
    keys: Mapping[str, str] | None = None,
    cooldown_s: float = 60.0,
    max_tokens: int = 300,
    script_max_tokens: int = 600,
    fault_hook: Any = None,
) -> Any:
    """A real `ChainReplyEngine` whose shared `httpx.AsyncClient` runs on `fake.transport`.

    Uses the constructor of contracts/adapters.md §2 with `ResolvedEntry(config, position, local, key)` from data-model
    §10, because `from_settings()` has no transport argument. `entries` are `ChainEntryConfig` objects or dicts in the
    `LLM_CHAIN` shape; `keys` maps `key_env` to the key value (default `FAKE_KEYS`).

    Imported lazily: this module (and every test using only the fake provider) must still load before feature 008's
    engine exists.
    """
    from ai_live.brain.chain_engine import ChainReplyEngine, ResolvedEntry
    from pydantic import SecretStr

    from ai_live.core.config import ChainEntryConfig

    keys = FAKE_KEYS if keys is None else keys
    resolved = []
    for position, entry in enumerate(entries, start=1):
        config = entry if isinstance(entry, ChainEntryConfig) else ChainEntryConfig.model_validate(entry)
        # Same numbering `Settings` gives, so messages naming "mục N" read the same as in the app.
        config = config.model_copy(deep=True)
        config._position = position
        resolved.append(
            ResolvedEntry(config=config, position=position, local=config.local, key=SecretStr(keys[config.key_env]))
        )
    return ChainReplyEngine(
        resolved,
        cooldown_s=cooldown_s,
        max_tokens=max_tokens,
        script_max_tokens=script_max_tokens,
        transport=fake.transport,
        fault_hook=fault_hook,
    )
