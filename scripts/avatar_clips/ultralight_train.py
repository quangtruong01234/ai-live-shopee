"""Train an Ultralight-Digital-Human UNet that the LiveTalking fork can load (ADR-060).

Runs on Kaggle through `train_ultralight.ipynb`, which embeds a copy of this file (rebuild the notebook after edits).
It also runs on the laptop for a short check on a small dataset.

Why not upstream `train.py`:
- After upstream commit b2dd34a (2026-05-23) the UNet state_dict keys no longer match the fork's
  `avatars/ultralight/unet.py`, so the model class is imported from a checkout of the pinned pre-refactor commit
  (ff0454d), whose hubert UNet is the fork's.
- The `datasetsss.py` of that commit fails in `__len__` (it compares a numpy array), and its `train.py` has no
  resume, no mixed precision and saves only every 5 epochs; a Kaggle session stops at 12 h.

The data pipeline matches the fork's inference exactly: the crop from landmarks 1, 31 and 52 resized to 168x168, the
inner 160x160, the black rectangle (5, 5, 150, 145) over the mouth area, a random frame of the same video as the
reference, and 8 HuBERT frames (16 x 1024 -> 16x32x32) centred on the video frame. Loss: L1 + 0.01 x MSE of VGG19
conv3_3 features, as upstream. SyncNet is left out: upstream removed it, its author saw no visible difference.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

CROP_SIZE = 168
INNER = slice(4, 164)
MASK_RECT = (5, 5, 150, 145)  # x, y, w, h; the fork masks the same box at inference
AUDIO_FRAMES_EACH_SIDE = 4  # aud_hu.npy has 2 HuBERT frames per video frame, so 8 rows give 16 x 1024
VGG_CONV3_3 = 15  # vgg19.features[:15] ends at conv3_3 (index 14), the upstream perceptual layer


def crop_box(lms: np.ndarray) -> tuple[int, int, int, int]:
    """Lower-face square used by upstream training and by the fork's genavatar.py."""
    xmin = int(lms[1][0])
    ymin = int(lms[52][1])
    xmax = int(lms[31][0])
    return xmin, ymin, xmax, ymin + (xmax - xmin)


class LowerFaceDataset(Dataset):
    """All crops are decoded once into memory: a 3-minute video is about 400 MB at 168x168, and Kaggle has few CPUs."""

    def __init__(self, dataset_dir: Path, limit: int | None = None) -> None:
        frames_dir = dataset_dir / "full_body_img"
        audio = np.load(dataset_dir / "aud_hu.npy").astype(np.float32)  # [N, 2, 1024]
        count = min(len(list(frames_dir.glob("*.jpg"))), audio.shape[0])
        if limit:
            count = min(count, limit)
        if count < 2:
            raise ValueError(f"{dataset_dir}: cần ít nhất 2 khung có tiếng, đang có {count}")
        self.audio = audio
        self.crops = np.empty((count, CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8)
        self.boxes: list[tuple[int, int, int, int]] = []
        for i in range(count):
            lms = np.loadtxt(dataset_dir / "landmarks" / f"{i}.lms", dtype=np.float32).astype(np.int32)
            box = crop_box(lms)
            img = cv2.imread(str(frames_dir / f"{i}.jpg"))
            x0, y0, x1, y1 = box
            region = img[y0:y1, x0:x1]
            if region.size == 0:
                raise ValueError(f"Khung {i}: vùng cắt {box} rỗng, điểm mặt sai")
            self.crops[i] = cv2.resize(region, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_AREA)
            self.boxes.append(box)

    def __len__(self) -> int:
        return len(self.crops)

    def audio_window(self, index: int) -> torch.Tensor:
        left, right = index - AUDIO_FRAMES_EACH_SIDE, index + AUDIO_FRAMES_EACH_SIDE
        window = np.zeros((right - left, *self.audio.shape[1:]), dtype=np.float32)
        lo, hi = max(left, 0), min(right, self.audio.shape[0])
        window[lo - left : hi - left] = self.audio[lo:hi]
        return torch.from_numpy(window.reshape(16, 32, 32))

    def sample(self, index: int, ref_index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        real = self.crops[index][INNER, INNER].copy()
        masked = cv2.rectangle(real.copy(), MASK_RECT, (0, 0, 0), -1)
        ref = self.crops[ref_index][INNER, INNER]

        def to_tensor(img: np.ndarray) -> torch.Tensor:
            return torch.from_numpy(img.transpose(2, 0, 1).astype(np.float32) / 255.0)

        inputs = torch.cat([to_tensor(ref), to_tensor(masked)], dim=0)
        return inputs, to_tensor(real), self.audio_window(index)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.sample(index, random.randrange(len(self)))


class PerceptualLoss(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        from torchvision.models import VGG19_Weights, vgg19

        # IMAGENET1K_V1 is what upstream's `pretrained=True` loads; frozen because only the UNet is optimised.
        self.features = vgg19(weights=VGG19_Weights.IMAGENET1K_V1).features[:VGG_CONV3_3].eval()
        self.features.requires_grad_(False)
        # GTX 16xx cards return NaN from VGG19 in fp16 (seen on the laptop's 1650 Ti, 2026-11-18) while the UNet itself
        # is fine; on the first non-finite result the VGG drops to fp32 for good and the UNet keeps its fp16 speed-up.
        self.fp16_ok = True

    def _loss(self, pred: torch.Tensor, real: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            target = self.features(real)
        return nn.functional.mse_loss(self.features(pred).float(), target.float())

    def forward(self, pred: torch.Tensor, real: torch.Tensor) -> torch.Tensor:
        if self.fp16_ok:
            loss = self._loss(pred, real)
            if torch.isfinite(loss):
                return loss
            self.fp16_ok = False
            print("VGG19 fp16 ra NaN/inf trên GPU này, chuyển perceptual loss sang fp32", flush=True)
        with torch.autocast(pred.device.type, enabled=False):
            return self._loss(pred.float(), real.float())


def load_model_class(ultralight_dir: Path) -> type[nn.Module]:
    sys.path.insert(0, str(ultralight_dir))
    from unet import Model  # the pinned pre-refactor upstream checkout

    return Model


def save_preview(net: nn.Module, dataset: LowerFaceDataset, path: Path, device: str) -> None:
    """Fixed frames, reference = first frame, so previews of different epochs are comparable.

    Runs in fp32 like the fork's inference, so a preview shows what the live avatar will show.
    """
    picks = np.linspace(0, len(dataset) - 1, num=min(6, len(dataset)), dtype=int)
    batch = [dataset.sample(int(i), 0) for i in picks]
    inputs = torch.stack([b[0] for b in batch]).to(device)
    audio = torch.stack([b[2] for b in batch]).to(device)
    net.eval()
    with torch.no_grad():
        pred = np.nan_to_num(net(inputs, audio).float().cpu().numpy())
    net.train()
    rows = []
    for (_, real, _), out in zip(batch, pred, strict=True):
        real_img = (real.numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
        pred_img = (out.transpose(1, 2, 0) * 255).clip(0, 255).astype(np.uint8)
        rows.append(np.concatenate([real_img, pred_img], axis=1))
    cv2.imwrite(str(path), np.concatenate(rows, axis=0))


def export_state_dict(net: nn.Module, path: Path) -> None:
    """Plain fp32 state_dict: the fork does `Model(6, 'hubert').load_state_dict(torch.load(...))`."""
    torch.save({k: v.detach().float().cpu() for k, v in net.state_dict().items()}, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset_dir", type=Path, required=True)
    parser.add_argument("--ultralight_dir", type=Path, required=True, help="checkout of the pinned upstream commit")
    parser.add_argument("--save_dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--num_workers", type=int, default=2)
    parser.add_argument("--amp", action="store_true", help="fp16 autocast + GradScaler (tensor cores on T4)")
    parser.add_argument("--save_every", type=int, default=5, help="preview, history and last.pt every N epochs")
    parser.add_argument("--pth_every", type=int, default=0, help="keep an epoch_NNN.pth every N epochs (0: save_every)")
    parser.add_argument("--resume", type=Path, default=None, help="a last.pt written by this script")
    parser.add_argument("--max_minutes", type=float, default=0, help="stop before the next epoch would pass this")
    parser.add_argument("--bench_steps", type=int, default=0, help="time this many steps, print img/s, exit")
    parser.add_argument("--limit_frames", type=int, default=0, help="use only the first N frames (quick checks)")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    started = time.monotonic()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    amp = args.amp and device == "cuda"
    args.save_dir.mkdir(parents=True, exist_ok=True)

    dataset = LowerFaceDataset(args.dataset_dir, limit=args.limit_frames or None)
    print(f"Dữ liệu: {len(dataset)} khung, nạp trong {time.monotonic() - started:.0f} s", flush=True)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        drop_last=len(dataset) > args.batch_size,
        num_workers=args.num_workers,
        pin_memory=device == "cuda",
        persistent_workers=args.num_workers > 0,
    )

    net = load_model_class(args.ultralight_dir)(6, "hubert").to(device)
    perceptual = PerceptualLoss().to(device)
    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr)
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    l1 = nn.L1Loss()

    start_epoch = 0
    history: list[dict] = []
    if args.resume and args.resume.exists():
        state = torch.load(args.resume, map_location=device, weights_only=False)
        net.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scaler.load_state_dict(state["scaler"])
        start_epoch = state["epoch"] + 1
        history = state.get("history", [])
        print(f"Tiếp tục từ {args.resume}, epoch {start_epoch}", flush=True)

    def step(batch: tuple[torch.Tensor, ...]) -> tuple[float, float]:
        inputs, real, audio = (t.to(device, non_blocking=True) for t in batch)
        with torch.autocast("cuda", dtype=torch.float16, enabled=amp):
            pred = net(inputs, audio)
            pixel = l1(pred.float(), real)
            loss = pixel + 0.01 * perceptual(pred, real)
        optimizer.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        return loss.item(), pixel.item()

    net.train()
    if args.bench_steps:
        done, timed_from, images = 0, 0.0, 0
        warmup = min(3, args.bench_steps)
        while done < args.bench_steps + warmup:
            for batch in loader:
                if done == warmup:
                    if device == "cuda":
                        torch.cuda.synchronize()
                    timed_from = time.monotonic()
                step(batch)
                if done >= warmup:
                    images += batch[0].shape[0]
                done += 1
                if done >= args.bench_steps + warmup:
                    break
        if device == "cuda":
            torch.cuda.synchronize()
        seconds = time.monotonic() - timed_from
        peak_gb = torch.cuda.max_memory_allocated() / 1e9 if device == "cuda" else 0.0
        result = {"amp": amp, "img_per_s": round(images / seconds, 2), "peak_vram_gb": round(peak_gb, 2)}
        print("BENCH " + json.dumps(result), flush=True)
        return

    epoch_seconds: list[float] = []
    for epoch in range(start_epoch, args.epochs):
        epoch_started = time.monotonic()
        losses, pixels = [], []
        for batch in loader:
            loss, pixel = step(batch)
            if not math.isfinite(loss):
                raise RuntimeError(f"Epoch {epoch}: loss = {loss}. Thử chạy lại không có --amp.")
            losses.append(loss)
            pixels.append(pixel)
        seconds = time.monotonic() - epoch_started
        epoch_seconds.append(seconds)
        record = {
            "epoch": epoch,
            "loss": round(float(np.mean(losses)), 5),
            "l1": round(float(np.mean(pixels)), 5),
            "seconds": round(seconds, 1),
            "img_per_s": round(len(losses) * args.batch_size / seconds, 1),
        }
        history.append(record)
        print("EPOCH " + json.dumps(record), flush=True)

        last = epoch == args.epochs - 1
        elapsed_min = (time.monotonic() - started) / 60
        next_epoch_min = max(epoch_seconds[-3:]) / 60
        out_of_time = bool(args.max_minutes) and elapsed_min + next_epoch_min > args.max_minutes
        if (epoch + 1) % args.save_every == 0 or last or out_of_time:
            # Each export is about 50 MB; keeping fewer keeps a 200-epoch Kaggle output small enough to download.
            if (epoch + 1) % (args.pth_every or args.save_every) == 0 or last or out_of_time:
                export_state_dict(net, args.save_dir / f"epoch_{epoch:03d}.pth")
            save_preview(net, dataset, args.save_dir / f"preview_{epoch:03d}.jpg", device)
            # Written last and replaced atomically: a session killed mid-save still leaves a usable last.pt.
            tmp = args.save_dir / "last.pt.tmp"
            state = {
                "epoch": epoch,
                "model": net.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "history": history,
                "args": {k: str(v) for k, v in vars(args).items()},
            }
            torch.save(state, tmp)
            tmp.replace(args.save_dir / "last.pt")
            (args.save_dir / "history.json").write_text(json.dumps(history, indent=1))
        if out_of_time and not last:
            print(f"Dừng ở epoch {epoch} vì sắp hết {args.max_minutes:.0f} phút; chạy lại với --resume.", flush=True)
            break

    export_state_dict(net, args.save_dir / "ultralight.pth")
    print(f"Xong: {args.save_dir / 'ultralight.pth'}", flush=True)


if __name__ == "__main__":
    main()
