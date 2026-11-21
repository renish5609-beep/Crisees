"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL, ApiError, DEFAULT_REGION, api } from "@/lib/api";
import type { Health } from "@/lib/types";

type Conn = { kind: "checking" } | { kind: "up"; health: Health } | { kind: "down"; message: string };

const POLL_MS = 15000;

export function StatusBar() {
  const [conn, setConn] = useState<Conn>({ kind: "checking" });

  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then((health) => alive && setConn({ kind: "up", health }))
        .catch((e: unknown) => alive && setConn({ kind: "down", message: e instanceof ApiError ? e.message : String(e) }));
    check();
    const id = setInterval(check, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-5 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">Southwest Houston pilot</p>
        <p className="text-xs text-muted">Harris and Fort Bend counties, Texas. Hazard: flooding</p>
      </div>
      <ConnectionIndicator conn={conn} />
    </header>
  );
}

function ConnectionIndicator({ conn }: { conn: Conn }) {
  const base = "flex items-center gap-2 rounded-full border px-3 py-1 text-xs";
  if (conn.kind === "checking") {
    return (
      <span className={`${base} border-rule text-muted`} role="status">
        <Dot className="bg-muted" /> Checking API
      </span>
    );
  }
  if (conn.kind === "down") {
    return (
      <span className={`${base} border-alarm/50 text-alarm`} role="status" title={conn.message}>
        <Dot className="bg-alarm" /> API offline at {API_BASE_URL.replace(/^https?:\/\//, "")}
      </span>
    );
  }
  const h = conn.health;
  const hasData = h.regions_with_processed_data > 0;
  return (
    <span
      className={`${base} ${hasData ? "border-water/40 text-water" : "border-sediment/50 text-sediment"}`}
      role="status"
      title={`API ${h.version}, ${h.environment}. Region ${DEFAULT_REGION}.`}
    >
      <Dot className={hasData ? "bg-water" : "bg-sediment"} />
      {hasData ? `API connected, v${h.version}` : "API connected, no processed data yet"}
    </span>
  );
}

function Dot({ className }: { className: string }) {
  return <span aria-hidden="true" className={`inline-block size-1.5 rounded-full ${className}`} />;
}
