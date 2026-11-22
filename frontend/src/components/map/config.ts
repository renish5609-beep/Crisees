import type { ThemeId } from "@/lib/themes";
import type { EdgeProps } from "@/lib/types";

export interface LayerToggles {
  basemap: boolean;
  roads: boolean;
  tracts: boolean;
  floodZones: boolean;
  coverage: boolean;
  closures: boolean;
  candidateHubs: boolean;
  shelters: boolean;
  selectedHubs: boolean;
  allocations: boolean;
}

export const DEFAULT_LAYERS: LayerToggles = {
  basemap: Boolean((process.env.NEXT_PUBLIC_BASEMAP_TILES ?? "").trim()) && !["none", "off", "false"].includes((process.env.NEXT_PUBLIC_BASEMAP_TILES ?? "").trim().toLowerCase()),
  roads: true, tracts: true, floodZones: true, coverage: true, closures: true,
  candidateHubs: false, shelters: true, selectedHubs: true, allocations: true,
};

export interface EdgeFeature {
  type: "Feature";
  geometry: { type: string; coordinates: unknown } | null;
  properties: EdgeProps;
}

export function tractValue(theme: ThemeId, p: Record<string, unknown>): number | null {
  const v = p[theme];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
