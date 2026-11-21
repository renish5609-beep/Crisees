"""Census tract GEOID normalisation.

Canonical form: 11-character string ``SSCCCTTTTTT`` (state 2 + county 3 +
tract 6), digits only, zero padded. Accepts the common variants found in
Census products and third-party copies:

* ``"48201410100"`` (canonical)
* ``"1400000US48201410100"`` (ACS / data.census.gov ``GEO_ID``)
* ``48201410100`` / ``48201410100.0`` (numeric, e.g. from CSV type inference)
* ``"6037101110"`` (leading zero lost: state 06 -> 10 digits)
* ``"48201-410100"`` / ``"48 201 410100"`` (separators)
"""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

_ACS_PREFIX = re.compile(r"^1400000US", re.IGNORECASE)
_SUMMARY_PREFIX = re.compile(r"^14000US", re.IGNORECASE)


class InvalidGeoidError(ValueError):
    pass


def normalize_tract_geoid(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise InvalidGeoidError("GEOID is missing")
    if isinstance(value, float):
        if not value.is_integer():
            raise InvalidGeoidError(f"Non-integer numeric GEOID: {value!r}")
        value = int(value)
    text = str(value).strip()
    text = _ACS_PREFIX.sub("", text)
    text = _SUMMARY_PREFIX.sub("", text)
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    text = re.sub(r"[\s\-_]", "", text)
    if not text.isdigit():
        raise InvalidGeoidError(f"GEOID contains non-digit characters: {value!r}")
    if len(text) == 10:
        text = text.zfill(11)
    if len(text) != 11:
        raise InvalidGeoidError(f"Tract GEOID must have 11 digits, got {len(text)}: {value!r}")
    return text


def normalize_geoid_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_tract_geoid)


def split_geoid(geoid: str) -> tuple[str, str, str]:
    g = normalize_tract_geoid(geoid)
    return g[:2], g[2:5], g[5:]
