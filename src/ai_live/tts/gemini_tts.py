"""Gemini TTS over the free tier of the Interactions API (ADR-024; 003 contracts/adapters.md §2, research R2).

Uses `google-genai`, already a dependency for the LLM (ADR-018). Only the spoken text and the voice leave the machine:
no session, utterance or viewer data is sent.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
from google.genai import _interactions
from google.genai import errors as genai_errors

from ai_live.core.protocols import TTSEngineError
from ai_live.security.redact import redact_text
from ai_live.tts.resample import Resampler

# Raw PCM16 LE; a delta without a rate is at the API's default, 24 kHz (research R2).
PCM_MIME_TYPE = "audio/l16"
PROVIDER_SAMPLE_RATE = 24000
QUOTA_MESSAGE = "Hết hạn mức giọng nói (Gemini TTS, gói miễn phí)."
# The Interactions API reports an exhausted quota as HTTP 429, or as an error event mid-stream.
_QUOTA_CODES = {"429", "RESOURCE_EXHAUSTED"}


class GeminiTTS:
    """Satisfies `TTSEngine`: PCM16 mono at `sample_rate`, streamed as the provider sends it."""

    def __init__(self, *, client: Any, model: str, voice: str, sample_rate: int = 16000) -> None:
        self.model = model
        self.voice = voice
        self.sample_rate = sample_rate
        # Hold the client itself: once collected it closes the HTTP client its `interactions` still use.
        self._client = client
        self._interactions = client.aio.interactions
        # One sentence at a time: the free tier counts requests per minute, and the director plays sentences in order.
        self._lock = asyncio.Lock()

    async def warm_up(self) -> None:
        # Nothing to load, and a test request would spend free quota (research R2).
        return None

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        async with self._lock:
            stream = None
            try:
                stream = await self._interactions.create(
                    model=self.model,
                    input=[{"type": "user_input", "content": [{"type": "text", "text": text}]}],
                    # Asking for 16 kHz l16 is rejected with HTTP 400 (T044); the default is l16 at 24 kHz.
                    response_format={"type": "audio"},
                    generation_config={"speech_config": [{"voice": self.voice}]},
                    stream=True,
                )
                carry = b""
                resampler: Resampler | None = None
                async for event in stream:
                    audio = self._audio(event)
                    if audio is None:
                        continue
                    pcm, rate = audio
                    # A delta may end inside a 2-byte sample; keep the odd byte for the next chunk.
                    pcm = carry + pcm
                    cut = len(pcm) - len(pcm) % 2
                    carry = pcm[cut:]
                    pcm = pcm[:cut]
                    if rate != self.sample_rate:
                        resampler = resampler or self._resampler(rate)
                        pcm = resampler(np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32767)
                    if pcm:
                        yield pcm
            except (_interactions.APIError, genai_errors.APIError) as exc:
                raise _api_error(exc) from None
            finally:
                if stream is not None:
                    await stream.close()

    def _resampler(self, rate: int) -> Resampler:
        try:
            return Resampler(rate, self.sample_rate)
        except ValueError:
            raise TTSEngineError(
                "config_error",
                f"Nguồn giọng chưa sẵn sàng: Gemini trả âm thanh {rate} Hz, không đổi được về {self.sample_rate} Hz.",
            ) from None

    def _audio(self, event: Any) -> tuple[bytes, int] | None:
        """The PCM in an audio delta and its rate; None for every other event. Raises on an error event."""
        event_type = getattr(event, "event_type", None)
        if event_type == "error":
            error = getattr(event, "error", None)
            code = str(getattr(error, "code", "") or "")
            if code in _QUOTA_CODES:
                raise TTSEngineError("quota_exhausted", QUOTA_MESSAGE)
            message = redact_text(str(getattr(error, "message", "") or ""))
            raise TTSEngineError("api_error", f"Gemini TTS lỗi ({code}): {message}")
        delta = getattr(event, "delta", None)
        if event_type != "step.delta" or getattr(delta, "type", None) != "audio":
            return None
        mime_type = getattr(delta, "mime_type", None)
        if mime_type and not mime_type.startswith(PCM_MIME_TYPE):
            raise TTSEngineError(
                "config_error", f"Nguồn giọng chưa sẵn sàng: Gemini trả âm thanh {mime_type}, cần {PCM_MIME_TYPE}."
            )
        rate = getattr(delta, "sample_rate", None) or PROVIDER_SAMPLE_RATE
        try:
            return base64.b64decode(getattr(delta, "data", "") or ""), rate
        except (binascii.Error, ValueError) as exc:
            raise TTSEngineError("api_error", "Gemini TTS lỗi: âm thanh trả về không giải mã được.") from exc


def _api_error(exc: Exception) -> TTSEngineError:
    """Map an SDK error to a Vietnamese message; the raw text may echo the request URL and key, so it is redacted."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status is None:
        return TTSEngineError("api_error", "Gemini TTS lỗi kết nối: không gọi được máy chủ, kiểm tra mạng.")
    if int(status) == 429:
        return TTSEngineError("quota_exhausted", QUOTA_MESSAGE)
    return TTSEngineError("api_error", f"Gemini TTS lỗi HTTP {status}: {redact_text(_message(exc))}")


def _message(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(getattr(exc, "message", "") or type(exc).__name__)
