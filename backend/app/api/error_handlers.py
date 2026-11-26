"""Turn every failure into the standard error envelope without leaking internals
(no stack traces, SQL text, file paths or input values)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError

logger = logging.getLogger("autoevolve")

_HTTP_CODES = {400: "BAD_REQUEST", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def error_response(status_code: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body = {"success": False, "data": None, "error": {"code": code, "message": message, "details": details}}
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", ())), "message": str(err.get("msg", "invalid"))}
            for err in exc.errors()
        ]
        return error_response(422, "VALIDATION_ERROR", "The request is invalid.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "The request could not be processed."
        return error_response(exc.status_code, code, message)

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError):
        logger.warning("Integrity error: %s", type(exc.orig).__name__)
        return error_response(409, "CONFLICT", "The request conflicts with existing data.")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        return error_response(500, "INTERNAL_ERROR", "An internal error occurred.")
