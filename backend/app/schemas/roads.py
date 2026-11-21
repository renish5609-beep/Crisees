from __future__ import annotations

from pydantic import BaseModel, Field


class RoadNode(BaseModel):
    node_id: int = Field(description="Stable integer node id (OSM node id for OSMnx; hashed connector id for Overture)")
    lon: float
    lat: float
    street_count: int | None = None
    source_ref: str | None = Field(default=None, description="Upstream identifier (OSM node / Overture connector)")


class RoadEdge(BaseModel):
    edge_id: str = Field(description="'{u}-{v}-{key}'")
    u: int
    v: int
    key: int
    road_class: str = Field(description="OSM 'highway' class, e.g. primary, residential, motorway_link")
    name: str | None = None
    length_m: float = Field(ge=0)
    oneway: bool
    reversed: bool = Field(default=False, description="True if this edge digitises the source way backwards")
    maxspeed_kph: float | None = None
    lanes: float | None = None
    osm_way_ids: list[int] = Field(default_factory=list)
    source_ref: str | None = None
