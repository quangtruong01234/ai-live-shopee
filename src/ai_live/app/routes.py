"""App HTTP routes (001 contracts/api.md §1–2; 004 contracts/api.md §2–4; 008 contracts/api.md §1)."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import html
import io
import logging
import time
import wave
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_live.app.context import AppContext, build_state
from ai_live.app.errors import (
    HOST_UNAVAILABLE_MESSAGE,
    NO_CONTENT_MESSAGE,
    SHOW_NOT_RUNNING_MESSAGE,
    TOPIC_UNAVAILABLE_MESSAGE,
    ApiError,
)
from ai_live.core.events import lipsync_health_event
from ai_live.core.logging import log_event
from ai_live.core.models import AvatarModeState, ContentSource, LipsyncHealth, Topic
from ai_live.core.protocols import RendererError, RendererUnavailable, RenderStatsSource
from ai_live.director.show_director import (
    ENTRY_FAULT_MODES,
    FAULT_MODES,
    FAULT_STEPS,
    DirectorBusy,
    HostUnavailable,
    NoContent,
    ShowDirector,
    ShowNotRunning,
    TopicUnavailable,
)
from ai_live.ops.readiness import run_readiness
from ai_live.products.models import ContentLoadError, ProductCatalog
from ai_live.scene.controller import DISABLED_HOST_CONFIG, disabled_status

logger = logging.getLogger("ai_live.app")

STATIC_DIR = Path(__file__).parent / "static"
LABEL_POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")
DEBUG_TEXT_MAX = 300
# How long `/host` waits for the first scene draw (009 contracts/api.md §4).
HOST_SCENE_WAIT_S = 2.0
# 005 speak-audio (contracts/api.md §1): about 160 s of 16 kHz PCM16 mono.
SPEAK_AUDIO_MAX_BYTES = 5 * 1024 * 1024
SPEAK_AUDIO_RATE = 16000
BAD_AUDIO_MESSAGE = "File phải là WAV PCM 16-bit, mono, 16 kHz. Đổi bằng lệnh trong quickstart bước 6."
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


class ShowStartIn(BaseModel):
    """`POST /api/show/start`, optional body (007 contracts/api.md §2): `verbatim` is the backup video's content."""

    model_config = ConfigDict(extra="forbid")

    content: ContentSource = "script"


class NextIn(BaseModel):
    """`POST /api/show/next`: at least one of the two fields (contracts/api.md §2)."""

    product_id: str | None = None
    topic: Topic | None = None

    @model_validator(mode="after")
    def _one_field_set(self) -> NextIn:
        if self.product_id is None and self.topic is None:
            raise ValueError("cần product_id hoặc topic")
        return self


# Step-wide modes first, then the 008 entry-only ones; `timeout` belongs to both and is listed once.
ALL_FAULT_MODES = tuple(dict.fromkeys((*FAULT_MODES, *ENTRY_FAULT_MODES)))


class FaultIn(BaseModel):
    """`POST /api/debug/fault`: a step-wide fault (004) or, with `entry`, a fault of one chain entry (008 FR-016)."""

    step: Literal[FAULT_STEPS]  # type: ignore[valid-type]
    mode: Literal[ALL_FAULT_MODES]  # type: ignore[valid-type]
    count: int = Field(default=1, ge=1, le=100)
    entry: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _mode_fits_the_form(self) -> FaultIn:
        if self.entry is None and self.mode not in FAULT_MODES:
            raise ValueError(f"mode {self.mode} cần chọn mục model (entry)")
        if self.entry is not None and (self.step != "llm" or self.mode not in ENTRY_FAULT_MODES):
            raise ValueError("lỗi theo mục model chỉ dùng với step llm và mode theo mục")
        return self


# ---------- Pages ----------


@router.get("/", include_in_schema=False)
async def control_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "control.html")


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Browsers ask for it on their own; an empty answer keeps a false 404 out of the log and console."""
    return Response(status_code=204)


@router.get("/host", include_in_schema=False)
async def host_page(request: Request) -> HTMLResponse:
    """Host page. The AI label comes from config.

    Deliberately reads no query string, so there is no way to hide the label through the URL (Article I).
    """
    return await _render_host_page(request, body_class="host")


@router.get("/obs", include_in_schema=False)
async def obs_page(request: Request) -> HTMLResponse:
    """The same host page for an OBS Browser Source: starts on load, no overlay or status text (006 contracts §1).

    Like `/host` it reads no query string (Article I).
    """
    return await _render_host_page(request, body_class="host obs")


async def _render_host_page(request: Request, *, body_class: str) -> HTMLResponse:
    settings = _ctx(request).settings
    position = settings.ai_label_position
    if position not in LABEL_POSITIONS:
        log_event(logger, "ai_label_position_invalid", logging.WARNING, value=position, used="top-right")
        position = "top-right"
    avatar_src = "/avatar-image" if _avatar_image(_ctx(request)).is_file() else "/static/avatar-placeholder.svg"
    scene = _ctx(request).scene
    if scene is not None:
        # The first draw runs right after startup; a page opened that early waits briefly rather than flash the face.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(scene.wait_idle(), HOST_SCENE_WAIT_S)
        if scene.still_png is not None:
            avatar_src = f"/api/scene/still.png?v={scene.version}"
    page = (
        (STATIC_DIR / "host.html")
        .read_text(encoding="utf-8")
        .replace("{{AI_LABEL_TEXT}}", html.escape(settings.ai_label_text))
        .replace("{{AI_LABEL_POSITION}}", position)
        .replace("{{AVATAR_SRC}}", avatar_src)
        .replace('<body class="host">', f'<body class="{body_class}">', 1)
    )
    # A new URL per file version: OBS's browser kept an old host.js from before `/static` sent `no-cache` (T029).
    for name in ("host.js", "style.css"):
        version = int((STATIC_DIR / name).stat().st_mtime)
        page = page.replace(f'"/static/{name}"', f'"/static/{name}?v={version}"')
    # no-store keeps the page out of the back/forward cache: a cached host page holds its socket open until it is
    # restored, so leaving it for another URL only raised `host_closed` after the ping timeout (007 T035).
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@router.get("/static/host.html", include_in_schema=False)
async def raw_host_template() -> RedirectResponse:
    # The raw template still has placeholders and would show a wrong label; redirect to the filled page.
    return RedirectResponse("/host")


def _avatar_image(ctx: AppContext) -> Path:
    # 005: the character's own face in `livetalking`, also the picture shown after a fallback (FR-022).
    return ctx.avatar_image if ctx.avatar_image is not None else ctx.settings.avatar_static_image


@router.get("/api/scene/still.png", include_in_schema=False)
async def scene_still(request: Request) -> Response:
    """The still picture with the scene on it (009 contracts/api.md §2); `?v=` only defeats the browser cache."""
    scene = _ctx(request).scene
    png = scene.still_png if scene is not None else None
    if png is None:
        raise ApiError(404, "not_found", "Chưa bật cảnh live hoặc cảnh chưa vẽ xong")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/avatar-image", include_in_schema=False)
async def avatar_image(request: Request) -> FileResponse:
    path = _avatar_image(_ctx(request))
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


def _with_show_state(director: ShowDirector, body: dict) -> dict:
    """`show_state` is in the body only while a show is on (contracts/api.md §3)."""
    if director.show_active:
        body["show_state"] = director.show_state
    return body


@router.post("/api/pause")
async def pause(request: Request) -> dict:
    director = _ctx(request).director
    return _with_show_state(director, {"state": director.pause(_control_command("pause"))})


@router.post("/api/resume")
async def resume(request: Request) -> dict:
    director = _ctx(request).director
    return _with_show_state(director, {"state": director.resume(_control_command("resume"))})


@router.post("/api/skip")
async def skip(request: Request) -> dict:
    """Skip the comment answer speaking now, else the rest of the scripted segment (FR-016)."""
    utterance_id, segment_id = await _ctx(request).director.skip_current(_control_command("skip"))
    body: dict = {"skipped_utterance_id": utterance_id}
    if segment_id is not None:
        body["skipped_segment_id"] = segment_id
    return body


@router.post("/api/show/end")
async def show_end(request: Request) -> dict:
    """Say the closing and end the show (FR-017); idempotent when there is no show or it already ended."""
    show_id, state = _ctx(request).director.end_show(_control_command("show_end"))
    return {"show_id": show_id, "state": state}


@router.post("/api/show/start")
async def show_start(request: Request, body: ShowStartIn | None = None) -> dict:
    """Start the scripted show; a second press returns the running show (`already_running`), source unchanged."""
    director = _ctx(request).director
    content = body.content if body is not None else "script"
    try:
        show, already_running = await director.start_show(_control_command("show_start"), content=content)
    except HostUnavailable as exc:
        raise ApiError(409, "host_unavailable", HOST_UNAVAILABLE_MESSAGE) from exc
    except NoContent as exc:
        raise ApiError(409, "no_content", NO_CONTENT_MESSAGE) from exc
    return {
        "show_id": show.show_id,
        "state": show.state.value,
        "already_running": already_running,
        "content": show.content_source,
    }


@router.post("/api/show/next")
async def show_next(body: NextIn, request: Request) -> dict:
    """Choose the next segment (FR-018): the prepared one is discarded, the one speaking finishes first."""
    t_mono = _control_command("show_next")
    try:
        slot = _ctx(request).director.choose_next(body.product_id, body.topic, t_mono)
    except ShowNotRunning as exc:
        raise ApiError(409, "show_not_running", SHOW_NOT_RUNNING_MESSAGE) from exc
    except TopicUnavailable as exc:
        raise ApiError(422, "topic_unavailable", TOPIC_UNAVAILABLE_MESSAGE) from exc
    return {"product_id": slot.product_id, "topic": slot.topic.value, "origin": slot.origin.value}


@router.get("/api/show")
async def get_show(request: Request) -> dict | None:
    """`ShowSnapshot` (contracts/api.md §4); null before the first start, like `state.show`."""
    return _ctx(request).director.show_snapshot()


@router.put("/api/content")
async def put_content(request: Request) -> dict:
    """Replace the product content with an uploaded `.docx` (FR-022). The turn speaking now keeps its old catalog.

    Raw body instead of multipart, so no `python-multipart` (research R13). `X-Filename` is only the `source_name`
    shown in issues; it never becomes a path, and nothing is written to disk. Browsers cannot put non-Latin-1 text in a
    header, so the control page percent-encodes it.
    """
    ctx = _ctx(request)
    catalog = await parse_content_upload(ctx, request)
    ctx.store.install(catalog)
    # A running show follows at once: the segment speaking finishes, the prepared one is redone (contracts/api.md §3).
    ctx.director.on_catalog_replaced(catalog)
    log_event(logger, "content_replaced", source=catalog.source_name, version=catalog.version)
    return catalog_reply(catalog)


async def parse_content_upload(ctx: AppContext, request: Request) -> ProductCatalog:
    """Read and validate an uploaded `.docx` without installing it; shared with "Chuẩn bị bộ mới" (012 US2)."""
    source_name = Path(unquote(request.headers.get("x-filename") or "")).name or "upload.docx"
    max_bytes = ctx.settings.content_max_bytes
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        # Refuse before reading the body into memory.
        raise ApiError(413, "content_too_large", f"File quá lớn (tối đa {max_bytes} byte)")
    data = await request.body()
    try:
        return await asyncio.to_thread(ctx.store.parse, data, source_name)
    except ContentLoadError as exc:
        log_event(logger, "content_rejected", logging.WARNING, source=source_name, issue_count=len(exc.issues))
        details = [dataclasses.asdict(issue) for issue in exc.issues]
        if len(exc.issues) == 1 and exc.issues[0].code in _UPLOAD_STATUS:
            status, error = _UPLOAD_STATUS[exc.issues[0].code]
            raise ApiError(status, error, exc.issues[0].message, details) from exc
        raise ApiError(400, "content_invalid", f"File nội dung có {len(exc.issues)} lỗi, chưa nạp", details) from exc


def catalog_reply(catalog: ProductCatalog) -> dict[str, Any]:
    """`{version, products}` of `PUT /api/content`; "Áp dụng bộ mới" answers the same so the page reuses its update."""
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


@router.get("/api/host-config")
async def host_config(request: Request) -> dict:
    """What the host page needs at load: which picture to show, where the fork's WebRTC is (005 contracts/api.md §3)."""
    ctx = _ctx(request)
    settings = ctx.settings
    mode = getattr(ctx.renderer, "mode", None)
    return {
        "mode": settings.avatar_mode,
        "active": mode.active if mode is not None else settings.avatar_mode,
        "livetalking_url": settings.livetalking_url,
        "ai_label": {"text": settings.ai_label_text, "position": settings.ai_label_position},
        "scene": ctx.scene.host_config() if ctx.scene is not None else DISABLED_HOST_CONFIG,
        "output_mode": settings.output_mode,
    }


@router.get("/api/scene")
async def get_scene(request: Request) -> dict:
    """Scene state for the control page and the operator (009 contracts/api.md §1)."""
    scene = _ctx(request).scene
    return scene.status() if scene is not None else disabled_status()


def _avatar_mode(ctx: AppContext) -> AvatarModeState:
    """`SwitchingRenderer`'s state; a `static` session has no switch, so it is always the configured still image."""
    mode = getattr(ctx.renderer, "mode", None)
    return mode if isinstance(mode, AvatarModeState) else AvatarModeState(configured="static", active="static")


def _lipsync_health(ctx: AppContext) -> LipsyncHealth | None:
    health = getattr(getattr(ctx.renderer, "lipsync", None), "health", None)
    return health if isinstance(health, LipsyncHealth) else None


@router.get("/api/avatar")
async def get_avatar(request: Request) -> dict:
    """Which picture the viewers see, the character and the fork's last health (005 contracts/api.md §1)."""
    ctx = _ctx(request)
    character = ctx.character
    health = _lipsync_health(ctx)
    return {
        "mode": _avatar_mode(ctx).to_json(),
        "character": None
        if character is None
        else {
            "character_id": character.character_id,
            "customer_id": character.customer_id,
            "clips": {kind: len(character.clips_of(kind)) for kind in ("idle", "talk")},
        },
        # Same payload as the `lipsync_health` event, so the fork's error text is redacted here too.
        "lipsync": lipsync_health_event(health).payload if health is not None else None,
    }


@router.post("/api/avatar/lipsync")
async def enable_lipsync(request: Request) -> dict:
    """Operator switch back to the lip-synced character after a fallback; applies from the next turn (FR-022)."""
    ctx = _ctx(request)
    enable = getattr(ctx.renderer, "enable_lipsync", None)
    try:
        if enable is None:
            raise ValueError("avatar mode is configured as static")
        state = await enable()
    except ValueError as exc:
        raise ApiError(
            409,
            "not_lipsync_mode",
            "Phiên đang chạy chế độ ảnh tĩnh theo cấu hình, không có nhân vật nhép miệng để bật lại.",
        ) from exc
    return state.to_json()


@router.get("/api/readiness")
async def get_readiness(request: Request) -> dict:
    """Pre-demo check (007 contracts/api.md §1): reads state only, never calls the LLM or plays anything (FR-004)."""
    ctx = _ctx(request)
    result = await run_readiness(ctx)
    ctx.session_log.write_readiness(result.to_json())
    return result.to_json()


@router.get("/health")
async def health(request: Request) -> dict:
    ctx = _ctx(request)
    mode = _avatar_mode(ctx)
    lipsync = _lipsync_health(ctx)
    body: dict = {
        "status": "ok",
        "host_connected": ctx.renderer.host_ready,
        "catalog_version": ctx.store.catalog.version,
        "reply_engine": ctx.settings.reply_engine,
        # 007: lets the readiness CLI and an outside monitor see whose character is live and whether a show runs.
        "customer_id": ctx.settings.customer_id,
        "avatar_id": ctx.settings.avatar_id,
        "show_active": ctx.director.show_active,
        "avatar": {
            "configured": mode.configured,
            "active": mode.active,
            "lipsync_connected": lipsync is not None and lipsync.connected,
        },
    }
    if ctx.chain is not None:
        # Still 200 with no entry ready: the show runs on the product text (008 edge case), so a monitor must not
        # restart the app. A rest past its `retry_at` already reads as ready in the snapshot.
        body["llm_ready"] = any(entry["status"] == "ready" for entry in ctx.chain.snapshot()["entries"])
    return body


# ---------- Debug (registered only when APP_ENV=dev) ----------


@debug_router.post("/api/debug/speak")
async def debug_speak(body: SpeakIn, request: Request) -> dict:
    """Run TTS + renderer alone (Article IV). Returns after the host page finishes playing."""
    ctx = _ctx(request)
    try:
        utterance_id = await ctx.director.speak_text(body.text)
    except DirectorBusy as exc:
        # Also while a show runs: the debug line would cut into the script (004 contracts/api.md §2).
        raise ApiError(409, "busy", "Đang có lượt nói, thử lại sau khi host nói xong") from exc
    except RendererUnavailable as exc:
        raise ApiError(503, "host_unavailable", str(exc)) from exc
    except TimeoutError as exc:
        raise ApiError(503, "host_unavailable", "Màn hình host không phản hồi (hết giờ chờ ack)") from exc
    return {"utterance_id": utterance_id}


def _read_wav(data: bytes) -> tuple[bytes, float]:
    """PCM frames and duration of a 16 kHz PCM16 mono WAV; anything else is `422 bad_audio` with what was read."""
    if len(data) > SPEAK_AUDIO_MAX_BYTES:
        raise ApiError(422, "bad_audio", f"{BAD_AUDIO_MESSAGE} File tối đa 5 MB.", {"size_bytes": len(data)})
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            fmt = {
                "sample_rate": w.getframerate(),
                "channels": w.getnchannels(),
                "sample_width_bits": w.getsampwidth() * 8,
            }
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError, RuntimeError, ValueError) as exc:  # a broken RIFF header can raise any of these
        raise ApiError(422, "bad_audio", BAD_AUDIO_MESSAGE, {"reason": "not_wav"}) from exc
    if fmt != {"sample_rate": SPEAK_AUDIO_RATE, "channels": 1, "sample_width_bits": 16} or not frames:
        raise ApiError(422, "bad_audio", BAD_AUDIO_MESSAGE, fmt)
    return frames, len(frames) / 2 / SPEAK_AUDIO_RATE


@debug_router.post("/api/debug/speak-audio")
async def debug_speak_audio(request: Request) -> dict:
    """Play a ready-made WAV through the active renderer (005 FR-011): judge lip-sync without the LLM or TTS.

    Raw WAV body plus an `X-Filename` header (the subtitle), not multipart: no extra dependency for one debug form.
    Nothing is written to disk and the audio is never logged.
    """
    ctx = _ctx(request)
    pcm, duration_s = _read_wav(await request.body())
    name = unquote(request.headers.get("x-filename", "")).strip()[:DEBUG_TEXT_MAX] or "speak-audio.wav"
    started = time.monotonic()
    try:
        utterance_id = await ctx.director.speak_audio(pcm, SPEAK_AUDIO_RATE, name)
    except DirectorBusy as exc:
        raise ApiError(409, "busy", "Đang có lượt nói, tạm dừng show rồi thử lại.") from exc
    except RendererError as exc:
        raise ApiError(503, exc.kind, str(exc)) from exc
    except RendererUnavailable as exc:
        raise ApiError(503, "host_unavailable", str(exc)) from exc
    except TimeoutError as exc:
        raise ApiError(503, "host_unavailable", "Màn hình host không phản hồi (hết giờ chờ ack)") from exc
    first = ctx.renderer.first_playback_at(utterance_id)
    stats = ctx.renderer.render_stats(utterance_id) if isinstance(ctx.renderer, RenderStatsSource) else None
    return {
        "utterance_id": utterance_id,
        "duration_s": round(duration_s, 3),
        "first_frame_s": round(first - started, 3) if first is not None else None,
        "render_fps": round(stats.render_fps, 1) if stats is not None and stats.render_fps is not None else None,
    }


@debug_router.post("/api/debug/fault")
async def debug_fault(body: FaultIn, request: Request) -> dict:
    """Make the next `count` turns fail at `step` (quickstart US4, SC-005), or the next `count` tries of one entry."""
    ctx = _ctx(request)
    if body.entry is None:
        ctx.director.inject_fault(body.step, body.mode, body.count)
        return {"step": body.step, "mode": body.mode, "count": body.count}
    if ctx.settings.reply_engine != "chain":
        raise ApiError(422, "chain_not_active", "Lỗi theo mục model chỉ dùng được khi REPLY_ENGINE=chain")
    labels = [entry.label for entry in ctx.settings.llm_chain]
    if body.entry not in labels:
        raise ApiError(422, "unknown_entry", f"Không có mục '{body.entry}' trong LLM_CHAIN (có: {', '.join(labels)})")
    ctx.director.inject_fault(body.step, body.mode, body.count, entry=body.entry)
    return {
        "step": body.step,
        "mode": body.mode,
        "count": body.count,
        "entry": body.entry,
        "pending": ctx.director.faults.pending_entry(body.entry),
    }
