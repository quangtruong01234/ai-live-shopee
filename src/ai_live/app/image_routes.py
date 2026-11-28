"""Product image routes of the control page (specs/012-product-image-upload/contracts/api.md §1, §6, §7).

Kept apart from `routes.py` so the image and staging flows of 012 read as one unit. Uploads are raw bodies with a
percent-encoded `X-Filename`, like `PUT /api/content` (research R3): no multipart dependency. The filename is shown on
the page only; it never becomes a path and never goes to a log line.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel

from ai_live.app.context import AppContext
from ai_live.app.errors import ApiError
from ai_live.app.routes import catalog_reply, parse_content_upload
from ai_live.app.staging import StagedSet
from ai_live.core.events import Event, EventType
from ai_live.core.logging import log_event
from ai_live.products.models import Product, product_detail
from ai_live.scene.layout import ArtFit
from ai_live.scene.loader import kit_art_path, load_kit_art, load_scene_set, load_version_art, scene_customer
from ai_live.scene.matting import CutResult, remove_background
from ai_live.scene.models import MAX_IMAGE_BYTES, ProductArt, SceneSet
from ai_live.scene.render import encode_png
from ai_live.scene.uploads import (
    KIT,
    ImageState,
    ImageStoreError,
    NormalizedImage,
    ProductImageStore,
    check_product_id,
    check_version_id,
    needs_bg_removal,
    now_iso,
    validate_and_normalize,
)

# Same logger as the 009 scene events (contracts/api.md §7).
logger = logging.getLogger("ai_live.scene")

router = APIRouter()

CUSTOMER_MISMATCH_MESSAGE = "Bộ cảnh không thuộc khách của phiên này"
IMMUTABLE = "max-age=31536000, immutable"
HAS_BACKGROUND_MESSAGE = (
    "Ảnh này không có nền trong suốt (ảnh còn nền): trên bàn sẽ hiện nguyên khung chữ nhật. Nên tách nền trước nếu kịp."
)
# Shown when removal itself broke (a bug, a full disk): the upload is kept and nothing is recorded, so the next upload
# of the same picture tries again.
BG_ERROR_REASON = "bỏ nền bị lỗi, thử tải lại ảnh"
BG_RECORD_KEYS = ("method", "result", "reason", "ms", "model")
LOW_RESOLUTION_ADVICE = "Ảnh vẫn áp được."
_TOO_WIDE_ADVICE = "Nên dùng ảnh gần vuông hoặc dọc hơn; ảnh vẫn áp được."
TOO_WIDE_MESSAGES: dict[ArtFit, str] = {
    "highlight_only": "Ảnh quá rộng so với ô của món trên bàn: chỉ hiện lúc AI đang nói về món này, "
    "lúc khác chỉ còn thẻ. " + _TOO_WIDE_ADVICE,
    "card_only": "Ảnh quá rộng so với ô của món trên bàn: trên live chỉ hiện thẻ, "
    "kể cả lúc AI nói về món này. " + _TOO_WIDE_ADVICE,
}


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def _images(ctx: AppContext) -> ProductImageStore:
    assert ctx.images is not None, "ProductImageStore is built at startup"
    return ctx.images


def _api_error(exc: ImageStoreError) -> ApiError:
    return ApiError(exc.status, exc.code, exc.message)


def _checked(check: Any, value: str) -> str:
    try:
        return check(value)
    except ImageStoreError as exc:
        raise _api_error(exc) from exc


def _live_product(ctx: AppContext, product_id: str, *, or_staged: bool = False) -> Product:
    """A product of the live catalog (or, with `or_staged`, of the staged set); 404 `unknown_product` otherwise."""
    _checked(check_product_id, product_id)
    products = list(ctx.store.catalog.products)
    if or_staged and ctx.staging is not None:
        products += ctx.staging.catalog.products
    product = next((p for p in products if p.id == product_id), None)
    if product is None:
        raise ApiError(404, "unknown_product", f"Không có sản phẩm {product_id} trong file đang nạp hay bộ chuẩn bị")
    return product


async def _check_scene_owner(ctx: AppContext) -> None:
    """Never write images into another customer's scene set (FR-007, constitution Article I).

    The store already refuses a manifest of another customer; this covers a `scene.json` that names one.
    """
    owner = await asyncio.to_thread(scene_customer, ctx.settings.scene_dir)
    session = ctx.settings.customer_id
    if owner and session and owner != session:
        raise ApiError(409, "customer_mismatch", CUSTOMER_MISMATCH_MESSAGE)


def _art_fit(ctx: AppContext, product_id: str, size: tuple[int, int], target: str) -> ArtFit | None:
    """How the picture would fare in the set it is meant for (FR-004a); the other set when the pid is not in it."""
    if ctx.scene is None:
        return None
    live = list(ctx.store.catalog.products)
    staged = list(ctx.staging.catalog.products) if ctx.staging is not None else []
    first, second = (staged, live) if target == "staging" else (live, staged)
    products = first if any(p.id == product_id for p in first) else second
    return ctx.scene.art_fit(products, product_id, size)


def _low_resolution(ctx: AppContext, product_id: str, size: tuple[int, int], target: str) -> str | None:
    """The FR-028 warning for the picture in the set it is meant for, chosen as `_art_fit` chooses it (013)."""
    if ctx.scene is None:
        return None
    live = list(ctx.store.catalog.products)
    staged = list(ctx.staging.catalog.products) if ctx.staging is not None else []
    first, second = (staged, live) if target == "staging" else (live, staged)
    products = first if any(p.id == product_id for p in first) else second
    return ctx.scene.low_resolution(products, product_id, size)


def _thumb_url(product_id: str, state: str, version_id: str | None) -> str | None:
    if state == "upload":
        return f"/api/scene/images/{product_id}/versions/{version_id}.png"
    if state == "kit":
        return f"/api/scene/images/{product_id}/kit.png"
    return None


def _product_status(
    product: Product, entry: dict[str, Any] | None, has_kit: bool, issues: list[dict[str, Any]]
) -> dict[str, Any]:
    """One `ProductImageStatus` (data-model §4)."""
    active: ImageState = KIT if entry is None else entry.get("active", KIT)
    versions: dict[str, Any] = (entry or {}).get("versions") or {}
    version_id: str | None = None
    if active == KIT:
        state = "kit" if has_kit else "none"
    elif active is None:
        state = "removed"
    else:
        state, version_id = "upload", active
    current = versions.get(version_id) if version_id else None
    current = current if isinstance(current, dict) else {}
    newest_first = sorted(
        ((vid, v) for vid, v in versions.items() if isinstance(v, dict)),
        key=lambda item: item[1].get("uploaded_at") or "",
        reverse=True,
    )
    return {
        "product_id": product.id,
        "name": product.name,
        "is_primary": product.is_primary,
        "state": state,
        "version_id": version_id,
        "thumb_url": _thumb_url(product.id, state, version_id),
        "uploaded_at": current.get("uploaded_at"),
        "applied_at": current.get("applied_at"),
        "rights_confirmed_at": current.get("rights_confirmed_at"),
        "has_alpha": current.get("has_alpha"),
        "can_revert": bool((entry or {}).get("history")),
        "issues": issues,
        "versions": [
            {
                "version_id": vid,
                "uploaded_at": v.get("uploaded_at"),
                "source_name": v.get("source_name"),
                "applied_at": v.get("applied_at"),
                "bg_removal": v.get("bg_removal"),
                "cutout_version": v.get("cutout_version"),
                "derived_from": v.get("derived_from"),
            }
            for vid, v in newest_first
        ],
    }


@router.get("/api/scene/images")
async def get_scene_images(request: Request) -> dict[str, Any]:
    """Image state of every product in the live catalog (contracts/api.md §1); works with the scene off."""
    ctx = _ctx(request)
    store = _images(ctx)
    catalog = ctx.store.catalog
    root = ctx.settings.scene_dir
    scene = ctx.scene.scene if ctx.scene is not None else None
    entries = store.entries()
    ids = [p.id for p in catalog.products]
    kits = await asyncio.to_thread(lambda: {pid: kit_art_path(root, pid) is not None for pid in ids})
    issues: dict[str, list[dict[str, Any]]] = {}
    layout_issues = ctx.scene.layout_issues(catalog) if ctx.scene is not None else []
    for issue in [*(scene.issues if scene is not None else ()), *layout_issues]:
        if issue.product_id is not None:
            issues.setdefault(issue.product_id, []).append(issue.to_json())
    uploads_bytes = sum(
        int(v.get("bytes") or 0)
        for entry in entries.values()
        for v in (entry.get("versions") or {}).values()
        if isinstance(v, dict)
    )
    return {
        "scene_enabled": ctx.settings.scene_enabled,
        "scene_usable": scene is not None and not scene.blocked,
        "catalog_version": catalog.version,
        "products": [_product_status(p, entries.get(p.id), kits[p.id], issues.get(p.id, [])) for p in catalog.products],
        "uploads_bytes": uploads_bytes,
    }


@router.post("/api/scene/uploads", status_code=201)
async def upload_scene_image(
    request: Request, product_id: str, target: Literal["live", "staging"] = "live"
) -> dict[str, Any]:
    """Store one uploaded image as a new version without showing it (contracts/api.md §1, FR-002–FR-004a)."""
    started = time.perf_counter()
    ctx = _ctx(request)
    try:
        _live_product(ctx, product_id, or_staged=True)
        await _check_scene_owner(ctx)
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
            # Refuse before reading the body into memory.
            raise ApiError(413, "too_large", "Ảnh quá lớn (tối đa 10 MB)")
        source_name = Path(unquote(request.headers.get("x-filename") or "")).name or "upload"
        data = await request.body()
        try:
            image = await asyncio.to_thread(validate_and_normalize, data)
            version, reused = await _images(ctx).save_version(product_id, image, source_name)
        except ImageStoreError as exc:
            raise _api_error(exc) from exc
    except ApiError as exc:
        log_event(logger, "scene_image_rejected", logging.WARNING, code=exc.error)
        raise
    version = _images(ctx).version(product_id, image.version_id) or version
    if needs_bg_removal(version):
        version = await _remove_background(ctx, product_id, image, version)
    log_event(
        logger,
        "scene_image_uploaded",
        product_id=product_id,
        version_id=image.version_id,
        reused=reused,
        has_alpha=version["has_alpha"],
        width=version["width"],
        height=version["height"],
        bytes=version["bytes"],
        ms=round((time.perf_counter() - started) * 1000, 1),
    )
    record = version.get("bg_removal")
    cutout_id = version.get("cutout_version")
    cutout = _images(ctx).version(product_id, cutout_id) if cutout_id else None
    recommended = cutout if cutout is not None else version
    warnings: dict[str, str] = {}
    # 013: only a failed removal leaves the operator without a see-through version (contracts/api.md §1).
    failed = record["result"] == "failed" if isinstance(record, dict) else not version["has_alpha"]
    if failed:
        warnings["has_background"] = HAS_BACKGROUND_MESSAGE
    size = (int(recommended["width"]), int(recommended["height"]))
    fit = _art_fit(ctx, product_id, size, target)
    if fit is not None and fit != "shown":
        warnings["too_wide"] = TOO_WIDE_MESSAGES[fit]
    # 013 FR-028: a small picture still applies; it just looks soft once the frame is scaled up.
    low = _low_resolution(ctx, product_id, size, target)
    if low is not None:
        warnings["low_resolution"] = f"{low}. {LOW_RESOLUTION_ADVICE}"
    return {
        "product_id": product_id,
        "version_id": image.version_id,
        "reused": reused,
        "width": version["width"],
        "height": version["height"],
        "has_alpha": version["has_alpha"],
        "bg_removal": {key: record.get(key) for key in BG_RECORD_KEYS} if isinstance(record, dict) else None,
        "cutout": None
        if cutout is None
        else {
            "version_id": cutout_id,
            "width": cutout["width"],
            "height": cutout["height"],
            "thumb_url": _thumb_url(product_id, "upload", cutout_id),
        },
        "recommended_version": cutout_id if cutout is not None else image.version_id,
        "warnings": list(warnings),
        "warning_messages": warnings,
        "thumb_url": _thumb_url(product_id, "upload", image.version_id),
    }


def _open_rgba(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as source:
        return source.convert("RGBA")


async def _remove_background(
    ctx: AppContext, product_id: str, image: NormalizedImage, version: dict[str, Any]
) -> dict[str, Any]:
    """Run 013 background removal on a saved upload and record it; never fails the upload (contracts/api.md §1).

    The request waits for it (research R9): the operator chooses between the two pictures right after.
    """
    try:
        picture = await asyncio.to_thread(_open_rgba, image.png)
        cut = await remove_background(
            picture,
            has_alpha=image.has_alpha,
            show_running=ctx.director.show_active,
            settings=ctx.settings,
        )
        return await _images(ctx).record_bg_removal(product_id, image.version_id, cut)
    except Exception as exc:  # noqa: BLE001 - any failure here must still leave a usable upload
        log_event(
            logger,
            "scene_bg_removal_error",
            logging.WARNING,
            product_id=product_id,
            version_id=image.version_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        failed = CutResult(None, "flat", "failed", BG_ERROR_REASON)
        return {**version, "bg_removal": {key: getattr(failed, key) for key in BG_RECORD_KEYS}, "cutout_version": None}


@router.get("/api/scene/images/{product_id}/versions/{version_id}.png", include_in_schema=False)
async def scene_image_version(request: Request, product_id: str, version_id: str) -> FileResponse:
    """The PNG of one uploaded version; fixed by its id, so browsers may keep it forever."""
    _checked(check_product_id, product_id)
    _checked(check_version_id, version_id)
    path = _images(_ctx(request)).path(product_id, version_id)
    if not await asyncio.to_thread(path.is_file):
        raise ApiError(404, "not_found", f"Không có phiên bản ảnh {version_id} của sản phẩm {product_id}")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": IMMUTABLE})


@router.get("/api/scene/images/{product_id}/kit.png", include_in_schema=False)
async def scene_image_kit(request: Request, product_id: str) -> Response:
    """The 009 kit art of a product as the scene draws it (cropped, ≤ 640 px), for the thumbnail."""
    _checked(check_product_id, product_id)
    root = _ctx(request).settings.scene_dir

    def _png() -> bytes | None:
        art = load_kit_art(root, product_id)
        return encode_png(art.image) if art is not None else None

    png = await asyncio.to_thread(_png)
    if png is None:
        raise ApiError(404, "not_found", f"Sản phẩm {product_id} không có ảnh trong bộ cảnh")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-cache"})


@router.get("/api/scene/preview.png", include_in_schema=False)
async def scene_preview(
    request: Request,
    target: Literal["live", "staging"] = "live",
    product_id: str | None = None,
    version_id: str | None = None,
    debug: bool = False,
) -> Response:
    """A still of the frame with one product's candidate image; the live scene is not touched (research R4).

    `debug=1` (013) draws the keep-out zones, the desk edge and the hands zone, to measure a new character.
    """
    ctx = _ctx(request)
    staged = _staging(ctx) if target == "staging" else None
    controller = ctx.scene
    if controller is None or not controller.enabled:
        raise ApiError(409, "scene_disabled", "Cảnh live đang tắt (SCENE_ENABLED)")
    scene = controller.scene
    if scene is None or scene.blocked:
        raise ApiError(409, "scene_unusable", "Bộ cảnh chưa dùng được, xem mục Cảnh live")
    if staged is not None:
        if product_id is not None:
            staged.product(product_id)
        if version_id is not None:
            raise ApiError(400, "bad_id", "Xem trước bộ chuẩn bị không nhận version_id, gán ảnh trước")
        return await _staging_preview(ctx, staged, debug=debug)
    overrides = {}
    if product_id is not None:
        _live_product(ctx, product_id)
    if version_id is not None:
        if product_id is None:
            raise ApiError(400, "bad_id", "Cần product_id đi kèm version_id")
        _checked(check_version_id, version_id)
        known = version_id in ((_images(ctx).entry(product_id) or {}).get("versions") or {})
        art = await asyncio.to_thread(load_version_art, ctx.settings.scene_dir, product_id, version_id)
        if not known or art is None:
            raise ApiError(404, "unknown_version", f"Không có phiên bản ảnh {version_id} của sản phẩm {product_id}")
        overrides[product_id] = art
    png = await controller.preview(ctx.store.catalog, overrides, controller.highlight, target=target, debug=debug)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


class ApplyIn(BaseModel):
    version_id: str
    # Any type on purpose: only the JSON value `true` counts, never "true" or 1 (FR-006).
    rights_confirmed: Any = None


async def _after_change(
    ctx: AppContext,
    product_id: str,
    action: str,
    version_id: str | None,
    from_state: ImageState,
    entry: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    """Shared tail of apply / revert / remove: redraw, tell the pages, log, answer (contracts/api.md §1)."""
    controller = ctx.scene
    scene_version = await controller.reload() if controller is not None else None
    to_frame_ms = round((time.perf_counter() - started) * 1000, 1) if scene_version is not None else None
    active: ImageState = entry.get("active", KIT)
    ctx.bus.publish(
        Event(
            EventType.SCENE,
            {
                "kind": "image_changed",
                "product_id": product_id,
                "action": action,
                "active": active,
                "scene_version": scene_version,
            },
        )
    )
    log_event(
        logger,
        "scene_image_changed",
        action=action,
        product_id=product_id,
        version_id=version_id,
        from_state=from_state,
        to_state=active,
        result="ok",
        to_frame_ms=to_frame_ms,
        scene_version=scene_version,
    )
    version = (entry.get("versions") or {}).get(active) if active not in (None, KIT) else None
    version = version if isinstance(version, dict) else {}
    return {
        "product_id": product_id,
        "active": active,
        "applied_at": version.get("applied_at"),
        "rights_confirmed_at": version.get("rights_confirmed_at"),
        "scene_version": scene_version,
        "to_frame_ms": to_frame_ms,
        "scene_enabled": ctx.settings.scene_enabled,
    }


def _log_failed_change(action: str, product_id: str, version_id: str | None, from_state: ImageState, code: str) -> None:
    log_event(
        logger,
        "scene_image_changed",
        logging.WARNING,
        action=action,
        product_id=product_id,
        version_id=version_id,
        from_state=from_state,
        to_state=from_state,
        result=code,
        to_frame_ms=None,
        scene_version=None,
    )


@router.post("/api/scene/images/{product_id}/apply")
async def apply_scene_image(request: Request, product_id: str, body: ApplyIn) -> dict[str, Any]:
    """Show an uploaded version on live once the operator confirmed the rights (FR-006, FR-008, FR-009)."""
    started = time.perf_counter()
    ctx = _ctx(request)
    _checked(check_product_id, product_id)
    _checked(check_version_id, body.version_id)
    if body.rights_confirmed is not True:
        raise ApiError(422, "rights_not_confirmed", "Chưa đánh dấu xác nhận quyền dùng ảnh")
    _live_product(ctx, product_id)
    await _check_scene_owner(ctx)
    store = _images(ctx)
    from_state = store.active(product_id)
    try:
        entry = await store.apply(product_id, body.version_id, now_iso())
    except ImageStoreError as exc:
        _log_failed_change("apply", product_id, body.version_id, from_state, exc.code)
        raise _api_error(exc) from exc
    return await _after_change(ctx, product_id, "apply", body.version_id, from_state, entry, started)


class RemoveIn(BaseModel):
    # Any type on purpose, as `rights_confirmed`: only the JSON value `true` removes (FR-017).
    confirm: Any = None


async def _change_image(request: Request, product_id: str, action: str) -> dict[str, Any]:
    """Revert or remove: the same checks and tail as apply (012 US3, FR-016, FR-017)."""
    started = time.perf_counter()
    ctx = _ctx(request)
    _live_product(ctx, product_id)
    await _check_scene_owner(ctx)
    store = _images(ctx)
    from_state = store.active(product_id)
    try:
        entry = await (store.revert(product_id) if action == "revert" else store.remove(product_id))
    except ImageStoreError as exc:
        _log_failed_change(action, product_id, None, from_state, exc.code)
        raise _api_error(exc) from exc
    active = entry.get("active")
    version_id = active if active not in (None, KIT) else None
    return await _after_change(ctx, product_id, action, version_id, from_state, entry, started)


@router.post("/api/scene/images/{product_id}/revert")
async def revert_scene_image(request: Request, product_id: str) -> dict[str, Any]:
    """Go back to the image shown before the last change, kit or upload or none (FR-016)."""
    _checked(check_product_id, product_id)
    return await _change_image(request, product_id, "revert")


@router.post("/api/scene/images/{product_id}/remove")
async def remove_scene_image(request: Request, product_id: str, body: RemoveIn) -> dict[str, Any]:
    """Take the product's image off live; its name/price card stays (FR-017)."""
    _checked(check_product_id, product_id)
    if body.confirm is not True:
        raise ApiError(422, "remove_not_confirmed", "Chưa xác nhận gỡ ảnh")
    return await _change_image(request, product_id, "remove")


# ---------- 012 US2: "Chuẩn bị bộ mới" (contracts/api.md §2, research R7) ----------


def _staging(ctx: AppContext) -> StagedSet:
    if ctx.staging is None:
        raise ApiError(404, "no_staging", "Chưa có bộ chuẩn bị")
    return ctx.staging


async def _kit_ids(ctx: AppContext, product_ids: list[str]) -> set[str]:
    root = ctx.settings.scene_dir
    return await asyncio.to_thread(lambda: {pid for pid in product_ids if kit_art_path(root, pid) is not None})


async def _staging_view(ctx: AppContext, staged: StagedSet) -> dict[str, Any]:
    kits = await _kit_ids(ctx, [p.id for p in staged.catalog.products])
    return staged.view(_images(ctx), live_version=ctx.store.catalog.version, kit_ids=kits)


def _staging_event(ctx: AppContext, action: str, staged_id: str) -> None:
    ctx.bus.publish(Event(EventType.SCENE, {"kind": "staging", "action": action, "staged_id": staged_id}))


async def _staging_preview(ctx: AppContext, staged: StagedSet, *, debug: bool = False) -> Response:
    """The whole staged set drawn as it would go live: its catalog and the images it would end up with (R4)."""
    controller = ctx.scene
    assert controller is not None
    root = ctx.settings.scene_dir
    ids = [p.id for p in staged.catalog.products]
    winning = staged.winning(_images(ctx))

    def _load() -> tuple[SceneSet, dict[str, ProductArt | None]]:
        scene = load_scene_set(root, ids, customer_id=ctx.settings.customer_id)
        overrides = {a.product_id: load_version_art(root, a.product_id, a.version_id) for a in winning}
        return scene, overrides

    scene, overrides = await asyncio.to_thread(_load)
    png = await controller.preview(staged.catalog, overrides, None, scene=scene, target="staging", debug=debug)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/api/content/staging")
async def create_staging(request: Request) -> dict[str, Any]:
    """Read a new content file without installing it; replaces any staged set (FR-013)."""
    ctx = _ctx(request)
    catalog = await parse_content_upload(ctx, request)
    staged = StagedSet.create(catalog, catalog.source_name, ctx.store.catalog.version, now=now_iso())
    ctx.staging = staged
    view = await _staging_view(ctx, staged)
    _staging_event(ctx, "created", staged.staged_id)
    log_event(logger, "scene_staging_created", staged_id=staged.staged_id, products=len(catalog.products))
    return view


@router.get("/api/content/staging")
async def get_staging(request: Request) -> dict[str, Any]:
    ctx = _ctx(request)
    return await _staging_view(ctx, _staging(ctx))


@router.delete("/api/content/staging", status_code=204)
async def cancel_staging(request: Request) -> Response:
    """Drop the staged set (FR-015a); uploaded images stay in the manifest for later."""
    ctx = _ctx(request)
    staged = _staging(ctx)
    ctx.staging = None
    _staging_event(ctx, "cancelled", staged.staged_id)
    return Response(status_code=204)


class StagedImageIn(BaseModel):
    staged_id: str
    version_id: str | None = None
    # Any type on purpose: only the JSON value `true` counts (FR-006).
    rights_confirmed: Any = None


@router.post("/api/content/staging/images/{product_id}")
async def assign_staged_image(request: Request, product_id: str, body: StagedImageIn) -> dict[str, Any]:
    """Give a staged product an uploaded version; nothing on live changes (FR-013)."""
    ctx = _ctx(request)
    staged = _staging(ctx)
    staged.check_id(body.staged_id)
    _checked(check_product_id, product_id)
    if body.version_id is not None:
        _checked(check_version_id, body.version_id)
    staged.assign(_images(ctx), product_id, body.version_id, rights_confirmed=body.rights_confirmed, now=now_iso())
    _staging_event(ctx, "updated", staged.staged_id)
    return await _staging_view(ctx, staged)


class StagingApplyIn(BaseModel):
    staged_id: str
    # Only the JSON value `true` skips the "some products have no image" question (FR-015).
    confirm_missing: Any = None


@router.post("/api/content/staging/apply")
async def apply_staging(request: Request, body: StagingApplyIn) -> dict[str, Any]:
    """Catalog and images go live together: no frame shows new cards with old pictures (FR-015, research R7)."""
    started = time.perf_counter()
    ctx = _ctx(request)
    staged = _staging(ctx)
    staged.check_id(body.staged_id)
    store = _images(ctx)
    catalog = staged.catalog
    kits = await _kit_ids(ctx, [p.id for p in catalog.products])
    lacking = staged.missing_products(store, kits)
    if lacking and body.confirm_missing is not True:
        raise ApiError(
            409,
            "missing_images",
            f"{len(lacking)} món chưa có ảnh: " + ", ".join(p.name for p in lacking),
            [{"product_id": p.id, "name": p.name} for p in lacking],
        )
    winning = staged.winning(store)
    controller = ctx.scene if ctx.scene is not None and ctx.scene.enabled else None
    try:
        await _check_scene_owner(ctx)
        snapshot = store.snapshot()
        async with controller.hold() if controller is not None else contextlib.nullcontext():
            try:
                await store.apply_many(winning)
            except ImageStoreError as exc:
                raise _api_error(exc) from exc
            try:
                ctx.store.install(catalog)
            except Exception as exc:
                # The manifest must not point at images of a set that never went live.
                await store.restore(snapshot)
                raise ApiError(500, "save_failed", f"Không nạp được bộ mới: {exc}") from exc
            # A running show follows at once, like `PUT /api/content`.
            ctx.director.on_catalog_replaced(catalog)
    except ApiError as exc:
        _log_staging_applied(staged, len(lacking), len(winning), exc.error, None)
        raise
    # Right after the hold with no await in between: this waits for the draw that reads both new files.
    scene_version = await controller.reload() if controller is not None else None
    to_frame_ms = round((time.perf_counter() - started) * 1000, 1) if scene_version is not None else None
    ctx.staging = None
    log_event(logger, "content_replaced", source=catalog.source_name, version=catalog.version)
    _log_staging_applied(staged, len(lacking), len(winning), "ok", to_frame_ms)
    _staging_event(ctx, "applied", staged.staged_id)
    return {
        **catalog_reply(catalog),
        "images_written": len(winning),
        "missing_images": len(lacking),
        "scene_version": scene_version,
        "to_frame_ms": to_frame_ms,
    }


def _log_staging_applied(staged: StagedSet, missing: int, written: int, result: str, to_frame_ms: float | None) -> None:
    log_event(
        logger,
        "scene_staging_applied",
        logging.INFO if result == "ok" else logging.WARNING,
        staged_id=staged.staged_id,
        products=len(staged.catalog.products),
        missing_images=missing,
        images_written=written,
        result=result,
        to_frame_ms=to_frame_ms,
    )


# ---------- 012 US4: the product as the file has it (FR-022, FR-023, contracts/api.md §3) ----------


@router.get("/api/content/products/{product_id}")
async def get_live_product(request: Request, product_id: str) -> dict[str, Any]:
    ctx = _ctx(request)
    product = next((p for p in ctx.store.catalog.products if p.id == product_id), None)
    if product is None:
        raise ApiError(404, "unknown_product", f"Không có sản phẩm {product_id} trong file đang nạp")
    return {**product_detail(product), "source": "live"}


@router.get("/api/content/staging/products/{product_id}")
async def get_staged_product(request: Request, product_id: str) -> dict[str, Any]:
    """Same panel for the staged set, marked `staging` so the page says it is not live yet (FR-023)."""
    staged = _staging(_ctx(request))
    return {**product_detail(staged.product(product_id)), "source": "staging"}
