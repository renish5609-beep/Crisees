"""Per-region engine context: loads Phase 1 datasets once, builds the routing
network and derived inputs, and caches them until the pipeline reruns."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd

from app.core.errors import DatasetNotAvailableError
from app.engine.demand import Origins, build_origins
from app.engine.network import RoadNetwork
from app.engine.params import AccessParams
from app.regions import RegionDefinition, get_region
from app.services.repository import DataRepository

logger = logging.getLogger(__name__)

REQUIRED = ("tracts", "demographics", "vehicle_access", "road_nodes", "road_edges", "facilities",
            "candidate_hubs", "edge_flood_exposure")


@dataclass
class Destinations:
    """Facilities used in a run, with internal network node ids."""

    shelters: pd.DataFrame  # facility_id, name, category, lon, lat, node, snap_m, flood_status
    hubs: pd.DataFrame  # hub_id, facility_id, name, category, lon, lat, node, snap_m, flood_status
    excluded_shelters: pd.DataFrame


@dataclass
class RegionEngine:
    region: RegionDefinition
    stamp: str
    tracts: gpd.GeoDataFrame
    demographics: pd.DataFrame
    vulnerability: pd.DataFrame | None
    vehicle_access: pd.DataFrame
    facilities: gpd.GeoDataFrame
    hubs: gpd.GeoDataFrame
    net: RoadNetwork
    exposure: pd.DataFrame  # aligned with net edges
    has_flood_data: bool
    build_seconds: float
    _origins: dict[float, Origins] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def origins(self, cell_m: float) -> Origins:
        with self._lock:
            if cell_m not in self._origins:
                self._origins[cell_m] = build_origins(self.tracts, self.net, self.region.analysis_crs, cell_m)
            return self._origins[cell_m]

    def _flood_status(self, gdf: gpd.GeoDataFrame) -> np.ndarray:
        """'in_1pct_zone' | 'mapped_outside_1pct' | 'unknown_no_fema_data' for points."""
        status = np.full(len(gdf), "unknown_no_fema_data", dtype=object)
        if not self.has_flood_data or len(gdf) == 0:
            return status
        crs = self.region.analysis_crs
        pts = gdf.to_crs(crs)
        cov, hz = self._flood_layers
        if cov is not None:
            status[pts.within(cov).to_numpy()] = "mapped_outside_1pct"
        if hz is not None:
            status[pts.within(hz).to_numpy()] = "in_1pct_zone"
        return status

    @property
    def _flood_layers(self):  # type: ignore[no-untyped-def]
        if not hasattr(self, "_fl"):
            crs = self.region.analysis_crs
            repo_cov, repo_hz = self._cov_gdf, self._hz_gdf
            cov = repo_cov.to_crs(crs).union_all() if repo_cov is not None and len(repo_cov) else None
            one = repo_hz[repo_hz["annual_chance_category"] == "1pct"] if repo_hz is not None else None
            hz = one.to_crs(crs).union_all() if one is not None and len(one) else None
            self._fl = (cov, hz)
        return self._fl

    def destinations(self, access: AccessParams) -> Destinations:
        crs = self.region.analysis_crs
        cats = [c.value for c in access.shelter_categories]
        shel = self.facilities[self.facilities["category"].isin(cats)].copy()
        shel["flood_status"] = self._flood_status(shel)
        excluded = shel.iloc[0:0]
        if access.exclude_shelters_in_1pct_zone:
            excluded = shel[shel["flood_status"] == "in_1pct_zone"]
            shel = shel[shel["flood_status"] != "in_1pct_zone"]
        hubs = self.hubs[~self.hubs["facility_id"].isin(shel["facility_id"])].copy()
        hubs["flood_status"] = self._flood_status(hubs)
        for df in (shel, hubs):
            p = df.to_crs(crs)
            node, d = self.net.nearest_node(p.geometry.x.to_numpy(), p.geometry.y.to_numpy())
            df["node"], df["snap_m"] = node, d.round(1)
            node_w, d_w = self.net.nearest_node(p.geometry.x.to_numpy(), p.geometry.y.to_numpy(), walkable_only=True)
            df["walk_node"], df["walk_snap_m"] = node_w, d_w.round(1)
        keep_s = ["facility_id", "name", "category", "lon", "lat", "node", "walk_node", "snap_m", "flood_status"]
        keep_h = ["hub_id", "facility_id", "name", "category", "lon", "lat", "node", "walk_node", "snap_m",
                  "flood_status"]
        return Destinations(
            shelters=pd.DataFrame(shel[keep_s]).sort_values("facility_id").reset_index(drop=True),
            hubs=pd.DataFrame(hubs[keep_h]).sort_values("hub_id").reset_index(drop=True),
            excluded_shelters=pd.DataFrame(excluded[["facility_id", "name", "flood_status"]]),
        )


_engines: dict[str, RegionEngine] = {}
_engine_lock = threading.Lock()


def get_engine(repo: DataRepository, region_id: str) -> RegionEngine:
    region = get_region(region_id)
    manifest = repo.manifest(region_id) or {}
    stamp = manifest.get("generated_at") or "none"
    cache_key = f"{repo.settings.processed_dir}|{region_id}"
    with _engine_lock:
        eng = _engines.get(cache_key)
        if eng is not None and eng.stamp == stamp:
            return eng
        t0 = time.perf_counter()
        data = {k: repo.load(region_id, k) for k in REQUIRED}  # raises DatasetNotAvailableError (503)
        try:
            vuln = repo.load(region_id, "vulnerability")
        except DatasetNotAvailableError:
            vuln = None
        try:
            hz, cov = repo.load(region_id, "flood_hazards"), repo.load(region_id, "flood_coverage")
        except DatasetNotAvailableError:
            hz = cov = None
        edges = data["road_edges"]
        net = RoadNetwork.from_tables(data["road_nodes"], edges, region.analysis_crs)
        exp = data["edge_flood_exposure"].set_index("edge_id").reindex(edges["edge_id"]).reset_index()
        if exp["length_m"].isna().any():
            raise DatasetNotAvailableError(
                "edge_flood_exposure is out of date relative to road_edges.", dataset="edge_flood_exposure",
                region_id=region_id, hint="Run `python scripts/process_data.py --only derived`.",
            )
        eng = RegionEngine(
            region=region, stamp=stamp, tracts=data["tracts"], demographics=data["demographics"],
            vulnerability=vuln, vehicle_access=data["vehicle_access"], facilities=data["facilities"],
            hubs=data["candidate_hubs"], net=net, exposure=exp, has_flood_data=hz is not None,
            build_seconds=0.0,
        )
        eng._hz_gdf, eng._cov_gdf = hz, cov  # type: ignore[attr-defined]
        eng.build_seconds = round(time.perf_counter() - t0, 3)
        logger.info("engine context for %s built in %.2fs", region_id, eng.build_seconds)
        _engines[cache_key] = eng
        return eng


def clear_engines() -> None:
    with _engine_lock:
        _engines.clear()
