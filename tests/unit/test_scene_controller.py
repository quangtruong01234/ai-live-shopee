"""009 T013, T027, T031: the scene follows the content, the frame and the sentence heard; a failure never stops it."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from ai_live.core.events import Event, EventBus, EventType
from ai_live.products.models import ProductCatalog
from ai_live.scene.controller import DISABLED_HOST_CONFIG, SceneController, disabled_status
from ai_live.scene.fonts import SceneFontError, SceneFonts, load_fonts
from ai_live.scene.layout import estimate_geometry
from ai_live.scene.models import SceneLayer
from fixtures.scene_builder import CUSTOMER, catalog, demo_catalog, make_scene_dir, product

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
    same = estimate_geometry("AI", "top-right")
    listener(type(same)(same.width, same.height, same.face_bottom, same.keep_out, "fork"))
    await settle(controller)
    assert controller.version == 1
    listener(estimate_geometry("AI", "top-right", face_bottom=304))
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
    controller.on_geometry(estimate_geometry("AI", "top-right", face_bottom=300))
    await settle(controller)
    assert controller.version == 1 and renderer.layers
    await controller.stop()


async def test_failed_host_send_is_only_logged(rig, caplog: pytest.LogCaptureFixture) -> None:
    controller, renderer, _, _, _ = rig
    caplog.set_level(logging.INFO, logger="ai_live")

    async def broken(message: dict[str, Any]) -> None:
        raise ConnectionError("host gone")

    renderer.send_to_host = broken
    controller.on_geometry(estimate_geometry("AI", "top-right", face_bottom=300))
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
