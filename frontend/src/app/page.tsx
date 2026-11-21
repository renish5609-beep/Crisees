"use client";

import { ApiNotice } from "@/components/Notice";
import { StudyAreaMap } from "@/components/StudyAreaMap";
import { DEFAULT_REGION, api } from "@/lib/api";
import { fmtInt, fmtPct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function WorkspacePage() {
  const tracts = useApi((s) => api.tracts(DEFAULT_REGION, s));
  const sfha = useApi((s) => api.sfha(DEFAULT_REGION, s));
  const summary = useApi((s) => api.summary(DEFAULT_REGION, s));

  return (
    <div className="grid h-full grid-cols-1 xl:grid-cols-[1fr_22rem]">
      <section aria-label="Map workspace" className="min-h-[60vh] border-rule p-4 xl:border-r">
        {tracts.status === "loading" && <p className="p-6 text-sm text-muted">Loading tract boundaries…</p>}
        {tracts.status === "error" && <ApiNotice error={tracts.error} what="Tract geometry" />}
        {tracts.status === "ok" && (
          <StudyAreaMap tracts={tracts.data} sfha={sfha.status === "ok" ? sfha.data : null} />
        )}
      </section>

      <aside aria-label="Study area summary" className="space-y-6 p-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Study area</h1>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            Alief, Sharpstown, Westchase, Mission Bend, Stafford and Missouri City, across the Brays and Keegans
            Bayou watersheds.
          </p>
        </div>
        {summary.status === "loading" && <p className="text-sm text-muted">Computing summary…</p>}
        {summary.status === "error" && <ApiNotice error={summary.error} what="Summary" />}
        {summary.status === "ok" && (
          <>
            <Group title="People (ACS 2020–2024)">
              <Row label="Residents" value={fmtInt(summary.data.population?.total_population)} />
              <Row label="Census tracts" value={fmtInt(summary.data.population?.tract_count)} />
              <Row
                label="Households without a vehicle"
                value={`${fmtInt(summary.data.population?.households_no_vehicle)} (${fmtPct(
                  summary.data.population?.pct_households_no_vehicle,
                )})`}
                strong
              />
              <Row label="Below poverty level" value={fmtPct(summary.data.population?.pct_below_poverty)} />
              <Row label="Age 65 and over" value={fmtPct(summary.data.population?.pct_65_plus)} />
              <Row label="With a disability" value={fmtPct(summary.data.population?.pct_with_disability)} />
            </Group>
            <Group title="Flood hazard (FEMA)">
              <Row label="Special flood hazard area" value={`${summary.data.flood?.sfha_area_km2 ?? "–"} km²`} />
              <Row label="Tracts touching it" value={fmtInt(summary.data.flood?.tracts_intersecting_sfha)} />
              <Row
                label="Study area with FEMA data"
                value={fmtPct(
                  summary.data.flood?.covered_area_fraction != null
                    ? summary.data.flood.covered_area_fraction * 100
                    : null,
                )}
                warn={(summary.data.flood?.covered_area_fraction ?? 1) < 0.99}
              />
            </Group>
            <Group title="Network and facilities">
              <Row label="Drivable road length" value={`${fmtInt(Math.round(summary.data.roads?.total_length_km ?? 0))} km (directed)`} />
              <Row label="Mapped facilities" value={fmtInt(summary.data.facilities?.facility_count)} />
              <Row label="Candidate pickup hubs" value={fmtInt(summary.data.facilities?.candidate_hub_count)} />
              <Row
                label="Verified evacuation shelters"
                value={fmtInt(summary.data.facilities?.authority_verified_shelters)}
                warn
              />
            </Group>
            <p className="text-xs leading-relaxed text-muted">
              FEMA zones show regulatory flood risk, not observed flooding. Parts of the Harris County side have no
              FEMA data loaded yet, which means unknown risk, not zero risk.
            </p>
          </>
        )}
      </aside>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="border-b border-rule pb-1.5 text-sm font-medium text-muted">{title}</h2>
      <dl className="divide-y divide-rule/60">{children}</dl>
    </section>
  );
}

function Row({ label, value, strong, warn }: { label: string; value: string; strong?: boolean; warn?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 text-sm">
      <dt className="text-ink/80">{label}</dt>
      <dd className={`text-right ${strong ? "font-semibold text-ink" : ""} ${warn ? "text-sediment" : ""}`}>{value}</dd>
    </div>
  );
}
