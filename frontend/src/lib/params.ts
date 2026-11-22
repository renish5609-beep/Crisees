// Planning parameters shared by the map, Scenario Lab, Planner and Impact views.
// Defaults and bounds mirror backend/app/engine/params.py; the backend re-validates.

import type { AccessParams, PresetName, ResourceParams, ScenarioSpec, WeightParams } from "./types";

export interface ScenarioDraft {
  preset: PresetName | "custom";
  seed: number;
  one_pct_closure_prob: number;
  point_two_pct_closure_prob: number;
  overbank_buffer_m: number;
  overbank_closure_prob: number;
  min_exposed_m: number;
  custom_closed_edge_ids: string[];
}

export interface PlanParams {
  scenario: ScenarioDraft;
  walk_max_m: number;
  vehicles: number;
  vehicle_capacity: number;
  max_active_hubs: number;
  shelter_capacity: number;
  hub_capacity: number;
  horizon_min: number;
  weights: "equity" | "equal";
}

export const PRESET_SPECS: Record<PresetName, Omit<ScenarioDraft, "preset" | "custom_closed_edge_ids">> = {
  baseline: { seed: 2017, one_pct_closure_prob: 0, point_two_pct_closure_prob: 0, overbank_buffer_m: 0, overbank_closure_prob: 0, min_exposed_m: 10 },
  moderate: { seed: 2017, one_pct_closure_prob: 0.6, point_two_pct_closure_prob: 0, overbank_buffer_m: 50, overbank_closure_prob: 0.15, min_exposed_m: 10 },
  severe: { seed: 2017, one_pct_closure_prob: 1, point_two_pct_closure_prob: 0.5, overbank_buffer_m: 150, overbank_closure_prob: 0.35, min_exposed_m: 5 },
};

export const DEFAULT_PARAMS: PlanParams = {
  scenario: { preset: "severe", ...PRESET_SPECS.severe, custom_closed_edge_ids: [] },
  walk_max_m: 800,
  vehicles: 15,
  vehicle_capacity: 40,
  max_active_hubs: 12,
  shelter_capacity: 400,
  hub_capacity: 600,
  horizon_min: 480,
  weights: "equity",
};

export const LIMITS = {
  seed: { min: 0, max: 999999, step: 1 },
  walk_max_m: { min: 200, max: 2000, step: 100, unit: "m" },
  vehicles: { min: 0, max: 100, step: 1, unit: "" },
  vehicle_capacity: { min: 5, max: 80, step: 5, unit: "seats" },
  max_active_hubs: { min: 0, max: 60, step: 1, unit: "" },
  shelter_capacity: { min: 50, max: 2000, step: 50, unit: "persons" },
  hub_capacity: { min: 50, max: 3000, step: 50, unit: "persons" },
  horizon_min: { min: 60, max: 1440, step: 30, unit: "min" },
  one_pct_closure_prob: { min: 0, max: 1, step: 0.05 },
  point_two_pct_closure_prob: { min: 0, max: 1, step: 0.05 },
  overbank_buffer_m: { min: 0, max: 500, step: 25, unit: "m" },
  overbank_closure_prob: { min: 0, max: 1, step: 0.05 },
} as const;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function scenarioSpec(d: ScenarioDraft): ScenarioSpec | PresetName {
  if (d.preset !== "custom" && d.custom_closed_edge_ids.length === 0) {
    const p = PRESET_SPECS[d.preset];
    const same = (Object.keys(p) as (keyof typeof p)[]).every((k) => p[k] === d[k]);
    if (same) return d.preset;
  }
  return {
    name: d.preset === "custom" ? "custom" : `${d.preset}-custom`,
    seed: d.seed,
    one_pct_closure_prob: d.one_pct_closure_prob,
    point_two_pct_closure_prob: d.point_two_pct_closure_prob,
    min_exposed_m: d.min_exposed_m,
    overbank_buffer_m: d.overbank_buffer_m,
    overbank_closure_prob: d.overbank_closure_prob,
    unknown_coverage_policy: "no_inference",
    unknown_closure_prob: 0,
    custom_closed_edge_ids: d.custom_closed_edge_ids,
  };
}

export const accessParams = (p: PlanParams): AccessParams => ({ walk_max_m: p.walk_max_m });

export const resourceParams = (p: PlanParams): ResourceParams => ({
  max_active_hubs: p.max_active_hubs,
  vehicles: p.vehicles,
  vehicle_capacity: p.vehicle_capacity,
  horizon_min: p.horizon_min,
  dwell_min: 10,
  hub_capacity: p.hub_capacity,
  shelter_capacity: p.shelter_capacity,
  shelters_per_hub: 4,
});

export const weightParams = (p: PlanParams): WeightParams => ({
  mode: p.weights,
  beta_poverty: 0.5,
  beta_disability: 0.5,
  beta_age65: 0,
});

/** Stable keys used to tell whether displayed results match current inputs. */
export const scenarioKey = (p: PlanParams) => JSON.stringify([scenarioSpec(p.scenario), p.walk_max_m]);
export const planKey = (p: PlanParams) => JSON.stringify([scenarioKey(p), resourceParams(p), p.weights]);
export const compareKey = (p: PlanParams) => JSON.stringify([scenarioKey(p), resourceParams(p)]);

/** Validation messages for user-entered values (null = valid). */
export function validate(p: PlanParams): string[] {
  const errs: string[] = [];
  const check = (name: keyof typeof LIMITS, v: number, label: string) => {
    const l = LIMITS[name];
    if (!Number.isFinite(v) || v < l.min || v > l.max) errs.push(`${label} must be between ${l.min} and ${l.max}.`);
  };
  check("walk_max_m", p.walk_max_m, "Walking distance");
  check("vehicles", p.vehicles, "Vehicles");
  check("vehicle_capacity", p.vehicle_capacity, "Seats per vehicle");
  check("max_active_hubs", p.max_active_hubs, "Pickup hubs");
  check("shelter_capacity", p.shelter_capacity, "Shelter capacity");
  check("hub_capacity", p.hub_capacity, "Hub capacity");
  check("horizon_min", p.horizon_min, "Planning horizon");
  check("seed", p.scenario.seed, "Seed");
  if (p.scenario.custom_closed_edge_ids.length > 500) errs.push("At most 500 custom road closures.");
  return errs;
}

// ---------------------------------------------------------------- URL state
const NUM_KEYS: [keyof PlanParams, string][] = [
  ["walk_max_m", "walk"], ["vehicles", "veh"], ["vehicle_capacity", "seats"], ["max_active_hubs", "hubs"],
  ["shelter_capacity", "shel"], ["hub_capacity", "hubcap"], ["horizon_min", "hor"],
];

export function paramsToQuery(p: PlanParams): URLSearchParams {
  const q = new URLSearchParams();
  q.set("s", p.scenario.preset);
  if (p.scenario.preset === "custom") {
    q.set("p1", String(p.scenario.one_pct_closure_prob));
    q.set("p02", String(p.scenario.point_two_pct_closure_prob));
    q.set("ob", String(p.scenario.overbank_buffer_m));
    q.set("obp", String(p.scenario.overbank_closure_prob));
    q.set("me", String(p.scenario.min_exposed_m));
  }
  if (p.scenario.seed !== 2017) q.set("seed", String(p.scenario.seed));
  if (p.scenario.custom_closed_edge_ids.length) q.set("close", p.scenario.custom_closed_edge_ids.join("~"));
  for (const [k, qk] of NUM_KEYS) if (p[k] !== DEFAULT_PARAMS[k]) q.set(qk, String(p[k]));
  if (p.weights !== "equity") q.set("w", p.weights);
  return q;
}

export function paramsFromQuery(q: URLSearchParams): PlanParams {
  const p: PlanParams = structuredClone(DEFAULT_PARAMS);
  const preset = q.get("s");
  if (preset === "baseline" || preset === "moderate" || preset === "severe") {
    p.scenario = { preset, ...PRESET_SPECS[preset], custom_closed_edge_ids: [] };
  } else if (preset === "custom") {
    const f = (k: string, d: number, lim: { min: number; max: number }) => {
      const v = Number(q.get(k));
      return q.has(k) && Number.isFinite(v) ? clamp(v, lim.min, lim.max) : d;
    };
    p.scenario = {
      preset: "custom", seed: 2017, custom_closed_edge_ids: [],
      min_exposed_m: f("me", 10, { min: 0, max: 1000 }),
      one_pct_closure_prob: f("p1", 0.6, LIMITS.one_pct_closure_prob),
      point_two_pct_closure_prob: f("p02", 0, LIMITS.point_two_pct_closure_prob),
      overbank_buffer_m: f("ob", 50, LIMITS.overbank_buffer_m),
      overbank_closure_prob: f("obp", 0.15, LIMITS.overbank_closure_prob),
    };
  }
  const seed = Number(q.get("seed"));
  if (q.has("seed") && Number.isInteger(seed)) p.scenario.seed = clamp(seed, 0, LIMITS.seed.max);
  const close = q.get("close");
  if (close) p.scenario.custom_closed_edge_ids = close.split("~").filter((e) => /^\d+-\d+-\d+$/.test(e)).slice(0, 500);
  for (const [k, qk] of NUM_KEYS) {
    const v = Number(q.get(qk));
    if (q.has(qk) && Number.isFinite(v)) {
      const lim = LIMITS[k as keyof typeof LIMITS];
      (p[k] as number) = clamp(v, lim.min, lim.max);
    }
  }
  if (q.get("w") === "equal") p.weights = "equal";
  return p;
}
