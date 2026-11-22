"""Lightweight read-only map layers for the frontend (no new algorithms).

* context roads: major roads merged by name/class, simplified, one direction
  per segment, as a self-hosted basemap substitute;
* flood coverage: ingested FEMA coverage, plus the explicit 'no FEMA data'
  remainder of the study area, so unknown hazard is drawn distinctly;
* planning sites: the assumed shelters and eligible candidate hubs exactly
  as the engine uses them, with flood status.
"""

from __future__ import annotations

import threading

import geopandas as gpd
import pandas as pd
from shapely.ops import linemerge

from app.engine.context import get_engine
from app.engine.params import AccessParams
from app.services.repository import DataRepository
from app.services.serialization import clean_value, geometry_to_geojson

CONTEXT_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary"]
_cache: dict[tuple[str, str, str], dict] = {}
_lock = threading.Lock()


def _memo(repo: DataRepository, region_id: str, kind: str, fn):  # type: ignore[no-untyped-def]
    stamp = (repo.manifest(region_id) or {}).get("generated_at", "none")
    key = (str(repo.settings.processed_dir), region_id, f"{kind}|{stamp}")
    with _lock:
        if key in _cache:
            return _cache[key]
    value = fn()
    with _lock:
        _cache[key] = value
    return value


def context_roads(repo: DataRepository, region_id: str) -> dict:
    def build() -> dict:
        eng = get_engine(repo, region_id)
        edges = repo.load(region_id, "road_edges")
        e = edges[edges["road_class"].str.replace("_link", "", regex=False).isin(CONTEXT_CLASSES)]
        # One direction per physical segment.
        seg = pd.Series(eng.net.segment_id, index=edges.index).loc[e.index]
        e = e.loc[~seg.duplicated().to_numpy()]
        proj = e.to_crs(eng.region.analysis_crs)
        proj["base"] = proj["road_class"].str.replace("_link", "", regex=False)
        proj["name"] = proj["name"].fillna("")
        rows, geoms = [], []
        for (cls, name), grp in proj.groupby(["base", "name"]):
            merged = linemerge(list(grp.geometry))
            rows.append({"road_class": cls, "name": name or None})
            geoms.append(merged.simplify(8))
        out = gpd.GeoDataFrame(rows, geometry=geoms, crs=eng.region.analysis_crs).to_crs(4326)
        feats = [{"type": "Feature", "geometry": geometry_to_geojson(g, precision=5), "properties": p}
                 for p, g in zip(rows, out.geometry)]
        return {"type": "FeatureCollection", "features": feats, "provenance": "derived",
                "note": "Major roads (OSM-derived) merged by name and class for map context; not routing data."}

    return _memo(repo, region_id, "context_roads", build)


def flood_coverage(repo: DataRepository, region_id: str) -> dict:
    def build() -> dict:
        eng = get_engine(repo, region_id)
        crs = eng.region.analysis_crs
        sa = repo.load(region_id, "study_area").to_crs(crs).geometry.iloc[0]
        feats = [{"type": "Feature", "id": "study_area", "geometry": geometry_to_geojson(
            gpd.GeoSeries([sa.simplify(10)], crs=crs).to_crs(4326).iloc[0], 5),
            "properties": {"kind": "study_area"}}]
        try:
            cov = repo.load(region_id, "flood_coverage").to_crs(crs)
            covered = cov.geometry.union_all() if len(cov) else None
        except Exception:  # noqa: BLE001 - coverage missing => everything unknown
            cov, covered = None, None
        unknown = sa if covered is None else sa.difference(covered)
        if covered is not None:
            for row in cov.itertuples():
                g = gpd.GeoSeries([row.geometry.simplify(10)], crs=crs).to_crs(4326).iloc[0]
                feats.append({"type": "Feature", "id": f"covered-{row.dfirm_id}", "geometry": geometry_to_geojson(g, 5),
                              "properties": {"kind": "fema_covered", "dfirm_id": row.dfirm_id}})
        if not unknown.is_empty:
            g = gpd.GeoSeries([unknown.simplify(10)], crs=crs).to_crs(4326).iloc[0]
            feats.append({"type": "Feature", "id": "no_fema_data", "geometry": geometry_to_geojson(g, 5),
                          "properties": {"kind": "no_fema_data",
                                         "note": "No FEMA flood data ingested: hazard UNKNOWN, not zero."}})
        frac = 1 - unknown.area / sa.area if sa.area else None
        return {"type": "FeatureCollection", "features": feats,
                "covered_area_fraction": round(frac, 4) if frac is not None else None, "provenance": "derived"}

    return _memo(repo, region_id, "flood_coverage", build)


def planning_sites(repo: DataRepository, region_id: str) -> dict:
    def build() -> dict:
        eng = get_engine(repo, region_id)
        dest = eng.destinations(AccessParams())

        def fc(df: pd.DataFrame, kind: str, id_col: str) -> dict:
            feats = []
            for r in df.to_dict("records"):
                props = {k: clean_value(v) for k, v in r.items() if k not in ("node", "walk_node", "lon", "lat")}
                props["kind"] = kind
                feats.append({"type": "Feature", "id": r[id_col],
                              "geometry": {"type": "Point", "coordinates": [round(r["lon"], 6), round(r["lat"], 6)]},
                              "properties": props})
            return {"type": "FeatureCollection", "features": feats}

        return {
            "shelters": fc(dest.shelters, "assumed_shelter", "facility_id"),
            "hubs": fc(dest.hubs, "candidate_hub", "hub_id"),
            "excluded_shelters": dest.excluded_shelters.to_dict("records"),
            "notes": ["Assumed shelters = mapped community centres (HYPOTHETICAL); none is a verified evacuation shelter.",
                      "Candidate hubs are unvalidated; schools and private properties require owner authorization."],
        }

    return _memo(repo, region_id, "planning_sites", build)
