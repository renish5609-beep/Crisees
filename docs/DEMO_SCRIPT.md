# Demo video script (≤ 3 minutes)

**Setup:** desktop browser at 1440×900 with https://crisees-drea7.vercel.app open on **Overview** and the
status pill reading "API connected".

**Warm up first:** the API is serverless, and its first request after an idle period takes about 10 s.
Click through the guided demo once before recording; later runs come from the server cache and respond
almost instantly.

Numbers below are the reference values from the deterministic demo (severe scenario, seed 2017, default
budget). The app fetches them live; if they ever differ, say what is on screen.

| Time | Screen action | Narration | Expected state |
| --- | --- | --- | --- |
| 0:00–0:15 | Overview, map shaded by demand | "In a flood, people without a car depend on someone else to get out. Crisees is a planning tool that finds where that help may not reach, and tests how to close the gap." | Tagline "Find the gaps. Plan the response."; 585,584 residents; 21,981 car-free households |
| 0:15–0:35 | Click **Run guided demo** (step 1) | "This is southwest Houston: 151 census tracts. Using Census data, we estimate about 23,000 people would need help evacuating. That is half of the residents of car-free households, and the half is a stated assumption. Amber hatching marks where we have no FEMA flood data: unknown, not safe." | Demand choropleth; hatched Harris side |
| 0:35–0:55 | Next (step 2) | "Now a severe hypothetical flood. Roads in and near FEMA flood zones close. These closures are simulated, not observed. It's reproducible from seed 2017." | Map zooms to Fort Bend; red closures; 3,123 segments, 266 km |
| 0:55–1:15 | Next (step 3) | "The routing engine recomputes access on 200,000 road edges. 229 neighbourhood origins, about 560 people of estimated need, lose every drive route to a shelter. Two tracts are cut off entirely." | Red-shaded tracts; 229 / 561 / 2 / 20 |
| 1:15–1:30 | Next (step 4) | "We give the planner a deliberately limited, hypothetical budget: 12 pickup hubs, 15 buses of 40 seats, 8 hours, 400 people per shelter." | Budget list |
| 1:30–1:50 | Next (step 5), click **Run the optimiser** | "This is a real mixed-integer program. It picks hubs and whole bus trips, and only counts someone as helped if a bus can carry them to a shelter with space. It solves in under a second, and we verify every constraint independently." | Badges: "Optimal within gap", "Constraints verified" |
| 1:50–2:10 | Next (step 6); click a hub in the list | "Green circles are the recommended hubs, mostly schools and libraries. Dashed lines show which shelters they feed: allocations, not routes. Every site would need owner authorization." | Hubs and allocation lines; 9,493 assisted; 13,540 unmet |
| 2:10–2:35 | Next (step 7) | "Same inputs, five counterfactuals. Without intervention, about 5,200 people reach help on foot. With the plan, about 9,500: plus 18.6 points. Equity weighting doesn't serve more people; it shifts coverage toward higher-poverty, higher-disability tracts." | Stacked bars; tercile bars; "no change" for equity vs equal |
| 2:35–2:55 | Next (step 8) | "And honestly: 8,800 people have no hub or shelter within walking distance, so no allocation can reach them without more sites or door-to-door service. This is a planning model, not an evacuation order." | Findings and limitations |
| 2:55–3:00 | Cut to the methodology page | "Everything is open: data sources, model and code." | Data & Methodology |

**Keep the distinction clear on camera.** Census, road and FEMA data are observed. Demand is an estimate.
Closures, budgets and capacities are hypothetical. Results are modelled, not measured impact.

**Backup.** If the network is slow, pre-run the demo once before recording; results are cached server-side.
