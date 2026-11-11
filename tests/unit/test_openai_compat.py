"""`OpenAICompatClient` on the fake provider, no network (contracts/adapters.md §3, research R1, R3, R6, R12).

T016 (008 US1): request shape, SSE parsing, `GET /models`, basic failures, key redaction.
T026 (008 US2): every row of the research R3 table maps to its `reason`, and the X-Routed-Via platform check (FR-024).
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from ai_live.brain.chain_state import AttemptReason
from ai_live.brain.openai_compat import (
    CHAT_TIMEOUT,
    ModelRow,
    OpenAICompatClient,
    ProviderFailure,
    ResolvedEntry,
    StreamMeta,
    Usage,
    make_http_client,
)
from ai_live.core.config import ChainEntryConfig
from fixtures import fake_openai as fo

pytestmark = pytest.mark.anyio

LOCAL = "http://127.0.0.1:3001/v1"
GROQ = "https://api.groq.com/openai/v1"
# Deliberately matches none of the redact.py key patterns: only redaction by value can hide it.
KEY = "plainvalue-without-any-known-prefix-42"
MESSAGES = [{"role": "system", "content": "Hệ thống."}, {"role": "user", "content": "Giá bao nhiêu?"}]


def _entry(
    *,
    base_url: str = LOCAL,
    model: str = "gpt-oss-120b",
    platform: str | None = "groq",
    params: dict | None = None,
) -> ResolvedEntry:
    config = ChainEntryConfig(
        label="gptoss",
        base_url=base_url,
        model=model,
        key_env="FREELLMAPI_KEY",
        platform=platform,
        first_sentence_timeout_s=2.0,
        params=params or {},
    )
    return ResolvedEntry(config=config, position=1, local=config.local, key=SecretStr(KEY))


async def _stream(fake: fo.FakeOpenAI, entry: ResolvedEntry, max_tokens: int = 300) -> tuple[list[str], StreamMeta]:
    meta = StreamMeta()
    async with httpx.AsyncClient(transport=fake.transport) as http:
        client = OpenAICompatClient(http, [KEY])
        deltas = [d async for d in client.stream_chat(entry, MESSAGES, max_tokens, meta)]
    return deltas, meta


# ------------------------------------------------------------------------------------------------- request shape


async def test_request_body_is_exactly_the_contract_shape_plus_params() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.stream_reply("Xin chào. ", routed_via="groq/x"))
    await _stream(fake, _entry(params={"reasoning_effort": "low", "temperature": 0.4}), max_tokens=321)
    (request,) = fake.chat_requests()
    assert request.method == "POST"
    assert request.url == f"{LOCAL}/chat/completions"
    assert request.body == {
        "model": "gpt-oss-120b",
        "messages": MESSAGES,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 321,
        "reasoning_effort": "low",
        "temperature": 0.4,
    }


async def test_headers_bearer_key_and_cache_off_when_entry_has_platform() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.stream_reply("Xin chào. ", routed_via="groq/x"))
    await _stream(fake, _entry(platform="groq"))
    headers = fake.chat_requests()[0].headers
    assert headers["authorization"] == f"Bearer {KEY}"
    assert headers["x-freellm-cache"] == "off"


async def test_no_cache_header_when_entry_has_no_platform() -> None:
    fake = fo.FakeOpenAI().chat(GROQ, "qwen/qwen3.8-27b", fo.stream_reply("Xin chào. "))
    await _stream(fake, _entry(base_url=GROQ, model="qwen/qwen3.8-27b", platform=None))
    headers = fake.chat_requests()[0].headers
    assert headers["authorization"] == f"Bearer {KEY}"
    assert "x-freellm-cache" not in headers


def test_http_client_timeout_leaves_read_unbounded() -> None:
    # The engine bounds the first sentence, the runner bounds the turn; a read timeout here would cut long segments.
    assert httpx.Timeout(connect=2.0, read=None, write=5.0, pool=2.0) == CHAT_TIMEOUT
    client = make_http_client()
    assert client.timeout == CHAT_TIMEOUT


# --------------------------------------------------------------------------------------------------- SSE parsing


async def test_sse_skips_comments_and_reasoning_and_stops_at_done() -> None:
    reply = fo.ChatReply(
        events=[
            fo.Role(),
            fo.Keepalive(),
            fo.Reasoning("đang nghĩ", field="reasoning_content"),
            fo.Text("Dạ chào "),
            fo.Reasoning("nghĩ tiếp", field="reasoning"),
            fo.Keepalive("ping"),
            fo.Text("bạn Lan."),
            fo.Finish("stop"),
            fo.UsageChunk(prompt_tokens=120, completion_tokens=30, cached_tokens=100),
            fo.Done(),
            fo.Text(" SAU DONE"),
        ],
        routed_via="groq/openai/gpt-oss-120b",
        response_model="openai/gpt-oss-120b",
    )
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
    deltas, meta = await _stream(fake, _entry())
    assert "".join(deltas) == "Dạ chào bạn Lan."
    assert all(d for d in deltas)
    assert meta.routed_via == "groq/openai/gpt-oss-120b"
    assert meta.model == "openai/gpt-oss-120b"
    assert meta.finish_reason == "stop"
    assert meta.usage == Usage(prompt_tokens=120, completion_tokens=30, cached_tokens=100)
    assert fake.served[0].closed


async def test_usage_under_x_groq_is_read() -> None:
    usage = fo.UsageChunk(prompt_tokens=50, completion_tokens=7, where="x_groq")
    fake = fo.FakeOpenAI().chat(GROQ, "qwen/qwen3.8-27b", fo.stream_reply("Dạ có ạ. ", usage=usage))
    _, meta = await _stream(fake, _entry(base_url=GROQ, model="qwen/qwen3.8-27b", platform=None))
    assert meta.usage == Usage(prompt_tokens=50, completion_tokens=7, cached_tokens=None)
    assert meta.routed_via is None


async def test_meta_without_usage_chunk_stays_none() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.stream_reply("Dạ có ạ. ", routed_via="groq/x"))
    _, meta = await _stream(fake, _entry())
    assert meta.usage is None
    assert meta.model == "gpt-oss-120b"  # the fake echoes the requested model
    assert meta.finish_reason == "stop"


async def test_finish_reason_content_filter_is_reported_in_meta() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.content_filtered(routed_via="groq/x"))
    deltas, meta = await _stream(fake, _entry())
    assert deltas == []
    assert meta.finish_reason == "content_filter"


# ---------------------------------------------------------------------------------------- chat failures (basic)


async def test_http_429_is_rate_limited_with_status() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.http_error(429, code="rate_limited"))
    with pytest.raises(ProviderFailure) as exc:
        await _stream(fake, _entry())
    assert exc.value.reason == AttemptReason.RATE_LIMITED
    assert exc.value.status == 429


async def test_http_401_is_rejected_and_message_hides_the_key() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.http_error(401, message=f"invalid api key {KEY}"))
    with pytest.raises(ProviderFailure) as exc:
        await _stream(fake, _entry())
    assert exc.value.reason == AttemptReason.REJECTED
    assert exc.value.status == 401
    assert KEY not in exc.value.message
    assert KEY not in str(exc.value)
    assert "401" in exc.value.message


async def test_connect_error_is_connection() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.connect_error())
    with pytest.raises(ProviderFailure) as exc:
        await _stream(fake, _entry())
    assert exc.value.reason == AttemptReason.CONNECTION
    assert exc.value.status is None


async def test_error_frame_after_text_raises_after_the_text_and_hides_key() -> None:
    reply = fo.ChatReply(
        events=[fo.Role(), fo.Text("Dạ chào bạn. "), fo.ErrorFrame(message=f"upstream died, key={KEY}"), fo.Done()],
        routed_via="groq/x",
    )
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
    meta = StreamMeta()
    got: list[str] = []
    async with httpx.AsyncClient(transport=fake.transport) as http:
        client = OpenAICompatClient(http, [KEY])
        with pytest.raises(ProviderFailure) as exc:
            async for delta in client.stream_chat(_entry(), MESSAGES, 300, meta):
                got.append(delta)
    assert got == ["Dạ chào bạn. "]
    assert KEY not in exc.value.message


async def test_disconnect_mid_stream_is_connection() -> None:
    reply = fo.ChatReply(events=[fo.Role(), fo.Text("Dạ. "), fo.Disconnect()], routed_via="groq/x")
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
    with pytest.raises(ProviderFailure) as exc:
        await _stream(fake, _entry())
    assert exc.value.reason == AttemptReason.CONNECTION


# ----------------------------------------------------------------------------- platform check (FR-024, for T018)


@pytest.mark.parametrize("routed_via", [None, "cache", "idempotency", "cerebras/gpt-oss-120b"])
async def test_wrong_platform_closes_after_headers_with_zero_sse_lines(routed_via: str | None) -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.stream_reply("Dạ có ạ. ", routed_via=routed_via))
    with pytest.raises(ProviderFailure) as exc:
        await _stream(fake, _entry(platform="groq"))
    assert exc.value.reason == AttemptReason.WRONG_PLATFORM
    assert exc.value.routed_via == routed_via
    assert fake.served[0].lines_read == 0
    assert fake.served[0].closed


@pytest.mark.parametrize("routed_via", ["Groq/openai/gpt-oss-120b", "GROQ/x/y", "groq"])
async def test_platform_matches_case_insensitively_on_the_part_before_the_first_slash(routed_via: str) -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.stream_reply("Dạ có ạ. ", routed_via=routed_via))
    deltas, meta = await _stream(fake, _entry(platform="groq"))
    assert "".join(deltas) == "Dạ có ạ. "
    assert meta.routed_via == routed_via


async def test_entry_without_platform_is_not_checked() -> None:
    fake = fo.FakeOpenAI().chat(GROQ, "qwen/qwen3.8-27b", fo.stream_reply("Dạ có ạ. ", routed_via="cache"))
    deltas, _ = await _stream(fake, _entry(base_url=GROQ, model="qwen/qwen3.8-27b", platform=None))
    assert "".join(deltas) == "Dạ có ạ. "


# --------------------------------------------------------------------------- research R3 classification (T026, US2)


async def _failure(fake: fo.FakeOpenAI, entry: ResolvedEntry | None = None) -> ProviderFailure:
    with pytest.raises(ProviderFailure) as exc:
        await _stream(fake, entry or _entry())
    return exc.value


@pytest.mark.parametrize(
    ("reply", "reason", "status"),
    [
        (fo.http_error(429), AttemptReason.RATE_LIMITED, 429),
        (fo.http_error(429, code="rate_limited"), AttemptReason.RATE_LIMITED, 429),
        (fo.http_error(429, type="tokens"), AttemptReason.RATE_LIMITED, 429),
        (fo.http_error(500), AttemptReason.OVERLOADED, 500),
        (fo.http_error(502), AttemptReason.OVERLOADED, 502),
        (fo.http_error(503), AttemptReason.OVERLOADED, 503),
        (fo.http_error(504), AttemptReason.OVERLOADED, 504),
        (fo.http_error(503, code="over_capacity"), AttemptReason.OVERLOADED, 503),
        (fo.http_error(502, code="empty_completion"), AttemptReason.EMPTY, 502),
        (fo.http_error(502, type="empty_completion"), AttemptReason.EMPTY, 502),
        (fo.http_error(400), AttemptReason.REJECTED, 400),
        (fo.http_error(401, type="invalid_api_key"), AttemptReason.REJECTED, 401),
        (fo.http_error(403), AttemptReason.REJECTED, 403),
        (fo.http_error(404, code="model_not_found"), AttemptReason.REJECTED, 404),
        (fo.http_error(422), AttemptReason.REJECTED, 422),
        (fo.http_error(409), AttemptReason.REJECTED, 409),
        (fo.http_error(413, type="request_too_large"), AttemptReason.REJECTED, 413),
        (fo.http_error(502, code="provider_authentication_failed"), AttemptReason.REJECTED, 502),
        (fo.http_error(502, type="provider_authentication_failed"), AttemptReason.REJECTED, 502),
        (fo.http_error(502, code="provider_error"), AttemptReason.REJECTED, 502),
        (fo.http_error(502, type="provider_error"), AttemptReason.REJECTED, 502),
        (fo.http_error(503, code="no_providers_configured"), AttemptReason.REJECTED, 503),
        (fo.http_error(503, type="no_providers_configured"), AttemptReason.REJECTED, 503),
    ],
    ids=lambda v: v.value if isinstance(v, AttemptReason) else None,
)
async def test_http_status_and_error_code_map_to_the_r3_reason(
    reply: fo.ChatReply, reason: AttemptReason, status: int
) -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
    failure = await _failure(fake)
    assert failure.reason == reason
    assert failure.status == status
    assert str(status) in failure.message


async def test_a_code_only_counts_with_its_own_status() -> None:
    # `empty_completion` is a 502 code of freellmapi; on a 429 the status decides.
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.http_error(429, code="empty_completion"))
    assert (await _failure(fake)).reason == AttemptReason.RATE_LIMITED


async def test_retry_after_is_not_read() -> None:
    reply = fo.ChatReply(
        status=429, error_body=fo.error_body("slow down", code="rate_limited"), headers={"Retry-After": "3600"}
    )
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
    failure = await _failure(fake)
    assert failure.reason == AttemptReason.RATE_LIMITED
    assert not any("retry" in name.lower() for name in vars(failure))
    assert "3600" not in failure.message


async def test_http_error_without_routed_via_is_classified_by_status_not_platform() -> None:
    # freellmapi error answers usually carry no X-Routed-Via; the status is the real cause.
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.http_error(429))
    assert (await _failure(fake, _entry(platform="groq"))).reason == AttemptReason.RATE_LIMITED


async def test_a_non_json_error_body_is_classified_by_status() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.ChatReply(status=502, error_body={"detail": "bad gateway"}))
    assert (await _failure(fake)).reason == AttemptReason.OVERLOADED


@pytest.mark.parametrize(
    "frame",
    [
        fo.ErrorFrame(),
        fo.ErrorFrame(type=None, code="stream_error"),
        fo.ErrorFrame(type="server_error", code="empty_completion"),
    ],
    ids=["type", "code", "other-code"],
)
async def test_sse_error_frame_before_text_is_overloaded(frame: fo.ErrorFrame) -> None:
    reply = fo.ChatReply(events=[fo.Role(), fo.Keepalive(), frame, fo.Done()], routed_via="groq/x")
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
    failure = await _failure(fake)
    assert failure.reason == AttemptReason.OVERLOADED
    assert failure.status is None
    assert failure.routed_via == "groq/x"


@pytest.mark.parametrize(
    "reply",
    [
        fo.connect_error(),
        fo.ChatReply(events=[fo.Role(), fo.Disconnect()], routed_via="groq/x"),
        fo.ChatReply(events=[fo.Role(), fo.Disconnect(protocol=True)], routed_via="groq/x"),
        fo.ChatReply(events=[fo.Role(), fo.Text("Dạ. "), fo.Disconnect(protocol=True)], routed_via="groq/x"),
    ],
    ids=["ConnectError", "ReadError", "RemoteProtocolError", "RemoteProtocolError-after-text"],
)
async def test_transport_errors_are_connection(reply: fo.ChatReply) -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
    failure = await _failure(fake)
    assert failure.reason == AttemptReason.CONNECTION
    assert failure.status is None


async def test_failure_messages_hide_the_key_for_every_row() -> None:
    for reply in (
        fo.http_error(502, code="provider_error", message=f"upstream said {KEY}"),
        fo.http_error(429, message=f"limit for {KEY}"),
        fo.ChatReply(events=[fo.Role(), fo.ErrorFrame(message=f"boom {KEY}")], routed_via="groq/x"),
    ):
        fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", reply)
        failure = await _failure(fake)
        assert KEY not in failure.message
        assert KEY not in str(failure)


# ---------------------------------------------------------------------------- platform check (FR-024, T026, US2)


@pytest.mark.parametrize(
    "routed_via",
    [None, "", "cache", "idempotency", "cerebras/gpt-oss-120b", "groqx/gpt-oss-120b", "openrouter/groq/x"],
    ids=["missing", "blank", "cache", "idempotency", "other", "prefix-lookalike", "groq-later-in-path"],
)
async def test_wrong_platform_reports_the_header_and_reads_no_sse_line(routed_via: str | None) -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.stream_reply("Dạ có ạ. ", routed_via=routed_via))
    failure = await _failure(fake, _entry(platform="groq"))
    assert failure.reason == AttemptReason.WRONG_PLATFORM
    assert failure.routed_via == routed_via
    assert "groq" in failure.message  # the expected platform is named
    (served,) = fake.served
    assert served.lines_read == 0
    assert served.closed
    assert not served.finished


async def test_cloudflare_route_matches_case_insensitively() -> None:
    route = "Cloudflare/@cf/aisingapore/gemma-sea-lion-v4-27b-it"
    fake = fo.FakeOpenAI().chat(LOCAL, "gemma-sea-lion-v4-27b", fo.stream_reply("Dạ có ạ. ", routed_via=route))
    deltas, meta = await _stream(fake, _entry(model="gemma-sea-lion-v4-27b", platform="cloudflare"))
    assert "".join(deltas) == "Dạ có ạ. "
    assert meta.routed_via == route


async def test_platform_declared_in_upper_case_still_matches() -> None:
    fake = fo.FakeOpenAI().chat(LOCAL, "gpt-oss-120b", fo.stream_reply("Dạ có ạ. ", routed_via="groq/x"))
    entry = _entry()
    entry = ResolvedEntry(
        config=entry.config.model_copy(update={"platform": " GROQ "}), position=1, local=True, key=SecretStr(KEY)
    )
    deltas, _ = await _stream(fake, entry)
    assert deltas == ["Dạ có ạ. "]


@pytest.mark.parametrize("routed_via", [None, "cache", "cerebras/gpt-oss-120b"])
async def test_entry_without_platform_never_checks_the_header(routed_via: str | None) -> None:
    fake = fo.FakeOpenAI().chat(GROQ, "qwen/qwen3.8-27b", fo.stream_reply("Dạ có ạ. ", routed_via=routed_via))
    deltas, meta = await _stream(fake, _entry(base_url=GROQ, model="qwen/qwen3.8-27b", platform=None))
    assert deltas == ["Dạ có ạ. "]
    assert meta.routed_via == routed_via


# ---------------------------------------------------------------------------------------------------- list_models


async def _list(fake: fo.FakeOpenAI, base_url: str = LOCAL, **kw) -> dict[str, ModelRow]:
    async with httpx.AsyncClient(transport=fake.transport) as http:
        return await OpenAICompatClient(http, [KEY], **kw).list_models(base_url, SecretStr(KEY))


async def test_list_models_reads_ids_and_freellmapi_fields() -> None:
    fake = fo.FakeOpenAI().models(
        LOCAL,
        fo.models_list(
            fo.ModelRow("gpt-oss-120b", available=True, execution_status="ready"),
            fo.ModelRow(
                "gemma-sea-lion-v4-27b", available=False, unavailable_reason="no_key", execution_status="needsKey"
            ),
            "qwen/qwen3.8-27b",
        ),
    )
    listing = await _list(fake)
    assert listing == {
        "gpt-oss-120b": ModelRow(available=True, unavailable_reason=None, execution_status="ready"),
        "gemma-sea-lion-v4-27b": ModelRow(available=False, unavailable_reason="no_key", execution_status="needsKey"),
        "qwen/qwen3.8-27b": ModelRow(available=None, unavailable_reason=None, execution_status=None),
    }
    (request,) = fake.models_requests()
    assert request.method == "GET"
    assert request.url == f"{LOCAL}/models"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert fake.chat_requests() == []


@pytest.mark.parametrize("status", [401, 403])
async def test_list_models_auth_failure_is_rejected_with_status(status: int) -> None:
    fake = fo.FakeOpenAI().models(LOCAL, fo.models_error(status, message=f"bad key {KEY}"))
    with pytest.raises(ProviderFailure) as exc:
        await _list(fake)
    assert exc.value.reason == AttemptReason.REJECTED
    assert exc.value.status == status
    assert KEY not in exc.value.message


async def test_list_models_other_status_is_rejected_with_that_status() -> None:
    fake = fo.FakeOpenAI().models(LOCAL, fo.models_error(500))
    with pytest.raises(ProviderFailure) as exc:
        await _list(fake)
    assert exc.value.reason == AttemptReason.REJECTED
    assert exc.value.status == 500


async def test_list_models_connect_error_is_connection() -> None:
    fake = fo.FakeOpenAI().models(LOCAL, fo.models_connect_error())
    with pytest.raises(ProviderFailure) as exc:
        await _list(fake)
    assert exc.value.reason == AttemptReason.CONNECTION
    assert exc.value.status is None


async def test_list_models_over_its_time_limit_is_connection() -> None:
    fake = fo.FakeOpenAI().models(LOCAL, fo.ModelsReply(hang_before_headers=True))
    with pytest.raises(ProviderFailure) as exc:
        await _list(fake, models_timeout_s=0.05)
    assert exc.value.reason == AttemptReason.CONNECTION


def test_list_models_default_time_limit_is_5_seconds() -> None:
    client = OpenAICompatClient(make_http_client(), [KEY])
    assert client.models_timeout_s == 5.0
