#!/usr/bin/env python3
"""Validate processed datasets (schemas, CRS, identifiers, ranges, provenance).

Exit code is non-zero if any dataset fails validation.
"""

from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401

from app.core.config import get_settings
from app.core.logging import configure_logging
from pipeline.context import PipelineContext
from pipeline.validate import validate


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--region", default="houston-sw-pilot")
    args = p.parse_args()
    configure_logging(get_settings().log_level)
    results = validate(PipelineContext.for_region(args.region))
    width = max(len(r.dataset) for r in results)
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        count = "-" if r.record_count is None else f"{r.record_count:,}"
        print(f"{status} {r.dataset:<{width}} {count:>10}")
        for e in r.errors:
            print(f"       error:   {e}")
        for w in r.warnings:
            print(f"       warning: {w}")
    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} datasets valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
