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
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import _bootstrap  # noqa: F401

from app.core.config import get_settings
from pipeline.context import PipelineContext
from pipeline.validate import validate

MARKER = ".release_sha256"


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
    dest = settings.processed_dir / args.region
    marker = dest / MARKER
    if marker.exists() and marker.read_text().strip() == args.sha256.lower():
        print(f"data release {args.sha256[:12]} already installed")
        return 0
    with tempfile.TemporaryDirectory(dir=settings.data_dir) as tmp:
        archive = Path(tmp) / "release.tar.gz"
        print(f"downloading {args.url}")
        with urllib.request.urlopen(args.url, timeout=300) as r, archive.open("wb") as fh:  # noqa: S310 - URL from operator config
            shutil.copyfileobj(r, fh)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != args.sha256.lower():
            print(f"CHECKSUM MISMATCH: expected {args.sha256}, got {digest}. Not installing.", file=sys.stderr)
            return 3
        extract = Path(tmp) / "x"
        with tarfile.open(archive) as tar:
            members = [m for m in tar.getmembers() if m.isfile() and m.name.startswith(f"{args.region}/")
                       and ".." not in Path(m.name).parts and not Path(m.name).is_absolute()]
            tar.extractall(extract, members=members, filter="data")
        staged = extract / args.region
        if not (staged / "manifest.json").exists():
            print("archive has no manifest.json for this region", file=sys.stderr)
            return 4
        (staged / MARKER).write_text(args.sha256.lower())
        dest.parent.mkdir(parents=True, exist_ok=True)
        backup = dest.with_name(dest.name + ".old")
        if dest.exists():
            shutil.rmtree(backup, ignore_errors=True)
            dest.rename(backup)
        shutil.move(str(staged), str(dest))
        shutil.rmtree(backup, ignore_errors=True)
    results = validate(PipelineContext.for_region(args.region, settings=settings))
    bad = [r for r in results if not r.ok]
    for r in bad:
        print(f"INVALID {r.dataset}: {r.errors}", file=sys.stderr)
    print(f"installed data release {args.sha256[:12]}: {len(results) - len(bad)}/{len(results)} datasets valid")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
