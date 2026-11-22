"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import maplibregl, { type GeoJSONSource, type Map as MLMap, type MapLayerMouseEvent } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { DEFAULT_REGION, api } from "@/lib/api";
import { RAMPS, type ThemeId, themeById } from "@/lib/themes";
import type { DemographicsRecord, OptimizationResult } from "@/lib/types";
import type { ScenarioBundle } from "@/lib/store";
import { type EdgeFeature, type LayerToggles, tractValue } from "./config";
import { hatchImage, squareIcon } from "./patterns";

export type { EdgeFeature, LayerToggles };


// External raster tiles are opt-in (many free providers now require API keys).
// Without them the map uses the self-hosted major-roads layer for context.
const RAW_TILES = (process.env.NEXT_PUBLIC_BASEMAP_TILES ?? "").trim();
export const BASEMAP_TILES = RAW_TILES && !["none", "off", "false"].includes(RAW_TILES.toLowerCase()) ? RAW_TILES : "";
const BASEMAP_ATTRIBUTION = process.env.NEXT_PUBLIC_BASEMAP_ATTRIBUTION ?? "";
const DATA_ATTRIBUTION = "Roads © OpenStreetMap contributors (ODbL) via Overture Maps · U.S. Census Bureau · FEMA · CDC/ATSDR";
const STUDY_BOUNDS: [number, number, number, number] = [-95.66523, 29.549161, -95.474078, 29.729579];
const EMPTY = { type: "FeatureCollection" as const, features: [] };

export interface HoverInfo {
  x: number;
  y: number;
  title: string;
  lines: string[];
}

interface Props {
  bundle: ScenarioBundle | undefined;
  plan: OptimizationResult | undefined;
  demographics: Map<string, DemographicsRecord>;
  theme: ThemeId;
  layers: LayerToggles;
  selectedTract: string | null;
  onSelectTract: (geoid: string | null) => void;
  selectedHub: string | null;
  onSelectHub: (hubId: string | null) => void;
  pickRoads?: boolean;
  onPickEdge?: (edge: EdgeFeature) => void;
  customClosureFeatures?: EdgeFeature[];
  /** Ask the map to frame a [w,s,e,n] box; change `n` to re-trigger. */
  focus?: { bbox: [number, number, number, number]; n: number } | null;
}

function rampExpression(theme: ThemeId, values: number[]) {
  const t = themeById(theme);
  const [lo, hi0] = t.domain === "data" ? [0, Math.max(1, ...values)] : t.domain;
  const hi = hi0 <= lo ? lo + 1 : hi0;
  const colors = RAMPS[t.ramp];
  const stops: (number | string)[] = [];
  colors.forEach((c, i) => stops.push(lo + ((hi - lo) * i) / (colors.length - 1), c));
  return { expr: ["interpolate", ["linear"], ["to-number", ["get", "v"]], ...stops], lo, hi, colors };
}

export default function CriseesMap(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const hoveredId = useRef<string | number | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  // ---- init map once
  useEffect(() => {
    if (!container.current || mapRef.current) return;
    let map: MLMap;
    try {
      map = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          sources: BASEMAP_TILES
            ? { basemap: { type: "raster", tiles: [BASEMAP_TILES], tileSize: 256, attribution: BASEMAP_ATTRIBUTION, maxzoom: 19 } }
            : {},
          layers: [
            { id: "bg", type: "background", paint: { "background-color": "#0c1822" } },
            ...(BASEMAP_TILES
              ? [{ id: "basemap", type: "raster" as const, source: "basemap", paint: { "raster-opacity": 0.85, "raster-saturation": -0.3 } }]
              : []),
          ],
        },
        bounds: STUDY_BOUNDS,
        fitBoundsOptions: { padding: 40 },
        attributionControl: { compact: true, customAttribution: DATA_ATTRIBUTION },
        dragRotate: false,
        pitchWithRotate: false,
      });
    } catch (e) {
      setMapError(e instanceof Error ? e.message : "WebGL is unavailable in this browser.");
      return;
    }
    mapRef.current = map;
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container.current);
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    map.on("error", () => undefined); // basemap tiles may be unreachable; data layers still render

    map.on("load", () => {
      map.addImage("hatch-unknown", hatchImage("rgba(217,162,91,0.55)"), { pixelRatio: 2 });
      map.addImage("hatch-tract", hatchImage("rgba(150,165,178,0.5)"), { pixelRatio: 2 });
      map.addImage("shelter", squareIcon("#0c1822", "#e8e2cf"), { pixelRatio: 1.5 });
      const add = (id: string) => map.addSource(id, { type: "geojson", data: EMPTY, promoteId: id === "tracts" ? "geoid" : undefined });
      ["coverage", "flood", "tracts", "roads", "closures", "custom", "alloc", "cand", "shelters", "hubs"].forEach(add);

      map.addLayer({ id: "coverage-unknown", type: "fill", source: "coverage", filter: ["==", ["get", "kind"], "no_fema_data"],
        paint: { "fill-pattern": "hatch-unknown", "fill-opacity": 0.55 } });
      map.addLayer({ id: "flood-02", type: "fill", source: "flood", filter: ["==", ["get", "annual_chance_category"], "0.2pct"],
        paint: { "fill-color": "#3e7fa3", "fill-opacity": 0.28 } });
      map.addLayer({ id: "flood-1", type: "fill", source: "flood", filter: ["==", ["get", "annual_chance_category"], "1pct"],
        paint: { "fill-color": "#4fb3e8", "fill-opacity": 0.55 } });
      map.addLayer({ id: "tracts-fill", type: "fill", source: "tracts", filter: ["!=", ["get", "v"], null],
        paint: { "fill-color": "#334", "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.78, 0.58] } });
      map.addLayer({ id: "tracts-unknown", type: "fill", source: "tracts", filter: ["==", ["get", "v"], null],
        paint: { "fill-pattern": "hatch-tract", "fill-opacity": 0.8 } });
      map.addLayer({ id: "tracts-line", type: "line", source: "tracts",
        paint: { "line-color": "#c9d6de", "line-opacity": 0.22, "line-width": 0.6 } });
      map.addLayer({ id: "coverage-line", type: "line", source: "coverage", filter: ["==", ["get", "kind"], "fema_covered"],
        paint: { "line-color": "#63b4d6", "line-width": 1.4, "line-dasharray": [3, 2], "line-opacity": 0.9 } });
      map.addLayer({ id: "study-line", type: "line", source: "coverage", filter: ["==", ["get", "kind"], "study_area"],
        paint: { "line-color": "#e8e2cf", "line-width": 1.6, "line-opacity": 0.7 } });
      map.addLayer({ id: "roads", type: "line", source: "roads",
        paint: {
          "line-color": ["match", ["get", "road_class"], "motorway", "#a9b7c2", "trunk", "#98a8b4", "primary", "#7f909d", "#5d6e7b"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 10, ["match", ["get", "road_class"], "motorway", 1.6, "trunk", 1.3, "primary", 1, 0.5],
            15, ["match", ["get", "road_class"], "motorway", 5, "trunk", 4, "primary", 3, 1.6]],
          "line-opacity": 0.55,
        } });
      map.addLayer({ id: "tract-selected", type: "line", source: "tracts", filter: ["==", ["get", "geoid"], ""],
        paint: { "line-color": "#ffffff", "line-width": 2.6 } });
      map.addLayer({ id: "closures", type: "line", source: "closures",
        paint: { "line-color": "#ff4d5e", "line-width": ["interpolate", ["linear"], ["zoom"], 10, 1.4, 15, 4], "line-opacity": 0.95 } });
      map.addLayer({ id: "custom-closures", type: "line", source: "custom",
        paint: { "line-color": "#ffd166", "line-width": 4, "line-opacity": 0.95 } });
      map.addLayer({ id: "alloc", type: "line", source: "alloc",
        paint: { "line-color": "#e8e2cf", "line-width": ["interpolate", ["linear"], ["get", "persons"], 0, 0.8, 600, 4],
          "line-dasharray": [1.5, 1.5], "line-opacity": 0.75 } });
      map.addLayer({ id: "cand", type: "circle", source: "cand",
        paint: { "circle-radius": 3.2, "circle-color": "#0c1822", "circle-stroke-color": "#9fb3c0", "circle-stroke-width": 1.2 } });
      map.addLayer({ id: "shelters", type: "symbol", source: "shelters",
        layout: { "icon-image": "shelter", "icon-allow-overlap": true, "icon-size": 0.9 } });
      map.addLayer({ id: "shelters-unknown", type: "circle", source: "shelters", filter: ["==", ["get", "flood_status"], "unknown_no_fema_data"],
        paint: { "circle-radius": 9, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#d9a25b", "circle-stroke-width": 1, "circle-stroke-opacity": 0.8 } });
      map.addLayer({ id: "hubs-halo", type: "circle", source: "hubs",
        paint: { "circle-radius": ["interpolate", ["linear"], ["get", "persons_assigned"], 0, 9, 600, 17], "circle-color": "#7ee0b5", "circle-opacity": 0.18 } });
      map.addLayer({ id: "hubs", type: "circle", source: "hubs",
        paint: { "circle-radius": ["interpolate", ["linear"], ["get", "persons_assigned"], 0, 5, 600, 9], "circle-color": "#7ee0b5",
          "circle-stroke-color": ["case", ["==", ["get", "hub_id"], ""], "#ffffff", "#0c1822"], "circle-stroke-width": 2 } });
      setReady(true);
    });

    // ---- interactions
    const tooltip = (e: MapLayerMouseEvent, title: string, lines: string[]) =>
      setHover({ x: e.point.x, y: e.point.y, title, lines });

    map.on("mousemove", "tracts-fill", (e) => onTractHover(e));
    map.on("mousemove", "tracts-unknown", (e) => onTractHover(e));
    function onTractHover(e: MapLayerMouseEvent) {
      const f = e.features?.[0];
      if (!f) return;
      if (hoveredId.current !== null) map.setFeatureState({ source: "tracts", id: hoveredId.current }, { hover: false });
      hoveredId.current = f.id ?? null;
      if (f.id !== undefined) map.setFeatureState({ source: "tracts", id: f.id }, { hover: true });
      const p = f.properties as Record<string, unknown>;
      const theme = themeById(propsRef.current.theme);
      const v = typeof p.v === "number" ? theme.format(p.v) : "Unknown (no data)";
      tooltip(e, String(p.name ?? p.geoid), [`${theme.short}: ${v}`, `Tract ${p.geoid}`]);
    }
    const leaveTracts = () => {
      if (hoveredId.current !== null) map.setFeatureState({ source: "tracts", id: hoveredId.current }, { hover: false });
      hoveredId.current = null;
      setHover(null);
    };
    map.on("mouseleave", "tracts-fill", leaveTracts);
    map.on("mouseleave", "tracts-unknown", leaveTracts);

    for (const layer of ["hubs", "cand", "shelters", "closures"]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = propsRef.current.pickRoads ? "crosshair" : "";
        setHover(null);
      });
    }
    map.on("mousemove", "hubs", (e) => {
      const p = e.features?.[0]?.properties as Record<string, unknown>;
      if (p) tooltip(e, String(p.name ?? p.hub_id), [`Selected pickup hub · ${Number(p.persons_assigned).toFixed(0)} persons assigned`, "Click for allocation details"]);
    });
    map.on("mousemove", "cand", (e) => {
      const p = e.features?.[0]?.properties as Record<string, unknown>;
      if (p) tooltip(e, String(p.name ?? "Candidate hub"), [`Candidate pickup hub (${p.category}), unvalidated`]);
    });
    map.on("mousemove", "shelters", (e) => {
      const p = e.features?.[0]?.properties as Record<string, unknown>;
      if (p) tooltip(e, String(p.name ?? "Assumed shelter"), ["Assumed shelter: NOT a verified evacuation shelter",
        p.flood_status === "unknown_no_fema_data" ? "Flood status: unknown (no FEMA data)" : `Flood status: ${String(p.flood_status).replaceAll("_", " ")}`]);
    });
    map.on("mousemove", "closures", (e) => {
      const p = e.features?.[0]?.properties as Record<string, unknown>;
      if (p) tooltip(e, String(p.name ?? p.road_class), ["Simulated closure (hypothetical)", `${Number(p.length_m).toFixed(0)} m · ${p.road_class}`]);
    });

    map.on("click", async (e) => {
      const P = propsRef.current;
      if (P.pickRoads && P.onPickEdge) {
        const d = 0.0012;
        const { lng, lat } = e.lngLat;
        try {
          const fc = await api.edgesNear(DEFAULT_REGION, [lng - d, lat - d, lng + d, lat + d]);
          const best = nearestEdge(fc.features as EdgeFeature[], lng, lat);
          if (best) P.onPickEdge(best);
        } catch {
          /* ignore: no road near click */
        }
        return;
      }
      const hub = map.queryRenderedFeatures(e.point, { layers: ["hubs"] })[0];
      if (hub) {
        P.onSelectHub(String(hub.properties?.hub_id));
        return;
      }
      const tract = map.queryRenderedFeatures(e.point, { layers: ["tracts-fill", "tracts-unknown"] })[0];
      P.onSelectTract(tract ? String(tract.properties?.geoid) : null);
    });

    return () => {
      ro.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- static layers (fetched once, lazily for heavy ones)
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current!;
    const ctrl = new AbortController();
    api.floodCoverage(DEFAULT_REGION, ctrl.signal).then((d) => (map.getSource("coverage") as GeoJSONSource).setData(d as never)).catch(() => undefined);
    api.contextRoads(DEFAULT_REGION, ctrl.signal).then((d) => (map.getSource("roads") as GeoJSONSource).setData(d as never)).catch(() => undefined);
    api.planningSites(DEFAULT_REGION, ctrl.signal).then((d) => {
      (map.getSource("cand") as GeoJSONSource).setData(d.hubs as never);
      (map.getSource("shelters") as GeoJSONSource).setData(d.shelters as never);
    }).catch(() => undefined);
    return () => ctrl.abort();
  }, [ready]);

  const floodLoaded = useRef(false);
  useEffect(() => {
    if (!ready || !props.layers.floodZones || floodLoaded.current) return;
    floodLoaded.current = true;
    api.floodHazards(DEFAULT_REGION).then((d) => (mapRef.current?.getSource("flood") as GeoJSONSource | undefined)?.setData(d as never))
      .catch(() => (floodLoaded.current = false));
  }, [ready, props.layers.floodZones]);

  // ---- tract choropleth (real API values merged per tract)
  const tractData = useMemo(() => {
    const feats = props.bundle?.accessibility.features ?? [];
    const planByTract = new Map(props.plan?.tracts.map((t) => [t.geoid, t]) ?? []);
    return {
      type: "FeatureCollection" as const,
      features: feats.map((f) => {
        const d = props.demographics.get(f.properties.geoid);
        const plan = planByTract.get(f.properties.geoid);
        const merged: Record<string, unknown> = {
          ...f.properties,
          pct_households_no_vehicle: d?.demographics.pct_households_no_vehicle ?? null,
          pct_below_poverty: d?.demographics.pct_below_poverty ?? null,
          pct_with_disability: d?.demographics.pct_with_disability ?? null,
          svi_rpl_themes: d?.vulnerability?.rpl_themes ?? null,
          plan_coverage: plan ? plan.coverage : null,
        };
        merged.v = tractValue(props.theme, merged);
        return { type: "Feature" as const, geometry: f.geometry, properties: merged };
      }),
    };
  }, [props.bundle, props.plan, props.demographics, props.theme]);

  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current!;
    (map.getSource("tracts") as GeoJSONSource).setData(tractData as never);
    const values = tractData.features.map((f) => f.properties.v).filter((v): v is number => typeof v === "number");
    map.setPaintProperty("tracts-fill", "fill-color", rampExpression(props.theme, values).expr as never);
  }, [ready, tractData, props.theme]);

  useEffect(() => {
    if (!ready) return;
    mapRef.current!.setFilter("tract-selected", ["==", ["get", "geoid"], props.selectedTract ?? ""]);
  }, [ready, props.selectedTract]);

  // ---- closures
  useEffect(() => {
    if (!ready) return;
    (mapRef.current!.getSource("closures") as GeoJSONSource).setData((props.bundle?.closures ?? EMPTY) as never);
  }, [ready, props.bundle]);

  useEffect(() => {
    if (!ready) return;
    (mapRef.current!.getSource("custom") as GeoJSONSource).setData(
      { type: "FeatureCollection", features: props.customClosureFeatures ?? [] } as never);
  }, [ready, props.customClosureFeatures]);

  // ---- optimiser outputs
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current!;
    const hubs = props.plan?.hubs ?? [];
    const shelters = new Map(props.plan?.shelters.map((s) => [s.facility_id, s]) ?? []);
    (map.getSource("hubs") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: hubs.map((h) => ({ type: "Feature", geometry: { type: "Point", coordinates: [h.lon, h.lat] },
        properties: { hub_id: h.hub_id, name: h.name, persons_assigned: h.persons_assigned } })),
    } as never);
    (map.getSource("alloc") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: hubs.flatMap((h) => h.legs.map((l) => {
        const s = shelters.get(l.shelter_id);
        return s ? { type: "Feature", geometry: { type: "LineString", coordinates: [[h.lon, h.lat], [s.lon, s.lat]] },
          properties: { persons: l.persons, hub_id: h.hub_id } } : null;
      }).filter(Boolean)),
    } as never);
  }, [ready, props.plan]);

  useEffect(() => {
    if (!ready) return;
    mapRef.current!.setPaintProperty("hubs", "circle-stroke-color",
      ["case", ["==", ["get", "hub_id"], props.selectedHub ?? ""], "#ffffff", "#0c1822"]);
    mapRef.current!.setPaintProperty("alloc", "line-opacity",
      props.selectedHub ? ["case", ["==", ["get", "hub_id"], props.selectedHub], 0.95, 0.2] : 0.75);
  }, [ready, props.selectedHub]);

  // ---- layer visibility
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current!;
    const L = props.layers;
    const vis: Record<string, boolean> = {
      basemap: L.basemap, roads: L.roads, "tracts-fill": L.tracts, "tracts-unknown": L.tracts, "tracts-line": L.tracts,
      "flood-1": L.floodZones, "flood-02": L.floodZones, "coverage-unknown": L.coverage, "coverage-line": L.coverage,
      closures: L.closures, "custom-closures": L.closures, cand: L.candidateHubs, shelters: L.shelters, "shelters-unknown": L.shelters,
      hubs: L.selectedHubs, "hubs-halo": L.selectedHubs, alloc: L.allocations,
    };
    for (const [id, on] of Object.entries(vis)) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  }, [ready, props.layers]);

  useEffect(() => {
    if (!ready) return;
    mapRef.current!.getCanvas().style.cursor = props.pickRoads ? "crosshair" : "";
  }, [ready, props.pickRoads]);

  useEffect(() => {
    if (!ready || !props.focus) return;
    const [w, s2, e, n] = props.focus.bbox;
    mapRef.current!.fitBounds([[w, s2], [e, n]], { padding: 50, duration: 900, maxZoom: 14 });
  }, [ready, props.focus]);

  // Fly to the selected hub.
  useEffect(() => {
    if (!ready || !props.selectedHub) return;
    const h = props.plan?.hubs.find((x) => x.hub_id === props.selectedHub);
    if (h) mapRef.current!.easeTo({ center: [h.lon, h.lat], zoom: Math.max(mapRef.current!.getZoom(), 13), duration: 600 });
  }, [ready, props.selectedHub, props.plan]);

  if (mapError) {
    return (
      <div className="grid h-full place-items-center p-6 text-center text-sm text-muted">
        <p>The interactive map needs WebGL, which is unavailable here ({mapError}). All analysis panels still work.</p>
      </div>
    );
  }

  return (
    <div className="absolute inset-0">
      <div ref={container} className="h-full w-full" role="application" aria-label="Interactive map of the southwest Houston study area" />
      {hover && (
        <div className="pointer-events-none absolute z-10 max-w-64 rounded-md border border-rule bg-panel/95 px-3 py-2 text-xs shadow-lg backdrop-blur"
          style={{ left: Math.min(hover.x + 14, 9999), top: hover.y + 14 }}>
          <p className="font-medium text-ink">{hover.title}</p>
          {hover.lines.map((l) => <p key={l} className="text-muted">{l}</p>)}
        </div>
      )}
      {!ready && <div className="absolute inset-0 grid place-items-center text-sm text-muted">Loading map…</div>}
    </div>
  );
}

function nearestEdge(features: EdgeFeature[], lng: number, lat: number): EdgeFeature | null {
  let best: { f: (typeof features)[number]; d: number } | null = null;
  const k = Math.cos((lat * Math.PI) / 180);
  for (const f of features) {
    if (!f.geometry || f.geometry.type !== "LineString") continue;
    const pts = f.geometry.coordinates as [number, number][];
    for (let i = 0; i < pts.length - 1; i++) {
      const d = segDist(lng * k, lat, pts[i][0] * k, pts[i][1], pts[i + 1][0] * k, pts[i + 1][1]);
      if (!best || d < best.d) best = { f, d };
    }
  }
  return best ? best.f : null;
}

function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number) {
  const dx = bx - ax, dy = by - ay;
  const t = dx || dy ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export { rampExpression };
