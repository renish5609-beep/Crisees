"use client";

// Workspace state: draft parameters (what the controls show), and results from
// the real backend. Each result records the parameter key it was computed for,
// so the UI can say when displayed results are out of date. Only the latest
// request of each kind may update state (stale responses are dropped).

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, DEFAULT_REGION, api } from "./api";
import {
  DEFAULT_PARAMS,
  type PlanParams,
  accessParams,
  compareKey,
  paramsFromQuery,
  paramsToQuery,
  planKey,
  resourceParams,
  scenarioKey,
  scenarioSpec,
  validate,
  weightParams,
} from "./params";
import type {
  AccessibilityResult,
  ComparisonResult,
  DemographicsRecord,
  EdgeProps,
  FeatureCollection,
  OptimizationResult,
  ScenarioEvaluation,
} from "./types";

export type Slot<T> =
  | { status: "idle"; data?: undefined; key?: undefined; error?: undefined }
  | { status: "loading"; data?: T; key?: string; error?: undefined; startedAt: number }
  | { status: "ok"; data: T; key: string; error?: undefined }
  | { status: "error"; data?: T; key?: string; error: ApiError };

export interface ScenarioBundle {
  evaluation: ScenarioEvaluation;
  accessibility: AccessibilityResult;
  closures: FeatureCollection<EdgeProps & { len_in_1pct_m: number | null }> | null;
}

export type View = "overview" | "scenario" | "access" | "planner" | "impact" | "demo";

interface Workspace {
  regionId: string;
  params: PlanParams;
  setParams: (fn: (p: PlanParams) => PlanParams) => void;
  resetParams: () => void;
  errors: string[];
  view: View;
  setView: (v: View) => void;
  scenario: Slot<ScenarioBundle>;
  plan: Slot<OptimizationResult>;
  comparison: Slot<ComparisonResult>;
  demographics: Map<string, DemographicsRecord>;
  runScenario: (p?: PlanParams) => Promise<ScenarioBundle | null>;
  runOptimize: (p?: PlanParams) => Promise<OptimizationResult | null>;
  runCompare: (p?: PlanParams) => Promise<ComparisonResult | null>;
  cancelAll: () => void;
  selectedTract: string | null;
  selectTract: (g: string | null) => void;
  selectedHub: string | null;
  selectHub: (h: string | null) => void;
  keys: { scenario: string; plan: string; compare: string };
}

const Ctx = createContext<Workspace | null>(null);

const asApiError = (e: unknown) => (e instanceof ApiError ? e : new ApiError(String(e), 0, "client_error"));

function useSlot<T>() {
  const [slot, setSlot] = useState<Slot<T>>({ status: "idle" });
  const seq = useRef(0);
  const ctrl = useRef<AbortController | null>(null);
  const run = useCallback(async (key: string, fn: (signal: AbortSignal) => Promise<T>): Promise<T | null> => {
    ctrl.current?.abort();
    const controller = new AbortController();
    ctrl.current = controller;
    const id = ++seq.current;
    setSlot((s) => ({ status: "loading", data: s.data, key: s.key, startedAt: Date.now() }));
    try {
      const data = await fn(controller.signal);
      if (id !== seq.current) return null; // stale
      setSlot({ status: "ok", data, key });
      return data;
    } catch (e) {
      if (id !== seq.current) return null;
      const err = asApiError(e);
      if (err.code === "aborted") return null;
      setSlot((s) => ({ status: "error", data: s.data, key: s.key, error: err }));
      return null;
    }
  }, []);
  const cancel = useCallback(() => {
    ctrl.current?.abort();
    seq.current++;
    setSlot((s) => (s.status === "loading" ? (s.data ? { status: "ok", data: s.data, key: s.key! } : { status: "idle" }) : s));
  }, []);
  return [slot, run, cancel] as const;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const regionId = DEFAULT_REGION;
  const [params, setParamsState] = useState<PlanParams>(DEFAULT_PARAMS);
  const [view, setViewState] = useState<View>("overview");
  const [hydrated, setHydrated] = useState(false);
  const [scenario, runScenarioSlot, cancelScenario] = useSlot<ScenarioBundle>();
  const [plan, runPlanSlot, cancelPlan] = useSlot<OptimizationResult>();
  const [comparison, runCompareSlot, cancelCompare] = useSlot<ComparisonResult>();
  const [demographics, setDemographics] = useState<Map<string, DemographicsRecord>>(new Map());
  const [selectedTract, selectTract] = useState<string | null>(null);
  const [selectedHub, selectHub] = useState<string | null>(null);

  // Hydrate from the URL once on the client.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setParamsState(paramsFromQuery(q));
    const v = q.get("view");
    if (v && ["overview", "scenario", "access", "planner", "impact", "demo"].includes(v)) setViewState(v as View);
    setHydrated(true);
  }, []);

  // Persist parameters + view in the URL (shareable, reload-safe).
  useEffect(() => {
    if (!hydrated) return;
    const q = paramsToQuery(params);
    if (view !== "overview") q.set("view", view);
    const s = q.toString();
    window.history.replaceState(null, "", s ? `?${s}` : window.location.pathname);
  }, [params, view, hydrated]);

  useEffect(() => {
    const ctrl = new AbortController();
    api.demographics(regionId, ctrl.signal)
      .then((d) => setDemographics(new Map(d.records.map((r) => [r.demographics.geoid, r]))))
      .catch(() => undefined); // the inspector shows "unavailable" if this fails
    return () => ctrl.abort();
  }, [regionId]);

  const setParams = useCallback((fn: (p: PlanParams) => PlanParams) => setParamsState((p) => fn(structuredClone(p))), []);
  const resetParams = useCallback(() => setParamsState(structuredClone(DEFAULT_PARAMS)), []);
  const setView = useCallback((v: View) => setViewState(v), []);

  const paramsRef = useRef(params);
  paramsRef.current = params;

  const runScenario = useCallback(
    (p?: PlanParams) => {
      const P = p ?? paramsRef.current;
      if (validate(P).length) return Promise.resolve(null);
      const spec = scenarioSpec(P.scenario);
      return runScenarioSlot(scenarioKey(P), async (signal) => {
        const evaluation = await api.evaluate(regionId, spec, accessParams(P), signal);
        const [accessibility, closures] = await Promise.all([
          api.accessibility(regionId, spec, accessParams(P), signal),
          evaluation.closures.closed_segments > 0
            ? api.closures(regionId, evaluation.scenario_id, signal).catch(() => null)
            : Promise.resolve(null),
        ]);
        return { evaluation, accessibility, closures };
      });
    },
    [regionId, runScenarioSlot],
  );

  const runOptimize = useCallback(
    (p?: PlanParams) => {
      const P = p ?? paramsRef.current;
      if (validate(P).length) return Promise.resolve(null);
      return runPlanSlot(planKey(P), (signal) =>
        api.optimize(regionId, {
          scenario: scenarioSpec(P.scenario), access: accessParams(P), resources: resourceParams(P), weights: weightParams(P),
        }, signal));
    },
    [regionId, runPlanSlot],
  );

  const runCompare = useCallback(
    (p?: PlanParams) => {
      const P = p ?? paramsRef.current;
      if (validate(P).length) return Promise.resolve(null);
      return runCompareSlot(compareKey(P), (signal) =>
        api.compare(regionId, {
          disrupted_scenario: scenarioSpec(P.scenario), access: accessParams(P), resources: resourceParams(P),
          weights: { ...weightParams(P), mode: "equity" },
        }, signal));
    },
    [regionId, runCompareSlot],
  );

  // First visit: compute the current scenario so the map has real data.
  const booted = useRef(false);
  useEffect(() => {
    if (!hydrated || booted.current) return;
    booted.current = true;
    void runScenario();
  }, [hydrated, runScenario]);

  const cancelAll = useCallback(() => {
    cancelScenario();
    cancelPlan();
    cancelCompare();
  }, [cancelScenario, cancelPlan, cancelCompare]);

  const value = useMemo<Workspace>(
    () => ({
      regionId, params, setParams, resetParams, errors: validate(params), view, setView, scenario, plan, comparison,
      demographics, runScenario, runOptimize, runCompare, cancelAll, selectedTract, selectTract, selectedHub, selectHub,
      keys: { scenario: scenarioKey(params), plan: planKey(params), compare: compareKey(params) },
    }),
    [regionId, params, setParams, resetParams, view, setView, scenario, plan, comparison, demographics, runScenario,
     runOptimize, runCompare, cancelAll, selectedTract, selectedHub],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace(): Workspace {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return v;
}
