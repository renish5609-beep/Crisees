"""Shared schema primitives: provenance, source attribution, GeoJSON, pagination.

Coordinate convention: every geometry exchanged by the API is GeoJSON in
WGS84 (EPSG:4326) with **[longitude, latitude]** axis order (RFC 7946).
Metric computations (lengths, areas, distances) are done in the region's
projected ``analysis_crs`` (UTM zone 15N, EPSG:32615, for Houston).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

WGS84 = "EPSG:4326"


class Provenance(str, Enum):
    """How a record came to exist. Never mix these silently."""

    real = "real"  # observed values published by an external authority
    derived = "derived"  # computed by Crisees from real inputs (documented method)
    synthetic = "synthetic"  # fabricated fixture for tests/local dev only


class SourceAttribution(BaseModel):
    source_id: str = Field(description="Stable Crisees identifier for the source, e.g. 'acs5-2024'.")
    name: str
    publisher: str
    url: str | None = None
    license: str | None = None
    vintage: str | None = Field(default=None, description="Data year or release identifier.")
    retrieved_at: str | None = Field(default=None, description="ISO-8601 UTC timestamp of download.")
    notes: str | None = None


class GeoJSONGeometry(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal[
        "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"
    ]
    coordinates: Any = None


P = TypeVar("P", bound=BaseModel)


class Feature(BaseModel, Generic[P]):
    type: Literal["Feature"] = "Feature"
    id: str | int | None = None
    geometry: GeoJSONGeometry | None
    properties: P


class PageInfo(BaseModel):
    total: int = Field(description="Number of records matching the filters.")
    limit: int
    offset: int
    returned: int
    next_offset: int | None = None


class FeatureCollection(BaseModel, Generic[P]):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature[P]]
    crs_note: str = "RFC 7946 GeoJSON: WGS84 (EPSG:4326), [longitude, latitude]."
    page: PageInfo
    provenance: Provenance
    sources: list[SourceAttribution] = []


class RecordPage(BaseModel, Generic[P]):
    records: list[P]
    page: PageInfo
    provenance: Provenance
    sources: list[SourceAttribution] = []
