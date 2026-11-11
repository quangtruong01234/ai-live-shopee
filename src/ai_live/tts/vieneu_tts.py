"""VieNeu-TTS v3 Turbo on the laptop CPU through ONNX (ADR-024; 003 contracts/adapters.md §2, research R1, R5, R6).

`vieneu` and `numpy` are imported only when this source is used, so `TTS_PROVIDER=fake` never pays for them.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import threading
import wave
from collections.abc import AsyncIterator, Callable
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import Any

from ai_live.core.protocols import TTSEngineError
from ai_live.tts.resample import Resampler

WARM_UP_TEXT = "Dạ."
# Same cap as vieneu's own reference cloning; longer clips only slow the one-time encode.
MAX_REF_SECONDS = 8


def load_vieneu(model_cache: Path, threads: int) -> Any:
    """Default loader: point the Hugging Face cache at `model_cache`, then build the ONNX model (blocking)."""
    cache = str(model_cache)
    # huggingface_hub reads these once at import time; onnxruntime cannot load models through cache symlinks (R1).
    if "huggingface_hub" in sys.modules and (
        os.environ.get("HF_HUB_CACHE") != cache or os.environ.get("HF_HUB_DISABLE_SYMLINKS") != "1"
    ):
        raise TTSEngineError(
            "config_error",
            "huggingface_hub đã được nạp trước VieNeu nên không dùng được thư mục VIENEU_MODEL_CACHE; "
            "khởi động lại app.",
        )
    os.environ["HF_HUB_CACHE"] = cache
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
    try:
        vieneu = import_module("vieneu")
    except ImportError as exc:
        raise TTSEngineError(
            "config_error", f"Chưa cài thư viện vieneu ({exc}); chạy `uv sync` hoặc đặt TTS_PROVIDER=fake."
        ) from exc
    return vieneu.Vieneu(mode="v3turbo", backend="onnx", threads=threads)


class VieneuTTS:
    """`TTSEngine` over a local VieNeu model; one sentence at a time, generated in a worker thread."""

    def __init__(
        self,
        *,
        voice: str,
        cpu_threads: int,
        model_cache: Path,
        sample_rate: int = 16000,
        load_model: Callable[[int], Any] | None = None,
        ref_audio: Path | None = None,
    ) -> None:
        self.voice = voice
        self.ref_audio = ref_audio
        self.cpu_threads = cpu_threads
        self.model_cache = model_cache
        self.sample_rate = sample_rate
        # Tests inject a fake model here; the real loader downloads nothing once the cache is filled.
        self._load_model = load_model or partial(load_vieneu, model_cache)
        self._model: Any = None
        # Preset name, or the preset's speaker embedding plus the encoded reference clip once loaded.
        self._voice_arg: Any = voice
        self._load_error: TTSEngineError | None = None
        self._lock = asyncio.Lock()
        # The ONNX sessions are not safe to share; this also covers a worker still finishing after a cancelled caller.
        self._model_lock = threading.Lock()

    async def warm_up(self) -> None:
        async with self._lock:
            await self._ensure_loaded()

    async def _ensure_loaded(self) -> None:
        # A failed load is kept: retrying would block for seconds on every sentence and fail the same way.
        if self._load_error is not None:
            raise self._load_error
        if self._model is not None:
            return
        try:
            self._model = await asyncio.to_thread(self._load)
        except TTSEngineError as exc:
            self._load_error = exc
            raise

    def _load(self) -> Any:
        try:
            model = self._load_model(self.cpu_threads)
        except TTSEngineError:
            raise
        except Exception as exc:
            raise TTSEngineError("config_error", f"Không nạp được model VieNeu: {exc}") from exc
        voices = [voice_id for _label, voice_id in model.list_preset_voices()]
        if self.voice not in voices:
            raise TTSEngineError(
                "config_error", f"Không có giọng VieNeu '{self.voice}'. Giọng có sẵn: {', '.join(voices)}"
            )
        if model.sample_rate % self.sample_rate:
            raise TTSEngineError(
                "config_error", f"VieNeu trả tiếng {model.sample_rate} Hz, không hạ đúng về {self.sample_rate} Hz"
            )
        if self.ref_audio is not None:
            self._voice_arg = self._encode_ref(model, self.ref_audio)
        try:
            for _ in model.infer_stream(WARM_UP_TEXT, voice=self._voice_arg):
                pass
        except Exception as exc:
            raise TTSEngineError("config_error", f"VieNeu đọc thử không được: {exc}") from exc
        return model

    def _encode_ref(self, model: Any, path: Path) -> dict[str, Any]:
        """Encode the reference clip once, pinned to the preset's speaker embedding (research R1).

        The public cloning path needs a speaker-encoder download (an ADR); the private codec encoder is already cached.
        """
        import numpy as np

        try:
            with wave.open(str(path), "rb") as clip:
                if clip.getsampwidth() != 2:
                    raise wave.Error(f"cần PCM16, file có {8 * clip.getsampwidth()} bit")
                channels, rate = clip.getnchannels(), clip.getframerate()
                frames = clip.readframes(MAX_REF_SECONDS * rate)
        except (OSError, EOFError, wave.Error) as exc:
            raise TTSEngineError("config_error", f"Không đọc được VIENEU_REF_AUDIO ({path}): {exc}") from exc
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768
        wav = samples.reshape(-1, channels).mean(axis=1, dtype=np.float32)
        encode = getattr(getattr(model, "engine", None), "_encode_ref_wav", None)
        if encode is None:
            raise TTSEngineError(
                "config_error", "Bản vieneu đang cài không còn hàm mã hóa đoạn mẫu; bỏ trống VIENEU_REF_AUDIO."
            )
        try:
            return {"speaker_emb": model.get_preset_voice(self.voice)["speaker_emb"], "codes": encode(wav, rate)}
        except Exception as exc:
            raise TTSEngineError("config_error", f"VieNeu không mã hóa được VIENEU_REF_AUDIO ({path}): {exc}") from exc

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        async with self._lock:
            await self._ensure_loaded()
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
            stop = threading.Event()
            worker = asyncio.ensure_future(asyncio.to_thread(self._produce, text, loop, queue, stop))
            try:
                while True:
                    kind, value = await queue.get()
                    if kind == "chunk":
                        yield value
                    elif kind == "error":
                        raise TTSEngineError("model_error", f"VieNeu lỗi khi đọc câu: {value}") from value
                    else:
                        return
            finally:
                # FR-014: a skipped sentence stops generating at the next chunk boundary.
                stop.set()
                await worker

    def _produce(
        self, text: str, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[tuple[str, Any]], stop: threading.Event
    ) -> None:
        def send(item: tuple[str, Any]) -> None:
            with contextlib.suppress(RuntimeError):  # the loop closed while this thread was still running
                loop.call_soon_threadsafe(queue.put_nowait, item)

        resample = Resampler(self._model.sample_rate, self.sample_rate)
        with self._model_lock:
            stream = self._model.infer_stream(text, voice=self._voice_arg)
            try:
                for chunk in stream:
                    pcm = resample(chunk)
                    if pcm:
                        send(("chunk", pcm))
                    if stop.is_set():
                        break
            except Exception as exc:
                send(("error", exc))
                return
            finally:
                stream.close()
        send(("end", None))
