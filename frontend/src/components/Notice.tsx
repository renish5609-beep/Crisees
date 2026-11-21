import type { ApiError } from "@/lib/api";

/** Explains an API failure and how to resolve it. */
export function ApiNotice({ error, what }: { error: ApiError; what: string }) {
  const hint = typeof error.details.hint === "string" ? error.details.hint : null;
  return (
    <div className="rounded-lg border border-sediment/40 bg-sediment/5 p-4 text-sm" role="alert">
      <p className="font-medium text-sediment">{what} is unavailable</p>
      <p className="mt-1 text-ink/90">{error.message}</p>
      {hint && <p className="mt-2 text-muted">{hint}</p>}
    </div>
  );
}
