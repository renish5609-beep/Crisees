import math

import numpy as np
import pandas as pd

from pipeline.processing.demographics import _clean, build_indicators, percent, read_table
from tests.fixtures.synthetic import GEOIDS, synthetic_acs_tables


def _df():
    return build_indicators(synthetic_acs_tables(GEOIDS), GEOIDS, "v", "synthetic").set_index("geoid")


def test_basic_counts_and_percentages():
    df = _df()
    t1 = df.loc["48201990100"]
    assert t1["total_population"] == 1000
    assert t1["households_no_vehicle"] == 40
    assert t1["pct_households_no_vehicle"] == 10.0
    assert t1["population_below_poverty"] == 100  # C17002 lines 2+3
    assert t1["population_below_150pct_poverty"] == 120  # lines 2-5
    assert t1["population_65_plus"] == 120  # 12 age cells x 10
    assert t1["pct_65_plus"] == 12.0
    assert t1["population_with_disability"] == 100  # lines 3,4,7,8,11,12


def test_sentinel_is_missing_not_zero():
    df = _df()
    t4 = df.loc["48157990400"]
    assert pd.isna(t4["poverty_universe"])
    assert pd.isna(t4["pct_below_poverty"])
    assert any(f.startswith("poverty_universe:estimate_not_computable") for f in t4["missing_fields"])
    # Other indicators for the same tract are still present.
    assert t4["total_population"] == 800


def test_zero_denominator_gives_null_and_flag():
    t3 = _df().loc["48157990300"]
    assert t3["households_total"] == 0
    assert pd.isna(t3["pct_households_no_vehicle"])
    assert "zero_denominator:pct_households_no_vehicle" in t3["quality_flags"]


def test_numerator_exceeding_denominator_is_flagged():
    tables = synthetic_acs_tables(GEOIDS)
    tables["B08201"].loc["48201990100", "B08201_E002"] = 9999
    df = build_indicators(tables, GEOIDS, "v", "s").set_index("geoid")
    row = df.loc["48201990100"]
    assert pd.isna(row["pct_households_no_vehicle"])
    assert "numerator_exceeds_denominator:pct_households_no_vehicle" in row["quality_flags"]


def test_moe_root_sum_of_squares():
    t1 = _df().loc["48201990100"]
    assert math.isclose(t1["population_below_poverty_moe"], math.sqrt(2 * 10**2))
    assert math.isclose(t1["population_65_plus_moe"], math.sqrt(12 * 10**2))


def test_tract_absent_from_acs_is_all_missing():
    df = build_indicators(synthetic_acs_tables(GEOIDS), GEOIDS + ["48201999999"], "v", "s").set_index("geoid")
    row = df.loc["48201999999"]
    assert pd.isna(row["total_population"]) and pd.isna(row["pct_65_plus"])
    assert "tract_absent_from_acs" in row["quality_flags"]


def test_b17001_poverty_fallback_leaves_150pct_null():
    tables = synthetic_acs_tables(GEOIDS)
    c = tables.pop("C17002")
    b = pd.DataFrame(index=c.index)
    b["B17001_E001"], b["B17001_M001"] = c["C17002_E001"], 5
    b["B17001_E002"], b["B17001_M002"] = c["C17002_E002"] + c["C17002_E003"], 5
    tables["B17001"] = b
    df = build_indicators(tables, GEOIDS, "v", "s").set_index("geoid")
    assert df.loc["48201990100", "population_below_poverty"] == 100
    assert df["population_below_150pct_poverty"].isna().all()
    assert any("table_unavailable:C17002" in f for f in df.loc["48201990100", "missing_fields"])


def test_clean_and_percent_helpers():
    vals, why = _clean(pd.Series([5.0, -666666666, np.nan, -555555555]))
    assert vals.tolist()[0] == 5.0 and vals.isna().tolist() == [False, True, True, True]
    assert why.tolist()[1:] == ["estimate_not_computable", "blank", "moe_controlled"]
    pct = percent(pd.Series([1.0, 1.0, np.nan]), pd.Series([4.0, 0.0, 2.0]))
    assert pct.iloc[0] == 25.0 and pct.iloc[1:].isna().all()


def test_read_table_normalizes_geo_id(tmp_path):
    p = tmp_path / "t.psv"
    p.write_text("GEO_ID|B01003_E001|B01003_M001\n1400000US48201990100|1000|-555555555\n")
    df = read_table(p)
    assert df.index.tolist() == ["48201990100"]
    assert df.loc["48201990100", "B01003_E001"] == 1000
