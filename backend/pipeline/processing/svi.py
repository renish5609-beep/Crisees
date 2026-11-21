"""Normalise CDC SVI tract records. -999 (CDC 'no data') becomes NaN."""

from __future__ import annotations

from pathlib import Path


import pandas as pd

from pipeline.processing.geoid import normalize_geoid_series

FIELD_MAP = {
    "RPL_THEMES": "rpl_themes",
    "RPL_THEME1": "rpl_theme1_socioeconomic",
    "RPL_THEME2": "rpl_theme2_household",
    "RPL_THEME3": "rpl_theme3_minority_language",
    "RPL_THEME4": "rpl_theme4_housing_transport",
    "EP_POV150": "ep_pov150", "EP_UNEMP": "ep_unemp", "EP_NOHSDP": "ep_nohsdp", "EP_UNINSUR": "ep_uninsur",
    "EP_AGE65": "ep_age65", "EP_AGE17": "ep_age17", "EP_DISABL": "ep_disabl", "EP_SNGPNT": "ep_sngpnt",
    "EP_LIMENG": "ep_limeng", "EP_MINRTY": "ep_minrty", "EP_MUNIT": "ep_munit", "EP_MOBILE": "ep_mobile",
    "EP_CROWD": "ep_crowd", "EP_NOVEH": "ep_noveh", "EP_GROUPQ": "ep_groupq", "F_TOTAL": "f_total",
}
CDC_MISSING = -999


def process_svi(path: Path, geoids: list[str], svi_year: int, source_id: str) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(path, dtype={"FIPS": str, "STCNTY": str})
    raw["geoid"] = normalize_geoid_series(raw["FIPS"])
    raw = raw.drop_duplicates("geoid").set_index("geoid")
    wanted = pd.Index(sorted(geoids), name="geoid")
    matched = wanted.intersection(raw.index)
    df = raw.reindex(matched)[list(FIELD_MAP)].rename(columns=FIELD_MAP)
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.where(df != CDC_MISSING)
    df.loc[:, df.columns.str.startswith("rpl_")] = df.loc[:, df.columns.str.startswith("rpl_")].where(
        lambda x: (x >= 0) & (x <= 1)
    )
    df["f_total"] = df["f_total"].round().astype("Int64")
    df["missing_fields"] = [
        [c for c in FIELD_MAP.values() if pd.isna(row[c])] for _, row in df.iterrows()
    ]
    df["svi_year"] = svi_year
    df["svi_geography"] = "US-wide percentile ranking"
    df["source_id"] = source_id
    stats = {
        "tracts_requested": len(wanted),
        "tracts_matched": len(matched),
        "unmatched_geoids": sorted(set(wanted) - set(matched)),
        "match_rate": round(len(matched) / max(len(wanted), 1), 4),
    }
    return df.reset_index(), stats


