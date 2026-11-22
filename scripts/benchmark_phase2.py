#!/usr/bin/env python3
"""Measure Phase 2 engine performance and print the demonstration results.

Runs the real API in-process (FastAPI TestClient) against data/processed/.
Cold timings start from empty caches. Usage:

    python scripts/benchmark_phase2.py [--region houston-sw-pilot] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import time

import _bootstrap  # noqa: F401

from fastapi.testclient import TestClient

from app.core.logging import configure_logging
from app.engine import service
from app.engine.context import clear_engines
from app.main import create_app


def timed(client: TestClient, method: str, path: str, body: dict | None = None) -> tuple[float, dict]:
    t0 = time.perf_counter()
    r = client.request(method, path, json=body)
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
    return dt, r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="houston-sw-pilot")
    p.add_argument("--json", help="write raw results to this file")
    args = p.parse_args()
    configure_logging("WARNING")
    clear_engines()
    service.clear_caches()
    c = TestClient(create_app())
    R = f"/api/v1/regions/{args.region}"
    rows = []

    def bench(label: str, method: str, path: str, body: dict | None = None) -> dict:
        dt, out = timed(c, method, path, body)
        rows.append((label, round(dt, 3), out.get("cache", "-") if isinstance(out, dict) else "-"))
        return out

    bench("evaluate severe (cold: engine build + baseline + severe)", "POST", f"{R}/scenarios/evaluate", {"scenario": "severe"})
    bench("evaluate severe (cached)", "POST", f"{R}/scenarios/evaluate", {"scenario": "severe"})
    bench("evaluate moderate (warm engine)", "POST", f"{R}/scenarios/evaluate", {"scenario": "moderate"})
    bench("accessibility severe (151 tracts + geometry)", "POST", f"{R}/accessibility/analyze", {"scenario": "severe"})
    opt = bench("optimize severe, defaults (12 hubs)", "POST", f"{R}/optimize", {"scenario": "severe"})
    for hubs in (20, 40):
        bench(f"optimize severe, {hubs} hubs", "POST", f"{R}/optimize", {"scenario": "severe", "resources": {"max_active_hubs": hubs}})
    bench("optimize severe, 12 hubs, fluid trips", "POST", f"{R}/optimize", {"scenario": "severe", "solver": {"integer_trips": False}})
    cmp_ = bench("compare (5 counterfactual solves)", "POST", f"{R}/compare", {})
    bench("compare (cached)", "POST", f"{R}/compare", {})

    print(f"\nPlatform: {platform.processor() or platform.machine()}, Python {platform.python_version()}")
    print("\n| Operation | Seconds | Cache |\n| --- | ---: | --- |")
    for label, dt, cache in rows:
        print(f"| {label} | {dt:.3f} | {cache} |")
    s = opt["solver"]
    print(f"\nDefault optimisation: status={s['status']} gap={s['mip_gap']} solve={s['solve_seconds']}s "
          f"build={s['build_seconds']}s size={s['model_size']}")
    print("\nComparison cases:")
    print("| Case | Served | Unmet | Coverage | Weighted unmet (equity w) | Hubs | Trips | Fleet use | T1 cov | T2 cov | T3 cov | Status |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for case in cmp_["cases"]:
        t, d = case["totals"], case["distribution_by_priority_tercile"]
        print(f"| {case['case']} | {t['served']:,.1f} | {t['unmet']:,.1f} | {t['coverage']:.4f} | "
              f"{t['weighted_unmet_equity_weights']:,.1f} | {t['active_hubs']} | {t['vehicle_trips']} | "
              f"{t['fleet_utilization'] if t['fleet_utilization'] is not None else '-'} | "
              f"{d['tercile_1']['coverage']} | {d['tercile_2']['coverage']} | {d['tercile_3']['coverage']} | "
              f"{case['solver_status']} (gap {case['mip_gap']}) |")
    print("\nDeltas:", json.dumps(cmp_["deltas"], indent=1))
    print("\nFindings:", *cmp_["findings"], sep="\n- ")
    print("\nAccessibility change:", json.dumps(cmp_["accessibility_change"], indent=1))
    print("\nBinding constraints (equity case):", cmp_["cases"][2]["binding_constraints"])
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"timings": rows, "optimize": opt, "compare": cmp_}, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
