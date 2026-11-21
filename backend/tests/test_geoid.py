import math

import pandas as pd
import pytest

from pipeline.processing.geoid import InvalidGeoidError, normalize_geoid_series, normalize_tract_geoid, split_geoid


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("48201410100", "48201410100"),
        ("1400000US48201410100", "48201410100"),
        ("14000US48201410100", "48201410100"),
        (48201410100, "48201410100"),
        (48201410100.0, "48201410100"),
        ("48201410100.0", "48201410100"),
        ("6037101110", "06037101110"),  # California: leading zero dropped
        (6037101110, "06037101110"),
        (" 48201-410100 ", "48201410100"),
    ],
)
def test_normalize_variants(raw, expected):
    assert normalize_tract_geoid(raw) == expected


@pytest.mark.parametrize("raw", [None, math.nan, "", "482014101", "482014101001", "48201ABC100", 1.5, "0500000US48201"])
def test_invalid_geoids_raise(raw):
    with pytest.raises(InvalidGeoidError):
        normalize_tract_geoid(raw)


def test_short_but_ten_digits_is_padded_not_rejected():
    # 10 digits is only valid as a dropped leading zero.
    assert normalize_tract_geoid("1001020100") == "01001020100"


def test_series_and_split():
    s = normalize_geoid_series(pd.Series(["1400000US48157670300", 48201410100]))
    assert s.tolist() == ["48157670300", "48201410100"]
    assert split_geoid("48157670300") == ("48", "157", "670300")
