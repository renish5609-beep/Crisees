"""Conversion between the stored road tables and a NetworkX graph.

The graph follows OSMnx conventions so OSMnx/NetworkX routines work on it:

* ``nx.MultiDiGraph`` with ``graph["crs"] = "EPSG:4326"``
* node attributes ``x`` (lon), ``y`` (lat), ``street_count``
* edge keys ``(u, v, key)``; attributes ``length`` (metres), ``highway``,
  ``oneway``, ``reversed``, ``name``, ``osmid``, ``geometry`` (shapely LineString)

Two-way streets are stored as two directed edges (u->v and v->u), exactly
as OSMnx does, so topology and directionality round-trip losslessly.
"""

from __future__ import annotations

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import LineString, Point

NODE_COLUMNS = ["node_id", "lon", "lat", "street_count", "source_ref"]
EDGE_COLUMNS = [
    "edge_id",
    "u",
    "v",
    "key",
    "road_class",
    "name",
    "length_m",
    "oneway",
    "reversed",
    "maxspeed_kph",
    "lanes",
    "osm_way_ids",
    "source_ref",
]


def _first(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def graph_to_tables(G: nx.MultiDiGraph) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Flatten a (OSMnx-style) MultiDiGraph into node and edge GeoDataFrames."""
    node_rows = []
    for n, d in G.nodes(data=True):
        node_rows.append(
            {
                "node_id": int(n),
                "lon": float(d["x"]),
                "lat": float(d["y"]),
                "street_count": int(d["street_count"]) if d.get("street_count") is not None else None,
                "source_ref": d.get("source_ref"),
            }
        )
    nodes = gpd.GeoDataFrame(
        pd.DataFrame(node_rows, columns=NODE_COLUMNS),
        geometry=[Point(r["lon"], r["lat"]) for r in node_rows],
        crs="EPSG:4326",
    )
    nodes["street_count"] = nodes["street_count"].astype("Int64")

    edge_rows, geoms = [], []
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        if geom is None:  # OSMnx omits geometry for straight edges
            geom = LineString([(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])])
        osmid = d.get("osmid")
        way_ids = [int(x) for x in (osmid if isinstance(osmid, (list, tuple)) else [osmid]) if x is not None]
        maxspeed = d.get("maxspeed_kph", d.get("speed_kph"))
        lanes = _first(d.get("lanes"))
        try:
            lanes = float(lanes) if lanes is not None else None
        except (TypeError, ValueError):
            lanes = None
        edge_rows.append(
            {
                "edge_id": f"{u}-{v}-{k}",
                "u": int(u),
                "v": int(v),
                "key": int(k),
                "road_class": str(_first(d.get("highway")) or "unclassified"),
                "name": _first(d.get("name")),
                "length_m": float(d["length"]),
                "oneway": bool(d.get("oneway", False)),
                "reversed": bool(_first(d.get("reversed", False))),
                "maxspeed_kph": float(maxspeed) if maxspeed is not None else None,
                "lanes": lanes,
                "osm_way_ids": way_ids,
                "source_ref": d.get("source_ref"),
            }
        )
        geoms.append(geom)
    edges = gpd.GeoDataFrame(pd.DataFrame(edge_rows, columns=EDGE_COLUMNS), geometry=geoms, crs="EPSG:4326")
    return nodes, edges


def tables_to_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.MultiDiGraph:
    """Rebuild the OSMnx-compatible MultiDiGraph from stored node/edge tables."""
    G = nx.MultiDiGraph(crs="EPSG:4326")
    for row in nodes.itertuples(index=False):
        attrs = {"x": float(row.lon), "y": float(row.lat)}
        sc = getattr(row, "street_count", None)
        if sc is not None and not pd.isna(sc):
            attrs["street_count"] = int(sc)
        G.add_node(int(row.node_id), **attrs)
    has_geom = "geometry" in edges.columns
    for row in edges.itertuples(index=False):
        u, v = int(row.u), int(row.v)
        if u not in G or v not in G:
            raise ValueError(f"Edge {row.edge_id} references a missing node")
        attrs = {
            "length": float(row.length_m),
            "highway": row.road_class,
            "oneway": bool(row.oneway),
            "reversed": bool(row.reversed),
        }
        if row.name is not None and not (isinstance(row.name, float) and pd.isna(row.name)):
            attrs["name"] = row.name
        way_ids = list(row.osm_way_ids) if row.osm_way_ids is not None else []
        if way_ids:
            attrs["osmid"] = way_ids[0] if len(way_ids) == 1 else way_ids
        if row.maxspeed_kph is not None and not pd.isna(row.maxspeed_kph):
            attrs["maxspeed_kph"] = float(row.maxspeed_kph)
        if has_geom and row.geometry is not None:
            attrs["geometry"] = row.geometry
        G.add_edge(u, v, key=int(row.key), **attrs)
    return G
