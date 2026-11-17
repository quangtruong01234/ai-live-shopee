"""Keeps the live scene in step with the show (research R6, contracts/api.md).

It reloads the scene when the content file is replaced (FR-013), follows the sentence being *heard* to highlight its
product (FR-015/FR-016), redraws when the fork reports its real frame, and hands each new layer to the lip-sync fork
and to the still image. Drawing runs in a worker thread; a redraw asked for while one runs is folded into the next, so
a burst of sentences costs one draw. Nothing here may stop the show: every failure becomes `last_error`, a log line
and a `scene` error event (FR-021).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from ai_live.core.config import Settings
from ai_live.core.events import Event, EventBus, EventType, Subscription
from ai_live.core.logging import log_event
from ai_live.core.protocols import ProductStore
from ai_live.products.models import ProductCatalog
from ai_live.scene.fonts import SceneFonts, load_fonts
from ai_live.scene.layout import compute_layout, estimate_geometry
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import FrameGeometry, SceneLayer, SceneLayout, SceneSet
from ai_live.scene.render import compose_still, cover_crop, encode_png, render_base, render_subtitle

logger = logging.getLogger("ai_live.scene")

# Scripted sentences remembered to find the product of the sentence being heard; a show speaks far fewer between
# preparing a sentence and hearing it.
MAX_TRACKED_UTTERANCES = 256
_CLEAR_STATES = ("idle", "ended")


@dataclass(frozen=True)
class _Snapshot:
    """Everything one draw reads, taken at once so a content replace never mixes two files (FR-013)."""

    scene: SceneSet
    catalog: ProductCatalog
    geometry: FrameGeometry
    highlight: str | None
    subtitle: str | None


def disabled_status() -> dict[str, Any]:
    """`GET /api/scene` with `SCENE_ENABLED` off (contracts/api.md §1)."""
    return {
        "enabled": False,
        "scene_id": None,
        "dir": None,
        "version": None,
        "highlight": None,
        "subtitles": False,
        "geometry": None,
        "slots": [],
        "overflow": [],
        "issues": [],
        "last_error": None,
        "render_ms": None,
    }


DISABLED_HOST_CONFIG: dict[str, Any] = {"enabled": False, "subtitles": False, "version": None}


class SceneController:
    def __init__(
        self,
        settings: Settings,
        store: ProductStore,
        renderer: Any,
        bus: EventBus,
        avatar_image: Path | None,
        *,
        fonts_loader: Callable[[Path | None], SceneFonts] = load_fonts,
    ) -> None:
        self._settings = settings
        self._store = store
        self._renderer = renderer
        self._bus = bus
        self._avatar_image = avatar_image
        self._fonts_loader = fonts_loader
        self._fonts: SceneFonts | None = None
        self._face: Image.Image | None = None
        self._scene: SceneSet | None = None
        self._geometry = estimate_geometry(settings.ai_label_text, settings.ai_label_position)
        self._highlight: str | None = None
        self._subtitle: str | None = None
        self._utterances: OrderedDict[str, tuple[str | None, str | None]] = OrderedDict()
        self._layout: SceneLayout | None = None
        self._base: SceneLayer | None = None
        self._subtitle_layer: SceneLayer | None = None
        self._base_key: tuple[Any, ...] | None = None
        self._subtitle_key: tuple[Any, ...] | None = None
        self._still_png: bytes | None = None
        self.version = 0
        self.render_ms: float | None = None
        self.last_error: str | None = None
        self._dirty = asyncio.Event()
        self._idle = asyncio.Event()
        self._reload = True
        self._sub: Subscription | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._sends: set[asyncio.Task[Any]] = set()

    # ---------- lifecycle ----------

    @property
    def enabled(self) -> bool:
        return self._settings.scene_enabled

    async def start(self) -> None:
        if not self.enabled:
            return
        self._sub = self._bus.subscribe()
        add_listener = getattr(self._renderer, "add_playback_listener", None)
        if add_listener is not None:
            add_listener(self)
        add_geometry = getattr(self._renderer, "add_scene_geometry_listener", None)
        if add_geometry is not None:
            add_geometry(self.on_geometry)
        self._tasks = [asyncio.create_task(self._read_events()), asyncio.create_task(self._work())]
        self._mark()

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        if self._sub is not None:
            self._sub.close()
            self._sub = None

    async def wait_idle(self) -> None:
        """Until no redraw is pending (tests and the first `/host` load)."""
        await self._idle.wait()

    def _mark(self) -> None:
        self._idle.clear()
        self._dirty.set()

    # ---------- what the routes read ----------

    @property
    def still_png(self) -> bytes | None:
        return self._still_png

    @property
    def highlight(self) -> str | None:
        return self._highlight

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return disabled_status()
        scene, layout = self._scene, self._layout
        issues = [*(scene.issues if scene else ()), *(layout.issues if layout else ())]
        # Nothing of a blocked set is drawn (another customer's set, FR-003): list no product as on the desk.
        on_desk = None if scene is not None and scene.blocked else layout
        return {
            "enabled": True,
            "scene_id": scene.scene_id if scene else None,
            "dir": self._settings.scene_dir.as_posix(),
            "version": self.version,
            "highlight": self._highlight,
            "subtitles": self._settings.scene_subtitles,
            "geometry": self._geometry.to_json(),
            "slots": [s.product_id for s in on_desk.slots] if on_desk else [],
            "overflow": list(on_desk.overflow) if on_desk else [],
            "issues": [i.to_json() for i in issues],
            "last_error": self.last_error,
            "render_ms": self.render_ms,
        }

    def host_config(self) -> dict[str, Any]:
        subtitles = self.enabled and self._settings.scene_subtitles
        return {"enabled": self.enabled, "subtitles": subtitles, "version": self.version if self.enabled else None}

    # ---------- inputs ----------

    def on_geometry(self, geometry: FrameGeometry) -> None:
        """The fork's real frame (`hello.scene`): redraw only when it moves something."""
        same = geometry.same_frame(self._geometry)
        self._geometry = geometry
        if not same:
            self._mark()

    def playback_started(self, utterance_id: str, seq: int, text: str) -> None:
        # The sentence event may still sit in the queue: read it now so the highlight never lags a sentence.
        if self._sub is not None:
            for event in self._sub.drain():
                self._handle(event)
        if utterance_id in self._utterances:
            segment_id, product_id = self._utterances[utterance_id]
            # A comment reply is not in the map and keeps the current highlight (FR-017).
            self._set_highlight(product_id, segment_id=segment_id, utterance_id=utterance_id)
        if self._settings.scene_subtitles:
            self._subtitle = text
            self._mark()

    def playback_ended(self, utterance_id: str, seq: int) -> None:
        self._clear_subtitle()

    def playback_stopped(self) -> None:
        self._clear_subtitle()

    def _clear_subtitle(self) -> None:
        if self._subtitle is not None:
            self._subtitle = None
            self._mark()

    def _set_highlight(self, product_id: str | None, **context: Any) -> None:
        if product_id == self._highlight:
            return
        self._highlight = product_id
        played_at = datetime.now(UTC).isoformat()
        log_event(logger, "scene_highlight", product_id=product_id, played_at=played_at, **context)
        self._bus.publish(Event(EventType.SCENE, {"kind": "highlight", "product_id": product_id, **context}))
        self._mark()

    async def _read_events(self) -> None:
        assert self._sub is not None
        async for event in self._sub:
            self._handle(event)

    def _handle(self, event: Event) -> None:
        payload = event.payload
        if event.type is EventType.SENTENCE and "segment_id" in payload:
            self._utterances[payload["utterance_id"]] = (payload["segment_id"], payload.get("product_id"))
            while len(self._utterances) > MAX_TRACKED_UTTERANCES:
                self._utterances.popitem(last=False)
        elif event.type is EventType.SHOW_STATE and payload.get("state") in _CLEAR_STATES:
            self._set_highlight(None, show_state=payload.get("state"))
        elif event.type is EventType.CONTENT_REPLACED:
            self._reload = True
            self._mark()

    # ---------- drawing ----------

    async def _work(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            try:
                await self._redraw()
            except Exception as exc:
                self._fail("draw", exc)
            if not self._dirty.is_set():
                self._idle.set()

    def _fail(self, step: str, exc: BaseException) -> None:
        self.last_error = f"{step}: {exc}"
        logger.exception("scene %s failed", step)
        self._bus.publish(Event(EventType.SCENE, {"kind": "error", "message": f"Lỗi cảnh ({step}): {exc}"}))

    async def _redraw(self) -> None:
        if self._fonts is None:
            self._fonts = await asyncio.to_thread(self._fonts_loader, self._settings.scene_font_path)
        catalog = self._store.catalog
        if self._reload or self._scene is None:
            self._reload = False
            self._scene = await asyncio.to_thread(
                load_scene_set,
                self._settings.scene_dir,
                [p.id for p in catalog.products],
                customer_id=self._settings.customer_id,
            )
            self._base_key = None
            scene = self._scene
            errors = sum(i.level == "error" for i in scene.issues)
            log_event(
                logger,
                "scene_loaded",
                scene_id=scene.scene_id,
                images=len(scene.art),
                issues=len(scene.issues),
                errors=errors,
            )
            if self._highlight is not None and self._highlight not in {p.id for p in catalog.products}:
                self._set_highlight(None, reason="content_replaced")
        snapshot = _Snapshot(self._scene, catalog, self._geometry, self._highlight, self._subtitle)
        changed = await asyncio.to_thread(self._draw, snapshot)
        if not changed:
            return
        self.version += 1
        sink = getattr(self._renderer, "set_scene_layer", None)
        for name in changed:
            layer = self._base if name == "base" else self._subtitle_layer
            if sink is not None:
                sink(name, layer or SceneLayer(name, 0, 0, None))
        log_event(
            logger,
            "scene_rendered",
            version=self.version,
            layers=list(changed),
            render_ms=self.render_ms,
            base_bytes=len(self._base.png or b"") if self._base else 0,
        )
        self._bus.publish(
            Event(EventType.SCENE, {"kind": "rendered", "version": self.version, "render_ms": self.render_ms})
        )
        self._tell_host()

    def _tell_host(self) -> None:
        # Sent in every avatar mode: the still image behind the video stays current for a fall-back.
        send = getattr(self._renderer, "send_to_host", None)
        if send is None:
            return
        task = asyncio.create_task(send({"type": "scene", "version": self.version}))
        self._sends.add(task)
        task.add_done_callback(self._sent)

    def _sent(self, task: asyncio.Task[Any]) -> None:
        self._sends.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log_event(logger, "scene_send_failed", logging.WARNING, target="host", error=str(task.exception()))

    def _draw(self, snap: _Snapshot) -> list[str]:
        """Worker thread: redraw the layers whose inputs changed and the still image; names of the changed layers."""
        assert self._fonts is not None
        started = time.perf_counter()
        geometry = snap.geometry
        if self._face is None or self._face.size != (geometry.width, geometry.height):
            self._face = self._load_face(geometry)
        products = {p.id: p for p in snap.catalog.products}
        changed: list[str] = []
        blocked = snap.scene.blocked
        base_key = (id(snap.scene), snap.catalog.version, geometry, snap.highlight)
        if base_key != self._base_key:
            self._base_key = base_key
            art_sizes = {pid: art.image.size for pid, art in snap.scene.art.items()}
            layout = compute_layout(snap.catalog.products, art_sizes, geometry, snap.scene.layout, snap.highlight)
            self._layout = layout
            self._base = None if blocked else render_base(snap.scene, layout, products, geometry, self._fonts)
            changed.append("base")
        subtitle_key = (snap.subtitle, geometry, id(self._layout))
        if subtitle_key != self._subtitle_key:
            self._subtitle_key = subtitle_key
            layer = None
            if snap.subtitle and self._layout is not None and not blocked:
                layer = render_subtitle(snap.subtitle, self._layout, geometry, self._fonts)
            if layer is not None or self._subtitle_layer is not None:
                changed.append("subtitle")
            self._subtitle_layer = layer
        if changed:
            still = compose_still(self._face, [self._base, self._subtitle_layer])
            self._still_png = encode_png(still)
            self.render_ms = round((time.perf_counter() - started) * 1000, 1)
        return changed

    def _load_face(self, geometry: FrameGeometry) -> Image.Image:
        path = self._avatar_image
        if path is not None and path.is_file():
            with Image.open(path) as image:
                return cover_crop(image.convert("RGB"), geometry.width, geometry.height)
        return Image.new("RGB", (geometry.width, geometry.height), (40, 40, 48))
