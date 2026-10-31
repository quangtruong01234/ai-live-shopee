"""Lỗi HTTP dạng JSON chung `{"error", "message", "details"}` (contracts/api.md)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_HTTP_CODES = {
    404: ("not_found", "Không tìm thấy"),
    405: ("method_not_allowed", "Phương thức không được hỗ trợ"),
}


class ApiError(Exception):
    def __init__(self, status: int, error: str, message: str, details: list[Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message
        self.details = details or []


def error_response(status: int, error: str, message: str, details: list[Any] | None = None) -> JSONResponse:
    return JSONResponse({"error": error, "message": message, "details": details or []}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.error, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Không trả lại `input`: body có thể chứa nội dung người xem, chỉ cần vị trí và lý do lỗi.
        details = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()
        ]
        return error_response(422, "validation_error", "Dữ liệu gửi lên không đúng định dạng", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        error, message = _HTTP_CODES.get(exc.status_code, ("http_error", str(exc.detail)))
        return error_response(exc.status_code, error, message)
