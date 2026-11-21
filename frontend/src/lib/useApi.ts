"use client";

import { useEffect, useState } from "react";
import { ApiError } from "./api";

export type Loadable<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "error"; error: ApiError };

/** Fetch once on mount (and when `deps` change); aborts on unmount. */
export function useApi<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[] = []): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ status: "loading" });
  useEffect(() => {
    const ctrl = new AbortController();
    setState({ status: "loading" });
    fn(ctrl.signal)
      .then((data) => !ctrl.signal.aborted && setState({ status: "ok", data }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        const error = err instanceof ApiError ? err : new ApiError(String(err), 0, "client_error");
        setState({ status: "error", error });
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
