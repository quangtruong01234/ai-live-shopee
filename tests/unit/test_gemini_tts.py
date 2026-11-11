"""T035 (003): `GeminiTTS` with a fake client (contracts/adapters.md §2, contracts/events.md §2, research R2).

No network and no quota: `client.aio.interactions.create` is faked, errors are the SDK's own classes.
"""

from __future__ import annotations

import base64
import gc
import logging
import weakref
from collections.abc import AsyncIterator

import anyio
import numpy as np
import pytest

from ai_live.core.protocols import TTSEngineError
from ai_live.tts.gemini_tts import GeminiTTS
from fixtures.fake_gemini_tts import (
    SECRET_KEY,
    FakeGeminiClient,
    FakeInteractions,
    audio_event,
    connection_error,
    error_event,
    http_error,
    other_event,
    pcm_chunks,
    text_delta_event,
)

pytestmark = pytest.mark.anyio


def _make(interactions: FakeInteractions | None = None, *, voice: str = "Leda") -> tuple[GeminiTTS, FakeInteractions]:
    client = FakeGeminiClient(interactions)
    return GeminiTTS(client=client, model="gemini-3.8-flash-tts", voice=voice), client.interactions


async def _collect(stream: AsyncIterator[bytes]) -> list[bytes]:
    with anyio.fail_after(5):
        return [c async for c in stream]


async def _error(stream: AsyncIterator[bytes]) -> TTSEngineError:
    with pytest.raises(TTSEngineError) as exc:
        await _collect(stream)
    return exc.value


async def test_request_has_model_text_format_voice_and_stream():
    tts, interactions = _make(voice="Kore")
    await _collect(tts.synthesize("Dạ chào chị Lan"))
    assert interactions.calls == [
        {
            "model": "gemini-3.8-flash-tts",
            "input": [{"type": "user_input", "content": [{"type": "text", "text": "Dạ chào chị Lan"}]}],
            # Asking for 16 kHz is rejected with HTTP 400 (T044); the API's own 24 kHz is resampled here.
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": "Kore"}]},
            "stream": True,
        }
    ]


async def test_no_session_or_viewer_metadata_is_sent():
    tts, interactions = _make()
    await _collect(tts.synthesize("Dạ"))
    [call] = interactions.calls
    assert set(call) == {"model", "input", "response_format", "generation_config", "stream"}


async def test_audio_deltas_are_decoded_in_order_and_other_events_skipped():
    pcm = pcm_chunks(3)
    events = [
        other_event("interaction.created"),
        other_event("step.start"),
        audio_event(pcm[0]),
        text_delta_event(),
        audio_event(pcm[1]),
        other_event("status_update"),
        audio_event(pcm[2]),
        other_event("step.stop"),
        other_event("interaction.completed"),
    ]
    tts, _ = _make(FakeInteractions(events))
    assert b"".join(await _collect(tts.synthesize("Dạ"))) == b"".join(pcm)


async def test_every_chunk_holds_whole_samples_even_when_deltas_split_one():
    # A delta boundary may fall inside a 2-byte sample; the odd byte is carried over to the next chunk.
    events = [audio_event(b"\x01\x02\x03"), audio_event(b"\x04\x05\x06\x07"), audio_event(b"\x08")]
    tts, _ = _make(FakeInteractions(events))
    chunks = await _collect(tts.synthesize("Dạ"))
    assert all(len(c) % 2 == 0 and c for c in chunks)
    assert b"".join(chunks) == bytes(range(1, 9))


async def test_sample_rate_is_the_requested_one():
    tts, _ = _make()
    assert tts.sample_rate == 16000


async def test_24khz_from_provider_is_resampled_to_16khz():
    # What the real API sends (T044): 0.1 s of 24 kHz split over deltas, one of them ending inside a sample.
    t = np.arange(2400) / 24000
    pcm = (8000 * np.sin(2 * np.pi * 440 * t)).astype("<i2").tobytes()
    events = [audio_event(pcm[:1001], sample_rate=24000), audio_event(pcm[1001:], sample_rate=24000)]
    tts, _ = _make(FakeInteractions(events))
    chunks = await _collect(tts.synthesize("Dạ"))
    assert all(len(c) % 2 == 0 and c for c in chunks)
    out = np.frombuffer(b"".join(chunks), dtype="<i2")
    assert len(out) == 1600
    assert np.abs(out).max() > 4000


async def test_sample_rate_that_cannot_be_resampled_is_config_error():
    tts, _ = _make(FakeInteractions([audio_event(b"\x00\x00", sample_rate=44100)]))
    err = await _error(tts.synthesize("Dạ"))
    assert err.kind == "config_error"
    assert "44100" in err.message


async def test_audio_that_is_not_raw_pcm_is_config_error():
    tts, _ = _make(FakeInteractions([audio_event(b"\x00\x00", mime_type="audio/mp3")]))
    err = await _error(tts.synthesize("Dạ"))
    assert err.kind == "config_error"
    assert "audio/mp3" in err.message


async def test_http_429_is_quota_exhausted():
    tts, _ = _make(FakeInteractions(call_error=http_error(429, "Resource has been exhausted")))
    err = await _error(tts.synthesize("Dạ"))
    assert err.kind == "quota_exhausted"
    assert err.message.startswith("Hết hạn mức giọng nói (Gemini TTS, gói miễn phí)")


async def test_429_error_event_mid_stream_is_quota_exhausted():
    events = [audio_event(pcm_chunks(1)[0]), error_event("RESOURCE_EXHAUSTED", "quota")]
    tts, _ = _make(FakeInteractions(events))
    err = await _error(tts.synthesize("Dạ"))
    assert err.kind == "quota_exhausted"


@pytest.mark.parametrize("status", [400, 403, 500, 503])
async def test_other_http_error_is_api_error_with_code(status):
    tts, _ = _make(FakeInteractions(call_error=http_error(status, "Bad thing")))
    err = await _error(tts.synthesize("Dạ"))
    assert err.kind == "api_error"
    assert err.message.startswith(f"Gemini TTS lỗi HTTP {status}: ")
    assert "Bad thing" in err.message


async def test_http_error_mid_stream_is_api_error():
    tts, _ = _make(FakeInteractions(iter_error=http_error(500, "stream broke")))
    err = await _error(tts.synthesize("Dạ"))
    assert (err.kind, err.message) == ("api_error", "Gemini TTS lỗi HTTP 500: stream broke")


async def test_error_event_other_than_quota_is_api_error():
    tts, _ = _make(FakeInteractions([error_event("INTERNAL", "server sad")]))
    err = await _error(tts.synthesize("Dạ"))
    assert err.kind == "api_error"
    assert "server sad" in err.message


async def test_connection_error_is_api_error():
    tts, _ = _make(FakeInteractions(call_error=connection_error()))
    err = await _error(tts.synthesize("Dạ"))
    assert err.kind == "api_error"
    assert err.message.startswith("Gemini TTS lỗi kết nối")


async def test_stream_is_closed_after_a_full_sentence():
    tts, interactions = _make()
    await _collect(tts.synthesize("Dạ"))
    assert interactions.streams[0].closed


async def test_aclose_mid_sentence_closes_the_client_stream():
    tts, interactions = _make(FakeInteractions(hang_after=2))
    stream = tts.synthesize("Dạ")
    with anyio.fail_after(5):
        first = await stream.__anext__()
    assert first
    await stream.aclose()
    assert interactions.streams[0].closed


async def test_stream_is_closed_after_an_error_mid_stream():
    tts, interactions = _make(FakeInteractions(iter_error=http_error(500)))
    await _error(tts.synthesize("Dạ"))
    assert interactions.streams[0].closed


async def test_two_sentences_run_one_after_the_other():
    tts, interactions = _make(FakeInteractions(hang_after=1))
    first = tts.synthesize("Một")
    second = tts.synthesize("Hai")
    async with anyio.create_task_group() as tg:
        tg.start_soon(_drain_quietly, first)
        tg.start_soon(_drain_quietly, second)
        await anyio.sleep(0.05)
        # The first sentence hangs mid-stream, so the second must still be waiting for the lock.
        assert len(interactions.calls) == 1
        tg.cancel_scope.cancel()


async def _drain_quietly(stream: AsyncIterator[bytes]) -> None:
    async for _ in stream:
        pass


async def test_warm_up_does_not_call_the_client():
    tts, interactions = _make()
    await tts.warm_up()
    await tts.warm_up()
    assert interactions.calls == []


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(lambda: http_error(429, f"quota for key={SECRET_KEY}"), id="429"),
        pytest.param(lambda: http_error(500, f"bad key={SECRET_KEY}"), id="500"),
        pytest.param(connection_error, id="connect"),
    ],
)
async def test_api_key_never_reaches_messages_or_logs(error, caplog):
    caplog.set_level(logging.DEBUG)
    tts, _ = _make(FakeInteractions(call_error=error()))
    err = await _error(tts.synthesize("Dạ"))
    assert SECRET_KEY not in err.message
    assert SECRET_KEY not in str(err)
    assert SECRET_KEY not in caplog.text


def test_adapter_keeps_the_client_alive():
    # Found by T044: a collected `genai.Client` closes its HTTP client, so a sentence later fails with
    # "Cannot send a request, as the client has been closed".
    client = FakeGeminiClient()
    ref = weakref.ref(client)
    tts = GeminiTTS(client=client, model="m", voice="Leda")
    del client
    gc.collect()
    assert ref() is not None
    assert tts.model == "m"


def test_audio_event_helper_round_trips():
    # Guards the fixture itself: the adapter decodes standard base64.
    assert base64.b64decode(audio_event(b"\x01\x02").delta.data) == b"\x01\x02"
