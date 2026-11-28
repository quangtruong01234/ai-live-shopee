"""014 T020: the app side of the new room behind the host (adapters.md §4, data-model §5, events.md; FR-006, FR-007)."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from ai_live.core.events import EventBus, EventType
from ai_live.core.protocols import BackgroundSink, ForkBackgroundStatus
from ai_live.scene.backdrop import BackdropResult, render_backdrop
from ai_live.scene.background import BackgroundController, disabled_background_status
from ai_live.scene.loader import load_scene_set
from ai_live.scene.models import SceneSet
from fixtures.background_builder import CHARACTER_ID, make_background_dir
from fixtures.fake_fork import FakeFork
from fixtures.scene_builder import make_scene_dir

pytestmark = pytest.mark.anyio

KE_HANG = {"background": {"style": "ke_hang"}}
STARTED_FIELDS = {
    "style",
    "active",
    "mask_status",
    "fallback_reason",
    "method",
    "reviewed",
    "items",
    "plate_bytes",
    "plate_ms",
}


class FakeSink:
    """Behaves like `LiveTalkingRenderer` for the background: keeps the plate, sends it on `set` once linked, and on
    every `hello` tells the listeners first and then sends the plate it holds again (fork-protocol §3)."""

    def __init__(self) -> None:
        self.listeners: list[Callable[[ForkBackgroundStatus | None], None]] = []
        self.plate: bytes | None = None
        self.plate_set = False
        self.status: ForkBackgroundStatus | None = None
        self.linked = False
        self.sent: list[bytes | None] = []

    def set_scene_background(self, plate_png: bytes | None) -> None:
        self.plate, self.plate_set = plate_png, True
        if self.linked and self.status is not None:
            self.sent.append(plate_png)

    def add_background_status_listener(self, callback: Callable[[ForkBackgroundStatus | None], None]) -> None:
        self.listeners.append(callback)

    def hello(self, block: dict[str, Any] | None) -> None:
        self.linked = True
        self.status = ForkBackgroundStatus.from_hello(block)
        self._notify()
        if self.status is not None and self.plate_set:
            self.sent.append(self.plate)

    def error(self, prefix: str, message: str) -> None:
        if self.status is not None:
            from dataclasses import replace

            self.status = replace(self.status, reason=f"{prefix}:{message}")
        self._notify()

    def _notify(self) -> None:
        for callback in self.listeners:
            callback(self.status)


def scene_of(tmp_path: Path, ids: list[str], *, scene: dict[str, Any] | None = None, name: str = "demo") -> SceneSet:
    root = make_scene_dir(tmp_path / "scenes" / name, ids, scene=scene, distinct_colors=True)
    return load_scene_set(root, ids)


def character_dir(tmp_path: Path, variant: str = "valid", **kw: Any) -> Path:
    path = tmp_path / "avatars" / CHARACTER_ID
    path.mkdir(parents=True, exist_ok=True)
    make_background_dir(path, variant, **kw)  # type: ignore[arg-type]
    return path


def make(tmp_path: Path, renderer: Any, *, variant: str = "valid", **kw: Any) -> tuple[BackgroundController, EventBus]:
    bus = EventBus()
    controller = BackgroundController(renderer, bus, character_dir(tmp_path, variant), **kw)
    return controller, bus


def records(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, Any]]:
    return [getattr(r, "fields", {}) for r in caplog.records if r.getMessage() == event]


def background_events(sub: Any) -> list[dict[str, Any]]:
    return [e.payload for e in sub.drain() if e.type is EventType.SCENE and e.payload.get("kind") == "background"]


async def test_ke_hang_with_valid_masks_goes_live(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    sink = FakeSink()
    assert isinstance(sink, BackgroundSink)
    threads: list[str] = []

    def render(*args: Any) -> BackdropResult:
        threads.append("worker" if _off_loop() else "loop")
        return render_backdrop(*args)

    controller, _ = make(tmp_path, sink, render=render)
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["a", "b"], scene=KE_HANG))
    assert threads == ["worker"]  # drawn in `asyncio.to_thread`, never on the event loop
    sink.hello(FakeFork.background_block())

    assert len(sink.sent) == 1 and sink.sent[0] is not None
    plate = Image.open(io.BytesIO(sink.sent[0]))
    assert (plate.format, plate.mode, plate.size) == ("PNG", "RGB", (480, 832))
    status = controller.status()
    assert status["style"] == "ke_hang"
    assert status["active"] is True
    assert status["mask_status"] == "valid"
    assert status["fallback_reason"] is None
    assert status["reviewed"] is False
    assert set(status["items"]) == {"a", "b"}
    assert status["changed_at"].endswith(("Z", "+00:00"))


def _off_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return True
    return False


async def test_goc_keeps_the_original_room(tmp_path: Path) -> None:
    sink = FakeSink()
    calls: list[Any] = []
    controller, _ = make(tmp_path, sink, render=lambda *a: calls.append(a) or render_backdrop(*a))
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["a"]))
    sink.hello(FakeFork.background_block())
    assert sink.sent == []  # no plate sent at all
    status = controller.status()
    assert (status["style"], status["active"], status["fallback_reason"], status["items"]) == (
        "goc",
        False,
        "style_goc",
        [],
    )


async def test_started_is_logged_with_every_field_at_startup_and_on_each_hello(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    sink = FakeSink()
    controller, _ = make(tmp_path, sink)
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["a"], scene=KE_HANG))
    first = records(caplog, "scene_background_started")
    assert len(first) == 1 and STARTED_FIELDS <= set(first[0])
    assert first[0]["mask_status"] == "unknown" and first[0]["plate_bytes"] > 0

    sink.hello(FakeFork.background_block())
    sink.hello(FakeFork.background_block())  # the fork restarted
    logged = records(caplog, "scene_background_started")
    assert len(logged) == 3
    assert [r["mask_status"] for r in logged[1:]] == ["valid", "valid"]
    assert [r["active"] for r in logged[1:]] == [True, True]
    assert all(r["method"] == "plate" for r in logged[1:])
    assert sink.sent.count(None) == 0 and len(sink.sent) == 2  # one plate per hello


async def test_a_new_product_set_draws_once_more(tmp_path: Path) -> None:
    sink = FakeSink()
    calls: list[tuple[str, ...]] = []

    def render(config, art, *rest):  # type: ignore[no-untyped-def]
        calls.append(tuple(art))
        return render_backdrop(config, art, *rest)

    controller, _ = make(tmp_path, sink, render=render)
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["a", "b"], scene=KE_HANG))
    sink.hello(FakeFork.background_block())
    await controller.on_scene_loaded(scene_of(tmp_path, ["c"], scene=KE_HANG, name="demo2"))
    assert calls == [("a", "b"), ("c",)]
    assert len(sink.sent) == 2 and sink.sent[0] != sink.sent[1]
    assert controller.status()["items"] and set(controller.status()["items"]) == {"c"}


async def test_another_customer_set_keeps_no_old_item(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, _ = make(tmp_path, sink)
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["shop1_a"], scene=KE_HANG))
    await controller.on_scene_loaded(
        scene_of(tmp_path, ["shop2_b"], scene={"background": {"style": "ke_hang", "max_items": 4}}, name="shop2")
    )
    assert controller.status()["items"] == ["shop2_b"] * 4


async def test_status_changes_reach_the_event_bus(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, bus = make(tmp_path, sink)
    sub = bus.subscribe()
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["a"], scene=KE_HANG))
    sink.hello(FakeFork.background_block())
    events = background_events(sub)
    assert events, "no SCENE background event"
    last = events[-1]
    assert (last["active"], last["mask_status"], last["fallback_reason"]) == (True, "valid", None)

    sink.error("failed", "ValueError: x")
    last = background_events(sub)[-1]
    assert (last["active"], last["fallback_reason"]) == (False, "failed:ValueError: x")


async def test_not_prepared_clears_the_plate_on_the_fork(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, _ = make(tmp_path, sink, variant="missing")
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["a"], scene=KE_HANG))
    sink.hello(FakeFork.background_block("missing", reason="not_prepared"))
    # A fork without masks refuses a plate (fork-protocol §3): it only ever gets "no plate".
    assert all(p is None for p in sink.sent)
    status = controller.status()
    assert (status["active"], status["mask_status"], status["fallback_reason"]) == (False, "missing", "not_prepared")


async def test_before_any_hello_the_fork_is_not_known(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, _ = make(tmp_path, sink)
    await controller.start()
    await controller.on_scene_loaded(scene_of(tmp_path, ["a"], scene=KE_HANG))
    status = controller.status()
    assert (status["active"], status["mask_status"], status["fallback_reason"]) == (
        False,
        "unknown",
        "fork_unsupported",
    )


# ---------- 014 T034: every fallback reason, in data-model §5 order (FR-010, FR-011) ----------


def message_of(status: dict[str, Any]) -> str:
    message = status["fallback_message"]
    assert isinstance(message, str) and message, status
    return message


async def started(
    tmp_path: Path, renderer: Any, scene: SceneSet, *, variant: str = "valid", **kw: Any
) -> tuple[BackgroundController, Any]:
    controller, bus = make(tmp_path, renderer, variant=variant, **kw)
    sub = bus.subscribe()
    await controller.start()
    await controller.on_scene_loaded(scene)
    return controller, sub


def assert_fallback(controller: BackgroundController, sub: Any, reason: str, *needles: str) -> None:
    status = controller.status()
    assert (status["active"], status["fallback_reason"]) == (False, reason), status
    message = message_of(status)
    for needle in needles:
        assert needle in message, (needle, message)
    events = background_events(sub)
    assert events and events[-1]["fallback_reason"] == reason
    assert events[-1]["fallback_message"] == message


async def test_style_goc_says_how_to_turn_the_room_on(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, sub = await started(tmp_path, sink, scene_of(tmp_path, ["a"]))
    sink.hello(FakeFork.background_block())
    assert_fallback(controller, sub, "style_goc", "phòng gốc", "scene.json")


def test_scene_disabled_status_has_every_field() -> None:
    status = disabled_background_status()
    assert set(status) == {
        "style",
        "active",
        "mask_status",
        "fallback_reason",
        "fallback_message",
        "reviewed",
        "items",
        "changed_at",
    }
    assert (status["active"], status["fallback_reason"], status["mask_status"]) == (False, "scene_disabled", "unknown")
    assert "SCENE_ENABLED" in message_of(status)


@pytest.mark.parametrize("style", ["bang_shop"])
async def test_a_style_not_made_yet_falls_back(tmp_path: Path, style: str) -> None:
    sink = FakeSink()
    scene = scene_of(tmp_path, ["a"], scene={"background": {"style": style}})
    controller, sub = await started(tmp_path, sink, scene)
    sink.hello(FakeFork.background_block())
    assert_fallback(controller, sub, "style_not_available", style, "ke_hang")
    assert sink.sent == []


async def test_no_cut_out_product_falls_back(tmp_path: Path) -> None:
    sink = FakeSink()
    root = make_scene_dir(tmp_path / "scenes" / "demo", ["a"], scene=KE_HANG)
    controller, sub = await started(tmp_path, sink, load_scene_set(root, ["not-in-the-set"]))
    sink.hello(FakeFork.background_block())
    assert_fallback(controller, sub, "no_product_art", "Chưa có ảnh sản phẩm đã bỏ nền cho kệ hàng")
    assert sink.sent == []


async def test_a_failed_draw_falls_back_and_never_raises(tmp_path: Path) -> None:
    sink = FakeSink()

    def broken(*_: Any) -> BackdropResult:
        raise RuntimeError("boom")

    controller, sub = await started(tmp_path, sink, scene_of(tmp_path, ["a"], scene=KE_HANG), render=broken)
    sink.hello(FakeFork.background_block())
    assert_fallback(controller, sub, "plate_failed", "ai_live.scene check")
    assert sink.sent == []


async def test_static_avatar_has_no_fork_frame(tmp_path: Path) -> None:
    controller, sub = await started(tmp_path, object(), scene_of(tmp_path, ["a"], scene=KE_HANG))
    assert_fallback(controller, sub, "avatar_static", "AVATAR_MODE=livetalking")
    assert controller.status()["mask_status"] == "unknown"


async def test_a_fork_without_background_support_falls_back(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, sub = await started(tmp_path, sink, scene_of(tmp_path, ["a"], scene=KE_HANG))
    sink.hello(None)  # an older fork: no `background` block in `hello`
    assert_fallback(controller, sub, "fork_unsupported", "run.ps1")
    assert all(p is None for p in sink.sent)


async def test_not_prepared_names_the_prepare_command(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, sub = await started(tmp_path, sink, scene_of(tmp_path, ["a"], scene=KE_HANG), variant="missing")
    sink.hello(FakeFork.background_block("missing", reason="not_prepared"))
    assert_fallback(
        controller,
        sub,
        "not_prepared",
        "Nhân vật chưa có nền, live sẽ hiện phòng gốc",
        f"uv run python -m ai_live.avatar background-prepare {CHARACTER_ID}",
    )
    assert all(p is None for p in sink.sent)


@pytest.mark.parametrize(
    ("detail", "words"),
    [
        ("frame_not_prepared:3", "3 khung"),
        ("size_mismatch", "cỡ khung"),
        ("character_mismatch", "nhân vật khác"),
        ("mask_unreadable:masks/0a1b2c3d.png", "masks/0a1b2c3d.png"),
    ],
)
async def test_a_mismatch_gives_its_detail_and_never_a_plate(tmp_path: Path, detail: str, words: str) -> None:
    sink = FakeSink()
    controller, sub = await started(tmp_path, sink, scene_of(tmp_path, ["a"], scene=KE_HANG), variant="mismatch")
    sink.hello(FakeFork.background_block("mismatch", reason=detail))
    assert_fallback(controller, sub, f"mismatch:{detail}", words, f"background-prepare {CHARACTER_ID}")
    # fork-protocol §3: the app never hands a plate to a fork that must refuse it.
    assert all(p is None for p in sink.sent)
    assert controller.status()["mask_status"] == "mismatch"


async def test_a_fork_turning_invalid_gets_no_plate_any_more(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, _ = await started(tmp_path, sink, scene_of(tmp_path, ["a"], scene=KE_HANG))
    sink.hello(FakeFork.background_block())
    assert sink.sent and sink.sent[-1] is not None
    sink.hello(FakeFork.background_block("mismatch", reason="frame_not_prepared:1"))  # the loop was re-made
    assert sink.plate is None and sink.sent[-1] is None


@pytest.mark.parametrize(("prefix", "words"), [("rejected", "từ chối"), ("failed", "phòng gốc")])
async def test_fork_errors_fall_back_and_raise_a_scene_error(tmp_path: Path, prefix: str, words: str) -> None:
    sink = FakeSink()
    controller, sub = await started(tmp_path, sink, scene_of(tmp_path, ["a"], scene=KE_HANG))
    sink.hello(FakeFork.background_block())
    sub.drain()
    sink.error(prefix, "sai cỡ khung")
    events = list(sub.drain())
    status = controller.status()
    assert (status["active"], status["fallback_reason"]) == (False, f"{prefix}:sai cỡ khung")
    message = message_of(status)
    assert words in message and "sai cỡ khung" in message
    background = [e.payload for e in events if e.type is EventType.SCENE and e.payload.get("kind") == "background"]
    assert background and background[-1]["fallback_message"] == message
    # T043: shown like any other scene error on the control page (events.md), never a new watchdog rule.
    errors = [e.payload for e in events if e.type is EventType.SCENE and e.payload.get("kind") == "error"]
    assert len(errors) == 1
    assert errors[0]["message"].startswith("Nền sau host") and "sai cỡ khung" in errors[0]["message"]


async def test_active_has_no_fallback_message_even_unreviewed(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, _ = await started(tmp_path, sink, scene_of(tmp_path, ["a"], scene=KE_HANG))
    sink.hello(FakeFork.background_block(reviewed=False))
    status = controller.status()
    assert (status["active"], status["reviewed"], status["fallback_message"]) == (True, False, None)


async def test_the_still_goes_into_the_same_room_as_the_video(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, _ = make(tmp_path, sink)
    told: list[str] = []
    controller.add_room_listener(lambda: told.append("room"))
    await controller.start()
    face = Image.new("RGB", (480, 832), (10, 200, 30))
    await controller.on_scene_loaded(scene_of(tmp_path, ["a", "b"], scene=KE_HANG))
    assert told  # a new plate may change the room
    assert controller.room_face(face) is None  # no `hello` yet: the video still shows the original room

    told.clear()
    sink.hello(FakeFork.background_block())
    assert told  # the fork now composites
    room_face = controller.room_face(face)
    assert room_face is not None and room_face.size == face.size
    plate = Image.open(io.BytesIO(sink.sent[0])).convert("RGB")
    assert room_face.getpixel((0, 0)) == plate.getpixel((0, 0))  # the room around the host is the plate
    assert room_face.getpixel((240, 416)) == face.getpixel((240, 416))  # the host stays
    assert controller.room_face(face) is room_face  # drawn once per face and plate

    sink.hello(FakeFork.background_block(status="missing", reason="not_prepared"))
    assert controller.room_face(face) is None  # the video is back in the original room: so is the still


async def test_the_original_room_keeps_the_still_as_it_is(tmp_path: Path) -> None:
    sink = FakeSink()
    controller, _ = await started(tmp_path, sink, scene_of(tmp_path, ["a"]))
    sink.hello(FakeFork.background_block())
    assert controller.room_face(Image.new("RGB", (480, 832))) is None
