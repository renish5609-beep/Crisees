"""Engine A: road-network routing and travel-time modelling.

The baseline road graph (Phase 1 ``road_nodes`` / ``road_edges``) is held as
immutable NumPy arrays. Scenario evaluations never mutate it: a closure is a
boolean edge mask from which a fresh sparse matrix is built in a few
milliseconds. Shortest paths use SciPy's compiled Dijkstra
(``scipy.sparse.csgraph.dijkstra``), which supports many sources per call,
``min_only`` multi-source search and distance ``limit`` cut-offs.

Units: distance in metres, time in minutes, speed in km/h.

Two networks are derived from the same edges:

* **drive**: directed, honours one-way streets; weight = minutes.
* **walk (proxy)**: undirected, excludes motorways/trunks and their links;
  weight = metres. There is no pedestrian network (sidewalks, crossings),
  so this is a *proxy* for walking access and is labelled as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

# Free-flow speed assumptions by OSM highway class (km/h). Used only when an
# edge has no plausible posted speed. Values follow typical Houston/Texas urban
# posted limits (mph in comments). They are planning assumptions, not data.
CLASS_SPEED_KPH: dict[str, float] = {
    "motorway": 96.6,  # 60 mph
    "motorway_link": 56.3,  # 35 mph
    "trunk": 80.5,  # 50 mph
    "trunk_link": 48.3,  # 30 mph
    "primary": 64.4,  # 40 mph
    "primary_link": 40.2,  # 25 mph
    "secondary": 56.3,  # 35 mph
    "secondary_link": 40.2,
    "tertiary": 48.3,  # 30 mph
    "tertiary_link": 40.2,
    "unclassified": 40.2,  # 25 mph
    "residential": 40.2,  # 25 mph
    "living_street": 16.1,  # 10 mph
    "service": 24.1,  # 15 mph
}
DEFAULT_SPEED_KPH = 40.2
POSTED_SPEED_RANGE = (8.0, 130.0)  # outside this a posted value is treated as unreliable
NON_WALKABLE = {"motorway", "motorway_link", "trunk", "trunk_link"}
RESIDENTIAL_CLASSES = {"residential", "living_street", "unclassified"}
WALK_SPEED_M_PER_MIN = 80.0  # 4.8 km/h; slower walkers are a documented limitation


@dataclass(frozen=True)
class SpeedModel:
    """Travel-time assumptions. ``speed_factor`` scales all speeds (e.g. 0.7
    for evacuation congestion); ``class_speed_kph`` overrides defaults."""

    speed_factor: float = 1.0
    class_speed_kph: tuple[tuple[str, float], ...] = ()

    def table(self) -> dict[str, float]:
        t = dict(CLASS_SPEED_KPH)
        t.update(dict(self.class_speed_kph))
        return t


@dataclass
class RoadNetwork:
    """Immutable array representation of a directed road graph."""

    node_ids: np.ndarray  # int64 external node ids, index = internal id
    x: np.ndarray  # projected metres (analysis CRS)
    y: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    u: np.ndarray  # internal ids
    v: np.ndarray
    length_m: np.ndarray
    road_class: np.ndarray  # object array
    edge_ids: np.ndarray  # object array, "{u}-{v}-{key}"
    segment_id: np.ndarray  # int: both directions of a physical segment share it
    speed_kph: np.ndarray
    speed_source: np.ndarray  # "posted" | "class_default"
    time_min: np.ndarray
    walkable: np.ndarray  # bool per edge
    residential: np.ndarray  # bool per edge
    _kdtree: cKDTree = field(repr=False, default=None)  # type: ignore[assignment]
    _walk_kdtree: cKDTree = field(repr=False, default=None)  # type: ignore[assignment]
    _walk_nodes: np.ndarray = field(repr=False, default=None)  # type: ignore[assignment]

    # ------------------------------------------------------------------ build
    @classmethod
    def from_tables(
        cls,
        nodes: pd.DataFrame,
        edges: pd.DataFrame,
        analysis_crs: str,
        speed_model: SpeedModel | None = None,
    ) -> "RoadNetwork":
        import pyproj

        speed_model = speed_model or SpeedModel()
        nodes = nodes.reset_index(drop=True)
        index = pd.Series(np.arange(len(nodes)), index=nodes["node_id"].to_numpy())
        if index.index.has_duplicates:
            raise ValueError("duplicate node ids")
        missing = ~edges["u"].isin(index.index) | ~edges["v"].isin(index.index)
        if missing.any():
            raise ValueError(f"{int(missing.sum())} edges reference unknown nodes")
        tr = pyproj.Transformer.from_crs(4326, analysis_crs, always_xy=True)
        lon = nodes["lon"].to_numpy(float)
        lat = nodes["lat"].to_numpy(float)
        x, y = tr.transform(lon, lat)
        u = index[edges["u"].to_numpy()].to_numpy()
        v = index[edges["v"].to_numpy()].to_numpy()
        length = edges["length_m"].to_numpy(float)
        if (length < 0).any() or not np.isfinite(length).all():
            raise ValueError("edge lengths must be finite and non-negative")
        road_class = edges["road_class"].astype(str).to_numpy(object)
        posted = pd.to_numeric(edges.get("maxspeed_kph"), errors="coerce").to_numpy(float) if "maxspeed_kph" in edges else np.full(len(edges), np.nan)
        lo, hi = POSTED_SPEED_RANGE
        posted_ok = np.isfinite(posted) & (posted >= lo) & (posted <= hi)
        table = speed_model.table()
        class_speed = np.array([table.get(c, DEFAULT_SPEED_KPH) for c in road_class])
        speed = np.where(posted_ok, posted, class_speed) * speed_model.speed_factor
        time_min = length / (speed * 1000.0 / 60.0)
        # Physical segment id: both directions of a two-way road share it.
        a, b = np.minimum(u, v), np.maximum(u, v)
        ref = edges["source_ref"].astype(str).to_numpy() if "source_ref" in edges else np.full(len(edges), "")
        seg_key = pd.Series(list(zip(a, b, ref)))
        segment_id = pd.factorize(seg_key)[0]
        return cls(
            node_ids=nodes["node_id"].to_numpy(np.int64), x=np.asarray(x), y=np.asarray(y), lon=lon, lat=lat,
            u=u, v=v, length_m=length, road_class=road_class,
            edge_ids=edges["edge_id"].astype(str).to_numpy(object), segment_id=segment_id,
            speed_kph=speed, speed_source=np.where(posted_ok, "posted", "class_default").astype(object),
            time_min=time_min, walkable=~np.isin(road_class, list(NON_WALKABLE)),
            residential=np.isin(road_class, list(RESIDENTIAL_CLASSES)),
        )

    # ------------------------------------------------------------ properties
    @property
    def n_nodes(self) -> int:
        return len(self.node_ids)

    @property
    def n_edges(self) -> int:
        return len(self.u)

    def edge_index(self, edge_ids: Iterable[str]) -> np.ndarray:
        lookup = pd.Series(np.arange(self.n_edges), index=self.edge_ids)
        ids = list(edge_ids)
        unknown = [e for e in ids if e not in lookup.index]
        if unknown:
            raise KeyError(f"unknown edge ids: {unknown[:5]}")
        return lookup[ids].to_numpy()

    def closure_mask_for_segments(self, edge_mask: np.ndarray) -> np.ndarray:
        """Expand a closure so both directions of each closed segment close."""
        closed_segments = np.unique(self.segment_id[edge_mask])
        return np.isin(self.segment_id, closed_segments)

    # ---------------------------------------------------------------- graphs
    def _matrix(self, weights: np.ndarray, keep: np.ndarray, undirected: bool) -> sp.csr_matrix:
        u, v, w = self.u[keep], self.v[keep], weights[keep]
        if undirected:
            u, v, w = np.concatenate([u, v]), np.concatenate([v, u]), np.concatenate([w, w])
        # Parallel edges: keep the minimum weight (a CSR constructor would sum them).
        order = np.lexsort((w, v, u))
        u, v, w = u[order], v[order], w[order]
        first = np.ones(len(u), dtype=bool)
        first[1:] = (u[1:] != u[:-1]) | (v[1:] != v[:-1])
        u, v, w = u[first], v[first], w[first]
        # Zero-weight edges would be dropped as "no edge" by csgraph; use a tiny epsilon.
        w = np.maximum(w, 1e-9)
        return sp.csr_matrix((w, (u, v)), shape=(self.n_nodes, self.n_nodes))

    def drive_matrix(self, closed: np.ndarray | None = None) -> sp.csr_matrix:
        keep = np.ones(self.n_edges, bool) if closed is None else ~closed
        return self._matrix(self.time_min, keep, undirected=False)

    def drive_length_matrix(self, closed: np.ndarray | None = None) -> sp.csr_matrix:
        keep = np.ones(self.n_edges, bool) if closed is None else ~closed
        return self._matrix(self.length_m, keep, undirected=False)

    def walk_matrix(self, closed: np.ndarray | None = None) -> sp.csr_matrix:
        keep = self.walkable.copy() if closed is None else self.walkable & ~closed
        return self._matrix(self.length_m, keep, undirected=True)

    # --------------------------------------------------------------- snapping
    def nearest_node(self, x: np.ndarray, y: np.ndarray, walkable_only: bool = False) -> tuple[np.ndarray, np.ndarray]:
        """Nearest node (internal id) and distance in metres for projected points."""
        if walkable_only:
            if self._walk_kdtree is None:
                nodes = np.unique(np.concatenate([self.u[self.walkable], self.v[self.walkable]]))
                self._walk_nodes = nodes
                self._walk_kdtree = cKDTree(np.c_[self.x[nodes], self.y[nodes]])
            d, i = self._walk_kdtree.query(np.c_[x, y])
            return self._walk_nodes[i], d
        if self._kdtree is None:
            self._kdtree = cKDTree(np.c_[self.x, self.y])
        d, i = self._kdtree.query(np.c_[x, y])
        return i, d

    def speed_summary(self) -> dict[str, float]:
        posted = self.speed_source == "posted"
        return {
            "edges_with_posted_speed": int(posted.sum()),
            "share_edges_posted_speed": round(float(posted.mean()), 4),
            "share_length_posted_speed": round(float(self.length_m[posted].sum() / self.length_m.sum()), 4),
        }


# ------------------------------------------------------------------ queries
def travel_costs(
    matrix: sp.csr_matrix, sources: np.ndarray, limit: float = np.inf
) -> np.ndarray:
    """Costs from each source to every node (``inf`` = unreachable). Shape (S, N)."""
    if len(sources) == 0:
        return np.empty((0, matrix.shape[0]))
    return dijkstra(matrix, directed=True, indices=np.asarray(sources), limit=limit)


def costs_to_targets(matrix: sp.csr_matrix, targets: np.ndarray, limit: float = np.inf) -> np.ndarray:
    """Cost from every node TO each target (runs Dijkstra on the transposed
    graph, so |targets| searches instead of |origins|). Shape (T, N)."""
    return travel_costs(matrix.T.tocsr(), targets, limit)


def nearest_target(matrix: sp.csr_matrix, targets: np.ndarray, limit: float = np.inf) -> tuple[np.ndarray, np.ndarray]:
    """For every node: cost to its nearest target and that target's node id
    (``-9999`` if none reachable). One multi-source Dijkstra on the transpose."""
    if len(targets) == 0:
        n = matrix.shape[0]
        return np.full(n, np.inf), np.full(n, -9999)
    dist, _, src = dijkstra(
        matrix.T.tocsr(), directed=True, indices=np.asarray(targets), min_only=True,
        return_predecessors=True, limit=limit,
    )
    return dist, src


def shortest_path(matrix: sp.csr_matrix, source: int, target: int) -> tuple[float, list[int]]:
    """Single shortest path (internal ids). Returns (inf, []) if unreachable."""
    dist, pred = dijkstra(matrix, directed=True, indices=[source], return_predecessors=True)
    if not np.isfinite(dist[0, target]):
        return float("inf"), []
    path, node = [], target
    while node != -9999:
        path.append(int(node))
        if node == source:
            break
        node = pred[0, node]
    return float(dist[0, target]), path[::-1]


def component_stats(matrix: sp.csr_matrix) -> dict[str, int]:
    n_weak, weak_labels = connected_components(matrix, directed=True, connection="weak")
    n_strong, strong_labels = connected_components(matrix, directed=True, connection="strong")
    largest_strong = int(np.bincount(strong_labels).max()) if len(strong_labels) else 0
    largest_weak = int(np.bincount(weak_labels).max()) if len(weak_labels) else 0
    return {
        "weak_components": int(n_weak),
        "strong_components": int(n_strong),
        "largest_weak_component_nodes": largest_weak,
        "largest_strong_component_nodes": largest_strong,
        "nodes_outside_largest_weak_component": int(len(weak_labels) - largest_weak),
    }
