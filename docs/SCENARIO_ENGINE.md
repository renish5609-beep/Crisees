# Scenario engine (Engine C)

Code: `backend/app/engine/scenarios.py`; exposure inputs: `backend/pipeline/processing/exposure.py`.

## Three kinds of flood information, kept separate

| Evidence | Meaning | In Crisees |
| --- | --- | --- |
| `fema_regulatory` | FEMA 1% / 0.2% annual-chance zones (probabilistic, regulatory) | `flood_hazards` (Phase 1) |
| `observed` | Inundation actually observed in an event | Not ingested |
| `simulated` | Hypothetical road closures produced by explicit rules | Scenario outputs (`evidence_type: simulated`) |

A road crossing a FEMA zone is **potentially exposed**, not closed. Closures exist only inside a scenario.
They are produced by stated hypothetical rules and never written back to the baseline data.

## Inputs: `edge_flood_exposure` (derived dataset)

For each directed edge, computed in EPSG:32615 with spatial-index prefiltering:

| Field | Meaning |
| --- | --- |
| `len_in_1pct_m` | Length inside A/AE/AO (1%-annual-chance) polygons |
| `len_in_0_2pct_m` | Length inside shaded-X (0.2%) polygons |
| `len_in_coverage_m` | Length inside the area actually covered by ingested FEMA panels |
| `dist_to_1pct_m` | Distance to the nearest 1% polygon (NaN beyond 1 km) |

Pilot facts: 527 directed edges touch a 1% zone and 1,997 touch a 0.2% zone. Only 30% of edges have any
covered length; the rest are on the Harris County side, where no FEMA data has been ingested.

## Rules

Sampling is done per **physical segment**, so both directions of a two-way street close together.
Rules are applied in this order (a segment closed by an earlier rule is not re-sampled):

| Rule | Eligible segments | Probability parameter |
| --- | --- | --- |
| `fema_1pct` | `len_in_1pct_m ≥ min_exposed_m` | `one_pct_closure_prob` |
| `fema_0.2pct` | `len_in_0_2pct_m ≥ min_exposed_m` | `point_two_pct_closure_prob` |
| `overbank` | within `overbank_buffer_m` of a 1% zone **and fully inside FEMA coverage** | `overbank_closure_prob` |
| `stress_unknown_coverage` | not fully inside coverage (only with `unknown_coverage_policy="stress_sample"`) | `unknown_closure_prob` |
| `custom` | `custom_closed_edge_ids` (≤ 5,000; both directions closed) | Always closed |

**Unknown coverage.** Under the default `no_inference` policy, roads outside FEMA coverage are never closed
by flood rules, and they are reported as unknown (80,344 segments, 4,875 km in the pilot). That is not a
claim that they are safe. The results are therefore a **lower bound** on disruption for the Harris side.
`stress_sample` exists for sensitivity testing only.

## Determinism

The draw for (seed, rule, segment) is `SHA-256("{seed}|{rule}|{segment_key}")[:8] / 2^64`, where
`segment_key` is the segment's lexicographically smallest edge id. The draw is independent of processing
order, worker count and Python hash randomization. Same inputs give the same closures.

`scenario_id = "scn_" + sha256({region, data generated_at, spec})[:16]`, so an id identifies the exact
inputs that produced it.

## Presets (all hypothetical)

| Preset | Rules | Pilot result |
| --- | --- | --- |
| `baseline` | None | 0 closures |
| `moderate` | 1%: p=0.6 (≥10 m); overbank 50 m: p=0.15 | 507 segments (846 directed edges), 62.7 km; 177 by 1%, 330 overbank |
| `severe` | 1%: p=1.0 (≥5 m); 0.2%: p=0.5; overbank 150 m: p=0.35 | 3,123 segments (5,431 directed edges), 266.2 km; 311 / 546 / 2,266 |

Default seed: 2017. These numbers are reproducible with `POST /scenarios/evaluate`.

## Scenario outputs

`POST /api/v1/regions/{id}/scenarios/evaluate` returns:

- **closures:** directed edges, segments, length, per-rule counts, unknown-coverage totals.
- **network:** weak and strong component statistics, baseline and scenario.
- **access_change:**
  - origins and estimated demand losing every drive route to a shelter;
  - mean nearest-shelter drive minutes and the p90 increase;
  - mean shelters reachable within the largest threshold;
  - hubs that still reach a shelter.
- **provenance:** data stamp, spec, deterministic id.

`GET /scenarios/{scenario_id}/closures` returns the closed segments as GeoJSON (one feature per segment).

Pilot, severe scenario:

- 229 of 1,667 origins (561 persons of estimated demand) lose every drive route to a shelter.
- 1,464 weak components remain after closures (baseline: 1).
- Mean shelters within 30 min fall from 47.0 to 41.9.
- 224 of 248 hubs still reach a shelter.

## Limitations

- Closure probabilities, buffers and thresholds are planning assumptions, not hydraulic modelling. No
  depth, rainfall, timing or underpass data is used.
- FEMA data covers 52% of the study area (Fort Bend only), so Harris-side disruption is not represented
  unless `stress_sample` is used.
- Edges are closed for the whole planning horizon.
