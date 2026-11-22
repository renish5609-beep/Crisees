# API reference (v1)

Base URL (local): `http://localhost:8000`. Interactive OpenAPI docs: `/docs`; schema: `/openapi.json`.

- All geometries are GeoJSON, EPSG:4326, `[longitude, latitude]`.
- List endpoints are paginated with `limit` (default 500, capped at `CRISEES_MAX_PAGE_SIZE`, default 5000)
  and `offset`. Each response carries
  `page: {total, limit, offset, returned, next_offset}`. `next_offset` is null on the last page.
- Each data response carries `provenance` (`real`, `derived` or `synthetic`) and `sources[]`.
- Phase 1 data endpoints are `GET`. Phase 2 analysis endpoints are `POST` with JSON bodies. CORS allows
  `GET`, `POST` and `OPTIONS` from `CRISEES_CORS_ORIGINS`.

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
| 400 | `unknown_scenario_preset` / `unknown_edge_ids` | Bad scenario preset name or custom edge id |
| 404 | `scenario_not_found` | Closures requested for a scenario id that has not been evaluated |
| 422 | `optimization_failed` | Solver returned no solution (`details.status`, `solver_message`) |
| 503 | `engine_busy` | More than 2 concurrent analysis jobs; retry |

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

## Phase 2 analysis endpoints

These are CPU-bound. Handlers are synchronous `def` functions, which FastAPI runs in its worker
threadpool, so the event loop is never blocked. At most 2 jobs run concurrently (otherwise 503
`engine_busy`), solves are time-limited (≤ 120 s), and results are LRU-cached by a hash of the request and
the data stamp (`"cache": "hit" | "miss"`). All request models reject unknown fields and enforce the bounds
defined in `backend/app/engine/params.py`.

A `scenario` field accepts a preset name (`"baseline"`, `"moderate"`, `"severe"`) or a full `ScenarioSpec`:

```json
{"name": "custom", "seed": 2017, "one_pct_closure_prob": 0.8, "point_two_pct_closure_prob": 0.0,
 "min_exposed_m": 10, "overbank_buffer_m": 100, "overbank_closure_prob": 0.2,
 "unknown_coverage_policy": "no_inference", "unknown_closure_prob": 0.0,
 "custom_closed_edge_ids": ["<edge_id>", "..."]}
```

Shared parameter blocks (all optional; defaults shown by `GET /methodology`):

| Block | Fields |
| --- | --- |
| `demand` | `participation_rate` [0,1] = 0.5, `persons_in_4plus_households` [4,8] = 4.5, `origin_cell_m` [200,2000] = 500 |
| `weights` | `mode` `equity`\|`equal`, `beta_poverty` = 0.5, `beta_disability` = 0.5, `beta_age65` = 0 |
| `access` | `walk_max_m` [100,2000] = 800, `drive_thresholds_min` = [10,20,30], `shelter_categories` = ["community_centre"], `exclude_shelters_in_1pct_zone` = true |
| `resources` | `max_active_hubs` = 12, `vehicles` = 15, `vehicle_capacity` = 40, `horizon_min` = 480, `dwell_min` = 10, `hub_capacity` = 600, `shelter_capacity` = 400, `shelters_per_hub` = 4 |
| `solver` | `time_limit_s` (0,120] = 30, `mip_rel_gap` = 0.005, `integer_trips` = true, `walk_cost_weight` = 0.01, `drive_cost_weight` = 0.01, `hub_activation_cost` = 0.1 |

### `GET /api/v1/regions/{id}/scenarios`
Presets: `[{name, description, spec}]`.

### `POST /api/v1/regions/{id}/scenarios/evaluate`
Body: `{scenario, access?, include_closures_geojson? (≤ 2000 features)}`. Response (`ScenarioEvaluation`):

- `scenario_id` (`scn_` + 16 hex digits, deterministic)
- `closures`: `{closed_directed_edges, closed_segments, closed_length_km, closed_segments_by_rule,
  unknown_coverage_segments, unknown_coverage_length_km, unknown_coverage_policy}`
- `network`: `{baseline, scenario}` component statistics
- `access_change`: origins and demand losing drive routes, mean and p90 drive-time change, shelters
  reachable within the threshold, hubs with a shelter route
- `speed_model`, `timings_s`, `provenance`, `disclaimer`

### `GET /api/v1/regions/{id}/scenarios/{scenario_id}/closures?limit&offset`
GeoJSON of closed segments (one feature per segment, both directions closed), `evidence_type: simulated`.
The scenario must have been evaluated in this server process (404 otherwise).

### `POST /api/v1/regions/{id}/accessibility/analyze`
Body: `{scenario, demand?, access?, include_geometry? = true, simplify_m? = 20}`. Response: a GeoJSON
FeatureCollection of tracts, plus `summary` (baseline vs scenario demand-weighted shares, disconnected
tracts, access-loss totals), `units` and `method_notes`. Per-tract properties are listed in
ACCESSIBILITY_METHODS.md. Unreachable values are `null`.

### `POST /api/v1/regions/{id}/demand`
Body: `{params?: DemandParams, weights?: EquityWeights}`. Returns per-tract observed counts, estimated
persons and demand, ranks and weights, a 4×3 sensitivity grid, and definitions separating observed,
estimated and priority fields.

### `POST /api/v1/regions/{id}/optimize`
Body: `OptimizeRequest {scenario, demand, weights, access, resources, solver, include_geometry}`.
Response (`OptimizationResult`):

- `totals`: `demand_est, served, served_via_hubs, served_by_direct_walk_to_shelter, unmet, coverage,
  weighted_unmet_run_weights, weighted_unmet_equity_weights, weighted_coverage_equity_weights, active_hubs,
  vehicle_trips, vehicle_minutes_used/available, fleet_utilization, mean_walk_m_served_via_hub,
  mean_bus_drive_min, mean_seat_occupancy`
- `binding_constraints`: hub budget, hubs and shelters at capacity, fleet binding, demand with no walkable
  hub or shelter
- `distribution_by_priority_tercile`: `tercile_1` (lowest priority) to `tercile_3`, each with demand,
  served and coverage
- `hubs[]`: activated hubs with `legs[] {shelter_id, persons, trips, drive_min, round_trip_min}`
- `shelters[]`, `tracts[]`, `tracts_geojson`, `hubs_geojson`
- `solver`: `{status, mip_gap, dual_bound, objective, solve_seconds, model_size, screening,
  optimality_claim}`
- `constraint_check`: independent recomputation of every constraint
- `assumptions`, `disclaimer`

### `POST /api/v1/regions/{id}/compare`
Body: `CompareRequest {disrupted_scenario, demand, weights, access, resources, solver,
include_robustness_case}`. Response: `cases[]`:

- `baseline_no_intervention`
- `disrupted_no_intervention`
- `disrupted_equity_optimized`
- `disrupted_equal_weight_optimized`
- `baseline_plan_under_disruption` (optional)

Each case has totals, terciles, binding constraints, solver status and active hub ids. The response also
includes `deltas` (exact differences), `findings` (generated text that reports a zero gain as zero),
`accessibility_change`, `most_affected_tracts` and `identical_inputs`.

### `GET /api/v1/regions/{id}/methodology`
Units, speed table, every default, scenario presets, the objective and constraint list, and the
equity-weight formula.

### `GET /api/v1/regions/{id}/demo`
The reproducible demonstration: `{title, story[], request, reproduce, result: ComparisonResult}`. See
PHASE2_RESULTS.md.

### Map layer endpoints (Phase 3, read-only)

| Endpoint | Returns |
| --- | --- |
| `GET /api/v1/regions/{id}/layers/context-roads` | Major roads merged by name and class, simplified (about 430 features), as a self-hosted basemap substitute |
| `GET /api/v1/regions/{id}/layers/flood-coverage` | FeatureCollection with `kind` = `study_area`, `fema_covered` (per DFIRM) or `no_fema_data` (study area minus coverage: hazard unknown), plus `covered_area_fraction` |
| `GET /api/v1/regions/{id}/layers/planning-sites` | `{shelters, hubs}` FeatureCollections exactly as the engine uses them (assumed shelters excluding 1% zones; candidate hubs excluding shelter facilities), each with `flood_status` |

`GET /scenarios/{scenario_id}/closures` also resolves preset scenario ids after a server restart.

## Stability for Phase 2

Paths, parameter names and response field names under `/api/v1` are the contract for Phase 2 and Phase 3. New fields may
be added. Breaking changes require `/api/v2`.
