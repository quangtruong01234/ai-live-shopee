"""Self-tests of the fake OpenAI-compatible provider (`tests/fixtures/fake_openai.py`), so engine tests can trust it."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from fixtures.fake_openai import (
    ChatReply,
    Delay,
    Disconnect,
    Done,
    ErrorFrame,
    FakeOpenAI,
    Finish,
    Keepalive,
    ModelRow,
    Reasoning,
    Role,
    Text,
    UsageChunk,
    connect_error,
    content_filtered,
    empty_stream,
    hang_without_text,
    http_error,
    models_connect_error,
    models_error,
    models_list,
    stream_reply,
)

pytestmark = pytest.mark.anyio

LOOPBACK = "http://127.0.0.1:3001/v1"
GROQ = "https://api.groq.com/openai/v1"


def _body(model: str) -> dict:
    return {"model": model, "messages": [{"role": "user", "content": "chào"}], "stream": True}


async def _read_lines(client: httpx.AsyncClient, base_url: str, model: str) -> tuple[httpx.Response, list[str]]:
    async with client.stream("POST", f"{base_url}/chat/completions", json=_body(model)) as resp:
        lines = [line async for line in resp.aiter_lines() if line]
    return resp, lines


async def test_stream_replays_every_event_kind_and_records_the_request() -> None:
    fake = FakeOpenAI().chat(
        LOOPBACK,
        "gpt-oss-120b",
        ChatReply(
            events=[
                Role(),
                Keepalive(),
                Reasoning("nghĩ đã", field="reasoning"),
                Text("Xin chào. "),
                Text("Áo mới."),
                Finish("stop"),
                UsageChunk(prompt_tokens=10, completion_tokens=4, cached_tokens=6),
                Done(),
            ],
            routed_via="groq/openai/gpt-oss-120b",
            response_model="openai/gpt-oss-120b",
        ),
    )
    async with httpx.AsyncClient(transport=fake.transport) as client:
        resp, lines = await _read_lines(client, LOOPBACK + "/", "gpt-oss-120b")

    assert resp.headers["x-routed-via"] == "groq/openai/gpt-oss-120b"
    assert resp.headers["content-type"] == "text/event-stream"
    assert lines[1] == ": keepalive"
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(line[6:]) for line in lines if line.startswith("data: {")]
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant", "content": ""}
    assert chunks[1]["choices"][0]["delta"] == {"content": None, "reasoning": "nghĩ đã"}
    assert [c["choices"][0]["delta"].get("content") for c in chunks[2:4]] == ["Xin chào. ", "Áo mới."]
    assert {c["model"] for c in chunks} == {"openai/gpt-oss-120b"}
    assert chunks[4]["choices"][0]["finish_reason"] == "stop"
    assert chunks[5]["choices"] == []
    assert chunks[5]["usage"]["prompt_tokens_details"] == {"cached_tokens": 6}

    [req] = fake.chat_requests(LOOPBACK, "gpt-oss-120b")
    assert req.base_url == LOOPBACK and req.path == "/chat/completions" and req.method == "POST"
    assert req.body["stream"] is True
    served = fake.served[0]
    assert served.lines_read == len(lines) == 8
    assert served.finished and served.closed
    assert fake.unscripted == []


async def test_closing_right_after_headers_reads_no_sse_line() -> None:
    fake = FakeOpenAI().chat(LOOPBACK, "m", stream_reply("Câu một.", routed_via="cache"))
    async with httpx.AsyncClient(transport=fake.transport) as client:
        async with client.stream("POST", f"{LOOPBACK}/chat/completions", json=_body("m")) as resp:
            assert resp.headers["x-routed-via"] == "cache"
    assert fake.lines_read() == 0
    assert fake.served[0].closed and not fake.served[0].finished


async def test_queue_order_last_reply_repeats_and_keys_by_base_url_and_model() -> None:
    fake = FakeOpenAI()
    fake.chat(LOOPBACK, "m", http_error(429, code="rate_limited"), stream_reply("Được rồi."))
    fake.chat(GROQ, "m", http_error(503, type="service_unavailable"))
    async with httpx.AsyncClient(transport=fake.transport) as client:
        statuses = []
        for _ in range(3):
            resp = await client.post(f"{LOOPBACK}/chat/completions", json=_body("m"))
            statuses.append(resp.status_code)
        groq = await client.post(f"{GROQ}/chat/completions", json=_body("m"))
    assert statuses == [429, 200, 200]
    assert groq.status_code == 503
    assert groq.json() == {"error": {"message": "fake provider error", "type": "service_unavailable"}}
    assert len(fake.chat_requests(LOOPBACK)) == 3 and len(fake.chat_requests(GROQ)) == 1


async def test_http_error_body_uses_freellmapi_code_and_keeps_routed_via() -> None:
    fake = FakeOpenAI().chat(LOOPBACK, "m", http_error(502, code="empty_completion", routed_via="cloudflare/@cf/x"))
    async with httpx.AsyncClient(transport=fake.transport) as client:
        resp = await client.post(f"{LOOPBACK}/chat/completions", json=_body("m"))
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "empty_completion"
    assert resp.headers["x-routed-via"] == "cloudflare/@cf/x"
    assert fake.served == []


async def test_connect_error_raises_httpx_connect_error_and_is_recorded() -> None:
    fake = FakeOpenAI().chat(LOOPBACK, "m", connect_error())
    async with httpx.AsyncClient(transport=fake.transport) as client:
        with pytest.raises(httpx.ConnectError):
            await client.post(f"{LOOPBACK}/chat/completions", json=_body("m"))
    assert len(fake.requests) == 1


async def test_hang_without_text_is_bounded_by_asyncio_timeout() -> None:
    fake = FakeOpenAI().chat(LOOPBACK, "m", hang_without_text(routed_via="groq/x"))
    async with httpx.AsyncClient(transport=fake.transport) as client:
        async with client.stream("POST", f"{LOOPBACK}/chat/completions", json=_body("m")) as resp:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    async for _ in resp.aiter_lines():
                        pass
    assert fake.served[0].lines_read == 1  # only the role chunk
    assert fake.served[0].closed


async def test_keepalive_forever_and_hang_before_headers() -> None:
    fake = FakeOpenAI()
    fake.chat(LOOPBACK, "a", hang_without_text(keepalive_every=0.01))
    fake.chat(LOOPBACK, "b", ChatReply(hang_before_headers=True))
    async with httpx.AsyncClient(transport=fake.transport) as client:
        async with client.stream("POST", f"{LOOPBACK}/chat/completions", json=_body("a")) as resp:
            seen: list[str] = []
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.1):
                    async for line in resp.aiter_lines():
                        if line:
                            seen.append(line)
        assert seen and set(seen) == {": keepalive"}
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await client.post(f"{LOOPBACK}/chat/completions", json=_body("b"))
    assert len(fake.served) == 1  # the hung request never got a response


async def test_disconnect_and_error_frame_after_first_text() -> None:
    fake = FakeOpenAI()
    fake.chat(LOOPBACK, "drop", ChatReply(events=[Text("Câu một. "), Delay(0.0), Disconnect()]))
    fake.chat(LOOPBACK, "frame", ChatReply(events=[Text("Câu một. "), ErrorFrame(code="upstream_failed"), Done()]))
    async with httpx.AsyncClient(transport=fake.transport) as client:
        with pytest.raises(httpx.ReadError):
            await _read_lines(client, LOOPBACK, "drop")
        _, lines = await _read_lines(client, LOOPBACK, "frame")
    assert json.loads(lines[1][6:]) == {
        "error": {"message": "upstream stream failed", "type": "stream_error", "code": "upstream_failed"}
    }
    assert fake.lines_read(model="drop") == 1


async def test_empty_and_content_filtered_streams_carry_no_text() -> None:
    fake = FakeOpenAI().chat(LOOPBACK, "e", empty_stream()).chat(LOOPBACK, "f", content_filtered())
    async with httpx.AsyncClient(transport=fake.transport) as client:
        _, empty = await _read_lines(client, LOOPBACK, "e")
        _, filtered = await _read_lines(client, LOOPBACK, "f")
    for lines in (empty, filtered):
        texts = [json.loads(x[6:])["choices"][0]["delta"].get("content") for x in lines if x.startswith("data: {")]
        assert not any(texts)
    assert json.loads(filtered[1][6:])["choices"][0]["finish_reason"] == "content_filter"


async def test_models_listing_errors_and_unscripted_requests() -> None:
    fake = FakeOpenAI()
    fake.models(
        LOOPBACK,
        models_list(
            ModelRow("gpt-oss-120b", available=True, execution_status="exhausted"),
            ModelRow("gemma-sea-lion-v4-27b", available=False, unavailable_reason="no_key"),
            "plain",
        ),
        models_error(401),
        models_connect_error(),
    )
    async with httpx.AsyncClient(transport=fake.transport) as client:
        ok = await client.get(f"{LOOPBACK}/models", headers={"Authorization": "Bearer freellmapi-test"})
        denied = await client.get(f"{LOOPBACK}/models")
        with pytest.raises(httpx.ConnectError):
            await client.get(f"{LOOPBACK}/models")
        unscripted = await client.get(f"{GROQ}/models")

    assert ok.json()["data"] == [
        {"id": "gpt-oss-120b", "object": "model", "available": True, "execution_status": "exhausted"},
        {"id": "gemma-sea-lion-v4-27b", "object": "model", "available": False, "unavailable_reason": "no_key"},
        {"id": "plain", "object": "model"},
    ]
    assert denied.status_code == 401
    assert unscripted.status_code == 501 and unscripted.json()["error"]["code"] == "fake_unscripted"
    assert [r.base_url for r in fake.unscripted] == [GROQ]
    assert fake.models_requests(LOOPBACK)[0].headers["authorization"] == "Bearer freellmapi-test"
    assert fake.chat_requests() == []
