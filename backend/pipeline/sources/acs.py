"""American Community Survey 5-year tract tables.

Two interchangeable retrieval methods produce identical raw CSVs
(``GEO_ID|<TABLE>_E001|<TABLE>_M001|...``) restricted to the region's counties:

1. Census Data API (``api.census.gov``): used when ``CENSUS_API_KEY`` is set.
2. ACS table-based Summary File on ``www2.census.gov`` (no key required):
   national per-table files streamed and filtered to the state's tracts.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from pathlib import Path

from pipeline.context import PipelineContext
from pipeline.http import SourceUnavailableError, download_file, session, write_sidecar
from pipeline.sources import catalog

logger = logging.getLogger(__name__)

# table -> number of lines (cells) in the table
ACS_TABLES: dict[str, int] = {
    "B01003": 1,  # Total population
    "B01001": 49,  # Sex by age (65+ = lines 20-25, 44-49)
    "B08201": 30,  # Household size by vehicles available (002 = no vehicle)
    "C17002": 8,  # Ratio of income to poverty level
    "C18108": 13,  # Age by number of disabilities (civilian noninstitutionalized)
}
# Poverty is required, but either table can supply it. C17002 is preferred
# (it also gives <150% of poverty); B17001 gives the below-poverty count only.
POVERTY_TABLES = ("C17002", "B17001")
ACS_TABLES_OPTIONAL = {"B17001": 59}


def table_path(ctx: PipelineContext, table: str) -> Path:
    y = ctx.region.acs_year
    return ctx.shared_raw / "acs" / f"acs5_{y}_{table.lower()}_tracts_{ctx.region.state_fips}.psv"


def _summary_file_url(year: int, table: str) -> str:
    return (
        f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}/table-based-SF/data/5YRData/"
        f"acsdt5y{year}-{table.lower()}.dat"
    )


def _download_summary_file(ctx: PipelineContext, table: str) -> Path:
    prefix = f"1400000US{ctx.region.state_fips}".encode()
    return download_file(
        _summary_file_url(ctx.region.acs_year, table),
        table_path(ctx, table),
        force=ctx.force,
        line_filter=lambda line: line.startswith(prefix),
        expect_prefix=b"GEO_ID|",
        method="summary_file",
        table=table,
        filter=f"GEO_ID startswith {prefix.decode()} (all tracts in state)",
        source=catalog.acs5(ctx.region.acs_year, "summary_file"),
    )


def _download_api(ctx: PipelineContext, table: str, key: str) -> Path:
    dest = table_path(ctx, table)
    if dest.exists() and not ctx.force:
        return dest
    n = {**ACS_TABLES, **ACS_TABLES_OPTIONAL}[table]
    variables = [f"{table}_{i:03d}{t}" for i in range(1, n + 1) for t in ("E", "M")]
    url = f"https://api.census.gov/data/{ctx.region.acs_year}/acs/acs5"
    rows: list[list[str]] = []
    for county in ctx.region.county_fips:
        params = {
            "get": ",".join(["GEO_ID"] + variables),
            "for": "tract:*",
            "in": f"state:{ctx.region.state_fips} county:{county}",
            "key": key,
        }
        r = session().get(url, params=params, timeout=(15, 120))
        if r.status_code != 200 or not r.text.startswith("["):
            raise SourceUnavailableError(f"Census API HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        cols = data[0]
        for rec in data[1:]:
            row = dict(zip(cols, rec))
            rows.append([row["GEO_ID"]] + [row[v] for v in variables])
    # Reformat to Summary File layout: TABLE_E001 / TABLE_M001 column naming
    header = ["GEO_ID"] + [f"{table}_{t}{i:03d}" for i in range(1, n + 1) for t in ("E", "M")]
    dest.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="|", lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    dest.write_text(buf.getvalue())
    write_sidecar(dest, url=url, method="census_api", table=table, source=catalog.acs5(ctx.region.acs_year, "census_api"))
    return dest


def _download_one(ctx: PipelineContext, table: str, key: str) -> Path:
    if key:
        try:
            return _download_api(ctx, table, key)
        except SourceUnavailableError as exc:
            logger.warning("Census API failed for %s (%s); falling back to Summary File", table, exc)
    return _download_summary_file(ctx, table)


def poverty_table(ctx: PipelineContext) -> str | None:
    """The poverty table actually available on disk, in preference order."""
    for t in POVERTY_TABLES:
        if table_path(ctx, t).exists():
            return t
    return None


def download_acs(ctx: PipelineContext) -> dict[str, Path]:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    out: dict[str, Path] = {}
    for table in ACS_TABLES:
        if table in POVERTY_TABLES:
            continue
        out[table] = _download_one(ctx, table, key)
    errors = []
    for table in POVERTY_TABLES:
        try:
            out[table] = _download_one(ctx, table, key)
            break
        except SourceUnavailableError as exc:
            logger.warning("Poverty table %s unavailable: %s", table, exc)
            errors.append(f"{table}: {exc}")
    else:
        raise SourceUnavailableError("No poverty table available: " + "; ".join(errors))
    return out
