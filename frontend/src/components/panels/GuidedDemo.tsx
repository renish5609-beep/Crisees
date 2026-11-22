"use client";

import { ChevronLeft, ChevronRight, Play, X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { LayerToggles } from "@/components/map/config";
import { Badge, Button, ErrorCard, Note, Stat, Working, fmt } from "@/components/ui";
import { DEFAULT_PARAMS, planKey, scenarioKey } from "@/lib/params";
import { useWorkspace } from "@/lib/store";
import type { ThemeId } from "@/lib/themes";
import { ComparisonView } from "./Impact";
import { SolverBadges } from "./Planner";

interface StepCtx {
  setTheme: (t: ThemeId) => void;
  setLayers: (fn: (l: LayerToggles) => LayerToggles) => void;
  frame: (bbox: [number, number, number, number] | null) => void;
}

const STUDY_BBOX: [number, number, number, number] = [-95.66523, 29.549161, -95.474078, 29.729579];

type Coords = number[] | Coords[];
function bboxOf(coordsList: Coords[]): [number, number, number, number] | null {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const walk = (c: Coords) => {
    if (typeof c[0] === "number") {
      const [x, y] = c as number[];
      w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y);
    } else (c as Coords[]).forEach(walk);
  };
  coordsList.forEach(walk);
  return Number.isFinite(w) ? [w, s, e, n] : null;
}

const STEPS = [
  "The transportation assistance gap",
  "A severe hypothetical flood",
  "Where access deteriorates",
  "A limited resource budget",
  "Run the optimiser",
  "Recommended pickup hubs",
  "With and without intervention",
  "Trade-offs and limitations",
];

export function GuidedDemo({ step, setStep, exit, ctx }: { step: number; setStep: (n: number) => void; exit: () => void; ctx: StepCtx }) {
  const ws = useWorkspace();
  const entered = useRef<number | null>(null);
  const P = DEFAULT_PARAMS; // fixed, reproducible demo inputs (severe, seed 2017, default budget)

  const closureBox = bboxOf((ws.scenario.data?.closures?.features ?? []).map((f) => (f.geometry?.coordinates ?? []) as Coords));
  const hubBox = bboxOf((ws.plan.data?.hubs ?? []).map((h) => [h.lon, h.lat]));
  // Frame the map for the step once its data exists.
  useEffect(() => {
    if (step === 0 || step === 3 || step === 7) ctx.frame(STUDY_BBOX);
    if ((step === 1 || step === 2) && closureBox) ctx.frame(closureBox);
    if (step === 5 && hubBox) ctx.frame(hubBox);
  }, [step, closureBox?.join(), hubBox?.join()]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (entered.current === step) return;
    entered.current = step;
    const L = (o: Partial<LayerToggles>) => ctx.setLayers((l) => ({ ...l, ...o }));
    if (step === 0) {
      ws.setParams(() => structuredClone(P));
      ctx.setTheme("demand_est");
      L({ closures: false, floodZones: true, coverage: true, selectedHubs: false, allocations: false });
      if (ws.scenario.key !== scenarioKey(P) && ws.scenario.status !== "loading") void ws.runScenario(P);
    } else if (step === 1) {
      ctx.setTheme("pct_households_no_vehicle");
      L({ closures: true, floodZones: true, coverage: true });
    } else if (step === 2) {
      ctx.setTheme("newly_no_drive_route_share");
      L({ closures: true });
    } else if (step === 5) {
      ctx.setTheme("plan_coverage");
      L({ selectedHubs: true, allocations: true, shelters: true });
    } else if (step === 6) {
      if (ws.comparison.status !== "loading") void ws.runCompare(P);
    }
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  const ev = ws.scenario.data?.evaluation;
  const sum = ws.scenario.data?.accessibility.summary;
  const plan = ws.plan.key === planKey(P) ? ws.plan.data : undefined;
  const cmp = ws.comparison.data;

  const body = (() => {
    switch (step) {
      case 0:
        return (
          <>
            <p>In this part of southwest Houston, {fmt.int(sum?.total_demand_est)} people are estimated to need help evacuating: half of the residents of households without a vehicle (ACS 2020–2024).</p>
            <p>The map shades each census tract by that estimated demand. Hatched amber marks where no FEMA flood data is loaded: hazard there is <em>unknown</em>, not zero.</p>
            {ws.scenario.status === "loading" && <Working label="Loading real data" startedAt={ws.scenario.startedAt} />}
          </>
        );
      case 1:
        return ev ? (
          <>
            <p>We apply the <strong>severe</strong> hypothetical rules (seed {ev.spec.seed}): roads in and near FEMA flood zones close. Red lines are simulated closures.</p>
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Closed road segments" value={fmt.int(ev.closures.closed_segments)} tone="bad" />
              <Stat label="Closed length" value={`${fmt.dec(ev.closures.closed_length_km)} km`} />
            </div>
            <Note tone="warn">Closures appear only where FEMA data exists (Fort Bend). The Harris side is unknown, so this is a lower bound.</Note>
          </>
        ) : <Working label="Simulating" startedAt={ws.scenario.status === "loading" ? ws.scenario.startedAt : undefined} />;
      case 2:
        return sum ? (
          <>
            <p>Origins cut off from every drive route to a shelter are shaded red.</p>
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Origins losing all drive routes" value={fmt.int(ev?.access_change.origins_losing_all_drive_routes_to_shelters as number)} tone="bad" />
              <Stat label="Demand newly without a route" value={fmt.int(sum.demand_newly_without_drive_route)} sub="persons" />
              <Stat label="Tracts disconnected" value={fmt.int(sum.tracts_disconnected_from_shelters)} />
              <Stat label="Tracts losing walk access" value={fmt.int(sum.tracts_with_walk_access_loss)} />
            </div>
          </>
        ) : null;
      case 3:
        return (
          <>
            <p>A deliberately limited, hypothetical budget:</p>
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <li>{P.max_active_hubs} pickup hubs</li><li>{P.vehicles} vehicles × {P.vehicle_capacity} seats</li>
              <li>{P.horizon_min / 60}-hour horizon</li><li>{P.shelter_capacity} persons per shelter</li>
              <li>{P.walk_max_m} m maximum walk</li><li>Equity-weighted objective</li>
            </ul>
            <p className="text-muted">Candidate hubs are mapped schools, libraries and civic buildings (unverified). Assumed shelters are community centres.</p>
          </>
        );
      case 4:
        return (
          <>
            <p>The optimiser chooses which hubs to open and how many vehicle trips carry people to shelters with space, on the flooded network.</p>
            <Button onClick={() => void ws.runOptimize(P)} disabled={ws.plan.status === "loading"}><Play size={15} aria-hidden /> Run the optimiser</Button>
            {ws.plan.status === "loading" && <Working label="Solving MILP" startedAt={ws.plan.startedAt} />}
            {ws.plan.status === "error" && <ErrorCard error={ws.plan.error} what="Optimisation" onRetry={() => void ws.runOptimize(P)} />}
            {plan && <><SolverBadges r={plan} /><p>Solved: {plan.totals.active_hubs} hubs, {plan.totals.vehicle_trips} vehicle trips.</p></>}
          </>
        );
      case 5:
        return plan ? (
          <>
            <p>Green circles are the selected hubs; dashed lines show which shelters they send people to (allocation, not routes).</p>
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Assisted via the plan" value={fmt.int(plan.totals.served)} tone="good" />
              <Stat label="Still unmet" value={fmt.int(plan.totals.unmet)} tone="warn" />
            </div>
            <ol className="list-decimal space-y-0.5 pl-5 text-sm">
              {[...plan.hubs].sort((a, b) => b.persons_assigned - a.persons_assigned).slice(0, 4).map((h) => (
                <li key={h.hub_id}><button className="hover:text-water" onClick={() => ws.selectHub(h.hub_id)}>{h.name}</button> <span className="text-muted">{fmt.int(h.persons_assigned)} people</span></li>
              ))}
            </ol>
          </>
        ) : <Note tone="warn">Run the optimiser in the previous step first.</Note>;
      case 6:
        return (
          <>
            {ws.comparison.status === "loading" && <Working label="Solving 5 counterfactual cases" startedAt={ws.comparison.startedAt} />}
            {ws.comparison.status === "error" && <ErrorCard error={ws.comparison.error} what="Comparison" onRetry={() => void ws.runCompare(P)} />}
            {cmp && <ComparisonView c={cmp} />}
          </>
        );
      default: {
        const eq = cmp?.cases.find((c) => c.case === "disrupted_equity_optimized");
        return (
          <>
            <ul className="list-disc space-y-1.5 pl-4">
              {cmp?.findings.map((f) => <li key={f}>{f}</li>)}
              {eq && <li>{fmt.int(eq.binding_constraints.demand_without_any_walkable_hub_or_shelter)} people have no candidate hub or shelter within walking distance. More sites or door-to-door service would be needed.</li>}
              {eq && <li>Lowest-priority tracts reach only {fmt.pct(eq.distribution_by_priority_tercile.tercile_1?.coverage)} coverage under the equity plan.</li>}
            </ul>
            <Note tone="warn">Flood closures, participation, fleet and capacities are hypothetical. Facilities are not verified shelters. FEMA data covers about 52% of the area. These are planning estimates, not emergency instructions.</Note>
          </>
        );
      }
    }
  })();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Badge tone="info">Guided demo · step {step + 1} of {STEPS.length}</Badge>
        <button onClick={exit} className="rounded p-1 text-muted hover:bg-raised hover:text-ink" aria-label="Exit guided demo"><X size={16} /></button>
      </div>
      <div className="flex gap-1" aria-hidden>
        {STEPS.map((_, i) => <span key={i} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-water" : "bg-raised"}`} />)}
      </div>
      <h2 className="text-xl font-semibold tracking-tight">{STEPS[step]}</h2>
      <div key={step} className="crisees-in space-y-3 text-sm leading-relaxed text-ink/90">{body}</div>
      <div className="flex justify-between pt-2">
        <Button variant="secondary" onClick={() => setStep(step - 1)} disabled={step === 0}><ChevronLeft size={15} aria-hidden /> Back</Button>
        {step < STEPS.length - 1 ? (
          <Button onClick={() => setStep(step + 1)} disabled={(step === 4 && !plan) || (step === 0 && !sum)}>Next <ChevronRight size={15} aria-hidden /></Button>
        ) : <Button onClick={exit}>Finish</Button>}
      </div>
    </div>
  );
}
