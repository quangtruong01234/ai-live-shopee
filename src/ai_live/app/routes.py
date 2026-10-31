"""App HTTP routes (contracts/api.md §1–2)."""

from __future__ import annotations

import asyncio
import dataclasses
import html
import logging
import time
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from ai_live.app.context import AppContext, build_state
from ai_live.app.errors import ApiError
from ai_live.core.logging import log_event
from ai_live.core.protocols import RendererUnavailable
from ai_live.director.show_director import FAULT_MODES, FAULT_STEPS, DirectorBusy
from ai_live.products.models import ContentLoadError

logger = logging.getLogger("ai_live.app")

STATIC_DIR = Path(__file__).parent / "static"
LABEL_POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")
DEBUG_TEXT_MAX = 300
# Loader issue codes that are not about the content itself but about the upload (contracts/api.md §2).
_UPLOAD_STATUS = {"too_large": (413, "content_too_large"), "not_docx": (415, "unsupported_media_type")}

router = APIRouter()
debug_router = APIRouter()


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


class CommentIn(BaseModel):
    author: str
    text: str


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=DEBUG_TEXT_MAX)


class FaultIn(BaseModel):
    step: Literal[FAULT_STEPS]  # type: ignore[valid-type]
    mode: Literal[FAULT_MODES]  # type: ignore[valid-type]
    count: int = Field(default=1, ge=1, le=100)


# ---------- Pages ----------


@router.get("/", include_in_schema=False)
async def control_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "control.html")


@router.get("/host", include_in_schema=False)
async def host_page(request: Request) -> HTMLResponse:
    """Host page. The AI label comes from config.

    Deliberately reads no query string, so there is no way to hide the label through the URL (Article I).
    """
    settings = _ctx(request).settings
    position = settings.ai_label_position
    if position not in LABEL_POSITIONS:
        log_event(logger, "ai_label_position_invalid", logging.WARNING, value=position, used="top-right")
        position = "top-right"
    avatar_src = "/avatar-image" if settings.avatar_static_image.is_file() else "/static/avatar-placeholder.svg"
    page = (
        (STATIC_DIR / "host.html")
        .read_text(encoding="utf-8")
        .replace("{{AI_LABEL_TEXT}}", html.escape(settings.ai_label_text))
        .replace("{{AI_LABEL_POSITION}}", position)
        .replace("{{AVATAR_SRC}}", avatar_src)
    )
    return HTMLResponse(page)


@router.get("/static/host.html", include_in_schema=False)
async def raw_host_template() -> RedirectResponse:
    # The raw template still has placeholders and would show a wrong label; redirect to the filled page.
    return RedirectResponse("/host")


@router.get("/avatar-image", include_in_schema=False)
async def avatar_image(request: Request) -> FileResponse:
    path = _ctx(request).settings.avatar_static_image
    if not path.is_file():
        raise ApiError(404, "not_found", "Chưa có ảnh avatar; trang host dùng ảnh minh họa")
    return FileResponse(path)


# ---------- API ----------


@router.post("/api/comments", status_code=202)
async def post_comment(body: CommentIn, request: Request) -> dict:
    # 202 even for dropped comments, so the control page shows the reason right away (US2 #4).
    result = await _ctx(request).intake.submit(body.author, body.text)
    return result.to_json()


def _control_command(command: str) -> float:
    """Log the moment a control command arrives; `control_applied` measures its latency from here (SC-007)."""
    t_mono = time.monotonic()
    log_event(logger, "control_command", command=command, t_mono=t_mono)
    return t_mono


@router.post("/api/pause")
async def pause(request: Request) -> dict:
    return {"state": _ctx(request).director.pause(_control_command("pause"))}


@router.post("/api/resume")
async def resume(request: Request) -> dict:
    return {"state": _ctx(request).director.resume(_control_command("resume"))}


@router.post("/api/skip")
async def skip(request: Request) -> dict:
    return {"skipped_utterance_id": await _ctx(request).director.skip(_control_command("skip"))}


@router.put("/api/content")
async def put_content(request: Request) -> dict:
    """Replace the product content with an uploaded `.docx` (FR-022). The turn speaking now keeps its old catalog.

    Raw body instead of multipart, so no `python-multipart` (research R13). `X-Filename` is only the `source_name`
    shown in issues; it never becomes a path, and nothing is written to disk. Browsers cannot put non-Latin-1 text in a
    header, so the control page percent-encodes it.
    """
    ctx = _ctx(request)
    source_name = Path(unquote(request.headers.get("x-filename") or "")).name or "upload.docx"
    max_bytes = ctx.settings.content_max_bytes
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        # Refuse before reading the body into memory.
        raise ApiError(413, "content_too_large", f"File quá lớn (tối đa {max_bytes} byte)")
    data = await request.body()
    try:
        catalog = await asyncio.to_thread(ctx.store.parse, data, source_name)
    except ContentLoadError as exc:
        log_event(logger, "content_rejected", logging.WARNING, source=source_name, issue_count=len(exc.issues))
        details = [dataclasses.asdict(issue) for issue in exc.issues]
        if len(exc.issues) == 1 and exc.issues[0].code in _UPLOAD_STATUS:
            status, error = _UPLOAD_STATUS[exc.issues[0].code]
            raise ApiError(status, error, exc.issues[0].message, details) from exc
        raise ApiError(400, "content_invalid", f"File nội dung có {len(exc.issues)} lỗi, chưa nạp", details) from exc
    ctx.store.install(catalog)
    log_event(logger, "content_replaced", source=source_name, version=catalog.version)
    return {
        "version": catalog.version,
        "products": [{"id": p.id, "name": p.name, "is_primary": p.is_primary} for p in catalog.products],
    }


@router.get("/api/state")
async def get_state(request: Request) -> dict:
    return build_state(_ctx(request))


@router.get("/api/latency")
async def get_latency(request: Request, idle_only: bool = False) -> dict:
    """`LatencySummary` of the current session, from memory (data-model §4, US3 #2)."""
    return _ctx(request).director.latency.summary(idle_only=idle_only).to_json()


@router.get("/health")
async def health(request: Request) -> dict:
    ctx = _ctx(request)
    return {"status": "ok", "host_connected": ctx.renderer.host_ready, "catalog_version": ctx.store.catalog.version}


# ---------- Debug (registered only when APP_ENV=dev) ----------


@debug_router.post("/api/debug/speak")
async def debug_speak(body: SpeakIn, request: Request) -> dict:
    """Run TTS + renderer alone (Article IV). Returns after the host page finishes playing."""
    ctx = _ctx(request)
    try:
        utterance_id = await ctx.director.speak_text(body.text)
    except DirectorBusy as exc:
        raise ApiError(409, "busy", "Đang có lượt nói, thử lại sau khi host nói xong") from exc
    except RendererUnavailable as exc:
        raise ApiError(503, "host_unavailable", str(exc)) from exc
    except TimeoutError as exc:
        raise ApiError(503, "host_unavailable", "Màn hình host không phản hồi (hết giờ chờ ack)") from exc
    return {"utterance_id": utterance_id}


@debug_router.post("/api/debug/fault")
async def debug_fault(body: FaultIn, request: Request) -> dict:
    """Make the next `count` turns fail at `step` (quickstart US4, SC-005)."""
    _ctx(request).director.inject_fault(body.step, body.mode, body.count)
    return {"step": body.step, "mode": body.mode, "count": body.count}
