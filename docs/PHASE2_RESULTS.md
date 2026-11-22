# Phase 2 results: demonstration scenario and measurements

All numbers below come from `python scripts/benchmark_phase2.py`, run on the real
`houston-sw-pilot` data. They are **modelled outcomes under hypothetical assumptions**, not demonstrated
real-world impact. Reproduce them through the API with `GET /api/v1/regions/houston-sw-pilot/demo`, or
with `POST /compare` and the body in the `request` field of that response.

## Demonstration scenario

**Title:** "Southwest Houston: severe hypothetical bayou flooding, 12 pickup hubs, 15 buses"

| Input | Value | Kind |
| --- | --- | --- |
| Geography | 151 tracts, 1,667 sub-tract origins, 88,404-node road graph | Real (Phase 1) |
| Demand | 23,033 persons: 50% of 46,066 residents of zero-vehicle households | Observed counts × hypothetical participation |
| Flood | `severe` preset, seed 2017: 3,123 segments / 266 km closed, Fort Bend side only | Hypothetical rules on FEMA exposure |
| Shelters | 47 mapped community centres, 400 persons each | Hypothetical |
| Hubs | Up to 12 of 249 candidates (schools, libraries, town halls), 600 persons each | Hypothetical |
| Fleet | 15 vehicles × 40 seats, 8-hour horizon, 10-minute dwell per trip | Hypothetical |
| Walking | ≤ 800 m on the walk-proxy network | Assumption |
| Weights | β_poverty = β_disability = 0.5 (ranks), normalized | Transparent priority |

### 1–3. Baseline access and deterioration

| Indicator (demand-weighted) | Baseline | Severe |
| --- | ---: | ---: |
| Demand within 800 m walk of any candidate hub | 53.8% | 53.1% |
| Demand within 800 m walk of an assumed shelter | 26.4% | 26.3% |
| Demand with no drive route to any shelter | 0.0% | 2.4% |
| Mean shelters within 30 min drive | 47.0 | 41.9 |
| Weak network components | 1 | 1,464 |

229 origins (561 persons of estimated demand) lose every drive route to a shelter. 2 tracts become fully
disconnected from shelters, 20 lose walk access to hubs and 23 have longer drives.

### 4. Communities most affected (demand-weighted walk-access loss)

| Tract | Demand | Walk-access loss (persons) | Newly without drive route (persons) |
| --- | ---: | ---: | ---: |
| 48157672004 | 386.8 | 59.8 | 111.1 |
| 48157671402 | 119.0 | 27.3 | 7.3 |
| 48157671501 | 156.0 | 20.2 | 46.3 |
| 48157674002 | 87.0 | 11.8 | 87.0 (no route at all) |
| 48157671002 | 45.5 | 9.3 | 5.0 |

All of these are Fort Bend tracts, because only that side has FEMA data. Harris-side tracts show no
disruption **because their flood status is unknown**, not because they are safe.

### 5–7. Optimization and counterfactuals

Identical inputs are used in every case.

| Case | Served | Unmet | Coverage | Weighted unmet* | Hubs | Trips | Fleet use | Cov. T1 (low priority) | Cov. T2 | Cov. T3 (high priority) | Solver |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A. Baseline, no intervention (walk to shelter only) | 5,239.7 | 17,793.1 | 22.75% | 17,546.4 | 0 | 0 | – | 12.4% | 19.5% | 30.1% | optimal |
| B. Disrupted, no intervention | 5,213.8 | 17,818.9 | 22.64% | 17,569.6 | 0 | 0 | – | 12.2% | 19.3% | 30.1% | optimal |
| C. Disrupted, **equity-optimized** hubs + vehicles | 9,493.3 | 13,539.5 | 41.22% | 13,166.5 | 12 | 128 | 30.3% | 18.9% | 44.0% | 48.6% | gap 0.017% |
| D. Disrupted, equal-weight optimized | 9,493.3 | 13,539.5 | 41.22% | 13,218.8 | 12 | 134 | 31.4% | 33.7% | 37.5% | 47.8% | gap 0.39% |
| E. Baseline-chosen hubs under disruption | 9,493.3 | 13,539.5 | 41.22% | 13,171.6 | 12 | 137 | 31.6% | 20.1% | 43.4% | 48.6% | optimal |

\*Unmet demand weighted with the equity weights in every row, so rows are comparable.

**Findings, stated without inflation:**

- **Disruption effect (B − A):** −25.9 served. Walk-only access to shelters barely changes, because walking
  ignores one-way restrictions and most closures are near bayous. The larger disruption effect is on
  drive access (561 persons lose all drive routes) and on hub-to-shelter legs (24 hubs lose every route).
- **Intervention effect (C − B):** +4,279.5 persons served (+18.6 percentage points coverage), and
  weighted unmet demand falls by 4,403.1. 13,540 of 23,033 remain unmet.
- **Equity vs equal (C − D):**
  - The same total is served, so the binding limit is the same (see below).
  - Priority-weighted unmet demand is 52.3 lower, which is small.
  - Coverage shifts from the lowest-priority tercile (33.7% → 18.9%) to the middle tercile
    (37.5% → 44.0%) and slightly to the highest (47.8% → 48.6%).
  - This is a redistribution, not a gain in total service.
- **Robustness (C − E):** hubs chosen for the intact network serve the same total under disruption once
  flows are re-optimized; re-choosing hubs for the flood improves weighted unmet by only 5.1.

**Why more is not served (binding constraints, case C):**

- The hub budget is fully used: 12 of 12.
- 20 of 41 used shelters are at capacity.
- Only 1 hub is at capacity, and the fleet uses 30% of its vehicle-minutes, so vehicles are **not** the
  bottleneck.
- 8,789.5 persons of demand have **no candidate hub or shelter within 800 m**, so no allocation can serve
  them without more candidate sites, longer walks or door-to-door service.

More hubs help: 20 hubs serve 10,573.6, and 30 hubs serve 11,427.1 (same scenario and defaults).

**Recommended hubs (case C):** Sharpstown High School, Energy For Stem Academy, SER-Niños Elementary II,
Walter Neighborhood Library, Foerster Elementary, Collins Elementary, St. Agnes Academy, Stanberry High
School, American Montessori School, Harmony School of Exploration, Arrow Academy Las Americas and Valley
West Elementary. Each has 1–3 shelter legs. All are unverified candidates. Some are private schools that
would need agreements, so the list is a planning hypothesis.

## Performance

Measured in a 4-vCPU cloud container (Python 3.13, SciPy 1.18.1, HiGHS via `scipy.optimize.milp`), through
the full API stack in-process:

| Operation | Seconds | Cache |
| --- | ---: | --- |
| Evaluate severe, cold (engine build 1.0 s + baseline and severe scenario states) | 3.61 | miss |
| Evaluate severe, repeated | 0.012 | hit |
| Evaluate moderate (warm engine) | 1.54 | miss |
| Accessibility, severe (151 tracts with geometry) | 0.16 | miss |
| Optimize severe, 12 hubs (solve 0.48 s) | 0.65 | miss |
| Optimize severe, 20 hubs | 0.59 | miss |
| Optimize severe, 40 hubs | 0.91 | miss |
| Optimize severe, fluid trips | 0.76 | miss |
| Compare (5 counterfactual solves) | 1.55 | miss |
| Compare, repeated | 0.004 | hit |

Breakdown of a scenario state:

| Step | Seconds |
| --- | ---: |
| Closures (segment table cached after the first build) | 0.01–0.09 |
| Sparse matrix build | about 0.11 |
| Walking searches | about 0.13 |
| Drive searches | 1.0–1.4 |

Model size (12 hubs): 4,619 variables (211 binary, 842 integer), 3,827 constraints.

## Reproduce

```bash
python scripts/download_data.py && python scripts/process_data.py   # includes the 'derived' step
```
```bash
python scripts/benchmark_phase2.py                                   # prints the tables above
```
```bash
cd backend && uvicorn app.main:app --port 8000
```
```bash
curl -s localhost:8000/api/v1/regions/houston-sw-pilot/demo | jq '.result.cases[] | {case, served: .totals.served}'
```

Timings vary with hardware. Solver results are deterministic for identical inputs; this is tested.
