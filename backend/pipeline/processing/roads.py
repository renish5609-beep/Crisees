"""Road network processing for both providers into one standard graph.

Both providers end as an OSMnx-style ``MultiDiGraph`` (see
``app.services.road_graph``), restricted to the largest weakly connected
component (OSMnx's ``retain_all=False`` default), then flattened to
``road_nodes`` / ``road_edges`` tables.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely import remove_repeated_points, wkb
from shapely.geometry import LineString
from shapely.ops import substring, transform

logger = logging.getLogger(__name__)

# Overture road classes treated as drivable (mirrors OSMnx network_type="drive").
DRIVABLE_CLASSES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "living_street", "service",
}
# OSMnx's drive filter excludes these service subtypes.
EXCLUDED_SUBCLASSES = {"driveway", "parking_aisle", "drive_through", "alley"}
MOTOR_MODES = {None, "motor_vehicle", "car", "vehicle"}
MPH_TO_KPH = 1.609344


def parse_maxspeed_kph(value: Any) -> float | None:
    """Parse OSM ``maxspeed`` strings ('35 mph', '60', ['30 mph','40 mph']) to km/h."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (list, tuple)):
        parsed = [parse_maxspeed_kph(v) for v in value]
        parsed = [p for p in parsed if p is not None]
        return round(float(np.mean(parsed)), 1) if parsed else None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?\s*$", str(value), re.IGNORECASE)
    if not m:
        return None
    speed = float(m.group(1))
    unit = (m.group(2) or "km/h").lower()
    return round(speed * MPH_TO_KPH, 1) if unit == "mph" else speed


def stable_node_id(uuid_like: str) -> int:
    """Deterministic positive int64 from an Overture connector/point id (60 bits)."""
    return int(uuid_like.replace("-", "")[:15], 16)


def _osm_way_ids(sources: Any) -> list[int]:
    ids = []
    for s in sources if sources is not None else []:
        rid = s.get("record_id") or ""
        m = re.match(r"^w(\d+)", rid)
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids))


def _restrictions(restrictions: Any) -> tuple[bool, str | None]:
    """Return (closed_to_cars, oneway_direction) from unscoped access rules."""
    closed, oneway = False, None
    for r in restrictions if restrictions is not None else []:
        if r.get("access_type") != "denied" or r.get("between") is not None:
            continue
        when = r.get("when") or {}
        modes = when.get("mode")
        modes = list(modes) if modes is not None else [None]
        if not any(m in MOTOR_MODES for m in modes) or when.get("during") or when.get("using"):
            continue
        heading = when.get("heading")
        if heading is None:
            closed = True
        elif heading == "backward":
            oneway = "forward"
        elif heading == "forward":
            oneway = "backward"
    return closed, oneway


def _speed_kph(limits: Any) -> float | None:
    for lim in limits if limits is not None else []:
        if lim.get("between") is not None or lim.get("when") is not None:
            continue
        mx = lim.get("max_speed")
        if mx and mx.get("value") is not None:
            v = float(mx["value"])
            return round(v * MPH_TO_KPH, 1) if mx.get("unit") == "mph" else v
    return None


def overture_to_graph(path: Path, analysis_crs: str) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Split Overture segments at their connectors and build a directed graph."""
    import pyproj

    df = pd.read_parquet(path)
    n_raw = len(df)
    df = df[(df["subtype"] == "road") & df["class"].isin(DRIVABLE_CLASSES)]
    df = df[~df["subclass"].isin(EXCLUDED_SUBCLASSES)].rename(columns={"class": "road_class"})
    to_proj = pyproj.Transformer.from_crs(4326, analysis_crs, always_xy=True).transform
    to_wgs = pyproj.Transformer.from_crs(analysis_crs, 4326, always_xy=True).transform

    drivable = len(df)
    G = nx.MultiDiGraph(crs="EPSG:4326")
    closed_count = 0
    for row in df.itertuples(index=False):
        closed, oneway = _restrictions(row.access_restrictions)
        if closed:
            closed_count += 1
            continue
        line_wgs = wkb.loads(row.geometry) if isinstance(row.geometry, (bytes, bytearray)) else row.geometry
        if not isinstance(line_wgs, LineString) or line_wgs.length == 0:
            continue
        line = transform(to_proj, line_wgs)
        conns = sorted(((c["at"], c["connector_id"]) for c in (row.connectors if row.connectors is not None else [])))
        if len(conns) < 2:
            continue
        road_class = row.road_class
        if row.subclass == "link":
            road_class = f"{road_class}_link"
        names = row.names
        name = names.get("primary") if isinstance(names, dict) else None
        way_ids = _osm_way_ids(row.sources)
        speed = _speed_kph(row.speed_limits)
        for (a0, c0), (a1, c1) in zip(conns[:-1], conns[1:]):
            if a1 <= a0:
                continue
            part = substring(line, a0, a1, normalized=True)
            if part.is_empty or part.length == 0:
                continue
            u, v = stable_node_id(c0), stable_node_id(c1)
            if u == v:
                continue
            geom = remove_repeated_points(transform(to_wgs, part), 1e-9)
            if len(geom.coords) < 2:
                continue
            for node, conn_id, xy in ((u, c0, geom.coords[0]), (v, c1, geom.coords[-1])):
                if node not in G:
                    G.add_node(node, x=round(xy[0], 7), y=round(xy[1], 7), source_ref=f"overture:connector:{conn_id}")
            attrs = dict(
                length=round(part.length, 3), highway=road_class, name=name,
                osmid=way_ids[0] if len(way_ids) == 1 else (tuple(way_ids) if way_ids else None),
                maxspeed_kph=speed, source_ref=f"overture:segment:{row.id}",
            )
            if oneway is None:
                G.add_edge(u, v, oneway=False, reversed=False, geometry=geom, **attrs)
                G.add_edge(v, u, oneway=False, reversed=True, geometry=LineString(geom.coords[::-1]), **attrs)
            elif oneway == "forward":
                G.add_edge(u, v, oneway=True, reversed=False, geometry=geom, **attrs)
            else:
                G.add_edge(v, u, oneway=True, reversed=True, geometry=LineString(geom.coords[::-1]), **attrs)
    stats = {"raw_segments": n_raw, "drivable_segments": drivable, "segments_closed_to_motor_vehicles": closed_count}
    return G, stats


def finalize_graph(G: nx.MultiDiGraph) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Keep the largest weakly connected component and compute street counts."""
    import osmnx as ox

    before = G.number_of_nodes()
    wcc = max(nx.weakly_connected_components(G), key=len) if before else set()
    G = G.subgraph(wcc).copy()
    counts = ox.stats.count_streets_per_node(G)
    nx.set_node_attributes(G, counts, "street_count")
    return G, {"nodes_before_component_filter": before, "nodes_dropped_outside_largest_wcc": before - len(wcc)}


def osmnx_to_graph(path: Path) -> nx.MultiDiGraph:
    import osmnx as ox

    G = ox.load_graphml(path)
    for _, _, d in G.edges(data=True):
        d["maxspeed_kph"] = parse_maxspeed_kph(d.get("maxspeed"))
        osmid = d.get("osmid")
        d["source_ref"] = f"osm:way:{osmid[0] if isinstance(osmid, list) else osmid}"
    for n, d in G.nodes(data=True):
        d["source_ref"] = f"osm:node:{n}"
    return G


def clip_edges_check(edges: gpd.GeoDataFrame) -> dict[str, Any]:
    return {
        "edge_count": len(edges),
        "total_length_km": round(float(edges["length_m"].sum()) / 1000, 2),
        "oneway_edges": int(edges["oneway"].sum()),
    }
