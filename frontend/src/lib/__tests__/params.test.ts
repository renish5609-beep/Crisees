import { describe, expect, it } from "vitest";
import { DEFAULT_PARAMS, paramsFromQuery, paramsToQuery, planKey, resourceParams, scenarioSpec, validate } from "../params";

describe("planning parameters", () => {
  it("defaults mirror the backend defaults and are valid", () => {
    expect(validate(DEFAULT_PARAMS)).toEqual([]);
    expect(resourceParams(DEFAULT_PARAMS)).toEqual({
      max_active_hubs: 12, vehicles: 15, vehicle_capacity: 40, horizon_min: 480, dwell_min: 10,
      hub_capacity: 600, shelter_capacity: 400, shelters_per_hub: 4,
    });
  });

  it("sends preset names when the rules match a preset exactly", () => {
    expect(scenarioSpec(DEFAULT_PARAMS.scenario)).toBe("severe");
    const tweaked = { ...DEFAULT_PARAMS.scenario, seed: 7 };
    const spec = scenarioSpec(tweaked);
    expect(typeof spec).toBe("object");
    expect(spec).toMatchObject({ seed: 7, one_pct_closure_prob: 1, unknown_coverage_policy: "no_inference" });
  });

  it("custom closures always produce an explicit spec", () => {
    const spec = scenarioSpec({ ...DEFAULT_PARAMS.scenario, custom_closed_edge_ids: ["1-2-0"] });
    expect(spec).toMatchObject({ custom_closed_edge_ids: ["1-2-0"] });
  });

  it("round-trips through the URL", () => {
    const p = structuredClone(DEFAULT_PARAMS);
    p.vehicles = 30;
    p.weights = "equal";
    p.scenario = { ...p.scenario, preset: "custom", one_pct_closure_prob: 0.4, seed: 99, custom_closed_edge_ids: ["11-22-0"] };
    const back = paramsFromQuery(paramsToQuery(p));
    expect(back.vehicles).toBe(30);
    expect(back.weights).toBe("equal");
    expect(back.scenario).toMatchObject({ preset: "custom", one_pct_closure_prob: 0.4, seed: 99, custom_closed_edge_ids: ["11-22-0"] });
    expect(planKey(back)).toBe(planKey(p));
  });

  it("clamps hostile URL values and drops malformed edge ids", () => {
    const p = paramsFromQuery(new URLSearchParams("veh=99999&walk=-5&hubs=abc&close=1-2-0~<script>~3-4-1"));
    expect(p.vehicles).toBe(100);
    expect(p.walk_max_m).toBe(200);
    expect(p.max_active_hubs).toBe(DEFAULT_PARAMS.max_active_hubs);
    expect(p.scenario.custom_closed_edge_ids).toEqual(["1-2-0", "3-4-1"]);
  });

  it("validation reports out-of-range values", () => {
    const errs = validate({ ...DEFAULT_PARAMS, vehicles: -1, horizon_min: 5000 });
    expect(errs.join(" ")).toMatch(/Vehicles/);
    expect(errs.join(" ")).toMatch(/Planning horizon/);
  });
});
