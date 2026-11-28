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
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from ai_live.core.config import Settings
from ai_live.core.events import Event, EventBus, EventType, Subscription
from ai_live.core.logging import log_event
from ai_live.core.protocols import ProductStore
from ai_live.products.models import Product, ProductCatalog
from ai_live.scene.fonts import SceneFonts, load_fonts
from ai_live.scene.layout import ArtFit, art_background_issues, art_fit, compute_scene_layout, estimate_geometry
from ai_live.scene.loader import ART_MAX_SIDE, load_scene_set
from ai_live.scene.merchandise import stock_size, with_stock
from ai_live.scene.models import FrameGeometry, ProductArt, SceneIssue, SceneLayer, SceneLayout, SceneSet
from ai_live.scene.render import (
    card_texts,
    compose_still,
    cover_crop,
    draw_debug_zones,
    encode_png,
    render_base,
    render_subtitle,
)

if TYPE_CHECKING:
    from ai_live.avatar.character import AvatarCharacter

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
        "images": [],
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
        character: AvatarCharacter | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._renderer = renderer
        self._bus = bus
        self._avatar_image = avatar_image
        self._fonts_loader = fonts_loader
        # 011: a picture with its own desk moves the desk line and drops the desk layer. Fixed for the app's life,
        # so it is not part of the base key.
        self._desk_in_image = bool(character is not None and character.desk_in_image)
        self._desk_top = character.desk_top if character is not None else None
        # 013: where the host's hands move (frame fractions), kept on every geometry so products stay out of it.
        self._hands_zone = getattr(character, "hands_zone", None) if character is not None else None
        self._fonts: SceneFonts | None = None
        self._face: Image.Image | None = None
        self._scene: SceneSet | None = None
        self._geometry = estimate_geometry(settings.ai_label_text, settings.ai_label_position).with_hands_zone(
            self._hands_zone
        )
        self._highlight: str | None = None
        self._subtitle: str | None = None
        self._utterances: OrderedDict[str, tuple[str | None, str | None]] = OrderedDict()
        self._layout: SceneLayout | None = None
        self._base: SceneLayer | None = None
        # What each drawn card says (013 T051): logged so a review can check it against the file (SC-007).
        self._card_texts: dict[str, dict[str, str | None]] = {}
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
        # 012: draws counted from the worker loop, so `reload()` can wait for one that starts after its call.
        self._draws_started = 0
        self._draws_done = 0
        self._draw_finished = asyncio.Condition()
        # 012 R7: held by `hold()` so "Áp dụng bộ mới" writes catalog and manifest with no draw in between.
        self._draw_lock = asyncio.Lock()
        # 014: told each newly loaded scene set (the backdrop plate is drawn from it).
        self._scene_loaded_listeners: list[Callable[[SceneSet], Awaitable[None]]] = []
        # 014: puts the host still into the room the fork shows (None: the original room); see `set_room`.
        self._room: Callable[[Image.Image], Image.Image | None] | None = None
        self._room_face: Image.Image | None = None

    # ---------- lifecycle ----------

    def add_scene_loaded_listener(self, listener: Callable[[SceneSet], Awaitable[None]]) -> None:
        """Await `listener(scene)` after every scene set load (startup, content replace, 012 apply)."""
        self._scene_loaded_listeners.append(listener)

    def set_room(self, room: Callable[[Image.Image], Image.Image | None]) -> None:
        """Draw the still on `room(face)` when it gives a picture, so the still and the video show the same room.

        `room` runs in the worker thread; call `refresh()` whenever it may give a different picture.
        """
        self._room = room

    def refresh(self) -> None:
        """Redraw the still (the room behind the host changed)."""
        if self._tasks:
            self._mark()

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

    @property
    def base_layer(self) -> SceneLayer | None:
        """The drawn desk/cards layer (None before the first draw); the 014 preview lays it over the host."""
        return self._base

    @property
    def fonts(self) -> SceneFonts | None:
        return self._fonts

    @property
    def scene(self) -> SceneSet | None:
        """The scene set drawn now (None before the first draw or with the scene off)."""
        return self._scene

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return disabled_status()
        scene, layout = self._scene, self._layout
        issues = [*(scene.issues if scene else ()), *(layout.issues if layout else ()), *self._art_issues()]
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
            # 012: which file each drawn product shows (kit or an uploaded version).
            "images": []
            if scene is None or scene.blocked
            else [
                {"product_id": a.product_id, "source": a.source, "version_id": a.version_id} for a in scene.art.values()
            ],
        }

    def art_fit(self, products: Sequence[Product], product_id: str, size: tuple[int, int]) -> ArtFit | None:
        """How a picture of `size` would fare among `products` in the current frame (FR-004a).

        None when the scene is off or its set is not usable: there is no layout to judge against.
        """
        scene = self._scene
        if not self.enabled or scene is None or scene.blocked:
            return None
        # FR-030: judged as the desk will show it, stacked when the scene stocks.
        shown = stock_size(size, scene.layout)
        return art_fit(products, product_id, shown, self._geometry, scene.layout, desk_top=self._desk_top)

    def low_resolution(self, products: Sequence[Product], product_id: str, size: tuple[int, int]) -> str | None:
        """The `art_low_resolution` message a picture of `size` would get among `products` (FR-028), or None.

        The other products keep their live pictures: in the showcase their sizes move this one. The picture is judged
        as the scene will load it, shrunk to `ART_MAX_SIDE`. None also when the scene is off or its set is unusable.
        """
        scene = self._scene
        if not self.enabled or scene is None or scene.blocked:
            return None
        shrink = min(1.0, ART_MAX_SIDE / max(size))
        art_sizes = {pid: art.desk_image.size for pid, art in scene.art.items()}
        loaded = (max(1, round(size[0] * shrink)), max(1, round(size[1] * shrink)))
        art_sizes[product_id] = stock_size(loaded, scene.layout)
        layout = compute_scene_layout(products, art_sizes, self._geometry, scene.layout, desk_top=self._desk_top)
        found = (i for i in layout.issues if i.code == "art_low_resolution" and i.product_id == product_id)
        issue = next(found, None)
        return None if issue is None else issue.message

    def layout_issues(self, catalog: ProductCatalog) -> list[SceneIssue]:
        """Layout issues of the live set while no product is highlighted (FR-004a).

        Not the last drawn layout: a picture too wide for its usual slot may fit while highlighted, and the
        image list must not flicker with each sentence.
        """
        scene = self._scene
        if not self.enabled or scene is None or scene.blocked:
            return []
        art_sizes = {pid: art.desk_image.size for pid, art in scene.art.items()}
        layout = compute_scene_layout(
            catalog.products, art_sizes, self._geometry, scene.layout, desk_top=self._desk_top
        )
        return [*layout.issues, *art_background_issues(catalog.products, scene.art, scene.layout)]

    def _art_issues(self) -> list[SceneIssue]:
        scene = self._scene
        if scene is None or scene.blocked:
            return []
        return art_background_issues(self._store.catalog.products, scene.art, scene.layout)

    def host_config(self) -> dict[str, Any]:
        subtitles = self.enabled and self._settings.scene_subtitles
        return {"enabled": self.enabled, "subtitles": subtitles, "version": self.version if self.enabled else None}

    # ---------- inputs ----------

    def on_geometry(self, geometry: FrameGeometry) -> None:
        """The fork's real frame (`hello.scene`): redraw only when it moves something.

        The fork knows nothing of the hands zone; it comes from the character, scaled to this frame.
        """
        geometry = geometry.with_hands_zone(self._hands_zone)
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

    @contextlib.asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        """No draw runs inside: wait for the one under way, then keep the next one out until the block ends.

        "Áp dụng bộ mới" swaps the catalog and the image manifest inside, so no frame mixes the old set with the new
        (research R7). Leaving always asks for a re-read; the caller then awaits `reload()` with no await in between,
        so that wait is for the draw that reads both new files.
        """
        async with self._draw_lock:
            try:
                yield
            finally:
                self._reload = True
                if self.enabled and self._tasks:
                    self._mark()

    async def reload(self) -> int | None:
        """Re-read the scene folder (an upload changed it) and return the version once that draw is done.

        Calls close together fold into one draw. A draw already running when this is called may have read the old
        manifest, so the wait is for a draw that *starts* after the call. None with the scene off or not started.
        """
        if not self.enabled or not self._tasks:
            return None
        target = self._draws_started + 1
        self._reload = True
        self._mark()
        async with self._draw_finished:
            await self._draw_finished.wait_for(lambda: self._draws_done >= target)
        return self.version

    async def preview(
        self,
        catalog: ProductCatalog,
        overrides: dict[str, ProductArt | None],
        highlight: str | None,
        *,
        scene: SceneSet | None = None,
        target: str = "live",
        debug: bool = False,
    ) -> bytes:
        """A PNG of the frame as it would look with `overrides` (None = no image), leaving the live scene untouched.

        `scene` defaults to the live set; staging (US2) passes the set it builds for the new content file.
        `debug` (013) draws the keep-out zones, the desk edge and the hands zone over the picture.
        """
        if self._fonts is None:
            self._fonts = await asyncio.to_thread(self._fonts_loader, self._settings.scene_font_path)
        if scene is None:
            scene = self._scene
        if scene is None:
            scene = await asyncio.to_thread(
                load_scene_set,
                self._settings.scene_dir,
                [p.id for p in catalog.products],
                customer_id=self._settings.customer_id,
            )
        art = dict(scene.art)
        # An override is one unit as uploaded: stock it like the loader does, so the preview shows what live will.
        stocked = with_stock({pid: item for pid, item in overrides.items() if item is not None}, scene.layout)
        for pid, item in overrides.items():
            if item is None:
                art.pop(pid, None)
            else:
                art[pid] = stocked[pid]
        candidate = replace(scene, art=art)
        started = time.perf_counter()
        png = await asyncio.to_thread(self._draw_preview, candidate, catalog, self._geometry, highlight, debug)
        render_ms = round((time.perf_counter() - started) * 1000, 1)
        log_event(
            logger,
            "scene_preview",
            target=target,
            product_id=next(iter(overrides), None),
            render_ms=render_ms,
            debug=debug,
        )
        return png

    def _draw_preview(
        self,
        scene: SceneSet,
        catalog: ProductCatalog,
        geometry: FrameGeometry,
        highlight: str | None,
        debug: bool = False,
    ) -> bytes:
        """Worker thread: one full frame for the preview, sharing no mutable state with the live draw."""
        assert self._fonts is not None
        face = self._face
        if face is None or face.size != (geometry.width, geometry.height):
            face = self._load_face(geometry)
        art_sizes = {pid: art.desk_image.size for pid, art in scene.art.items()}
        layout = compute_scene_layout(
            catalog.products, art_sizes, geometry, scene.layout, highlight, desk_top=self._desk_top
        )
        products = {p.id: p for p in catalog.products}
        base = (
            None
            if scene.blocked
            else render_base(scene, layout, products, geometry, self._fonts, desk_in_image=self._desk_in_image)
        )
        still = compose_still(face, [base])
        if debug:
            still = draw_debug_zones(still, geometry, layout)
        return encode_png(still)

    async def _work(self) -> None:
        while True:
            await self._dirty.wait()
            async with self._draw_lock:
                self._dirty.clear()
                self._draws_started += 1
                try:
                    await self._redraw()
                except Exception as exc:
                    self._fail("draw", exc)
                finally:
                    self._draws_done = self._draws_started
                    async with self._draw_finished:
                        self._draw_finished.notify_all()
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
                uploads=sum(a.source == "upload" for a in scene.art.values()),
                issues=len(scene.issues),
                errors=errors,
            )
            for listener in self._scene_loaded_listeners:
                try:
                    await listener(scene)
                except Exception:
                    # A listener (the 014 backdrop) must never stop the scene from drawing.
                    logger.exception("scene_loaded listener failed")
            if self._highlight is not None and self._highlight not in {p.id for p in catalog.products}:
                self._set_highlight(None, reason="content_replaced")
        snapshot = _Snapshot(self._scene, catalog, self._geometry, self._highlight, self._subtitle)
        changed = await asyncio.to_thread(self._draw, snapshot)
        if not changed:
            return
        self.version += 1
        sink = getattr(self._renderer, "set_scene_layer", None)
        for name in changed:
            if name == "still":
                continue  # only the still image changed: no layer for the fork
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
            layout_mode=self._layout.mode if self._layout else None,
            cards=self._scene.layout.cards if self._scene else None,
            stations={s.product_id: s.station for s in self._layout.slots} if self._layout else {},
            card_texts=self._card_texts,
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
        """Worker thread: redraw the layers whose inputs changed and the still image; names of the changed layers
        (`"still"` when only the room behind the host changed)."""
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
            art_sizes = {pid: art.desk_image.size for pid, art in snap.scene.art.items()}
            layout = compute_scene_layout(
                snap.catalog.products,
                art_sizes,
                geometry,
                snap.scene.layout,
                snap.highlight,
                desk_top=self._desk_top,
            )
            self._layout = layout
            self._card_texts = (
                {}
                if blocked
                else {
                    pid: {
                        "name": " ".join(text.name_lines),
                        "price": " ".join(text.price_lines),
                        "promotion": " ".join(text.promotion_lines) or None,
                    }
                    for pid, text in card_texts(snap.scene, layout, products, geometry, self._fonts).items()
                }
            )
            self._base = (
                None
                if blocked
                else render_base(snap.scene, layout, products, geometry, self._fonts, desk_in_image=self._desk_in_image)
            )
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
        room_face = self._room(self._face) if self._room is not None else None
        if room_face is not self._room_face:
            self._room_face = room_face
            changed.append("still")
        if changed:
            still = compose_still(room_face or self._face, [self._base, self._subtitle_layer])
            self._still_png = encode_png(still)
            self.render_ms = round((time.perf_counter() - started) * 1000, 1)
        return changed

    def _load_face(self, geometry: FrameGeometry) -> Image.Image:
        path = self._avatar_image
        if path is not None and path.is_file():
            with Image.open(path) as image:
                return cover_crop(image.convert("RGB"), geometry.width, geometry.height)
        return Image.new("RGB", (geometry.width, geometry.height), (40, 40, 48))
