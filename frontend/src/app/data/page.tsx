"use client";

import { ApiNotice } from "@/components/Notice";
import { DEFAULT_REGION, api } from "@/lib/api";
import { fmtBytes, fmtDate, fmtInt } from "@/lib/format";
import type { DatasetStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const STATE_STYLE: Record<DatasetStatus["state"], string> = {
  available: "text-water",
  missing: "text-sediment",
  invalid: "text-alarm",
};

const PROVENANCE_LABEL: Record<string, string> = {
  real: "Published data",
  derived: "Derived by Crisees",
  synthetic: "Synthetic test data",
};

export default function DataStatusPage() {
  const region = useApi((s) => api.region(DEFAULT_REGION, s));

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-5">
      <div className="max-w-2xl">
        <h1 className="text-xl font-semibold tracking-tight">Data status</h1>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          Which datasets the API can serve for this region, where each came from, and what to watch out for.
          Missing datasets are produced by the scripts in <code className="text-ink">scripts/</code>.
        </p>
      </div>

      {region.status === "loading" && <p className="text-sm text-muted">Loading dataset inventory…</p>}
      {region.status === "error" && <ApiNotice error={region.error} what="The dataset inventory" />}
      {region.status === "ok" && (
        <>
          <p className="text-sm text-muted">
            {region.data.datasets.filter((d) => d.state === "available").length} of {region.data.datasets.length}{" "}
            datasets available. Last processed {fmtDate(region.data.pipeline_generated_at) || "never"}.
          </p>
          <ul className="divide-y divide-rule border-y border-rule">
            {region.data.datasets.map((d) => (
              <DatasetRow key={d.dataset} d={d} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function DatasetRow({ d }: { d: DatasetStatus }) {
  const src = d.sources[0];
  return (
    <li className="grid gap-x-6 gap-y-2 py-4 md:grid-cols-[16rem_1fr]">
      <div>
        <p className="font-medium">{d.title}</p>
        <p className="mt-0.5 text-sm">
          <span className={STATE_STYLE[d.state]}>{d.state === "available" ? "Available" : d.state === "missing" ? "Not generated" : "Invalid"}</span>
          {d.record_count != null && (
            <span className="text-muted">
              , {fmtInt(d.record_count)} records{d.size_bytes ? `, ${fmtBytes(d.size_bytes)}` : ""}
            </span>
          )}
        </p>
        {d.provenance && <p className="mt-0.5 text-xs text-muted">{PROVENANCE_LABEL[d.provenance] ?? d.provenance}</p>}
      </div>
      <div className="min-w-0 text-sm">
        {src ? (
          <p>
            {src.url?.startsWith("http") ? (
              <a href={src.url} className="text-ink underline decoration-rule underline-offset-4 hover:decoration-water">
                {src.name}
              </a>
            ) : (
              <span>{src.name}</span>
            )}
            <span className="text-muted">
              {" "}
              ({src.publisher}
              {src.license ? `; ${src.license}` : ""})
            </span>
          </p>
        ) : (
          <p className="text-muted">No source recorded.</p>
        )}
        {d.notes.length > 0 && (
          <ul className="mt-1.5 space-y-1 text-muted">
            {d.notes.map((n) => (
              <li key={n} className="leading-relaxed">
                {n}
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}
