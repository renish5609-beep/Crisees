"use client";

import { Footprints } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, ErrorCard, Note, Section, Stat, Working, fmt } from "@/components/ui";
import { useWorkspace } from "@/lib/store";
import type { ThemeId } from "@/lib/themes";

export function AccessibilityPanel({ setTheme }: { setTheme: (t: ThemeId) => void }) {
  const ws = useWorkspace();
  const slot = ws.scenario;
  const acc = slot.data?.accessibility;
  const sum = acc?.summary;
  const ranked = [...(acc?.features ?? [])]
    .map((f) => f.properties)
    .filter((p) => (p.demand_weighted_walk_access_loss ?? 0) + (p.demand_newly_without_drive_route ?? 0) > 0.05)
    .sort((a, b) => ((b.demand_weighted_walk_access_loss ?? 0) + (b.demand_newly_without_drive_route ?? 0))
      - ((a.demand_weighted_walk_access_loss ?? 0) + (a.demand_newly_without_drive_route ?? 0)))
    .slice(0, 10);
  const chart = ranked.map((p) => ({
    geoid: p.geoid.slice(5),
    full: p.geoid,
    "Lost walk access": Number((p.demand_weighted_walk_access_loss ?? 0).toFixed(1)),
    "Lost drive route": Number((p.demand_newly_without_drive_route ?? 0).toFixed(1)),
  }));

  return (
    <div className="space-y-6">
      <header>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><Footprints size={18} aria-hidden className="text-water" /> Accessibility</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          How estimated assistance demand reaches pickup hubs on foot and shelters by road, before and during the{" "}
          <span className="text-ink">{slot.data?.evaluation.spec.name ?? "selected"}</span> scenario. Click a tract on the map for details.
        </p>
      </header>
      {slot.status === "loading" && <Working label="Computing accessibility" startedAt={slot.startedAt} />}
      {slot.status === "error" && <ErrorCard error={slot.error} what="Accessibility analysis" onRetry={() => void ws.runScenario()} />}
      {sum && (
        <>
          <Section title="Study-area summary (demand-weighted)">
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Estimated assistance demand" value={fmt.int(sum.total_demand_est)} sub="persons, 151 tracts" />
              <Stat label="Tracts disconnected from shelters" value={fmt.int(sum.tracts_disconnected_from_shelters)} tone={sum.tracts_disconnected_from_shelters ? "bad" : "default"} />
              <Stat label="Within walk of a hub" value={fmt.pct(sum.scenario.demand_share_within_walk_of_hub)} sub={`baseline ${fmt.pct(sum.baseline.demand_share_within_walk_of_hub)}`} />
              <Stat label="Within walk of a shelter" value={fmt.pct(sum.scenario.demand_share_within_walk_of_shelter)} sub={`baseline ${fmt.pct(sum.baseline.demand_share_within_walk_of_shelter)}`} />
              <Stat label="No drive route to a shelter" value={fmt.pct(sum.scenario.demand_share_no_drive_route_to_shelter)} sub={`baseline ${fmt.pct(sum.baseline.demand_share_no_drive_route_to_shelter)}`} tone={(sum.scenario.demand_share_no_drive_route_to_shelter ?? 0) > 0 ? "bad" : "default"} />
              <Stat label="Demand newly without drive route" value={fmt.int(sum.demand_newly_without_drive_route)} sub={`${sum.tracts_with_longer_drive} tracts with longer drives`} />
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="text-muted">Map:</span>
              {([["share_demand_within_walk_of_hub", "Walk access"], ["lost_share_within_walk_of_hub", "Walk access lost"], ["newly_no_drive_route_share", "Drive route lost"], ["drive_min_to_nearest_shelter", "Drive time"]] as [ThemeId, string][]).map(([id, l]) => (
                <button key={id} onClick={() => setTheme(id)} className="rounded-full border border-rule px-2 py-0.5 text-ink/90 hover:border-water">{l}</button>
              ))}
            </div>
          </Section>

          <Section title="Most affected tracts" aside={<Badge>persons of demand</Badge>}>
            {chart.length === 0 ? (
              <p className="text-sm text-muted">No tract loses access in this scenario. The baseline has no closures; try Moderate or Severe in the Scenario Lab.</p>
            ) : (
              <>
                <div className="h-56" aria-label="Bar chart of most affected tracts">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chart} layout="vertical" margin={{ left: 4, right: 8, top: 4, bottom: 0 }}>
                      <CartesianGrid horizontal={false} stroke="#233847" />
                      <XAxis type="number" stroke="#8597a3" fontSize={11} />
                      <YAxis type="category" dataKey="geoid" width={52} stroke="#8597a3" fontSize={11} />
                      <Tooltip contentStyle={{ background: "#111f2b", border: "1px solid #233847", fontSize: 12 }} labelFormatter={(l) => `Tract …${l}`} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="Lost drive route" stackId="a" fill="#ff4d5e" />
                      <Bar dataKey="Lost walk access" stackId="a" fill="#d9a25b" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <ul className="space-y-1 text-sm">
                  {ranked.slice(0, 5).map((p) => (
                    <li key={p.geoid}>
                      <button onClick={() => ws.selectTract(p.geoid)} className="flex w-full justify-between gap-2 rounded px-2 py-1 text-left hover:bg-raised">
                        <span>{p.name ?? p.geoid} <span className="text-xs text-muted">{p.geoid.startsWith("48157") ? "Fort Bend" : "Harris"}</span></span>
                        <span className="tabular-nums text-muted">{fmt.dec(p.demand_est, 0)} demand</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Section>
          <Section title="How this is computed">
            <div className="space-y-2">
              {acc.method_notes.map((n) => <Note key={n}>{n}</Note>)}
              <Note tone="warn">Only Fort Bend tracts have FEMA data, so disruption appears only there. Harris tracts are unknown, not unaffected.</Note>
            </div>
          </Section>
        </>
      )}
    </div>
  );
}
