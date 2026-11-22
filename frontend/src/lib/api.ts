import { z } from "zod";
import type {
  AccessibilityResult,
  AccessParams,
  ApiErrorBody,
  ComparisonResult,
  DatasetStatus,
  DemographicsRecord,
  DemoResult,
  EdgeProps,
  FeatureCollection,
  FloodProps,
  GeographicRegion,
  Health,
  Methodology,
  OptimizationResult,
  RegionSummary,
  ResourceParams,
  ScenarioEvaluation,
  ScenarioPreset,
  ScenarioSpec,
  TractProps,
  WeightParams,
} from "./types";

/** API base URL comes from the environment at build time. In production it
 * must be set (NEXT_PUBLIC_API_BASE_URL); localhost is only a dev default. */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000")
).replace(/\/$/, "");
export const DEFAULT_REGION = process.env.NEXT_PUBLIC_DEFAULT_REGION ?? "houston-sw-pilot";
export const REPO_URL = "https://github.com/renish5609-beep/Crisees";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
  get retryable() {
    return this.status === 0 || this.status === 503 || this.code === "timeout";
  }
}

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  body?: unknown;
  method?: "GET" | "POST";
  schema?: z.ZodTypeAny;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError("NEXT_PUBLIC_API_BASE_URL is not configured for this deployment.", 0, "config_error");
  }
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts.timeoutMs ?? 20000);
  const onAbort = () => controller.abort();
  opts.signal?.addEventListener("abort", onAbort);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: opts.method ?? (opts.body ? "POST" : "GET"),
      signal: controller.signal,
      headers: { Accept: "application/json", ...(opts.body ? { "Content-Type": "application/json" } : {}) },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (err) {
    if (opts.signal?.aborted) throw new ApiError("Request cancelled.", 0, "aborted");
    if (timedOut) throw new ApiError("The analysis took longer than expected. Retry, or reduce the problem size.", 0, "timeout");
    throw new ApiError(`Cannot reach the Crisees API at ${API_BASE_URL}.`, 0, "network_error", {
      cause: err instanceof Error ? err.message : String(err),
    });
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onAbort);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      body?.error.message ?? `Request failed with HTTP ${res.status}`,
      res.status,
      body?.error.code ?? "http_error",
      body?.error.details ?? {},
    );
  }
  const data = (await res.json()) as T;
  if (opts.schema) {
    const parsed = opts.schema.safeParse(data);
    if (!parsed.success) {
      throw new ApiError("The API returned data in an unexpected shape.", res.status, "schema_mismatch", {
        issues: parsed.error.issues.slice(0, 3).map((i) => `${i.path.join(".")}: ${i.message}`),
      });
    }
  }
  return data;
}

// Runtime validation of the fields the UI depends on (extra fields allowed).
const num = z.number();
const nnum = z.number().nullable();
const totalsSchema = z.object({ demand_est: num, served: num, unmet: num, coverage: nnum, active_hubs: num }).passthrough();
const optimizeSchema = z
  .object({
    totals: totalsSchema,
    hubs: z.array(z.object({ hub_id: z.string(), lon: num, lat: num, legs: z.array(z.object({ shelter_id: z.string(), persons: num, trips: num }).passthrough()) }).passthrough()),
    solver: z.object({ status: z.string(), mip_gap: nnum }).passthrough(),
    constraint_check: z.object({ feasible: z.boolean() }).passthrough(),
    binding_constraints: z.object({}).passthrough(),
  })
  .passthrough();
const compareSchema = z
  .object({ cases: z.array(z.object({ case: z.string(), totals: totalsSchema }).passthrough()).min(4), findings: z.array(z.string()) })
  .passthrough();
const evaluateSchema = z
  .object({ scenario_id: z.string(), closures: z.object({ closed_segments: num, closed_length_km: num }).passthrough() })
  .passthrough();
const accessSchema = z
  .object({ features: z.array(z.object({ properties: z.object({ geoid: z.string() }).passthrough() }).passthrough()), summary: z.object({ total_demand_est: num }).passthrough() })
  .passthrough();

const r = (id: string) => `/api/v1/regions/${encodeURIComponent(id)}`;
const ANALYSIS_TIMEOUT = 150000;

export type ScenarioInput = ScenarioSpec | string;

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal, timeoutMs: 8000 }),
  region: (id: string, signal?: AbortSignal) => request<GeographicRegion>(r(id), { signal }),
  summary: (id: string, signal?: AbortSignal) => request<RegionSummary>(`${r(id)}/summary`, { signal, timeoutMs: 60000 }),
  tracts: (id: string, signal?: AbortSignal) =>
    request<FeatureCollection<TractProps>>(`${r(id)}/tracts?limit=1000&simplify_m=15`, { signal }),
  demographics: (id: string, signal?: AbortSignal) =>
    request<{ records: DemographicsRecord[] }>(`${r(id)}/demographics?limit=1000`, { signal }),
  floodHazards: (id: string, signal?: AbortSignal) =>
    request<FeatureCollection<FloodProps>>(`${r(id)}/flood-hazards?limit=2000&simplify_m=8`, { signal, timeoutMs: 40000 }),
  floodCoverage: (id: string, signal?: AbortSignal) =>
    request<{ type: "FeatureCollection"; features: FeatureCollection<{ kind: string }>["features"]; covered_area_fraction: number | null }>(
      `${r(id)}/layers/flood-coverage`, { signal, timeoutMs: 60000 }),
  contextRoads: (id: string, signal?: AbortSignal) =>
    request<FeatureCollection<{ road_class: string; name: string | null }>>(`${r(id)}/layers/context-roads`, { signal, timeoutMs: 60000 }),
  planningSites: (id: string, signal?: AbortSignal) =>
    request<{ shelters: FeatureCollection<Record<string, unknown>>; hubs: FeatureCollection<Record<string, unknown>>; notes: string[] }>(
      `${r(id)}/layers/planning-sites`, { signal, timeoutMs: 60000 }),
  datasets: (id: string, signal?: AbortSignal) => request<DatasetStatus[]>(`${r(id)}/datasets`, { signal }),
  presets: (id: string, signal?: AbortSignal) => request<ScenarioPreset[]>(`${r(id)}/scenarios`, { signal }),
  methodology: (id: string, signal?: AbortSignal) => request<Methodology>(`${r(id)}/methodology`, { signal }),
  evaluate: (id: string, scenario: ScenarioInput, access: AccessParams, signal?: AbortSignal) =>
    request<ScenarioEvaluation>(`${r(id)}/scenarios/evaluate`, {
      body: { scenario, access }, signal, timeoutMs: ANALYSIS_TIMEOUT, schema: evaluateSchema,
    }),
  closures: (id: string, scenarioId: string, signal?: AbortSignal) =>
    request<FeatureCollection<EdgeProps & { len_in_1pct_m: number | null }>>(
      `${r(id)}/scenarios/${scenarioId}/closures?limit=5000`, { signal, timeoutMs: 60000 }),
  accessibility: (id: string, scenario: ScenarioInput, access: AccessParams, signal?: AbortSignal) =>
    request<AccessibilityResult>(`${r(id)}/accessibility/analyze`, {
      body: { scenario, access, include_geometry: true, simplify_m: 15 }, signal, timeoutMs: ANALYSIS_TIMEOUT, schema: accessSchema,
    }),
  optimize: (id: string, body: { scenario: ScenarioInput; access: AccessParams; resources: ResourceParams; weights: WeightParams }, signal?: AbortSignal) =>
    request<OptimizationResult>(`${r(id)}/optimize`, {
      body: { ...body, include_geometry: false }, signal, timeoutMs: ANALYSIS_TIMEOUT, schema: optimizeSchema,
    }),
  compare: (id: string, body: { disrupted_scenario: ScenarioInput; access: AccessParams; resources: ResourceParams; weights: WeightParams }, signal?: AbortSignal) =>
    request<ComparisonResult>(`${r(id)}/compare`, { body, signal, timeoutMs: ANALYSIS_TIMEOUT, schema: compareSchema }),
  demo: (id: string, signal?: AbortSignal) => request<DemoResult>(`${r(id)}/demo`, { signal, timeoutMs: ANALYSIS_TIMEOUT }),
  edgesNear: (id: string, bbox: [number, number, number, number], signal?: AbortSignal) =>
    request<FeatureCollection<EdgeProps>>(`${r(id)}/roads?bbox=${bbox.join(",")}&limit=200`, { signal }),
};
