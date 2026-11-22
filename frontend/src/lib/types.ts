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

// ---------------------------------------------------------------- Phase 2
// Mirrors backend/app/engine/params.py and backend/app/schemas/analysis.py.

export type PresetName = "baseline" | "moderate" | "severe";

export interface ScenarioSpec {
  name: string;
  seed: number;
  one_pct_closure_prob: number;
  point_two_pct_closure_prob: number;
  min_exposed_m: number;
  overbank_buffer_m: number;
  overbank_closure_prob: number;
  unknown_coverage_policy: "no_inference" | "stress_sample";
  unknown_closure_prob: number;
  custom_closed_edge_ids: string[];
}

export interface ScenarioPreset {
  name: PresetName;
  description: string;
  spec: ScenarioSpec;
}

export interface AccessParams {
  walk_max_m: number;
  drive_thresholds_min?: number[];
  shelter_categories?: string[];
  exclude_shelters_in_1pct_zone?: boolean;
}

export interface ResourceParams {
  max_active_hubs: number;
  vehicles: number;
  vehicle_capacity: number;
  horizon_min: number;
  dwell_min: number;
  hub_capacity: number;
  shelter_capacity: number;
  shelters_per_hub: number;
}

export interface WeightParams {
  mode: "equity" | "equal";
  beta_poverty: number;
  beta_disability: number;
  beta_age65: number;
}

export interface ScenarioEvaluation {
  scenario_id: string;
  region_id: string;
  spec: ScenarioSpec;
  description: string;
  closures: {
    closed_directed_edges: number;
    closed_segments: number;
    closed_length_km: number;
    closed_segments_by_rule: Record<string, number>;
    unknown_coverage_segments: number;
    unknown_coverage_length_km: number;
    unknown_coverage_policy: string;
    note: string;
  };
  network: { baseline: Record<string, number>; scenario: Record<string, number> };
  access_change: Record<string, number | null>;
  speed_model: Record<string, number>;
  timings_s: Record<string, number>;
  disclaimer: string;
  cache: string;
}

export interface AccessTractProps {
  geoid: string;
  name?: string;
  origins: number;
  demand_est: number | null;
  drive_min_to_nearest_shelter: number | null;
  drive_min_to_nearest_shelter_baseline: number | null;
  delta_drive_min_to_nearest_shelter: number | null;
  share_demand_no_drive_route_to_shelter: number | null;
  share_demand_no_drive_route_to_shelter_baseline: number | null;
  newly_no_drive_route_share: number | null;
  walk_m_to_nearest_hub: number | null;
  walk_min_to_nearest_hub: number | null;
  share_demand_within_walk_of_hub: number | null;
  share_demand_within_walk_of_hub_baseline: number | null;
  share_demand_within_walk_of_shelter: number | null;
  lost_share_within_walk_of_hub: number | null;
  hubs_within_walk: number | null;
  disconnected_from_shelters: boolean;
  demand_weighted_walk_access_loss: number | null;
  demand_newly_without_drive_route: number | null;
  [key: string]: unknown;
}

export interface AccessSummaryBlock {
  demand_share_within_walk_of_hub: number | null;
  demand_share_within_walk_of_shelter: number | null;
  demand_share_no_drive_route_to_shelter: number | null;
  mean_drive_min_to_nearest_shelter: number | null;
}

export interface AccessibilityResult {
  type: "FeatureCollection";
  scenario_id: string;
  summary: {
    total_demand_est: number;
    baseline: AccessSummaryBlock;
    scenario: AccessSummaryBlock;
    tracts_disconnected_from_shelters: number;
    tracts_with_walk_access_loss: number;
    tracts_with_longer_drive: number;
    demand_weighted_walk_access_loss: number;
    demand_newly_without_drive_route: number;
  };
  features: Feature<AccessTractProps>[];
  units: Record<string, string>;
  method_notes: string[];
  disclaimer: string;
  cache: string;
}

export interface OptimizationTotals {
  demand_est: number;
  served: number;
  served_via_hubs: number;
  served_by_direct_walk_to_shelter: number;
  unmet: number;
  coverage: number | null;
  weighted_unmet_run_weights: number;
  weighted_unmet_equity_weights: number;
  weighted_coverage_equity_weights: number | null;
  active_hubs: number;
  vehicle_trips: number;
  vehicle_minutes_used: number | null;
  vehicle_minutes_available: number;
  fleet_utilization: number | null;
  mean_walk_m_served_via_hub: number | null;
  mean_bus_drive_min: number | null;
  mean_seat_occupancy: number | null;
}

export interface TercileOutcome {
  tracts: number;
  demand: number;
  served: number;
  coverage: number | null;
}

export interface BindingConstraints {
  hub_budget_used: string;
  hubs_at_capacity: number;
  shelters_at_capacity: number;
  shelters_used: number;
  fleet_time_binding: boolean;
  demand_without_any_walkable_hub_or_shelter: number;
}

export interface HubLeg {
  shelter_id: string;
  shelter_name: string | null;
  persons: number;
  trips: number;
  drive_min: number;
  round_trip_min: number;
}

export interface ActivatedHub {
  hub_id: string;
  facility_id: string;
  name: string | null;
  category: string;
  lon: number;
  lat: number;
  flood_status: string;
  persons_assigned: number;
  capacity_utilization: number | null;
  mean_walk_m: number | null;
  origins_served: number;
  legs: HubLeg[];
}

export interface ShelterUse {
  facility_id: string;
  name: string | null;
  lon: number;
  lat: number;
  flood_status: string;
  persons: number;
  capacity_utilization: number | null;
}

export interface TractOutcome {
  geoid: string;
  demand: number;
  served_via_hubs: number;
  served_by_direct_walk: number;
  unmet: number;
  coverage: number | null;
  weight: number | null;
  priority_tercile: number;
}

export interface SolverReport {
  status: string;
  message: string;
  objective: number | null;
  mip_gap: number | null;
  dual_bound: number | null;
  solve_seconds: number;
  build_seconds: number;
  model_size: Record<string, number>;
  screening: Record<string, unknown>;
  engine: string;
  optimality_claim: string;
}

export interface ConstraintCheck {
  feasible: boolean;
  tolerance?: number;
  max_violation?: Record<string, number>;
  max_trip_integrality_gap?: number;
  vehicle_minutes_used?: number;
  vehicle_minutes_available?: number;
  active_hubs?: number;
}

export interface OptimizationResult {
  region_id: string;
  scenario_id: string;
  scenario: ScenarioSpec;
  totals: OptimizationTotals;
  binding_constraints: BindingConstraints;
  distribution_by_priority_tercile: Record<string, TercileOutcome>;
  hubs: ActivatedHub[];
  shelters: ShelterUse[];
  tracts: TractOutcome[];
  solver: SolverReport;
  constraint_check: ConstraintCheck;
  weights_used: WeightParams;
  assumptions: Record<string, unknown>;
  timings_s: Record<string, number>;
  disclaimer: string;
  cache: string;
}

export interface ComparisonCase {
  case: string;
  label: string;
  scenario_id: string;
  totals: OptimizationTotals;
  distribution_by_priority_tercile: Record<string, TercileOutcome>;
  binding_constraints: BindingConstraints;
  solver_status: string;
  mip_gap: number | null;
  constraint_check_feasible: boolean;
  active_hub_ids: string[];
}

export interface ComparisonResult {
  region_id: string;
  scenario_id: string;
  disrupted_scenario: ScenarioSpec;
  cases: ComparisonCase[];
  deltas: Record<string, Record<string, number | null>>;
  findings: string[];
  accessibility_change: AccessibilityResult["summary"];
  most_affected_tracts: Record<string, number | string | null>[];
  identical_inputs: Record<string, unknown>;
  disclaimer: string;
  cache: string;
}

export interface DemoResult {
  title: string;
  story: string[];
  request: Record<string, unknown>;
  reproduce: string;
  result: ComparisonResult;
}

export interface DemographicsRecord {
  demographics: {
    geoid: string;
    total_population: number | null;
    households_total: number | null;
    households_no_vehicle: number | null;
    pct_households_no_vehicle: number | null;
    pct_below_poverty: number | null;
    pct_65_plus: number | null;
    pct_with_disability: number | null;
    missing_fields: string[];
    acs_vintage: string;
  };
  vulnerability: {
    rpl_themes: number | null;
    rpl_theme4_housing_transport: number | null;
    svi_year: number;
  } | null;
}

export interface Methodology {
  units: Record<string, string>;
  speed_model: { posted_speed_used_if_within_kph: number[]; class_default_kph: Record<string, number>; walk_speed_m_per_min: number };
  defaults: Record<string, Record<string, unknown>>;
  scenario_presets: ScenarioPreset[];
  optimization_model: { objective: string; constraints: string[]; approximation: string };
  equity_weights: string;
  disclaimer: string;
}

export interface EdgeProps {
  edge_id: string;
  road_class: string;
  name: string | null;
  length_m: number;
}
