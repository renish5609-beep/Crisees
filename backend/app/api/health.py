from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import Repo, SettingsDep
from app.core.config import API_VERSION
from app.datasets import utc_now
from app.regions import load_regions

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    time: str
    data_dir_exists: bool
    regions_configured: int
    regions_with_processed_data: int


@router.get("/health", response_model=HealthResponse, summary="Liveness and data-directory check")
def health(settings: SettingsDep, repo: Repo) -> HealthResponse:
    regions = load_regions()
    processed = sum(1 for r in regions if repo.manifest(r) is not None)
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        environment=settings.env,
        time=utc_now(),
        data_dir_exists=settings.data_dir.exists(),
        regions_configured=len(regions),
        regions_with_processed_data=processed,
    )
