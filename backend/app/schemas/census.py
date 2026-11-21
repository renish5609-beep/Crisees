from __future__ import annotations

from pydantic import BaseModel, Field

GEOID_PATTERN = r"^\d{11}$"


class CensusTract(BaseModel):
    geoid: str = Field(pattern=GEOID_PATTERN, description="11-digit tract GEOID: state(2)+county(3)+tract(6).")
    state_fips: str
    county_fips: str
    tract_code: str
    name: str
    county_name: str | None = None
    land_area_m2: float | None = None
    water_area_m2: float | None = None
    internal_point: tuple[float, float] | None = Field(default=None, description="[lon, lat] Census internal point")
    tiger_year: int
    source_id: str


class DemographicIndicators(BaseModel):
    """ACS 5-year estimates for one tract.

    ``None`` means *not available* (suppressed, missing, or zero denominator);
    it is never silently converted to 0. Percentages are 0-100.
    """

    geoid: str = Field(pattern=GEOID_PATTERN)
    acs_vintage: str = Field(description="e.g. '2020-2024 ACS 5-year'")
    total_population: int | None
    total_population_moe: float | None = None
    households_total: int | None
    households_no_vehicle: int | None
    households_no_vehicle_moe: float | None = None
    pct_households_no_vehicle: float | None
    poverty_universe: int | None = Field(description="Population for whom poverty status is determined (C17002_001)")
    population_below_poverty: int | None
    population_below_poverty_moe: float | None = None
    pct_below_poverty: float | None
    population_below_150pct_poverty: int | None
    pct_below_150pct_poverty: float | None
    population_65_plus: int | None
    population_65_plus_moe: float | None = None
    pct_65_plus: float | None
    disability_universe: int | None = Field(description="Civilian noninstitutionalized population (C18108_001)")
    population_with_disability: int | None
    population_with_disability_moe: float | None = None
    pct_with_disability: float | None
    missing_fields: list[str] = Field(default_factory=list, description="Fields whose value is None and why")
    quality_flags: list[str] = Field(default_factory=list)
    source_id: str


class VulnerabilityIndicators(BaseModel):
    """CDC/ATSDR SVI variables preserved individually (no composite re-weighting).

    ``rpl_*`` values are the CDC's own percentile rankings (0-1) *within the
    nation*, as published. Phase 2 must not treat them as independent of the
    ACS indicators above: they overlap.
    """

    geoid: str = Field(pattern=GEOID_PATTERN)
    svi_year: int
    svi_geography: str = Field(description="e.g. 'US-wide percentile ranking'")
    rpl_themes: float | None = None
    rpl_theme1_socioeconomic: float | None = None
    rpl_theme2_household: float | None = None
    rpl_theme3_minority_language: float | None = None
    rpl_theme4_housing_transport: float | None = None
    ep_pov150: float | None = None
    ep_unemp: float | None = None
    ep_nohsdp: float | None = None
    ep_uninsur: float | None = None
    ep_age65: float | None = None
    ep_age17: float | None = None
    ep_disabl: float | None = None
    ep_sngpnt: float | None = None
    ep_limeng: float | None = None
    ep_minrty: float | None = None
    ep_munit: float | None = None
    ep_mobile: float | None = None
    ep_crowd: float | None = None
    ep_noveh: float | None = None
    ep_groupq: float | None = None
    f_total: int | None = Field(default=None, description="Count of SVI flags (>= 90th percentile)")
    missing_fields: list[str] = Field(default_factory=list)
    source_id: str


class TractDemographics(BaseModel):
    demographics: DemographicIndicators
    vulnerability: VulnerabilityIndicators | None = None
