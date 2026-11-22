#!/usr/bin/env python3
"""Download raw datasets for a region (idempotent; cached files are reused).

Examples:
    python scripts/download_data.py --region houston-sw-pilot
    python scripts/download_data.py --region houston-sw-pilot --only roads facilities --force
    python scripts/download_data.py --road-provider overture
"""

from __future__ import annotations

import argparse
import json
import sys

import _bootstrap  # noqa: F401

from app.core.config import get_settings
from app.core.logging import configure_logging
from pipeline.context import PipelineContext
from pipeline.run import STEPS, download


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default="houston-sw-pilot")
    p.add_argument("--only", nargs="+", choices=STEPS, help="Subset of sources to download")
    p.add_argument("--force", action="store_true", help="Re-download even if cached")
    p.add_argument("--road-provider", choices=["auto", "osmnx", "overture"], default="auto")
    p.add_argument("--facility-provider", choices=["auto", "osm", "overture"], default="auto")
    p.add_argument("--flood-provider", choices=["auto", "fema_official", "fema_mirror_48157C"], default="auto")
    args = p.parse_args()
    configure_logging(get_settings().log_level)
    ctx = PipelineContext.for_region(args.region, force=args.force)
    reports = download(ctx, tuple(args.only or STEPS), args.road_provider, args.facility_provider, args.flood_provider)
    print(json.dumps(reports, indent=2, default=str))
    failed = [r for r in reports if r["status"] != "ok"]
    if failed:
        print(f"\n{len(failed)} source(s) unavailable; see docs/DATA_SOURCES.md for fallbacks.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
