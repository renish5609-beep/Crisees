import pytest
from pydantic import ValidationError

from app.regions import RegionDefinition, load_regions
from app.schemas.census import CensusTract, DemographicIndicators
from app.schemas.common import Feature, GeoJSONGeometry, Provenance
from app.schemas.facilities import EmergencyFacility, VerificationStatus
from app.schemas.flood import FloodHazardArea, HazardEvidenceType


def test_tract_rejects_malformed_geoid():
    with pytest.raises(ValidationError):
        CensusTract(geoid="4820141010", state_fips="48", county_fips="201", tract_code="410100", name="x",
                    tiger_year=2024, source_id="s")


def test_demographics_allow_none_for_missing():
    d = DemographicIndicators(
        geoid="48201410100", acs_vintage="v", total_population=None, households_total=None,
        households_no_vehicle=None, pct_households_no_vehicle=None, poverty_universe=None,
        population_below_poverty=None, pct_below_poverty=None, population_below_150pct_poverty=None,
        pct_below_150pct_poverty=None, population_65_plus=None, pct_65_plus=None, disability_universe=None,
        population_with_disability=None, pct_with_disability=None, source_id="s",
    )
    assert d.total_population is None  # not coerced to 0


def test_facility_defaults_to_unverified():
    f = EmergencyFacility(facility_id="f", name="n", category="library", source_category="amenity=library",
                          lon=-95.5, lat=29.6, source_id="s", source_record_id="1")
    assert f.verification_status is VerificationStatus.mapped_unverified
    assert f.is_designated_evacuation_shelter is None


def test_flood_defaults_to_fema_regulatory():
    h = FloodHazardArea(hazard_id="h", flood_zone="AE", is_sfha=True, annual_chance_category="1pct", source_id="s")
    assert h.evidence_type is HazardEvidenceType.fema_regulatory
    assert {e.value for e in HazardEvidenceType} == {"fema_regulatory", "observed", "simulated"}


def test_geojson_feature_shape():
    from app.schemas.roads import RoadNode

    f = Feature[RoadNode](id=1, geometry=GeoJSONGeometry(type="Point", coordinates=[-95.5, 29.6]),
                          properties=RoadNode(node_id=1, lon=-95.5, lat=29.6))
    dumped = f.model_dump()
    assert dumped["type"] == "Feature" and dumped["geometry"]["coordinates"] == [-95.5, 29.6]
    with pytest.raises(ValidationError):
        GeoJSONGeometry(type="Circle", coordinates=[0, 0])


def test_provenance_values():
    assert {p.value for p in Provenance} == {"real", "derived", "synthetic"}


def test_region_registry_valid():
    regions = load_regions()
    r = regions["houston-sw-pilot"]
    assert r.county_geoids == ["48201", "48157"]
    w, s, e, n = r.selection_bbox
    assert w < e and s < n and -96 < w < -95 and 29 < s < 30  # lon/lat order


def test_region_definition_rejects_lat_lon_swap():
    base = load_regions()["houston-sw-pilot"].model_dump()
    base["selection_bbox"] = (29.56, -95.66, 29.72, -95.48)  # lat/lon swapped
    with pytest.raises(ValidationError):
        RegionDefinition(**base)
