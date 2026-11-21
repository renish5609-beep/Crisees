import type {
  ApiErrorBody,
  DatasetStatus,
  FeatureCollection,
  FloodProps,
  GeographicRegion,
  Health,
  RegionSummary,
  TractProps,
} from "./types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const DEFAULT_REGION = process.env.NEXT_PUBLIC_DEFAULT_REGION ?? "houston-sw-pilot";

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
}

async function request<T>(path: string, init: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), init.timeoutMs ?? 15000);
  init.signal?.addEventListener("abort", () => controller.abort());
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { signal: controller.signal, headers: { Accept: "application/json" } });
  } catch (err) {
    throw new ApiError(
      `Cannot reach the Crisees API at ${API_BASE_URL}. Start it with: uvicorn app.main:app --port 8000`,
      0,
      err instanceof DOMException && err.name === "AbortError" ? "timeout" : "network_error",
    );
  } finally {
    clearTimeout(timer);
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
  return (await res.json()) as T;
}

const r = (id: string) => `/api/v1/regions/${encodeURIComponent(id)}`;

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal, timeoutMs: 5000 }),
  regions: (signal?: AbortSignal) => request<GeographicRegion[]>("/api/v1/regions", { signal }),
  region: (id: string, signal?: AbortSignal) => request<GeographicRegion>(r(id), { signal }),
  datasets: (id: string, signal?: AbortSignal) => request<DatasetStatus[]>(`${r(id)}/datasets`, { signal }),
  summary: (id: string, signal?: AbortSignal) => request<RegionSummary>(`${r(id)}/summary`, { signal }),
  tracts: (id: string, signal?: AbortSignal) =>
    request<FeatureCollection<TractProps>>(`${r(id)}/tracts?limit=1000&simplify_m=15`, { signal }),
  sfha: (id: string, signal?: AbortSignal) =>
    request<FeatureCollection<FloodProps>>(`${r(id)}/flood-hazards?sfha_only=true&limit=2000&simplify_m=10`, {
      signal,
    }),
};
