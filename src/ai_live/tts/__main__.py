"""Chạy riêng khâu TTS (Điều IV): `uv run python -m ai_live.tts say "<câu>" --out out.wav`.

Thoát mã 0 khi ghi được file, 1 khi lỗi cấu hình hoặc TTS lỗi.
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
from ai_live.core.protocols import TTSEngine
from ai_live.tts.factory import TTSConfigError, create_tts


async def _say(tts: TTSEngine, text: str, out: Path) -> None:
    started = time.perf_counter()
    first_chunk_s: float | None = None
    pcm = bytearray()
    async for chunk in tts.synthesize(text):
        if first_chunk_s is None:
            first_chunk_s = time.perf_counter() - started
            print(f"Thời gian tới chunk đầu: {first_chunk_s:.2f} s")
        pcm += chunk
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(tts.sample_rate)
        wav.writeframes(bytes(pcm))
    seconds = len(pcm) / 2 / tts.sample_rate
    print(f"Đã ghi {out} ({seconds:.2f} s audio, {tts.sample_rate} Hz), tổng {time.perf_counter() - started:.2f} s")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m ai_live.tts")
    sub = parser.add_subparsers(dest="command", required=True)
    say = sub.add_parser("say", help="đọc một câu ra file WAV")
    say.add_argument("text")
    say.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        tts = create_tts(Settings())
    except (TTSConfigError, ValidationError) as exc:
        print(f"Lỗi cấu hình TTS_PROVIDER: {exc}")
        return 1
    try:
        asyncio.run(_say(tts, args.text, args.out))
    except Exception as exc:
        print(f"TTS lỗi: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
