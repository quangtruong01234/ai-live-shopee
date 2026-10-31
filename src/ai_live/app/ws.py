"""WebSocket `/ws/control` và `/ws/host` (contracts/api.md §3–4)."""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ai_live.app.context import AppContext, build_state, now_iso
from ai_live.core.events import Subscription

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
        await ws.send_json({**event.to_json(), "ts": now_iso()})


@router.websocket("/ws/host")
async def host_ws(ws: WebSocket) -> None:
    ctx: AppContext = ws.app.state.ctx
    await ws.accept()
    await ctx.renderer.attach(ws)
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
