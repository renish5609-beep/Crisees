// Thematic map metrics. Every metric reads a field that exists in a real API
// response; null values are drawn as "unknown" (hatched), never as zero.

export type ThemeId =
  | "demand_est"
  | "pct_households_no_vehicle"
  | "pct_below_poverty"
  | "pct_with_disability"
  | "svi_rpl_themes"
  | "share_demand_within_walk_of_hub"
  | "lost_share_within_walk_of_hub"
  | "newly_no_drive_route_share"
  | "drive_min_to_nearest_shelter"
  | "plan_coverage";

export interface Theme {
  id: ThemeId;
  label: string;
  short: string;
  group: "Demographics (ACS 2020–2024)" | "Accessibility (modelled)" | "Intervention (optimiser)";
  domain: [number, number] | "data";
  ramp: "need" | "access" | "loss";
  format: (v: number) => string;
  description: string;
}

const pct = (v: number) => `${v.toFixed(1)}%`;
const share = (v: number) => `${(v * 100).toFixed(0)}%`;

export const THEMES: Theme[] = [
  { id: "demand_est", label: "Estimated assistance demand", short: "Demand (persons)", group: "Demographics (ACS 2020–2024)", domain: "data", ramp: "need",
    format: (v) => v.toFixed(0), description: "Persons in zero-vehicle households × 50% hypothetical participation." },
  { id: "pct_households_no_vehicle", label: "Households without a vehicle", short: "No vehicle", group: "Demographics (ACS 2020–2024)", domain: [0, 40], ramp: "need",
    format: pct, description: "ACS B08201. Observed estimate." },
  { id: "pct_below_poverty", label: "Population below poverty", short: "Below poverty", group: "Demographics (ACS 2020–2024)", domain: [0, 55], ramp: "need",
    format: pct, description: "ACS B17001. Observed estimate." },
  { id: "pct_with_disability", label: "Population with a disability", short: "Disability", group: "Demographics (ACS 2020–2024)", domain: [0, 30], ramp: "need",
    format: pct, description: "ACS C18108. Observed estimate." },
  { id: "svi_rpl_themes", label: "CDC Social Vulnerability (2020)", short: "SVI", group: "Demographics (ACS 2020–2024)", domain: [0, 1], ramp: "need",
    format: (v) => v.toFixed(2), description: "CDC/ATSDR SVI 2020 overall percentile (US-wide)." },
  { id: "share_demand_within_walk_of_hub", label: "Demand within walking distance of a hub", short: "Walk access", group: "Accessibility (modelled)", domain: [0, 1], ramp: "access",
    format: share, description: "Share of tract demand within the walking limit of any candidate hub, in the selected scenario." },
  { id: "lost_share_within_walk_of_hub", label: "Walk access lost to the flood", short: "Walk access lost", group: "Accessibility (modelled)", domain: [0, 0.5], ramp: "loss",
    format: share, description: "Baseline minus scenario share of demand within walking distance of a hub." },
  { id: "newly_no_drive_route_share", label: "Demand newly without a drive route", short: "Drive route lost", group: "Accessibility (modelled)", domain: [0, 0.5], ramp: "loss",
    format: share, description: "Share of tract demand whose origins lose every drive route to an assumed shelter." },
  { id: "drive_min_to_nearest_shelter", label: "Drive time to nearest assumed shelter", short: "Drive min", group: "Accessibility (modelled)", domain: [0, 8], ramp: "loss",
    format: (v) => `${v.toFixed(1)} min`, description: "Free-flow estimate on the scenario network; unreachable shown as unknown." },
  { id: "plan_coverage", label: "Share of demand served by the plan", short: "Plan coverage", group: "Intervention (optimiser)", domain: [0, 1], ramp: "access",
    format: share, description: "Optimiser output for the last successful run." },
];

export const themeById = (id: ThemeId) => THEMES.find((t) => t.id === id)!;

export const RAMPS: Record<Theme["ramp"], string[]> = {
  need: ["#1b2c3a", "#3d4f6b", "#7a5f8f", "#c06f86", "#f1a17a"],
  access: ["#5a2a2a", "#7b4a35", "#6c7a52", "#3f9c8d", "#79d0d8"],
  loss: ["#2a4657", "#3f6a7a", "#c98b45", "#e0614f", "#ff3d5a"],
};
