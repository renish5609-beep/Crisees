# Devpost submission: Crisees

Draft for your review. **Do not submit until the demo video link is added and you approve.**

| Field | Value |
| --- | --- |
| Project title | Crisees |
| Tagline | Find the gaps. Plan the response. |
| Public application | https://crisees-drea7.vercel.app |
| API (for judges) | https://crisees-api-drea7.vercel.app/docs |
| GitHub repository | https://github.com/renish5609-beep/Crisees |
| Demo video | **PENDING: being recorded separately by the team; add the link before submitting** |
| Screenshots | `docs/img/` (real captures of the live production app) |

**Tagline:** Find the gaps. Plan the response.

**Track:** EvoHacks II: Projects for Social Good

## Inspiration

When Hurricane Harvey flooded Houston in 2017, the people with the fewest options were often those without
a car. Evacuation plans tend to assume people can drive themselves. In southwest Houston, about one in ten
households has no vehicle, and in some tracts it is nearly four in ten. We wanted a tool that asks a
specific, uncomfortable question: when flooding cuts the roads, who loses access to help, and where should
a planner with only a few buses put them?

## What it does

Crisees is an equity-aware evacuation planning prototype for 151 census tracts in southwest Houston
(Harris and Fort Bend counties).

- **Estimates need from public data.** Census household-size tables count people in car-free
  households. A stated 50% participation assumption turns that into about 23,000 people who might need
  assisted evacuation.
- **Simulates hypothetical flood disruption.** Roads in and near FEMA flood zones close under
  transparent, seeded rules. Areas without FEMA data are explicitly shown as unknown, never as safe.
- **Measures access.** Walking access to pickup points and drive routes to shelters are computed on the
  real 200,000-edge road network.
- **Optimizes an intervention.** A mixed-integer program chooses which temporary pickup hubs to open
  and how many whole vehicle trips to run. Someone counts as helped only if a vehicle can carry them to a
  shelter with space in time.
- **Compares counterfactuals honestly.** The comparison covers: no intervention; an equity-weighted
  plan; an equal-weight plan; and reusing baseline hubs during the flood.

In the reproducible demo (severe scenario, 12 hubs, 15 buses), modelled assistance rises from 5,214 to
9,493 people, an increase of 18.6 percentage points. Equity weighting does **not** increase that total; it
shifts coverage toward higher-poverty, higher-disability neighbourhoods. The app also shows the limit: about
8,800 people have no candidate site within walking distance at all.

## How we built it

- **Data pipeline (Python):**
  - ACS 2020–2024 and TIGER 2024 from the Census Bureau;
  - CDC SVI 2020;
  - FEMA flood hazard polygons;
  - roads and facilities from OpenStreetMap via Overture Maps.

  Every file carries source, retrieval time, provider and checksum, and missing values are never
  turned into zeros.
- **Routing:** an immutable array graph with SciPy's compiled multi-source Dijkstra. Closures are masks,
  so the baseline is never mutated.
- **Scenarios:** SHA-256-seeded sampling per road segment, so every scenario is exactly reproducible.
- **Optimization:** a MILP solved with HiGHS through SciPy, with demand conservation, hub and shelter
  capacity, hub-to-shelter flow balance, integer trips and a fleet-time budget. Every solution is
  re-verified against all constraints independently of the solver.
- **API:** FastAPI with typed Pydantic contracts, threadpool execution for CPU work, bounded inputs,
  time limits and result caching.
- **Frontend:**
  - Next.js, TypeScript and Tailwind;
  - a MapLibre map, Recharts charts and a typed API client with cancellation and stale-response
    protection;
  - an eight-step guided demo that calls the real backend at every step.
- **Testing:**
  - 157 backend tests, most on small graphs with hand-computed answers, plus end-to-end runs on the
    real Houston data;
  - frontend unit tests;
  - a Playwright browser test that checks the numbers on screen match the API.

## Challenges

- **Data access.** Several official endpoints (FEMA, CDC, Overpass) were unreachable from our build
  environment. We added provider fallbacks and recorded exactly which source fed each dataset. One Census
  table was blocked by a web firewall that returned an error page with HTTP 200, and we caught it with
  content checks.
- **Honesty about gaps.** FEMA data covers only about 52% of the area. We had to make "unknown" a
  first-class state in the data model, the scenario rules and the map.
- **Not double counting people.** Poverty, disability and age overlap, so they set priority and never
  add people to demand.
- **Correctness traps.** Building a sparse matrix silently summed parallel road edges, and we caught it in
  testing. "Reaching a pickup point" had to be separated from "being evacuated" in the model.
- **Free serverless deployment.** The geospatial Python stack is about 550 MB, more than twice Vercel's
  250 MB function limit. At build time we verify the checksummed data release, convert it to a
  pyarrow-free bundle, and prune unused libraries, then re-ran every endpoint with pyarrow blocked.

## Accomplishments we're proud of

- A real optimization model whose outputs are independently checked, with solver status and gap always
  shown.
- A guided demo that runs genuine computations end to end in under three minutes.
- Results that report "no change" when there is no change. The equity-versus-equal comparison says plainly
  that the total doesn't increase.

## What we learned

The most useful output of an equity model is often a limit, not a recommendation: about 8,800 people have
no candidate site within walking distance. More buses don't fix that; more sites or door-to-door service
would. We also learned how much rigor it takes to make public data say only what it actually supports.

## What's next

- Ingest full FEMA coverage for Harris County, and observed flood extents for validation.
- Add a pedestrian network and block-group demand, then test against the demand and participation
  assumptions with sensitivity sweeps in the UI.
- Add vehicle scheduling (depot, sequencing) on top of the capacity model.
- Work with emergency-management practitioners to validate candidate sites and assumptions. No such
  partnership exists today.

## Built with

Python, FastAPI, Pydantic, GeoPandas, Shapely, SciPy (HiGHS), NetworkX, OSMnx, PyArrow, Next.js,
TypeScript, Tailwind CSS, MapLibre GL JS, Recharts, Lucide, zod, Vitest, Playwright, Vercel, GitHub Releases.

## Responsible use

Crisees is a research and planning prototype. It is not an emergency warning, evacuation order, verified
shelter directory or dispatch service.

- All flood closures, budgets and capacities are hypothetical.
- Mapped facilities are not verified shelters.
- Results are modelled outcomes, not demonstrated impact.
- No real users, partners or deployments are claimed.

## Links

- Live app: https://crisees-drea7.vercel.app. Open it once before judging: the first request after an idle
  period wakes the serverless API, about 10 s.
- API docs: https://crisees-api-drea7.vercel.app/docs
- Code: https://github.com/renish5609-beep/Crisees
- Data release: https://github.com/renish5609-beep/Crisees/releases/tag/data-v1
- Demo video: **pending (being recorded separately)**
