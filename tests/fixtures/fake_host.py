"""Trang `/host` giả: nhận message của `StaticRenderer` và gửi ack như trình duyệt thật (contracts/api.md §4)."""

from __future__ import annotations

import asyncio
from typing import Any


class FakeHostConnection:
    """Kết nối host giả. `auto_ack=True` thì gửi `playback_started` khi nhận `sentence_start` và `sentence_played`
    khi nhận `sentence_end`, mô phỏng trình duyệt phát xong ngay.
    """

    def __init__(self, renderer: Any = None, *, auto_ack: bool = True, ack_delay_s: float = 0.0) -> None:
        self.renderer = renderer
        self.auto_ack = auto_ack
        self.ack_delay_s = ack_delay_s
        self.sent: list[Any] = []  # dict cho JSON, bytes cho audio
        self.closed_code: int | None = None
        self.closed_reason: str | None = None
        self._tasks: set[asyncio.Task] = set()

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)
        if not self.auto_ack or self.renderer is None:
            return
        if data.get("type") == "sentence_start":
            self._ack("playback_started", data)
        elif data.get("type") == "sentence_end":
            self._ack("sentence_played", data)

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed_code = code
        self.closed_reason = reason

    def _ack(self, kind: str, data: dict) -> None:
        message = {"type": kind, "utterance_id": data["utterance_id"], "seq": data["seq"]}

        async def send() -> None:
            if self.ack_delay_s:
                await asyncio.sleep(self.ack_delay_s)
            self.renderer.handle_message(self, message)

        task = asyncio.get_running_loop().create_task(send())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # Tiện ích cho assert.
    def json_messages(self, kind: str | None = None) -> list[dict]:
        return [m for m in self.sent if isinstance(m, dict) and (kind is None or m.get("type") == kind)]

    def audio_bytes(self) -> int:
        return sum(len(m) for m in self.sent if isinstance(m, bytes))
