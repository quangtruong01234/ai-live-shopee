"""The new room behind the host, app side (014 adapters.md §4, data-model §5, events.md; FR-006, FR-007, FR-010).

The controller draws the backdrop plate from the loaded scene set, hands it to the renderer (`BackgroundSink`), and
keeps the status the control page shows: whether the live frame really shows the new room and, if not, why. The fork
decides per frame; this side only follows what the fork reports in `hello.background` and its error messages. Nothing
here may stop the show: a failed draw or a broken manifest falls back to the original room.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import zlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ai_live.core.events import Event, EventBus, EventType
from ai_live.core.logging import log_event
from ai_live.core.protocols import BackgroundSink, ForkBackgroundStatus
from ai_live.scene.backdrop import BackdropResult, LightStats, render_backdrop
from ai_live.scene.layout import LABEL_FONT_RATIO, estimate_label_box, label_lines
from ai_live.scene.models import BackgroundConfig, SceneSet
from ai_live.scene.render import compose_still
from ai_live.scene.shop_photo import ShopPhoto

logger = logging.getLogger("ai_live.scene")

# The fork frame before any manifest or `hello` says otherwise (the 009 estimate; contracts/fork-protocol.md §2).
DEFAULT_FRAME = (480, 832)
MANIFEST = Path("background") / "manifest.json"
REVIEW = Path("background") / "review.jpg"
PREVIEW_FRAME = Path("background") / "preview_frame.png"
STYLE_NAMES = {"goc": "phòng gốc", "ke_hang": "kệ hàng", "bang_shop": "bảng tên shop", "anh_shop": "ảnh shop"}
# The fork's label look (ailive_ext/label.py): white letters, dark outline.
_LABEL_TEXT = (255, 255, 255)
_LABEL_STROKE = (20, 20, 20)
_LABEL_STROKE_RATIO = 0.08

RenderFn = Callable[
    [BackgroundConfig, dict[str, Image.Image], tuple[int, int], int, LightStats | None, ShopPhoto | None],
    BackdropResult,
]


class BackgroundController:
    def __init__(
        self,
        renderer: Any,
        bus: EventBus,
        character_dir: Path | None,
        *,
        render: RenderFn = render_backdrop,
        character_id: str | None = None,
    ) -> None:
        # The static renderer has no fork frame to composite into: nothing is ever sent (research R14).
        self._sink: BackgroundSink | None = renderer if isinstance(renderer, BackgroundSink) else None
        self._bus = bus
        self._character_dir = character_dir
        # Named in the fix commands the operator copies (`background-prepare <id>`).
        self._character_id = character_id or (character_dir.name if character_dir is not None else "<character_id>")
        self._render = render
        self._error: str | None = None  # the fork error already shown as a scene error
        self._manifest: dict[str, Any] | None = None
        self._config = BackgroundConfig()  # the original room until a scene set says otherwise
        self._result: BackdropResult | None = None
        self._plate_ms: float | None = None
        self._failed = False
        self._fork_known = False  # a `hello` arrived (with or without a background block)
        self._fork: ForkBackgroundStatus | None = None
        self._given: bytes | None = None
        self._given_set = False
        self._last: dict[str, Any] | None = None
        self._changed_at = _now()
        self._lock = asyncio.Lock()
        # Told when the room viewers see may have changed (the scene redraws its still with it).
        self._room_listeners: list[Callable[[], None]] = []
        self._room_cache: tuple[Image.Image, bytes, Image.Image | None] | None = None

    async def start(self) -> None:
        self._manifest = await asyncio.to_thread(self._read_manifest)
        if self._sink is not None:
            self._sink.add_background_status_listener(self._on_fork_status)

    # ---------- inputs ----------

    async def on_scene_loaded(self, scene: SceneSet) -> None:
        """Draw the plate for a newly loaded scene set (startup, content replace, 012 "Áp dụng bộ mới")."""
        async with self._lock:
            config = scene.background
            art = {} if scene.blocked else {pid: a.image for pid, a in scene.art.items() if _usable(a)}
            width, height = self._frame_size()
            desk_top = self._desk_top(scene, height)
            light = LightStats.from_manifest((self._manifest or {}).get("light"))
            started = time.perf_counter()
            try:
                photo = None if scene.blocked else scene.shop_photo
                result = await asyncio.to_thread(self._render, config, art, (width, height), desk_top, light, photo)
                failed = False
            except Exception:
                logger.exception("background plate failed")
                result, failed = None, True
            # Swapped together once drawn: while the plate is drawing the status keeps the previous set.
            self._config, self._result, self._failed = config, result, failed
            self._plate_ms = round((time.perf_counter() - started) * 1000, 1)
            self._push(redrawn=True)
            self._started()
            self._room_changed()

    def _on_fork_status(self, status: ForkBackgroundStatus | None) -> None:
        # Called on every `hello` (also after a fork restart) and on `background_rejected` / `background_failed`.
        self._fork_known, self._fork = True, status
        self._push()
        error = status.reason if status is not None and _is_fork_error(status.reason) else None
        if error is None:
            self._error = None
            self._started()  # a new `hello`
            return
        current = self._publish_if_changed()
        if error != self._error:
            # Shown like the other scene errors (red on the control page's scene line); the show goes on (FR-010).
            self._error = error
            message = f"Nền sau host: {current['fallback_message']}"
            self._bus.publish(Event(EventType.SCENE, {"kind": "error", "message": message}))

    # ---------- outputs ----------

    def status(self) -> dict[str, Any]:
        """`GET /api/scene/background` (data-model §5)."""
        current = self._compute()
        return {**current, "changed_at": self._changed_at}

    def frames(self) -> int:
        """How many frames have a mask: the fork's count when it told us, else the manifest's."""
        if self._fork is not None and self._fork.frames > 0:
            return self._fork.frames
        frames = (self._manifest or {}).get("frames")
        return len(frames) if isinstance(frames, list) else 0

    @property
    def character_id(self) -> str:
        return self._character_id

    @property
    def review_path(self) -> Path | None:
        return self._character_dir / REVIEW if self._character_dir is not None else None

    def preview_png(
        self, base: Any, fonts: Any, label_text: str, label_position: str
    ) -> tuple[bytes | None, str | None]:
        """The live frame with the new room, as the fork would make it (research R13). Blocking: run in a thread.

        `base` is the 009/013 `base` layer. Returns `(png, None)`, or `(None, reason)` when there is nothing to show.
        """
        status = self._compute()
        if status["fallback_reason"] is not None:
            return None, status["fallback_reason"]
        plate = self._result.png if self._result is not None else None
        if plate is None or self._character_dir is None:
            return None, "plate_failed"
        try:
            frame = _open_rgb(self._character_dir / PREVIEW_FRAME)
            mask = self._preview_mask(frame)
        except (OSError, ValueError) as exc:
            log_event(logger, "background_preview_unreadable", logging.WARNING, error=str(exc))
            return None, "mismatch:mask_unreadable:preview_frame.png"
        with Image.open(io.BytesIO(plate)) as image:
            room = image.convert("RGB").resize(frame.size)
        # Mask 0 = room (takes the plate), 255 = host and desk (keep the frame); feathered values blend.
        frame = Image.composite(frame, room, mask.resize(frame.size))
        still = compose_still(frame, [base])
        _draw_label(still, fonts, label_text, label_position)
        out = io.BytesIO()
        still.save(out, format="PNG")
        return out.getvalue(), None

    def add_room_listener(self, listener: Callable[[], None]) -> None:
        """Call `listener()` whenever `room_face` may give a different picture (new plate, fork status change)."""
        self._room_listeners.append(listener)

    def room_face(self, face: Image.Image) -> Image.Image | None:
        """`face` (a still of the host as the fork's first frame) in the new room, or None while the live frame shows
        the original room. Keeps the still behind the video in the same room as the video. Blocking: run in a thread.
        """
        reason = self._fallback_reason()
        plate = self._result.png if self._result is not None else None
        if reason is not None or plate is None or self._character_dir is None:
            return None
        cached = self._room_cache
        if cached is not None and cached[0] is face and cached[1] is plate:
            return cached[2]
        try:
            mask = self._preview_mask(face.convert("RGB"))
        except (OSError, ValueError, KeyError) as exc:
            log_event(logger, "background_still_unavailable", logging.WARNING, error=str(exc))
            room_face = None
        else:
            with Image.open(io.BytesIO(plate)) as image:
                room = image.convert("RGB").resize(face.size)
            room_face = Image.composite(face.convert("RGB"), room, mask.resize(face.size))
        self._room_cache = (face, plate, room_face)
        return room_face

    def _room_changed(self) -> None:
        for listener in self._room_listeners:
            try:
                listener()
            except Exception:
                logger.exception("room listener failed")

    def _preview_mask(self, frame: Image.Image) -> Image.Image:
        # The mask whose fingerprint matches the preview frame (the fork's own lookup), else the loop's first frame.
        assert self._character_dir is not None
        entries = [e for e in (self._manifest or {}).get("frames") or [] if isinstance(e, dict) and e.get("mask")]
        if not entries:
            raise ValueError("manifest has no frames")
        bgr = np.ascontiguousarray(np.asarray(frame)[:, :, ::-1]).tobytes()
        fingerprint = f"{zlib.crc32(bgr) & 0xFFFFFFFF:08x}"
        entry = next((e for e in entries if e.get("fingerprint") == fingerprint), entries[0])
        with Image.open(self._character_dir / "background" / str(entry["mask"])) as image:
            return image.convert("L")

    def _push(self, *, redrawn: bool = False) -> None:
        """Give the renderer the plate the fork should show; it resends it on every `hello` by itself.

        A redraw always goes out, even when it looks the same: a new product set is a new plate (FR-007).
        """
        if self._sink is None:
            return
        plate = self._result.png if self._result is not None else None
        # A fork without valid masks refuses a plate (fork-protocol §3): it only ever gets "no plate".
        if self._fork is not None and self._fork.status != "valid":
            plate = None
        if not self._given_set and plate is None:
            return
        if self._given_set and plate is self._given and not (redrawn and plate is not None):
            return
        self._given, self._given_set = plate, True
        self._sink.set_scene_background(plate)

    def _started(self) -> None:
        status = self._publish_if_changed()
        log_event(
            logger,
            "scene_background_started",
            style=status["style"],
            active=status["active"],
            mask_status=status["mask_status"],
            fallback_reason=status["fallback_reason"],
            method=self._method(),
            reviewed=status["reviewed"],
            items=status["items"],
            plate_bytes=len(self._result.png) if self._result is not None and self._result.png else 0,
            plate_ms=self._plate_ms,
        )

    def _publish_if_changed(self) -> dict[str, Any]:
        current = self._compute()
        if current != self._last:
            self._last = current
            self._changed_at = _now()
            self._bus.publish(Event(EventType.SCENE, {"kind": "background", **current}))
            self._room_changed()
        return current

    # ---------- status ----------

    def _compute(self) -> dict[str, Any]:
        reason = self._fallback_reason()
        plated = self._result is not None and self._result.png is not None
        return {
            "style": self._config.style,
            "active": reason is None,
            "mask_status": self._mask_status(),
            "fallback_reason": reason,
            "fallback_message": fallback_message(reason, self._character_id, style=self._config.style),
            "reviewed": self._reviewed(),
            "items": list(self._result.items) if plated and self._result is not None else [],
        }

    def _fallback_reason(self) -> str | None:
        """data-model §5, checked in its order."""
        if self._config.style == "goc":
            return "style_goc"
        if self._failed:
            return "plate_failed"
        if self._result is not None and self._result.png is None:
            return self._result.reason or "plate_failed"
        if self._result is None:
            return "plate_failed"
        if self._sink is None:
            return "avatar_static"
        fork = self._fork
        if not self._fork_known or fork is None:
            return "fork_unsupported"
        if fork.status == "missing":
            return fork.reason or "not_prepared"
        if fork.status == "mismatch":
            detail = fork.reason or "unknown"
            return detail if detail.startswith("mismatch:") else f"mismatch:{detail}"
        return fork.reason  # `rejected:<msg>` / `failed:<msg>`, or None when the fork composites

    def _mask_status(self) -> str:
        if self._sink is None or self._fork is None:
            return "unknown"
        return self._fork.status

    def _reviewed(self) -> bool | None:
        if self._fork is not None and self._fork.reviewed is not None:
            return self._fork.reviewed
        reviewed = (self._manifest or {}).get("reviewed")
        return reviewed if isinstance(reviewed, bool) else None

    def _method(self) -> str | None:
        if self._fork is not None and self._fork.method is not None:
            return self._fork.method
        method = (self._manifest or {}).get("method")
        return method if isinstance(method, str) else None

    # ---------- manifest ----------

    def _read_manifest(self) -> dict[str, Any] | None:
        """Only `light`, `desk_top_px`, size, `method` and `reviewed` are read here; the fork checks the masks."""
        if self._character_dir is None:
            return None
        path = self._character_dir / MANIFEST
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            log_event(logger, "background_manifest_unreadable", logging.WARNING, path=str(path), error=str(exc))
            return None
        return data if isinstance(data, dict) else None

    def _frame_size(self) -> tuple[int, int]:
        if self._fork is not None and self._fork.width > 0 and self._fork.height > 0:
            return self._fork.width, self._fork.height
        manifest = self._manifest or {}
        width, height = manifest.get("width"), manifest.get("height")
        if _positive_int(width) and _positive_int(height):
            return int(width), int(height)
        return DEFAULT_FRAME

    def _desk_top(self, scene: SceneSet, height: int) -> int:
        desk_top = (self._manifest or {}).get("desk_top_px")
        if _positive_int(desk_top) and desk_top <= height:
            return int(desk_top)
        return round(scene.layout.desk_top * height)


# ---------- wording (data-model §5): one text for the control page, the scene error and readiness ----------


def fallback_text(reason: str | None, character_id: str, *, style: str | None = None) -> tuple[str, str] | None:
    """`(problem, fix)` for a fallback reason, in Vietnamese for the operator; None when the new room is live."""
    if reason is None:
        return None
    prepare = f"uv run python -m ai_live.avatar background-prepare {character_id}"
    kind, _, detail = reason.partition(":")
    if kind == "style_goc":
        return (
            "Nền đang là phòng gốc",
            'muốn có kệ hàng sau host thì đặt "background": {"style": "ke_hang"} trong scene.json'
            " rồi khởi động lại app",
        )
    if kind == "scene_disabled":
        return "Cảnh live đang tắt nên nền là phòng gốc", "đặt SCENE_ENABLED=true trong .env rồi khởi động lại app"
    if kind == "style_not_available":
        return (
            f"Kiểu nền {style or '?'} chưa làm, live hiện phòng gốc",
            'đổi "style" trong scene.json thành "ke_hang", "anh_shop" hoặc "goc"',
        )
    if kind == "no_product_art":
        return (
            "Chưa có ảnh sản phẩm đã bỏ nền cho kệ hàng",
            "tải ảnh sản phẩm ở mục Ảnh sản phẩm trên trang điều khiển (app tự bỏ nền) rồi áp dụng bộ ảnh",
        )
    if kind == "no_shop_photo":
        return (
            "Chưa có ảnh shop cho nền sau host, live hiện phòng gốc",
            "uv run python -m ai_live.scene shop-photo <thư mục cảnh> <ảnh> --confirmed-by <tên> [--ai-generated]"
            " rồi khởi động lại app",
        )
    if kind == "shop_photo_unconfirmed":
        return (
            "Ảnh shop chưa được xác nhận quyền dùng (hoặc file đã đổi sau khi xác nhận), live hiện phòng gốc",
            "xác nhận lại bằng uv run python -m ai_live.scene shop-photo <thư mục cảnh> <ảnh> --confirmed-by <tên>"
            " rồi khởi động lại app",
        )
    if kind == "plate_failed":
        return (
            f"Không vẽ được ảnh nền {STYLE_NAMES.get(style or '', 'sau host')}, live hiện phòng gốc",
            "chạy uv run python -m ai_live.scene check để xem lỗi bộ cảnh",
        )
    if kind == "avatar_static":
        return "Chế độ ảnh tĩnh không có nền sau host", "đặt AVATAR_MODE=livetalking để dùng nền mới"
    if kind == "fork_unsupported":
        return (
            "Máy nhép miệng chưa báo hỗ trợ nền mới, live hiện phòng gốc",
            "khởi động lại fork bằng scripts/livetalking/run.ps1 (bản fork có 014)",
        )
    if kind == "not_prepared":
        return "Nhân vật chưa có nền, live sẽ hiện phòng gốc", f"chạy {prepare}"
    if kind == "mismatch":
        return f"Mặt nạ nền không khớp ({_mismatch_text(detail)}), live hiện phòng gốc", f"chạy lại {prepare}"
    if kind == "rejected":
        return f"Fork từ chối ảnh nền ({detail}), live hiện phòng gốc", f"chạy lại {prepare} rồi khởi động lại app"
    if kind == "failed":
        return (
            f"Lỗi khi ghép nền ({detail}), live đã về phòng gốc",
            f"show vẫn chạy; xem log của fork, sau buổi live chạy lại {prepare}",
        )
    return f"Nền mới chưa bật ({reason}), live hiện phòng gốc", "xem log của app"


def fallback_message(reason: str | None, character_id: str, *, style: str | None = None) -> str | None:
    text = fallback_text(reason, character_id, style=style)
    return f"{text[0]}: {text[1]}" if text is not None else None


def _mismatch_text(detail: str) -> str:
    kind, _, value = detail.partition(":")
    if kind == "frame_not_prepared":
        return f"{value or '?'} khung chưa có mặt nạ"
    if kind == "size_mismatch":
        return "sai cỡ khung so với lúc chuẩn bị"
    if kind == "character_mismatch":
        return "mặt nạ của nhân vật khác"
    if kind == "mask_unreadable":
        return f"không đọc được {value or 'mặt nạ'}"
    return detail or "không rõ"


def disabled_background_status() -> dict[str, Any]:
    """`GET /api/scene/background` with `SCENE_ENABLED=false`: a status, never an error (contracts/api.md)."""
    return {
        "style": "goc",
        "active": False,
        "mask_status": "unknown",
        "fallback_reason": "scene_disabled",
        "fallback_message": fallback_message("scene_disabled", "<character_id>"),
        "reviewed": None,
        "items": [],
        "changed_at": None,
    }


# ---------- offline: readiness without the app or the fork ----------


def read_disk_masks(character_dir: Path | None, character_id: str) -> ForkBackgroundStatus:
    """What the fork would say in `hello.background`, read from `background/manifest.json` alone. Blocking.

    Without the fork's frames this cannot catch a frame or size mismatch; it checks the owner and the mask files.
    """

    def status(kind: str, reason: str | None, data: dict[str, Any] | None = None) -> ForkBackgroundStatus:
        data = data or {}
        frames = data.get("frames")
        block = {
            "status": kind,
            "reason": reason,
            "frames": len(frames) if isinstance(frames, list) else 0,
            "width": data.get("width"),
            "height": data.get("height"),
            "method": data.get("method"),
            "reviewed": data.get("reviewed"),
        }
        parsed = ForkBackgroundStatus.from_hello(block)
        assert parsed is not None  # `kind` is always a known status
        return parsed

    if character_dir is None:
        return status("missing", "not_prepared")
    try:
        data = json.loads((character_dir / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return status("missing", "not_prepared")
    except (OSError, ValueError):
        return status("mismatch", "mask_unreadable:manifest.json")
    if not isinstance(data, dict) or not isinstance(data.get("frames"), list) or not data["frames"]:
        return status("mismatch", "mask_unreadable:manifest.json")
    if data.get("character_id") != character_id:
        return status("mismatch", "character_mismatch", data)
    for entry in data["frames"]:
        mask = entry.get("mask") if isinstance(entry, dict) else None
        if not isinstance(mask, str) or not (character_dir / "background" / mask).is_file():
            return status("mismatch", f"mask_unreadable:{mask}", data)
    return status("valid", None, data)


class DiskMasks:
    """A `BackgroundSink` standing in for a fork that is not running: it reports the masks on disk."""

    def __init__(self, status: ForkBackgroundStatus) -> None:
        self._status = status

    def set_scene_background(self, plate_png: bytes | None) -> None:
        return None

    def add_background_status_listener(self, callback: Callable[[ForkBackgroundStatus | None], None]) -> None:
        callback(self._status)


async def offline_background(
    scene: SceneSet, character_dir: Path | None, character_id: str, *, lipsync: bool
) -> BackgroundController:
    """The same controller as in the app, fed by the disk instead of the fork, so readiness words it the same."""
    renderer: Any = object()  # static mode: no fork frame, as in the app
    if lipsync:
        renderer = DiskMasks(await asyncio.to_thread(read_disk_masks, character_dir, character_id))
    controller = BackgroundController(renderer, EventBus(), character_dir, character_id=character_id)
    await controller.start()
    await controller.on_scene_loaded(scene)
    return controller


# ---------- helpers ----------


def _is_fork_error(reason: str | None) -> bool:
    return reason is not None and reason.startswith(("rejected:", "failed:"))


def _open_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def _draw_label(image: Image.Image, fonts: Any, text: str, position: str) -> None:
    """The AI label where the fork draws it (`estimate_label_box`), so the preview never shows a frame without it.

    `shopee-top` wraps into two lines, centred in the box (ADR-085).
    """
    if not text:
        return
    width, height = image.size
    lines, estimated_px = label_lines(width, height, text, position)
    px = max(8, round(estimated_px)) if len(lines) > 1 else max(10, round(height * LABEL_FONT_RATIO))
    x1, y1, x2, _ = estimate_label_box(width, height, text, position)
    font: Any
    try:
        font = fonts.get(px, bold=True) if fonts is not None else ImageFont.load_default(px)
    except Exception:  # a broken font file must not lose the label
        font = ImageFont.load_default(px)
    stroke = max(1, round(px * _LABEL_STROKE_RATIO))
    draw = ImageDraw.Draw(image)
    if len(lines) == 1:
        origin = (x1 + stroke, y1 + stroke)
        draw.text(origin, text, font=font, fill=_LABEL_TEXT, stroke_width=stroke, stroke_fill=_LABEL_STROKE)
        return
    draw.multiline_text(
        ((x1 + x2) // 2, y1 + stroke),
        "\n".join(lines),
        font=font,
        anchor="ma",
        align="center",
        spacing=max(1, round(px * 0.12)),
        fill=_LABEL_TEXT,
        stroke_width=stroke,
        stroke_fill=_LABEL_STROKE,
    )


def _usable(art: Any) -> bool:
    # Only real cut-outs go on the shelves: a placeholder is not the product, an opaque photo still has its background.
    return not getattr(art, "placeholder", False) and not getattr(art, "opaque", False)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
