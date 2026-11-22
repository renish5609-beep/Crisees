"use client";

import { ArrowRight, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Note, Section, Stat, fmt } from "@/components/ui";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { RegionSummary } from "@/lib/types";

const REAL_VS_HYPOTHETICAL: [string, string, "real" | "model" | "hyp"][] = [
  ["Census tracts, population, car-free households, poverty, disability", "ACS 2020–2024, TIGER 2024", "real"],
  ["Road network (88,404 nodes, 199,542 directed edges)", "OpenStreetMap via Overture Maps", "real"],
  ["FEMA flood zones (Fort Bend side only, about 52% of area)", "FEMA FIRM 48157C", "real"],
  ["Assistance demand: 50% of residents in car-free households", "Estimate + assumption", "model"],
  ["Flood road closures", "Hypothetical rules", "hyp"],
  ["Vehicles, hub and shelter capacities", "Hypothetical budget", "hyp"],
  ["Selected hubs and trips", "Optimisation output", "model"],
];

export function Overview({ startDemo }: { startDemo: () => void }) {
  const ws = useWorkspace();
  const [summary, setSummary] = useState<RegionSummary | null>(null);
  useEffect(() => {
    const c = new AbortController();
    api.summary(ws.regionId, c.signal).then(setSummary).catch(() => undefined);
    return () => c.abort();
  }, [ws.regionId]);
  const acc = ws.scenario.data?.accessibility.summary;
  const pop = summary?.population;
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <p className="text-sm text-water">Southwest Houston pilot · Harris and Fort Bend counties</p>
        <h2 className="text-2xl font-semibold leading-tight tracking-tight">Find the gaps. Plan the response.</h2>
        <p className="text-sm leading-relaxed text-muted">
          Crisees estimates where residents without a car would struggle to reach evacuation help during a flood, simulates hypothetical road
          disruptions, and uses mathematical optimisation to test where limited pickup hubs and vehicles would help most.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button onClick={startDemo}><Play size={15} aria-hidden /> Run guided demo</Button>
          <Button variant="secondary" onClick={() => ws.setView("planner")}>Plan an intervention <ArrowRight size={15} aria-hidden /></Button>
        </div>
      </header>

      <Section title="The study area">
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Residents" value={fmt.int(pop?.total_population)} sub="ACS 2020–2024" />
          <Stat label="Households without a vehicle" value={fmt.int(pop?.households_no_vehicle)} sub={pop ? `${fmt.pctRaw(pop.pct_households_no_vehicle)} of households` : ""} />
          <Stat label="Estimated assistance demand" value={fmt.int(acc?.total_demand_est)} sub="persons (modelled)" />
          <Stat label="Demand within 800 m of a hub" value={fmt.pct(acc?.baseline.demand_share_within_walk_of_hub)} sub="intact network" />
        </div>
      </Section>

      <Section title="What is real and what is hypothetical">
        <ul className="space-y-1.5 text-sm">
          {REAL_VS_HYPOTHETICAL.map(([what, src, kind]) => (
            <li key={what} className="flex items-start gap-2">
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${kind === "real" ? "bg-water" : kind === "model" ? "bg-[#7ee0b5]" : "bg-sediment"}`} aria-hidden />
              <span className="flex-1 text-ink/90">{what}</span>
              <span className="shrink-0 text-xs text-muted">{src}</span>
            </li>
          ))}
        </ul>
        <p className="flex gap-4 text-xs text-muted">
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-water" />Public data</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#7ee0b5]" />Model output</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-sediment" />Hypothetical</span>
        </p>
      </Section>

      <Section title="Explore">
        <div className="grid gap-2">
          {([["scenario", "Scenario Lab", "Simulate flood-related road closures"], ["access", "Accessibility", "See which tracts lose walk or drive access"],
            ["planner", "Intervention Planner", "Optimise hubs, vehicles and shelter use"], ["impact", "Impact Analysis", "Compare outcomes with and without a plan"]] as const).map(([v, t, d]) => (
            <button key={v} onClick={() => ws.setView(v)} className="flex items-center justify-between rounded-lg border border-rule px-3 py-2.5 text-left hover:border-water/60">
              <span><span className="block text-sm font-medium">{t}</span><span className="text-xs text-muted">{d}</span></span>
              <ArrowRight size={15} className="text-muted" aria-hidden />
            </button>
          ))}
        </div>
      </Section>
      <Note tone="warn">
        Crisees is a research and planning prototype. It is not an emergency warning, evacuation order, verified shelter directory, or dispatch service.
      </Note>
    </div>
  );
}
