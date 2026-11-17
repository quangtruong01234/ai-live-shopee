"""WebSocket `/ws/control` và `/ws/host` (contracts/api.md §3–4)."""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ai_live.app.context import AppContext, build_state, now_iso
from ai_live.core.events import EventType, Subscription

router = APIRouter()


@router.websocket("/ws/control")
async def control_ws(ws: WebSocket) -> None:
    ctx: AppContext = ws.app.state.ctx
    await ws.accept()
    # Đăng ký trước khi gửi `state` để không lỡ sự kiện phát ra giữa hai bước.
    sub = ctx.bus.subscribe()
    forward = asyncio.create_task(_forward(ws, ctx, sub))
    try:
        # Client không gửi gì; vẫn phải đọc để biết lúc tab đóng,
        # nếu không task chuyển tiếp treo mãi khi không có sự kiện.
        while (await ws.receive())["type"] != "websocket.disconnect":
            pass
    except WebSocketDisconnect:
        pass
    finally:
        sub.close()
        forward.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await forward


async def _forward(ws: WebSocket, ctx: AppContext, sub: Subscription) -> None:
    await ws.send_json({"type": "state", "ts": now_iso(), **build_state(ctx)})
    async for event in sub:
        # One heartbeat a second from the host tab feeds the watchdog; the control page shows alerts instead (007).
        if event.type is EventType.HOST_STATUS:
            continue
        await ws.send_json({**event.to_json(), "ts": now_iso()})


@router.websocket("/ws/host")
async def host_ws(ws: WebSocket) -> None:
    ctx: AppContext = ws.app.state.ctx
    await ws.accept()
    # 006: `/obs` connects with role=obs and outranks a `/host` tab; a refused page was already closed with 4001.
    if not await ctx.renderer.attach(ws, ws.query_params.get("role", "host")):
        return
    try:
        while (message := await ws.receive())["type"] != "websocket.disconnect":
            # Message hỏng thì bỏ qua thay vì đóng kết nối: rớt host giữa live là mất tiếng.
            try:
                data = json.loads(message.get("text") or "")
            except ValueError:
                continue
            if isinstance(data, dict):
                ctx.renderer.handle_message(ws, data)
    except WebSocketDisconnect:
        pass
    finally:
        ctx.renderer.detach(ws)
