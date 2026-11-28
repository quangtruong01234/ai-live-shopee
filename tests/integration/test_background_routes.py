"""014 T035: the room behind the host over HTTP (contracts/api.md, data-model §5, research R13; FR-012).

The real app runs with the lip-sync renderer against a fake fork that reports a `background` block in `hello`.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai_live.app.main import create_app
from ai_live.scene.layout import estimate_label_box
from fixtures.background_builder import make_background_dir
from fixtures.character_builder import CHARACTER_ID, CUSTOMER_ID, READY_PREPARE, make_character_dir
from fixtures.fake_fork import FakeFork
from fixtures.fake_host import FakeHostConnection
from fixtures.scene_builder import make_scene_dir

pytestmark = pytest.mark.anyio

# Slugs of the products in `valid_docx()` (primary first in the file).
IDS = ["kem-chong-nang-x", "sua-rua-mat-y", "toner-z"]
FIELDS = {"style", "active", "mask_status", "fallback_reason", "fallback_message", "reviewed", "items", "changed_at"}
ROOM_PX = (20, 200)  # room in every fixture mask, above the desk, away from the label
PERSON_PX = (240, 200)  # head ellipse of the first mask
ROOM_RGB = (140, 130, 120)
PERSON_RGB = (160, 40, 70)


def lipsync_settings(app_settings: Any, tmp_path: Path, fork_url: str, *, variant: str = "valid") -> Any:
    avatar_dir = make_character_dir(tmp_path / "avatars", prepare=READY_PREPARE)
    make_background_dir(avatar_dir, variant)  # type: ignore[arg-type]
    root = make_scene_dir(
        tmp_path / "scenes" / "demo",
        IDS,
        customer_id=CUSTOMER_ID,
        scene={"background": {"style": "ke_hang"}},
        distinct_colors=True,
    )
    return app_settings.model_copy(
        update={
            "avatar_mode": "livetalking",
            "customer_id": CUSTOMER_ID,
            "avatar_id": CHARACTER_ID,
            "avatar_dir": avatar_dir,
            "livetalking_url": fork_url,
            "scene_enabled": True,
            "scene_dir": root,
        }
    )


@asynccontextmanager
async def running(settings: Any) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        ctx = app.state.ctx
        if settings.avatar_mode == "livetalking":
            # The fork connects only once a host page reports its lip-sync session.
            host = FakeHostConnection(ctx.renderer, ack_delay_s=0.02)
            await ctx.renderer.attach(host)
            ctx.renderer.handle_message(host, {"type": "ready", "lipsync_session": "sess-1"})
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def wait_status(client: httpx.AsyncClient, pred: Any, limit_s: float = 5.0) -> dict[str, Any]:
    body: dict[str, Any] = {}
    try:
        with anyio.fail_after(limit_s):
            while True:
                body = (await client.get("/api/scene/background")).json()
                if pred(body):
                    return body
                await anyio.sleep(0.05)
    except TimeoutError:
        pytest.fail(f"background status never matched: {body}")


def close(a: tuple[int, ...], b: tuple[int, ...], tol: int = 3) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=False))


async def test_status_preview_and_scene_block(app_settings, tmp_path: Path) -> None:
    async with FakeFork(background=FakeFork.background_block()) as fork:
        async with running(lipsync_settings(app_settings, tmp_path, fork.url)) as client:
            body = await wait_status(client, lambda b: b.get("active") is True)
            assert set(body) == FIELDS
            assert (body["style"], body["mask_status"], body["fallback_reason"], body["fallback_message"]) == (
                "ke_hang",
                "valid",
                None,
                None,
            )
            assert body["reviewed"] is False and body["items"]

            scene = (await client.get("/api/scene")).json()
            assert scene["background"]["active"] is True and set(scene["background"]) == FIELDS

            await wait_status(client, lambda _: bool(fork.scene_backgrounds))
            r = await client.get("/api/scene/background/preview.png")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "image/png"
            assert r.headers["cache-control"] == "no-store"
            preview = Image.open(io.BytesIO(r.content)).convert("RGB")
            assert preview.size == (480, 832)

            plate = Image.open(io.BytesIO(fork_plate(fork))).convert("RGB")
            # The room comes from the plate, the host from the sample frame.
            room = preview.getpixel(ROOM_PX)
            assert close(room, plate.getpixel(ROOM_PX)) and not close(room, ROOM_RGB, 10)
            assert close(preview.getpixel(PERSON_PX), PERSON_RGB)
            # The AI label is drawn where the fork draws it: white text inside its box.
            x1, y1, x2, y2 = estimate_label_box(480, 832, app_settings.ai_label_text, app_settings.ai_label_position)
            label = preview.crop((x1, y1, x2, y2))
            assert any(min(px) >= 240 for px in label.get_flattened_data()), "no white AI label text"


def all_routes(routes: Any) -> list[Any]:
    """Every route, inside included routers too (FastAPI keeps them behind a wrapper)."""
    found: list[Any] = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        found += all_routes(inner.routes) if inner is not None else [route]
    return found


def fork_plate(fork: FakeFork) -> bytes:
    import base64

    last = [m for m in fork.scene_backgrounds if m.get("png_b64")][-1]
    return base64.b64decode(last["png_b64"])


async def test_preview_is_404_with_the_reason_when_not_prepared(app_settings, tmp_path: Path) -> None:
    block = FakeFork.background_block("missing", reason="not_prepared")
    async with FakeFork(background=block) as fork:
        settings = lipsync_settings(app_settings, tmp_path, fork.url, variant="missing")
        async with running(settings) as client:
            body = await wait_status(client, lambda b: (b.get("style"), b.get("mask_status")) == ("ke_hang", "missing"))
            assert body["active"] is False and body["fallback_reason"] == "not_prepared"
            assert f"background-prepare {CHARACTER_ID}" in body["fallback_message"]
            r = await client.get("/api/scene/background/preview.png")
            assert r.status_code == 404
            assert r.json()["error"] == "not_prepared"
            assert "chưa có nền" in r.json()["message"]


def test_scene_disabled_is_a_status_never_a_500(app_settings) -> None:
    with TestClient(create_app(app_settings)) as client:
        body = client.get("/api/scene/background").json()
        assert set(body) == FIELDS
        assert (body["active"], body["fallback_reason"]) == (False, "scene_disabled")
        assert "SCENE_ENABLED" in body["fallback_message"]
        assert client.get("/api/scene").json()["background"]["fallback_reason"] == "scene_disabled"
        r = client.get("/api/scene/background/preview.png")
        assert r.status_code == 404 and r.json()["error"] == "scene_disabled"


def test_no_route_changes_the_background(app_settings) -> None:
    app = create_app(app_settings)
    paths = {(getattr(r, "path", ""), m) for r in all_routes(app.routes) for m in getattr(r, "methods", None) or ()}
    background = {(p, m) for p, m in paths if p.startswith("/api/scene/background")}
    assert background and all(m in {"GET", "HEAD"} for _, m in background), background
