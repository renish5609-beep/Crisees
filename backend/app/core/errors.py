"""Domain errors and their mapping to HTTP responses.

Every error response has the shape::

    {"error": {"code": str, "message": str, "details": {...}}}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class CriseesError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class RegionNotFoundError(CriseesError):
    status_code = 404
    code = "region_not_found"


class DatasetNotAvailableError(CriseesError):
    """The dataset has not been downloaded/processed yet (or failed validation)."""

    status_code = 503
    code = "dataset_not_available"


class DatasetCorruptError(CriseesError):
    status_code = 500
    code = "dataset_corrupt"


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CriseesError)
    async def _crisees(_: Request, exc: CriseesError) -> JSONResponse:
        if exc.status_code >= 500 and not isinstance(exc, DatasetNotAvailableError):
            logger.error("%s: %s %s", exc.code, exc.message, exc.details)
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "Invalid request parameters.", {"errors": errors}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body("http_error", str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=500, content=_body("internal_error", "An unexpected error occurred.")
        )
