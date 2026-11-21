"""Helpers to turn (Geo)DataFrames into JSON-safe records and GeoJSON features."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from app.schemas.common import PageInfo


def clean_value(value: Any) -> Any:
    """Convert numpy/pandas scalars to Python; NaN/NA -> None."""
    if value is None:
        return None
    if isinstance(value, (np.ndarray, list, tuple)):
        return [clean_value(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_value(v) for k, v in value.items()}
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def row_to_dict(row: pd.Series, columns: Iterable[str]) -> dict[str, Any]:
    return {c: clean_value(row[c]) for c in columns if c in row.index}


def geometry_to_geojson(geom: BaseGeometry | None, precision: int = 6) -> dict[str, Any] | None:
    if geom is None or geom.is_empty:
        return None
    gj = mapping(geom)

    def _round(coords: Any) -> Any:
        if isinstance(coords, (float, int)):
            return round(float(coords), precision)
        return [_round(c) for c in coords]

    if "coordinates" in gj:
        gj = {"type": gj["type"], "coordinates": _round(gj["coordinates"])}
    return gj


def paginate(df: pd.DataFrame, limit: int, offset: int) -> tuple[pd.DataFrame, PageInfo]:
    total = len(df)
    page = df.iloc[offset : offset + limit]
    next_offset = offset + limit if offset + limit < total else None
    return page, PageInfo(total=total, limit=limit, offset=offset, returned=len(page), next_offset=next_offset)
