import { afterEach, describe, expect, it, vi } from "vitest";

process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
const { api, ApiError } = await import("../api");

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => vi.restoreAllMocks());

describe("API client", () => {
  it("surfaces backend error envelopes as ApiError with code and hint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(503, { error: { code: "dataset_not_available", message: "missing", details: { hint: "run the pipeline" } } }));
    const err = await api.optimize("r", { scenario: "severe", access: { walk_max_m: 800 }, resources: {} as never, weights: {} as never }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("dataset_not_available");
    expect(err.details.hint).toBe("run the pipeline");
    expect(err.retryable).toBe(true);
  });

  it("rejects responses that do not match the expected shape", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { totals: { served: "lots" } }));
    const err = await api.optimize("r", { scenario: "severe", access: { walk_max_m: 800 }, resources: {} as never, weights: {} as never }).catch((e) => e);
    expect(err.code).toBe("schema_mismatch");
  });

  it("reports network failures without inventing data", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const err = await api.health().catch((e) => e);
    expect(err.code).toBe("network_error");
  });

  it("posts JSON bodies to versioned endpoints", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { scenario_id: "scn_1", closures: { closed_segments: 0, closed_length_km: 0 } }));
    await api.evaluate("houston-sw-pilot", "baseline", { walk_max_m: 800 });
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/regions/houston-sw-pilot/scenarios/evaluate");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ scenario: "baseline", access: { walk_max_m: 800 } });
  });

  it("propagates caller cancellation as 'aborted'", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_u, init) => new Promise((_, rej) => {
      (init as RequestInit).signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
    }));
    const c = new AbortController();
    const p = api.health(c.signal).catch((e) => e);
    c.abort();
    expect((await p).code).toBe("aborted");
  });
});
