"""Common JSON HTTP error body `{"error", "message", "details"}` (contracts/api.md)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# 004 `POST /api/show/start` refusals (contracts/api.md §2); the operator reads these on the control page.
HOST_UNAVAILABLE_MESSAGE = "Màn hình host chưa sẵn sàng. Mở /host và bấm Bắt đầu."
NO_CONTENT_MESSAGE = "Chưa nạp file nội dung sản phẩm hợp lệ."
# 004 `POST /api/show/next` refusals (contracts/api.md §2).
SHOW_NOT_RUNNING_MESSAGE = "Show chưa chạy."
TOPIC_UNAVAILABLE_MESSAGE = "Sản phẩm này không có dữ liệu cho chủ đề đã chọn."

_HTTP_CODES = {
    404: ("not_found", "Không tìm thấy"),
    405: ("method_not_allowed", "Phương thức không được hỗ trợ"),
}


class ApiError(Exception):
    def __init__(
        self, status: int, error: str, message: str, details: list[Any] | dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message
        self.details = details or []


def error_response(
    status: int, error: str, message: str, details: list[Any] | dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse({"error": error, "message": message, "details": details or []}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.error, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # `input` is not echoed back: the body may hold viewer text; the location and reason are enough.
        details = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()
        ]
        return error_response(422, "validation_error", "Dữ liệu gửi lên không đúng định dạng", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        error, message = _HTTP_CODES.get(exc.status_code, ("http_error", str(exc.detail)))
        return error_response(exc.status_code, error, message)
