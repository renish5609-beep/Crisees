// Types mirroring the backend's Pydantic schemas (backend/app/schemas).
// Geometry is GeoJSON, EPSG:4326, [longitude, latitude].

export type Provenance = "real" | "derived" | "synthetic";

export interface SourceAttribution {
  source_id: string;
  name: string;
  publisher: string;
  url?: string | null;
  license?: string | null;
  vintage?: string | null;
  retrieved_at?: string | null;
  notes?: string | null;
}

export interface Health {
  status: string;
  version: string;
  environment: string;
  time: string;
  data_dir_exists: boolean;
  regions_configured: number;
  regions_with_processed_data: number;
}

export type DatasetState = "available" | "missing" | "invalid";

export interface DatasetStatus {
  dataset: string;
  title: string;
  state: DatasetState;
  record_count: number | null;
  provenance: Provenance | null;
  file: string | null;
  size_bytes: number | null;
  generated_at: string | null;
  provider: string | null;
  sources: SourceAttribution[];
  notes: string[];
}

export interface GeographicRegion {
  region_id: string;
  name: string;
  description: string;
  county_names: Record<string, string>;
  selection_bbox: [number, number, number, number];
  study_area_bbox: [number, number, number, number] | null;
  analysis_crs: string;
  acs_year: number;
  tiger_year: number;
  selection_rule: string;
  justification: string[];
  datasets: DatasetStatus[];
  pipeline_generated_at: string | null;
}

export type Position = [number, number];
export interface Geometry {
  type: "Polygon" | "MultiPolygon" | "LineString" | "Point" | string;
  coordinates: unknown;
}

export interface Feature<P> {
  type: "Feature";
  id: string | number | null;
  geometry: Geometry | null;
  properties: P;
}

export interface PageInfo {
  total: number;
  limit: number;
  offset: number;
  returned: number;
  next_offset: number | null;
}

export interface FeatureCollection<P> {
  type: "FeatureCollection";
  features: Feature<P>[];
  page: PageInfo;
  provenance: Provenance;
  sources: SourceAttribution[];
}

export interface TractProps {
  geoid: string;
  name: string;
  county_name: string | null;
}

export interface FloodProps {
  hazard_id: string;
  flood_zone: string | null;
  is_sfha: boolean | null;
  annual_chance_category: string;
}

export interface RegionSummary {
  region_id: string;
  name: string;
  population: {
    tract_count: number;
    total_population: number | null;
    households_total: number | null;
    households_no_vehicle: number | null;
    pct_households_no_vehicle: number | null;
    pct_below_poverty: number | null;
    pct_65_plus: number | null;
    pct_with_disability: number | null;
    tracts_with_missing_values: number;
  } | null;
  roads: {
    node_count: number;
    edge_count: number;
    total_length_km: number;
    largest_scc_node_fraction: number;
    provider: string | null;
  } | null;
  facilities: {
    facility_count: number;
    by_category: Record<string, number>;
    candidate_hub_count: number;
    authority_verified_shelters: number;
  } | null;
  flood: {
    polygon_count: number;
    sfha_area_km2: number;
    covered_area_fraction: number | null;
    dfirm_ids: string[];
    tracts_intersecting_sfha: number | null;
  } | null;
  unavailable_datasets: string[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}
