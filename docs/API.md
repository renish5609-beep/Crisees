# API reference (v1)

Base URL (local): `http://localhost:8000`. Interactive OpenAPI docs: `/docs`; schema: `/openapi.json`.

- All geometries are GeoJSON, EPSG:4326, `[longitude, latitude]`.
- List endpoints are paginated with `limit` (default 500, capped at `CRISEES_MAX_PAGE_SIZE`, default 5000)
  and `offset`. Each response carries
  `page: {total, limit, offset, returned, next_offset}`. `next_offset` is null on the last page.
- Each data response carries `provenance` (`real`, `derived` or `synthetic`) and `sources[]`.
- The API is read-only (`GET`). CORS allows the origins in `CRISEES_CORS_ORIGINS`.

## Errors

Every error has the same shape:

```json
{"error": {"code": "dataset_not_available", "message": "...", "details": {"dataset": "tracts", "hint": "Run ..."}}}
```

| HTTP | code | When |
| --- | --- | --- |
| 400 | `bad_request` | Malformed `bbox`, unknown facility category |
| 404 | `region_not_found` | Unknown `region_id` (`details.available` lists valid ids) |
| 422 | `validation_error` | Parameter type or pattern violations (`details.errors`) |
| 500 | `dataset_corrupt` | Processed file unreadable or missing required columns |
| 503 | `dataset_not_available` | Dataset not yet downloaded or processed. `details.hint` gives the commands |

The API never substitutes fabricated values for missing data.

## Endpoints

### `GET /health`
Liveness check: `{status, version, environment, time, data_dir_exists, regions_configured, regions_with_processed_data}`.

### `GET /api/v1/regions`
All configured regions as `GeographicRegion`, including `datasets[]` status (state, record count,
provenance, provider, sources, notes).

### `GET /api/v1/regions/{region_id}`
One region. `GET /api/v1/regions/{region_id}/datasets` returns just the dataset inventory.

### `GET /api/v1/regions/{region_id}/tracts`
FeatureCollection of `CensusTract`.

| Param | Description |
| --- | --- |
| `include_geometry` | `true` (default) / `false` |
| `county_fips` | 3-digit county filter, e.g. `201` |
| `simplify_m` | Douglas–Peucker tolerance in metres (0 < x ≤ 500), for lighter map payloads |

### `GET /api/v1/regions/{region_id}/demographics`
`RecordPage` of `{demographics: DemographicIndicators, vulnerability: VulnerabilityIndicators | null}`.

| Param | Description |
| --- | --- |
| `geoid` | 11-digit GEOID filter |
| `include_vulnerability` | Join SVI fields (default `true`). If SVI is unavailable, `vulnerability` is null |

### `GET /api/v1/regions/{region_id}/roads`
FeatureCollection of `RoadEdge` (default) or `RoadNode`.

| Param | Description |
| --- | --- |
| `layer` | `edges` (default) or `nodes` |
| `bbox` | `west,south,east,north` spatial filter |
| `road_class` | Comma-separated OSM highway classes, e.g. `motorway,primary` |

To get the full routing graph in Python, use
`app.services.roads.get_road_graph(repo, region_id)` rather than paging through 200,000 edges.

### `GET /api/v1/regions/{region_id}/facilities`
FeatureCollection of `EmergencyFacility`. `category` is a comma-separated filter over
shelter, hospital, clinic, community_centre, library, school, fire_station, police, townhall,
social_facility.

### `GET /api/v1/regions/{region_id}/candidate-hubs`
FeatureCollection of `CandidatePickupHub` (derived, unvalidated).

### `GET /api/v1/regions/{region_id}/flood-hazards`
FeatureCollection of `FloodHazardArea`, plus `coverage: {covered_area_fraction, dfirm_ids, method}` and a
`disclaimer`.

| Param | Description |
| --- | --- |
| `sfha_only` | Only Special Flood Hazard Areas (1% annual chance) |
| `zone` | Comma-separated FEMA zones, e.g. `AE,A` |
| `simplify_m` | Simplification tolerance in metres |

### `GET /api/v1/regions/{region_id}/summary`
`RegionSummary`, computed from the processed datasets on request and cached until the pipeline reruns.
It contains population totals and consistent ratios, road network statistics (connectivity, length by
class), facility counts and flood statistics (SFHA area, tracts touching the SFHA, coverage).
Sections whose datasets are missing are `null` and listed in `unavailable_datasets`.

## Examples (real pilot data)

```bash
curl -s localhost:8000/api/v1/regions/houston-sw-pilot/summary | jq '.population'
```

```json
{
  "tract_count": 151, "tracts_with_demographics": 151, "total_population": 585584,
  "households_total": 209463, "households_no_vehicle": 21981, "pct_households_no_vehicle": 10.49,
  "population_below_poverty": 111918, "pct_below_poverty": 19.24, "population_65_plus": 82217,
  "pct_65_plus": 14.04, "population_with_disability": 65828, "pct_with_disability": 11.28,
  "tracts_with_missing_values": 0,
  "note": "Sums of ACS tract estimates; aggregate MOEs are not computed in Phase 1."
}
```

```bash
curl -s 'localhost:8000/api/v1/regions/houston-sw-pilot/roads?road_class=motorway&limit=1' | jq '.features[0].properties'
curl -s 'localhost:8000/api/v1/regions/houston-sw-pilot/facilities?category=library,community_centre'
curl -s 'localhost:8000/api/v1/regions/houston-sw-pilot/flood-hazards?sfha_only=true&simplify_m=10' | jq '.coverage'
```

## Stability for Phase 2

Paths, parameter names and response field names under `/api/v1` are the Phase 2 contract. New fields may
be added. Breaking changes require `/api/v2`.
