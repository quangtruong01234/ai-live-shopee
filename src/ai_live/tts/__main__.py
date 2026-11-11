"""Run the TTS stage on its own (constitution IV).

- `uv run python -m ai_live.tts say "<câu>" --out out.wav` writes the sentence to a WAV file.
- `uv run python -m ai_live.tts normalize "<câu>"` prints what the voice source would be sent, without building one.

Exit code 0 on success, 1 on a config or TTS error.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

from pydantic import ValidationError

from ai_live.core.config import Settings
from ai_live.core.protocols import TTSEngineError
from ai_live.tts.factory import TTSConfigError, create_tts, load_normalizer
from ai_live.tts.speech import SpeechTTS


class _OutputError(Exception):
    """The WAV file cannot be written; kept apart from voice-source errors so the message names the file."""


async def _say(tts: SpeechTTS, text: str, out: Path) -> None:
    # Checked before warm-up: a cloud source would otherwise spend quota on a sentence that cannot be saved.
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _OutputError(f"Không ghi được file {out}: {exc}") from exc
    # Same order as the app: a local model loads here, so the first-chunk time below is a warm one.
    await tts.warm_up()
    print(f"Nguồn giọng: {tts.usage.provider}")
    print(f"Chữ gửi đi: {tts.normalize(text)}")
    started = time.perf_counter()
    first_chunk_s: float | None = None
    pcm = bytearray()
    async for chunk in tts.synthesize(text):
        if first_chunk_s is None:
            first_chunk_s = time.perf_counter() - started
            print(f"Thời gian tới chunk đầu: {first_chunk_s:.2f} s")
        pcm += chunk
    # The free cloud quota is counted in characters (FR-012).
    print(f"Số ký tự đã gửi: {tts.usage.chars}")
    # Written only after the whole sentence arrived, so a failed call leaves no half-file behind.
    # The file is opened separately: `wave.open(path)` failing leaves a half-built writer whose `__del__` raises.
    try:
        with out.open("wb") as file, wave.open(file, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(tts.sample_rate)
            wav.writeframes(bytes(pcm))
    except OSError as exc:
        raise _OutputError(f"Không ghi được file {out}: {exc}") from exc
    seconds = len(pcm) / 2 / tts.sample_rate
    print(f"Đã ghi {out} ({seconds:.2f} s audio, {tts.sample_rate} Hz), tổng {time.perf_counter() - started:.2f} s")


def _normalize(text: str) -> int:
    # Only Settings and the abbreviation table: checking the spoken form must not need a voice source (FR-010).
    try:
        normalize = load_normalizer(Settings())
    except (TTSConfigError, ValidationError) as exc:
        print(f"Lỗi cấu hình: {exc}")
        return 1
    print(normalize(text))
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m ai_live.tts")
    sub = parser.add_subparsers(dest="command", required=True)
    say = sub.add_parser("say", help="đọc một câu ra file WAV")
    say.add_argument("text")
    say.add_argument("--out", type=Path, required=True)
    normalize = sub.add_parser("normalize", help="in chữ đã chuẩn hóa sẽ gửi cho nguồn giọng")
    normalize.add_argument("text")
    args = parser.parse_args(argv)

    if args.command == "normalize":
        return _normalize(args.text)

    try:
        tts = create_tts(Settings())
    except (TTSConfigError, ValidationError) as exc:
        print(f"Lỗi cấu hình TTS_PROVIDER: {exc}")
        return 1
    try:
        asyncio.run(_say(tts, args.text, args.out))
    except _OutputError as exc:
        print(exc)
        return 1
    except TTSEngineError as exc:
        print(f"TTS lỗi ({exc.kind}): {exc.message}")
        return 1
    except Exception as exc:
        print(f"TTS lỗi: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
