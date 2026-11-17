"""Read the fixed mouth sentence set aloud in the host's voice (010 FR-007), one WAV per sentence.

The fork's measurement tool (`ailive_ext/mouth_eval`) renders the avatar from these files, so every run of every mouth
method hears exactly the same audio. Audio is the host's voice, so it stays outside git (`out/` is ignored).
Run: `TTS_PROVIDER=vieneu uv run python scripts/mouth/synth_sentences.py [--set data/eval/mouth_sentences.json]
[--out out/mouth/sentences]`.
Sentences whose WAV already exists for the same text are skipped, so a run cut short can be restarted.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import wave
from pathlib import Path

from ai_live.core.config import Settings
from ai_live.tts.factory import create_tts


def _text_key(text: str, provider: str) -> str:
    return hashlib.sha1(f"{provider}\n{text}".encode()).hexdigest()[:12]


def _load(set_path: Path, out: Path) -> tuple[list[dict], dict]:
    # A one-off CLI: blocking file I/O around the TTS calls holds up nothing else.
    sentences = json.loads(set_path.read_text(encoding="utf-8"))["sentences"]
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return sentences, manifest


async def _run(set_path: Path, out: Path) -> int:
    sentences, manifest = _load(set_path, out)
    manifest_path = out / "manifest.json"
    settings = Settings()
    tts = create_tts(settings)
    await tts.warm_up()
    for item in sentences:
        key = _text_key(item["text"], settings.tts_provider)
        wav_path = out / f"{item['id']}.wav"
        if wav_path.exists() and manifest.get(item["id"], {}).get("key") == key:
            continue
        started = time.perf_counter()
        pcm = bytearray()
        async for chunk in tts.synthesize(item["text"]):
            pcm += chunk
        with wav_path.open("wb") as file, wave.open(file, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(tts.sample_rate)
            wav.writeframes(bytes(pcm))
        seconds = len(pcm) / 2 / tts.sample_rate
        manifest[item["id"]] = {"key": key, "group": item["group"], "text": item["text"], "seconds": round(seconds, 2)}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{item['id']}: {seconds:.1f} s audio trong {time.perf_counter() - started:.1f} s")
    print(f"Xong {len(sentences)} câu ở {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="synth_sentences")
    parser.add_argument("--set", type=Path, default=Path("data/eval/mouth_sentences.json"))
    parser.add_argument("--out", type=Path, default=Path("out/mouth/sentences"))
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.set, args.out))


if __name__ == "__main__":
    sys.exit(main())
