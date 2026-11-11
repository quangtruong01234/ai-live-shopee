"""Remove frame-to-frame shimmer from generated base clips with a short temporal blur.

Video models leave a sub-pixel tremble whose direction flips almost every frame, while the real idle motion (breathing,
slight sway) spans many frames. A small binomial kernel over neighbouring frames cancels the flip and barely touches the
slow motion. This edits the offline base clips only (ADR-036); live frames are still generated in real time.

Run with the fork venv, which already has PyAV with libx264 (no new dependency):

    vendor/livetalking/.venv/Scripts/python scripts/avatar_clips/smooth_clips.py --radius 2 <dir>/clips/idle_01.mp4

Writes `<name>_smooth.mp4` next to each input and never overwrites the original.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
from math import comb
from pathlib import Path

import av
import numpy as np


def binomial_kernel(radius: int) -> np.ndarray:
    weights = np.array([comb(2 * radius, k) for k in range(2 * radius + 1)], dtype=np.float32)
    return weights / weights.sum()


def read_frames(path: Path) -> tuple[list[np.ndarray], Fraction]:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        rate = stream.average_rate or Fraction(25)
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(stream)]
    return frames, rate


def smooth(frames: list[np.ndarray], radius: int) -> list[np.ndarray]:
    """Temporal blur; ends are mirrored because the fork plays clips forward then backward (`mirror_index`)."""
    kernel = binomial_kernel(radius)
    stack = np.stack(frames).astype(np.float32)
    padded = np.concatenate([stack[radius:0:-1], stack, stack[-2 : -radius - 2 : -1]])
    out = np.zeros_like(stack)
    for offset, weight in enumerate(kernel):
        out += weight * padded[offset : offset + len(stack)]
    return [np.clip(f + 0.5, 0, 255).astype(np.uint8) for f in out]


def write_frames(path: Path, frames: list[np.ndarray], rate: Fraction, crf: int) -> None:
    height, width = frames[0].shape[:2]
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=rate)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": str(crf), "preset": "slow"}
        for array in frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(array, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clips", nargs="+", type=Path)
    parser.add_argument("--radius", type=int, default=1, help="1 = weights 1-2-1 over 3 frames, 2 = 1-4-6-4-1 over 5")
    parser.add_argument("--crf", type=int, default=14, help="x264 quality; lower is closer to lossless")
    args = parser.parse_args()
    for clip in args.clips:
        frames, rate = read_frames(clip)
        if len(frames) <= 2 * args.radius:
            raise SystemExit(f"{clip}: only {len(frames)} frames, too short for radius {args.radius}")
        target = clip.with_name(f"{clip.stem}_smooth{clip.suffix}")
        write_frames(target, smooth(frames, args.radius), rate, args.crf)
        print(f"{clip.name} -> {target.name}: {len(frames)} frames at {rate} fps")


if __name__ == "__main__":
    main()
