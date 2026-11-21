from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Query

from app.core.config import Settings, get_settings
from app.services.repository import DataRepository


@lru_cache
def _repository() -> DataRepository:
    return DataRepository(get_settings())


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
