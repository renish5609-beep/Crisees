"""Engine C: hypothetical flood-disruption scenarios.

A FEMA regulatory flood zone indicates *potential exposure*, not a confirmed
closure. Scenarios translate exposure into closures with explicit,
HYPOTHETICAL rules and deterministic seeded sampling:

* each *physical segment* (both directions of a two-way road) is sampled once;
* the draw for (seed, rule, segment) comes from SHA-256, so it does not depend
  on processing order, worker count or Python's hash randomisation;
* roads outside the ingested FEMA coverage are never closed by flood rules
  under the default ``no_inference`` policy: they are reported as *unknown*,
  not as safe. ``stress_sample`` is available for sensitivity tests only.

The baseline network arrays are never modified; a scenario is a boolean mask.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.errors import CriseesError
from app.engine.context import RegionEngine


class UnknownEdgeError(CriseesError):
    status_code = 400
    code = "unknown_edge_ids"
from app.engine.params import ScenarioSpec

PRESETS: dict[str, ScenarioSpec] = {
    "baseline": ScenarioSpec(name="baseline"),
    "moderate": ScenarioSpec(
        name="moderate", one_pct_closure_prob=0.6, min_exposed_m=10, overbank_buffer_m=50, overbank_closure_prob=0.15
    ),
    "severe": ScenarioSpec(
        name="severe", one_pct_closure_prob=1.0, min_exposed_m=5, point_two_pct_closure_prob=0.5,
        overbank_buffer_m=150, overbank_closure_prob=0.35,
    ),
}
PRESET_DESCRIPTIONS = {
    "baseline": "No simulated road closures.",
    "moderate": "Hypothetical moderate event: 60% of road segments with >=10 m inside a FEMA 1%-annual-chance "
    "zone close, plus 15% of segments within 50 m of one (overbank).",
    "severe": "Hypothetical severe event (Harvey-like spatial pattern is NOT modelled): every segment with >=5 m "
    "inside a 1% zone closes, 50% of segments in 0.2% zones close, and 35% of segments within 150 m of a 1% "
    "zone close (overbank).",
}


def resolve(spec: ScenarioSpec | str) -> ScenarioSpec:
    if isinstance(spec, str):
        if spec not in PRESETS:
            raise KeyError(spec)
        return PRESETS[spec]
    return spec


def scenario_id(region_id: str, stamp: str, spec: ScenarioSpec) -> str:
    payload = json.dumps({"region": region_id, "data": stamp, "spec": spec.model_dump(mode="json")}, sort_keys=True)
    return "scn_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _uniform(seed: int, rule: str, keys: np.ndarray) -> np.ndarray:
    out = np.empty(len(keys))
    for i, k in enumerate(keys):
        h = hashlib.sha256(f"{seed}|{rule}|{k}".encode()).digest()
        out[i] = int.from_bytes(h[:8], "big") / 2**64
    return out


@dataclass
class ClosureResult:
    closed: np.ndarray  # bool per directed edge
    by_rule: dict[str, int]  # closed segments attributable to each rule (first rule wins)
    unknown_segments: int
    unknown_length_km: float


def segment_table(eng: RegionEngine) -> pd.DataFrame:
    """Per physical segment: stable key and max exposure over its directions (cached)."""
    cached = getattr(eng, "_segment_table", None)
    if cached is not None:
        return cached
    net, exp = eng.net, eng.exposure
    seg = pd.DataFrame({
        "segment_id": net.segment_id,
        "edge_id": net.edge_ids,
        "len": exp["length_m"].to_numpy(),
        "in1": exp["len_in_1pct_m"].to_numpy(),
        "in02": exp["len_in_0_2pct_m"].to_numpy(),
        "cov": exp["len_in_coverage_m"].to_numpy(),
        "dist1": exp["dist_to_1pct_m"].to_numpy() if "dist_to_1pct_m" in exp else np.nan,
    })
    g = seg.groupby("segment_id").agg(len=("len", "max"), in1=("in1", "max"), in02=("in02", "max"),
                                       cov=("cov", "max"), dist1=("dist1", "min"))
    # Stable sampling key: lexicographically smallest directed edge id of the segment.
    keys = seg[["segment_id", "edge_id"]].sort_values("edge_id", kind="stable").drop_duplicates("segment_id")
    g["key"] = keys.set_index("segment_id")["edge_id"].reindex(g.index)
    eng._segment_table = g  # type: ignore[attr-defined]
    return g


def compute_closures(eng: RegionEngine, spec: ScenarioSpec) -> ClosureResult:
    net = eng.net
    g = segment_table(eng)
    closed_seg = pd.Series(False, index=g.index)
    by_rule: dict[str, int] = {}

    def apply(rule: str, eligible: pd.Series, prob: float) -> None:
        if prob <= 0:
            by_rule[rule] = 0
            return
        cand = eligible & ~closed_seg
        idx = cand[cand].index
        draws = _uniform(spec.seed, rule, g.loc[idx, "key"].to_numpy())
        hit = idx[draws < prob]
        closed_seg.loc[hit] = True
        by_rule[rule] = len(hit)

    uncovered = g["cov"] < (g["len"] - 0.5)
    apply("fema_1pct", g["in1"] >= spec.min_exposed_m, spec.one_pct_closure_prob)
    apply("fema_0.2pct", g["in02"] >= spec.min_exposed_m, spec.point_two_pct_closure_prob)
    # Overbank is inferred from proximity, so it only applies where FEMA data
    # describes the whole segment; elsewhere the hazard is unknown.
    apply("overbank", (g["dist1"] <= spec.overbank_buffer_m) & (spec.overbank_buffer_m > 0) & ~uncovered,
          spec.overbank_closure_prob)
    if spec.unknown_coverage_policy == "stress_sample":
        apply("stress_unknown_coverage", uncovered, spec.unknown_closure_prob)
    edge_closed = closed_seg.reindex(net.segment_id).to_numpy()
    if spec.custom_closed_edge_ids:
        custom = np.zeros(net.n_edges, bool)
        try:
            custom[net.edge_index(spec.custom_closed_edge_ids)] = True
        except KeyError as exc:
            raise UnknownEdgeError("custom_closed_edge_ids contains unknown edge ids.", detail=str(exc)) from None
        custom = net.closure_mask_for_segments(custom)
        by_rule["custom"] = int(len(np.unique(net.segment_id[custom & ~edge_closed])))
        edge_closed = edge_closed | custom
    return ClosureResult(
        closed=edge_closed,
        by_rule=by_rule,
        unknown_segments=int(uncovered.sum()),
        unknown_length_km=round(float(g.loc[uncovered, "len"].sum() - g.loc[uncovered, "cov"].sum()) / 1000, 1),
    )
