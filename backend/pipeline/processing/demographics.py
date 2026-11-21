"""ACS tract indicators with explicit missing-value handling.

Rules (documented in docs/DATA_DICTIONARY.md):

* ACS Summary File annotation sentinels (negative codes such as
  -666666666) and blanks become ``NaN`` (never 0); the affected field is
  recorded in ``missing_fields`` with the reason.
* Derived counts (sums of table cells) are ``NaN`` if any component is NaN.
* MOEs of sums use the Census root-sum-of-squares approximation.
* Percentages are 0-100, rounded to 2 dp, and ``NaN`` when the denominator
  is missing or zero (flag ``zero_denominator:<field>``).
* A numerator greater than its denominator is flagged and the percentage
  is set to ``NaN`` rather than reported above 100.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.processing.geoid import normalize_geoid_series

logger = logging.getLogger(__name__)

# ACS Summary File / API annotation values (estimates and MOEs).
ANNOTATIONS: dict[int, str] = {
    -666666666: "estimate_not_computable",
    -999999999: "insufficient_sample",
    -888888888: "not_applicable",
    -222222222: "moe_not_computable",
    -333333333: "median_open_interval",
    -555555555: "moe_controlled",
    -111111111: "median_open_lower",
    -444444444: "insufficient_sample_moe",
}

AGE65_LINES = list(range(20, 26)) + list(range(44, 50))


def read_table(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="|", dtype=str)
    df["geoid"] = normalize_geoid_series(df["GEO_ID"])
    df = df.drop(columns=["GEO_ID"]).set_index("geoid")
    out = df.apply(pd.to_numeric, errors="coerce")
    return out


def _clean(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (values with sentinels -> NaN, reason series)."""
    reason = pd.Series(pd.NA, index=series.index, dtype="object")
    for code, label in ANNOTATIONS.items():
        reason[series == code] = label
    reason[series.isna()] = "blank"
    cleaned = series.where(series >= 0)
    return cleaned, reason


def _cells(df: pd.DataFrame, table: str, lines: list[int], kind: str = "E") -> pd.DataFrame:
    cols = [f"{table}_{kind}{i:03d}" for i in lines]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"ACS table {table} missing columns {missing[:5]}")
    return df[cols]


def _sum_cells(df: pd.DataFrame, table: str, lines: list[int]) -> tuple[pd.Series, pd.Series]:
    est = _cells(df, table, lines, "E").where(lambda x: x >= 0)
    moe = _cells(df, table, lines, "M").where(lambda x: x >= 0)
    total = est.sum(axis=1, min_count=len(lines))
    total[est.isna().any(axis=1)] = np.nan
    moe_total = np.sqrt((moe**2).sum(axis=1, min_count=len(lines)))
    moe_total[moe.isna().any(axis=1)] = np.nan
    return total, moe_total


def percent(num: pd.Series, den: pd.Series) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = (100.0 * num / den).round(2)
    pct[(den == 0) | den.isna() | num.isna() | (num > den)] = np.nan
    return pct


def build_indicators(tables: dict[str, pd.DataFrame], geoids: list[str], vintage: str, source_id: str) -> pd.DataFrame:
    idx = pd.Index(sorted(geoids), name="geoid")
    t = {k: v.reindex(idx) for k, v in tables.items()}
    out = pd.DataFrame(index=idx)
    reasons: dict[str, pd.Series] = {}

    def single(table: str, line: int, name: str) -> None:
        est, why = _clean(t[table][f"{table}_E{line:03d}"])
        moe, _ = _clean(t[table][f"{table}_M{line:03d}"])
        out[name] = est
        out[f"{name}_moe"] = moe
        reasons[name] = why

    single("B01003", 1, "total_population")
    single("B08201", 1, "households_total")
    single("B08201", 2, "households_no_vehicle")
    single("C18108", 1, "disability_universe")

    # Poverty: C17002 preferred; B17001 (same universe) as a fallback.
    table_reason: dict[str, str] = {}
    if "C17002" in t:
        single("C17002", 1, "poverty_universe")
        pov, pov_moe = _sum_cells(t["C17002"], "C17002", [2, 3])
        pov150, _ = _sum_cells(t["C17002"], "C17002", [2, 3, 4, 5])
    elif "B17001" in t:
        single("B17001", 1, "poverty_universe")
        pov, pov_moe = _sum_cells(t["B17001"], "B17001", [2])
        pov150 = pd.Series(np.nan, index=idx)
        table_reason["population_below_150pct_poverty"] = "table_unavailable:C17002"
    else:
        raise KeyError("No poverty table (C17002 or B17001) supplied")
    out["population_below_poverty"], out["population_below_poverty_moe"] = pov, pov_moe
    out["population_below_150pct_poverty"] = pov150
    old, old_moe = _sum_cells(t["B01001"], "B01001", AGE65_LINES)
    out["population_65_plus"], out["population_65_plus_moe"] = old, old_moe
    dis, dis_moe = _sum_cells(t["C18108"], "C18108", [3, 4, 7, 8, 11, 12])
    out["population_with_disability"], out["population_with_disability_moe"] = dis, dis_moe
    for name in ["population_below_poverty", "population_below_150pct_poverty", "population_65_plus",
                 "population_with_disability"]:
        why = table_reason.get(name, "component_missing")
        reasons[name] = pd.Series(np.where(out[name].isna(), why, pd.NA), index=idx, dtype="object")

    pairs = {
        "pct_households_no_vehicle": ("households_no_vehicle", "households_total"),
        "pct_below_poverty": ("population_below_poverty", "poverty_universe"),
        "pct_below_150pct_poverty": ("population_below_150pct_poverty", "poverty_universe"),
        "pct_65_plus": ("population_65_plus", "total_population"),
        "pct_with_disability": ("population_with_disability", "disability_universe"),
    }
    flags: dict[str, list[str]] = {g: [] for g in idx}
    for pct_name, (num, den) in pairs.items():
        out[pct_name] = percent(out[num], out[den])
        for g in idx[(out[den] == 0).fillna(False).to_numpy()]:
            flags[g].append(f"zero_denominator:{pct_name}")
        for g in idx[(out[num] > out[den]).fillna(False).to_numpy()]:
            flags[g].append(f"numerator_exceeds_denominator:{pct_name}")

    # Consistency check: B01003 total equals B01001 total by construction.
    b01001_total = t["B01001"]["B01001_E001"].where(lambda x: x >= 0)
    mismatch = (b01001_total != out["total_population"]) & b01001_total.notna() & out["total_population"].notna()
    for g in idx[mismatch.to_numpy()]:
        flags[g].append("b01001_b01003_total_mismatch")
    for g in idx[(out["total_population"] == 0).fillna(False).to_numpy()]:
        flags[g].append("zero_population_tract")
    for g in idx[t["B01003"].isna().all(axis=1).to_numpy()]:
        flags[g].append("tract_absent_from_acs")

    missing_fields: dict[str, list[str]] = {g: [] for g in idx}
    for name, why in reasons.items():
        for g, r in why.dropna().items():
            missing_fields[g].append(f"{name}:{r}")
    for pct_name in pairs:
        for g in idx[out[pct_name].isna().to_numpy()]:
            missing_fields[g].append(f"{pct_name}:undefined")

    int_cols = [
        "total_population", "households_total", "households_no_vehicle", "poverty_universe",
        "population_below_poverty", "population_below_150pct_poverty", "population_65_plus",
        "disability_universe", "population_with_disability",
    ]
    for c in int_cols:
        out[c] = out[c].round().astype("Int64")
    out["missing_fields"] = [missing_fields[g] for g in idx]
    out["quality_flags"] = [flags[g] for g in idx]
    out["acs_vintage"] = vintage
    out["source_id"] = source_id
    return out.reset_index()
