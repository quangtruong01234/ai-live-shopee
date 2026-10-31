"""Log JSON một dòng mỗi bản ghi (contracts/events.md §1). Mọi bản ghi đi qua `redact` trước khi ghi (FR-021)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from ai_live.security.redact import redact


class JsonFormatter(logging.Formatter):
    def __init__(self, session_id: str | None = None) -> None:
        super().__init__()
        self.session_id = session_id

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "session_id": self.session_id,
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(fields)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(redact(entry), ensure_ascii=False, default=str)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Ghi một sự kiện có cấu trúc: `event` là tên sự kiện, các trường thêm nằm cùng cấp trong dòng JSON."""
    logger.log(level, event, extra={"fields": fields})


def configure_logging(level: str = "INFO", session_id: str | None = None) -> None:
    # Windows chuyển hướng stdout ra file thì dùng cp1252: log tiếng Việt lỗi encode và mất dòng log.
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    if encoding != "utf8" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(session_id))
    root = logging.getLogger("ai_live")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
