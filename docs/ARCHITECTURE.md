# Architecture

```
                 ┌─────────────────────────── scripts/ ───────────────────────────┐
 public sources  │ download_data.py ─► pipeline.sources.*  (providers + fallbacks)│
 Census, CDC,    │        │  data/raw/…  + .source.json provenance sidecars         │
 FEMA, OSM,      │ process_data.py  ─► pipeline.processing.* ─► data/processed/   │
 Overture ──────►│ validate_data.py ─► pipeline.validate      (GeoParquet+manifest)│
                 └────────────────────────────────┬───────────────────────────────┘
                                                  │ app.datasets (file contract)
                 ┌───────────── backend/app (FastAPI) ─────────────┐
                 │ services.repository  (mtime-cached loads, 503s) │
                 │ services.{geography,demographics,roads,         │
                 │          facilities,flood,summary,road_graph}   │
                 │ api.v1.routes.regions  ── /api/v1/...           │
                 └───────────────────────┬─────────────────────────┘
                                         │ JSON / GeoJSON (EPSG:4326)
                 ┌───────────── frontend (Next.js) ────────────────┐
                 │ lib/api.ts client · StatusBar health · /data    │
                 └─────────────────────────────────────────────────┘
```

## Principles

1. **Real data or no data.** Every value traces to a source recorded in a sidecar and the manifest.
   Missing data gives a 503 or a null, never a fabricated number. Synthetic data lives only in
   `backend/tests/fixtures/` and is labeled `provenance: synthetic`.
2. **One file contract.** `backend/app/datasets.py` names every processed file and its required columns.
   The pipeline writes it, the API reads it, the validator enforces it. Phase 2 reads the same files.
3. **Region-agnostic.** A region is a JSON definition (counties, selection bbox, analysis CRS, vintages).
   State-level downloads are shared across regions in `data/raw/shared/state-<fips>/`.
4. **Providers with fallbacks.** Each source module tries providers in order (official first) and records
   which one succeeded. Swapping providers changes neither the schema nor the API.
5. **Explicit evidence types.** FEMA regulatory zones, observed flooding and simulated closures are
   separate concepts (`HazardEvidenceType`). Mapped facilities are never treated as designated shelters.

## Backend layout

```
backend/app/
  main.py               app factory: CORS, gzip, request logging, error handlers
  core/config.py        Settings (env prefix CRISEES_), paths
  core/errors.py        CriseesError hierarchy → {"error": {code, message, details}}
  core/logging.py
  regions/              RegionDefinition + definitions/*.json registry
  datasets.py           processed-file contract + manifest helpers
  schemas/              Pydantic models: common (Provenance, SourceAttribution, GeoJSON generics,
                        pagination), region, census, roads, facilities, flood, summary
  services/             repository, serialization, geography, demographics, roads, road_graph,
                        facilities, flood, summary
  api/                  deps (repo, pagination), health, v1/routes/regions.py
backend/pipeline/
  http.py               retrying session, atomic idempotent downloads, content guards, ArcGIS paging
  context.py            per-region paths
  sources/              tiger, acs, svi, fema, roads (osmnx|overture), facilities (osm|overture),
                        overture (S3 bbox reader), catalog (attribution)
  processing/           geoid, tracts, demographics, svi, flood, roads, facilities
  run.py                download / process orchestration, manifest writing
  validate.py           contract checks
backend/tests/          97 tests; synthetic fixture; opt-in real-data checks
```

## Coordinate reference systems

| Purpose | CRS |
| --- | --- |
| Storage, API, frontend | EPSG:4326, GeoJSON [lon, lat] |
| Lengths, areas, buffers, nearest-node snapping | Region `analysis_crs` (EPSG:32615, UTM 15N, metres) |
| TIGER native | EPSG:4269 (NAD83), converted on ingest |
| ArcGIS queries | Requested with `outSR=4326` |

## Road graph

`road_nodes` and `road_edges` flatten an OSMnx-style `MultiDiGraph`. `tables_to_graph` rebuilds it
losslessly; `get_road_graph(repo, region)` returns a cached instance. OSMnx and NetworkX routines work
on it directly (`ox.graph_to_gdfs`, `ox.routing.shortest_path`, `nx.shortest_path(..., weight="length")`).

## Frontend (Phase 3)

```
src/app/page.tsx            map-first workspace: Overview, Scenario Lab, Accessibility, Planner, Impact, guided demo
src/app/methodology/        data sources, live dataset status, model formulation, limitations
src/components/map/         CriseesMap (MapLibre GL, canvas-generated patterns, no external sprites or glyphs)
src/components/panels/      one panel per view plus TractInspector and MapControls
src/lib/api.ts              typed client: timeouts (150 s for analysis), AbortSignal, zod runtime checks, ApiError
src/lib/store.tsx           WorkspaceProvider: draft parameters (URL-persisted) and result slots with keys; latest-request-wins
src/lib/params.ts           defaults and bounds mirroring backend params.py; URL encoding; validation
```

Results are displayed only after the corresponding API call succeeds. Each result slot records the
parameter key it was computed for, and the UI flags stale results when inputs change. Chart-heavy panels
and the map are lazy-loaded (first-load JS for `/` is about 135 kB).

## Frontend (Phase 1, superseded)

Next.js 15 App Router, TypeScript and Tailwind v4, with the Public Sans typeface (self-hosted through
`@fontsource`). Phase 1 scope is limited to:

- **App shell.** Left navigation rail with placeholders for Phase 2 and 3 sections, and a top status bar
  that polls `/health` every 15 seconds.
- **Workspace (`/`).** A map-ready panel. As a preview, it renders the real tract outlines and FEMA SFHA
  polygons as SVG through a local equirectangular projection. It also shows the region summary inspector.
  Phase 3 replaces the SVG with an interactive web map that consumes the same GeoJSON endpoints.
- **Data status (`/data`).** The dataset inventory with sources, provenance and caveats.
- **`src/lib/api.ts`.** A typed client with timeouts and structured `ApiError`s. `src/lib/types.ts`
  mirrors the backend schemas.

## Phase 2 analysis engine (`backend/app/engine/`)

```
params.py         bounded request models (scenario, demand, weights, access, resources, solver)
network.py        Engine A: immutable array graph, CSR matrices per closure mask, SciPy Dijkstra
demand.py         Engine B: zero-vehicle demand, sub-tract origins, priority weights, sensitivity
context.py        per-region cache: datasets, network, origins, shelter/hub sets with flood status
scenarios.py      Engine C: deterministic hypothetical closures, presets, scenario ids
accessibility.py  Engine D: cached scenario states (walk/drive matrices), tract metrics, deltas
optimization.py   Engine E: MILP (HiGHS via scipy.optimize.milp) + independent constraint verification
service.py        Engine F (compare) + payload shaping, LRU result cache, job limiter, demo
api/v1/routes/analysis.py   POST endpoints (sync handlers run in the threadpool)
```

Data flow: the Phase 1 datasets plus `vehicle_access` and `edge_flood_exposure` (the pipeline step
`derived`) feed `RegionEngine` (built once, about 1 s). A scenario spec yields a closure mask, which yields
a `ScenarioState` with walk and drive matrices (cached per scenario and access parameters, 1–1.5 s). That
state feeds accessibility tables and the MILP inputs; solving takes under 1 s, and verification follows.
`compare` runs up to 5 solves with identical inputs.

Caches are keyed by the data stamp (`manifest.generated_at`), so rerunning the pipeline invalidates them.
Methods and numbers are documented in OPTIMIZATION_MODEL.md, SCENARIO_ENGINE.md, ACCESSIBILITY_METHODS.md
and PHASE2_RESULTS.md.

## How Phase 3 should consume the engine

- Map layers:
  - tracts: `POST /accessibility/analyze` (FeatureCollection with baseline, scenario and delta properties);
  - closures: `GET /scenarios/{id}/closures`;
  - hubs: `hubs_geojson` from `/optimize`;
  - flood zones and coverage: `GET /flood-hazards`.
- Scenario picker: `GET /scenarios`. Use custom specs for sliders; every result carries a deterministic
  `scenario_id`.
- Resource sliders: `POST /optimize` (about 0.6–1 s warm). Show `solver.status`, `optimality_claim`,
  `binding_constraints` and `constraint_check.feasible`.
- Before/after story: `GET /demo` or `POST /compare`. Always display the `disclaimer` and the FEMA coverage
  caveat.

## How Phase 2 consumed the Phase 1 data (historical)

1. Load data through `DataRepository` (or directly with `geopandas.read_parquet` from
   `data/processed/<region>/`), and check `manifest.json` provenance and coverage before you trust a dataset.
2. Get the routing graph with `get_road_graph(repo, region_id)`. Edge `length` is in metres. There are no
   imputed speeds. To add travel times, use `osmnx.routing.add_edge_speeds` / `add_edge_travel_times` and
   record the result as a derived dataset.
3. Origins: tract population-weighted points (Phase 2 should add block-group or block points). Demand
   inputs: `households_no_vehicle`, `population_65_plus` and `population_with_disability`, with their MOEs.
4. Destinations: `facilities` (hospitals, social shelters) and `candidate_hubs`, using `nearest_node_id`.
5. Flood disruption: intersect `road_edges` with `flood_hazards` in EPSG:32615 to produce **simulated**
   closures, stored as a new dataset with `evidence_type = simulated`. Never overwrite FEMA data. Treat
   edges outside `flood_coverage` as having unknown hazard.
6. Vulnerability weighting: build it in Phase 2 from preserved variables. Document the weights and avoid
   double counting SVI and ACS overlaps (vehicle access, age, disability, poverty).
7. New outputs go through the same pattern: add a `DatasetSpec`, write with provenance `derived`, extend
   the validator, and expose them under `/api/v1/regions/{id}/...`.
