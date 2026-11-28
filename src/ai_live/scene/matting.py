"""Background removal for uploaded product photos (feature 013, research R5–R8, data-model §6, §9, contracts/api.md §6).

Two ways, tried in order:
1. **Flat background** (white or one colour): flood fill from the picture border, on a worker thread of the app.
2. **Model** (complex background): an ONNX matting model (IS-Net or BiRefNet) in a low-priority child process
   (`python -m ai_live.scene.matting ...`), so a slow, crashing or memory-hungry model never stalls the event loop
   or the voice.

Only the alpha channel ever changes: R, G, B of every pixel stay as uploaded (FR-015). Every cut goes through
`assess_cut`; an unsure cut is reported as `failed` with a Vietnamese reason instead of reaching the live scene
(FR-014).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import time
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
from PIL import Image, ImageFilter

Method = Literal["already_transparent", "flat", "model"]
Result = Literal["removed", "failed", "kept"]
ModelKind = Literal["isnet", "birefnet"]

# R5: border ring used to find the background colour, and how close (Chebyshev on R, G, B) a pixel must be
# to count as background.
BORDER_PX = 2
COLOUR_TOLERANCE = 28
FLAT_BORDER_SHARE = 0.90

# R8 first values; tune on the SC-003 photo set (T044).
FG_RATIO_MIN = 0.05
FG_RATIO_MAX = 0.95
BORDER_FG_MAX = 0.25
UNCERTAIN_MAX = 0.12
LARGEST_COMPONENT_MIN = 0.85
UNCERTAIN_LOW = 26
UNCERTAIN_HIGH = 229

# R7: one model run at a time, killed after this many seconds; the child leaves cores for VieNeu.
MODEL_TIMEOUT_S: float = 60
MODEL_THREADS = 2
CHILD_ARGS: tuple[str, ...] = ("-m", "ai_live.scene.matting")
MODEL_SIZE = 1024

NO_MODEL_REASON = "chưa cài model tách nền"
LIVE_REASON = "đang live, bỏ nền phức tạp sau khi dừng show"
TIMEOUT_REASON = "tách nền quá lâu"
MODEL_UNSURE_REASON = "nền quá phức tạp, model không chắc"
NOT_FLAT_REASON = "nền không phẳng"
CHILD_ERROR_REASONS = {
    2: "lỗi gọi model tách nền",
    3: "không mở được model tách nền",
    4: "model tách nền không đọc được ảnh",
    5: "model tách nền bị lỗi khi chạy",
}

# Reasons that depend on conditions that may change (model installed later, show stopped): a re-upload runs
# again (data-model §9).
RETRYABLE_REASONS = (NO_MODEL_REASON, LIVE_REASON)


class MattingSettings(Protocol):
    matting_model_path: Path | None
    matting_during_show: bool


@dataclass
class CutResult:
    """The outcome of one background removal (data-model §6)."""

    image: Image.Image | None
    method: Method
    result: Result
    reason: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    ms: float = 0.0
    model: str | None = None


@dataclass(frozen=True)
class CutCheck:
    ok: bool
    reason: str | None
    metrics: dict[str, float]


# ---------------------------------------------------------------------------------------------------------------------
# Connected components on run-length segments: exact 4-connectivity without scipy, fast enough for ≤ 1280 px pictures.


def _runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Horizontal runs of True pixels as (row, start, end-exclusive), row-major order."""
    h, w = mask.shape
    padded = np.zeros((h, w + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    diff = np.diff(padded, axis=1)
    rows, starts = np.nonzero(diff == 1)
    _, ends = np.nonzero(diff == -1)
    return rows, starts, ends


def _components(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Label the 4-connected components of `mask`.

    Returns the runs (rows, starts, ends) and, for each run, the index of its component (0..n-1).
    """
    rows, starts, ends = _runs(mask)
    n = len(rows)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    if n:
        start_list = starts.tolist()
        end_list = ends.tolist()
        bounds = np.searchsorted(rows, np.arange(mask.shape[0] + 1)).tolist()
        for y in range(1, mask.shape[0]):
            i, i_end = bounds[y - 1], bounds[y]
            j, j_end = bounds[y], bounds[y + 1]
            while i < i_end and j < j_end:
                if start_list[i] < end_list[j] and start_list[j] < end_list[i]:
                    a, b = find(i), find(j)
                    if a != b:
                        parent[b] = a
                if end_list[i] < end_list[j]:
                    i += 1
                else:
                    j += 1
    roots = np.array([find(i) for i in range(n)], dtype=np.int64)
    _, labels = np.unique(roots, return_inverse=True)
    return rows, starts, ends, labels.reshape(-1)


def _largest_component_ratio(fg: np.ndarray) -> float:
    total = int(fg.sum())
    if total == 0:
        return 0.0
    _, starts, ends, labels = _components(fg)
    sizes = np.bincount(labels, weights=(ends - starts).astype(np.float64))
    return float(sizes.max() / total)


# ---------------------------------------------------------------------------------------------------------------------
# R8: confidence check, shared by both ways.


def assess_cut(alpha: np.ndarray, *, flat: bool) -> CutCheck:
    """Decide whether a cut is clean enough to offer; cheap metrics on the full-size alpha mask (research R8)."""
    alpha = np.asarray(alpha)
    fg = alpha >= 128
    total = alpha.size
    fg_count = int(fg.sum())
    fg_ratio = fg_count / total if total else 0.0
    border = np.concatenate([fg[0], fg[-1], fg[1:-1, 0], fg[1:-1, -1]])
    border_fg_ratio = float(border.mean()) if border.size else 0.0
    uncertain = int(((alpha >= UNCERTAIN_LOW) & (alpha <= UNCERTAIN_HIGH)).sum())
    uncertain_ratio = uncertain / fg_count if fg_count else 0.0
    largest = _largest_component_ratio(fg)
    metrics = {
        "fg_ratio": round(fg_ratio, 4),
        "border_fg_ratio": round(border_fg_ratio, 4),
        "uncertain_ratio": round(uncertain_ratio, 4),
        "largest_component_ratio": round(largest, 4),
    }
    reason: str | None = None
    if fg_ratio < FG_RATIO_MIN:
        reason = "gần như không còn gì sau khi bỏ nền"
    elif fg_ratio > FG_RATIO_MAX:
        reason = "không tách được nền"
    elif border_fg_ratio > BORDER_FG_MAX:
        reason = "sản phẩm dính viền ảnh, có thể bị cắt hoặc nền chưa bỏ hết"
    elif uncertain_ratio > UNCERTAIN_MAX:
        reason = "mép sản phẩm nhòe, không chắc đã tách đúng"
    elif flat and largest < LARGEST_COMPONENT_MIN:
        reason = "sản phẩm bị vỡ thành nhiều mảnh, có thể đã khoét mất phần cùng màu nền"
    return CutCheck(ok=reason is None, reason=reason, metrics=metrics)


def _apply_alpha(image: Image.Image, alpha: Image.Image) -> Image.Image | None:
    """Put `alpha` on the picture (RGB untouched) and crop to the alpha box, like 012 does."""
    out = image.convert("RGBA")
    out.putalpha(alpha)
    box = alpha.getbbox()
    return out.crop(box) if box else None


# ---------------------------------------------------------------------------------------------------------------------
# R5: flat background.


def remove_flat_background(image: Image.Image) -> CutResult:
    """Remove a white or single-colour background by flood fill from the border; failed when the border is not flat."""
    started = time.perf_counter()
    rgba = image.convert("RGBA")
    rgb = np.asarray(rgba)[..., :3].astype(np.int16)
    h, w = rgb.shape[:2]
    ring = np.ones((h, w), dtype=bool)
    if h > 2 * BORDER_PX and w > 2 * BORDER_PX:
        ring[BORDER_PX:-BORDER_PX, BORDER_PX:-BORDER_PX] = False
    border = rgb[ring]
    background = np.median(border, axis=0)
    near_border = np.abs(border - background).max(axis=1) <= COLOUR_TOLERANCE
    if near_border.mean() < FLAT_BORDER_SHARE:
        return CutResult(None, "flat", "failed", NOT_FLAT_REASON, ms=_ms(started))

    near = np.abs(rgb - background).max(axis=2) <= COLOUR_TOLERANCE
    rows, starts, ends, labels = _components(near)
    touching = (rows == 0) | (rows == h - 1) | (starts == 0) | (ends == w)
    border_labels = np.unique(labels[touching])
    is_background = np.isin(labels, border_labels)
    mask = np.full((h, w), 255, dtype=np.uint8)
    for y, s, e in zip(
        rows[is_background].tolist(), starts[is_background].tolist(), ends[is_background].tolist(), strict=True
    ):
        mask[y, s:e] = 0
    alpha = Image.fromarray(mask, "L").filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    check = assess_cut(np.asarray(alpha), flat=True)
    if not check.ok:
        return CutResult(None, "flat", "failed", check.reason, check.metrics, _ms(started))
    cut = _apply_alpha(rgba, alpha)
    if cut is None:
        return CutResult(None, "flat", "failed", "gần như không còn gì sau khi bỏ nền", check.metrics, _ms(started))
    return CutResult(cut, "flat", "removed", None, check.metrics, _ms(started))


# ---------------------------------------------------------------------------------------------------------------------
# R6: model pre/post-processing (no rembg; the same maths as its sessions).


def model_kind(path: Path) -> ModelKind | None:
    name = path.name.lower()
    if name.startswith("isnet"):
        return "isnet"
    if name.startswith("birefnet"):
        return "birefnet"
    return None


def preprocess(image: Image.Image, kind: ModelKind) -> np.ndarray:
    """RGB picture → NCHW float32 tensor of 1024², normalised the way the model was trained."""
    resized = image.convert("RGB").resize((MODEL_SIZE, MODEL_SIZE), Image.Resampling.LANCZOS)
    a = np.asarray(resized, dtype=np.float32)
    a = a / max(float(a.max()), 1e-6)
    if kind == "isnet":
        mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        std = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    else:
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    a = (a - mean) / std
    return np.ascontiguousarray(a.transpose(2, 0, 1)[np.newaxis], dtype=np.float32)


def postprocess(raw: np.ndarray, size: tuple[int, int], kind: ModelKind) -> Image.Image:
    """Model output → 8-bit mask the size of the source picture."""
    pred = np.asarray(raw, dtype=np.float32)[0, 0]
    if kind == "birefnet":
        pred = 1.0 / (1.0 + np.exp(-pred))
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / (hi - lo) if hi > lo else np.zeros_like(pred)
    mask = Image.fromarray((pred * 255).clip(0, 255).astype(np.uint8), "L")
    return mask.resize(size, Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------------------------------------------------
# R7: the parent side of the model run.

_semaphores: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


def _model_semaphore() -> asyncio.Semaphore:
    # One per event loop: an asyncio.Semaphore binds to the loop it first waits on.
    loop = asyncio.get_running_loop()
    semaphore = _semaphores.get(loop)
    if semaphore is None:
        semaphore = _semaphores[loop] = asyncio.Semaphore(1)
    return semaphore


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _has_see_through_pixels(image: Image.Image) -> bool:
    if "A" not in image.getbands() and "transparency" not in image.info:
        return False
    return image.convert("RGBA").getchannel("A").getextrema()[0] < 255


async def _run_model(image: Image.Image, model_path: Path) -> CutResult:
    name = model_path.name
    async with _model_semaphore():
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="ai_live_matting_") as tmp:
            src = Path(tmp) / "in.png"
            out = Path(tmp) / "mask.png"
            await asyncio.to_thread(image.convert("RGB").save, src)
            kwargs: dict[str, object] = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                *CHILD_ARGS,
                "--model",
                str(model_path),
                "--in",
                str(src),
                "--out",
                str(out),
                "--threads",
                str(MODEL_THREADS),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                **kwargs,  # type: ignore[arg-type]
            )
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), MODEL_TIMEOUT_S)
            except TimeoutError:
                process.kill()
                await process.wait()
                return CutResult(None, "model", "failed", TIMEOUT_REASON, ms=_ms(started), model=name)
            if process.returncode != 0:
                detail = (stderr or b"").decode("utf-8", "replace").strip().splitlines()
                reason = CHILD_ERROR_REASONS.get(
                    process.returncode or 0, f"model tách nền thoát mã {process.returncode}"
                )
                if detail:
                    reason = f"{reason} ({detail[-1][:160]})"
                return CutResult(None, "model", "failed", reason, ms=_ms(started), model=name)
            try:
                with Image.open(out) as raw_mask:
                    mask = raw_mask.convert("L")
            except OSError:
                return CutResult(None, "model", "failed", CHILD_ERROR_REASONS[5], ms=_ms(started), model=name)
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.Resampling.LANCZOS)
        check = await asyncio.to_thread(assess_cut, np.asarray(mask), flat=False)
        if not check.ok:
            reason = f"{MODEL_UNSURE_REASON} ({check.reason})"
            return CutResult(None, "model", "failed", reason, check.metrics, _ms(started), name)
        cut = await asyncio.to_thread(_apply_alpha, image, mask)
        if cut is None:
            return CutResult(None, "model", "failed", MODEL_UNSURE_REASON, check.metrics, _ms(started), name)
        return CutResult(cut, "model", "removed", None, check.metrics, _ms(started), name)


async def remove_background(
    image: Image.Image,
    *,
    has_alpha: bool | None = None,
    show_running: bool,
    settings: MattingSettings,
) -> CutResult:
    """Remove the background of an uploaded picture following data-model §9.

    `has_alpha` is the 012 upload flag: a 012 upload is cropped to its alpha box, so its pixels may all be opaque
    although the source had alpha. When it is None, the picture's own pixels decide.
    """
    started = time.perf_counter()
    see_through = has_alpha if has_alpha is not None else _has_see_through_pixels(image)
    if see_through:
        return CutResult(None, "already_transparent", "kept", ms=_ms(started))
    rgba = image.convert("RGBA")
    flat = await asyncio.to_thread(remove_flat_background, rgba)
    if flat.result == "removed":
        flat.ms = _ms(started)
        return flat
    model_path = settings.matting_model_path
    if model_path is None or not await asyncio.to_thread(Path(model_path).is_file):
        return CutResult(None, "model", "failed", NO_MODEL_REASON, flat.metrics, _ms(started))
    if show_running and not settings.matting_during_show:
        return CutResult(None, "model", "failed", LIVE_REASON, flat.metrics, _ms(started))
    cut = await _run_model(rgba, Path(model_path))
    cut.ms = _ms(started)
    return cut


# ---------------------------------------------------------------------------------------------------------------------
# The child process (contracts/api.md §6). Reads no .env and touches no network.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ai_live.scene.matting", description="Write a matting mask for one picture."
    )
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--in", dest="src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=MODEL_THREADS)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    # On Windows the parent already set BELOW_NORMAL_PRIORITY_CLASS; POSIX lowers it here.
    nice = getattr(os, "nice", None)
    if nice is not None:
        try:
            nice(10)
        except OSError:
            pass
    kind = model_kind(args.model)
    if kind is None:
        print(f"unknown model kind: {args.model.name}", file=sys.stderr)
        return 3
    try:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, args.threads)
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(args.model), sess_options=options, providers=["CPUExecutionProvider"])
    except Exception as exc:  # noqa: BLE001 - any loader failure is "cannot open the model"
        print(f"cannot open model: {exc}".splitlines()[0], file=sys.stderr)
        return 3
    try:
        with Image.open(args.src) as source:
            image = source.convert("RGB")
    except OSError as exc:
        print(f"cannot read image: {exc}".splitlines()[0], file=sys.stderr)
        return 4
    try:
        tensor = preprocess(image, kind)
        raw = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        postprocess(raw, image.size, kind).save(args.out)
    except Exception as exc:  # noqa: BLE001 - report any inference failure as exit 5
        print(f"inference failed: {exc}".splitlines()[0], file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
