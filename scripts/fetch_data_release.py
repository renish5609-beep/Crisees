#!/usr/bin/env python3
"""Fetch and install a processed-data release artifact (checksum verified).

Environment (or flags):
    CRISEES_DATA_URL      URL of crisees-data-<region>-<stamp>.tar.gz (https:// or file://)
    CRISEES_DATA_SHA256   expected SHA-256 of the archive (required)

Idempotent: if the installed manifest already came from the same checksum it
does nothing. Extraction goes to a temporary directory and is moved into
place only after validation, so a failed download never leaves partial data.
"""

from __future__ import annotations

import argparse
import os
import sys

import _bootstrap  # noqa: F401

from app.core.config import get_settings
from pipeline.context import PipelineContext
from pipeline.release import ReleaseError, install_release, installed
from pipeline.validate import validate


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default=os.environ.get("CRISEES_REGION", "houston-sw-pilot"))
    p.add_argument("--url", default=os.environ.get("CRISEES_DATA_URL"))
    p.add_argument("--sha256", default=os.environ.get("CRISEES_DATA_SHA256"))
    args = p.parse_args()
    if not args.url or not args.sha256:
        print("CRISEES_DATA_URL and CRISEES_DATA_SHA256 are both required.", file=sys.stderr)
        return 2
    settings = get_settings()
    if installed(settings, args.region, args.sha256):
        print(f"data release {args.sha256[:12]} already installed")
        return 0
    try:
        install_release(settings, args.region, args.url, args.sha256)
    except ReleaseError as exc:
        print(f"{exc}. Not installing.", file=sys.stderr)
        return 3
    results = validate(PipelineContext.for_region(args.region, settings=settings))
    bad = [r for r in results if not r.ok]
    for r in bad:
        print(f"INVALID {r.dataset}: {r.errors}", file=sys.stderr)
    print(f"installed data release {args.sha256[:12]}: {len(results) - len(bad)}/{len(results)} datasets valid")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
