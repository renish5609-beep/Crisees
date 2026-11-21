"""Registry of supported study regions.

Each region is a JSON file in ``definitions/``. Adding a region requires only a
new definition file and running the data pipeline; no code changes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.core.errors import RegionNotFoundError

DEFINITIONS_DIR = Path(__file__).parent / "definitions"


class RegionDefinition(BaseModel):
    region_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    description: str
    country: str = "US"
    state_fips: str = Field(pattern=r"^\d{2}$")
    state_abbr: str
    county_fips: list[str]
    county_names: dict[str, str] = {}
    selection_bbox: tuple[float, float, float, float]
    road_buffer_m: float = 1000
    analysis_crs: str = "EPSG:32615"
    acs_year: int
    tiger_year: int
    hazard: str = "flood"
    selection_rule: str
    justification: list[str] = []

    @field_validator("county_fips")
    @classmethod
    def _three_digits(cls, v: list[str]) -> list[str]:
        for c in v:
            if len(c) != 3 or not c.isdigit():
                raise ValueError(f"county FIPS must be 3 digits: {c!r}")
        return v

    @field_validator("selection_bbox")
    @classmethod
    def _valid_bbox(cls, v: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        w, s, e, n = v
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("bbox must be [west, south, east, north] in lon/lat degrees")
        return v

    @property
    def county_geoids(self) -> list[str]:
        return [self.state_fips + c for c in self.county_fips]


@lru_cache
def load_regions() -> dict[str, RegionDefinition]:
    regions: dict[str, RegionDefinition] = {}
    for path in sorted(DEFINITIONS_DIR.glob("*.json")):
        region = RegionDefinition.model_validate(json.loads(path.read_text()))
        regions[region.region_id] = region
    return regions


def get_region(region_id: str) -> RegionDefinition:
    try:
        return load_regions()[region_id]
    except KeyError:
        raise RegionNotFoundError(
            f"Unknown region '{region_id}'.", region_id=region_id, available=sorted(load_regions())
        ) from None
