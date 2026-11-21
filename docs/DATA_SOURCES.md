# Data sources

Every Crisees dataset comes from a public source. This file records what was used, how it was retrieved,
under which license, and what it cannot tell you. The same metadata is kept in machine-readable form in
`backend/pipeline/sources/catalog.py`, each raw file's `.source.json` sidecar (URL, retrieval time, SHA-256,
provider), and `data/processed/<region>/manifest.json`.

**Provenance labels** used throughout:

| Label | Meaning |
| --- | --- |
| `real` | Values published by an external authority, unchanged apart from format, CRS and clipping |
| `derived` | Computed by Crisees from real inputs with a documented method (percentages, study area, hubs) |
| `synthetic` | Fabricated test fixture. Only in `backend/tests/`, never in `data/` |

## Geographic scope

**Region `houston-sw-pilot`: Southwest Houston pilot (Harris / Fort Bend)**

- Selection: 2020-vintage census tracts (TIGER/Line 2024) in Harris (48201) or Fort Bend (48157) County
  whose Census internal point lies in the box `[-95.66, 29.56, -95.48, 29.72]` (west, south, east, north).
- Result: 151 tracts (110 Harris, 41 Fort Bend), 286.6 km², 585,584 residents (ACS 2020–2024).
- Study-area bounds: `[-95.66523, 29.549161, -95.474078, 29.729579]`.
- Road and facility download box: study-area bounds plus 1 km, `[-95.67944, 29.53859, -95.4601, 29.74155]`.
  The buffer keeps routes that briefly leave the area.

Why this area:

1. **Flood relevance.** It spans the Brays Bayou and Keegans Bayou watersheds, which flooded in Tropical
   Storm Allison (2001) and Hurricane Harvey (2017).
2. **Equity relevance.** Alief, Sharpstown and the Gulfton edge have high shares of households without a
   vehicle (up to 38% per tract) and high poverty (up to 52% per tract).
3. **Flood data availability.** FEMA flood hazard polygons could be retrieved for the Fort Bend portion.
   The official FEMA NFHL service, configured as the primary source, would cover the whole area.
4. **Multi-county from day one.** Two counties exercise the data model's multi-county paths.
5. **Size.** About 18 × 20 km keeps processing under a minute and leaves room for Phase 2 routing
   experiments, while the road network is dense and complete.

New regions need only a JSON file in `backend/app/regions/definitions/` followed by the pipeline. No code
changes are required.

## Sources

### Census tract boundaries: U.S. Census Bureau TIGER/Line 2024

- URL: https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_48_tract.zip (Texas, 32.6 MB)
- License: public domain (U.S. Government work).
- Native CRS NAD83 (EPSG:4269), converted to WGS84 (EPSG:4326). The datum shift is about 1 m.
- Used fields: `GEOID`, `STATEFP`, `COUNTYFP`, `TRACTCE`, `NAMELSAD`, `ALAND`, `AWATER`, `INTPTLAT/LON`.
- Status: **retrieved** (6,896 Texas tracts, 151 selected).

### Demographics: American Community Survey 2020–2024 5-year estimates

- Primary method (no key): ACS table-based Summary File, national per-table files on
  `https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/`, streamed
  and filtered to `GEO_ID` starting `1400000US48` (all Texas tracts). Only the filtered rows are stored.
- Alternative: Census Data API (`api.census.gov/data/2024/acs/acs5`) when `CENSUS_API_KEY` is set. The API
  now redirects keyless requests to a "missing key" page, so a free key is required.
- License: public domain.
- Tables:

  | Table | Universe | Used for |
  | --- | --- | --- |
  | B01003 | Total population | total population |
  | B01001 | Total population | 65+ (lines 20–25, 44–49) |
  | B08201 | Households | households, households with no vehicle (line 2) |
  | C17002 (preferred) / B17001 (fallback) | Population for whom poverty status is determined | below poverty; C17002 also gives below 150% |
  | C18108 | Civilian noninstitutionalized population | with any disability (lines 3, 4, 7, 8, 11, 12) |

- Status: **retrieved** for B01003, B01001, B08201, C18108 and B17001. **C17002 failed.** The
  Census web server returned a "Request Rejected" firewall page (with HTTP 200) for
  `acsdt5y2024-c17002.dat` specifically, while every other table worked. The pipeline detected the bad
  content (it checks that files start with `GEO_ID|`) and fell back to B17001. Consequence:
  `population_below_150pct_poverty` and `pct_below_150pct_poverty` are null for every tract. Rerunning the
  download later (or with `CENSUS_API_KEY`) retrieves C17002 automatically, because the fallback is only
  used when C17002 is missing.

### Social vulnerability: CDC/ATSDR Social Vulnerability Index

- Primary: CDC SVI 2022 Texas tract CSV, https://svi.cdc.gov/Documents/Data/2022/csv/states/Texas.csv
- Fallback (used): an ArcGIS Online copy of the CDC SVI **2020** US tract table hosted by Esri,
  https://services1.arcgis.com/gGHDlz6USftL5Pau/ArcGIS/rest/services/CDC_Social_Vulnerability_Index_Tracts_2020/FeatureServer/1 ,
  queried by county (`STCOFIPS IN (48201, 48157)`), attributes only.
- License: public domain; cite "Centers for Disease Control and Prevention/Agency for Toxic Substances and
  Disease Registry/Geospatial Research, Analysis, and Services Program. CDC/ATSDR Social Vulnerability
  Index 2020 Database Texas."
- Status: **retrieved via fallback.** svi.cdc.gov and onemap.cdc.gov were blocked by the build
  environment's network policy. 151/151 tracts matched by GEOID; SVI 2020 uses 2020 tract definitions.
- Variables preserved individually: `RPL_THEMES`, `RPL_THEME1..4`, 15 `EP_*` percentages and `F_TOTAL`.
  CDC's `-999` becomes null. **No composite score was built**, so Phase 2 can design and test a transparent
  weighting.
- Limitations: SVI percentiles are US-wide rankings, not rankings within Houston. SVI 2020 reflects ACS
  2016–2020, which is older than the ACS 2020–2024 indicators. Several SVI variables (`EP_NOVEH`,
  `EP_AGE65`, `EP_DISABL`, `EP_POV150`) overlap the ACS indicators and must not be double counted.

### Flood hazard: FEMA flood hazard zones

- Primary: FEMA NFHL MapServer, https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer,
  layer 28 (Flood Hazard Zones, `S_FLD_HAZ_AR`) and layer 3 (FIRM Panels, `S_FIRM_PAN`), queried by the
  download box with output in EPSG:4326.
- Fallback (used): an ArcGIS Online copy of the FEMA FIRM database for **DFIRM 48157C (Fort Bend County)**,
  https://services1.arcgis.com/cTNi34MxOdcfum3A/ArcGIS/rest/services/Map_TX_WFL1/FeatureServer, layers 24
  (`S_FLD_HAZ_AR`) and 25 (`S_FIRM_PAN`). It is hosted by a third party, and its effective status was not
  independently verified (`VERSION_ID` values 1.1.1.0 and 2.3.3.x).
- License: public domain.
- Status: **partial sample retrieved.** 813 polygons were downloaded and 445 remain after clipping to the
  study area (AE 147, A 35, X 263); 13 FIRM panels. hazards.fema.gov, msc.fema.gov and the
  Harris County / City of Houston GIS servers were blocked by the build environment's network policy.
- **Coverage is 52.3% of the study area.** That is the Fort Bend side, computed from FIRM panel extents
  clipped to Fort Bend tracts. The Harris County side (DFIRM 48201C) has **no flood data** in this build.
  Absence of a polygon there means "unknown", not "no hazard". The API reports this coverage beside every
  flood response.
- What FEMA zones are: regulatory, probabilistic designations (1% and 0.2% annual chance). They are **not**
  observed or real-time flooding, and Harvey flooded many homes outside mapped floodplains. The data model
  keeps three evidence types separate: `fema_regulatory` (ingested), `observed` and `simulated` (Phase 2).

### Roads: OpenStreetMap via OSMnx, or Overture Maps transportation

- Primary: OSMnx `graph_from_bbox(bbox, network_type="drive", simplify=True, retain_all=False,
  truncate_by_edge=True)` against the Overpass API. The raw graph is saved as GraphML.
- Fallback (used): Overture Maps Foundation release **2026-11-18.0**, `theme=transportation/type=segment`,
  read from the public bucket `s3://overturemaps-us-west-2` with PyArrow (anonymous access, bbox predicate
  pushdown). 83,396 segments were downloaded and 60,630 drivable segments used. Overture's transportation
  layer is built from OpenStreetMap, and every edge keeps its OSM way id(s).
- License: ODbL 1.0, © OpenStreetMap contributors.
- Status: **retrieved via fallback**; overpass-api.de and its mirrors were blocked by the build environment's
  network policy.
- Conversion rules (`backend/pipeline/processing/roads.py`) mirror the OSMnx `drive` filter:
  - Classes kept: motorway, trunk, primary, secondary, tertiary, unclassified, residential, living_street,
    service. Each class also keeps its `_link` variant.
  - Service subclasses dropped: driveway, parking_aisle, drive_through, alley.
  - Segments with an unconditional motor-vehicle `denied` access rule are dropped (272 segments).
  - Direction: `denied` + `heading: backward` means one-way forward, and vice versa. Two-way roads become
    two directed edges, as in OSMnx.
  - Segments are split at every connector, and connectors become nodes.
  - Only the largest weakly connected component is kept (1,349 nodes dropped).
- Result: 88,404 nodes, 199,542 directed edges, 12,339 km of directed length. 98.2% of nodes are in the
  largest strongly connected component.
- The graph is **not** degree-2 simplified. OSMnx's simplifier would replace curved edge geometry with
  straight node-to-node lines, so interstitial nodes remain. Routing results are unaffected.

### Facilities: OpenStreetMap via OSMnx, or Overture Maps places

- Primary: `osmnx.features_from_bbox` with tags `amenity` ∈ {hospital, clinic, doctors, community_centre,
  social_centre, library, school, fire_station, police, townhall, social_facility, shelter},
  `healthcare` ∈ {hospital, clinic}, and `social_facility=shelter`. OSM `amenity=shelter` is always dropped
  because it tags bus, picnic and weather shelters.
- Fallback (used): Overture Maps release 2026-11-18.0 `theme=places`. 62,858 places were in the box. Kept:
  `taxonomy.primary` mapped to a Crisees category (see the data dictionary), confidence ≥ 0.5, and not
  `permanently_closed`. Near-duplicates within 25 m that share a name and category were merged.
- License: CDLA-Permissive-2.0 (Overture places).
- Status: **retrieved via fallback**: 451 facilities (school 228, hospital 102, community centre 47,
  fire station 21, library 16, clinic 15, police 14, town hall 5, shelter 3).
- **No facility is a verified evacuation shelter.** All records are `mapped_unverified`, with
  `is_designated_evacuation_shelter = null`. "shelter" means a mapped homeless or social shelter. Harris
  County and the City of Houston publish designated shelter locations only during events. A
  `verification_status = authority_verified` path exists in the schema for when such a list is ingested.
- Overture's "hospital" category includes some medical office buildings. Treat counts as indicative.

### Candidate pickup hubs (derived)

Facilities in {community_centre, library, school, townhall} within 300 m of a drivable-network node, each
snapped to its nearest node (UTM 15N distance): 296 candidates. These are planning hypotheses
(`status = candidate_unvalidated`), not designations.

## Network restrictions in the build environment

The Phase 1 build ran behind an egress allowlist. **Reachable:** `www2.census.gov`,
`tigerweb.geo.census.gov`, `services1.arcgis.com`, and the Overture S3 bucket. **Blocked:**
`hazards.fema.gov`, `msc.fema.gov`, `svi.cdc.gov`, `onemap.cdc.gov`, `overpass-api.de` and mirrors,
`nominatim.openstreetmap.org`, `download.geofabrik.de`, `services.arcgis.com`,
`mycity2.houstontx.gov`, and the Fort Bend GIS server. `api.census.gov` was reachable but requires a key.
On an unrestricted network the primary providers are tried first; no code changes are needed.

## Known limitations

1. Flood data covers 52% of the study area (Fort Bend only), from a third-party copy of the FEMA FIRM.
2. Roads and facilities come from Overture's OSM-derived data rather than live Overpass. The schema and
   graph conventions are identical.
3. SVI is the 2020 edition from a mirror and is older than the ACS 2020–2024 indicators.
4. Below-150%-of-poverty is null because C17002 could not be fetched (the server's firewall rejected it).
5. ACS margins of error are kept per tract. Region-level summaries do not compute aggregate MOEs.
6. No observed flood extents (for example Harvey inundation) and no designated shelter list are ingested.
7. Edge lengths for the Overture graph are planar UTM lengths. OSMnx uses great-circle lengths; the
   difference over this area is below 0.1%.
