"use client";

import { Scale } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, CASE_LABELS, ErrorCard, Note, Section, Stat, Working, fmt } from "@/components/ui";
import { useWorkspace } from "@/lib/store";
import type { ComparisonResult } from "@/lib/types";

const SHORT: Record<string, string> = {
  baseline_no_intervention: "Baseline",
  disrupted_no_intervention: "Flood",
  disrupted_equity_optimized: "Flood + equity",
  disrupted_equal_weight_optimized: "Flood + equal",
  baseline_plan_under_disruption: "Reused hubs",
};
const tooltipStyle = { background: "#111f2b", border: "1px solid #233847", fontSize: 12 };

export function ImpactPanel() {
  const ws = useWorkspace();
  const slot = ws.comparison;
  const stale = slot.status !== "idle" && slot.key !== ws.keys.compare;
  const run = () => void ws.runCompare();
  return (
    <div className="space-y-6">
      <header>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Scale size={18} aria-hidden className="text-water" /> Impact Analysis</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          Five counterfactual cases solved with identical demand, budget and scenario inputs. These are modelled outcomes under hypothetical assumptions, not measured impact.
        </p>
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={run} disabled={slot.status === "loading" || ws.errors.length > 0}><Scale size={15} aria-hidden /> Run comparison</Button>
        {slot.status === "loading" && <Working label="Solving 5 cases" startedAt={slot.startedAt} />}
      </div>
      {stale && slot.status !== "loading" && <Note tone="warn">Inputs changed since this comparison ran. Run it again to update.</Note>}
      {slot.status === "error" && <ErrorCard error={slot.error} what="Comparison" onRetry={run} />}
      {!slot.data && slot.status === "idle" && <Note>Uses the scenario and budget from the Scenario Lab and Planner (about 2 s).</Note>}
      {slot.data && <ComparisonView c={slot.data} />}
    </div>
  );
}

export function ComparisonView({ c }: { c: ComparisonResult }) {
  const ws = useWorkspace();
  const by = Object.fromEntries(c.cases.map((x) => [x.case, x]));
  const noInt = by.disrupted_no_intervention?.totals;
  const eq = by.disrupted_equity_optimized?.totals;
  const flat = by.disrupted_equal_weight_optimized?.totals;
  const base = by.baseline_no_intervention?.totals;
  const served = c.cases.map((x) => ({ name: SHORT[x.case] ?? x.case, Assisted: Math.round(x.totals.served), Unmet: Math.round(x.totals.unmet) }));
  const terc = c.cases.map((x) => ({
    name: SHORT[x.case] ?? x.case,
    Lowest: pctOf(x.distribution_by_priority_tercile.tercile_1?.coverage),
    Middle: pctOf(x.distribution_by_priority_tercile.tercile_2?.coverage),
    Highest: pctOf(x.distribution_by_priority_tercile.tercile_3?.coverage),
  }));
  const sameTotal = eq && flat && Math.abs(eq.served - flat.served) < 0.5;
  const gain = eq && noInt ? eq.served - noInt.served : null;
  return (
    <div className="crisees-in space-y-6">
      <Section title="Headline (modelled)">
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Estimated assistance demand" value={fmt.int(eq?.demand_est)} sub="persons, all cases" />
          <Stat label="Flood, no intervention" value={fmt.int(noInt?.served)} sub={`assisted · ${fmt.pct(noInt?.coverage)}`} />
          <Stat label="Flood + optimised plan" value={fmt.int(eq?.served)} sub={`assisted · ${fmt.pct(eq?.coverage)}`} tone="good" />
          <Stat label="Change from intervention" value={fmt.signed(gain)} sub={eq && noInt ? `${((eq.coverage! - noInt.coverage!) * 100).toFixed(1)} percentage points` : ""} tone={gain && gain > 0 ? "good" : "default"} />
        </div>
      </Section>

      <Section title="Assisted vs unmet, by case">
        <div className="h-56" aria-label="Stacked bars of assisted and unmet demand for each case">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={served} margin={{ left: -6, right: 4 }}>
              <CartesianGrid vertical={false} stroke="#233847" />
              <XAxis dataKey="name" stroke="#8597a3" fontSize={10} interval={0} />
              <YAxis stroke="#8597a3" fontSize={11} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => v.toLocaleString("en-US")} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Assisted" stackId="a" fill="#7ee0b5" />
              <Bar dataKey="Unmet" stackId="a" fill="#3a4b58" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Section>

      <Section title="Coverage by priority tercile" aside={<Badge>% of tercile demand</Badge>}>
        <div className="h-56" aria-label="Grouped bars of coverage by priority tercile">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={terc} margin={{ left: -14, right: 4 }}>
              <CartesianGrid vertical={false} stroke="#233847" />
              <XAxis dataKey="name" stroke="#8597a3" fontSize={10} interval={0} />
              <YAxis stroke="#8597a3" fontSize={11} unit="%" />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${v.toFixed(1)}%`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Lowest" fill="#3d4f6b" />
              <Bar dataKey="Middle" fill="#7a5f8f" />
              <Bar dataKey="Highest" fill="#f1a17a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        {sameTotal ? (
          <Note>Equity weighting serves the same total ({fmt.int(eq!.served)}) as equal weighting. It redistributes coverage toward higher-priority tracts; it does not increase the number assisted.</Note>
        ) : eq && flat ? (
          <Note>Equity weighting changes the total assisted by {fmt.signed(eq.served - flat.served, 1)} versus equal weighting.</Note>
        ) : null}
      </Section>

      <Section title="Changes between cases">
        <ul className="space-y-2 text-sm">
          {base && noInt && <Delta label="Flood effect (no intervention)" v={noInt.served - base.served} detail={`coverage ${fmt.pct(base.coverage)} → ${fmt.pct(noInt.coverage)}`} />}
          {eq && noInt && <Delta label="Optimised intervention vs none" v={eq.served - noInt.served} detail={`weighted unmet ${fmt.signed(eq.weighted_unmet_equity_weights - noInt.weighted_unmet_equity_weights, 1)}`} />}
          {eq && flat && <Delta label="Equity vs equal weighting" v={eq.served - flat.served} detail={`priority-weighted unmet ${fmt.signed(eq.weighted_unmet_equity_weights - flat.weighted_unmet_equity_weights, 1)}`} />}
          {by.baseline_plan_under_disruption && eq && <Delta label="Re-choosing hubs for the flood vs reusing baseline hubs" v={eq.served - by.baseline_plan_under_disruption.totals.served} detail={`weighted unmet ${fmt.signed(eq.weighted_unmet_equity_weights - by.baseline_plan_under_disruption.totals.weighted_unmet_equity_weights, 1)}`} />}
        </ul>
      </Section>

      <Section title="Resource use">
        <table className="w-full text-xs">
          <thead><tr className="text-muted"><th className="text-left font-normal">Case</th><th className="text-right font-normal">Hubs</th><th className="text-right font-normal">Trips</th><th className="text-right font-normal">Fleet</th><th className="text-right font-normal">Full shelters</th><th className="text-right font-normal">Solver</th></tr></thead>
          <tbody>
            {c.cases.map((x) => (
              <tr key={x.case} className="border-t border-rule/50">
                <td className="py-1 pr-2">{CASE_LABELS[x.case] ?? x.case}</td>
                <td className="text-right tabular-nums">{x.totals.active_hubs}</td>
                <td className="text-right tabular-nums">{x.totals.vehicle_trips}</td>
                <td className="text-right tabular-nums">{x.totals.fleet_utilization == null ? "–" : `${Math.round(x.totals.fleet_utilization * 100)}%`}</td>
                <td className="text-right tabular-nums">{x.binding_constraints.shelters_at_capacity}</td>
                <td className="text-right">{x.constraint_check_feasible ? "✓" : "✗"} {x.solver_status.replace("optimal_within_gap", "≈opt").replace("optimal", "opt")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Findings (generated from the results)">
        <ul className="list-disc space-y-1.5 pl-4 text-sm text-ink/90">{c.findings.map((f) => <li key={f}>{f}</li>)}</ul>
      </Section>

      <Section title="Most affected communities">
        <ul className="space-y-1 text-sm">
          {c.most_affected_tracts.slice(0, 5).map((t) => (
            <li key={String(t.geoid)}>
              <button onClick={() => ws.selectTract(String(t.geoid))} className="flex w-full justify-between gap-2 rounded px-2 py-1 text-left hover:bg-raised">
                <span>Tract {String(t.geoid)}</span>
                <span className="text-xs tabular-nums text-muted">walk loss {fmt.dec(t.demand_weighted_walk_access_loss as number)} · no route {fmt.dec(t.demand_newly_without_drive_route as number)}</span>
              </button>
            </li>
          ))}
        </ul>
      </Section>
      <Note tone="warn">{c.disclaimer}</Note>
    </div>
  );
}

function Delta({ label, v, detail }: { label: string; v: number; detail: string }) {
  const zero = Math.abs(v) < 0.5;
  return (
    <li className="flex items-baseline justify-between gap-3 rounded-md border border-rule px-3 py-2">
      <span><span className="text-ink/90">{label}</span><span className="block text-xs text-muted">{detail}</span></span>
      <span className={`shrink-0 font-semibold tabular-nums ${zero ? "text-muted" : v > 0 ? "text-[#7ee0b5]" : "text-alarm"}`}>
        {zero ? "no change" : `${fmt.signed(v)} assisted`}
      </span>
    </li>
  );
}

const pctOf = (v: number | null | undefined) => (v == null ? 0 : Number((v * 100).toFixed(1)));
