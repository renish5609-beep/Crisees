"use client";

import { FlaskConical, MousePointerClick, Play, X } from "lucide-react";
import type { EdgeFeature } from "@/components/map/config";
import { Badge, Button, ErrorCard, Note, Section, Segmented, Slider, Stat, Working, fmt } from "@/components/ui";
import { LIMITS, PRESET_SPECS } from "@/lib/params";
import { useWorkspace } from "@/lib/store";
import type { PresetName } from "@/lib/types";

const PRESET_TEXT: Record<PresetName | "custom", string> = {
  baseline: "No simulated closures: the intact road network.",
  moderate: "60% of road segments with ≥10 m in a FEMA 1% zone close, plus 15% within 50 m of one.",
  severe: "Every segment with ≥5 m in a 1% zone closes, 50% in 0.2% zones, 35% within 150 m of a 1% zone.",
  custom: "Set your own hypothetical closure rules.",
};

export function ScenarioLab({ picking, setPicking, picked, onRemovePicked }: {
  picking: boolean; setPicking: (b: boolean) => void; picked: EdgeFeature[]; onRemovePicked: (id: string) => void;
}) {
  const ws = useWorkspace();
  const s = ws.params.scenario;
  const slot = ws.scenario;
  const ev = slot.data?.evaluation;
  const stale = slot.status !== "idle" && slot.key !== ws.keys.scenario;
  const setPreset = (preset: PresetName | "custom") =>
    ws.setParams((p) => {
      p.scenario = preset === "custom"
        ? { ...p.scenario, preset }
        : { preset, ...PRESET_SPECS[preset], custom_closed_edge_ids: p.scenario.custom_closed_edge_ids };
      return p;
    });
  const setS = (k: keyof typeof s, v: number) => ws.setParams((p) => ({ ...p, scenario: { ...p.scenario, preset: "custom", [k]: v } }));
  const ac = ev?.access_change ?? {};

  return (
    <div className="space-y-6">
      <header>
        <h2 className="flex items-center gap-2 text-lg font-semibold"><FlaskConical size={18} aria-hidden className="text-water" /> Scenario Lab</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          Turn FEMA flood-zone exposure into hypothetical road closures. Each run executes the real routing engine on 199,542 road edges.
        </p>
      </header>

      <Section title="Flood disruption">
        <Segmented label="Scenario preset" value={s.preset} onChange={setPreset}
          options={[{ value: "baseline", label: "Baseline" }, { value: "moderate", label: "Moderate" }, { value: "severe", label: "Severe" }, { value: "custom", label: "Custom" }]} />
        <p className="text-xs leading-relaxed text-muted">{PRESET_TEXT[s.preset]}</p>
        {s.preset === "custom" && (
          <div className="crisees-in space-y-4 rounded-lg border border-rule p-3">
            <Slider label="Closure chance in 1% zones" value={s.one_pct_closure_prob} onChange={(v) => setS("one_pct_closure_prob", v)} {...LIMITS.one_pct_closure_prob} format={(v) => `${Math.round(v * 100)}%`} />
            <Slider label="Closure chance in 0.2% zones" value={s.point_two_pct_closure_prob} onChange={(v) => setS("point_two_pct_closure_prob", v)} {...LIMITS.point_two_pct_closure_prob} />
            <Slider label="Overbank distance" value={s.overbank_buffer_m} onChange={(v) => setS("overbank_buffer_m", v)} {...LIMITS.overbank_buffer_m} hint="Roads this close to a 1% zone may also close." />
            <Slider label="Overbank closure chance" value={s.overbank_closure_prob} onChange={(v) => setS("overbank_closure_prob", v)} {...LIMITS.overbank_closure_prob} />
          </div>
        )}
        <Slider label="Random seed" value={s.seed} onChange={(v) => ws.setParams((p) => ({ ...p, scenario: { ...p.scenario, seed: Math.round(v) } }))}
          min={0} max={9999} step={1} hint="Same seed + same rules = identical closures (SHA-256 sampling)." />
        <Slider label="Maximum walking distance" value={ws.params.walk_max_m} onChange={(v) => ws.setParams((p) => ({ ...p, walk_max_m: v }))}
          {...LIMITS.walk_max_m} hint="Walk-proxy network distance to a pickup hub or shelter (about 10 min at 800 m)." />
      </Section>

      <Section title="Custom road closures" aside={<Badge>{s.custom_closed_edge_ids.length}</Badge>}>
        <Button variant={picking ? "primary" : "secondary"} onClick={() => setPicking(!picking)} aria-pressed={picking}>
          <MousePointerClick size={15} aria-hidden /> {picking ? "Click roads on the map… (done)" : "Pick roads on the map"}
        </Button>
        {picked.length > 0 && (
          <ul className="max-h-32 space-y-1 overflow-auto text-sm">
            {picked.map((f) => (
              <li key={f.properties.edge_id} className="flex items-center justify-between gap-2 rounded bg-ground/50 px-2 py-1">
                <span className="truncate">{f.properties.name ?? f.properties.road_class} <span className="text-xs text-muted">{Math.round(f.properties.length_m)} m</span></span>
                <button onClick={() => onRemovePicked(f.properties.edge_id)} aria-label={`Remove ${f.properties.edge_id}`} className="text-muted hover:text-ink"><X size={14} /></button>
              </li>
            ))}
          </ul>
        )}
        <Note>Picked edges close in both directions and are added to the scenario rules.</Note>
      </Section>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => void ws.runScenario()} disabled={slot.status === "loading" || ws.errors.length > 0}>
          <Play size={15} aria-hidden /> Run simulation
        </Button>
        {slot.status === "loading" && <Working label="Simulating disruption" startedAt={slot.startedAt} />}
      </div>
      {ws.errors.map((e) => <p key={e} className="text-sm text-alarm">{e}</p>)}
      {stale && slot.status !== "loading" && <Note tone="warn">Inputs changed since the results below were computed. Run the simulation to update them.</Note>}
      {slot.status === "error" && <ErrorCard error={slot.error} what="Scenario simulation" onRetry={() => void ws.runScenario()} />}

      {ev && (
        <Section title={`Result: ${ev.spec.name}`} aside={<Badge tone="info" title="Deterministic id of these exact inputs">{ev.scenario_id}</Badge>}>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Closed road segments" value={fmt.int(ev.closures.closed_segments)} sub={`${fmt.int(ev.closures.closed_directed_edges)} directed edges`} tone={ev.closures.closed_segments ? "bad" : "default"} />
            <Stat label="Closed road length" value={`${fmt.dec(ev.closures.closed_length_km)} km`} />
            <Stat label="Origins losing every drive route" value={fmt.int(ac.origins_losing_all_drive_routes_to_shelters)} sub={`${fmt.dec(ac.demand_at_origins_losing_drive_routes as number, 0)} persons of demand`} tone={(ac.origins_losing_all_drive_routes_to_shelters ?? 0) > 0 ? "bad" : "default"} />
            <Stat label="Hubs still reaching a shelter" value={`${ac.hubs_with_drive_route_to_a_shelter_scenario} / ${ac.hubs_with_drive_route_to_a_shelter_baseline}`} />
            <Stat label="Mean drive to nearest shelter" value={`${fmt.dec(ac.mean_drive_min_to_nearest_shelter_scenario as number, 2)} min`} sub={`baseline ${fmt.dec(ac.mean_drive_min_to_nearest_shelter_baseline as number, 2)} · p90 +${fmt.dec(ac.p90_drive_min_increase as number, 2)}`} />
            <Stat label="Shelters within 30 min (avg)" value={fmt.dec(ac.mean_shelters_within_30_min_scenario as number)} sub={`baseline ${fmt.dec(ac.mean_shelters_within_30_min_baseline as number)}`} />
          </div>
          <div className="text-xs text-muted">
            <p>Closed by rule: {Object.entries(ev.closures.closed_segments_by_rule).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
            <p>Network: {ev.network.baseline.weak_components} → {ev.network.scenario.weak_components} connected pieces · computed in {fmt.dec(ev.timings_s.total, 2)} s ({ev.cache === "hit" ? "cached" : "fresh"})</p>
          </div>
          <Note tone="warn">
            {fmt.int(ev.closures.unknown_coverage_segments)} segments ({fmt.int(ev.closures.unknown_coverage_length_km)} km) have no FEMA data. They are
            treated as unknown and never closed by flood rules, so Harris County disruption is a lower bound.
          </Note>
        </Section>
      )}
    </div>
  );
}
