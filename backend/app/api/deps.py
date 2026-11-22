from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Query

from app.core.config import Settings, get_settings
from app.services.repository import DataRepository


@lru_cache
def _repository() -> DataRepository:
    settings = get_settings()
    _provision_data(settings)
    return DataRepository(settings)


def _provision_data(settings: Settings) -> None:
    """If CRISEES_DATA_URL/SHA256 are set and the data is missing (e.g. a fresh
    serverless instance with an empty /tmp), install the release once. Failures
    are logged; data endpoints then return 503 rather than invented values."""
    if not (settings.data_url and settings.data_sha256):
        return
    import logging

    from app.regions import load_regions
    from pipeline.release import ReleaseError, install_release

    for region in load_regions():
        try:
            install_release(settings, region, settings.data_url, settings.data_sha256)
        except ReleaseError as exc:
            logging.getLogger("crisees.data").error("data release not installed: %s", exc)


def get_repository() -> DataRepository:
    return _repository()


Repo = Annotated[DataRepository, Depends(get_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class Pagination:
    def __init__(
        self,
        settings: SettingsDep,
        limit: Annotated[int | None, Query(ge=1, description="Page size (bounded by server max)")] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = min(limit or settings.default_page_size, settings.max_page_size)
        self.offset = offset


Page = Annotated[Pagination, Depends()]
