# Routing, demand and accessibility methods (Engines A, B, D)

## Engine A: road network and travel time (`app/engine/network.py`)

**Representation.** The Phase 1 graph (88,404 nodes, 199,542 directed edges) is held as immutable NumPy
arrays. A scenario is a boolean closure mask. Each evaluation builds a fresh CSR sparse matrix from the
kept edges (about 0.1 s), and the baseline arrays are never mutated (tested). Parallel edges keep the
**minimum** weight: a naive CSR build would *sum* them, which was detected and fixed. Two-way streets are
two directed edges, and one-way streets have a single direction.

**Algorithms.** All searches use `scipy.sparse.csgraph.dijkstra`, which is compiled:

| Need | Method | Cost |
| --- | --- | --- |
| Every node → nearest shelter | One multi-source Dijkstra (`min_only=True`) on the transposed graph | 1 search |
| Hub → shelter, every node → shelter | One search per shelter on the transposed graph (47) | 47 searches |
| Shelter → hub (return legs) | One search per shelter on the forward graph | 47 searches |
| Origin → hubs / shelters on foot | One **bounded** search per hub/shelter (`limit=2000 m`) on the walk graph | 249 + 47 small searches |

The engine never runs one search per origin-destination pair. Searches run in chunks of 64 sources to
bound memory.

**Travel time.** time = length / speed. The posted `maxspeed_kph` is used only if it lies in 8–130 km/h
(`speed_source = "posted"`). Otherwise the documented class default applies (`"class_default"`).

| Class | km/h (mph) |
| --- | --- |
| motorway | 96.6 (60) |
| trunk | 80.5 (50) |
| primary | 64.4 (40) |
| secondary | 56.3 (35) |
| tertiary | 48.3 (30) |
| residential / unclassified | 40.2 (25) |
| service | 24.1 (15) |
| living_street | 16.1 (10) |
| motorway_link | 56.3 |
| other links | 40.2–48.3 |

Only 6.0% of edges (7.8% of length) carry a posted speed, so **travel times are mostly assumption-based
free-flow estimates**. `SpeedModel.speed_factor` scales all speeds, for example 0.7 for evacuation
congestion. Units are metres, minutes and km/h.

**Walking proxy.** No pedestrian network (sidewalks, crossings) is available. Walking distance is the
shortest path on the road network treated as **undirected**, excluding motorway and trunk roads and their
links. One-way restrictions do not apply on foot. Speed is 80 m/min (4.8 km/h), and the default limit is
800 m (10 minutes). This overstates access where sidewalks are missing and understates it where footpaths
shortcut blocks. Many residents with disabilities walk slower or cannot walk 800 m; lower `walk_max_m` to
test that.

**Vehicle routing is not walking accessibility.** Drive times are used for hub-to-shelter vehicle legs and
for drive-access indicators. Car-free residents are only ever connected to hubs and shelters by walking.

## Engine B: demand (`app/engine/demand.py`)

```
persons_zero_vehicle_t = 1·H1 + 2·H2 + 3·H3 + p4·H4      (ACS B08201 lines 008/014/020/026)
demand_t               = participation × persons_zero_vehicle_t
```

| Term | Kind | Default |
| --- | --- | --- |
| H1..H4: zero-vehicle households of size 1, 2, 3, 4+ | **Observed** (ACS 2020–2024) | |
| p4: mean size of 4+ households | Assumption | 4.5 |
| participation: share requesting assisted evacuation | **Hypothetical** | 0.5 |
| Priority weights | Priority, not demand | See OPTIMIZATION_MODEL.md |

- **Fallback.** If the size cells are missing, the zero-vehicle total × the tract's mean household size is
  used (`demand_method` records this). If nothing is available, demand is **null**, the tract is flagged
  and it is excluded.
- **Overlap.** Older-adult, disability and poverty counts are never added to demand, because the same
  person can appear in several tables.
- **Pilot.** 21,981 zero-vehicle households (size cells reconcile with the total in all 151 tracts) give
  46,066 persons and 23,033 demand at 50% participation.

**Sensitivity** (`POST /demand` returns this grid):

| participation \ p4 | 4.0 | 4.5 | 5.0 |
| --- | ---: | ---: | ---: |
| 0.25 | 11,159 | 11,516 | 11,874 |
| 0.50 | 22,319 | 23,033 | 23,747 |
| 0.75 | 33,478 | 34,549 | 35,621 |
| 1.00 | 44,637 | 46,066 | 47,494 |

**Spatial allocation (sub-tract origins).** Tract demand is split across cells of a 500 m grid intersected
with the tract, in proportion to **residential street length** (residential, living_street and
unclassified segments, each counted once), which serves as a housing proxy. Each cell's origin is the
length-weighted centroid snapped to the walk network (median snap 40 m, max 207 m). The pilot has 1,667
origins. Three tracts with no residential streets use the Census internal point. This is a dasymetric
approximation: actual housing locations and block-level population are not used.

## Engine D: accessibility (`app/engine/accessibility.py`)

Tract metrics are averages over the tract's origins, weighted by each origin's share of tract demand.

| Metric | Unit |
| --- | --- |
| `drive_min_to_nearest_shelter` (finite routes only) | minutes |
| `share_demand_no_drive_route_to_shelter` | 0–1 |
| `shelters_within_{10,20,30}_min` | count |
| `walk_m_to_nearest_hub`, `walk_min_to_nearest_hub` | m, min |
| `share_demand_within_walk_of_hub` / `_of_shelter` | 0–1 |
| `hubs_within_walk` | count |
| `disconnected_from_shelters` (no origin has any drive route) | bool |
| Deltas vs baseline: `delta_drive_min_to_nearest_shelter`, `lost_share_within_walk_of_hub`, `newly_no_drive_route_share` | |
| `demand_weighted_walk_access_loss`, `demand_newly_without_drive_route` | persons |

Unreachable values are `inf` internally and `null` in JSON, **never 0**. Shelters are assumed facilities
(default: mapped community centres), and each carries a `flood_status` of `in_1pct_zone`,
`mapped_outside_1pct` or `unknown_no_fema_data`. Of the 47 in the pilot, 32 are unknown and 15 mapped
outside the 1% zone.

**Pilot results (severe vs baseline):**

- Demand within walking distance of any hub: 53.8% → 53.1%.
- Demand within walking distance of a shelter: 26.4% → 26.3%.
- Demand with no drive route to a shelter: 0% → 2.4%.
- 2 tracts are fully disconnected; 20 tracts lose walk access; 23 tracts see longer drives.

## Reproduce

```bash
python scripts/process_data.py --only derived     # vehicle_access + edge_flood_exposure
```
```bash
curl -s -X POST localhost:8000/api/v1/regions/houston-sw-pilot/accessibility/analyze \
  -H 'content-type: application/json' -d '{"scenario":"severe"}'
```
