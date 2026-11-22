"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { API_BASE_URL, api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { Health } from "@/lib/types";

type Conn = { kind: "checking" } | { kind: "up"; health: Health } | { kind: "down"; message: string };

export function StatusBar() {
  const ws = useWorkspace();
  const [conn, setConn] = useState<Conn>({ kind: "checking" });
  useEffect(() => {
    let alive = true;
    const check = () => api.health()
      .then((health) => alive && setConn({ kind: "up", health }))
      .catch((e: unknown) => alive && setConn({ kind: "down", message: e instanceof Error ? e.message : String(e) }));
    check();
    const id = setInterval(check, 20000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  const busy = [ws.scenario, ws.plan, ws.comparison].some((s) => s.status === "loading");
  const ev = ws.scenario.data?.evaluation;
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-rule px-4 py-2">
      <div className="min-w-0 text-sm">
        <span className="font-medium">Southwest Houston pilot</span>
        <span className="ml-2 text-xs text-muted">151 tracts · Harris + Fort Bend · flood planning simulation</span>
      </div>
      <div className="flex items-center gap-2 text-xs">
        {busy && <span className="flex items-center gap-1.5 text-water" role="status"><Loader2 size={13} className="animate-spin" aria-hidden /> Computing</span>}
        {ev && <span className="hidden rounded-full border border-rule px-2 py-0.5 text-muted sm:inline">Scenario: {ev.spec.name} · seed {ev.spec.seed}</span>}
        {conn.kind === "checking" && <span className="rounded-full border border-rule px-2 py-0.5 text-muted">Checking API</span>}
        {conn.kind === "down" && <span className="rounded-full border border-alarm/50 px-2 py-0.5 text-alarm" title={conn.message}>API offline ({API_BASE_URL || "not configured"})</span>}
        {conn.kind === "up" && (
          <span className={`rounded-full border px-2 py-0.5 ${conn.health.regions_with_processed_data ? "border-water/40 text-water" : "border-sediment/50 text-sediment"}`}>
            {conn.health.regions_with_processed_data ? `API connected · v${conn.health.version}` : "API up, data not provisioned"}
          </span>
        )}
      </div>
    </header>
  );
}
