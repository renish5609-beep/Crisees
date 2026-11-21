"""Facility normalisation and candidate pickup-hub derivation.

No facility is marked as a designated evacuation shelter: open map data
cannot establish that. ``shelter`` here means a mapped *social* shelter
(e.g. homeless shelter, OSM ``social_facility=shelter``); OSM
``amenity=shelter`` features that are bus/picnic/weather shelters are dropped.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkb

logger = logging.getLogger(__name__)

# Overture taxonomy.primary -> Crisees FacilityCategory
OVERTURE_CATEGORY_MAP = {
    "hospital": "hospital", "childrens_hospital": "hospital", "specialty_hospital": "hospital",
    "psychiatric_hospital": "hospital", "emergency_department": "hospital",
    "primary_care_or_general_clinic": "clinic", "emergency_or_urgent_care_facility": "clinic",
    "community_health_center": "clinic", "urgent_care_clinic": "clinic",
    "community_center": "community_centre", "civic_center": "community_centre",
    "senior_citizen_service": "community_centre",
    "library": "library",
    "elementary_school": "school", "middle_school": "school", "high_school": "school",
    "public_school": "school",
    "fire_station": "fire_station",
    "police_station": "police",
    "town_hall": "townhall", "city_hall": "townhall",
    "homeless_shelter": "shelter", "emergency_shelter": "shelter",
    "social_service_organization": "social_facility",
}
OVERTURE_MIN_CONFIDENCE = 0.5

OSM_AMENITY_MAP = {
    "hospital": "hospital", "clinic": "clinic", "doctors": "clinic", "community_centre": "community_centre",
    "social_centre": "community_centre", "library": "library", "school": "school",
    "fire_station": "fire_station", "police": "police", "townhall": "townhall",
    "social_facility": "social_facility",
}

# Facilities typically public, with parking/frontage, suitable as *candidate* pickup hubs.
HUB_CATEGORIES = {
    "community_centre": "Public community/civic center: public access and parking typical",
    "library": "Public library: public access, known community landmark",
    "school": "School (elementary/middle/high): large parking and bus loading areas typical",
    "townhall": "Municipal building: public access",
}
HUB_MAX_SNAP_M = 300.0

FACILITY_COLUMNS = [
    "facility_id", "name", "category", "source_category", "lon", "lat", "address", "verification_status",
    "is_designated_evacuation_shelter", "source_id", "source_record_id", "confidence", "geometry",
]


def _frame(rows: list[dict], geoms: list) -> gpd.GeoDataFrame:
    gdf = gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms, crs=4326)
    if gdf.empty:
        return gpd.GeoDataFrame(columns=FACILITY_COLUMNS, geometry="geometry", crs=4326)
    gdf["lon"] = gdf.geometry.x.round(7)
    gdf["lat"] = gdf.geometry.y.round(7)
    gdf["verification_status"] = "mapped_unverified"
    gdf["is_designated_evacuation_shelter"] = None
    return gdf[FACILITY_COLUMNS]


def from_overture(path: Path, source_id: str) -> gpd.GeoDataFrame:
    df = pd.read_parquet(path)
    rows, geoms = [], []
    for r in df.itertuples(index=False):
        primary = r.taxonomy.get("primary") if isinstance(r.taxonomy, dict) else None
        cat = OVERTURE_CATEGORY_MAP.get(primary)
        if cat is None or r.operating_status == "permanently_closed":
            continue
        if r.confidence is not None and r.confidence < OVERTURE_MIN_CONFIDENCE:
            continue
        geom = wkb.loads(r.geometry)
        addr = None
        if r.addresses is not None and len(r.addresses):
            a = r.addresses[0]
            addr = ", ".join(x for x in [a.get("freeform"), a.get("locality"), a.get("postcode")] if x)
        rows.append(
            {
                "facility_id": f"ovt-{r.id}",
                "name": r.names.get("primary") if isinstance(r.names, dict) else None,
                "category": cat,
                "source_category": f"overture:{primary}",
                "address": addr,
                "source_id": source_id,
                "source_record_id": r.id,
                "confidence": round(float(r.confidence), 3) if r.confidence is not None else None,
            }
        )
        geoms.append(geom.centroid if geom.geom_type != "Point" else geom)
    return _frame(rows, geoms)


def from_osm(path: Path, source_id: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    rows, geoms = [], []
    for r in gdf.itertuples(index=False):
        amenity = getattr(r, "amenity", None)
        healthcare = getattr(r, "healthcare", None)
        social = getattr(r, "social_facility", None)
        if social == "shelter":
            cat, raw = "shelter", "social_facility=shelter"
        elif amenity == "shelter":
            # OSM amenity=shelter denotes weather/transit/picnic shelters, not
            # evacuation shelters; excluded regardless of shelter_type.
            continue
        elif amenity in OSM_AMENITY_MAP:
            cat, raw = OSM_AMENITY_MAP[amenity], f"amenity={amenity}"
        elif healthcare in ("hospital", "clinic"):
            cat, raw = healthcare, f"healthcare={healthcare}"
        else:
            continue
        parts = [getattr(r, "addr:housenumber", None), getattr(r, "addr:street", None),
                 getattr(r, "addr:city", None)]
        geom = r.geometry
        pt = geom if geom.geom_type == "Point" else geom.representative_point()
        rows.append(
            {
                "facility_id": f"osm-{r.element}-{r.id}",
                "name": getattr(r, "name", None),
                "category": cat,
                "source_category": raw,
                "address": ", ".join(str(p) for p in parts if p and str(p) != "nan") or None,
                "source_id": source_id,
                "source_record_id": f"{r.element}/{r.id}",
                "confidence": None,
            }
        )
        geoms.append(pt)
    return _frame(rows, geoms)


def clip_to(gdf: gpd.GeoDataFrame, area) -> gpd.GeoDataFrame:  # type: ignore[no-untyped-def]
    return gdf[gdf.within(area)].reset_index(drop=True)


def dedupe(gdf: gpd.GeoDataFrame, analysis_crs: str, tolerance_m: float = 25) -> gpd.GeoDataFrame:
    """Drop near-duplicate points of the same category and name (common in merged POI data)."""
    if gdf.empty:
        return gdf
    proj = gdf.to_crs(analysis_crs)
    key = proj["category"] + "|" + proj["name"].fillna("").str.lower().str.strip()
    proj["_cell"] = (proj.geometry.x // tolerance_m).astype(int).astype(str) + ":" + (
        proj.geometry.y // tolerance_m
    ).astype(int).astype(str)
    keep = ~(key + "|" + proj["_cell"]).duplicated()
    return gdf[keep.to_numpy()].reset_index(drop=True)


def derive_candidate_hubs(
    facilities: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame | None, analysis_crs: str
) -> gpd.GeoDataFrame:
    hubs = facilities[facilities["category"].isin(HUB_CATEGORIES)].copy()
    hubs["hub_id"] = "hub-" + hubs["facility_id"]
    hubs["candidacy_basis"] = hubs["category"].map(HUB_CATEGORIES)
    hubs["status"] = "candidate_unvalidated"
    hubs["nearest_node_id"] = pd.array([None] * len(hubs), dtype="Int64")
    hubs["snap_distance_m"] = float("nan")
    if nodes is not None and len(hubs) and len(nodes):
        hp = hubs.to_crs(analysis_crs)
        npj = nodes[["node_id", "geometry"]].to_crs(analysis_crs)
        joined = gpd.sjoin_nearest(hp, npj, how="left", distance_col="_dist")
        joined = joined[~joined.index.duplicated()]
        hubs["nearest_node_id"] = joined["node_id"].astype("Int64").to_numpy()
        hubs["snap_distance_m"] = joined["_dist"].round(1).to_numpy()
        far = hubs["snap_distance_m"] > HUB_MAX_SNAP_M
        hubs = hubs[~far]
    cols = ["hub_id", "facility_id", "name", "category", "lon", "lat", "candidacy_basis", "nearest_node_id",
            "snap_distance_m", "status", "geometry"]
    return gpd.GeoDataFrame(hubs[cols], geometry="geometry", crs=4326).reset_index(drop=True)
