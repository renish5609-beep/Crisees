"""ACS demographic indicators and CDC SVI vulnerability variables per tract."""

from __future__ import annotations

from app.core.errors import DatasetNotAvailableError
from app.schemas.census import DemographicIndicators, TractDemographics, VulnerabilityIndicators
from app.schemas.common import RecordPage
from app.services.repository import DataRepository
from app.services.serialization import clean_value, paginate

DEMO_FIELDS = list(DemographicIndicators.model_fields)
VULN_FIELDS = list(VulnerabilityIndicators.model_fields)


def _as_list(value: object) -> list[str]:
    value = clean_value(value)
    if value is None:
        return []
    return [str(v) for v in value]


def demographics_page(
    repo: DataRepository,
    region_id: str,
    limit: int,
    offset: int,
    geoid: str | None = None,
    include_vulnerability: bool = True,
) -> RecordPage[TractDemographics]:
    demo = repo.load(region_id, "demographics")
    vuln = None
    if include_vulnerability:
        try:
            vuln = repo.load(region_id, "vulnerability").set_index("geoid")
        except DatasetNotAvailableError:
            vuln = None  # demographics remain useful without SVI
    if geoid:
        demo = demo[demo["geoid"] == geoid]
    demo = demo.sort_values("geoid")
    page, info = paginate(demo, limit, offset)
    records: list[TractDemographics] = []
    for _, row in page.iterrows():
        d = {f: clean_value(row.get(f)) for f in DEMO_FIELDS}
        d["missing_fields"] = _as_list(row.get("missing_fields"))
        d["quality_flags"] = _as_list(row.get("quality_flags"))
        v_model = None
        if vuln is not None and row["geoid"] in vuln.index:
            v_row = vuln.loc[row["geoid"]]
            v = {f: clean_value(v_row.get(f)) for f in VULN_FIELDS if f != "geoid"}
            v["missing_fields"] = _as_list(v_row.get("missing_fields"))
            v_model = VulnerabilityIndicators(geoid=row["geoid"], **v)
        records.append(TractDemographics(demographics=DemographicIndicators(**d), vulnerability=v_model))
    sources = repo.sources(region_id, "demographics")
    if vuln is not None:
        sources += repo.sources(region_id, "vulnerability")
    return RecordPage[TractDemographics](
        records=records, page=info, provenance=repo.provenance(region_id, "demographics"), sources=sources
    )
