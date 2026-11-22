#!/usr/bin/env python3
"""Process raw downloads into the standardized datasets in data/processed/<region>/.

Example:
    python scripts/process_data.py --region houston-sw-pilot
"""

from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401

from app.core.config import get_settings
from app.core.logging import configure_logging
from pipeline.context import PipelineContext
from pipeline.run import STEPS, process


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default="houston-sw-pilot")
    p.add_argument("--only", nargs="+", choices=STEPS)
    args = p.parse_args()
    configure_logging(get_settings().log_level)
    ctx = PipelineContext.for_region(args.region)
    reports = process(ctx, tuple(args.only or STEPS))
    print(json.dumps(reports, indent=2, default=str))
    return 0 if all(r["status"] == "ok" for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
