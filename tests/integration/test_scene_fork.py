"""009 T015: the scene through `LiveTalkingRenderer` to the (fake) fork (contracts/fork-protocol.md §1–§4).

A real `SceneController` draws, a real renderer sends `scene_layer` over the fork WebSocket; the fake fork reports its
frame in `hello.scene`, may refuse a layer, and adds `scene_ms` to `stats`.
"""

from __future__ import annotations

import base64
import io
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from PIL import Image

from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.core.events import EventBus, EventType
from ai_live.core.models import TurnOutcome
from ai_live.director.latency import LatencyTracker
from ai_live.scene.background import BackgroundController
from ai_live.scene.controller import SceneController
from fixtures.background_builder import CHARACTER_ID as BG_CHARACTER
from fixtures.background_builder import make_background_dir
from fixtures.fake_fork import FakeFork
from fixtures.scene_builder import CUSTOMER, catalog, demo_catalog, make_scene_dir

pytestmark = pytest.mark.anyio

SAMPLE_RATE = 16000
FACE_BOTTOM = 304
FORK_SCENE = {
    "frame_size": [480, 832],
    "face_bottom": FACE_BOTTOM,
    "keep_out": [
        {"name": "ai_label", "box": [402, 8, 472, 68]},
        {"name": "watermark", "box": [0, 0, 90, 30]},
    ],
}


class Store:
    def __init__(self) -> None:
        self.catalog = demo_catalog()


class HostLink:
    def __init__(self) -> None:
        self.lipsync_session: str | None = "sess-1"
        self.host_ready = True
        self.sent: list[dict[str, Any]] = []

    async def send_to_host(self, message: dict[str, Any]) -> bool:
        self.sent.append(message)
        return True

    def on_session_change(self, callback: Callable[[str | None], None]) -> None:
        pass


async def audio(chunks: int = 2) -> AsyncIterator[bytes]:
    for _ in range(chunks):
        yield b"\x01\x00" * 1600


async def until(predicate: Callable[[], bool], timeout_s: float = 5.0) -> None:
    # Polling on purpose: the fake fork exposes plain dicts, not events.
    with anyio.fail_after(timeout_s):
        while not predicate():  # noqa: ASYNC110
            await anyio.sleep(0.01)


def decode(message: dict[str, Any]) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(message["png_b64"])))


Rig = tuple[SceneController, LiveTalkingRenderer, EventBus]
# 014: every background controller the rig made, newest last.
BACKGROUNDS: list[BackgroundController] = []


@pytest.fixture
async def make_rig(settings, tmp_path: Path):
    made: list[tuple[SceneController, LiveTalkingRenderer]] = []

    async def factory(fork: FakeFork, *, subtitles: bool = False, background: dict[str, Any] | None = None) -> Rig:
        root = make_scene_dir(
            tmp_path / "scenes" / "demo",
            [p.id for p in demo_catalog().products],
            scene={"background": background} if background is not None else None,
            distinct_colors=background is not None,
        )
        scene_settings = settings.model_copy(
            update={"scene_enabled": True, "scene_dir": root, "customer_id": CUSTOMER, "scene_subtitles": subtitles}
        )
        bus = EventBus()
        renderer = LiveTalkingRenderer(fork.url, HostLink(), bus=bus)
        controller = SceneController(scene_settings, Store(), renderer, bus, None)
        if background is not None:
            # Same wiring as `main.py` (014 T029): made before the renderer starts so it hears the first `hello`.
            character = tmp_path / "avatars" / BG_CHARACTER
            character.mkdir(parents=True, exist_ok=True)
            make_background_dir(character)
            BACKGROUNDS.append(BackgroundController(renderer, bus, character))
            controller.add_scene_loaded_listener(BACKGROUNDS[-1].on_scene_loaded)
            await BACKGROUNDS[-1].start()
        # Same order as the app: the renderer first, so the fork link exists to take the first layer.
        await renderer.start()
        await controller.start()
        made.append((controller, renderer))
        await until(lambda: renderer.ready)
        return controller, renderer, bus

    yield factory
    for controller, renderer in made:
        await controller.stop()
        await renderer.stop()


async def test_fork_gets_the_base_layer_drawn_for_its_frame(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE) as fork:
        controller, _, _ = await make_rig(fork)
        await until(lambda: "base" in fork.scene_layers)
        await controller.wait_idle()
        status = controller.status()
        assert status["geometry"] == {"width": 480, "height": 832, "face_bottom": FACE_BOTTOM, "source": "fork"}
        message = fork.scene_layers["base"]
        image = decode(message)
        assert image.mode == "RGBA"
        # Inside the frame and wholly below the chin line the fork checks (fork-protocol §2).
        assert message["y"] >= FACE_BOTTOM + 8
        assert message["x"] + image.width <= 480 and message["y"] + image.height <= 832


async def test_layers_are_sent_again_after_a_fork_restart(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE) as fork:
        await make_rig(fork)
        await until(lambda: "base" in fork.scene_layers)
        first_connections = fork.connections
        fork.scene_layers.clear()  # a restarted fork has no layer
        await fork.restart()
        await until(lambda: fork.connections > first_connections and "base" in fork.scene_layers)


async def test_rejected_layer_does_not_fail_the_turn(make_rig, caplog: pytest.LogCaptureFixture) -> None:
    async with FakeFork(scene=FORK_SCENE) as fork:
        fork.reject_scene = True
        _, renderer, bus = await make_rig(fork)
        events = bus.subscribe()
        with caplog.at_level(logging.WARNING, logger="ai_live.avatar"):
            await until(lambda: any(m.get("type") == "scene_layer" for m in fork.received))
            await until(lambda: any(r.getMessage() == "scene_rejected" for r in caplog.records))
            await renderer.speak("u1", "Dạ chào cả nhà.", audio(), SAMPLE_RATE)
        stats = renderer.render_stats("u1")
        assert stats is not None and stats.frames > 0
        errors = [e for e in events.drain() if e.type is EventType.SCENE and e.payload.get("kind") == "error"]
        assert errors and "base" in errors[0].payload["message"]


async def test_older_fork_without_scene_gets_no_layer(make_rig, caplog: pytest.LogCaptureFixture) -> None:
    async with FakeFork() as fork:
        with caplog.at_level(logging.WARNING, logger="ai_live.avatar"):
            controller, renderer, _ = await make_rig(fork)
            await controller.wait_idle()
            await renderer.speak("u1", "Dạ.", audio(), SAMPLE_RATE)
        assert not any(m.get("type") == "scene_layer" for m in fork.received)
        assert any(r.getMessage() == "scene_unsupported" for r in caplog.records)
        # The controller keeps its own estimate; the still image is still drawn for a fall-back.
        assert controller.status()["geometry"]["source"] == "estimate"
        assert controller.still_png is not None


async def test_subtitle_layer_follows_the_spoken_sentence(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE) as fork:
        fork.time_scale = 1.0
        controller, renderer, _ = await make_rig(fork, subtitles=True)
        await until(lambda: "base" in fork.scene_layers)
        subtitles: list[bool] = []

        def watch() -> bool:
            seen = [m for m in fork.received if m.get("type") == "scene_layer" and m.get("name") == "subtitle"]
            subtitles[:] = [m["png_b64"] is not None for m in seen]
            return subtitles[-2:] == [True, False]

        await renderer.speak("u1", "Dạ kem này thấm nhanh lắm ạ.", audio(), SAMPLE_RATE)
        await until(watch)
        assert "subtitle" not in fork.scene_layers  # cleared once the sentence was heard


async def test_scene_ms_reaches_render_stats_and_latency(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE) as fork:
        fork.scene_ms = 1.5
        _, renderer, _ = await make_rig(fork)
        await renderer.speak("u1", "Câu một.", audio(), SAMPLE_RATE)
        fork.scene_ms = 2.5
        await renderer.speak("u1", "Câu hai.", audio(), SAMPLE_RATE)
        stats = renderer.render_stats("u1")
        assert stats is not None and stats.scene_ms == pytest.approx(2.0)
        tracker = LatencyTracker()
        turn = tracker.finish("u1", TurnOutcome.COMPLETED, render=stats)
        assert turn is not None and turn.to_row()["scene_ms"] == 2.0


# ---------- 014 T022: the backdrop through the renderer to the (fake) fork (fork-protocol §1, §3) ----------

KE_HANG = {"style": "ke_hang", "softness_px": 3.0, "brightness": 0.95}


async def test_ke_hang_sends_exactly_one_plate_of_frame_size_after_hello(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE, background=FakeFork.background_block()) as fork:
        controller, _, _ = await make_rig(fork, background=KE_HANG)
        await until(lambda: "base" in fork.scene_layers and len(fork.scene_backgrounds) >= 1)
        await controller.wait_idle()
        await anyio.sleep(0.2)  # a second send would have arrived by now
        assert len(fork.scene_backgrounds) == 1
        plate = decode(fork.scene_backgrounds[0])
        assert (plate.format, plate.size) == ("PNG", (480, 832))
        status = BACKGROUNDS[-1].status()
        assert (status["active"], status["mask_status"]) == (True, "valid")
        # The 009/013 layers still go out next to the plate; the AI label stays the fork's own.
        assert "base" in fork.scene_layers


async def test_plate_is_sent_again_after_a_fork_restart(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE, background=FakeFork.background_block()) as fork:
        await make_rig(fork, background=KE_HANG)
        await until(lambda: len(fork.scene_backgrounds) == 1)
        first_connections = fork.connections
        await fork.restart()
        await until(lambda: fork.connections > first_connections and len(fork.scene_backgrounds) == 2)
        assert fork.scene_backgrounds[1]["png_b64"] == fork.scene_backgrounds[0]["png_b64"]


async def test_a_new_product_set_sends_a_new_plate(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE, background=FakeFork.background_block()) as fork:
        controller, _, _ = await make_rig(fork, background=KE_HANG)
        await until(lambda: len(fork.scene_backgrounds) == 1)
        first = demo_catalog().products[0]
        # 012 "Áp dụng bộ mới": a smaller set, then the reload the apply route awaits.
        controller._store.catalog = catalog(first)  # noqa: SLF001
        await controller.reload()
        await until(lambda: len(fork.scene_backgrounds) == 2)
        assert fork.scene_backgrounds[1]["png_b64"] != fork.scene_backgrounds[0]["png_b64"]
        assert set(BACKGROUNDS[-1].status()["items"]) == {first.id}


async def test_goc_scene_sends_no_plate(make_rig) -> None:
    async with FakeFork(scene=FORK_SCENE, background=FakeFork.background_block()) as fork:
        controller, _, _ = await make_rig(fork, background={"style": "goc"})
        await until(lambda: "base" in fork.scene_layers)
        await controller.wait_idle()
        await anyio.sleep(0.2)
        assert fork.scene_backgrounds == []
