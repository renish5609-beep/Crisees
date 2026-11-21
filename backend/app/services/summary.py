"""Region-level summary computed from the processed datasets (never hardcoded)."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from app.core.errors import DatasetNotAvailableError
from app.datasets import utc_now
from app.regions import get_region
from app.schemas.summary import FacilitySummary, FloodSummary, PopulationSummary, RegionSummary, RoadSummary
from app.services.flood import flood_coverage
from app.services.repository import DataRepository
from app.services.roads import get_road_graph


def _sum(series: pd.Series) -> int | None:
    s = pd.to_numeric(series, errors="coerce")
    return int(s.sum()) if s.notna().any() else None


def _pct(num: int | None, den: int | None) -> float | None:
    if num is None or not den:
        return None
    return round(100.0 * num / den, 2)


def population_summary(repo: DataRepository, region_id: str) -> PopulationSummary:
    tracts = repo.load(region_id, "tracts")
    demo = repo.load(region_id, "demographics")
    # Only sum numerators over tracts where the matching denominator is present,
    # so percentages are internally consistent.
    def ratio(num: str, den: str) -> tuple[int | None, float | None]:
        ok = demo[num].notna() & demo[den].notna()
        n, d = _sum(demo.loc[ok, num]), _sum(demo.loc[ok, den])
        return _sum(demo[num]), _pct(n, d)

    nov, nov_pct = ratio("households_no_vehicle", "households_total")
    pov, pov_pct = ratio("population_below_poverty", "poverty_universe")
    old, old_pct = ratio("population_65_plus", "total_population")
    dis, dis_pct = ratio("population_with_disability", "disability_universe")
    # Count tracts missing any core indicator (fields unavailable for *every*
    # tract, such as a table that could not be retrieved, are reported in the
    # dataset notes instead).
    core = ["pct_households_no_vehicle", "pct_below_poverty", "pct_65_plus", "pct_with_disability"]
    missing = demo[core].isna().any(axis=1).sum()
    return PopulationSummary(
        tract_count=len(tracts),
        tracts_with_demographics=int(demo["total_population"].notna().sum()),
        total_population=_sum(demo["total_population"]),
        households_total=_sum(demo["households_total"]),
        households_no_vehicle=nov,
        pct_households_no_vehicle=nov_pct,
        population_below_poverty=pov,
        pct_below_poverty=pov_pct,
        population_65_plus=old,
        pct_65_plus=old_pct,
        population_with_disability=dis,
        pct_with_disability=dis_pct,
        tracts_with_missing_values=int(missing),
    )


def road_summary(repo: DataRepository, region_id: str) -> RoadSummary:
    edges = repo.load(region_id, "road_edges")
    G = get_road_graph(repo, region_id)
    by_class = (edges.groupby("road_class")["length_m"].sum() / 1000).round(2).sort_values(ascending=False)
    largest_scc = max((len(c) for c in nx.strongly_connected_components(G)), default=0)
    return RoadSummary(
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
        total_length_km=round(float(edges["length_m"].sum()) / 1000, 2),
        road_class_length_km={str(k): float(v) for k, v in by_class.items()},
        weakly_connected_components=nx.number_weakly_connected_components(G),
        largest_scc_node_fraction=round(largest_scc / max(G.number_of_nodes(), 1), 4),
        provider=repo.manifest_entry(region_id, "road_edges").get("provider"),
    )


def facility_summary(repo: DataRepository, region_id: str) -> FacilitySummary:
    fac = repo.load(region_id, "facilities")
    try:
        hubs = len(repo.load(region_id, "candidate_hubs"))
    except DatasetNotAvailableError:
        hubs = 0
    return FacilitySummary(
        facility_count=len(fac),
        by_category={str(k): int(v) for k, v in fac["category"].value_counts().items()},
        candidate_hub_count=hubs,
        authority_verified_shelters=int((fac["verification_status"] == "authority_verified").sum()),
    )


def flood_summary(repo: DataRepository, region_id: str) -> FloodSummary:
    region = get_region(region_id)
    fz = repo.load(region_id, "flood_hazards")
    proj = fz.to_crs(region.analysis_crs)
    area_by_zone = (proj.geometry.area.groupby(fz["flood_zone"].fillna("unknown")).sum() / 1e6).round(3)
    sfha = proj[fz["is_sfha"] == True]  # noqa: E712
    tracts_sfha = tracts_cov = None
    try:
        tracts = repo.load(region_id, "tracts").to_crs(region.analysis_crs)
        if len(sfha):
            hit = tracts.sindex.query(sfha.geometry.union_all(), predicate="intersects")
            tracts_sfha = len(set(hit.tolist()))
        else:
            tracts_sfha = 0
        try:
            cov = repo.load(region_id, "flood_coverage").to_crs(region.analysis_crs).geometry.union_all()
            tracts_cov = int((tracts.geometry.intersection(cov).area / tracts.geometry.area > 0.5).sum())
        except DatasetNotAvailableError:
            pass
    except DatasetNotAvailableError:
        pass
    coverage = flood_coverage(repo, region_id)
    return FloodSummary(
        polygon_count=len(fz),
        sfha_area_km2=round(float(sfha.geometry.area.sum()) / 1e6, 3),
        area_km2_by_zone={str(k): float(v) for k, v in area_by_zone.items()},
        covered_area_fraction=coverage.covered_area_fraction if coverage else None,
        dfirm_ids=coverage.dfirm_ids if coverage else sorted(fz["dfirm_id"].dropna().unique().tolist()),
        tracts_intersecting_sfha=tracts_sfha,
        tracts_in_covered_area=tracts_cov,
    )


_summary_cache: dict[str, tuple[str | None, RegionSummary]] = {}


def region_summary(repo: DataRepository, region_id: str) -> RegionSummary:
    """Cached per region until the pipeline rewrites the manifest."""
    stamp = (repo.manifest(region_id) or {}).get("generated_at")
    cached = _summary_cache.get(region_id)
    if cached and stamp is not None and cached[0] == stamp:
        return cached[1]
    result = _compute_summary(repo, region_id)
    _summary_cache[region_id] = (stamp, result)
    return result


def _compute_summary(repo: DataRepository, region_id: str) -> RegionSummary:
    region = get_region(region_id)
    unavailable: list[str] = []

    def attempt(fn, label):  # type: ignore[no-untyped-def]
        try:
            return fn(repo, region_id)
        except DatasetNotAvailableError as exc:
            unavailable.append(f"{label}: {exc.details.get('dataset')}")
            return None

    return RegionSummary(
        region_id=region.region_id,
        name=region.name,
        population=attempt(population_summary, "population"),
        roads=attempt(road_summary, "roads"),
        facilities=attempt(facility_summary, "facilities"),
        flood=attempt(flood_summary, "flood"),
        unavailable_datasets=unavailable,
        generated_at=utc_now(),
    )
