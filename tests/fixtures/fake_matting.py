"""Stand-in for the background-removal child process (013 contracts/api.md §6), so tests never need the real model.

Run as a script with the same arguments as `python -m ai_live.scene.matting`:

    python tests/fixtures/fake_matting.py --model <file.onnx> --in <input.png> --out <mask.png> [--threads 2]

`FAKE_MATTING_MODE` picks the behaviour:
- `ellipse` (default): writes a confident mask, an opaque ellipse in the middle of the picture;
- `uncertain`: writes a mask where most product pixels sit between alpha 26 and 229 (the model "is not sure");
- `sleep`: sleeps `FAKE_MATTING_SLEEP` seconds (default 30) before writing the ellipse, to hit the parent's timeout;
- `exit3` / `exit4` / `exit5`: exits with that code and one line on stderr (model / image / inference error).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from PIL import Image, ImageDraw

MODE_ENV = "FAKE_MATTING_MODE"
SLEEP_ENV = "FAKE_MATTING_SLEEP"
SCRIPT = __file__


def _mask(size: tuple[int, int], fill: int) -> Image.Image:
    w, h = size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse((w // 4, h // 6, 3 * w // 4, 5 * h // 6), fill=fill)
    return mask


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--in", dest="src", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threads", type=int, default=2)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    mode = os.environ.get(MODE_ENV, "ellipse")
    if mode.startswith("exit"):
        code = int(mode[4:])
        print(f"fake matting error {code}", file=sys.stderr)
        return code
    if mode == "sleep":
        time.sleep(float(os.environ.get(SLEEP_ENV, "30")))
    try:
        with Image.open(args.src) as image:
            size = image.size
    except OSError as exc:
        print(f"cannot read image: {exc}", file=sys.stderr)
        return 4
    mask = _mask(size, 128 if mode == "uncertain" else 255)
    mask.save(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
