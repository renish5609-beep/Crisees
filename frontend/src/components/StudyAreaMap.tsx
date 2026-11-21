"use client";

import { useMemo, useState } from "react";
import type { Feature, FeatureCollection, FloodProps, Geometry, Position, TractProps } from "@/lib/types";

/**
 * Phase 1 preview of the map workspace: draws real tract boundaries and FEMA
 * Special Flood Hazard Areas as SVG using a local equirectangular projection
 * (x scaled by cos(latitude)). Phase 3 replaces this with an interactive
 * web map; the props contract (GeoJSON FeatureCollections) stays the same.
 */
export function StudyAreaMap({
  tracts,
  sfha,
}: {
  tracts: FeatureCollection<TractProps>;
  sfha: FeatureCollection<FloodProps> | null;
}) {
  const [hover, setHover] = useState<Feature<TractProps> | null>(null);

  const view = useMemo(() => {
    let [minX, minY, maxX, maxY] = [Infinity, Infinity, -Infinity, -Infinity];
    for (const f of tracts.features) {
      for (const ring of rings(f.geometry)) {
        for (const [x, y] of ring) {
          if (x < minX) minX = x;
          if (y < minY) minY = y;
          if (x > maxX) maxX = x;
          if (y > maxY) maxY = y;
        }
      }
    }
    const k = Math.cos((((minY + maxY) / 2) * Math.PI) / 180);
    const W = 1000;
    const scale = W / ((maxX - minX) * k);
    const H = (maxY - minY) * scale;
    const project = ([x, y]: Position) => [((x - minX) * k * scale).toFixed(1), ((maxY - y) * scale).toFixed(1)];
    const toPath = (g: Geometry | null) =>
      rings(g)
        .map((ring) => "M" + ring.map((p) => project(p).join(",")).join("L") + "Z")
        .join("");
    return { W, H, toPath };
  }, [tracts]);

  const tractPaths = useMemo(
    () => tracts.features.map((f) => ({ f, d: view.toPath(f.geometry) })),
    [tracts, view],
  );
  const floodPath = useMemo(
    () => (sfha ? sfha.features.map((f) => view.toPath(f.geometry)).join("") : ""),
    [sfha, view],
  );

  return (
    <figure className="flex h-full flex-col gap-3">
      <svg
        viewBox={`-20 -20 ${view.W + 40} ${view.H + 40}`}
        className="max-h-[calc(100dvh-11rem)] min-h-0 w-full flex-1"
        role="img"
        aria-label={`Study area: ${tracts.features.length} census tracts with FEMA special flood hazard areas`}
      >
        <path d={floodPath} fill="var(--color-water-deep)" fillOpacity={0.55} fillRule="nonzero" />
        {tractPaths.map(({ f, d }) => (
          <path
            key={f.properties.geoid}
            d={d}
            fill={hover?.properties.geoid === f.properties.geoid ? "var(--color-raised)" : "transparent"}
            fillOpacity={0.7}
            stroke="var(--color-ink)"
            strokeOpacity={0.28}
            strokeWidth={0.9}
            vectorEffect="non-scaling-stroke"
            onMouseEnter={() => setHover(f)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>
      <figcaption className="flex flex-col gap-1.5 text-xs text-muted">
        {hover ? (
          <span className="text-ink">
            {hover.properties.name}, {hover.properties.county_name} ({hover.properties.geoid})
          </span>
        ) : (
          <span>Hover a tract to identify it</span>
        )}
        <span className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-4 rounded-sm bg-water-deep/80" /> FEMA 1% annual chance floodplain
          (where mapped)
        </span>
      </figcaption>
    </figure>
  );
}

function rings(g: Geometry | null): Position[][] {
  if (!g) return [];
  if (g.type === "Polygon") return g.coordinates as Position[][];
  if (g.type === "MultiPolygon") return (g.coordinates as Position[][][]).flat();
  return [];
}
