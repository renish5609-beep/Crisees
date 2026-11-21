"""Road network access: paginated GeoJSON views and the full routing graph."""

from __future__ import annotations

import threading
from typing import Literal

import networkx as nx
from shapely.geometry import box

from app.schemas.common import Feature, FeatureCollection
from app.schemas.roads import RoadEdge, RoadNode
from app.services.repository import DataRepository
from app.services.road_graph import tables_to_graph
from app.services.serialization import clean_value, geometry_to_geojson, paginate

EDGE_FIELDS = list(RoadEdge.model_fields)
NODE_FIELDS = list(RoadNode.model_fields)

_graph_cache: dict[str, tuple[tuple[float, float], nx.MultiDiGraph]] = {}
_graph_lock = threading.Lock()


def roads_collection(
    repo: DataRepository,
    region_id: str,
    layer: Literal["edges", "nodes"],
    limit: int,
    offset: int,
    bbox: tuple[float, float, float, float] | None = None,
    road_classes: list[str] | None = None,
) -> FeatureCollection:
    key = "road_edges" if layer == "edges" else "road_nodes"
    gdf = repo.load(region_id, key)
    if bbox:
        gdf = gdf.iloc[gdf.sindex.query(box(*bbox), predicate="intersects")]
    if road_classes and layer == "edges":
        gdf = gdf[gdf["road_class"].isin(road_classes)]
    gdf = gdf.sort_values("edge_id" if layer == "edges" else "node_id")
    page, info = paginate(gdf, limit, offset)
    model, fields = (RoadEdge, EDGE_FIELDS) if layer == "edges" else (RoadNode, NODE_FIELDS)
    features = []
    for row in page.itertuples(index=False):
        d = row._asdict()
        props = {f: clean_value(d.get(f)) for f in fields}
        if layer == "edges":
            props["osm_way_ids"] = props.get("osm_way_ids") or []
        features.append(
            Feature[model](  # type: ignore[valid-type]
                id=props["edge_id"] if layer == "edges" else props["node_id"],
                geometry=geometry_to_geojson(d["geometry"]),
                properties=model(**props),
            )
        )
    return FeatureCollection[model](  # type: ignore[valid-type]
        features=features,
        page=info,
        provenance=repo.provenance(region_id, key),
        sources=repo.sources(region_id, key),
    )


def get_road_graph(repo: DataRepository, region_id: str) -> nx.MultiDiGraph:
    """Return the cached OSMnx-compatible graph for a region (Phase 2 entry point)."""
    nodes = repo.load(region_id, "road_nodes")
    edges = repo.load(region_id, "road_edges")
    stamp = (
        repo.path(region_id, "road_nodes").stat().st_mtime,
        repo.path(region_id, "road_edges").stat().st_mtime,
    )
    with _graph_lock:
        cached = _graph_cache.get(region_id)
        if cached and cached[0] == stamp:
            return cached[1]
    G = tables_to_graph(nodes, edges)
    with _graph_lock:
        _graph_cache[region_id] = (stamp, G)
    return G
