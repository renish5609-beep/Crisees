"use client";

import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorCard, Note, fmt } from "@/components/ui";
import { ApiError, DEFAULT_REGION, REPO_URL, api } from "@/lib/api";
import type { DatasetStatus, Methodology } from "@/lib/types";

const SOURCES = [
  ["U.S. Census Bureau: American Community Survey 2020–2024 5-year (B01003, B01001, B08201, B17001, C18108)", "https://www.census.gov/programs-surveys/acs"],
  ["U.S. Census Bureau: TIGER/Line 2024 census tracts", "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html"],
  ["CDC/ATSDR Social Vulnerability Index 2020", "https://www.atsdr.cdc.gov/place-health/php/svi/index.html"],
  ["FEMA National Flood Hazard Layer / FIRM database (DFIRM 48157C)", "https://www.fema.gov/flood-maps/national-flood-hazard-layer"],
  ["OpenStreetMap contributors (ODbL), via Overture Maps Foundation", "https://www.openstreetmap.org/copyright"],
  ["Overture Maps Foundation: places and transportation themes", "https://overturemaps.org/"],
];

function H({ id, children }: { id: string; children: React.ReactNode }) {
  return <h2 id={id} className="scroll-mt-4 border-b border-rule pb-1.5 text-lg font-semibold tracking-tight">{children}</h2>;
}

export default function MethodologyPage() {
  const [datasets, setDatasets] = useState<DatasetStatus[] | null>(null);
  const [meth, setMeth] = useState<Methodology | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const load = () => {
    setError(null);
    api.datasets(DEFAULT_REGION).then(setDatasets).catch((e) => setError(e));
    api.methodology(DEFAULT_REGION).then(setMeth).catch((e) => setError(e));
  };
  useEffect(load, []);

  return (
    <div className="h-full overflow-y-auto">
      <article className="mx-auto max-w-3xl space-y-8 px-5 py-8 text-[15px] leading-relaxed text-ink/90">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Data &amp; Methodology</h1>
          <p className="rounded-lg border border-sediment/40 bg-sediment/5 p-3 text-sm text-ink">
            Crisees is a research and planning prototype. It is not an emergency warning, evacuation order, verified shelter directory, or dispatch service.
          </p>
          <nav aria-label="On this page" className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-water">
            {[["what", "What it does"], ["data", "Data sources"], ["demand", "Demand"], ["roads", "Road network"], ["flood", "Flood simulation"],
              ["optimisation", "Optimisation"], ["equity", "Equity weights"], ["limits", "Limitations"]].map(([id, l]) => <a key={id} href={`#${id}`} className="hover:underline">{l}</a>)}
          </nav>
        </header>

        <section className="space-y-3">
          <H id="what">What Crisees does, and for whom</H>
          <p>
            During floods, residents without a private vehicle, and people facing other barriers, can struggle to reach evacuation help. Crisees is built for
            emergency planners, transportation agencies and community organisations who need to see where those gaps are and test how limited resources might
            close them. It estimates assistance demand from public Census data, simulates hypothetical flood-related road closures on the real road network, measures
            access before and after, and solves a mathematical optimisation model to choose temporary pickup hubs and vehicle trips.
          </p>
          <p>
            <strong>Study area:</strong> 151 census tracts in southwest Houston (110 in Harris County, 41 in Fort Bend County): Alief, Sharpstown, Westchase,
            Mission Bend, Stafford and Missouri City, across the Brays and Keegans Bayou watersheds. About 287 km² and 586,000 residents.
          </p>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-muted"><th className="py-1 font-normal">Real public data</th><th className="py-1 font-normal">Model estimates</th><th className="py-1 font-normal">Hypothetical</th></tr></thead>
            <tbody className="align-top">
              <tr>
                <td className="pr-3">Tracts, population, car-free households, poverty, disability, SVI, road network, mapped facilities, FEMA flood zones (part of area)</td>
                <td className="pr-3">Assistance demand, travel times, walk access, selected hubs and trips</td>
                <td>Road closures, participation rate, vehicles, hub and shelter capacities, which facilities act as shelters</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="space-y-3">
          <H id="data">Data sources and live dataset status</H>
          <ul className="space-y-1 text-sm">
            {SOURCES.map(([t, u]) => (
              <li key={u}><a href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-water hover:underline">{t} <ExternalLink size={12} aria-hidden /></a></li>
            ))}
          </ul>
          {error && <ErrorCard error={error} what="Loading dataset status" onRetry={load} />}
          {datasets && (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-muted"><th className="py-1 font-normal">Dataset</th><th className="py-1 text-right font-normal">Records</th><th className="py-1 pl-3 font-normal">Provenance</th><th className="py-1 font-normal">Source</th></tr></thead>
              <tbody>
                {datasets.map((d) => (
                  <tr key={d.dataset} className="border-t border-rule/60 align-top">
                    <td className="py-1.5 pr-2">{d.title}{d.state !== "available" && <span className="ml-1 text-sediment">({d.state})</span>}</td>
                    <td className="py-1.5 text-right tabular-nums">{fmt.int(d.record_count)}</td>
                    <td className="py-1.5 pl-3 text-muted">{d.provenance}</td>
                    <td className="py-1.5 text-xs text-muted">{d.sources[0]?.name ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Note tone="warn">Some primary sources were unreachable when the data was built, so mirrors and fallbacks were used (SVI 2020 via an ArcGIS copy; roads and places via Overture). Every dataset records its provider; see docs/DATA_SOURCES.md.</Note>
        </section>

        <section className="space-y-3">
          <H id="demand">Demographic demand estimation</H>
          <p>
            Demand = participation × persons in zero-vehicle households, where persons = 1·H<sub>1</sub> + 2·H<sub>2</sub> + 3·H<sub>3</sub> + 4.5·H<sub>4+</sub> from ACS table B08201
            (observed household counts by size). Participation is a hypothetical 50%. Poverty, disability and age are never added to demand, because the same
            person can appear in several tables. Tract demand is spread over 500 m sub-tract cells in proportion to residential street length (a housing proxy).
            Missing values stay unknown; they are never treated as zero.
          </p>
        </section>

        <section className="space-y-3">
          <H id="roads">Road-network assumptions</H>
          <p>
            Driving uses the directed network (one-way streets honoured), with posted speeds where reliable (only about 6% of edges) and otherwise road-class
            free-flow speeds{meth ? ` (e.g. residential ${meth.speed_model.class_default_kph.residential} km/h, primary ${meth.speed_model.class_default_kph.primary} km/h)` : ""}.
            Walking uses the same roads, undirected and without motorways, at {meth?.speed_model.walk_speed_m_per_min ?? 80} m/min. That is a proxy, because no
            sidewalk network is available. Shortest paths use compiled multi-source Dijkstra; scenarios never modify the baseline network.
          </p>
        </section>

        <section className="space-y-3">
          <H id="flood">Flood simulation</H>
          <p>
            A FEMA zone marks regulatory exposure, not a confirmed closure. Hypothetical rules close road segments inside or near 1% and 0.2% annual-chance zones
            with stated probabilities. Each segment&apos;s draw comes from SHA-256 of (seed, rule, segment), so a scenario is exactly reproducible. Roads outside FEMA
            coverage are never closed by flood rules: their hazard is unknown, which the map shows with amber hatching.
          </p>
          {meth && (
            <ul className="space-y-1 text-sm">
              {meth.scenario_presets.map((p) => <li key={p.name}><strong className="capitalize">{p.name}:</strong> <span className="text-muted">{p.description}</span></li>)}
            </ul>
          )}
        </section>

        <section className="space-y-3">
          <H id="optimisation">Mathematical optimisation model</H>
          <p>
            A mixed-integer linear program, solved by HiGHS, chooses which candidate hubs to activate (binary), how many people walk to each hub or directly to a
            shelter, how many are carried from each hub to each shelter, and how many whole vehicle trips run on each hub–shelter leg. It minimises
            priority-weighted unmet demand, plus small tie-breaking penalties for walking, driving and opening hubs.
          </p>
          {meth && (
            <>
              <p className="rounded-md bg-ground/60 p-3 font-mono text-xs text-ink/80">minimise {meth.optimization_model.objective}</p>
              <ul className="list-disc space-y-0.5 pl-5 text-sm">{meth.optimization_model.constraints.map((c) => <li key={c}>{c}</li>)}</ul>
              <Note>{meth.optimization_model.approximation} Reaching a hub only counts as assistance if a vehicle carries the person to a shelter with space within the horizon.</Note>
            </>
          )}
          <p>Every solution is re-checked against every constraint independently of the solver, and the solver status and optimality gap are always reported.</p>
        </section>

        <section className="space-y-3">
          <H id="equity">Equity weighting</H>
          <p>{meth?.equity_weights ?? "Loading…"}</p>
          <p>
            The equal-weight baseline sets every weight to 1. In the demonstration scenario both weightings assist the same total number of people. Equity
            weighting shifts which communities are covered; it does not increase the total.
          </p>
        </section>

        <section className="space-y-3">
          <H id="limits">Uncertainty and limitations</H>
          <ul className="list-disc space-y-1 pl-5">
            <li>FEMA flood data covers about 52% of the study area (Fort Bend). Harris County disruption is therefore a lower bound.</li>
            <li>Flood closures, participation, fleet size, hub and shelter capacities are hypothetical planning assumptions.</li>
            <li>Mapped facilities are not verified evacuation shelters. Schools and private properties would require owner authorisation.</li>
            <li>Walking access uses the road network as a proxy; it ignores sidewalks, crossings and individual mobility limits.</li>
            <li>The vehicle model is a fleet-time capacity approximation, not a routing or scheduling solution.</li>
            <li>ACS values are sample estimates with margins of error; the CDC SVI edition (2020) is older than the ACS data (2020–2024).</li>
            <li>Results are modelled outcomes, not demonstrated real-world impact.</li>
          </ul>
          <p className="text-sm">
            Source code, documentation and reproducible commands:{" "}
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-water hover:underline">{REPO_URL.replace("https://", "")} <ExternalLink size={12} aria-hidden /></a>
          </p>
        </section>
      </article>
    </div>
  );
}
