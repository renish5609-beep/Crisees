# Data dictionary

Processed datasets live in `data/processed/<region_id>/`. The file-name contract is defined once in
`backend/app/datasets.py`. API schemas are in `backend/app/schemas/`.

## Conventions

- **Coordinates.** Every stored geometry and every API response uses WGS84, **EPSG:4326**, in GeoJSON
  **[longitude, latitude]** order (RFC 7946). In Houston, x ≈ −95.5 and y ≈ 29.6. Point datasets also carry
  explicit `lon` and `lat` columns.
- **Metric work** (lengths, areas, buffers, snapping) uses the region's `analysis_crs`, **EPSG:32615**
  (WGS 84 / UTM zone 15N, metres). Never measure in degrees.
- **Formats.** Spatial datasets are GeoParquet; tabular datasets are Parquet.
- **Tract GEOID.** An 11-character string, `SS` state + `CCC` county + `TTTTTT` tract (for example
  `48201410100`). It is normalized by `pipeline/processing/geoid.py`, which accepts the `1400000US`
  prefix, numeric values, lost leading zeros and separators.
- **Missing values.** `null` (NaN or `<NA>` in pandas) means *not available*. Missing values are never
  replaced with 0. The reason is recorded in the record's `missing_fields` list.
- **Percentages** are 0–100 with 2 decimals.
- **Provenance and sources** are recorded per dataset in `manifest.json` (`provenance`, `provider`,
  `sources[]`, `notes[]`, `record_count`, `generated_at`, `extra`).

## manifest.json

```jsonc
{
  "region_id": "houston-sw-pilot",
  "schema_version": "1.0",
  "generated_at": "2026-11-21T23:32:16Z",
  "study_area_bbox": [-95.66523, 29.549161, -95.474078, 29.729579],
  "datasets": {
    "<key>": {
      "file": "tracts.parquet", "title": "...", "record_count": 151,
      "provenance": "real|derived|synthetic", "provider": "tiger|summary_file|overture|...",
      "crs": "EPSG:4326", "sources": [SourceAttribution], "notes": ["..."],
      "generated_at": "...", "extra": { /* dataset-specific stats */ }
    }
  }
}
```

## study_area.parquet (GeographicRegion boundary) · derived

| Field | Type | Description |
| --- | --- | --- |
| region_id | str | Region identifier |
| tract_count | int | Tracts in the union |
| area_km2 | float | Area in UTM 15N |
| geometry | (Multi)Polygon | Union of selected tracts |

Region metadata (name, counties, bbox, CRS, vintages, selection rule, justification) comes from
`backend/app/regions/definitions/<region_id>.json` and is served as `GeographicRegion`.

## tracts.parquet (CensusTract) · real

| Field | Type | Description |
| --- | --- | --- |
| geoid | str(11) | Tract GEOID |
| state_fips / county_fips / tract_code | str | GEOID components |
| name | str | e.g. "Census Tract 4101" |
| county_name | str | Harris County / Fort Bend County |
| land_area_m2 / water_area_m2 | float | TIGER `ALAND` / `AWATER` |
| intpt_lon / intpt_lat | float | Census internal point (served as `internal_point: [lon, lat]`) |
| tiger_year | int | 2024 |
| source_id | str | `tiger-2024-tract-48` |
| geometry | (Multi)Polygon | Tract boundary |

## demographics.parquet (DemographicIndicators) · derived from real ACS counts

ACS 2020–2024 5-year estimates. `*_moe` fields are 90% margins of error. MOEs of summed cells use the
Census root-sum-of-squares approximation.

| Field | Type | Definition (ACS cells) |
| --- | --- | --- |
| geoid | str | Tract GEOID |
| acs_vintage | str | "2020-2024 ACS 5-year" |
| total_population (+_moe) | int | B01003_001 |
| households_total | int | B08201_001 |
| households_no_vehicle (+_moe) | int | B08201_002 |
| pct_households_no_vehicle | float | 100 × no_vehicle / households_total |
| poverty_universe | int | C17002_001, or B17001_001 in the fallback |
| population_below_poverty (+_moe) | int | C17002_002+003, or B17001_002 |
| pct_below_poverty | float | 100 × below / poverty_universe |
| population_below_150pct_poverty | int | C17002_002..005 (**null if C17002 unavailable**) |
| pct_below_150pct_poverty | float | 100 × below150 / poverty_universe |
| population_65_plus (+_moe) | int | B01001_020..025 + B01001_044..049 |
| pct_65_plus | float | 100 × 65+ / total_population |
| disability_universe | int | C18108_001 (civilian noninstitutionalized) |
| population_with_disability (+_moe) | int | C18108_003,004,007,008,011,012 |
| pct_with_disability | float | 100 × with_disability / disability_universe |
| missing_fields | list[str] | `"<field>:<reason>"`, e.g. `poverty_universe:estimate_not_computable` |
| quality_flags | list[str] | See below |
| source_id | str | `acs5-2024` |

**Missing-value reasons.** ACS annotation codes map as follows: −666666666 `estimate_not_computable`,
−999999999 `insufficient_sample`, −888888888 `not_applicable`, −222222222 `moe_not_computable`,
−555555555 `moe_controlled`, and so on. Other reasons: `blank`; `component_missing` (a summed cell was
missing); `table_unavailable:<TABLE>`; `undefined` (a percentage whose inputs were missing).

**Quality flags.** `zero_denominator:<pct>` (percentage set to null), `numerator_exceeds_denominator:<pct>`
(percentage set to null rather than over 100), `b01001_b01003_total_mismatch`, `zero_population_tract`,
`tract_absent_from_acs`.

## vulnerability.parquet (VulnerabilityIndicators) · real

CDC/ATSDR SVI fields, unchanged apart from renaming. CDC's −999 becomes null. The data is not combined
into any new score.

| Field | SVI source field | Meaning |
| --- | --- | --- |
| svi_year | (metadata) | 2020 (fallback) or 2022 (official source) |
| svi_geography | (metadata) | "US-wide percentile ranking" |
| rpl_themes | RPL_THEMES | Overall percentile rank, 0–1 |
| rpl_theme1_socioeconomic | RPL_THEME1 | Socioeconomic status |
| rpl_theme2_household | RPL_THEME2 | Household characteristics |
| rpl_theme3_minority_language | RPL_THEME3 | Racial and ethnic minority status |
| rpl_theme4_housing_transport | RPL_THEME4 | Housing type and transportation |
| ep_pov150, ep_unemp, ep_nohsdp, ep_uninsur, ep_age65, ep_age17, ep_disabl, ep_sngpnt, ep_limeng, ep_minrty, ep_munit, ep_mobile, ep_crowd, ep_noveh, ep_groupq | EP_* | Estimated percentages (0–100) |
| f_total | F_TOTAL | Count of variables at or above the 90th percentile |
| missing_fields | – | Fields that are null |

## road_nodes.parquet (RoadNode) · real (OSM-derived)

| Field | Type | Description |
| --- | --- | --- |
| node_id | int64 | OSM node id (OSMnx provider), or the first 60 bits of the Overture connector UUID |
| lon / lat | float | Coordinates |
| street_count | int | Physical streets meeting at the node (`osmnx.stats.count_streets_per_node`) |
| source_ref | str | `osm:node:<id>` or `overture:connector:<uuid>` |
| geometry | Point | |

## road_edges.parquet (RoadEdge) · real (OSM-derived)

| Field | Type | Description |
| --- | --- | --- |
| edge_id | str | `"{u}-{v}-{key}"` |
| u / v / key | int | Directed edge from `u` to `v`; `key` separates parallel edges (MultiDiGraph) |
| road_class | str | OSM `highway` value (`primary`, `residential`, `motorway_link`, ...) |
| name | str? | Street name |
| length_m | float | Length in metres |
| oneway | bool | True if traffic flows only u→v. Two-way roads appear as two edges with `oneway=false` |
| reversed | bool | True if the edge runs against the source way's digitized direction |
| maxspeed_kph | float? | Posted speed limit only. **No imputed speeds** |
| lanes | float? | Lane count where tagged (OSMnx provider) |
| osm_way_ids | list[int] | Source OpenStreetMap way ids |
| source_ref | str | `osm:way:<id>` or `overture:segment:<uuid>` |
| geometry | LineString | Oriented from u to v |

**Graph reconstruction.** `app.services.road_graph.tables_to_graph(nodes, edges)` returns an
OSMnx-compatible `networkx.MultiDiGraph` with `graph["crs"]="EPSG:4326"`, node attributes `x`, `y`,
`street_count`, and edge attributes `length`, `highway`, `oneway`, `reversed`, `name`, `osmid`,
`maxspeed_kph` and `geometry`. `graph_to_tables` is the inverse. A round trip preserves nodes, edge keys,
directionality and geometry, which the tests verify.

## facilities.parquet (EmergencyFacility) · real

| Field | Type | Description |
| --- | --- | --- |
| facility_id | str | `osm-<element>-<id>` or `ovt-<overture id>` |
| name | str? | |
| category | enum | shelter, hospital, clinic, community_centre, library, school, fire_station, police, townhall, social_facility |
| source_category | str | Raw tag, e.g. `amenity=library` or `overture:elementary_school` |
| lon / lat | float | Point (polygon features use a representative point) |
| address | str? | |
| verification_status | enum | `mapped_unverified` (all Phase 1 records) or `authority_verified` |
| is_designated_evacuation_shelter | bool? | Always null in Phase 1 (unknown) |
| source_id / source_record_id | str | Upstream identifiers |
| confidence | float? | Overture existence confidence (0–1) |

Overture `taxonomy.primary` mapping: hospital, childrens_hospital, specialty_hospital,
psychiatric_hospital, emergency_department → hospital; primary_care_or_general_clinic,
emergency_or_urgent_care_facility, community_health_center, urgent_care_clinic → clinic;
community_center, civic_center, senior_citizen_service → community_centre; library → library;
elementary_school, middle_school, high_school, public_school → school; fire_station → fire_station;
police_station → police; town_hall, city_hall → townhall; homeless_shelter, emergency_shelter → shelter;
social_service_organization → social_facility.

## candidate_hubs.parquet (CandidatePickupHub) · derived

| Field | Type | Description |
| --- | --- | --- |
| hub_id | str | `hub-<facility_id>` |
| facility_id, name, category, lon, lat | | From the facility |
| candidacy_basis | str | Why this category is a plausible pickup point |
| nearest_node_id | int | Nearest road node (UTM distance) |
| snap_distance_m | float | Distance to that node; candidates over 300 m are excluded |
| status | str | `candidate_unvalidated` |

## flood_hazards.parquet (FloodHazardArea) · real

| Field | Type | Description |
| --- | --- | --- |
| hazard_id | str | `<DFIRM_ID>-<FLD_AR_ID>-<n>` |
| evidence_type | enum | Always `fema_regulatory` here (`observed` and `simulated` are reserved) |
| flood_zone | str | FEMA `FLD_ZONE` (A, AE, AO, X, ...) |
| zone_subtype | str? | FEMA `ZONE_SUBTY` |
| is_sfha | bool? | Special Flood Hazard Area (`SFHA_TF`) |
| annual_chance_category | str | `1pct` (A/V zones), `0.2pct` (shaded X), `minimal` (X), `other` |
| static_bfe_ft | float? | Static base flood elevation; FEMA −9999 becomes null |
| dfirm_id / version_id / source_citation | str | FEMA provenance fields |
| area_m2 | float | Clipped area in UTM 15N |
| geometry | (Multi)Polygon | Clipped to the study area |

## flood_coverage.parquet · derived

| Field | Type | Description |
| --- | --- | --- |
| dfirm_id | str | FIRM database id |
| geometry | (Multi)Polygon | FIRM panel extent within the study area, clipped to the DFIRM's county |

`manifest.datasets.flood_coverage.extra` holds `covered_area_fraction` (0.5229), `dfirm_ids`,
`panel_count` and `method`.

## vehicle_access.parquet · real (Phase 2 input)

| Field | Type | Description |
| --- | --- | --- |
| geoid | str | Tract |
| hh_no_vehicle (+_moe) | int | B08201_002: households with no vehicle |
| hh_no_vehicle_1p / _2p / _3p / _4p_plus (+_moe) | int | B08201_008 / 014 / 020 / 026: no-vehicle households of 1, 2, 3 and 4+ persons |
| size_cells_consistent | bool? | Size cells sum to the total (true for all 151 pilot tracts) |

## edge_flood_exposure.parquet · derived (Phase 2 input)

One row per directed edge, in the same order and with the same `edge_id` as `road_edges`. Lengths are in
metres (EPSG:32615).

| Field | Description |
| --- | --- |
| length_m | Edge length |
| len_in_1pct_m | Length inside FEMA 1%-annual-chance zones (regulatory exposure, **not** observed flooding) |
| len_in_0_2pct_m | Length inside 0.2%-annual-chance zones |
| len_in_coverage_m | Length inside ingested FEMA coverage; less than length_m means part of the edge has unknown status |
| dist_to_1pct_m | Distance to the nearest 1% polygon, capped at 1 km (NaN beyond) |

Phase 2 analysis outputs (scenarios, accessibility, optimization) are computed on request and returned by
the API. They are not stored as datasets. See API.md.
