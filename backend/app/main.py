"""FastAPI application factory.

Run locally:  ``uvicorn app.main:app --reload --port 8000`` from ``backend/``.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api import health
from app.api.v1.router import api_router
from app.core.config import API_PREFIX, API_VERSION, Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

logger = logging.getLogger("crisees.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Crisees API",
        version=API_VERSION,
        description=(
            "Equity-aware flood evacuation accessibility data API. Planning and simulation use only; "
            "not an emergency dispatch system. All geometries are GeoJSON, EPSG:4326, [lon, lat]."
        ),
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "%s %s -> %d (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
