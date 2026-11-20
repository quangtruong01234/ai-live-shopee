"""009 T013, T027, T031: the scene follows the content, the frame and the sentence heard; a failure never stops it."""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Any

import pytest

from ai_live.core.config import Settings
from ai_live.core.events import Event, EventBus, EventType
from ai_live.products.models import ProductCatalog
from ai_live.scene.controller import DISABLED_HOST_CONFIG, SceneController, disabled_status
from ai_live.scene.fonts import SceneFontError, SceneFonts, load_fonts
from ai_live.scene.layout import estimate_geometry
from ai_live.scene.models import SceneLayer
from fixtures.scene_builder import CUSTOMER, catalog, demo_catalog, make_scene_dir, product

# The label the controller estimates with when the settings keep the default.
LABEL = Settings.model_fields["ai_label_text"].default

pytestmark = pytest.mark.anyio


def _fonts(path: Path | None) -> SceneFonts:
    try:
        return load_fonts(None)
    except SceneFontError:
        pytest.skip("no font with Vietnamese diacritics on this machine")


class FakeStore:
    def __init__(self, catalog: ProductCatalog) -> None:
        self.catalog = catalog


class FakeRenderer:
    """The renderer hooks the controller looks for (`getattr`): layers, host messages, listeners."""

    def __init__(self) -> None:
        self.layers: list[tuple[str, SceneLayer]] = []
        self.sent: list[dict[str, Any]] = []
        self.playback: list[Any] = []
        self.geometry: list[Any] = []

    def set_scene_layer(self, name: str, layer: SceneLayer) -> None:
        self.layers.append((name, layer))

    async def send_to_host(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def add_playback_listener(self, listener: Any) -> None:
        self.playback.append(listener)

    def add_scene_geometry_listener(self, listener: Any) -> None:
        self.geometry.append(listener)

    def last(self, name: str) -> SceneLayer:
        return next(layer for n, layer in reversed(self.layers) if n == name)


@pytest.fixture
def scene_settings(settings, tmp_path: Path):
    root = make_scene_dir(tmp_path / "scenes" / "demo", [p.id for p in demo_catalog().products])
    return settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})


@pytest.fixture
async def rig(scene_settings):
    bus = EventBus()
    renderer = FakeRenderer()
    store = FakeStore(demo_catalog())
    controller = SceneController(scene_settings, store, renderer, bus, None, fonts_loader=_fonts)
    events = bus.subscribe()
    await controller.start()
    await settle(controller)
    yield controller, renderer, bus, store, events
    await controller.stop()
    events.close()


async def settle(controller: SceneController) -> None:
    # Let the event reader run, then wait for the drawing it asked for.
    for _ in range(5):
        await asyncio.sleep(0)
    await asyncio.wait_for(controller.wait_idle(), 5)
    for _ in range(3):
        await asyncio.sleep(0)


def scene_events(events, kind: str) -> list[dict[str, Any]]:
    return [e.payload for e in events.drain() if e.type is EventType.SCENE and e.payload["kind"] == kind]


def sentence(utterance_id: str, product_id: str | None, segment_id: str = "seg-1") -> Event:
    payload = {"utterance_id": utterance_id, "segment_id": segment_id, "product_id": product_id, "text": "x"}
    return Event(EventType.SENTENCE, payload)


# ---------- T013 ----------


async def test_start_draws_and_tells_everyone(rig) -> None:
    controller, renderer, _, _, events = rig
    assert controller.version == 1
    assert renderer.playback == [controller] and len(renderer.geometry) == 1
    name, layer = renderer.layers[0]
    assert name == "base" and layer.image is not None and layer.png
    assert renderer.sent == [{"type": "scene", "version": 1}]
    assert controller.still_png and controller.still_png.startswith(b"\x89PNG")
    assert scene_events(events, "rendered") == [{"kind": "rendered", "version": 1, "render_ms": controller.render_ms}]
    status = controller.status()
    assert status["enabled"] and status["scene_id"] == "demo" and status["issues"] == []
    assert status["slots"] == ["sua-rua-mat", "kem-chong-nang", "toner"]
    assert status["geometry"]["source"] == "estimate"
    assert controller.host_config() == {"enabled": True, "subtitles": False, "version": 1}


async def test_disabled_scene_does_nothing(settings) -> None:
    bus = EventBus()
    renderer = FakeRenderer()
    controller = SceneController(settings, FakeStore(demo_catalog()), renderer, bus, None, fonts_loader=_fonts)
    await controller.start()
    await asyncio.sleep(0.01)
    assert bus.subscriber_count == 0
    assert renderer.layers == [] and renderer.sent == [] and renderer.playback == []
    assert controller.still_png is None
    assert controller.status() == disabled_status()
    assert controller.host_config() == DISABLED_HOST_CONFIG
    await controller.stop()


async def test_content_replace_redraws_from_the_new_catalog(rig) -> None:
    controller, renderer, bus, store, _ = rig
    store.catalog = catalog(product("kem-chong-nang", primary=True), product("toner"), version="v2")
    bus.publish(Event(EventType.CONTENT_REPLACED, {}))
    await settle(controller)
    assert controller.version == 2
    assert controller.status()["slots"] == ["kem-chong-nang", "toner"]
    # The removed product's picture is now an orphan of the new file.
    assert [i["code"] for i in controller.status()["issues"]] == ["orphan_image"]


async def test_content_replace_drops_a_highlight_that_is_gone(rig) -> None:
    controller, _, bus, store, events = rig
    bus.publish(sentence("u1", "sua-rua-mat"))
    await settle(controller)
    controller.playback_started("u1", 0, "x")
    await settle(controller)
    assert controller.highlight == "sua-rua-mat"
    store.catalog = catalog(product("kem-chong-nang", primary=True), version="v2")
    bus.publish(Event(EventType.CONTENT_REPLACED, {}))
    await settle(controller)
    assert controller.highlight is None
    assert scene_events(events, "highlight")[-1]["reason"] == "content_replaced"


async def test_fork_geometry_redraws_only_when_the_frame_moves(rig) -> None:
    controller, renderer, _, _, _ = rig
    [listener] = renderer.geometry
    same = estimate_geometry(LABEL, "top-right")
    listener(type(same)(same.width, same.height, same.face_bottom, same.keep_out, "fork"))
    await settle(controller)
    assert controller.version == 1
    listener(estimate_geometry(LABEL, "top-right", face_bottom=304))
    await settle(controller)
    assert controller.version == 2
    assert controller.status()["geometry"]["face_bottom"] == 304


async def test_draw_failure_reports_and_the_next_draw_works(scene_settings) -> None:
    bus = EventBus()
    renderer = FakeRenderer()
    calls = 0

    def flaky(path: Path | None) -> SceneFonts:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SceneFontError("không có font")
        return _fonts(path)

    controller = SceneController(scene_settings, FakeStore(demo_catalog()), renderer, bus, None, fonts_loader=flaky)
    events = bus.subscribe()
    await controller.start()
    await settle(controller)
    assert controller.last_error == "draw: không có font"
    [error] = scene_events(events, "error")
    assert "không có font" in error["message"]
    assert controller.version == 0
    controller.on_geometry(estimate_geometry(LABEL, "top-right", face_bottom=300))
    await settle(controller)
    assert controller.version == 1 and renderer.layers
    await controller.stop()


async def test_failed_host_send_is_only_logged(rig, caplog: pytest.LogCaptureFixture) -> None:
    controller, renderer, _, _, _ = rig
    caplog.set_level(logging.INFO, logger="ai_live")

    async def broken(message: dict[str, Any]) -> None:
        raise ConnectionError("host gone")

    renderer.send_to_host = broken
    controller.on_geometry(estimate_geometry(LABEL, "top-right", face_bottom=300))
    await settle(controller)
    assert controller.version == 2
    assert any(r.getMessage() == "scene_send_failed" for r in caplog.records)


async def test_other_customers_scene_is_never_drawn(settings, tmp_path: Path) -> None:
    root = make_scene_dir(tmp_path / "other", [p.id for p in demo_catalog().products], customer_id="other_shop")
    blocked = settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})
    renderer = FakeRenderer()
    controller = SceneController(blocked, FakeStore(demo_catalog()), renderer, EventBus(), None, fonts_loader=_fonts)
    await controller.start()
    await settle(controller)
    assert renderer.last("base").image is None
    assert "customer_mismatch" in [i["code"] for i in controller.status()["issues"]]
    await controller.stop()


async def test_avatar_image_is_the_still_background(scene_settings, tmp_path: Path) -> None:
    from PIL import Image

    face = tmp_path / "face.png"
    Image.new("RGB", (960, 1664), (10, 200, 10)).save(face)
    controller = SceneController(
        scene_settings, FakeStore(demo_catalog()), FakeRenderer(), EventBus(), face, fonts_loader=_fonts
    )
    await controller.start()
    await settle(controller)
    import io

    still = Image.open(io.BytesIO(controller.still_png))
    assert still.size == (480, 832)
    assert still.getpixel((240, 80)) == (10, 200, 10)
    await controller.stop()


# ---------- T027 ----------


async def test_highlight_follows_what_is_heard_not_what_is_prepared(rig, caplog: pytest.LogCaptureFixture) -> None:
    controller, _, bus, _, events = rig
    caplog.set_level(logging.INFO, logger="ai_live")
    bus.publish(sentence("u1", "toner", "seg-7"))
    await settle(controller)
    assert controller.highlight is None
    controller.playback_started("u1", 0, "Nước hoa hồng")
    await settle(controller)
    assert controller.highlight == "toner"
    assert controller.version == 2
    [event] = scene_events(events, "highlight")
    assert event == {"kind": "highlight", "product_id": "toner", "segment_id": "seg-7", "utterance_id": "u1"}
    [record] = [r for r in caplog.records if r.getMessage() == "scene_highlight"]
    assert record.fields["product_id"] == "toner" and record.fields["played_at"]


async def test_sentence_still_queued_is_read_at_playback(rig) -> None:
    controller, _, bus, _, _ = rig
    bus.publish(sentence("u1", "kem-chong-nang"))
    # No await between: the reader task has not run yet.
    controller.playback_started("u1", 0, "x")
    assert controller.highlight == "kem-chong-nang"
    await settle(controller)


async def test_general_segment_clears_and_comment_keeps(rig) -> None:
    controller, _, bus, _, _ = rig
    bus.publish(sentence("u1", "toner"))
    bus.publish(sentence("u2", None, "seg-general"))
    await settle(controller)
    controller.playback_started("u1", 0, "x")
    assert controller.highlight == "toner"
    controller.playback_started("comment-reply-1", 0, "Dạ chị ơi")  # not a scripted sentence (FR-017)
    assert controller.highlight == "toner"
    controller.playback_started("u2", 0, "x")
    assert controller.highlight is None
    await settle(controller)


async def test_pause_keeps_idle_and_ended_clear(rig) -> None:
    controller, _, bus, _, _ = rig
    bus.publish(sentence("u1", "toner"))
    await settle(controller)
    controller.playback_started("u1", 0, "x")
    bus.publish(Event(EventType.SHOW_STATE, {"state": "paused"}))
    await settle(controller)
    assert controller.highlight == "toner"
    for state in ("ended", "idle"):
        controller.playback_started("u1", 0, "x")
        bus.publish(Event(EventType.SHOW_STATE, {"state": state}))
        await settle(controller)
        assert controller.highlight is None


async def test_product_without_a_slot_is_not_highlighted(settings, tmp_path: Path) -> None:
    products = [product("p", primary=True), *[product(f"s{i}") for i in range(3)]]
    root = make_scene_dir(tmp_path / "small", [p.id for p in products], scene={"layout": {"max_slots": 2}})
    small = settings.model_copy(update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER})
    bus = EventBus()
    controller = SceneController(small, FakeStore(catalog(*products)), FakeRenderer(), bus, None, fonts_loader=_fonts)
    await controller.start()
    await settle(controller)
    assert controller.status()["overflow"] == ["s1", "s2"]
    bus.publish(sentence("u1", "s2"))
    await settle(controller)
    controller.playback_started("u1", 0, "x")
    await settle(controller)
    assert controller._layout is not None
    assert not any(s.highlighted for s in controller._layout.slots)
    await controller.stop()


async def test_tracked_utterances_are_bounded(rig) -> None:
    controller, _, bus, _, _ = rig
    from ai_live.scene.controller import MAX_TRACKED_UTTERANCES

    for i in range(MAX_TRACKED_UTTERANCES + 50):
        bus.publish(sentence(f"u{i}", "toner"))
    await settle(controller)
    assert len(controller._utterances) == MAX_TRACKED_UTTERANCES
    assert "u0" not in controller._utterances


# ---------- T031 ----------


@pytest.fixture
async def subtitled(scene_settings):
    renderer = FakeRenderer()
    controller = SceneController(
        scene_settings.model_copy(update={"scene_subtitles": True}),
        FakeStore(demo_catalog()),
        renderer,
        EventBus(),
        None,
        fonts_loader=_fonts,
    )
    await controller.start()
    await settle(controller)
    yield controller, renderer
    await controller.stop()


async def test_subtitle_shows_while_playing_and_clears_on_end(subtitled) -> None:
    controller, renderer = subtitled
    assert controller.host_config()["subtitles"] is True
    controller.playback_started("c1", 0, "Dạ chị ơi, kem này thấm nhanh lắm ạ.")
    await settle(controller)
    layer = renderer.last("subtitle")
    assert layer.image is not None
    # Only the subtitle changed: the desk and cards were not redrawn.
    assert [n for n, _ in renderer.layers] == ["base", "subtitle"]
    controller.playback_ended("c1", 0)
    await settle(controller)
    assert renderer.last("subtitle").image is None


async def test_subtitle_clears_on_stop(subtitled) -> None:
    controller, renderer = subtitled
    controller.playback_started("c1", 0, "Dạ.")
    await settle(controller)
    controller.playback_stopped()
    await settle(controller)
    assert renderer.last("subtitle").image is None


async def test_subtitle_is_at_most_two_lines(subtitled) -> None:
    controller, renderer = subtitled
    controller.playback_started("c1", 0, "Dạ kem chống nắng Mây Sáng có hai dung tích ạ. " * 6)
    await settle(controller)
    layer = renderer.last("subtitle")
    assert layer.image is not None and layer.image.height < 832 * 0.085 + 10


async def test_no_subtitle_layer_when_off(rig) -> None:
    controller, renderer, _, _, _ = rig
    controller.playback_started("c1", 0, "Dạ.")
    await settle(controller)
    assert all(n == "base" for n, _ in renderer.layers)
    assert controller.host_config()["subtitles"] is False


# ---------- 011 T018: the scene block of the character in use ----------


class _Character:
    """The two fields the controller reads from `AvatarCharacter` (011 data-model §1)."""

    def __init__(self, desk_in_image: bool, desk_top: float | None) -> None:
        self.desk_in_image = desk_in_image
        self.desk_top = desk_top


def _left_desk_strip_clear(controller: SceneController, layer: SceneLayer) -> bool:
    from PIL import Image

    geometry = estimate_geometry(LABEL, "top-right")
    frame = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    assert layer.image is not None
    frame.alpha_composite(layer.image, (layer.x, layer.y))
    x1, y1, _, y2 = controller._layout.desk_box
    strip = frame.crop((x1, y1, x1 + 4, min(y2, geometry.height - 40)))
    return strip.getchannel("A").getextrema()[1] == 0


async def test_character_scene_block_moves_the_desk_and_drops_its_layer(scene_settings) -> None:
    async def draw(character: Any) -> tuple[SceneController, FakeRenderer]:
        renderer = FakeRenderer()
        controller = SceneController(
            scene_settings,
            FakeStore(demo_catalog()),
            renderer,
            EventBus(),
            None,
            fonts_loader=_fonts,
            character=character,
        )
        await controller.start()
        await settle(controller)
        await controller.stop()
        return controller, renderer

    plain, plain_renderer = await draw(None)
    in_image, renderer = await draw(_Character(desk_in_image=True, desk_top=0.84))
    assert in_image._layout.desk_box[1] > plain._layout.desk_box[1]
    assert _left_desk_strip_clear(in_image, renderer.last("base"))
    # A character without the block keeps the 009 scene: the desk is drawn.
    assert not _left_desk_strip_clear(plain, plain_renderer.last("base"))
    no_block, no_block_renderer = await draw(_Character(desk_in_image=False, desk_top=None))
    assert no_block._layout.desk_box == plain._layout.desk_box
    assert not _left_desk_strip_clear(no_block, no_block_renderer.last("base"))


# ---------- 012 T006: reload() and preview() ----------

UPLOAD_COLOR = (10, 200, 30)


def _write_upload(root: Path, pid: str, *, size: tuple[int, int] = (200, 300), color=UPLOAD_COLOR) -> str:
    from ai_live.scene.uploads import validate_and_normalize
    from fixtures.scene_builder import image_bytes, write_manifest

    image = validate_and_normalize(image_bytes("png", size=size, color=color))
    path = root / "uploads" / pid / f"{image.version_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image.png)
    stamp = "2026-11-20T09:00:00.000Z"
    version = {
        "uploaded_at": stamp,
        "source_name": "a.png",
        "width": image.width,
        "height": image.height,
        "has_alpha": True,
        "bytes": len(image.png),
        "applied_at": stamp,
        "rights_confirmed_at": stamp,
    }
    manifest = {
        "schema_version": 1,
        "customer_id": CUSTOMER,
        "products": {
            pid: {
                "active": image.version_id,
                "history": ["kit"],
                "updated_at": stamp,
                "versions": {image.version_id: version},
            }
        },
    }
    write_manifest(root, manifest)
    return image.version_id


async def test_reload_returns_after_a_fresh_draw(rig, scene_settings) -> None:
    controller, renderer, _, _, _ = rig
    vid = _write_upload(scene_settings.scene_dir, "toner")
    version = await asyncio.wait_for(controller.reload(), 5)
    assert version == controller.version == 2
    art = controller.scene.art["toner"]
    assert (art.source, art.version_id) == ("upload", vid)
    assert renderer.last("base") is renderer.layers[-1][1]


async def test_reload_logs_the_number_of_uploads(rig, scene_settings, caplog: pytest.LogCaptureFixture) -> None:
    controller, _, _, _, _ = rig
    caplog.set_level(logging.INFO, logger="ai_live")
    _write_upload(scene_settings.scene_dir, "toner")
    await asyncio.wait_for(controller.reload(), 5)
    loaded = [r for r in caplog.records if r.getMessage() == "scene_loaded"]
    assert loaded[-1].fields["uploads"] == 1  # type: ignore[attr-defined]


async def test_close_reloads_fold_into_one_and_both_see_the_latest_manifest(rig, scene_settings) -> None:
    controller, _, _, _, _ = rig
    _write_upload(scene_settings.scene_dir, "toner", color=(200, 0, 0))
    first = asyncio.create_task(controller.reload())
    latest = _write_upload(scene_settings.scene_dir, "toner", color=(0, 0, 200))
    second = asyncio.create_task(controller.reload())
    versions = await asyncio.wait_for(asyncio.gather(first, second), 5)
    assert versions == [2, 2]
    assert controller.scene.art["toner"].version_id == latest


async def test_reload_waits_for_a_draw_started_after_the_call(rig, scene_settings) -> None:
    """A draw already running when `reload()` is called read the old manifest: it must not count."""
    controller, _, bus, _, _ = rig
    bus.publish(Event(EventType.CONTENT_REPLACED, {}))
    for _ in range(5):
        await asyncio.sleep(0)  # the old draw is now under way
    vid = _write_upload(scene_settings.scene_dir, "toner")
    await asyncio.wait_for(controller.reload(), 5)
    assert controller.scene.art["toner"].version_id == vid


async def test_reload_with_the_scene_off_returns_none(settings) -> None:
    controller = SceneController(settings, FakeStore(demo_catalog()), FakeRenderer(), EventBus(), None)
    assert await asyncio.wait_for(controller.reload(), 1) is None


async def test_preview_swaps_one_image_without_touching_the_live_scene(rig, caplog: pytest.LogCaptureFixture) -> None:
    from PIL import Image

    from ai_live.scene.layout import compute_layout
    from ai_live.scene.models import ProductArt

    controller, renderer, bus, store, _ = rig
    caplog.set_level(logging.INFO, logger="ai_live")
    bus.publish(sentence("u1", "toner"))
    await settle(controller)
    controller.playback_started("u1", 0, "x")
    await settle(controller)
    version, layers, base = controller.version, len(renderer.layers), controller._base
    candidate = Image.new("RGBA", (200, 300), (*UPLOAD_COLOR, 255))
    override = ProductArt("toner", Path("candidate.png"), candidate, source="upload", version_id="0123456789ab")

    png = await controller.preview(store.catalog, {"toner": override}, controller.highlight)

    assert (controller.version, len(renderer.layers), controller._base) == (version, layers, base)
    frame = Image.open(io.BytesIO(png)).convert("RGB")
    sizes = {pid: art.image.size for pid, art in controller.scene.art.items()}
    sizes["toner"] = candidate.size
    expected = compute_layout(store.catalog.products, sizes, controller._geometry, controller.scene.layout, "toner")
    slot = next(s for s in expected.slots if s.product_id == "toner")
    assert slot.highlighted and slot.art_box is not None
    x1, y1, x2, y2 = slot.art_box
    assert frame.getpixel(((x1 + x2) // 2, (y1 + y2) // 2)) == pytest.approx(UPLOAD_COLOR, abs=8)
    logged = [r for r in caplog.records if r.getMessage() == "scene_preview"]
    assert logged and logged[-1].fields["render_ms"] >= 0  # type: ignore[attr-defined]


async def test_preview_can_remove_an_image(rig) -> None:
    controller, renderer, _, store, _ = rig
    layers = len(renderer.layers)
    png = await controller.preview(store.catalog, {"toner": None}, None)
    assert png.startswith(b"\x89PNG")
    assert "toner" in controller.scene.art and len(renderer.layers) == layers


# ---------- 012 T030: hold() for "Áp dụng bộ mới" (research R7) ----------


async def test_no_draw_runs_while_held_not_even_a_subtitle(subtitled) -> None:
    controller, renderer = subtitled
    version, layers = controller.version, len(renderer.layers)
    async with controller.hold():
        controller.playback_started("c1", 0, "Dạ chị ơi.")
        for _ in range(20):
            await asyncio.sleep(0)
        await asyncio.sleep(0.05)
        assert (controller.version, len(renderer.layers)) == (version, layers)
    await settle(controller)
    assert controller.version > version
    assert renderer.last("subtitle").image is not None


async def test_hold_waits_for_the_draw_under_way(rig) -> None:
    import threading

    controller, _, bus, _, _ = rig
    started, release = threading.Event(), threading.Event()
    real_draw = controller._draw

    def slow_draw(snap: Any) -> list[str]:
        started.set()
        release.wait(5)
        return real_draw(snap)

    controller._draw = slow_draw  # type: ignore[method-assign]
    bus.publish(Event(EventType.CONTENT_REPLACED, {}))
    await asyncio.wait_for(asyncio.to_thread(started.wait, 5), 6)
    entered = asyncio.Event()

    async def enter() -> None:
        async with controller.hold():
            entered.set()

    task = asyncio.create_task(enter())
    await asyncio.sleep(0.05)
    assert not entered.is_set()
    release.set()
    await asyncio.wait_for(task, 5)
    assert entered.is_set()


async def test_after_hold_one_draw_shows_the_new_catalog_with_its_images(rig, scene_settings) -> None:
    controller, _, _, store, _ = rig
    seen: list[tuple[str, str | None]] = []
    real_draw = controller._draw

    def recording_draw(snap: Any) -> list[str]:
        art = snap.scene.art.get("serum")
        seen.append((snap.catalog.version, art.source if art is not None else None))
        return real_draw(snap)

    controller._draw = recording_draw  # type: ignore[method-assign]
    version = controller.version
    async with controller.hold():
        store.catalog = catalog(product("serum", primary=True), product("toner"), version="v2")
        _write_upload(scene_settings.scene_dir, "serum")
        await asyncio.sleep(0.02)
    scene_version = await asyncio.wait_for(controller.reload(), 5)
    assert scene_version == controller.version == version + 1
    assert seen == [("v2", "upload")]


async def test_hold_with_the_scene_off_is_a_plain_lock(settings) -> None:
    controller = SceneController(settings, FakeStore(demo_catalog()), FakeRenderer(), EventBus(), None)
    async with controller.hold():
        pass
    assert await asyncio.wait_for(controller.reload(), 1) is None
