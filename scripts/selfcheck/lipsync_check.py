"""Records a lip-sync run on the fork and checks it, so a run can be judged without anyone watching the host page.

Needs the fork (`scripts/livetalking/run.ps1`) started with `AILIVE_RECORD_DIR` set, the app running with
`APP_ENV=dev` and `AVATAR_MODE=livetalking`, and the host page connected (the button "Bắt đầu" pressed once).

    uv run python scripts/selfcheck/lipsync_check.py --name t062 --text "Câu một." --text "Câu hai."
    uv run python scripts/selfcheck/lipsync_check.py --name wav1 --wav out/t052/sample.wav --idle 5

Each `--text` goes through TTS (`/api/debug/speak`), each `--wav` straight to the renderer (`/api/debug/speak-audio`);
both return after the host finished playing. Then the recording stops and the fork's analyzer
(`ailive_ext.analyze`) writes `<prefix>.report.json`, `.sheet.jpg` and `.mouth.jpg` next to the recording.
`<prefix>.driver.json` keeps what the app answered for each line (first-frame time, render fps).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ai_live.core.config import Settings

REPO = Path(__file__).resolve().parents[2]
FORK_DIR = REPO / "vendor" / "livetalking"


def _session(fork: httpx.Client) -> str:
    sessions = fork.get("/ailive/health").json().get("sessions") or []
    if not sessions:
        sys.exit("Fork chưa có phiên: mở http://127.0.0.1:8000/host và bấm 'Bắt đầu' trước.")
    return sessions[0]


def _line(what: dict[str, str], response: httpx.Response, t0: float) -> dict[str, object]:
    return dict(what, status=response.status_code, body=response.json(), took_s=round(time.monotonic() - t0, 2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="recording name under AILIVE_RECORD_DIR")
    parser.add_argument("--text", action="append", default=[], help="a line spoken through TTS (repeatable)")
    parser.add_argument("--wav", action="append", default=[], type=Path, help="a 16 kHz mono WAV (repeatable)")
    parser.add_argument("--idle", type=float, default=3.0, help="seconds recorded before, between and after lines")
    parser.add_argument("--app", default=None, help="app base URL (default http://127.0.0.1:<APP_PORT>)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # Vietnamese messages on a cp1252 Windows console
    if not args.text and not args.wav:
        parser.error("give at least one --text or --wav")

    settings = Settings()
    app_url = args.app or f"http://127.0.0.1:{settings.app_port}"
    fork = httpx.Client(base_url=settings.livetalking_url, timeout=30)
    app = httpx.Client(base_url=app_url, timeout=300)
    sid = _session(fork)

    started = fork.post("/ailive/record/start", params={"sessionid": sid, "name": args.name})
    if started.status_code != 200:
        sys.exit(f"Không bật được ghi: {started.status_code} {started.text}")
    prefix = Path(started.json()["prefix"])
    lines = []
    try:
        print(f"Đang ghi {prefix}")
        time.sleep(args.idle)
        for text in args.text:
            t0 = time.monotonic()
            r = app.post("/api/debug/speak", json={"text": text})
            lines.append(_line({"text": text}, r, t0))
            time.sleep(args.idle)
        for wav in args.wav:
            t0 = time.monotonic()
            r = app.post(
                "/api/debug/speak-audio",
                content=wav.read_bytes(),
                headers={"Content-Type": "audio/wav", "X-Filename": wav.name},
            )
            lines.append(_line({"wav": str(wav)}, r, t0))
            time.sleep(args.idle)
    finally:
        summary = fork.post("/ailive/record/stop", params={"sessionid": sid}, timeout=120).json()
    Path(f"{prefix}.driver.json").write_text(
        json.dumps({"recording": summary, "lines": lines}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for line in lines:
        print(f"  {line['status']} {line.get('text') or line.get('wav')}: {line['body']} ({line['took_s']} s)")

    python = settings.livetalking_python
    if not python.is_absolute():
        python = REPO / python
    result = subprocess.run([str(python), "-m", "ailive_ext.analyze", str(prefix)], cwd=FORK_DIR)
    failed_lines = any(line["status"] != 200 for line in lines)
    return 1 if failed_lines or result.returncode != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
