"use client";

import { Building2, CheckCircle2, ChevronRight, ShieldAlert, Truck, XCircle } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, ErrorCard, Meter, Note, STATUS_TEXT, Section, Segmented, Slider, Stat, Working, fmt } from "@/components/ui";
import { LIMITS } from "@/lib/params";
import { useWorkspace } from "@/lib/store";
import type { OptimizationResult } from "@/lib/types";

export function ResourceControls({ compact = false }: { compact?: boolean }) {
  const ws = useWorkspace();
  const p = ws.params;
  const set = <K extends keyof typeof p>(k: K) => (v: (typeof p)[K]) => ws.setParams((x) => ({ ...x, [k]: v }));
  return (
    <div className="space-y-4">
      <Slider label="Pickup hubs to activate (max)" value={p.max_active_hubs} onChange={set("max_active_hubs")} {...LIMITS.max_active_hubs} />
      <Slider label="Vehicles" value={p.vehicles} onChange={set("vehicles")} {...LIMITS.vehicles} />
      <Slider label="Seats per vehicle" value={p.vehicle_capacity} onChange={set("vehicle_capacity")} {...LIMITS.vehicle_capacity} />
      <Slider label="Planning horizon" value={p.horizon_min} onChange={set("horizon_min")} {...LIMITS.horizon_min} />
      {!compact && <Slider label="Shelter capacity (each)" value={p.shelter_capacity} onChange={set("shelter_capacity")} {...LIMITS.shelter_capacity} />}
      {!compact && <Slider label="Hub throughput (each)" value={p.hub_capacity} onChange={set("hub_capacity")} {...LIMITS.hub_capacity} />}
      {!compact && <Slider label="Maximum walking distance" value={p.walk_max_m} onChange={set("walk_max_m")} {...LIMITS.walk_max_m} />}
      <div className="space-y-1.5">
        <p className="text-sm text-ink/90">Objective weighting</p>
        <Segmented label="Objective weighting" value={p.weights} onChange={set("weights")}
          options={[{ value: "equity", label: "Equity-weighted" }, { value: "equal", label: "Equal weights" }]} />
        <p className="text-xs leading-relaxed text-muted">
          Equity weights raise priority for tracts with higher poverty and disability rates (ranks, mean 1). They never add people to demand.
        </p>
      </div>
    </div>
  );
}

export function SolverBadges({ r }: { r: OptimizationResult }) {
  const st = STATUS_TEXT[r.solver.status] ?? { label: r.solver.status, tone: "bad" as const };
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge tone={st.tone} title={r.solver.optimality_claim}>{st.label}</Badge>
      <Badge title="Relative MIP gap reported by HiGHS">gap {r.solver.mip_gap == null ? "n/a" : `${(r.solver.mip_gap * 100).toFixed(3)}%`}</Badge>
      <Badge tone={r.constraint_check.feasible ? "good" : "bad"} title="Every constraint recomputed independently of the solver">
        {r.constraint_check.feasible ? <CheckCircle2 size={12} aria-hidden /> : <XCircle size={12} aria-hidden />}
        Constraints {r.constraint_check.feasible ? "verified" : "VIOLATED"}
      </Badge>
      <Badge>solve {r.solver.solve_seconds.toFixed(2)} s</Badge>
    </div>
  );
}

export function Planner() {
  const ws = useWorkspace();
  const slot = ws.plan;
  const r = slot.data;
  const stale = slot.status !== "idle" && slot.key !== ws.keys.plan;
  const optimize = () => {
    if (ws.scenario.key !== ws.keys.scenario) void ws.runScenario();
    void ws.runOptimize();
  };
  return (
    <div className="space-y-6">
      <header>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Truck size={18} aria-hidden className="text-water" /> Intervention Planner</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          Choose a hypothetical budget. A mixed-integer program (HiGHS) picks which pickup hubs to open and how many vehicle trips carry people to shelters with space, on the{" "}
          <span className="text-ink">{ws.params.scenario.preset}</span> network.
        </p>
      </header>
      <Section title="Resource budget (hypothetical)">
        <ResourceControls />
      </Section>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={optimize} disabled={slot.status === "loading" || ws.errors.length > 0}>
          <Truck size={15} aria-hidden /> Optimize response
        </Button>
        {slot.status === "loading" && <Working label="Solving optimisation model" startedAt={slot.startedAt} />}
      </div>
      {ws.errors.map((e) => <p key={e} className="text-sm text-alarm">{e}</p>)}
      {stale && slot.status !== "loading" && <Note tone="warn">The plan below was computed for different inputs. Optimize again to update it.</Note>}
      {slot.status === "error" && <ErrorCard error={slot.error} what="Optimisation" onRetry={optimize} />}
      {!r && slot.status === "idle" && <Note>No plan yet. Set a budget and select Optimize response; results take about 1 s.</Note>}
      {r && <PlanResults r={r} />}
    </div>
  );
}

export function PlanResults({ r }: { r: OptimizationResult }) {
  const ws = useWorkspace();
  const t = r.totals;
  const b = r.binding_constraints;
  const hubs = [...r.hubs].sort((a, b2) => b2.persons_assigned - a.persons_assigned);
  const terc = r.distribution_by_priority_tercile;
  const [used, cap] = b.hub_budget_used.split("/").map(Number);
  return (
    <div className="crisees-in space-y-6">
      <Section title="Optimised plan" aside={<SolverBadges r={r} />}>
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Estimated people assisted" value={fmt.int(t.served)} sub={`of ${fmt.int(t.demand_est)} estimated demand`} tone="good" />
          <Stat label="Unmet estimated need" value={fmt.int(t.unmet)} sub={`coverage ${fmt.pct(t.coverage)}`} tone={t.unmet > 0 ? "warn" : "good"} />
          <Stat label="Via pickup hubs + vehicles" value={fmt.int(t.served_via_hubs)} sub={`${t.vehicle_trips} trips · ${fmt.dec(t.mean_bus_drive_min)} min avg drive`} />
          <Stat label="Walk directly to a shelter" value={fmt.int(t.served_by_direct_walk_to_shelter)} sub={`mean hub walk ${fmt.int(t.mean_walk_m_served_via_hub)} m`} />
        </div>
      </Section>

      <Section title="What limits the plan (binding constraints)">
        <div className="space-y-2.5">
          <Meter label={`Hub budget used (${b.hub_budget_used})`} value={cap ? used / cap : null} tone={used >= cap ? "warn" : "info"} />
          <Meter label="Fleet time used" value={t.fleet_utilization} tone={b.fleet_time_binding ? "warn" : "info"} />
          <Meter label={`Shelters full (${b.shelters_at_capacity} of ${b.shelters_used} used)`} value={b.shelters_used ? b.shelters_at_capacity / b.shelters_used : null} tone="warn" />
        </div>
        <Note tone="warn">
          {fmt.int(b.demand_without_any_walkable_hub_or_shelter)} persons of demand have no candidate hub or shelter within {ws.params.walk_max_m} m.
          No allocation can reach them without more sites, longer walks or door-to-door service.
        </Note>
      </Section>

      <Section title="Outcome by priority tercile" aside={<Badge>tracts ranked by equity weight</Badge>}>
        <div className="space-y-2">
          {(["tercile_3", "tercile_2", "tercile_1"] as const).map((k) => terc[k] && (
            <Meter key={k} label={`${k === "tercile_3" ? "Highest" : k === "tercile_2" ? "Middle" : "Lowest"} priority: ${fmt.int(terc[k].served)} of ${fmt.int(terc[k].demand)}`} value={terc[k].coverage} />
          ))}
        </div>
      </Section>

      <Section title={`Selected pickup hubs (${hubs.length})`}>
        <Note>
          Why these hubs: each reaches priority-weighted demand within walking distance and has a feasible round trip to a shelter with spare capacity.
          Hubs are ranked by persons assigned.
        </Note>
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hubs.map((h, i) => ({ n: `${i + 1}`, name: h.name, persons: h.persons_assigned }))} margin={{ left: -18, right: 4 }}>
              <XAxis dataKey="n" stroke="#8597a3" fontSize={11} />
              <YAxis stroke="#8597a3" fontSize={11} />
              <Tooltip contentStyle={{ background: "#111f2b", border: "1px solid #233847", fontSize: 12 }} labelFormatter={(_, p) => String(p?.[0]?.payload?.name ?? "")} />
              <Bar dataKey="persons" name="Persons assigned" fill="#7ee0b5" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ul className="space-y-1.5">
          {hubs.map((h, i) => {
            const open = ws.selectedHub === h.hub_id;
            return (
              <li key={h.hub_id} className={`rounded-lg border ${open ? "border-[#7ee0b5]/60 bg-ground/60" : "border-rule"}`}>
                <button onClick={() => ws.selectHub(open ? null : h.hub_id)} aria-expanded={open}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm">
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[#7ee0b5] text-xs font-semibold text-ground">{i + 1}</span>
                  <span className="min-w-0 flex-1 truncate">{h.name ?? h.hub_id}</span>
                  <span className="tabular-nums text-muted">{fmt.int(h.persons_assigned)}</span>
                  <ChevronRight size={14} className={`text-muted transition-transform ${open ? "rotate-90" : ""}`} aria-hidden />
                </button>
                {open && (
                  <div className="crisees-in space-y-2 border-t border-rule px-3 py-2 text-sm">
                    <p className="text-muted"><Building2 size={13} className="mr-1 inline" aria-hidden />{h.category} · {h.origins_served} origin cells · mean walk {fmt.int(h.mean_walk_m)} m · {fmt.pct(h.capacity_utilization, 0)} of hub capacity</p>
                    <p className="text-xs text-muted">Flood status at site: {h.flood_status.replaceAll("_", " ")}</p>
                    <table className="w-full text-xs">
                      <thead><tr className="text-muted"><th className="text-left font-normal">To assumed shelter</th><th className="text-right font-normal">Persons</th><th className="text-right font-normal">Trips</th><th className="text-right font-normal">Drive</th></tr></thead>
                      <tbody>
                        {h.legs.map((l) => (
                          <tr key={l.shelter_id}><td className="truncate py-0.5 pr-2">{l.shelter_name ?? l.shelter_id}</td><td className="text-right tabular-nums">{fmt.dec(l.persons, 0)}</td><td className="text-right tabular-nums">{l.trips}</td><td className="text-right tabular-nums">{fmt.dec(l.drive_min)} min</td></tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="flex gap-1.5 text-xs text-sediment"><ShieldAlert size={13} className="mt-0.5 shrink-0" aria-hidden />
                      Unverified candidate. Schools and private properties require owner authorization before any real-world use.</p>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        <Note>Dashed map lines connect hubs to their assigned shelters. They show allocation, not driving routes.</Note>
      </Section>
      <details className="text-xs text-muted">
        <summary className="cursor-pointer text-ink/80">Solver and verification details</summary>
        <div className="mt-2 space-y-1">
          <p>{r.solver.engine}. {r.solver.optimality_claim}</p>
          <p>Model: {Object.entries(r.solver.model_size).map(([k, v]) => `${k.replaceAll("_", " ")} ${v}`).join(" · ")}</p>
          <p>Max constraint violation: {Object.values(r.constraint_check.max_violation ?? {}).reduce((a, b2) => Math.max(a, b2), 0)}</p>
          <p>Scenario {r.scenario_id} · {r.cache === "hit" ? "cached result" : "fresh solve"}</p>
          <p>{r.disclaimer}</p>
        </div>
      </details>
    </div>
  );
}
