# Optimization model (Engine E)

Code: `backend/app/engine/optimization.py`. Solver: HiGHS 1.x via `scipy.optimize.milp`, with branch and
bound and presolve. OR-Tools was evaluated and not needed: HiGHS solves the pilot instances to a proven
gap in under a second and adds no dependency beyond SciPy.

## Question answered

Given a hypothetical flood disruption, limited pickup hubs, vehicles and shelter space, the model asks:
which hubs should be activated, and how should people flow from their neighbourhoods through hubs to
shelters, so that the **priority-weighted number of people who cannot be evacuated is as small as
possible**?

## Sets and data

| Symbol | Meaning | Source |
| --- | --- | --- |
| o ∈ O | Sub-tract origin cells with demand > 0 (1,506 in the pilot) | Engine B |
| h ∈ H | Candidate pickup hubs (Phase 1 `candidate_hubs`, minus facilities used as shelters) | Phase 1 (derived) |
| s ∈ S | Assumed shelter destinations (default: mapped community centres, excluding those in a 1% zone) | HYPOTHETICAL |
| D_o | Persons needing assisted evacuation at o | Engine B (estimated) |
| w_o | Priority weight of o's tract (1 for the equal-weight model) | Equity weights below |
| c_oh, c_os | Walk-proxy network distance in metres | Engine A |
| t_hs, t_sh | Drive minutes hub→shelter and shelter→hub on the **disrupted** network | Engine A + C |
| r_hs | Round trip t_hs + t_sh + dwell, in minutes | derived |
| W | Max walk distance (default 800 m) | assumption |
| K | Hub throughput capacity, persons per horizon (default 600) | HYPOTHETICAL |
| C | Shelter capacity in persons (default 400) | HYPOTHETICAL |
| V, Q, T | Vehicles (15), seats per trip (40), horizon (480 min) | HYPOTHETICAL |
| P | Max active hubs (12) | HYPOTHETICAL |

Eligible pairs:

- (o,h) exists only if c_oh ≤ W.
- (o,s) exists only if c_os ≤ W.
- A leg (h,s) is kept for each hub's `shelters_per_hub` (default 4) nearest shelters with finite t_hs and
  t_sh and r_hs ≤ T.

## Decision variables

| Variable | Domain | Meaning |
| --- | --- | --- |
| y_h | {0,1} | Activate hub h |
| x_oh | ≥ 0 | Persons walking from o to hub h |
| g_os | ≥ 0 | Persons walking directly from o to shelter s |
| f_hs | ≥ 0 | Persons carried from hub h to shelter s |
| n_hs | ℤ≥0 (or ℝ≥0 if `integer_trips=false`) | Vehicle trips on leg (h,s) |
| u_o | ≥ 0 | Unmet demand at o |

## Objective (minimize)

```
  Σ_o w_o u_o
+ α_walk  Σ_oh (c_oh / W) x_oh  +  α_walk Σ_os (c_os / W) g_os
+ α_drive Σ_hs (t_hs / T) f_hs  +  0.001 Σ_hs (r_hs / T) n_hs
+ α_hub   Σ_h y_h
```

Defaults: α_walk = 0.01, α_drive = 0.01, α_hub = 0.1. Each penalty is at most about 0.02 per person, while
the smallest priority weight in the pilot is 0.66. Serving one more person therefore always lowers the
objective; the penalties only break ties (shorter walks, shorter drives, fewer hubs).

## Constraints

| # | Constraint | Meaning |
| --- | --- | --- |
| 1 | Σ_h x_oh + Σ_s g_os + u_o = D_o | Demand conservation: every estimated person is served or counted unmet |
| 2 | x_oh ≤ D_o y_h | Nobody is assigned to an inactive hub |
| 3 | Σ_o x_oh ≤ K y_h | Hub throughput capacity |
| 4 | Σ_o x_oh = Σ_s f_hs | Flow balance: **reaching a hub is not evacuation**. Everyone at a hub must be carried to a shelter |
| 5 | f_hs ≤ Q n_hs | Vehicle seats |
| 6 | Σ_hs r_hs n_hs ≤ V T | Fleet time budget, in vehicle-minutes |
| 7 | n_hs ≤ V ⌊T / r_hs⌋ | A leg cannot be served more often than the whole fleet could repeat it |
| 8 | Σ_h f_hs + Σ_o g_os ≤ C | Shelter capacity, shared by bus arrivals and walk-ins |
| 9 | Σ_h y_h ≤ P | Hub budget |

"Served" means walked to a shelter directly (g), or walked to an active hub and then carried by a feasible
trip to a shelter with capacity (x = f).

### What the vehicle model is and is not

Constraints 5–7 are a **capacity-based approximation**. They guarantee enough seats and vehicle-minutes
for every trip within the horizon. They do **not**:

- assign trips to individual vehicles (bin packing);
- model a depot, deadheading or trip sequencing;
- model traffic or loading queues.

The integer trip count n_hs removes fractional seats. Constraint 7 prevents a single leg from using more
repetitions than the fleet allows. This is not a vehicle routing or scheduling solution.

## Equity weights

```
w_t^raw = 1 + β_pov · rank(pct_below_poverty_t) + β_dis · rank(pct_with_disability_t) [+ β_65 · rank(pct_65_plus_t)]
w_t     = w_t^raw / ( Σ_t D_t w_t^raw / Σ_t D_t )          (demand-weighted mean = 1)
```

- `rank` is the within-region percentile rank, rescaled to [0,1].
- A missing indicator gets the neutral rank 0.5, and the tract is flagged in `weight_flags`.
- Defaults: β_pov = β_dis = 0.5 and β_65 = 0, so raw weights lie in [1, 2]. Pilot weights after
  normalization: min 0.658, median 0.946, max 1.268.
- **Non-overlap.** Car-free status defines *who* is counted in demand. Poverty and disability are
  *rates*, used only to prioritize, never to add people. Age 65+ is off by default because ACS C18108
  disability counts already include older adults with disabilities. SVI themes are not used, because SVI
  theme 4 includes the no-vehicle share, which is already the demand base.
- **Equal-weight baseline:** w = 1 everywhere (`weights.mode = "equal"`).

## Candidate screening

A hub enters the model only if it can serve someone: at least one origin with demand lies within W, and
at least one feasible shelter leg exists. No other pruning is applied, so no community loses its only
option. In the pilot (severe scenario) 211 of 249 hubs remain.

## Solver settings and status reporting

| Setting | Default | Bounds |
| --- | --- | --- |
| `time_limit_s` | 30 | (0, 120] |
| `mip_rel_gap` | 0.005 | [0, 0.2] |
| `integer_trips` | true | |

| Status | Meaning |
| --- | --- |
| `optimal` | Proven optimal (gap 0) |
| `optimal_within_gap` | Proven within the reported `mip_gap` |
| `time_limit_feasible` | Feasible but **not** proven optimal |
| `time_limit_no_solution`, `infeasible`, `solver_error` | No solution; the API returns HTTP 422 `optimization_failed` |

Because u_o slack always exists, the model is feasible for any valid input. "Infeasible" can only arise
from solver errors, and it is handled.

## Independent verification

After every solve, `verify()` recomputes each constraint from the returned values in NumPy, independent
of the solver. It reports the maximum violation per constraint family, the trip integrality gap and the
vehicle-minutes used. The result is returned as `constraint_check` and asserted in the tests. On the real
pilot, every family's violation is 0.0.

## Model size and performance (pilot, severe scenario, 4-core container)

| Item | Value |
| --- | --- |
| Variables / binaries / integer trips | 4,619 / 211 / 842 |
| Constraints / nonzeros | 3,827 / 11,604 |
| Solve time (12 hubs) | 0.48 s, gap 0.017% |
| `/optimize` end to end (warm engine) | 0.59–0.91 s for 12, 20 or 40 hubs |

## Edge cases handled

| Case | Behaviour |
| --- | --- |
| Zero demand | Trivial model returns `optimal`, served = 0 |
| Zero vehicles or hubs | Only direct walking to shelters can serve; hub service = 0 |
| Unreachable hub (walk > W) | No x variable exists |
| Unreachable or too-distant shelter (∞ or r > T) | No leg exists |
| Disconnected facilities | Drive times are ∞, so the leg is excluded |
| Insufficient shelter capacity | Constraint 8 binds; the rest is reported unmet |
| Fixed hub plan (robustness case) | `fixed_hubs` fixes y |

## Limitations

- Persons are continuous (fractional people); trips are integer.
- One hub capacity and one shelter capacity value apply to all sites. These are hypothetical, not official
  capacities.
- Walking uses a road-network proxy (see `ACCESSIBILITY_METHODS.md`).
- Demand is static. There is no time-dependent flooding during the horizon.
