"""Streaming client for OpenAI-compatible chat APIs: freellmapi, Groq (feature 008, research R1, R12; ADR-035).

One class covers every provider of the chain: it builds the request, parses the SSE stream and reports failures as
`ProviderFailure`. Deciding what a failure means for the turn (switch entry, rest, give up) is the engine's job.
Nothing here logs; every message that leaves this module has the key values masked.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from ai_live.brain.chain_state import AttemptReason
from ai_live.core.config import ChainEntryConfig
from ai_live.security.redact import redact_secret_values

__all__ = [
    "CHAT_TIMEOUT",
    "MODELS_TIMEOUT_S",
    "ModelListing",
    "ModelRow",
    "OpenAICompatClient",
    "ProviderFailure",
    "ResolvedEntry",
    "StreamMeta",
    "Usage",
    "make_http_client",
]

# No read limit: the engine bounds the wait for the first sentence per entry and the runner bounds the whole turn, so a
# read timeout here could only cut a long segment that is still flowing (contracts/adapters.md §3).
CHAT_TIMEOUT = httpx.Timeout(connect=2.0, read=None, write=5.0, pool=2.0)
# Startup check only (research R9): a gateway that does not answer in 5 s counts as unreachable.
MODELS_TIMEOUT_S = 5.0

_DONE = "[DONE]"


@dataclass(frozen=True)
class Usage:
    """Token counts of one turn, each `None` when the provider did not send it (only logged, data-model §5)."""

    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None


@dataclass(frozen=True)
class ResolvedEntry:
    """A chain entry plus its key, built by `ChainReplyEngine.from_settings` (data-model §10). `key` is never logged."""

    config: ChainEntryConfig
    position: int
    local: bool
    key: SecretStr

    @property
    def label(self) -> str:
        return self.config.label


@dataclass
class StreamMeta:
    """Filled in by `stream_chat` while it runs, so the caller can read it even after a failure or cancellation."""

    routed_via: str | None = None  # X-Routed-Via response header
    model: str | None = None  # "model" field of the response chunks
    finish_reason: str | None = None
    usage: Usage | None = None


@dataclass(frozen=True)
class ModelRow:
    """One row of `GET /models`. `available` is absent on Groq; only `False` means unusable (contracts/config.md §4)."""

    available: bool | None = None
    unavailable_reason: str | None = None
    execution_status: str | None = None


ModelListing = dict[str, ModelRow]


class ProviderFailure(Exception):
    """One provider call failed. `message` is already redacted (research R12); `Retry-After` is never read (R3)."""

    def __init__(
        self,
        reason: AttemptReason,
        status: int | None = None,
        message: str = "",
        *,
        routed_via: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status
        self.message = message
        self.routed_via = routed_via


def make_http_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """The shared client of one engine; tests pass `httpx.MockTransport` (tests/fixtures/fake_openai.py)."""
    return httpx.AsyncClient(transport=transport, timeout=CHAT_TIMEOUT)


def _platform_matches(routed_via: str | None, platform: str) -> bool:
    """`Cloudflare/gemma…` matches `cloudflare`; `cache`, `idempotency` or a missing header never match."""
    if not routed_via:
        return False
    return routed_via.split("/", 1)[0].strip().casefold() == platform.strip().casefold()


# freellmapi answers these with a 5xx, yet retrying the same entry soon will not help: they mean the gateway itself is
# misconfigured for this model (research R3). They still move the turn to the next entry.
_REJECTED_TAGS = {
    502: frozenset({"provider_authentication_failed", "provider_error"}),
    503: frozenset({"no_providers_configured"}),
}


def _classify(status: int, raw: bytes) -> AttemptReason:
    """Map a non-200 answer to its reason (research R3 table). Both `error.code` (freellmapi) and `error.type`
    (OpenAI/Groq) are read; `Retry-After` is not, since every entry rests the same `cooldown_s`.
    """
    if status == 429:
        return AttemptReason.RATE_LIMITED
    tags = _error_tags(raw)
    if status == 502 and "empty_completion" in tags:
        return AttemptReason.EMPTY
    if tags & _REJECTED_TAGS.get(status, frozenset()):
        return AttemptReason.REJECTED
    # R3 lists 500/502/503/504; any other 5xx is also a server-side fault worth retrying after the rest.
    if status >= 500:
        return AttemptReason.OVERLOADED
    return AttemptReason.REJECTED


def _error_tags(raw: bytes) -> frozenset[str]:
    try:
        body = json.loads(raw)
    except ValueError:
        return frozenset()
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return frozenset()
    return frozenset(str(error[k]).strip().casefold() for k in ("code", "type") if error.get(k))


def _error_text(raw: bytes) -> str:
    """Short description from an OpenAI-style error body: `error.message` plus `error.code` / `error.type`."""
    try:
        body = json.loads(raw)
    except ValueError:
        return raw[:200].decode("utf-8", errors="replace")
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return json.dumps(body, ensure_ascii=False)[:200]
    tag = error.get("code") or error.get("type")
    message = str(error.get("message") or "")
    return f"{tag}: {message}" if tag else message


def _usage(raw: Any) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    details = raw.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    return Usage(
        prompt_tokens=raw.get("prompt_tokens"),
        completion_tokens=raw.get("completion_tokens"),
        cached_tokens=cached,
    )


class OpenAICompatClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        secrets: Sequence[str | SecretStr],
        *,
        models_timeout_s: float = MODELS_TIMEOUT_S,
    ) -> None:
        self._client = client
        self._secrets = list(secrets)
        self.models_timeout_s = models_timeout_s

    def _failure(
        self, reason: AttemptReason, status: int | None, message: str, routed_via: str | None = None
    ) -> ProviderFailure:
        # A provider may echo the key it received in its error body; mask by value, not only by pattern (R12).
        return ProviderFailure(reason, status, redact_secret_values(message, self._secrets), routed_via=routed_via)

    async def stream_chat(
        self,
        entry: ResolvedEntry,
        messages: list[dict[str, str]],
        max_tokens: int,
        meta: StreamMeta,
    ) -> AsyncGenerator[str, None]:
        """Yield the text deltas of one streamed completion; raise `ProviderFailure` on any failure.

        Whether a failure happened before or after the first sentence is the caller's call.
        """
        config = entry.config
        body = {
            "model": config.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": max_tokens,
            **config.params,
        }
        headers = {"Authorization": f"Bearer {entry.key.get_secret_value()}"}
        if config.platform:
            # A cache hit would replay an old answer instead of generating one (Article I, research R2).
            headers["X-FreeLLM-Cache"] = "off"
        url = f"{config.base_url}/chat/completions"
        try:
            async with self._client.stream("POST", url, json=body, headers=headers) as response:
                meta.routed_via = response.headers.get("x-routed-via")
                if response.status_code != 200:
                    raw = await response.aread()
                    # Status before platform: freellmapi error answers usually carry no X-Routed-Via, and the status
                    # is the real cause (a 429 must rest as rate_limited, not as wrong_platform).
                    raise self._failure(
                        _classify(response.status_code, raw),
                        response.status_code,
                        f"HTTP {response.status_code}: {_error_text(raw)}",
                        meta.routed_via,
                    )
                if config.platform and not _platform_matches(meta.routed_via, config.platform):
                    # Checked before the first SSE line: leaving the `async with` closes the response unread, so a
                    # cached, replayed or wrongly routed answer never reaches the viewer (FR-024, research R2).
                    raise self._failure(
                        AttemptReason.WRONG_PLATFORM,
                        response.status_code,
                        f'X-Routed-Via={meta.routed_via!r}, cần nền tảng "{config.platform}"',
                        meta.routed_via,
                    )
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue  # SSE separator or comment (freellmapi ": keepalive")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == _DONE:
                        return
                    text = self._parse_chunk(data, meta)
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise self._failure(
                AttemptReason.CONNECTION, None, f"{type(exc).__name__}: {exc}", meta.routed_via
            ) from exc

    def _parse_chunk(self, data: str, meta: StreamMeta) -> str | None:
        try:
            chunk = json.loads(data)
        except ValueError:
            return None  # a malformed line carries no usable text; a stream of only those ends up `empty`
        if not isinstance(chunk, dict):
            return None
        if "error" in chunk:
            error = chunk["error"]
            text = _error_text(json.dumps({"error": error}).encode()) if isinstance(error, dict) else str(error)
            raise self._failure(AttemptReason.OVERLOADED, None, f"lỗi trong luồng: {text}", meta.routed_via)
        if chunk.get("model"):
            meta.model = chunk["model"]
        usage = chunk.get("usage")
        if usage is None:
            x_groq = chunk.get("x_groq")
            usage = x_groq.get("usage") if isinstance(x_groq, dict) else None
        if usage is not None:
            meta.usage = _usage(usage) or meta.usage
        choices = chunk.get("choices")
        if not choices or not isinstance(choices[0], dict):
            return None
        choice = choices[0]
        if choice.get("finish_reason"):
            meta.finish_reason = choice["finish_reason"]
        delta = choice.get("delta")
        # Only `content` is spoken; `reasoning` / `reasoning_content` must never reach the viewer.
        content = delta.get("content") if isinstance(delta, dict) else None
        return content if isinstance(content, str) else None

    async def list_models(self, base_url: str, key: SecretStr) -> ModelListing:
        """`GET {base_url}/models` within `models_timeout_s` (startup check, research R9).

        Raises `ProviderFailure(CONNECTION)` when unreachable or too slow, `ProviderFailure(REJECTED, status)` for any
        non-200 answer.
        """
        url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {key.get_secret_value()}"}
        try:
            async with asyncio.timeout(self.models_timeout_s):
                response = await self._client.get(url, headers=headers)
        except TimeoutError as exc:
            raise self._failure(
                AttemptReason.CONNECTION, None, f"quá {self.models_timeout_s:g} s không có trả lời"
            ) from exc
        except httpx.HTTPError as exc:
            raise self._failure(AttemptReason.CONNECTION, None, f"{type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise self._failure(
                AttemptReason.REJECTED,
                response.status_code,
                f"HTTP {response.status_code}: {_error_text(response.content)}",
            )
        try:
            rows = response.json().get("data") or []
        except (ValueError, AttributeError) as exc:
            raise self._failure(AttemptReason.REJECTED, 200, "danh sách model không phải JSON hợp lệ") from exc
        listing: ModelListing = {}
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                available = row.get("available")
                listing[row["id"]] = ModelRow(
                    available=available if isinstance(available, bool) else None,
                    unavailable_reason=row.get("unavailable_reason"),
                    execution_status=row.get("execution_status"),
                )
        return listing
