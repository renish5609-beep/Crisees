"use client";

import { X } from "lucide-react";
import { Badge, fmt } from "@/components/ui";
import { useWorkspace } from "@/lib/store";

/** Details for one tract: observed ACS values, modelled access, plan outcome. */
export function TractInspector() {
  const ws = useWorkspace();
  const g = ws.selectedTract;
  if (!g) return null;
  const access = ws.scenario.data?.accessibility.features.find((f) => f.properties.geoid === g)?.properties;
  const demo = ws.demographics.get(g);
  const plan = ws.plan.data?.tracts.find((t) => t.geoid === g);
  const county = g.startsWith("48157") ? "Fort Bend County" : "Harris County";
  const d = demo?.demographics;
  const row = (label: string, value: string, unknown = false) => (
    <div className="flex justify-between gap-3 py-1 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className={`text-right tabular-nums ${unknown ? "text-sediment" : "text-ink"}`}>{value}</dd>
    </div>
  );
  return (
    <section aria-label={`Tract ${g} details`} className="crisees-in rounded-lg border border-water/30 bg-ground/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium">{access?.name ?? `Tract ${g}`}</h3>
          <p className="text-xs text-muted">{county} · GEOID {g}</p>
        </div>
        <button onClick={() => ws.selectTract(null)} className="rounded p-1 text-muted hover:bg-raised hover:text-ink" aria-label="Close tract details">
          <X size={16} />
        </button>
      </div>
      <p className="mt-3 text-xs font-medium text-muted">Observed (ACS 2020–2024, 5-year)</p>
      <dl className="divide-y divide-rule/50">
        {row("Population", fmt.int(d?.total_population), d?.total_population == null)}
        {row("Households without a vehicle", d ? `${fmt.int(d.households_no_vehicle)} (${fmt.pctRaw(d.pct_households_no_vehicle)})` : "Unavailable", !d)}
        {row("Below poverty", fmt.pctRaw(d?.pct_below_poverty), d?.pct_below_poverty == null)}
        {row("Age 65+", fmt.pctRaw(d?.pct_65_plus), d?.pct_65_plus == null)}
        {row("With a disability", fmt.pctRaw(d?.pct_with_disability), d?.pct_with_disability == null)}
        {row("CDC SVI 2020 (US percentile)", demo?.vulnerability?.rpl_themes == null ? "Unknown" : demo.vulnerability.rpl_themes.toFixed(2), demo?.vulnerability?.rpl_themes == null)}
      </dl>
      <p className="mt-3 text-xs font-medium text-muted">Modelled access ({ws.scenario.data?.evaluation.spec.name ?? "no scenario"})</p>
      {access ? (
        <dl className="divide-y divide-rule/50">
          {row("Estimated assistance demand", `${fmt.dec(access.demand_est, 0)} persons`)}
          {row("Demand within walk of a hub", `${fmt.pct(access.share_demand_within_walk_of_hub_baseline, 0)} → ${fmt.pct(access.share_demand_within_walk_of_hub, 0)}`)}
          {row("Drive to nearest assumed shelter", access.drive_min_to_nearest_shelter == null ? "No route (unknown)" : `${fmt.dec(access.drive_min_to_nearest_shelter)} min`, access.drive_min_to_nearest_shelter == null)}
          {row("Demand newly without drive route", fmt.pct(access.newly_no_drive_route_share, 0), (access.newly_no_drive_route_share ?? 0) > 0)}
        </dl>
      ) : <p className="text-sm text-muted">Run a scenario to see modelled access.</p>}
      {access?.disconnected_from_shelters && <div className="mt-2"><Badge tone="bad">Disconnected from all assumed shelters</Badge></div>}
      {plan && (
        <>
          <p className="mt-3 text-xs font-medium text-muted">Optimised plan</p>
          <dl className="divide-y divide-rule/50">
            {row("Served via hubs", `${fmt.dec(plan.served_via_hubs, 0)} persons`)}
            {row("Served by walking to a shelter", `${fmt.dec(plan.served_by_direct_walk, 0)} persons`)}
            {row("Unmet", `${fmt.dec(plan.unmet, 0)} persons`, plan.unmet > 0.5)}
            {row("Priority tercile", plan.priority_tercile === 3 ? "Highest" : plan.priority_tercile === 2 ? "Middle" : "Lowest")}
          </dl>
        </>
      )}
      {d && d.missing_fields.length > 0 && (
        <p className="mt-2 text-xs text-muted">Missing in source: {d.missing_fields.map((m) => m.split(":")[0]).join(", ")}</p>
      )}
    </section>
  );
}
